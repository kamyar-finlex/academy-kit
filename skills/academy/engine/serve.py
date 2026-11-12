#!/usr/bin/env python3
"""Serve a built academy on this computer only, with the local AI features.

  python3 serve.py <academy-folder> [--port 8765] [--open]

It serves the built site on 127.0.0.1 and passes the page's AI requests (translate, visualize,
mind map, ask) to the Ollama running on this computer. Only Ollama's chat call is passed on, so
the page cannot pull, delete or list models. Nothing leaves this machine.
Standard library only. Stop it with Ctrl+C.
"""
import argparse
import http.server
import os
import re
import sys
import urllib.error
import urllib.request
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import Academy  # noqa: E402

OLLAMA = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
if not OLLAMA.startswith("http"):
    OLLAMA = "http://" + OLLAMA


class Handler(http.server.SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):  # quiet
        pass

    def end_headers(self):
        if re.search(r"\.(html|js|css|json|mp4|vtt)$", self.path.split("?")[0]) or self.path.split("?")[0].endswith("/"):
            self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def guess_type(self, path):
        return "text/vtt" if path.endswith(".vtt") else super().guess_type(path)

    def do_POST(self):
        if self.path.split("?")[0].rstrip("/") != "/ai/chat":
            return self.send_error(404)
        n = int(self.headers.get("Content-Length") or 0)
        if n > 256 * 1024:
            return self.send_error(413)
        req = urllib.request.Request(OLLAMA + "/api/chat", data=self.rfile.read(n), headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                body, code = r.read(), r.status
        except urllib.error.HTTPError as e:
            body, code = e.read(), e.code
        except Exception:
            body, code = b'{"error": "Ollama is not reachable on this computer"}', 502
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_head(self):
        """Like the base class, plus single byte ranges, so a video can be scrubbed."""
        rng = re.fullmatch(r"bytes=(\d*)-(\d*)", self.headers.get("Range", "") or "")
        path = self.translate_path(self.path)
        if not rng or not os.path.isfile(path):
            return super().send_head()
        size = os.path.getsize(path)
        a, b = rng.groups()
        start = int(a) if a else max(0, size - int(b or 0))
        end = min(int(b), size - 1) if a and b else size - 1
        if start > end or start >= size:
            self.send_error(416)
            return None
        f = open(path, "rb")
        f.seek(start)
        self.range_left = end - start + 1
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(self.range_left))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        return f

    def copyfile(self, source, outputfile):
        left = getattr(self, "range_left", None)
        if left is None:
            return super().copyfile(source, outputfile)
        self.range_left = None
        while left > 0:
            chunk = source.read(min(64 * 1024, left))
            if not chunk:
                break
            outputfile.write(chunk)
            left -= len(chunk)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("academy", help="the academy folder (with academy.json), or a built site folder")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--open", action="store_true", help="open the browser")
    a = ap.parse_args()
    root = Academy(a.academy).out if os.path.exists(os.path.join(a.academy, "academy.json")) else os.path.abspath(a.academy)
    if not os.path.exists(os.path.join(root, "index.html")):
        sys.exit(f"{root} has no index.html yet. Build first: python3 build.py {a.academy}")
    handler = lambda *x, **k: Handler(*x, directory=root, **k)  # noqa: E731
    try:
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", a.port), handler)
    except OSError:
        sys.exit(f"port {a.port} is in use. Pick another one with --port.")
    url = f"http://localhost:{a.port}/"
    print(f"academy at {url}  (serving {root}; AI requests go to {OLLAMA})")
    if a.open:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

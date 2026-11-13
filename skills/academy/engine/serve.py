#!/usr/bin/env python3
"""Serve a built academy on this computer only, with the local AI features.

  python3 serve.py <academy-folder> [--port 8765] [--open]

It serves the built site on 127.0.0.1 and passes the page's AI requests (translate, visualize,
mind map, ask) to the Ollama running on this computer. Only Ollama's chat call is passed on, so
the page cannot pull, delete or list models. For "Listen" it starts the kit's natural voice
(speak_server.py) when it finds a Python that has Kokoro, and passes the page's /speak requests
to it. Nothing leaves this machine.
Standard library only. Stop it with Ctrl+C.
"""
import argparse
import http.server
import os
import re
import signal
import subprocess
import sys
import urllib.error
import urllib.request
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import Academy  # noqa: E402

OLLAMA = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
if not OLLAMA.startswith("http"):
    OLLAMA = "http://" + OLLAMA
SPEAK = os.environ.get("ACADEMY_SPEAK_URL", "http://127.0.0.1:8770").rstrip("/")
TTS_PY = "~/.local/share/academy-kit/tts/bin/python"


def start_voice(cfg):
    """Start the natural voice next to this server, if it is not running and a Kokoro setup exists."""
    try:
        urllib.request.urlopen(SPEAK + "/voices", timeout=1).read()
        return None, "already running"
    except Exception:
        pass
    sp, vd = cfg.get("speech") or {}, cfg.get("video") or {}
    if cfg.get("speech") is False:
        return None, "off in academy.json"
    py = os.path.expanduser(os.environ.get("ACADEMY_TTS_PYTHON") or sp.get("python") or vd.get("python") or TTS_PY)
    if not os.path.exists(py):
        return None, "no Kokoro setup found (references/LISTEN.md)"
    env = dict(os.environ, HF_HUB_OFFLINE=os.environ.get("HF_HUB_OFFLINE", "1"))
    data = sp.get("espeak_data") or vd.get("espeak_data")
    if data:
        env.setdefault("ACADEMY_ESPEAK_DATA", data)
    args = [py, os.path.join(os.path.dirname(os.path.abspath(__file__)), "speak_server.py"), "--port", SPEAK.rsplit(":", 1)[-1]]
    if sp.get("voice"):
        args += ["--voice", sp["voice"]]
    return subprocess.Popen(args, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL), "starting (ready in a few seconds)"


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

    def relay(self, req, timeout, down):
        """Pass one request to a local service and hand its answer back."""
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body, code, ctype = r.read(), r.status, r.headers.get("Content-Type", "application/json")
        except urllib.error.HTTPError as e:
            body, code, ctype = e.read(), e.code, "application/json"
        except Exception:
            body, code, ctype = down, 502, "application/json"
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        path = self.path.split("?")[0].rstrip("/")
        if path not in ("/ai/chat", "/speak"):
            return self.send_error(404)
        n = int(self.headers.get("Content-Length") or 0)
        if n > 256 * 1024:
            return self.send_error(413)
        data, head = self.rfile.read(n), {"Content-Type": "application/json"}
        if path == "/speak":
            return self.relay(urllib.request.Request(SPEAK + "/speak", data=data, headers=head), 120, b'{"error": "the voice is not running on this computer"}')
        self.relay(urllib.request.Request(OLLAMA + "/api/chat", data=data, headers=head), 180, b'{"error": "Ollama is not reachable on this computer"}')

    def do_GET(self):
        if self.path.split("?")[0].rstrip("/") == "/speak/voices":
            return self.relay(urllib.request.Request(SPEAK + "/voices"), 5, b'{"error": "the voice is not running on this computer"}')
        super().do_GET()

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
    is_academy = os.path.exists(os.path.join(a.academy, "academy.json"))
    ac = Academy(a.academy) if is_academy else None
    root = ac.out if ac else os.path.abspath(a.academy)
    if not os.path.exists(os.path.join(root, "index.html")):
        sys.exit(f"{root} has no index.html yet. Build first: python3 build.py {a.academy}")
    handler = lambda *x, **k: Handler(*x, directory=root, **k)  # noqa: E731
    try:
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", a.port), handler)
    except OSError:
        sys.exit(f"port {a.port} is in use. Pick another one with --port.")
    url = f"http://localhost:{a.port}/"
    voice, voice_note = start_voice(ac.cfg if ac else {})
    print(f"academy at {url}  (serving {root}; AI requests go to {OLLAMA}; natural voice: {voice_note})", flush=True)

    def leave(*_):  # also when the terminal is closed or the process is told to stop: do not leave the voice behind
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, leave)
    if hasattr(signal, "SIGHUP"):
        signal.signal(signal.SIGHUP, leave)
    if a.open:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if voice:
            voice.terminate()


if __name__ == "__main__":
    main()

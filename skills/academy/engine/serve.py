#!/usr/bin/env python3
"""Serve a built academy on this computer only, with local AI and GitHub App Studio.

  python3 serve.py [<academy-folder>] [--port 8765] [--open]

It serves the built site on 127.0.0.1 and:
- proxies /ai/chat to local Ollama and /speak to the local natural voice;
- provides /api/github/* and /api/academy/* endpoints for connecting a GitHub
  organization via a GitHub App, browsing repository files, and generating an
  academy in an external folder. Nothing leaves this machine except the
  explicit GitHub App calls you initiate.
Standard library only. Stop it with Ctrl+C.
"""
import argparse
import http.server
import json
import os
import re
import signal
import subprocess
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ENGINE, Academy  # noqa: E402
import github_app  # noqa: E402
import studio  # noqa: E402

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


class StudioState:
    """Shared server state holding the currently served and connected academies."""

    def __init__(self, academy, root, port):
        self._lock = threading.Lock()
        self.active_academy = academy
        self.connected_academy = academy if (academy and (academy.cfg.get("source") or {}).get("type") == "git") else None
        self.root = root
        self.port = port
        self.jobs = studio.JobManager(OLLAMA, on_built=self.activate)

    def get_root(self):
        with self._lock:
            return self.root

    def activate(self, academy):
        with self._lock:
            self.active_academy = academy
            self.connected_academy = academy
            self.root = academy.out

    def set_connected(self, academy):
        with self._lock:
            self.connected_academy = academy

    def get_connected(self):
        with self._lock:
            return self.connected_academy

    def status_payload(self):
        with self._lock:
            conn = self.connected_academy
            act = self.active_academy
        src = (conn.cfg.get("source") or {}) if conn else {}
        return {
            "app": github_app.public_status(),
            "connected": {
                "academy_dir": conn.dir,
                "title": conn.cfg.get("title", ""),
                "repo": src.get("label") or src.get("repo", ""),
                "repo_url": src.get("repo", ""),
                "branch": src.get("branch", ""),
                "docs_root": src.get("docs_root", ""),
                "installation_id": src.get("installation_id"),
            } if conn else None,
            "active": {
                "academy_dir": act.dir if act else "",
                "title": act.cfg.get("title", "") if act else "",
            },
            "default_workspace": os.path.expanduser(studio.DEFAULT_WORKSPACE),
        }


class Handler(http.server.SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def __init__(self, *args, state=None, **kwargs):
        self.state = state
        super().__init__(*args, directory=state.get_root(), **kwargs)

    def log_message(self, *a):  # quiet
        pass

    def end_headers(self):
        if re.search(r"\.(html|js|css|json|mp4|vtt)$", self.path.split("?")[0]) or self.path.split("?")[0].endswith("/"):
            self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def guess_type(self, path):
        return "text/vtt" if path.endswith(".vtt") else super().guess_type(path)

    def _send_json(self, code, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self, limit=2 * 1024 * 1024):
        n = int(self.headers.get("Content-Length") or 0)
        if n > limit:
            raise ValueError("Request body too large")
        raw = self.rfile.read(n) if n else b"{}"
        return json.loads(raw.decode("utf-8")), raw

    def _base_url(self):
        host = self.headers.get("Host") or f"localhost:{self.state.port}"
        return f"http://{host}"

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
        if path in ("/ai/chat", "/speak"):
            n = int(self.headers.get("Content-Length") or 0)
            if n > 256 * 1024:
                return self.send_error(413)
            data, head = self.rfile.read(n), {"Content-Type": "application/json"}
            if path == "/speak":
                return self.relay(urllib.request.Request(SPEAK + "/speak", data=data, headers=head), 120, b'{"error": "the voice is not running on this computer"}')
            return self.relay(urllib.request.Request(OLLAMA + "/api/chat", data=data, headers=head), 180, b'{"error": "Ollama is not reachable on this computer"}')

        if not path.startswith("/api/"):
            return self.send_error(404)
        try:
            body, raw = self._read_json_body()
            if path == "/api/github/manifest":
                return self._send_json(200, github_app.build_manifest(self._base_url(), body.get("org", ""), body.get("name", "")))
            if path == "/api/github/app":
                return self._send_json(200, github_app.save_manual_config(body.get("app_id", ""), body.get("pem", ""), body.get("webhook_secret", "")))
            if path == "/api/github/app/disconnect":
                github_app.delete_config()
                return self._send_json(200, github_app.public_status())
            if path == "/api/github/connect":
                full_name = (body.get("full_name") or "").strip()
                repo_url = (body.get("repo_url") or "").strip()
                if not repo_url and full_name:
                    repo_url = f"https://github.com/{full_name}.git"
                if not full_name and repo_url:
                    full_name = re.sub(r"^https?://[^/]+/|\.git$", "", repo_url)
                if not repo_url:
                    return self._send_json(400, {"error": "Repository name or URL is required"})
                repo_short = full_name.split("/")[-1] or "repo"
                target_dir = (body.get("academy_dir") or "").strip() or studio.default_academy_dir(repo_short)
                ac, commit = studio.init_or_update_academy(
                    target_dir=target_dir,
                    repo_url=repo_url,
                    full_name=full_name,
                    branch=(body.get("branch") or "").strip(),
                    docs_root=(body.get("docs_root") or "").strip(),
                    installation_id=body.get("installation_id"),
                    title=(body.get("title") or "").strip(),
                    reader=(body.get("reader") or "").strip(),
                    language=(body.get("language") or "English").strip() or "English",
                )
                self.state.set_connected(ac)
                files = studio.scan_repo_files(ac, include_code=bool(body.get("include_code")))
                return self._send_json(200, {
                    "academy_dir": ac.dir,
                    "commit": commit,
                    "files": files,
                    "status": self.state.status_payload(),
                })
            if path == "/api/academy/generate":
                conn = self.state.get_connected()
                if not conn:
                    return self._send_json(400, {"error": "Connect a GitHub repository first"})
                files = body.get("files") or []
                if not files:
                    return self._send_json(400, {"error": "Select at least one file to document"})
                job_id = self.state.jobs.start_generate(
                    academy_dir=conn.dir,
                    files=files,
                    model=(body.get("model") or "").strip(),
                    title=(body.get("title") or "").strip(),
                    reader=(body.get("reader") or "").strip(),
                )
                return self._send_json(202, {"job_id": job_id})
            if path == "/api/github/webhook":
                sig = self.headers.get("X-Hub-Signature-256", "")
                if not github_app.verify_webhook_signature(raw, sig):
                    return self._send_json(401, {"error": "Invalid webhook signature"})
                event = self.headers.get("X-GitHub-Event", "")
                conn = self.state.get_connected()
                if event == "push" and conn:
                    repo_full = ((body.get("repository") or {}).get("full_name") or "").lower()
                    src_label = ((conn.cfg.get("source") or {}).get("label") or "").lower()
                    if repo_full and repo_full == src_label:
                        src = conn.cfg.get("source") or {}
                        github_app.git_clone_or_pull(
                            src.get("repo", ""),
                            conn.path(src.get("clone", "source-repo")),
                            branch=src.get("branch") or None,
                            installation_id=src.get("installation_id"),
                        )
                        return self._send_json(200, {"synced": True})
                return self._send_json(200, {"ignored": True, "event": event})
            return self._send_json(404, {"error": "Unknown endpoint"})
        except Exception as e:
            return self._send_json(400, {"error": str(e)})

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/")
        qs = urllib.parse.parse_qs(parsed.query)
        if path == "/speak/voices":
            return self.relay(urllib.request.Request(SPEAK + "/voices"), 5, b'{"error": "the voice is not running on this computer"}')
        if path.startswith("/api/"):
            try:
                if path == "/api/github/status":
                    return self._send_json(200, self.state.status_payload())
                if path == "/api/github/manifest/callback":
                    code = (qs.get("code") or [""])[0]
                    status = github_app.exchange_manifest_code(code)
                    dest = status.get("install_url") or "/?github_setup=ok"
                    self.send_response(302)
                    self.send_header("Location", dest)
                    self.end_headers()
                    return
                if path == "/api/github/installations":
                    return self._send_json(200, {"installations": github_app.list_installations()})
                if path == "/api/github/repos":
                    inst = (qs.get("installation_id") or [""])[0]
                    if not inst:
                        return self._send_json(400, {"error": "installation_id is required"})
                    return self._send_json(200, {"repos": github_app.list_installation_repos(inst)})
                if path == "/api/github/branches":
                    inst = (qs.get("installation_id") or [""])[0]
                    repo = (qs.get("repo") or [""])[0]
                    if not inst or not repo:
                        return self._send_json(400, {"error": "installation_id and repo are required"})
                    return self._send_json(200, {"branches": github_app.list_repo_branches(inst, repo)})
                if path == "/api/github/files":
                    conn = self.state.get_connected()
                    if not conn:
                        return self._send_json(200, {"files": [], "connected": None})
                    inc = (qs.get("include_code") or ["0"])[0] in ("1", "true", "yes")
                    return self._send_json(200, {
                        "files": studio.scan_repo_files(conn, include_code=inc),
                        "connected": self.state.status_payload()["connected"],
                    })
                if path == "/api/github/file":
                    conn = self.state.get_connected()
                    rel = (qs.get("path") or [""])[0]
                    if not conn or not rel:
                        return self._send_json(400, {"error": "No repository connected or path missing"})
                    return self._send_json(200, studio.read_repo_file(conn, rel))
                if path == "/api/ai/models":
                    return self._send_json(200, {"models": studio.list_ollama_models(OLLAMA)})
                if path.startswith("/api/jobs/"):
                    jid = path.split("/")[-1]
                    job = self.state.jobs.get(jid)
                    if not job:
                        return self._send_json(404, {"error": "Job not found"})
                    return self._send_json(200, job)
                return self._send_json(404, {"error": "Unknown endpoint"})
            except Exception as e:
                return self._send_json(400, {"error": str(e)})
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
    ap.add_argument("academy", nargs="?", default=os.path.join(os.path.dirname(ENGINE), "example"),
                    help="the academy folder (with academy.json), or a built site folder")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--open", action="store_true", help="open the browser")
    a = ap.parse_args()
    is_academy = os.path.exists(os.path.join(a.academy, "academy.json"))
    ac = Academy(a.academy) if is_academy else None
    root = ac.out if ac else os.path.abspath(a.academy)
    if not os.path.exists(os.path.join(root, "index.html")):
        sys.exit(f"{root} has no index.html yet. Build first: python3 build.py {a.academy}")
    state = StudioState(ac, root, a.port)
    handler = lambda *x, **k: Handler(*x, state=state, **k)  # noqa: E731
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

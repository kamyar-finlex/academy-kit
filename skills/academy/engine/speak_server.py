#!/usr/bin/env python3
"""The natural voice for "Listen": a small speech server on this computer only.

  <python with kokoro> speak_server.py [--port 8770] [--voice af_heart]

It turns a sentence into audio with Kokoro, a neural voice model that runs locally, so read-aloud
sounds like a person and not like a machine. serve.py starts it by itself when it finds a Python
that has kokoro (references/VIDEO.md shows how to set one up); the page reaches it through
serve.py at /speak. Nothing is sent anywhere: the server listens on 127.0.0.1 only.

  GET  /voices  -> {"voices": ["af_heart", ...], "default": "af_heart"}
  POST /speak   {"text": "...", "voice": "af_heart"}  -> audio/wav

Environment: ACADEMY_ESPEAK_DATA (folder with espeak-ng data, only if kokoro cannot find its own),
HF_HUB_OFFLINE=1 to use only voices that are already downloaded.
"""
import argparse
import gc
import glob
import hashlib
import http.server
import io
import json
import os
import re
import sys
import threading
import time

ESPEAK = os.path.expanduser(os.environ.get("ACADEMY_ESPEAK_DATA", ""))
if ESPEAK and os.path.isdir(ESPEAK):
    import espeakng_loader
    espeakng_loader.get_data_path = lambda: ESPEAK
import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402
from kokoro import KModel, KPipeline  # noqa: E402

SR = 24000
MAX_CHARS = 1200
CACHE = os.path.expanduser("~/.cache/academy-kit/speech")
VOICE_RE = re.compile(r"^[a-z]{2}_[a-z0-9]+$")
LOCK = threading.Lock()
PIPES = {}
STATE = {"model": None, "used": time.time(), "idle": 15 * 60}
DEFAULT = "af_heart"


def installed_voices():
    """Voices already on disk (Kokoro keeps them in the Hugging Face cache)."""
    hub = os.path.join(os.environ.get("HF_HOME") or os.path.expanduser("~/.cache/huggingface"), "hub")
    found = {os.path.basename(p)[:-3] for p in glob.glob(os.path.join(hub, "models--hexgrad--Kokoro-82M", "snapshots", "*", "voices", "*.pt"))}
    return sorted(found)


def pipeline(voice):
    code = voice[0]  # the first letter of a Kokoro voice is its language: a/b English, e Spanish, f French, i Italian, p Portuguese…
    if STATE["model"] is None:  # one copy of the model, shared by every language
        STATE["model"] = KModel(repo_id="hexgrad/Kokoro-82M").eval()
    if code not in PIPES:
        PIPES[code] = KPipeline(lang_code=code, repo_id="hexgrad/Kokoro-82M", model=STATE["model"])
    return PIPES[code]


def rest_when_idle():
    """After a while without requests, let go of the model so the voice costs almost no memory while nobody listens.
    The next sentence loads it again in a few seconds."""
    while True:
        time.sleep(30)
        if STATE["model"] is not None and time.time() - STATE["used"] > STATE["idle"]:
            with LOCK:
                PIPES.clear()
                STATE["model"] = None
                gc.collect()


def speak(text, voice):
    key = hashlib.sha1(f"{voice}|{text}".encode()).hexdigest()
    path = os.path.join(CACHE, key[:2], key + ".wav")
    if os.path.exists(path):
        return open(path, "rb").read()
    with LOCK:  # one sentence at a time; the model is not thread-safe
        STATE["used"] = time.time()
        audio = np.concatenate([np.asarray(a) for _, _, a in pipeline(voice)(text, voice=voice, speed=1.0)])
    buf = io.BytesIO()
    sf.write(buf, np.clip(audio, -1, 1), SR, format="WAV", subtype="PCM_16")
    data = buf.getvalue()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "wb") as f:
        f.write(data)
    os.replace(path + ".tmp", path)
    return data


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def send(self, code, body, ctype="application/json"):
        if not isinstance(body, bytes):
            body = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.rstrip("/").endswith("/voices"):
            voices = installed_voices()
            return self.send(200, {"voices": voices or [DEFAULT], "default": DEFAULT if DEFAULT in voices or not voices else voices[0]})
        self.send(404, {"error": "not found"})

    def do_POST(self):
        if not self.path.rstrip("/").endswith("/speak"):
            return self.send(404, {"error": "not found"})
        try:
            req = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            text = " ".join(str(req.get("text") or "").split())
            voice = str(req.get("voice") or DEFAULT)
            if not text or len(text) > MAX_CHARS or not VOICE_RE.match(voice):
                return self.send(400, {"error": f"text must be 1 to {MAX_CHARS} characters and voice a Kokoro voice name"})
            self.send(200, speak(text, voice), "audio/wav")
        except Exception as e:  # a bad voice name, a missing model file…
            self.send(500, {"error": str(e)[:300]})


def main():
    global DEFAULT
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8770)
    ap.add_argument("--voice", default=DEFAULT, help="the default voice (default af_heart)")
    ap.add_argument("--idle-minutes", type=float, default=15, help="free the model after this long without a request (default 15; 0 = keep it)")
    a = ap.parse_args()
    DEFAULT = a.voice
    STATE["idle"] = a.idle_minutes * 60
    try:
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    except OSError:
        sys.exit(f"port {a.port} is in use (the voice may already be running)")
    with LOCK:
        pipeline(DEFAULT)  # load the model now, so the first sentence does not wait for it
    if STATE["idle"] > 0:
        threading.Thread(target=rest_when_idle, daemon=True).start()
    print(f"voice ready on http://127.0.0.1:{a.port}  (voices: {', '.join(installed_voices()) or DEFAULT})", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

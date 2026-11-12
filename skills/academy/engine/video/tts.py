"""Voice every segment with local Kokoro and write per-segment wavs.

<kokoro python> tts.py <lessonDir> <buildDir> L1 L2 ...

Needs a Python with kokoro, soundfile and numpy (see references/VIDEO.md). Environment:
VOICE (default af_heart), KOKORO_LANG (default "a" = American English),
ACADEMY_ESPEAK_DATA (folder with espeak-ng data, only if kokoro cannot find its own).
"""
import hashlib
import json
import os
import sys

ESPEAK = os.path.expanduser(os.environ.get("ACADEMY_ESPEAK_DATA", ""))
if ESPEAK and os.path.isdir(ESPEAK):
    import espeakng_loader  # noqa: E402
    espeakng_loader.get_data_path = lambda: ESPEAK
import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402
from kokoro import KPipeline  # noqa: E402

SR = 24000
VOICE = os.environ.get("VOICE", "af_heart")
content_dir, build_dir, ids = sys.argv[1], sys.argv[2], sys.argv[3:]
cache = os.path.join(build_dir, "_tts_cache")
os.makedirs(cache, exist_ok=True)
pipe = KPipeline(lang_code=os.environ.get("KOKORO_LANG", "a"), repo_id="hexgrad/Kokoro-82M")


def speak(text):
    key = hashlib.sha1(f"{VOICE}|{text}".encode()).hexdigest()[:16]
    path = os.path.join(cache, key + ".wav")
    if not os.path.exists(path):
        audio = np.concatenate([np.asarray(a) for _, _, a in pipe(text, voice=VOICE, speed=0.98)])
        sf.write(path, np.clip(audio, -1, 1), SR)
    return path


for lid in ids:
    lesson = json.load(open(os.path.join(content_dir, f"{lid}.json"), encoding="utf-8"))
    segs = []
    for si, sc in enumerate(lesson["video"]["scenes"]):
        for gi, seg in enumerate(sc["segments"]):
            p = speak(seg["say"])
            dur = sf.info(p).duration
            segs.append({"scene": si, "seg": gi, "wav": p, "dur": dur, "say": seg["say"], "tr": seg.get("tr", "")})
    os.makedirs(os.path.join(build_dir, lid), exist_ok=True)
    json.dump(segs, open(os.path.join(build_dir, lid, "segments.json"), "w"), ensure_ascii=False, indent=1)
    print(lid, len(segs), "segments", round(sum(s["dur"] for s in segs), 1), "s speech")

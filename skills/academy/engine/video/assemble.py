"""Join frames + narration into an MP4 and write WebVTT captions (<ID>.<lang>.vtt).

<kokoro python> assemble.py <buildDir> <outDir> L1 L2 ...
"""
import re
import json
import os
import subprocess
import sys

import numpy as np
import soundfile as sf

SR = 24000
GAP, SCENE_GAP, LEAD, TAIL = 0.35, 0.8, 0.8, 1.6
build_dir, out_dir, ids = sys.argv[1], sys.argv[2], sys.argv[3:]
os.makedirs(out_dir, exist_ok=True)

_NUM = {"zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7",
        "eight": "8", "nine": "9", "ten": "10", "eleven": "11"}
_ACR = re.compile(r"\b[A-Z](?: [A-Z])+(?=s?\b)")
_ID = re.compile(r"\b([A-Z])((?: (?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven)\b)+)")
LANG, READER = os.environ.get("ACADEMY_LANG", "en"), os.environ.get("ACADEMY_READER", "")


def written(s):
    """Narration spells IDs for the voice ("L five"); captions show them as written ("L5")."""
    s = _ID.sub(lambda m: m.group(1) + "".join(_NUM[w] for w in m.group(2).split()), s)
    s = _ACR.sub(lambda m: m.group(0).replace(" ", ""), s)  # "A P Is" -> "APIs", "M C P" -> "MCP"
    return s.replace("`", "").replace("*", "")


def ts(t):
    h, r = divmod(t, 3600)
    m, s = divmod(r, 60)
    return f"{int(h):02d}:{int(m):02d}:{s:06.3f}"


for lid in ids:
    segs = json.load(open(os.path.join(build_dir, lid, "segments.json"), encoding="utf-8"))
    pieces, concat, vtt_en, vtt_tr = [], [], ["WEBVTT", ""], ["WEBVTT", ""]
    t = 0.0
    pieces.append(np.zeros(int(LEAD * SR), dtype="float32"))
    t += LEAD
    for i, s in enumerate(segs):
        audio, _ = sf.read(s["wav"], dtype="float32")
        nxt = segs[i + 1] if i + 1 < len(segs) else None
        pause = TAIL if nxt is None else (SCENE_GAP if nxt["scene"] != s["scene"] else GAP)
        lead = LEAD if i == 0 else 0.0
        start = t
        pieces.append(audio)
        pieces.append(np.zeros(int(pause * SR), dtype="float32"))
        dur = len(audio) / SR + int(pause * SR) / SR
        t += dur
        frame = os.path.join(os.path.abspath(build_dir), lid, "frames", f"s{s['scene']:02d}_g{s['seg']:02d}.png")
        concat.append(f"file '{frame}'\nduration {dur + lead:.4f}")
        vtt_en += [f"{ts(start)} --> {ts(start + len(audio) / SR + 0.1)}", written(s["say"]), ""]
        vtt_tr += [f"{ts(start)} --> {ts(start + len(audio) / SR + 0.1)}", s.get("tr", ""), ""]
    concat.append(f"file '{frame}'")  # concat demuxer needs the last file repeated
    wav = os.path.join(build_dir, lid, "narration.wav")
    sf.write(wav, np.concatenate(pieces), SR)
    lst = os.path.join(build_dir, lid, "frames.txt")
    open(lst, "w").write("\n".join(concat) + "\n")
    mp4 = os.path.join(out_dir, f"{lid}.mp4")
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "concat", "-safe", "0", "-i", lst, "-i", wav,
        "-vf", "fps=30,format=yuv420p", "-c:v", "libx264", "-preset", "medium", "-crf", "22", "-tune", "stillimage",
        "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart", mp4,
    ], check=True)
    open(os.path.join(out_dir, f"{lid}.{LANG}.vtt"), "w", encoding="utf-8").write("\n".join(vtt_en))
    if READER and any(s.get("tr") for s in segs):  # captions in the reader's language, when the lesson has them
        open(os.path.join(out_dir, f"{lid}.{READER}.vtt"), "w", encoding="utf-8").write("\n".join(vtt_tr))
    print(lid, f"{t:.1f}s", os.path.getsize(mp4) // 1024, "KB")

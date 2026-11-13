#!/usr/bin/env python3
"""Build an academy's website from its lesson files.

  python3 build.py <academy-folder>               build the site; make videos that are missing or out of date
  python3 build.py <academy-folder> L3 L5         same, but (re)make the videos of these lessons
  python3 build.py <academy-folder> --no-video    site only
  python3 build.py <academy-folder> --all-videos  re-render every video (slow: about 2–3 minutes each)

The site is written to the folder named by "out" in academy.json (default: site/).
Videos are optional and off unless academy.json has "video": {"enabled": true}; see references/VIDEO.md.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ENGINE, Academy, natural  # noqa: E402
import validate  # noqa: E402

TTS_PY = "~/.local/share/academy-kit/tts/bin/python"
CHROME = os.environ.get("CHROME_BIN") or "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def video_hash(lesson):
    blob = json.dumps([lesson.get("name"), lesson.get("tagline"), lesson.get("video")], sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(blob.encode()).hexdigest()


def make_videos(ac, lessons, asked, force_all):
    """Render the videos that need it. Returns nothing; finished files land in <out>/videos."""
    vcfg = ac.cfg.get("video") or {}
    vout = os.path.join(ac.out, "videos")
    todo = []
    for lid, l in lessons.items():
        if not l.get("video"):
            continue
        hfile = os.path.join(ac.build, lid, "video.hash")
        mp4 = os.path.join(vout, lid + ".mp4")
        h = video_hash(l)
        old = open(hfile).read().strip() if os.path.exists(hfile) else None
        if os.path.exists(mp4) and old is None and not (force_all or lid in asked):
            # A video made before hashes existed: take it as current instead of re-rendering everything.
            os.makedirs(os.path.dirname(hfile), exist_ok=True)
            open(hfile, "w").write(h)
            continue
        if force_all or lid in asked or not os.path.exists(mp4) or old != h:
            todo.append((lid, h))
    if not todo:
        return
    py = os.path.expanduser(os.environ.get("ACADEMY_TTS_PYTHON") or vcfg.get("python") or TTS_PY)
    missing = [n for n, ok in (("node", shutil.which("node")), ("ffmpeg", shutil.which("ffmpeg")), (f"Chrome ({CHROME})", os.path.exists(CHROME)),
                               (f"a Python with kokoro ({py})", os.path.exists(py))) if not ok]
    if missing:
        print(f"videos skipped ({', '.join(i for i, _ in todo)}): missing {', '.join(missing)}. See references/VIDEO.md.")
        return
    ids = [i for i, _ in todo]
    print("rendering videos:", " ".join(ids))
    norm_dir = os.path.join(ac.build, "_lessons")
    os.makedirs(norm_dir, exist_ok=True)
    for lid in ids:
        json.dump(lessons[lid], open(os.path.join(norm_dir, lid + ".json"), "w", encoding="utf-8"), ensure_ascii=False)
    env = dict(os.environ, HF_HUB_OFFLINE=os.environ.get("HF_HUB_OFFLINE", "1"),
               ACADEMY_LANG=(ac.cfg.get("language") or {}).get("code", "en"), ACADEMY_READER=ac.reader or "")
    if vcfg.get("voice"):
        env.setdefault("VOICE", vcfg["voice"])
    if vcfg.get("lang_code"):
        env.setdefault("KOKORO_LANG", vcfg["lang_code"])
    if vcfg.get("espeak_data"):
        env.setdefault("ACADEMY_ESPEAK_DATA", vcfg["espeak_data"])
    env["ACADEMY_THEME"] = json.dumps({k: v for k, v in (ac.cfg.get("theme") or {}).items() if isinstance(v, str)})
    font = ac.cfg.get("font") or {}
    if font.get("file"):
        env.update(ACADEMY_FONT_FILE=ac.path(font["file"]), ACADEMY_FONT_FAMILY=font.get("family", "AcademyFont"))
    vdir = os.path.join(ENGINE, "video")
    out_tmp = os.path.join(ac.build, "out")
    subprocess.run(["node", "render.mjs", norm_dir, ac.build, *ids], cwd=vdir, check=True, env=env)
    tts = subprocess.run([py, "tts.py", norm_dir, ac.build, *ids], cwd=vdir, env=env, stderr=subprocess.PIPE, text=True)
    if tts.returncode:  # the voice model is chatty on stderr; show it only when it failed
        print("the narration step failed:\n" + tts.stderr[-2000:])
        raise subprocess.CalledProcessError(tts.returncode, [py, "tts.py"])
    subprocess.run([py, "assemble.py", ac.build, out_tmp, *ids], cwd=vdir, check=True, env=env)
    os.makedirs(vout, exist_ok=True)
    for lid, h in todo:
        for f in os.listdir(out_tmp):
            if f == lid + ".mp4" or (f.startswith(lid + ".") and f.endswith(".vtt")):
                shutil.copy2(os.path.join(out_tmp, f), os.path.join(vout, f))
        open(os.path.join(ac.build, lid, "video.hash"), "w").write(h)


def find_videos(ac, ids):
    vout, lang, found = os.path.join(ac.out, "videos"), (ac.cfg.get("language") or {}).get("code", "en"), {}
    for lid in ids:
        if os.path.exists(os.path.join(vout, lid + ".mp4")):
            caps = next((c for c in (f"{lid}.{lang}.vtt", f"{lid}.vtt") if os.path.exists(os.path.join(vout, c))), None)
            found[lid] = {"captions": caps}
    return found


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("academy")
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--no-video", action="store_true")
    ap.add_argument("--all-videos", action="store_true")
    a = ap.parse_args()
    ac = Academy(a.academy)
    cfg = ac.cfg
    kit = os.path.realpath(os.path.join(ENGINE, "..", "..", ".."))
    if os.path.commonpath([kit, os.path.realpath(ac.dir)]) == kit and os.path.realpath(ac.dir) != os.path.realpath(os.path.join(ENGINE, "..", "example")):
        sys.exit(f"{ac.dir} is inside the kit. Move the academy out: the kit is the shared tool and must not hold anyone's content.")
    ids = ac.ids()
    if validate.run(ac):
        sys.exit("fix the errors above, then build again")
    lessons = {i: ac.lesson(i) for i in ids}
    groups = ac.groups(ids)
    for g in groups:
        if g.get("intro") in lessons:
            lessons[g["intro"]]["intro"] = True
    if cfg.get("lesson_order", "groups") == "groups":
        order = [i for g in groups for i in g["lessons"]]
    else:
        order = sorted(ids, key=natural)

    for i in a.ids:
        if i not in lessons:
            print(f"note: {i} is not a lesson here (ids only choose which videos to re-make; the whole site is always rebuilt)")
    if (cfg.get("video") or {}).get("enabled") and not a.no_video:
        try:
            make_videos(ac, lessons, set(a.ids), a.all_videos)
        except subprocess.CalledProcessError as err:  # a failed video must not cost the reader the site
            print(f"videos failed ({' '.join(map(str, err.cmd[:2]))}, exit {err.returncode}); building the site without the new ones")

    assets = os.path.join(ac.out, "assets")
    os.makedirs(os.path.join(assets, "vendor"), exist_ok=True)
    src = os.path.join(ENGINE, "portal")
    for f in ("app.js", "style.css", "icon.svg"):
        shutil.copy2(os.path.join(src, "assets", f), os.path.join(assets, f))
    for f in os.listdir(os.path.join(src, "assets", "vendor")):
        shutil.copy2(os.path.join(src, "assets", "vendor", f), os.path.join(assets, "vendor", f))
    theme = cfg.get("theme") or {}
    font, font_css = cfg.get("font") or {}, ""
    if font.get("file"):  # the academy's own font: copied from its folder, the kit ships none
        fsrc = ac.path(font["file"])
        if not os.path.exists(fsrc):
            sys.exit(f'academy.json "font.file" not found: {fsrc}')
        shutil.copy2(fsrc, os.path.join(assets, os.path.basename(fsrc)))
        fam = font.get("family", "AcademyFont")
        font_css = (f'@font-face {{ font-family: "{fam}"; src: url("{os.path.basename(fsrc)}"); font-display: swap; }}\n'
                    f':root {{ --font: "{fam}", -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; }}\n')
    elif font.get("family"):  # a font the reader's system already has
        font_css = f':root {{ --font: "{font["family"]}", -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; }}\n'
    open(os.path.join(assets, "theme.css"), "w", encoding="utf-8").write(
        font_css + ":root {" + " ".join(f"--{k}: {v};" for k, v in theme.items() if k != "dark") + "}\n" +
        ("@media (prefers-color-scheme: dark) { :root {" + " ".join(f"--{k}: {v};" for k, v in theme["dark"].items()) + "} }\n" if theme.get("dark") else ""))

    stamp = str(int(time.time()))
    title = cfg.get("title", "Academy")
    public = {
        "id": cfg.get("id") or os.path.basename(ac.dir), "storage": cfg.get("storage"), "title": title,
        "home": cfg.get("home") or {}, "labels": cfg.get("labels") or {}, "groups": groups,
        "language": cfg.get("language") or {"code": "en", "name": "English"}, "reader": cfg.get("reader"),
        "domain": cfg.get("domain"), "ai": cfg.get("ai", {}), "speech": cfg.get("speech", {}), "videos": find_videos(ac, ids),
        "sync": bool(cfg.get("source")),
    }
    if "codes" in cfg:
        public["codes"] = cfg["codes"]
    with open(os.path.join(assets, "lessons.js"), "w", encoding="utf-8") as f:
        f.write("window.LESSONS = " + json.dumps([lessons[i] for i in order], ensure_ascii=False) + ";\n")
        f.write("window.ACADEMY = " + json.dumps(public, ensure_ascii=False) + ";\n")
        f.write(f'window.LESSONS_BUILD = "{stamp}";\n')
    esc = lambda s: str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    page = open(os.path.join(src, "index.html"), encoding="utf-8").read()
    for k, v in {"lang": public["language"].get("code", "en"), "title": title, "subtitle": cfg.get("subtitle", ""),
                 "logo": cfg.get("logo") or title[:1].upper(), "build": stamp,
                 "plain_toggle": (cfg.get("labels") or {}).get("plain_toggle", "Plain-words notes")}.items():
        page = page.replace("{{" + k + "}}", esc(v))
    open(os.path.join(ac.out, "index.html"), "w", encoding="utf-8").write(page)
    badge = os.path.join(assets, "sync.json")
    if cfg.get("source") and not os.path.exists(badge):  # the home page reads it; say "not checked yet" until sync.py runs
        json.dump({"label": (cfg["source"].get("label") or ""), "status": "new"}, open(badge, "w"))
    print(f"built {len(order)} lessons ({len(public['videos'])} with video) -> {ac.out}")
    print(f"open it:  python3 {os.path.join(ENGINE, 'serve.py')} {ac.dir} --open")


if __name__ == "__main__":
    main()

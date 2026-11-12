#!/usr/bin/env python3
"""Start a new academy folder.

  python3 init.py <new-folder> --title "Library Handbook Academy" [--docs <path-or-git-url>] [--reader German]

Creates academy.json, an empty content/ folder, sources.json (which files each lesson comes from) and a .gitignore.
With --docs it also records where the documents are, which the sync check uses later.
Then write lessons into content/ (references/LESSON_BRIEF.md) and build.
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ENGINE  # noqa: E402

# Languages people are likely to ask for: code, right-to-left, a regex that recognizes the script
# (so a question typed in it is answered in it; Latin-script languages are recognized by the model itself).
LANGS = {"persian": ("fa", True, "[\\u0600-\\u06FF]"), "arabic": ("ar", True, "[\\u0600-\\u06FF]"), "hebrew": ("he", True, "[\\u0590-\\u05FF]"),
         "german": ("de", False, None), "french": ("fr", False, None), "spanish": ("es", False, None), "turkish": ("tr", False, None),
         "polish": ("pl", False, None), "russian": ("ru", False, "[\\u0400-\\u04FF]"), "ukrainian": ("uk", False, "[\\u0400-\\u04FF]"),
         "hindi": ("hi", False, "[\\u0900-\\u097F]"), "chinese": ("zh", False, "[\\u4E00-\\u9FFF]"), "english": ("en", False, None)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder")
    ap.add_argument("--title", required=True)
    ap.add_argument("--docs", help="where the source documents are: a folder or a git URL (optional; enables sync)")
    ap.add_argument("--reader", help="the reader's own language, if it is not the lessons' language (e.g. German, Persian)")
    ap.add_argument("--language", default="English", help="the language the lessons are written in (default English)")
    a = ap.parse_args()
    d = os.path.abspath(a.folder)
    kit = os.path.realpath(os.path.join(ENGINE, "..", "..", ".."))  # the kit's repository
    if os.path.commonpath([kit, os.path.realpath(d)]) == kit:
        sys.exit(f"{d} is inside the kit ({kit}).\nThe kit is the shared tool; an academy holds your documents' content and must live outside it.\n"
                 "Choose a folder next to your documents instead.")
    if os.path.exists(os.path.join(d, "academy.json")):
        sys.exit(f"{d} already has an academy.json")
    os.makedirs(os.path.join(d, "content"), exist_ok=True)
    lang = LANGS.get(a.language.lower(), (a.language[:2].lower(), False, None))
    cfg = {
        "id": re.sub(r"[^a-z0-9]+", "-", a.title.lower()).strip("-"),
        "title": a.title,
        "subtitle": "",
        "domain": "internal company",
        "language": {"code": lang[0], "name": a.language},
        "groups": [],
        "home": {"heading": "Start here", "intro": "", "source_note": ""},
        "ai": {"models": ["gemma4:e4b", "gemma3:4b"]},
    }
    if a.reader and a.reader.lower() != a.language.lower():
        code, rtl, detect = LANGS.get(a.reader.lower(), (a.reader[:2].lower(), False, None))
        cfg["reader"] = {"code": code, "name": a.reader, "rtl": rtl, "badge": code.upper(),
                         "example": {"tr": "", "meaning": ""}}
        if detect:
            cfg["reader"]["detect"] = detect
    if a.docs:
        if re.match(r"^(https?://|git@)", a.docs):
            cfg["source"] = {"type": "git", "repo": a.docs, "docs_root": ""}
        else:
            cfg["source"] = {"type": "folder", "path": os.path.relpath(os.path.abspath(a.docs), d)}
    json.dump({"shared_sources": [], "lessons": {}}, open(os.path.join(d, "sources.json"), "w"), indent=2)
    json.dump(cfg, open(os.path.join(d, "academy.json"), "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    open(os.path.join(d, ".gitignore"), "w").write("site/\nbuild/\nsource-repo/\nsync-state.json\n")
    open(os.path.join(d, "PRIVATE.md"), "w", encoding="utf-8").write(
        "# Private\n\nThis folder is an academy: its lessons restate the source documents. Treat it exactly as confidential as those documents.\n\n"
        "- Keep it where the documents may be kept (your computer, or a private repository your team already uses for them).\n"
        "- Never put it in a public repository, and never inside the academy kit.\n"
        "- No passwords or tokens in `academy.json`: for a private git source, let git's own credential helper sign in.\n"
        "- The built site (`site/`) and videos contain the same content; share them only with people who may read the documents.\n")
    print(f"created {d}  (private: see PRIVATE.md there)")
    print(f"next: write lessons into {os.path.join(d, 'content')} following {os.path.normpath(os.path.join(ENGINE, '..', 'references', 'LESSON_BRIEF.md'))}")
    print(f"then: python3 {os.path.join(ENGINE, 'build.py')} {d}")


if __name__ == "__main__":
    main()

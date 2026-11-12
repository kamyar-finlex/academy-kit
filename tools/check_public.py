#!/usr/bin/env python3
"""Check that this repository holds only the tool, nothing private.

  python3 tools/check_public.py            check what git would publish (or every file, if this is not a git repo yet)
  python3 tools/check_public.py --staged   check only what is staged for the next commit (the pre-commit hook does this)

The kit is public. Academies are not: an academy is someone's documents, rewritten as lessons.
This check fails (exit 1) when it finds anything that looks like content, a secret or a personal detail:

  - an academy (academy.json, lesson files) anywhere but skills/academy/example
  - built sites, videos, fonts, office documents, PDFs, archives, images
  - passwords, keys and tokens; web addresses with a login in them
  - e-mail addresses; paths into someone's home folder
  - any word on your own private list (company, project and host names you never want published):
    one per line in ~/.config/academy-kit/private-words.txt, or the file named by ACADEMY_PRIVATE_WORDS.
    That list stays on your computer; it is never part of the repository.

Standard library only.
"""
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLE = "skills/academy/example/"            # the one academy that may live here: it is built from the kit's own guides
VENDOR = ("skills/academy/engine/portal/assets/vendor/",)   # third-party code, listed in THIRD_PARTY_NOTICES.md
SKIP_DIRS = {".git", "__pycache__", "node_modules"}
# Things that only exist once an academy is built or synced: fine on disk, never to be committed.
LOCAL_ONLY = re.compile(r"(^|/)(site|build|source-repo|videos)/|(^|/)sync-state\.json$")
BLOCKED_EXT = {".woff", ".woff2", ".ttf", ".otf", ".eot", ".mp4", ".mov", ".webm", ".mp3", ".wav", ".vtt", ".pdf", ".doc", ".docx",
               ".xls", ".xlsx", ".ppt", ".pptx", ".key", ".pages", ".numbers", ".zip", ".tgz", ".gz", ".tar", ".7z", ".png", ".jpg",
               ".jpeg", ".gif", ".webp", ".heic", ".sqlite", ".db", ".env", ".pem", ".p12", ".pfx"}
PATTERNS = [
    ("a private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("an AWS access key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("a GitHub token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}\b|\bgithub_pat_[A-Za-z0-9_]{30,}\b")),
    ("a Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("an API key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("a password or secret with a value", re.compile(r"""(?i)\b(?:password|passwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token)\b["']?\s*[:=]\s*["'][^"'\s]{6,}["']""")),
    ("a web address with a login in it", re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s/:@\"']+:[^\s/@\"']+@")),
    ("an e-mail address", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}\b")),
    ("a path into someone's home folder", re.compile(r"/(?:Users|home)/(?!you\b|me\b|name\b|username\b|user\b|Shared\b)[A-Za-z][\w.-]*/|[A-Za-z]:\\Users\\[\w.-]+")),
]
ALLOWED_EMAILS = re.compile(r"@(example\.(com|org|net)|users\.noreply\.github\.com)$", re.I)


def private_words():
    path = os.environ.get("ACADEMY_PRIVATE_WORDS") or os.path.expanduser("~/.config/academy-kit/private-words.txt")
    if not os.path.exists(path):
        return [], path
    words = [w.strip() for w in open(path, encoding="utf-8") if w.strip() and not w.startswith("#")]
    return words, path


def files(staged):
    if os.path.isdir(os.path.join(ROOT, ".git")):
        args = ["diff", "--cached", "--name-only", "--diff-filter=ACMR"] if staged else ["ls-files", "--cached", "--others", "--exclude-standard"]
        out = subprocess.run(["git", "-C", ROOT, *args], capture_output=True, text=True, check=True).stdout
        return [f for f in out.splitlines() if os.path.isfile(os.path.join(ROOT, f))]
    found = []  # not a repository yet: everything on disk, minus what .gitignore would keep out anyway
    for d, dirs, names in os.walk(ROOT):
        dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
        for n in names:
            rel = os.path.relpath(os.path.join(d, n), ROOT).replace(os.sep, "/")
            if n != ".DS_Store" and not LOCAL_ONLY.search(rel):
                found.append(rel)
    return found


def main():
    staged = "--staged" in sys.argv
    words, words_path = private_words()
    word_rx = re.compile("|".join(re.escape(w) for w in words), re.I) if words else None
    problems = []
    for rel in sorted(files(staged)):
        ext = os.path.splitext(rel)[1].lower()
        base = os.path.basename(rel)
        if LOCAL_ONLY.search(rel):
            problems.append((rel, 0, "a built or synced file (site/, build/, videos/, sync state): these stay on your computer"))
            continue
        if ext in BLOCKED_EXT:
            problems.append((rel, 0, f"a {ext} file: fonts, media, documents and archives are content, not the tool"))
            continue
        if not rel.startswith(EXAMPLE):
            if base == "academy.json" or base == "ACADEMY_NOTES.md" or base == "sources.json" or re.search(r"(^|/)content/[^/]+\.json$", rel):
                problems.append((rel, 0, "part of an academy: academies live outside this repository"))
                continue
        if rel.startswith(VENDOR):
            continue
        try:
            text = open(os.path.join(ROOT, rel), encoding="utf-8").read()
        except UnicodeDecodeError:
            problems.append((rel, 0, "a binary file: only text belongs here"))
            continue
        if rel == "tools/check_public.py":
            continue  # this file names the patterns it looks for
        for n, line in enumerate(text.splitlines(), 1):
            for what, rx in PATTERNS:
                m = rx.search(line)
                if m and not (what == "an e-mail address" and ALLOWED_EMAILS.search(m.group(0))):
                    problems.append((rel, n, f"{what}: {m.group(0)[:60]}"))
            if word_rx:
                m = word_rx.search(line)
                if m:
                    problems.append((rel, n, f'a word on your private list: "{m.group(0)}"'))
    for rel, n, msg in problems:
        print(f"{rel}{':' + str(n) if n else ''}  {msg}")
    if problems:
        print(f"\n{len(problems)} problem(s). Nothing private may go into this repository; move it to your academy's own folder.")
        return 1
    note = f"{len(words)} private word(s) from {words_path}" if words else f"no private-word list at {words_path}"
    print(f"public check passed ({note})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

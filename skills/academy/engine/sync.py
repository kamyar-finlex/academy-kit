#!/usr/bin/env python3
"""Tell when the source documents changed and which lessons that touches.

  python3 sync.py <academy-folder> check
        Look at the source (a git repository or a folder), compare it with the last synced
        state, print a JSON report and refresh the badge on the academy's home page.
        Exit 0 = up to date, 10 = lessons need an update.
  python3 sync.py <academy-folder> mark [<revision>] --lessons L3,L5 --note "what changed"
        Record a finished update (after the lessons were edited and the site rebuilt).
  python3 sync.py <academy-folder> fail "message"
        Show a problem on the home page; the next check retries.

Deterministic on purpose: this script decides IF something changed and WHICH lessons it
touches. Rewriting the lesson text is a person's or an agent's job (references/SYNC.md).

academy.json:  "source": {"type": "git", "repo": "<url>", "docs_root": "docs"}
           or  "source": {"type": "folder", "path": "../my-docs"}
sources.json:  {"shared_sources": ["README.md"], "lessons": {"L3": {"sources": ["lending.md"]}}}
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import Academy, die, load_json, natural, save_json  # noqa: E402

TEXT_EXT = (".md", ".mdx", ".txt", ".rst", ".adoc", ".html", ".json", ".yaml", ".yml", ".csv")


def now():
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


class Sync:
    def __init__(self, ac):
        self.ac = ac
        self.src = ac.cfg.get("source") or die('academy.json has no "source" block; see references/SYNC.md')
        self.kind = self.src.get("type", "git")
        self.state_path = ac.path(self.src.get("state", "sync-state.json"))
        self.map = load_json(ac.path(self.src.get("sources", "sources.json")), {})
        self.docs = (self.src.get("docs_root") or self.map.get("docs_root") or "").strip("/")
        self.root = ac.path(self.src.get("clone", "source-repo") if self.kind == "git" else self.src.get("path", ""))
        self.label = self.src.get("label") or re.sub(r"^https?://[^/]+/|\.git$", "", self.src.get("repo", "")) or os.path.basename(self.root)
        self.badge = os.path.join(ac.out, "assets", "sync.json")
        self.state = load_json(self.state_path, {})

    # ---- where the documents are
    def git(self, *args):
        return subprocess.run(["git", "-C", self.root, *args], check=True, capture_output=True, text=True).stdout.strip()

    def manifest(self):
        base, out = os.path.join(self.root, self.docs), {}
        for d, dirs, files in os.walk(base):
            dirs[:] = [x for x in dirs if not x.startswith(".")]
            for f in files:
                if f.startswith("."):
                    continue
                p = os.path.join(d, f)
                out[os.path.relpath(p, base)] = hashlib.sha1(open(p, "rb").read()).hexdigest()
        return out

    def changes(self):
        """-> (revision, [(status, path relative to docs_root)], commit lines). Status is A, M or D."""
        base = self.state.get("synced_commit")
        if self.kind == "folder":
            if not os.path.isdir(self.root):
                die(f"source folder not found: {self.root}")
            new, old = self.manifest(), self.state.get("manifest")
            rev = hashlib.sha1(json.dumps(new, sort_keys=True).encode()).hexdigest()
            self.state["pending_manifest"] = new
            if old is None:
                return rev, [], []
            ch = [("A", p) for p in new if p not in old] + [("M", p) for p in new if p in old and old[p] != new[p]] + [("D", p) for p in old if p not in new]
            return rev, sorted(ch, key=lambda x: x[1]), []
        if not os.path.isdir(os.path.join(self.root, ".git")):
            if not self.src.get("repo"):
                die('"source" needs a "repo" URL (or an existing clone at "clone")')
            os.makedirs(os.path.dirname(self.root), exist_ok=True)
            subprocess.run(["git", "clone", "-q", self.src["repo"], self.root], check=True)
        self.git("fetch", "-q", "origin")
        remote = self.git("rev-parse", "origin/HEAD")
        if base == remote:
            return remote, [], []
        self.git("merge", "-q", "--ff-only", "origin/HEAD")  # the clone is read-only; fast-forward only
        if not base:
            return remote, [], []
        lines = self.git("diff", "--name-status", f"{base}..{remote}", "--", self.docs or ".").splitlines()
        ch = []
        for line in lines:
            parts = line.split("\t")
            path = parts[-1]
            ch.append((parts[0][:1], path[len(self.docs) + 1:] if self.docs and path.startswith(self.docs + "/") else path))
        return remote, ch, self.git("log", "--format=%h %ad %s", "--date=short", f"{base}..{remote}").splitlines()

    # ---- state and badge
    def save(self):
        save_json(self.state_path, self.state)

    def write_badge(self, status, remote, pending, error=None):
        os.makedirs(os.path.dirname(self.badge), exist_ok=True)
        s = self.state
        data = {"label": self.label, "repo": self.label, "status": status, "checked_at": s.get("checked_at"), "remote_commit": remote,
                "synced_commit": s.get("synced_commit"), "synced_at": s.get("synced_at"), "pending_lessons": pending,
                "history": s.get("history", [])[:20]}
        if error:
            data["error"] = error
        save_json(self.badge, data)

    def record(self, rev, lessons, note):
        self.state.update(synced_commit=rev, synced_at=now(), checked_at=now())
        if "pending_manifest" in self.state:
            self.state["manifest"] = self.state.pop("pending_manifest")
        self.state.pop("pending_rev", None)
        self.state.setdefault("history", []).insert(0, {"at": now(), "commit": rev[:7], "lessons": lessons, "note": note})
        self.save()
        self.write_badge("in_sync", rev, [])

    # ---- commands
    def check(self):
        ids = self.ac.ids()
        intros = self.ac.intros(ids)
        first = not self.state.get("synced_commit")
        rev, changed, commits = self.changes()
        self.state["checked_at"] = now()
        if rev == self.state.get("synced_commit"):
            self.state.pop("pending_manifest", None)
            self.save()
            self.write_badge("in_sync", rev, [])
            print(json.dumps({"status": "up_to_date", "revision": rev[:7]}))
            return 0
        if first:
            self.record(rev, [], "First check: recorded the starting point.")
            print(json.dumps({"status": "baseline_recorded", "revision": rev[:7]}))
            return 0
        shared = set(self.map.get("shared_sources", []))
        shared_lessons = self.src.get("shared_lessons") or sorted(intros, key=natural)
        id_rx = re.compile(r"(?<![\w-])(" + "|".join(re.escape(i) for i in sorted(set(ids) - intros, key=len, reverse=True)) + r")(?![\w-])") if set(ids) - intros else None
        phrases = self.src.get("mentions") or []
        direct, mentions, other = {}, {}, []
        for status, rel in changed:
            hit = [lid for lid, v in self.map.get("lessons", {}).items() if rel in v.get("sources", [])]
            if rel in shared:
                hit = sorted(set(hit) | set(shared_lessons), key=natural)
            if hit:
                for lid in hit:
                    direct.setdefault(lid, []).append(f"{status} {rel}")
                continue
            found = []
            full = os.path.join(self.root, self.docs, rel)
            if status != "D" and os.path.isfile(full) and rel.lower().endswith(TEXT_EXT):
                text = open(full, encoding="utf-8", errors="replace").read()
                by_id = sorted(set(id_rx.findall(text)), key=natural) if id_rx else []
                if by_id or any(p in text for p in phrases):
                    found = by_id or ["?"]
            if found:
                mentions[rel] = {"status": status, "mentions": [i for i in found if i != "?"]}
            else:
                other.append(f"{status} {rel}")
        pending = sorted(direct, key=natural)
        report = {"status": "changes" if (direct or mentions) else "source_changed_elsewhere", "from": (self.state.get("synced_commit") or "")[:7],
                  "to": rev[:7], "to_full": rev, "lessons_from_sources": {k: direct[k] for k in pending},
                  "files_mentioning_lessons": mentions, "other_changed_files": other, "commits": commits}
        print(json.dumps(report, indent=2, ensure_ascii=False))
        if not direct and not mentions:
            self.record(rev, [], "Source changed, no lesson affected.")
            return 0
        self.state["pending_rev"] = rev
        self.save()
        self.write_badge("updating", rev, pending or sorted({i for m in mentions.values() for i in m["mentions"]}, key=natural))
        return 10

    def mark(self, rev, lessons, note):
        rev = rev or self.state.get("pending_rev") or die("nothing pending; give the revision: mark <revision>")
        self.record(rev, lessons, note)
        print(json.dumps({"status": "marked", "revision": rev[:7], "lessons": lessons}))
        return 0

    def fail(self, msg):
        self.state["last_error"] = {"at": now(), "message": msg}
        self.state["checked_at"] = now()
        self.save()
        self.write_badge("error", self.state.get("pending_rev"), [], error=msg)
        print(json.dumps({"status": "error_recorded"}))
        return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("academy")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    m = sub.add_parser("mark")
    m.add_argument("revision", nargs="?")
    m.add_argument("--lessons", default="")
    m.add_argument("--note", default="")
    f = sub.add_parser("fail")
    f.add_argument("message")
    a = ap.parse_args()
    s = Sync(Academy(a.academy))
    if a.cmd == "check":
        sys.exit(s.check())
    if a.cmd == "fail":
        sys.exit(s.fail(a.message))
    sys.exit(s.mark(a.revision, [x for x in a.lessons.split(",") if x], a.note))

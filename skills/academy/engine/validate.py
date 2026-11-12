#!/usr/bin/env python3
"""Check an academy's lesson files before building.

  python3 validate.py <academy-folder> [ID ...]

Errors stop a build (the portal would break). Warnings are things a reader would miss.
Exit 0 = no errors, 1 = errors.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import Academy  # noqa: E402

SCENE_KINDS = {"title", "diagram", "layers", "timeline", "flow", "split", "cards", "bullets"}


def words(s):
    return len(str(s).split())


def check_lesson(lid, l, all_ids, reader=None):
    err, warn = [], []
    e, w = err.append, warn.append
    if l.get("id") != lid:
        e(f'"id" is {l.get("id")!r} but the file is {lid}.json')
    for k in ("name", "tagline"):
        if not str(l.get(k) or "").strip():
            e(f'missing "{k}"')
    secs = l.get("sections")
    if not isinstance(secs, list) or not secs:
        e('"sections" must be a list with at least one section')
        secs = []
    elif len(secs) < 3:
        w(f"only {len(secs)} section(s); a lesson usually needs 3–9 to cover its sources")
    for i, s in enumerate(secs):
        if not isinstance(s, dict) or not str(s.get("heading") or "").strip():
            e(f"sections[{i}] has no heading")
            continue
        body = s.get("body")
        if not body or not all(isinstance(b, str) for b in ([body] if isinstance(body, str) else body)):
            e(f'sections[{i}] "{s.get("heading")}": body must be a string or a list of strings')
        if not s.get("explain"):
            w(f'sections[{i}] "{s.get("heading")}": no plain-words note ("explain")')
    for key, need in (("components", ("name", "text")), ("relationships", ("with", "text")), ("gates", ("gate", "text")),
                      ("pitfalls", ("text",)), ("key_terms", ("term", "text"))):
        for i, x in enumerate(l.get(key) or []):
            miss = [n for n in need if not (isinstance(x, dict) and str(x.get(n) or "").strip())]
            if miss:
                e(f"{key}[{i}] is missing {', '.join(miss)}")
    b = l.get("boundary")
    if b is not None and not (isinstance(b, dict) and isinstance(b.get("owns", []), list) and isinstance(b.get("not_owns", []), list)):
        e('"boundary" needs "owns" and "not_owns" lists')
    ex = l.get("example")
    if ex is not None and not (isinstance(ex, dict) and isinstance(ex.get("steps"), list) and ex["steps"]):
        e('"example" needs a non-empty "steps" list')
    quiz = l.get("quiz") or []
    for i, q in enumerate(quiz):
        opts = q.get("options") if isinstance(q, dict) else None
        if not (isinstance(q, dict) and q.get("q") and isinstance(opts, list) and len(opts) >= 2):
            e(f'quiz[{i}] needs "q" and at least two "options"')
            continue
        if not (isinstance(q.get("answer"), int) and 0 <= q["answer"] < len(opts)):
            e(f'quiz[{i}]: "answer" must be the index (0-based) of the right option')
        if not q.get("why"):
            w(f'quiz[{i}]: no "why" explanation')
    if not quiz:
        w("no quiz")
    elif len(quiz) > 2 and len({q.get("answer") for q in quiz if isinstance(q, dict)}) == 1:
        w("every quiz answer is in the same position")
    if not l.get("key_terms"):
        w("no key_terms (the glossary and mind maps use them)")
    elif reader:
        n = sum(1 for t in l["key_terms"] if isinstance(t, dict) and not t.get("tr"))
        if n:
            w(f'{n} key term(s) have no "tr" (the academy has a reader language)')
    v = l.get("video")
    if v is not None:
        scenes = v.get("scenes") if isinstance(v, dict) else None
        if not isinstance(scenes, list) or not scenes:
            e('"video" needs a non-empty "scenes" list (or leave "video" out)')
        else:
            said = 0
            for i, sc in enumerate(scenes):
                if sc.get("kind") not in SCENE_KINDS:
                    e(f'video.scenes[{i}]: unknown kind {sc.get("kind")!r}')
                segs = sc.get("segments")
                if not isinstance(segs, list) or not segs or not all(isinstance(g, dict) and g.get("say") for g in segs):
                    e(f'video.scenes[{i}]: needs "segments" with a "say" each')
                    continue
                said += sum(words(g["say"]) for g in segs)
                if sc.get("kind") == "diagram":
                    n = len(sc.get("nodes") or [])
                    for j, ed in enumerate(sc.get("edges") or []):
                        if not all(isinstance(ed.get(k), int) and 0 <= ed[k] < n for k in ("from", "to")):
                            e(f"video.scenes[{i}].edges[{j}]: from/to must be node indexes 0..{n - 1}")
            if scenes[0].get("kind") != "title":
                w("video: the first scene should be a title scene")
            if said and not 200 <= said <= 450:
                w(f"video narration is {said} words (aim for 280–380)")
    return err, warn


def run(ac, only=None):
    ids = ac.ids()
    if not ids:
        print(f"no lessons in {ac.content}")
        return 1
    bad = 0
    for lid in only or ids:
        if lid not in ids:
            print(f"{lid}: no such lesson file")
            bad += 1
            continue
        err, warn = check_lesson(lid, ac.lesson(lid), ids, ac.reader)
        for m in err:
            print(f"{lid}: ERROR  {m}")
        for m in warn:
            print(f"{lid}: warn   {m}")
        bad += len(err)
    for g in ac.cfg.get("groups") or []:
        for i in (g.get("lessons") or []) + ([g["intro"]] if g.get("intro") else []):
            if i not in ids:
                print(f'academy.json: warn   group "{g.get("title")}" names {i}, which has no lesson file')
    rd = ac.cfg.get("reader")
    if rd and not (rd.get("example") or {}).get("tr"):
        print('academy.json: warn   "reader.example.tr" is empty; without it a small model translates the whole sentence (references/CONFIG.md)')
    print(f"{len(only or ids)} lesson(s) checked, {bad} error(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(run(Academy(sys.argv[1]), sys.argv[2:] or None))

"""Shared by build.py, validate.py, sync.py and serve.py. Standard library only."""
import json
import os
import re
import sys

ENGINE = os.path.dirname(os.path.abspath(__file__))


def die(msg):
    print("error: " + msg, file=sys.stderr)
    sys.exit(1)


def load_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        if default is not None:
            return default
        die(f"missing file: {path}")
    except json.JSONDecodeError as e:
        die(f"{path} is not valid JSON: {e}")


def save_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def natural(s):
    """L2 before L10, S01 before S10."""
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r"(\d+)", s)]


class Academy:
    """One academy = a folder with academy.json and content/<ID>.json lessons."""

    def __init__(self, path):
        self.dir = os.path.abspath(path)
        cfg_path = os.path.join(self.dir, "academy.json")
        if not os.path.exists(cfg_path):
            die(f"{self.dir} has no academy.json. Create one with: python3 {os.path.join(ENGINE, 'init.py')} <folder> --title \"…\"")
        self.cfg = load_json(cfg_path)
        self.content = self.path(self.cfg.get("content", "content"))
        self.out = self.path(self.cfg.get("out", "site"))
        self.build = self.path(self.cfg.get("build", "build"))
        self.reader = (self.cfg.get("reader") or {}).get("code")

    def path(self, rel):
        return os.path.normpath(os.path.join(self.dir, os.path.expanduser(rel)))

    def ids(self):
        if not os.path.isdir(self.content):
            return []
        ids = [f[:-5] for f in os.listdir(self.content) if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*\.json", f)]
        return sorted(ids, key=natural)

    def raw(self, lid):
        return load_json(os.path.join(self.content, lid + ".json"))

    def lesson(self, lid):
        return normalize(self.raw(lid), self.reader)

    def groups(self, ids):
        """Resolve academy.json "groups" to lists of lesson ids; ungrouped lessons get a group of their own."""
        out, used = [], set()
        for g in self.cfg.get("groups") or []:
            if "lessons" in g:
                ls = [i for i in g["lessons"] if i in ids]
            else:
                pre = g.get("prefix", "")
                ls = [i for i in ids if re.fullmatch(re.escape(pre) + r"\d.*", i)] if pre else list(ids)
            ls = [i for i in ls if i not in used]
            used.update(ls)
            out.append({"title": g.get("title", "Lessons"), "blurb": g.get("blurb", ""), "intro": g.get("intro"), "lessons": ls})
        rest = [i for i in ids if i not in used]
        if rest:
            out.append({"title": "Lessons" if not out else "More lessons", "blurb": "", "intro": None, "lessons": rest})
        return out

    def intros(self, ids):
        return {g["intro"] for g in self.groups(ids) if g.get("intro")}


def normalize(node, reader=None):
    """Lesson files may use the older suffixed field names (name_en, body_en, {"en": …, "fa": …}).
    The portal reads one shape: no language suffix, "text" for a definition, "tr" for the reader's language."""
    if isinstance(node, list):
        return [normalize(x, reader) for x in node]
    if not isinstance(node, dict):
        return node
    out, legacy = {}, {}
    for k, v in node.items():
        v = normalize(v, reader)
        if k == "en":
            legacy["text"] = v
        elif k.endswith("_en"):
            legacy[k[:-3]] = v
        elif reader and k == reader:
            legacy["tr"] = v
        elif reader and k.endswith("_" + reader):
            continue  # reader-language copies of whole fields are not shown
        else:
            out[k] = v
    for k, v in legacy.items():
        out.setdefault(k, v)
    return out

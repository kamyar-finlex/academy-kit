"""Local Studio orchestration: connect GitHub repos, list doc files, and build academies.

Standard library only. Coordinates ``github_app.py``, ``validate.py``, ``build.py``,
and ``sync.py`` while keeping every generated academy strictly outside the kit repo.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ENGINE, Academy, load_json, natural, save_json  # noqa: E402
import github_app  # noqa: E402
import sync as sync_mod  # noqa: E402
import validate  # noqa: E402

DOC_EXT = {".md", ".mdx", ".txt", ".rst", ".adoc"}
CODE_EXT = {".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".yaml", ".yml", ".json", ".toml", ".sh"}
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".next", "target", "vendor"}
DEFAULT_WORKSPACE = os.environ.get("ACADEMY_WORKSPACE") or "~/academies"

LANGS = {
    "persian": ("fa", True, "[\\u0600-\\u06FF]"),
    "arabic": ("ar", True, "[\\u0600-\\u06FF]"),
    "hebrew": ("he", True, "[\\u0590-\\u05FF]"),
    "german": ("de", False, None),
    "french": ("fr", False, None),
    "spanish": ("es", False, None),
    "turkish": ("tr", False, None),
    "polish": ("pl", False, None),
    "russian": ("ru", False, "[\\u0400-\\u04FF]"),
    "ukrainian": ("uk", False, "[\\u0400-\\u04FF]"),
    "hindi": ("hi", False, "[\\u0900-\\u097F]"),
    "chinese": ("zh", False, "[\\u4E00-\\u9FFF]"),
    "english": ("en", False, None),
}


def kit_root():
    return os.path.realpath(os.path.join(ENGINE, "..", "..", ".."))


def ensure_outside_kit(folder):
    real = os.path.realpath(os.path.abspath(os.path.expanduser(folder)))
    kit = kit_root()
    if os.path.commonpath([kit, real]) == kit:
        raise ValueError(
            f"{real} is inside the kit ({kit}). Academies hold private content and must live outside the kit."
        )
    return real


def default_academy_dir(full_name):
    """Isolate each repository in its own workspace folder: ~/academies/<org>/<repo>."""
    base = os.path.expanduser(DEFAULT_WORKSPACE)
    clean = (full_name or "").strip("/")
    parts = [re.sub(r"[^a-z0-9._-]+", "-", p.lower()).strip("-") for p in clean.split("/") if p]
    if len(parts) >= 2:
        return os.path.join(base, parts[-2], parts[-1])
    slug = parts[0] if parts else "repo"
    return os.path.join(base, slug)


def available_languages():
    return [k.capitalize() for k in sorted(LANGS.keys())]


def list_workspaces(extra_dirs=()):
    """Discover isolated academy workspaces outside the kit."""
    base = os.path.expanduser(DEFAULT_WORKSPACE)
    candidates = set()
    if os.path.isdir(base):
        for root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and d not in ("site", "build", "source-repo", "content", "videos")]
            if "academy.json" in files:
                candidates.add(os.path.realpath(root))
                dirs[:] = []
            elif os.path.relpath(root, base).count(os.sep) >= 2:
                dirs[:] = []
    for d in extra_dirs:
        if d and os.path.exists(os.path.join(d, "academy.json")):
            candidates.add(os.path.realpath(d))
    out = []
    for d in sorted(candidates):
        try:
            ac = Academy(d)
            src = ac.cfg.get("source") or {}
            out.append({
                "dir": d,
                "title": ac.cfg.get("title") or os.path.basename(d),
                "repo": src.get("label") or src.get("repo") or "",
                "branch": src.get("branch") or "",
                "docs_root": src.get("docs_root") or "",
                "lessons": len(ac.ids()),
                "built": os.path.exists(os.path.join(ac.out, "index.html")),
            })
        except Exception:
            continue
    return out


def _title_from_file(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for _ in range(25):
                line = f.readline()
                if not line:
                    break
                m = re.match(r"^#\s+(.+)$", line.strip())
                if m:
                    return m.group(1).strip()
    except OSError:
        pass
    return ""


def _sha1(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def scan_repo_files(ac, include_code=False):
    """Scan the connected repository's docs_root and return files with sync status."""
    src = ac.cfg.get("source") or {}
    docs_root = (src.get("docs_root") or "").strip("/")
    repo_dir = ac.path(src.get("clone", "source-repo") if src.get("type") == "git" else src.get("path", ""))
    base = os.path.join(repo_dir, docs_root) if docs_root else repo_dir
    if not os.path.isdir(base):
        raise ValueError(f"Docs path not found in repository: {docs_root or '.'}")

    smap = load_json(ac.path(src.get("sources", "sources.json")), {})
    lessons_map = smap.get("lessons") or {}
    state = load_json(ac.path(src.get("state", "sync-state.json")), {})
    old_manifest = state.get("manifest") or {}

    by_file = {}
    for lid, meta in lessons_map.items():
        for p in meta.get("sources") or []:
            by_file.setdefault(p, []).append(lid)

    allowed = DOC_EXT | (CODE_EXT if include_code else set())
    items = []
    for root, dirs, names in os.walk(base):
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d not in SKIP_DIRS)
        for name in sorted(names):
            if name.startswith("."):
                continue
            ext = os.path.splitext(name)[1].lower()
            if ext not in allowed:
                continue
            full = os.path.join(root, name)
            rel = os.path.relpath(full, base).replace(os.sep, "/")
            mapped = sorted(by_file.get(rel, []), key=natural)
            digest = _sha1(full)
            if not mapped:
                status = "new"
            elif old_manifest and old_manifest.get(rel) and old_manifest.get(rel) != digest:
                status = "changed"
            else:
                status = "synced"
            items.append({
                "path": rel,
                "name": name,
                "ext": ext,
                "is_doc": ext in DOC_EXT,
                "size": os.path.getsize(full),
                "title": _title_from_file(full),
                "lessons": mapped,
                "status": status,
            })
    return items


def read_repo_file(ac, rel_path, max_bytes=120000):
    """Safely read one file inside the academy's source-repo."""
    src = ac.cfg.get("source") or {}
    docs_root = (src.get("docs_root") or "").strip("/")
    repo_dir = ac.path(src.get("clone", "source-repo") if src.get("type") == "git" else src.get("path", ""))
    base = os.path.realpath(os.path.join(repo_dir, docs_root) if docs_root else repo_dir)
    target = os.path.realpath(os.path.join(base, rel_path))
    if os.path.commonpath([base, target]) != base or not os.path.isfile(target):
        raise ValueError("File not found inside repository docs root")
    with open(target, encoding="utf-8", errors="replace") as f:
        text = f.read(max_bytes + 1)
    truncated = len(text) > max_bytes
    return {"path": rel_path, "content": text[:max_bytes], "truncated": truncated}


def init_or_update_academy(target_dir, repo_url, full_name, branch="main", docs_root="",
                           installation_id=None, title="", reader="", language="English"):
    """Ensure external academy folder exists, initialize config, and clone/pull source-repo."""
    d = ensure_outside_kit(target_dir)
    os.makedirs(os.path.join(d, "content"), exist_ok=True)
    cfg_path = os.path.join(d, "academy.json")
    repo_short = full_name.split("/")[-1] if "/" in full_name else full_name
    clean_title = title.strip() or f"{repo_short} Academy"

    if os.path.exists(cfg_path):
        cfg = load_json(cfg_path)
    else:
        lang = LANGS.get(language.lower(), (language[:2].lower(), False, None))
        cfg = {
            "id": re.sub(r"[^a-z0-9]+", "-", clean_title.lower()).strip("-") or "academy",
            "title": clean_title,
            "subtitle": f"Generated from {full_name}",
            "domain": "internal documentation",
            "language": {"code": lang[0], "name": language},
            "groups": [],
            "home": {"heading": "Start here", "intro": "", "source_note": f"Built from {full_name}"},
            "ai": {"models": ["gemma4:e4b", "gemma3:4b"]},
        }
    if title.strip():
        cfg["title"] = clean_title
    if reader and reader.lower() != (cfg.get("language") or {}).get("name", "English").lower():
        code, rtl, detect = LANGS.get(reader.lower(), (reader[:2].lower(), False, None))
        cfg["reader"] = {
            "code": code,
            "name": reader,
            "rtl": rtl,
            "badge": code.upper(),
            "example": {"tr": "", "meaning": ""},
        }
        if detect:
            cfg["reader"]["detect"] = detect
    elif reader == "":
        cfg.pop("reader", None)

    source_block = {
        "type": "git",
        "repo": repo_url,
        "docs_root": (docs_root or "").strip("/"),
        "branch": branch or "main",
        "label": full_name,
    }
    if installation_id:
        source_block["installation_id"] = int(installation_id)
    cfg["source"] = source_block
    save_json(cfg_path, cfg)

    sources_path = os.path.join(d, "sources.json")
    if not os.path.exists(sources_path):
        save_json(sources_path, {"shared_sources": [], "lessons": {}})

    gi_path = os.path.join(d, ".gitignore")
    if not os.path.exists(gi_path):
        with open(gi_path, "w", encoding="utf-8") as f:
            f.write("site/\nbuild/\nsource-repo/\nsync-state.json\n")

    priv_path = os.path.join(d, "PRIVATE.md")
    if not os.path.exists(priv_path):
        with open(priv_path, "w", encoding="utf-8") as f:
            f.write(
                "# Private\n\nThis folder is an academy built from your repository documents.\n"
                "Keep it out of public repositories and never store GitHub tokens in academy.json.\n"
            )

    repo_dir = os.path.join(d, "source-repo")
    commit = github_app.git_clone_or_pull(
        repo_url,
        repo_dir,
        branch=branch or None,
        installation_id=installation_id,
    )
    return Academy(d), commit


def list_ollama_models(ollama_url):
    try:
        with urllib.request.urlopen(f"{ollama_url}/api/tags", timeout=3) as r:
            data = json.loads(r.read().decode("utf-8"))
        return [m["name"] for m in (data.get("models") or []) if m.get("name")]
    except Exception:
        return []


def _ollama_chat(ollama_url, model, system_prompt, user_prompt, timeout=240):
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.2},
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{ollama_url}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            res = json.loads(r.read().decode("utf-8"))
    except urllib.error.URLError as e:
        raise RuntimeError(f"Ollama is not reachable at {ollama_url}: {e.reason}")
    text = ((res.get("message") or {}).get("content") or "").strip()
    return _extract_json(text)


def _extract_json(text):
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.I)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end > start:
            return json.loads(cleaned[start:end + 1])
        raise


def _normalize_lesson(lid, raw, fallback_title):
    """Coerce model output into a valid lesson shape that passes validate.py."""
    data = dict(raw) if isinstance(raw, dict) else {}
    data["id"] = lid
    data["name"] = str(data.get("name") or fallback_title or f"Lesson {lid}").strip()[:80]
    data["tagline"] = str(data.get("tagline") or f"Overview of {data['name']}").strip()
    if not str(data.get("why") or "").strip():
        data["why"] = data["tagline"]

    secs = []
    for i, s in enumerate(data.get("sections") or []):
        if not isinstance(s, dict):
            continue
        heading = str(s.get("heading") or f"Part {i + 1}").strip()
        body = s.get("body")
        if isinstance(body, str):
            body = [body]
        elif isinstance(body, list):
            body = [str(b).strip() for b in body if str(b).strip()]
        else:
            body = []
        if not body:
            continue
        sec = {"heading": heading, "body": body}
        if str(s.get("explain") or "").strip():
            sec["explain"] = str(s["explain"]).strip()
        secs.append(sec)
    if not secs:
        secs = [{"heading": "Overview", "body": [data["why"]], "explain": data["tagline"]}]
    data["sections"] = secs

    for list_key, req_keys in (
        ("components", ("name", "text")),
        ("relationships", ("with", "text")),
        ("gates", ("gate", "text")),
        ("pitfalls", ("text",)),
        ("key_terms", ("term", "text")),
    ):
        if list_key in data:
            cleaned = [
                item for item in (data.get(list_key) or [])
                if isinstance(item, dict) and all(str(item.get(k) or "").strip() for k in req_keys)
            ]
            if cleaned:
                data[list_key] = cleaned
            else:
                data.pop(list_key, None)

    b = data.get("boundary")
    if isinstance(b, dict) and (b.get("owns") or b.get("not_owns")):
        data["boundary"] = {
            "owns": [str(x) for x in (b.get("owns") or []) if str(x).strip()],
            "not_owns": [str(x) for x in (b.get("not_owns") or []) if str(x).strip()],
        }
        if b.get("explain"):
            data["boundary"]["explain"] = str(b["explain"])
    else:
        data.pop("boundary", None)

    ex = data.get("example")
    if isinstance(ex, dict) and isinstance(ex.get("steps"), list) and any(str(s).strip() for s in ex["steps"]):
        data["example"] = {
            "title": str(ex.get("title") or "Worked example").strip(),
            "steps": [str(s).strip() for s in ex["steps"] if str(s).strip()],
        }
        if ex.get("explain"):
            data["example"]["explain"] = str(ex["explain"]).strip()
    else:
        data.pop("example", None)

    quiz = []
    for q in data.get("quiz") or []:
        if not isinstance(q, dict):
            continue
        opts = [str(o).strip() for o in (q.get("options") or []) if str(o).strip()]
        ans = q.get("answer")
        if str(q.get("q") or "").strip() and len(opts) >= 2 and isinstance(ans, int) and 0 <= ans < len(opts):
            quiz.append({
                "q": str(q["q"]).strip(),
                "options": opts,
                "answer": ans,
                "why": str(q.get("why") or "Check the lesson section above for the exact rule.").strip(),
            })
    if quiz:
        data["quiz"] = quiz
    else:
        data.pop("quiz", None)
    data.pop("video", None)
    return data


def _plan_lessons(ollama_url, model, repo_label, file_docs):
    """Ask Ollama to group selected source files into coherent topic-based lessons."""
    if len(file_docs) == 1:
        f = file_docs[0]
        return {
            "groups": [{"title": "Lessons", "blurb": f"Documentation from {repo_label}", "lessons": ["L1"]}],
            "lessons": [{"id": "L1", "name": f["title"] or f["name"], "sources": [f["path"]]}],
        }
    listing = "\n".join(
        f"- {d['path']} (title: {d['title'] or d['name']}, size: {len(d['content'])} chars)"
        for d in file_docs
    )
    sys_p = (
        "You plan learning academies from documentation files. Return ONLY JSON with:\n"
        '{"groups":[{"title":"Group Name","blurb":"1 line","lessons":["L1","L2"]}],'
        '"lessons":[{"id":"L1","name":"Short 2-5 word title","sources":["path/to/file.md"]}]}\n'
        "Rules: Use short IDs L1, L2, ...; combine small related files into 1 lesson (target 2-12 lessons); "
        "every selected file path must appear in at least one lesson."
    )
    user_p = f"Repository: {repo_label}\nSelected files:\n{listing}"
    try:
        plan = _ollama_chat(ollama_url, model, sys_p, user_p, timeout=120)
        valid_paths = {d["path"] for d in file_docs}
        lessons = []
        covered = set()
        for idx, item in enumerate(plan.get("lessons") or [], 1):
            lid = re.sub(r"[^A-Za-z0-9_-]", "", str(item.get("id") or f"L{idx}")) or f"L{idx}"
            srcs = [s for s in (item.get("sources") or []) if s in valid_paths]
            if not srcs:
                continue
            covered.update(srcs)
            lessons.append({"id": lid, "name": str(item.get("name") or lid)[:60], "sources": srcs})
        missing = [d for d in file_docs if d["path"] not in covered]
        for d in missing:
            lid = f"L{len(lessons) + 1}"
            lessons.append({"id": lid, "name": d["title"] or os.path.splitext(d["name"])[0], "sources": [d["path"]]})
        if lessons:
            lesson_ids = [x["id"] for x in lessons]
            groups = []
            used = set()
            for g in plan.get("groups") or []:
                gl = [i for i in (g.get("lessons") or []) if i in lesson_ids and i not in used]
                if gl:
                    used.update(gl)
                    groups.append({"title": str(g.get("title") or "Lessons"), "blurb": str(g.get("blurb") or ""), "lessons": gl})
            rest = [i for i in lesson_ids if i not in used]
            if rest:
                groups.append({"title": "Lessons" if not groups else "More lessons", "blurb": "", "lessons": rest})
            return {"groups": groups, "lessons": lessons}
    except Exception:
        pass
    # Fallback: 1 lesson per file (capped cleanly)
    lessons = [
        {"id": f"L{i}", "name": (d["title"] or os.path.splitext(d["name"])[0])[:60], "sources": [d["path"]]}
        for i, d in enumerate(file_docs, 1)
    ]
    return {
        "groups": [{"title": "Lessons", "blurb": f"Documentation from {repo_label}", "lessons": [l["id"] for l in lessons]}],
        "lessons": lessons,
    }


def _generate_one_lesson(ollama_url, model, plan_item, doc_texts, lang_name, reader_name):
    tr_hint = (
        f'Include "tr" on key_terms with the {reader_name} translation + brief gloss.'
        if reader_name else ""
    )
    sys_p = (
        f"Write ONE structured learning lesson in {lang_name} strictly grounded in the provided source documents. "
        "Never invent facts, dates, or rules not in the sources. Return ONLY valid JSON matching:\n"
        '{"id":"' + plan_item["id"] + '","name":"2-5 words","tagline":"1 sentence",'
        '"why":"2-4 sentences why it matters",'
        '"sections":[{"heading":"...","body":["paragraph","- bullet"],"explain":"2-4 plain-words sentences"}],'
        '"components":[{"name":"...","text":"..."}],'
        '"example":{"title":"...","steps":["step 1","step 2"],"explain":"..."},'
        '"pitfalls":[{"text":"..."}],'
        '"key_terms":[{"term":"...","text":"definition"}],'
        '"quiz":[{"q":"...","options":["A","B","C","D"],"answer":0,"why":"..."}]}\n'
        f"Aim for 3-6 sections, 4-8 key_terms, and 3-5 quiz questions (spread answer index across 0-3). {tr_hint}"
    )
    bundle = "\n\n---\n\n".join(
        f"FILE: {path}\n{content[:18000]}" for path, content in doc_texts
    )
    raw = _ollama_chat(ollama_url, model, sys_p, f"Lesson topic: {plan_item['name']}\n\n{bundle}", timeout=240)
    return _normalize_lesson(plan_item["id"], raw, plan_item["name"])


class JobManager:
    """Thread-safe tracker for asynchronous academy generation jobs."""

    def __init__(self, ollama_url, on_built=None):
        self.ollama_url = ollama_url
        self.on_built = on_built
        self._lock = threading.Lock()
        self._jobs = {}

    def get(self, job_id):
        with self._lock:
            j = self._jobs.get(job_id)
            return dict(j) if j else None

    def _update(self, job_id, **fields):
        with self._lock:
            j = self._jobs[job_id]
            j.update(fields)
            if "log" in fields:
                pass

    def _log(self, job_id, msg):
        with self._lock:
            self._jobs[job_id]["logs"].append(msg)

    def start_generate(self, academy_dir, files, model="", title="", reader=""):
        job_id = uuid.uuid4().hex[:12]
        with self._lock:
            self._jobs[job_id] = {
                "id": job_id,
                "status": "running",
                "stage": "preparing",
                "progress": 0,
                "total": max(len(files), 1),
                "current": "",
                "logs": ["Starting academy generation…"],
                "error": None,
                "academy_dir": academy_dir,
            }
        t = threading.Thread(
            target=self._run_generate,
            args=(job_id, academy_dir, files, model, title, reader),
            daemon=True,
        )
        t.start()
        return job_id

    def _run_generate(self, job_id, academy_dir, files, model, title, reader):
        try:
            ac = Academy(academy_dir)
            if title.strip():
                ac.cfg["title"] = title.strip()
            lang_name = (ac.cfg.get("language") or {}).get("name", "English")
            if reader and reader.lower() != lang_name.lower():
                code, rtl, detect = LANGS.get(reader.lower(), (reader[:2].lower(), False, None))
                ac.cfg["reader"] = {"code": code, "name": reader, "rtl": rtl, "badge": code.upper(), "example": {"tr": "", "meaning": ""}}
                if detect:
                    ac.cfg["reader"]["detect"] = detect
            save_json(ac.path("academy.json"), ac.cfg)
            ac = Academy(academy_dir)

            models = list_ollama_models(self.ollama_url)
            chosen = model or next((m for m in (ac.cfg.get("ai") or {}).get("models", []) if m in models), None) or (models[0] if models else "gemma4:e4b")
            self._log(job_id, f"Using local model: {chosen}")

            file_docs = []
            for rel in files:
                doc = read_repo_file(ac, rel, max_bytes=24000)
                file_docs.append({
                    "path": rel,
                    "name": os.path.basename(rel),
                    "title": _title_from_file(os.path.join(ac.path((ac.cfg.get("source") or {}).get("clone", "source-repo")), (ac.cfg.get("source") or {}).get("docs_root", "").strip("/"), rel)),
                    "content": doc["content"],
                })

            self._update(job_id, stage="planning", current="Grouping documents into lessons")
            repo_label = (ac.cfg.get("source") or {}).get("label") or ac.cfg.get("title", "Repository")
            plan = _plan_lessons(self.ollama_url, chosen, repo_label, file_docs)
            planned = plan["lessons"]
            self._update(job_id, total=len(planned) + 1, progress=0)
            self._log(job_id, f"Planned {len(planned)} lesson(s) from {len(file_docs)} file(s)")

            by_path = {d["path"]: d["content"] for d in file_docs}
            lang_name = (ac.cfg.get("language") or {}).get("name", "English")
            reader_name = (ac.cfg.get("reader") or {}).get("name", "")
            sources_json = load_json(ac.path("sources.json"), {"shared_sources": [], "lessons": {}})
            lessons_map = sources_json.setdefault("lessons", {})

            # Replace generated content for clean build of selected repo docs
            os.makedirs(ac.content, exist_ok=True)
            for old in os.listdir(ac.content):
                if old.endswith(".json"):
                    os.remove(os.path.join(ac.content, old))
            lessons_map.clear()

            all_ids = [p["id"] for p in planned]
            for idx, item in enumerate(planned, 1):
                self._update(job_id, stage="generating", current=f"{item['id']} · {item['name']}", progress=idx - 1)
                self._log(job_id, f"Writing {item['id']} ({item['name']})…")
                docs_bundle = [(p, by_path[p]) for p in item["sources"] if p in by_path]
                lesson_obj = _generate_one_lesson(self.ollama_url, chosen, item, docs_bundle, lang_name, reader_name)
                errs, _ = validate.check_lesson(item["id"], lesson_obj, all_ids, ac.reader)
                if errs:
                    raise RuntimeError(f"Lesson {item['id']} failed validation: {'; '.join(errs)}")
                save_json(os.path.join(ac.content, item["id"] + ".json"), lesson_obj)
                lessons_map[item["id"]] = {"sources": item["sources"]}

            ac.cfg["groups"] = plan["groups"]
            if chosen not in ((ac.cfg.get("ai") or {}).get("models") or []):
                ac.cfg.setdefault("ai", {})["models"] = [chosen]
            save_json(ac.path("academy.json"), ac.cfg)
            save_json(ac.path("sources.json"), sources_json)

            self._update(job_id, stage="building", current="Building portal site", progress=len(planned))
            self._log(job_id, "Running build.py…")
            proc = subprocess.run(
                [sys.executable, os.path.join(ENGINE, "build.py"), academy_dir, "--no-video"],
                capture_output=True,
                text=True,
            )
            if proc.returncode != 0:
                raise RuntimeError((proc.stderr or proc.stdout or "build failed").strip())

            # Record sync baseline commit if source-repo is a git checkout
            ac = Academy(academy_dir)
            repo_dir = ac.path((ac.cfg.get("source") or {}).get("clone", "source-repo"))
            if os.path.isdir(os.path.join(repo_dir, ".git")):
                rev = subprocess.run(["git", "-C", repo_dir, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
                if rev:
                    sy = sync_mod.Sync(ac)
                    sy.state["manifest"] = sy.manifest()
                    sy.record(rev, all_ids, "Created from GitHub repository")

            if self.on_built:
                self.on_built(ac)

            self._update(job_id, status="done", stage="done", progress=len(planned) + 1, current="Ready")
            self._log(job_id, f"Built {len(all_ids)} lesson(s) -> {ac.out}")
        except Exception as e:
            self._update(job_id, status="error", stage="error", error=str(e))
            self._log(job_id, f"Error: {e}")

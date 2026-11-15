"""GitHub App authentication, App Manifest onboarding, and read-only git fetch.

Standard library + local ``openssl`` and ``git`` binaries only.
Credentials (PEM private key, client secret, webhook secret) stay outside the
repository in ``~/.config/academy-kit/github-app.json`` (mode 0600) or env vars,
and installation tokens are held in memory only—never written to ``academy.json``
or ``.git/config``.
"""
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import ssl
import stat
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

GITHUB_API = os.environ.get("ACADEMY_GITHUB_API", "https://api.github.com").rstrip("/")
DEFAULT_CONFIG = "~/.config/academy-kit/github-app.json"
USER_AGENT = "academy-kit/1.0"

_TOKEN_LOCK = threading.Lock()
_TOKEN_CACHE = {}  # installation_id -> (token, expires_epoch)


def config_path():
    """Return the external path where GitHub App credentials are stored."""
    return os.path.expanduser(os.environ.get("ACADEMY_GITHUB_APP_CONFIG") or DEFAULT_CONFIG)


def _b64u(data):
    if isinstance(data, str):
        data = data.encode("utf-8")
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def load_config():
    """Load GitHub App config from env vars or external config file."""
    env_id = os.environ.get("ACADEMY_GITHUB_APP_ID", "").strip()
    env_pem = os.environ.get("ACADEMY_GITHUB_PEM", "").strip()
    env_pem_path = os.environ.get("ACADEMY_GITHUB_PEM_PATH", "").strip()
    if env_id and (env_pem or env_pem_path):
        pem = env_pem or open(os.path.expanduser(env_pem_path), encoding="utf-8").read()
        return {
            "id": int(env_id) if env_id.isdigit() else env_id,
            "pem": pem,
            "slug": os.environ.get("ACADEMY_GITHUB_APP_SLUG", ""),
            "name": os.environ.get("ACADEMY_GITHUB_APP_NAME", "Academy Kit"),
            "webhook_secret": os.environ.get("ACADEMY_GITHUB_WEBHOOK_SECRET", ""),
            "source": "env",
        }
    path = config_path()
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    data["source"] = "file"
    return data


def save_config(cfg):
    """Persist GitHub App credentials outside the repository with 0600 permissions."""
    path = config_path()
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def delete_config():
    """Remove local GitHub App credentials and clear cached installation tokens."""
    with _TOKEN_LOCK:
        _TOKEN_CACHE.clear()
    path = config_path()
    if os.path.exists(path):
        os.remove(path)


def public_status():
    """Return safe, secret-free GitHub App status for the UI."""
    cfg = load_config()
    if not cfg or not cfg.get("id") or not cfg.get("pem"):
        return {"configured": False}
    slug = cfg.get("slug") or ""
    return {
        "configured": True,
        "app_id": cfg["id"],
        "name": cfg.get("name") or "Academy Kit",
        "slug": slug,
        "html_url": cfg.get("html_url") or (f"https://github.com/apps/{slug}" if slug else ""),
        "install_url": f"https://github.com/apps/{slug}/installations/new" if slug else "",
        "owner": cfg.get("owner") or "",
        "source": cfg.get("source", "file"),
    }


def _sign_rs256(message_bytes, pem_text):
    openssl = shutil.which("openssl")
    if not openssl:
        raise RuntimeError("openssl binary is required to sign GitHub App JWTs")
    fd, pem_path = tempfile.mkstemp(prefix="ak-gh-", suffix=".pem")
    try:
        os.chmod(pem_path, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(pem_text.strip() + "\n")
        proc = subprocess.run(
            [openssl, "dgst", "-sha256", "-sign", pem_path],
            input=message_bytes,
            capture_output=True,
            check=True,
        )
        return proc.stdout
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to sign JWT with PEM key: {e.stderr.decode('utf-8', 'replace').strip()}")
    finally:
        if os.path.exists(pem_path):
            os.remove(pem_path)


def create_app_jwt(cfg=None):
    """Build a short-lived RS256 JWT for authenticating as the GitHub App."""
    cfg = cfg or load_config()
    if not cfg or not cfg.get("id") or not cfg.get("pem"):
        raise RuntimeError("GitHub App is not configured")
    now = int(time.time())
    header = _b64u(json.dumps({"alg": "RS256", "typ": "JWT"}, separators=(",", ":")))
    payload = _b64u(json.dumps({"iat": now - 60, "exp": now + 540, "iss": str(cfg["id"])}, separators=(",", ":")))
    signing_input = f"{header}.{payload}".encode("ascii")
    sig = _b64u(_sign_rs256(signing_input, cfg["pem"]))
    return f"{header}.{payload}.{sig}"


def _ssl_context():
    """Return a verified SSL context, falling back to OS CA bundles when Python lacks one."""
    vp = ssl.get_default_verify_paths()
    if (vp.cafile and os.path.exists(vp.cafile)) or (vp.capath and os.path.isdir(vp.capath)):
        return ssl.create_default_context()
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        pass
    for ca in (
        "/etc/ssl/cert.pem",
        "/etc/ssl/certs/ca-certificates.crt",
        "/etc/pki/tls/certs/ca-bundle.crt",
        "/opt/homebrew/etc/openssl@3/cert.pem",
        "/usr/local/etc/openssl@3/cert.pem",
    ):
        if os.path.exists(ca):
            return ssl.create_default_context(cafile=ca)
    return ssl.create_default_context()


def _api(path, method="GET", token=None, body=None, bearer_jwt=None):
    url = path if path.startswith("http") else f"{GITHUB_API}{path}"
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": USER_AGENT,
    }
    if bearer_jwt:
        headers["Authorization"] = f"Bearer {bearer_jwt}"
    elif token:
        headers["Authorization"] = f"token {token}"
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20, context=_ssl_context()) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        msg = e.read().decode("utf-8", "replace")
        try:
            detail = json.loads(msg).get("message") or msg
        except Exception:
            detail = msg
        raise RuntimeError(f"GitHub API ({e.code}): {detail}")


def _is_local_url(url):
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    return host in ("localhost", "127.0.0.1", "0.0.0.0", "::1")


def build_manifest(base_url, org="", name="", webhook_url=""):
    """Build a GitHub App Manifest payload for one-click org or account registration."""
    base = base_url.rstrip("/")
    clean_org = re.sub(r"[^A-Za-z0-9-]", "", org or "")
    raw_name = (name or "").strip()
    if not raw_name or raw_name.lower() == "academy kit":
        tag = clean_org[:14] if clean_org else secrets.token_hex(2)
        app_name = f"Academy Kit {tag}"[:34]
    else:
        app_name = raw_name[:34]
    action_url = (
        f"https://github.com/organizations/{clean_org}/settings/apps/new"
        if clean_org else "https://github.com/settings/apps/new"
    )
    hook = (webhook_url or "").strip()
    if not hook and not _is_local_url(base) and base.startswith("https://"):
        hook = base + "/api/github/webhook"
    if hook and not _is_local_url(hook):
        hook_attributes = {"url": hook, "active": True}
        default_events = ["push"]
    else:
        # GitHub requires a non-blank public URL inside hook_attributes even when webhooks are off.
        hook_attributes = {"url": "https://example.com/api/github/webhook", "active": False}
        default_events = []
    manifest = {
        "name": app_name,
        "url": base + "/",
        "redirect_url": base + "/api/github/manifest/callback",
        "setup_url": base + "/?github_installed=1",
        "setup_on_update": True,
        "public": False,
        "hook_attributes": hook_attributes,
        "default_permissions": {
            "contents": "read",
            "metadata": "read",
        },
        "default_events": default_events,
    }
    return {"action_url": action_url, "manifest": manifest}


def exchange_manifest_code(code):
    """Complete GitHub App Manifest flow by exchanging the one-time code for App credentials."""
    if not code or not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", code):
        raise ValueError("Invalid manifest code")
    res = _api(f"/app-manifests/{code}/conversions", method="POST")
    owner = (res.get("owner") or {}).get("login") or ""
    cfg = {
        "id": res["id"],
        "slug": res.get("slug", ""),
        "name": res.get("name", "Academy Kit"),
        "html_url": res.get("html_url", ""),
        "client_id": res.get("client_id", ""),
        "client_secret": res.get("client_secret", ""),
        "webhook_secret": res.get("webhook_secret", ""),
        "pem": res["pem"],
        "owner": owner,
    }
    save_config(cfg)
    with _TOKEN_LOCK:
        _TOKEN_CACHE.clear()
    return public_status()


def save_manual_config(app_id, pem_text, webhook_secret=""):
    """Verify and store manually entered GitHub App ID and PEM private key."""
    if not str(app_id).strip().isdigit():
        raise ValueError("App ID must be a number")
    if "PRIVATE KEY-----" not in (pem_text or ""):
        raise ValueError("PEM private key must contain a valid PRIVATE KEY block")
    probe = {"id": int(str(app_id).strip()), "pem": pem_text.strip() + "\n"}
    jwt_tok = create_app_jwt(probe)
    info = _api("/app", bearer_jwt=jwt_tok)
    cfg = {
        "id": info.get("id", probe["id"]),
        "slug": info.get("slug", ""),
        "name": info.get("name", "Academy Kit"),
        "html_url": info.get("html_url", ""),
        "owner": (info.get("owner") or {}).get("login", ""),
        "webhook_secret": webhook_secret or "",
        "pem": probe["pem"],
    }
    save_config(cfg)
    with _TOKEN_LOCK:
        _TOKEN_CACHE.clear()
    return public_status()


def list_installations():
    """List organizations/accounts where this GitHub App is installed."""
    jwt_tok = create_app_jwt()
    items = []
    page = 1
    while page <= 5:
        batch = _api(f"/app/installations?per_page=100&page={page}", bearer_jwt=jwt_tok)
        if not batch:
            break
        for inst in batch:
            acc = inst.get("account") or {}
            items.append({
                "id": inst["id"],
                "account": acc.get("login", ""),
                "type": acc.get("type", "Organization"),
                "avatar_url": acc.get("avatar_url", ""),
                "repository_selection": inst.get("repository_selection", "selected"),
                "html_url": inst.get("html_url", ""),
            })
        if len(batch) < 100:
            break
        page += 1
    return items


def get_installation_token(installation_id):
    """Fetch (and briefly cache in memory) a short-lived installation access token."""
    key = str(installation_id)
    now = time.time()
    with _TOKEN_LOCK:
        cached = _TOKEN_CACHE.get(key)
        if cached and cached[1] - 60 > now:
            return cached[0]
    jwt_tok = create_app_jwt()
    res = _api(f"/app/installations/{key}/access_tokens", method="POST", bearer_jwt=jwt_tok)
    token = res["token"]
    # GitHub installation tokens last 1 hour; cache for 50 minutes.
    with _TOKEN_LOCK:
        _TOKEN_CACHE[key] = (token, now + 3000)
    return token


def list_installation_repos(installation_id):
    """List repositories accessible to the selected GitHub App installation."""
    tok = get_installation_token(installation_id)
    repos = []
    page = 1
    while page <= 5:
        res = _api(f"/installation/repositories?per_page=100&page={page}", token=tok)
        batch = res.get("repositories") or []
        for r in batch:
            repos.append({
                "id": r["id"],
                "full_name": r["full_name"],
                "name": r["name"],
                "private": bool(r.get("private")),
                "default_branch": r.get("default_branch") or "main",
                "description": r.get("description") or "",
                "clone_url": r["clone_url"],
                "html_url": r["html_url"],
            })
        if len(batch) < 100:
            break
        page += 1
    return repos


def list_repo_branches(installation_id, full_name):
    """List branches for a repository accessible via an installation."""
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", full_name):
        raise ValueError("Invalid repository name")
    tok = get_installation_token(installation_id)
    batch = _api(f"/repos/{full_name}/branches?per_page=100", token=tok)
    return [b["name"] for b in batch]


SKIP_TREE_PARTS = {"node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".next", "target", "vendor"}


def list_repo_folders(installation_id, full_name, branch="main"):
    """List directory paths in a repository branch via the Git Trees API."""
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", full_name):
        raise ValueError("Invalid repository name")
    tok = get_installation_token(installation_id)
    ref = urllib.parse.quote(branch or "HEAD", safe="")
    try:
        res = _api(f"/repos/{full_name}/git/trees/{ref}?recursive=1", token=tok)
    except RuntimeError:
        return [""]
    folders = [""]
    for item in res.get("tree") or []:
        if item.get("type") != "tree":
            continue
        p = item.get("path") or ""
        parts = p.split("/")
        if len(parts) > 3 or any(x.startswith(".") or x in SKIP_TREE_PARTS for x in parts):
            continue
        folders.append(p)
        if len(folders) >= 200:
            break
    return folders


def _run_git(args, cwd=None, token=None):
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    askpass = None
    try:
        if token:
            fd, askpass = tempfile.mkstemp(prefix="ak-askpass-", suffix=".sh")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write("#!/bin/sh\ncase \"$1\" in\n  *Username*) echo 'x-access-token' ;;\n  *) printf '%s\\n' \"$ACADEMY_GIT_TOKEN\" ;;\nesac\n")
            os.chmod(askpass, stat.S_IRUSR | stat.S_IXUSR)
            env["GIT_ASKPASS"] = askpass
            env["ACADEMY_GIT_TOKEN"] = token
        proc = subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, text=True)
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()
            if token:
                err = err.replace(token, "***")
            raise RuntimeError(f"git {' '.join(args[:2])} failed: {err}")
        return proc.stdout.strip()
    finally:
        if askpass and os.path.exists(askpass):
            os.remove(askpass)


def git_clone_or_pull(repo_url, dest_dir, branch=None, installation_id=None):
    """Clone or fast-forward update a read-only source repository without persisting tokens."""
    if not re.match(r"^https://[A-Za-z0-9._-]+/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?$", repo_url):
        raise ValueError("Repository URL must be a clean https:// GitHub URL without embedded credentials")
    token = get_installation_token(installation_id) if installation_id else None
    git_dir = os.path.join(dest_dir, ".git")
    if not os.path.isdir(git_dir):
        os.makedirs(os.path.dirname(dest_dir), exist_ok=True)
        args = ["clone", "--depth", "1"]
        if branch:
            args += ["--branch", branch]
        args += [repo_url, dest_dir]
        _run_git(args, token=token)
    else:
        _run_git(["remote", "set-url", "origin", repo_url], cwd=dest_dir)
        target = branch or "HEAD"
        _run_git(["fetch", "--depth", "1", "origin", target], cwd=dest_dir, token=token)
        _run_git(["checkout", "-B", branch or "main", "FETCH_HEAD"], cwd=dest_dir)
    return _run_git(["rev-parse", "HEAD"], cwd=dest_dir)


def verify_webhook_signature(payload_bytes, signature_header):
    """Verify GitHub X-Hub-Signature-256 HMAC when a webhook secret is configured."""
    cfg = load_config()
    secret = (cfg or {}).get("webhook_secret") or ""
    if not secret:
        return True
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header)

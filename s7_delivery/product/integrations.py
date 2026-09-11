"""The GitHub integration layer — what the tenant allows S7 to do with its
git hosting, read from the active delivery profile's `integrations/github.md`
(`factory/layers.py`), plus the two read-only probes the admin surface shows.

Disciplines:

- **Credentials never live in configuration.** Publication, CI sync and
  repository creation shell out to the `gh` CLI and use whatever login it
  already holds (hard rule 3). `gh_status()` reports *whether* that login
  exists and *who* it is, never a token.
- **Settings are inputs to checks the engine already makes.** The owner
  allowlist gates `intake_connect_repo`, `allow_repo_creation` gates
  `intake_create_new_app_repo`, `refuse_branch_names` feeds
  `publication.check_branch`. Nothing here bypasses a check; a profile can
  only tighten what the code refuses.
- **Probes are explicit operator actions.** `test_connection()` runs
  `git ls-remote` against a URL the operator typed; it is never called from
  a run, so a locked-down environment with no network still runs every run.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from typing import Any
from urllib.parse import urlparse

from s7_delivery.factory import layers
from s7_delivery.product.config import ConfigError, now_iso

FILE_ID = "github"
DEFAULTS: dict[str, Any] = {
    "host": "github.com",
    "allowed_owners": [],
    "allow_local_paths": True,
    "allow_repo_creation": True,
    "refuse_branch_names": ["main", "master"],
    "expected_gh_login": "",
}
_SSH_RE = re.compile(r"^(?:ssh://)?git@(?P<host>[^:/]+)[:/](?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$")
_OWNER_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")


class IntegrationError(ConfigError):
    """A repository, owner or action the active profile does not allow."""


def validate(data: Any) -> dict[str, Any]:
    """The shape the engine's checks rely on; refused before it is written."""
    if not isinstance(data, dict):
        raise IntegrationError("github integration body must be a JSON object")
    out = {**DEFAULTS, **{k: v for k, v in data.items() if k in DEFAULTS}}
    if not isinstance(out["host"], str) or not out["host"].strip():
        raise IntegrationError("github: 'host' must be a non-empty string")
    owners = out["allowed_owners"]
    if not isinstance(owners, list) or not all(isinstance(o, str) for o in owners):
        raise IntegrationError("github: 'allowed_owners' must be a list of owner names")
    bad = [o for o in owners if not _OWNER_RE.match(o)]
    if bad:
        raise IntegrationError(f"github: invalid owner names {bad}")
    for key in ("allow_local_paths", "allow_repo_creation"):
        if not isinstance(out[key], bool):
            raise IntegrationError(f"github: {key!r} must be true or false")
    names = out["refuse_branch_names"]
    if not isinstance(names, list) or not all(isinstance(n, str) and n.strip() for n in names):
        raise IntegrationError("github: 'refuse_branch_names' must be a list of branch names")
    if not isinstance(out["expected_gh_login"], str):
        raise IntegrationError("github: 'expected_gh_login' must be a string")
    if any(k in data for k in ("token", "password", "secret", "api_key")):
        raise IntegrationError("github: credentials never live in configuration (hard rule 3)")
    return out


def settings() -> dict[str, Any]:
    """The effective settings for the active profile (whatever `layers.use()`
    set — the engine sets it per run). A root without the file — a legacy
    set made before the layer existed falls through to the default anyway —
    yields the defaults, which are exactly the code's previous behaviour."""
    try:
        return validate(layers.structured(FILE_ID))
    except layers.LayerError:
        return dict(DEFAULTS)


# --- checks the engine calls ---------------------------------------------------


def parse_repo_url(url: str) -> dict[str, str]:
    """`{kind, host, owner, repo}` — kind is `https`, `ssh` or `local`."""
    url = url.strip()
    m = _SSH_RE.match(url)
    if m:
        return {"kind": "ssh", "host": m["host"].lower(), "owner": m["owner"], "repo": m["repo"]}
    parsed = urlparse(url)
    if parsed.scheme in ("http", "https") and parsed.netloc:
        parts = [p for p in parsed.path.split("/") if p]
        owner = parts[0] if parts else ""
        repo = parts[1].removesuffix(".git") if len(parts) > 1 else ""
        return {"kind": "https", "host": parsed.hostname or "", "owner": owner, "repo": repo}
    return {"kind": "local", "host": "", "owner": "", "repo": url.rstrip("/\\").split("/")[-1]}


def check_repo_url(url: str, conf: dict[str, Any] | None = None) -> dict[str, str]:
    """Refuse a URL the profile does not allow; return its parsed parts."""
    conf = conf or settings()
    parts = parse_repo_url(url)
    if parts["kind"] == "local":
        if not conf["allow_local_paths"]:
            raise IntegrationError(
                "this delivery profile does not allow connecting a local path — "
                "connect a repository on " + conf["host"]
            )
        return parts
    if parts["host"].lower() != conf["host"].lower():
        raise IntegrationError(
            f"repositories must be on {conf['host']} for this delivery profile, "
            f"not {parts['host'] or 'an unknown host'}"
        )
    owners = [o.lower() for o in conf["allowed_owners"]]
    if owners and parts["owner"].lower() not in owners:
        raise IntegrationError(
            f"owner {parts['owner']!r} is not in this delivery profile's allowed owners "
            f"({', '.join(conf['allowed_owners'])})"
        )
    return parts


def require_repo_creation(conf: dict[str, Any] | None = None) -> None:
    conf = conf or settings()
    if not conf["allow_repo_creation"]:
        raise IntegrationError(
            "this delivery profile does not allow S7 to create repositories — "
            "create the repository by hand and connect it by URL"
        )


def refused_branch_names(conf: dict[str, Any] | None = None) -> tuple[str, ...]:
    conf = conf or settings()
    return tuple(conf["refuse_branch_names"])


# --- probes the admin surface runs -----------------------------------------------


def _run(cmd: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)


def gh_status(conf: dict[str, Any] | None = None) -> dict[str, Any]:
    """Is the `gh` CLI present and logged in, and as whom. Parsed from
    `gh auth status` text; the token is never requested or shown."""
    conf = conf or settings()
    out: dict[str, Any] = {
        "available": shutil.which("gh") is not None,
        "authenticated": False, "login": "", "host": "", "error": "",
        "expected_login": conf["expected_gh_login"], "login_matches": None,
        "checked_at": now_iso(),
    }
    if not out["available"]:
        out["error"] = "gh CLI not found on PATH"
        return out
    try:
        proc = _run(["gh", "auth", "status", "--hostname", conf["host"]], timeout=15)
    except (subprocess.TimeoutExpired, OSError) as exc:
        out["error"] = f"gh auth status failed: {exc}"
        return out
    text = (proc.stdout or "") + (proc.stderr or "")
    login = re.search(r"account\s+(\S+)|as\s+(\S+)\s*\(", text)
    if proc.returncode == 0 and ("Logged in" in text or login):
        out["authenticated"] = True
        out["login"] = (login.group(1) or login.group(2)) if login else ""
        out["host"] = conf["host"]
    else:
        out["error"] = text.strip().splitlines()[-1] if text.strip() else "not logged in"
    if out["expected_login"]:
        out["login_matches"] = (
            out["authenticated"] and out["login"].lower() == out["expected_login"].lower()
        )
    return out


def test_connection(url: str, conf: dict[str, Any] | None = None) -> dict[str, Any]:
    """`git ls-remote --symref <url> HEAD` plus the heads — reachability and
    the default branch, without cloning. The profile's URL checks apply
    first, so a disallowed owner is reported as such, not as unreachable."""
    conf = conf or settings()
    result: dict[str, Any] = {
        "url": url, "reachable": False, "default_branch": "", "heads": 0,
        "error": "", "checked_at": now_iso(),
    }
    try:
        parts = check_repo_url(url, conf)
    except IntegrationError as exc:
        result["error"] = str(exc)
        return result
    result.update({k: parts[k] for k in ("kind", "host", "owner", "repo")})
    try:
        # no --heads: the `ref: refs/heads/<x> HEAD` symref line that names the
        # default branch is only printed when HEAD itself is listed
        proc = _run(["git", "ls-remote", "--symref", url], timeout=30)
    except (subprocess.TimeoutExpired, OSError) as exc:
        result["error"] = f"git ls-remote failed: {exc}"
        return result
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip().splitlines()
        result["error"] = err[-1] if err else f"git exited {proc.returncode}"
        return result
    heads = 0
    for line in proc.stdout.splitlines():
        if line.startswith("ref: refs/heads/"):
            result["default_branch"] = line.split()[1].removeprefix("refs/heads/")
        elif "\trefs/heads/" in line:
            heads += 1
    result["reachable"] = True
    result["heads"] = heads
    return result

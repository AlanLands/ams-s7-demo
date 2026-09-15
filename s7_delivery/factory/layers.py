"""The four-layer delivery system, as files (feature priority #2).

    Rules        s7_delivery/layers/rules/<id>.md    the stable prefix every
                                                     model call of one lane starts with
    Skills       s7_delivery/layers/skills/<id>.md   one per stage: the role text that
                                                     specialises a call
    Tasks        s7_delivery/layers/tasks/<id>.md    the per-call task text, with the
                                                     {{variables}} the workflow supplies
    Workflows    s7_delivery/factory/engine.py       role check → gate check → write →
                 + gates.py + build_phases.py        provenance append → activity append
    Orchestrator apps/control/ + s7_delivery/cli.py  thin surfaces over the same engine

The first two layers are *data*, and this module is their loader. The
mapping onto the prompt-prefix convention in `common/prompt.py` is exact:
`rules` is the Rules layer, `role` is the Skills layer, and `memory`, `ref`
and `task` are supplied per call by the workflow that runs the skill.

Two disciplines, both enforced by tests:

- **The body of a layer file is the prompt text, byte for byte.** Committed
  replay recordings hash the assembled prompt (CLAUDE.md § Determinism), so
  any edit to a rules or skill file is a cache miss on every recording that
  carried the old text. That is the intended cost of changing the delivery
  system, and it is why `tests/test_layers.py` checks every committed
  recording against the current files: an edit without a re-record fails
  loudly instead of silently serving stale prompts.
- **Versions are recorded, never implied.** `history.jsonl` is an
  append-only ledger of (id, sha256, version, note); `record_versions()`
  appends a line for each file whose content changed. A file that differs
  from its last recorded hash is *unrecorded*, and the same test refuses it —
  the versioned-amendment step of feature priority #8 applied to the
  system's own instructions.

Line endings: files are read as bytes and CRLF-normalised before hashing, so
a checkout with `core.autocrlf=true` produces the same hash and the same
prompt as one without (`.gitattributes` also pins them to LF).

Dynamic prompts (added 2026-09-03, the product layer). Three additions, none
of which change what the default files assemble to:

- **The active root is a context variable.** `ACTIVE_ROOT` names the prompt
  set a call resolves against; `use(root)` sets it around a call. The engine
  sets it from the run's `prompt_set`, so every model call of a run reads
  that set's files *at call time* — no module-level constant is ever pinned
  at import. The default set is `s7_delivery/layers/`, the one committed
  recordings hash; custom sets live under the product config directory
  (`s7_delivery/product/prompt_sets.py`).
- **Tasks are the fourth file-backed layer.** `tasks/<id>.md` carries the
  per-call task text with `{{placeholders}}` declared in its frontmatter
  (`variables: a, b`). `render_task()` substitutes them verbatim and refuses
  an undeclared placeholder — an admin edit can restructure a prompt but can
  never reference data the workflow does not supply.
- **Editing is versioned in place.** `write_body()` / `create_file()` /
  `rollback()` write a file and append its ledger line in one step, and every
  recorded version's body is snapshotted under `versions/<id>/v<N>.md`, so
  `diff()` and `rollback()` work from the ledger rather than from memory.

Delivery profiles (added 2026-09-07). The same loader now carries every
configuration layer, not only prompts, and resolves through an overlay:

- **Six layers, one file shape.** Prompts (rules/skills/tasks/playbooks),
  Standards (`standards/` — what developers are told), Templates
  (`templates/` — what S7 generates mechanically), Governance
  (`governance/` — roles × permissions), Models (`models/` — provider and
  model per stage, pricing) and Identity (`identity/` — organisation,
  palette, synthetic domain). Text layers have markdown bodies; structured
  layers have JSON bodies, exactly like playbooks. Standards and templates
  declare `{{variables}}` like tasks and are rendered by `render()`.
- **Overlay, not copy.** A profile root (a directory holding
  `profile.json`) resolves a file from the profile first and falls through
  to the committed default set. `LayerFile.source` says which one answered
  (`default` / `override`). Editing a default file inside a profile is
  copy-on-write: the override is created, then versioned in the profile's
  own ledger; `revert_override()` deletes it and the default shows through
  again. Legacy full-copy prompt sets (no `profile.json`) still resolve as a
  single root.
- **Locked tokens.** A file's frontmatter may declare `locked:` literal
  tokens that every edit must keep — the lines a consumer depends on (a
  branch placeholder, the s7-managed marker). `write_body` refuses an edit
  that drops one, so an operator can restyle a standard but cannot silently
  break the convention the Control Centre reads progress by.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import re
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

LAYERS_ROOT: Path = Path(__file__).resolve().parents[1] / "layers"
HISTORY_FILE = "history.jsonl"
VERSIONS_DIR = "versions"

# The prompt-set root the current call resolves against. `None` means the
# default set. Set by `use()`; read by every accessor through `_root()`.
ACTIVE_ROOT: ContextVar[Path | None] = ContextVar("s7_layers_active_root", default=None)

# Playbooks are the third file-backed layer (added 2026-09-02): the ordered
# steps a self-healing change runs, one file per change type, versioned in the
# same ledger as rules and skills. Their body is JSON, parsed by
# `factory/self_heal.py`; this module treats it as bytes like any other layer.
# Tasks are the fourth (2026-09-03): per-call task text with declared
# `{{variables}}`, rendered by `render_task()`.
_SUBDIR = {
    "rules": "rules", "skill": "skills", "playbook": "playbooks", "task": "tasks",
    # Delivery-profile layers (2026-09-07): developer standards, mechanical
    # templates, and the three structured layers with JSON bodies.
    "standard": "standards", "template": "templates",
    "governance": "governance", "model": "models", "identity": "identity",
    # Integrations (2026-09-07): how S7 may talk to the tenant's git hosting.
    "integration": "integrations",
}
# Layers whose body may carry `{{placeholders}}` declared in `variables:`.
VARIABLE_LAYERS = frozenset({"task", "standard", "template"})
# Layers whose body must parse as JSON (playbooks are validated by
# `playbook()` with their own structural checks; the rest at load).
JSON_LAYERS = frozenset({"governance", "model", "identity", "integration"})
# The six groups the admin surface presents, in order.
LAYER_GROUPS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("prompts", "Prompts — what the models are told", ("rules", "skill", "task", "playbook")),
    ("standards", "Standards — what developers are told", ("standard",)),
    ("templates", "Templates — what S7 generates mechanically", ("template",)),
    ("governance", "Governance — who may decide what", ("governance",)),
    ("models", "Models and economics", ("model",)),
    ("identity", "Identity — the tenant's name and palette", ("identity",)),
    ("integrations", "Integrations — the tenant's git hosting", ("integration",)),
)
# Which layers enter a model call: an edit there misses recordings; an edit
# elsewhere only makes generated artifacts stale.
PROMPT_LAYERS = frozenset({"rules", "skill", "task"})
PROFILE_META = "profile.json"
_ID_RE = re.compile(r"^[a-z][a-z0-9-]{1,63}$")
_PLACEHOLDER_RE = re.compile(r"\{\{([A-Za-z_][A-Za-z0-9_]*)\}\}")


class LayerError(RuntimeError):
    """A layer file is missing or malformed. Raised at import of the module
    that needs it — a missing skill must fail loudly, never fall back."""


@dataclass(frozen=True)
class LayerFile:
    id: str
    layer: str  # "rules" | "skill" | "playbook" | "task"
    title: str
    stage: str
    summary: str
    path: str  # relative to the set root, POSIX separators
    body: str
    sha256: str
    variables: tuple[str, ...] = ()  # variable layers: declared placeholders
    locked: tuple[str, ...] = ()  # literal tokens every edit must keep
    source: str = "default"  # "default" | "override" | "set" (legacy full copy)

    @property
    def short(self) -> str:
        return self.sha256[:8]


def _root(root: Path | None) -> Path:
    """Explicit root wins, then the active prompt set, then the default."""
    return root or ACTIVE_ROOT.get() or LAYERS_ROOT


@contextmanager
def use(root: Path | None) -> Iterator[Path]:
    """Resolve every accessor against `root` for the duration of the block.
    `None` means the default set. Context-local, so concurrent requests on
    different runs never see each other's set."""
    token = ACTIVE_ROOT.set(root)
    try:
        yield _root(None)
    finally:
        ACTIVE_ROOT.reset(token)


def active_root() -> Path:
    return _root(None)


def is_overlay(root: Path | None = None) -> bool:
    """Any root other than the default resolves through the default: a
    delivery profile (overrides only) or a legacy full copy, which may lack
    a layer added after it was made."""
    return _root(root).resolve() != LAYERS_ROOT.resolve()


def is_profile(root: Path | None = None) -> bool:
    """A delivery profile proper — a directory holding `profile.json`."""
    base = _root(root)
    return is_overlay(base) and (base / PROFILE_META).is_file()


def _roots(root: Path | None) -> tuple[Path, ...]:
    """Resolution order, first wins: (root, default) for a profile or a
    legacy set, (default,) for the default itself."""
    base = _root(root)
    if base.resolve() == LAYERS_ROOT.resolve():
        return (LAYERS_ROOT,)
    return (base, LAYERS_ROOT)


def _ledger_root(file_id: str, root: Path | None) -> Path:
    """The root whose `history.jsonl` owns this file's versions: the root
    itself when the file is physically there, else the default set."""
    base = _root(root)
    if not is_overlay(root):
        return base
    lf = get(file_id, root)
    return base if lf.source != "default" else LAYERS_ROOT


def _parse(path: Path, root: Path) -> LayerFile:
    raw = path.read_bytes().decode("utf-8").replace("\r\n", "\n")
    if not raw.startswith("---\n"):
        raise LayerError(f"{path}: missing frontmatter")
    end = raw.find("\n---\n", 4)
    if end < 0:
        raise LayerError(f"{path}: unterminated frontmatter")
    meta: dict[str, str] = {}
    for line in raw[4:end].splitlines():
        if ":" not in line:
            raise LayerError(f"{path}: bad frontmatter line {line!r}")
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip()
    body = raw[end + len("\n---\n"):].rstrip("\n")
    if not body:
        raise LayerError(f"{path}: empty body")
    layer = meta.get("layer", "")
    if layer not in _SUBDIR:
        raise LayerError(
            f"{path}: layer must be one of {', '.join(sorted(_SUBDIR))}, got {layer!r}"
        )
    if path.parent.name != _SUBDIR[layer]:
        raise LayerError(f"{path}: a {layer} file belongs under {_SUBDIR[layer]}/")
    file_id = meta.get("id", "")
    if file_id != path.stem:
        raise LayerError(f"{path}: id {file_id!r} must equal the file name")
    variables = tuple(
        v.strip() for v in meta.get("variables", "").split(",") if v.strip()
    )
    locked = tuple(
        v.strip() for v in (meta.get("locked") or "").split(",") if v.strip()
    )
    if layer in VARIABLE_LAYERS:
        undeclared = sorted(set(_PLACEHOLDER_RE.findall(body)) - set(variables))
        if undeclared:
            raise LayerError(
                f"{path}: placeholders {undeclared} are not declared in `variables:`"
            )
    if layer in JSON_LAYERS:
        try:
            json.loads(body)
        except json.JSONDecodeError as exc:
            raise LayerError(f"{path}: {layer} body is not valid JSON: {exc}") from exc
    for token in locked:
        if token not in body:
            raise LayerError(f"{path}: locked token {token!r} is missing from the body")
    return LayerFile(
        id=file_id,
        layer=layer,
        title=meta.get("title", file_id),
        stage=meta.get("stage", ""),
        summary=meta.get("summary", ""),
        path=path.relative_to(root).as_posix(),
        body=body,
        sha256=hashlib.sha256(body.encode("utf-8")).hexdigest(),
        variables=variables,
        locked=locked,
    )


def load_all(root: Path | None = None) -> dict[str, LayerFile]:
    """Every layer file, keyed by id, resolved through the overlay: the
    default set first, then the profile's overrides replacing by id. Ids are
    unique across all layers so a workflow can name any without ambiguity."""
    roots = _roots(root)
    out: dict[str, LayerFile] = {}
    for base in reversed(roots):
        if base.resolve() == LAYERS_ROOT.resolve():
            source = "default"
        elif (base / PROFILE_META).is_file():
            source = "override"
        else:
            source = "set"
        seen: set[str] = set()
        for sub in _SUBDIR.values():
            for path in sorted((base / sub).glob("*.md")):
                lf = _parse(path, base)
                if lf.id in seen:
                    raise LayerError(f"duplicate layer id {lf.id!r}")
                seen.add(lf.id)
                out[lf.id] = replace(lf, source=source)
    return out


def overridden(root: Path | None = None) -> list[str]:
    """Ids the profile overrides (empty for the default set and legacy sets)."""
    return sorted(lf.id for lf in load_all(root).values() if lf.source == "override")


def get(file_id: str, root: Path | None = None) -> LayerFile:
    files = load_all(root)
    if file_id not in files:
        raise LayerError(
            f"no layer file {file_id!r} under {_root(root)}"
            f" (have: {', '.join(sorted(files))})"
        )
    return files[file_id]


def rules(file_id: str, root: Path | None = None) -> str:
    """The body of a Rules-layer file — the `rules` slot of `PromptLayers`."""
    lf = get(file_id, root)
    if lf.layer != "rules":
        raise LayerError(f"{file_id!r} is a {lf.layer} file, not rules")
    return lf.body


def skill(file_id: str, root: Path | None = None) -> str:
    """The body of a Skills-layer file — the `role` slot of `PromptLayers`."""
    lf = get(file_id, root)
    if lf.layer != "skill":
        raise LayerError(f"{file_id!r} is a {lf.layer} file, not a skill")
    return lf.body


def playbook(file_id: str, root: Path | None = None) -> dict[str, Any]:
    """The parsed body of a Playbook-layer file, with the file's identity
    attached so a change record can name the exact version it ran."""
    lf = get(file_id, root)
    if lf.layer != "playbook":
        raise LayerError(f"{file_id!r} is a {lf.layer} file, not a playbook")
    try:
        body = json.loads(lf.body)
    except json.JSONDecodeError as exc:
        raise LayerError(f"playbook {file_id!r}: body is not valid JSON: {exc}") from exc
    steps = body.get("steps")
    if not isinstance(steps, list) or not steps:
        raise LayerError(f"playbook {file_id!r}: needs a non-empty 'steps' list")
    for step in steps:
        for key in ("step_id", "kind", "action", "label"):
            if not step.get(key):
                raise LayerError(f"playbook {file_id!r}: step missing {key!r}: {step}")
        if step["kind"] not in ("mechanical", "gate"):
            raise LayerError(f"playbook {file_id!r}: step kind must be mechanical or gate")
        if step["kind"] == "gate" and not step.get("role"):
            raise LayerError(f"playbook {file_id!r}: gate step {step['step_id']} names no role")
    v = version_of(file_id, root)
    return {**body, "playbook_id": lf.id, "title": lf.title, "summary": lf.summary,
            "version": v["version"], "recorded": v["recorded"], "sha256": lf.sha256,
            "short": lf.short}


def task(file_id: str, root: Path | None = None) -> str:
    """The raw body of a Task-layer file, placeholders intact."""
    lf = get(file_id, root)
    if lf.layer != "task":
        raise LayerError(f"{file_id!r} is a {lf.layer} file, not a task")
    return lf.body


def placeholders_of(body: str) -> list[str]:
    """Placeholder names in first-appearance order, de-duplicated."""
    seen: list[str] = []
    for name in _PLACEHOLDER_RE.findall(body):
        if name not in seen:
            seen.append(name)
    return seen


def render(file_id: str, root: Path | None = None, /, **values: Any) -> str:
    """Substitute `{{name}}` placeholders verbatim — `str(value)`, no escaping,
    no formatting — so the rendered text is exactly what an f-string built
    before the template existed, byte for byte. Every placeholder in the body
    must be declared *and* supplied; an unsupplied one is a workflow bug, an
    undeclared one is refused at load. Values the template does not use are
    ignored, so a template may drop a variable without touching the caller.
    Works for every variable layer: tasks, standards and templates."""
    lf = get(file_id, root)
    if lf.layer not in VARIABLE_LAYERS:
        raise LayerError(f"{file_id!r} is a {lf.layer} file, not a renderable layer")
    missing = [n for n in placeholders_of(lf.body) if n not in values]
    if missing:
        raise LayerError(f"{lf.layer} {file_id!r}: no value supplied for {missing}")
    # One pass over the template, never over substituted text: a value that
    # happens to contain `{{name}}` is data and stays exactly as supplied —
    # the same guarantee an f-string gave.
    return _PLACEHOLDER_RE.sub(lambda m: str(values[m.group(1)]), lf.body)


def render_task(file_id: str, root: Path | None = None, /, **values: Any) -> str:
    """`render()` for a task file — the original entry point, kept so every
    workflow call site reads the same."""
    lf = get(file_id, root)
    if lf.layer != "task":
        raise LayerError(f"{file_id!r} is a {lf.layer} file, not a task")
    return render(file_id, root, **values)


def standard(file_id: str, root: Path | None = None, /, **values: Any) -> str:
    """A rendered Standards-layer file (developer-facing text)."""
    lf = get(file_id, root)
    if lf.layer != "standard":
        raise LayerError(f"{file_id!r} is a {lf.layer} file, not a standard")
    return render(file_id, root, **values)


def template(file_id: str, root: Path | None = None, /, **values: Any) -> str:
    """A rendered Templates-layer file (mechanically generated output)."""
    lf = get(file_id, root)
    if lf.layer != "template":
        raise LayerError(f"{file_id!r} is a {lf.layer} file, not a template")
    return render(file_id, root, **values)


def structured(file_id: str, root: Path | None = None) -> dict[str, Any]:
    """The parsed JSON body of a governance, model or identity file."""
    lf = get(file_id, root)
    if lf.layer not in JSON_LAYERS:
        raise LayerError(f"{file_id!r} is a {lf.layer} file, not a structured layer")
    return json.loads(lf.body)


# --- version ledger ---------------------------------------------------------


def history(root: Path | None = None) -> list[dict[str, Any]]:
    target = _root(root) / HISTORY_FILE
    if not target.exists():
        return []
    out = []
    for line in target.read_bytes().decode("utf-8").replace("\r\n", "\n").splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out


def latest_versions(root: Path | None = None) -> dict[str, dict[str, Any]]:
    """Last recorded ledger line per id (append order wins, not timestamps)."""
    latest: dict[str, dict[str, Any]] = {}
    for rec in history(root):
        latest[rec["id"]] = rec
    return latest


def version_of(file_id: str, root: Path | None = None) -> dict[str, Any]:
    """{"version": n, "recorded": bool, "sha256": current} — `recorded` is
    False when the file has changed since its last ledger line (or was never
    recorded); `version` is then the *last recorded* number, not a guess."""
    lf = get(file_id, root)
    rec = latest_versions(_ledger_root(file_id, root)).get(file_id)
    return {
        "version": int(rec["version"]) if rec else 0,
        "recorded": bool(rec) and rec["sha256"] == lf.sha256,
        "sha256": lf.sha256,
    }


def skill_ref(file_id: str, root: Path | None = None) -> str:
    """The string the activity ledger carries for a call: `id@vN` when the
    file matches its recorded version, otherwise `id@<sha8>(unrecorded)` —
    the ledger never claims a version number the ledger does not hold."""
    v = version_of(file_id, root)
    if v["recorded"]:
        return f"{file_id}@v{v['version']}"
    return f"{file_id}@{v['sha256'][:8]}(unrecorded)"


def pin_ref(file_id: str, root: Path | None = None) -> str:
    """What a generated artifact pins: `id@vN+<sha8>`. The hash disambiguates
    a profile override (whose ledger restarts at v1) from the default file
    it replaced, so a pin compares by content, never by number alone."""
    return f"{skill_ref(file_id, root)}+{get(file_id, root).short}"


def unrecorded(root: Path | None = None) -> list[LayerFile]:
    """Files whose current content is not the last recorded version. In a
    profile only the overrides count — the default files it shows through
    are the default set's business."""
    latest = latest_versions(root)
    overlay = is_overlay(root)
    return [
        lf for lf in load_all(root).values()
        if (not overlay or lf.source != "default")
        and (lf.id not in latest or latest[lf.id]["sha256"] != lf.sha256)
    ]


def _snapshot_path(base: Path, file_id: str, version: int) -> Path:
    return base / VERSIONS_DIR / file_id / f"v{version}.md"


def _write_snapshot(base: Path, file_id: str, version: int, body: str) -> None:
    target = _snapshot_path(base, file_id, version)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes((body + "\n").encode("utf-8"))


def record_versions(
    note: str, author: str = "", root: Path | None = None, *,
    now: str | None = None, only: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    """Append one ledger line per changed file; return the lines appended.
    Idempotent: a second call with nothing changed appends nothing. Each
    recorded version's body is snapshotted under `versions/<id>/v<N>.md` so
    it can be diffed against and rolled back to later. `only` restricts the
    record to the named ids (an editor records the one file it changed)."""
    if not note.strip():
        raise LayerError("a version record needs a note saying what changed and why")
    base = _root(root)
    latest = latest_versions(root)
    stamp = now or datetime.now(UTC).isoformat(timespec="seconds")
    wanted = set(only) if only is not None else None
    appended: list[dict[str, Any]] = []
    default_latest = latest_versions(LAYERS_ROOT) if is_overlay(root) else {}
    for lf in unrecorded(root):
        if wanted is not None and lf.id not in wanted:
            continue
        prev = latest.get(lf.id)
        rec = {
            "recorded_at": stamp,
            "id": lf.id,
            "layer": lf.layer,
            "path": lf.path,
            "version": (int(prev["version"]) + 1) if prev else 1,
            "sha256": lf.sha256,
            "previous_sha256": prev["sha256"] if prev else None,
            "author": author,
            "note": note.strip(),
        }
        if not prev and lf.id in default_latest:
            # First override of a default file: name what it diverged from.
            base_rec = default_latest[lf.id]
            rec["previous_sha256"] = base_rec["sha256"]
            rec["overrides"] = f"default@v{base_rec['version']}"
        appended.append(rec)
    if appended:
        with (base / HISTORY_FILE).open("a", encoding="utf-8", newline="\n") as fh:
            for rec in appended:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        files = load_all(root)
        for rec in appended:
            _write_snapshot(base, rec["id"], int(rec["version"]), files[rec["id"]].body)
    return appended


# --- editing: write, create, roll back — always through the ledger -----------


def _frontmatter_raw(path: Path) -> str:
    """The file's frontmatter block, verbatim (LF), through the closing `---`."""
    raw = path.read_bytes().decode("utf-8").replace("\r\n", "\n")
    end = raw.find("\n---\n", 4)
    return raw[: end + len("\n---\n")]


def _normalise_body(body: str) -> str:
    body = body.replace("\r\n", "\n").rstrip("\n")
    if not body.strip():
        raise LayerError("a layer body cannot be empty")
    return body


def versions_of(file_id: str, root: Path | None = None) -> list[dict[str, Any]]:
    """Every ledger line for one id, oldest first, each flagged with whether
    its body snapshot is available (`has_body`)."""
    base = _ledger_root(file_id, root)
    out = []
    for rec in history(base):
        if rec["id"] == file_id:
            snap = _snapshot_path(base, file_id, int(rec["version"]))
            out.append({**rec, "has_body": snap.exists()})
    return out


def version_body(file_id: str, version: int, root: Path | None = None) -> str | None:
    """The body recorded as version N. Falls back to the current file when it
    *is* the recorded version and no snapshot was written (ledger lines that
    pre-date snapshots); `None` when the body is genuinely unavailable."""
    base = _ledger_root(file_id, root)
    snap = _snapshot_path(base, file_id, version)
    if snap.exists():
        return snap.read_bytes().decode("utf-8").replace("\r\n", "\n").rstrip("\n")
    v = version_of(file_id, root)
    if v["recorded"] and v["version"] == version:
        return get(file_id, root).body
    return None


def write_body(
    file_id: str, body: str, *, note: str, author: str = "",
    root: Path | None = None, now: str | None = None,
) -> dict[str, Any] | None:
    """Replace a file's body and record the new version in one step. Returns
    the ledger line, or `None` when the body is unchanged. The frontmatter is
    preserved byte for byte; a task body is validated against its declared
    variables before anything is written. The previous version's body is
    snapshotted first if it never was, so a rollback target always exists."""
    base = _root(root)
    lf = get(file_id, root)
    body = _normalise_body(body)
    if body == lf.body:
        return None
    _check_body(lf.layer, file_id, body, lf.variables, lf.locked)
    if not note.strip():
        raise LayerError("a version record needs a note saying what changed and why")
    copy_on_write = is_overlay(root) and lf.source == "default"
    if copy_on_write:
        # The default file shows through; the edit creates the override with
        # the default's frontmatter byte for byte, versioned from v1 in the
        # profile's own ledger (the line names what it diverged from).
        source_path = LAYERS_ROOT / lf.path
        target = base / lf.path
        target.parent.mkdir(parents=True, exist_ok=True)
    else:
        prev = version_of(file_id, root)
        owner = _ledger_root(file_id, root)
        if prev["recorded"] and not _snapshot_path(owner, file_id, prev["version"]).exists():
            _write_snapshot(owner, file_id, prev["version"], lf.body)
        source_path = target = base / lf.path
    front = _frontmatter_raw(source_path)
    target.write_bytes((front + body + "\n").encode("utf-8"))
    appended = record_versions(note, author, root, now=now, only=(file_id,))
    return appended[0] if appended else None


def _check_body(layer: str, file_id: str, body: str, variables: Iterable[str],
                locked: Iterable[str]) -> None:
    """The per-layer body contract, shared by write and create."""
    if layer in VARIABLE_LAYERS:
        undeclared = sorted(set(_PLACEHOLDER_RE.findall(body)) - set(variables))
        if undeclared:
            raise LayerError(
                f"{layer} {file_id!r}: placeholders {undeclared} are not declared in "
                f"`variables:` ({', '.join(variables) or 'none'})"
            )
    if layer == "playbook" or layer in JSON_LAYERS:
        try:
            json.loads(body)
        except json.JSONDecodeError as exc:
            raise LayerError(f"{layer} {file_id!r}: body is not valid JSON: {exc}") from exc
    missing = [t for t in locked if t not in body]
    if missing:
        raise LayerError(
            f"{layer} {file_id!r}: locked tokens {missing} must stay in the body — "
            "the Control Centre depends on them"
        )


def revert_override(
    file_id: str, *, note: str, author: str = "",
    root: Path | None = None, now: str | None = None,
) -> dict[str, Any]:
    """Delete a profile's override so the default file shows through again.
    Recorded in the profile's ledger as a `reverted_to` line, so the history
    says when the override existed and what it was; the override's snapshots
    stay for the record."""
    if not is_overlay(root):
        raise LayerError("only a delivery profile can revert an override")
    base = _root(root)
    lf = get(file_id, root)
    if lf.source == "default":
        raise LayerError(f"{file_id!r} is not overridden in this profile")
    if file_id not in load_all(LAYERS_ROOT):
        raise LayerError(
            f"{file_id!r} exists only in this profile — delete is not a revert"
        )
    if not note.strip():
        raise LayerError("a version record needs a note saying what changed and why")
    prev = latest_versions(root).get(file_id)
    if prev and not _snapshot_path(base, file_id, int(prev["version"])).exists():
        _write_snapshot(base, file_id, int(prev["version"]), lf.body)
    (base / lf.path).unlink()
    default = get(file_id, LAYERS_ROOT)
    default_rec = latest_versions(LAYERS_ROOT).get(file_id)
    rec = {
        "recorded_at": now or datetime.now(UTC).isoformat(timespec="seconds"),
        "id": file_id,
        "layer": lf.layer,
        "path": lf.path,
        "version": (int(prev["version"]) + 1) if prev else 1,
        "sha256": default.sha256,
        "previous_sha256": lf.sha256,
        "author": author,
        "note": note.strip(),
        "reverted_to": f"default@v{default_rec['version']}" if default_rec else "default",
    }
    with (base / HISTORY_FILE).open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def create_file(
    layer: str, file_id: str, *, title: str, stage: str, summary: str, body: str,
    variables: Iterable[str] = (), locked: Iterable[str] = (), note: str,
    author: str = "", root: Path | None = None, now: str | None = None,
) -> dict[str, Any]:
    """Add a new layer file and record it as v1."""
    if layer not in _SUBDIR:
        raise LayerError(f"layer must be one of {', '.join(sorted(_SUBDIR))}, got {layer!r}")
    if not _ID_RE.match(file_id):
        raise LayerError(f"id {file_id!r} must be lowercase kebab-case (a-z, 0-9, -)")
    base = _root(root)
    if file_id in load_all(root):
        raise LayerError(f"layer id {file_id!r} already exists")
    if not (title.strip() and stage.strip() and summary.strip()):
        raise LayerError("title, stage and summary are all required")
    body = _normalise_body(body)
    variables = tuple(v.strip() for v in variables if v.strip())
    locked = tuple(t.strip() for t in locked if t.strip())
    if any("," in t for t in locked):
        raise LayerError("a locked token cannot contain a comma")
    _check_body(layer, file_id, body, variables, locked)
    meta = [f"id: {file_id}", f"layer: {layer}", f"title: {title.strip()}",
            f"stage: {stage.strip()}", f"summary: {summary.strip()}"]
    if variables:
        meta.append("variables: " + ", ".join(variables))
    if locked:
        meta.append("locked: " + ", ".join(locked))
    text = "---\n" + "\n".join(meta) + "\n---\n" + body + "\n"
    target = base / _SUBDIR[layer] / f"{file_id}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(text.encode("utf-8"))
    appended = record_versions(note, author, root, now=now, only=(file_id,))
    return appended[0]


def rollback(
    file_id: str, to_version: int, *, note: str, author: str = "",
    root: Path | None = None, now: str | None = None,
) -> dict[str, Any] | None:
    """Restore a recorded version's body as a *new* version — the ledger only
    ever grows, so a rollback is itself an amendment."""
    body = version_body(file_id, to_version, root)
    if body is None:
        raise LayerError(f"{file_id}: version {to_version} has no recorded body")
    return write_body(file_id, body, note=note, author=author, root=root, now=now)


def diff(file_id: str, from_version: int, to_version: int, root: Path | None = None) -> str:
    """Unified diff between two recorded versions' bodies."""
    a = version_body(file_id, from_version, root)
    b = version_body(file_id, to_version, root)
    if a is None or b is None:
        missing = from_version if a is None else to_version
        raise LayerError(f"{file_id}: version {missing} has no recorded body")
    return "".join(difflib.unified_diff(
        a.splitlines(keepends=True), b.splitlines(keepends=True),
        fromfile=f"{file_id}@v{from_version}", tofile=f"{file_id}@v{to_version}",
    ))


# --- the workflow and orchestrator layers, described ------------------------

# Each workflow names the rules file and skill file(s) its model calls
# assemble, where it enters the engine, the gate that consumes its output,
# and what each run mode actually does — the honest mode behaviour is part
# of the description because the layer diagram must not imply a model call
# in a mode that makes none.
WORKFLOWS: tuple[dict[str, Any], ...] = (
    {
        "id": "intake-analysis", "label": "Intake analysis", "stage": "intake",
        "gate": "G0", "rules": "delivery-assistant", "skills": ["intake-analysis"],
        "entry": "Engine.intake_analyse → live_intake.run_analysis",
        "tasks": ["intake-analysis-task"],
        "simulation": "seeded analysis, badged SIMULATED — no model call",
        "live": "one grounded model call; its clarification_questions open the popup",
    },
    {
        "id": "clarification", "label": "Clarification round", "stage": "intake",
        "gate": "G0", "rules": "delivery-assistant", "skills": ["clarification"],
        "entry": "Engine.intake_clarify → live_intake.run_clarification",
        "tasks": ["clarification-task"],
        "simulation": "the analysis's own questions are queued — no model call",
        "live": "one model call per round, capped at MAX_CLARIFICATION_ROUNDS",
    },
    {
        "id": "requirement-routing", "label": "Requirement routing", "stage": "intake",
        "gate": "G0", "rules": "delivery-assistant", "skills": ["requirement-routing"],
        "entry": "Engine.intake_route → live_intake.route_requirement",
        "tasks": ["requirement-routing-task"],
        "simulation": "seeded routable verdict — no model call",
        "live": "one model call; zero connected repos short-circuits with no call",
    },
    {
        "id": "requirement-extraction", "label": "Requirement extraction", "stage": "intake",
        "gate": "G0", "rules": "delivery-assistant", "skills": ["requirement-extraction"],
        "entry": "Engine.intake_extract → live_intake.run_extraction",
        "tasks": ["requirement-extraction-task"],
        "simulation": "deterministic parser, badged RULE_BASED — no model call",
        "live": "one model call over the uploaded or pasted source",
    },
    {
        "id": "new-application-setup", "label": "New-application setup", "stage": "intake",
        "gate": "G0", "rules": "delivery-assistant", "skills": ["new-application-setup"],
        "entry": "Engine.intake_new_app_setup → live_intake.run_new_app_setup",
        "tasks": ["new-application-setup-task"],
        "simulation": "not offered — simulation runs are pre-grounded",
        "live": "capped conversational rounds, forced to finalise on the last",
    },
    {
        "id": "new-application-scaffold", "label": "New-application scaffold", "stage": "intake",
        "gate": "G0", "rules": "delivery-assistant", "skills": ["new-application-scaffold"],
        "entry": "Engine.intake_generate_scaffold → scaffold.generate_scaffold",
        "tasks": ["new-application-scaffold-task"],
        "simulation": "not offered — simulation runs are pre-grounded",
        "live": "one model call producing architecture.md + README.md for review",
    },
    {
        "id": "epic-decomposition", "label": "Epic decomposition", "stage": "planning",
        "gate": "G1", "rules": "delivery-assistant", "skills": ["epic-decomposition"],
        "entry": "Engine.planning_generate → live_intake.run_plan",
        "tasks": ["epic-decomposition-task", "epic-decomposition-correction-task"],
        "simulation": "seeded MapleSure plan, badged SIMULATED — no model call",
        "live": "one model call plus one bounded corrective retry naming every defect",
    },
    {
        "id": "architecture-refine", "label": "Architecture refine", "stage": "build_review",
        "gate": "architecture acceptance", "rules": "delivery-assistant",
        "skills": ["architecture-refine"],
        "entry": "Engine.architecture_revise → refine.refine_architecture_proposal",
        "tasks": ["architecture-refine-task"],
        "simulation": "deterministic normaliser, badged RULE_BASED — no model call",
        "live": "one model call; the lead's proposal is recorded verbatim as HUMAN first",
    },
    {
        "id": "test-plan-refine", "label": "Test-plan refine", "stage": "build_review",
        "gate": "QA test-plan approval", "rules": "delivery-assistant",
        "skills": ["test-plan-refine"],
        "entry": "Engine.test_plan_amend → refine.refine_test_amendment",
        "tasks": ["test-plan-refine-task"],
        "simulation": "deterministic normaliser, badged RULE_BASED — no model call",
        "live": "one model call; cases append under governed test_qa_* names",
    },
    {
        "id": "development-lane", "label": "Develop → test → review lane",
        "stage": "build_review", "gate": "G2", "rules": "downstream-lane",
        "skills": ["developer", "tester", "reviewer"],
        "entry": "Engine.task_develop → factory.live → downstream.run_lane",
        "tasks": ["developer-task", "tester-task", "reviewer-task",
                  "developer-revision-task", "tester-revision-task"],
        "simulation": "simulated evidence per story, badged SIMULATED — no model call",
        "live": "three real calls per task (second model for the reviewer when "
                "REVIEW_LLM_* is set), real pytest, bounded revision loop",
    },
    {
        "id": "staged-pipeline", "label": "Staged pipeline (assess → design → stories)",
        "stage": "assess/design/stories", "gate": "human review gate",
        "rules": "staged-pipeline", "skills": [],
        "entry": "pipeline.py → generate.py",
        "tasks": ["staged-assessment-task", "staged-design-task", "staged-stories-task"],
        "simulation": "staged artifacts, badged STAGED — no model call",
        "live": "the original three calls; role text lives in each task, "
                "pinned by committed recordings",
    },
    {
        "id": "prompt-improvement", "label": "Prompt improvement (correction learning)",
        "stage": "admin", "gate": "operator accepts the proposed version",
        "rules": "delivery-assistant", "skills": ["prompt-improve"],
        "entry": "admin app → product/improve.py",
        "tasks": ["prompt-improve-task"],
        "simulation": "not offered — a proposal is a real model call or nothing",
        "live": "one model call per proposal over the file body and the human "
                "corrections; the draft is applied only when an operator accepts it",
    },
)

ORCHESTRATOR: tuple[dict[str, str], ...] = (
    {
        "surface": "app", "label": "Control Centre",
        "where": "apps/control/server.py + apps/control/web/",
        "role": "where a human decides or reads: intake, design, gates, "
                "approvals, evidence — rendered from one state payload",
    },
    {
        "surface": "cli", "label": "python -m s7_delivery",
        "where": "s7_delivery/cli.py",
        "role": "where an agent executes: drives sim/demo tasks through the "
                "lane and renders the ledger as assertable text",
    },
)

WORKFLOW_ENGINE: tuple[dict[str, str], ...] = (
    {"where": "s7_delivery/factory/engine.py",
     "role": "every action: role check → gate check → write → provenance "
             "append → activity append"},
    {"where": "s7_delivery/factory/gates.py",
     "role": "G0–G4 as explicit named conditions, never a score"},
    {"where": "s7_delivery/factory/build_phases.py",
     "role": "the Build & Review phase machine; out-of-order actions 409"},
    {"where": "s7_delivery/factory/roles.py",
     "role": "role → permitted actions; the separation rules the gates enforce"},
)


# Who reads a non-prompt layer file, so the admin surface can say what an
# edit touches. Prompt files are described by their workflows instead.
CONSUMERS: dict[str, tuple[str, ...]] = {
    "when-to-read-what": (
        "delivery_packs.render_when_to_read_what_md → .s7/shared/when-to-read-what.md"
        " (the routing index every other standard is reached through)",
    ),
    "git-workflow": ("delivery_packs.render_git_workflow_md → .s7/shared/git-workflow.md",),
    "verification": (
        "delivery_packs.render_situational_standards → .s7/shared/verification.md",
    ),
    "debugging": (
        "delivery_packs.render_situational_standards → .s7/shared/debugging.md",
    ),
    "reviewing-feedback": (
        "delivery_packs.render_situational_standards → .s7/shared/reviewing-feedback.md",
    ),
    "code-conventions": (
        "delivery_packs.render_code_conventions_md → .s7/shared/code-conventions.md",
    ),
    "engineering-rules": ("architecture.engineering_rules_md → .s7/shared/engineering-rules.md",),
    "ui-guidelines": ("delivery_packs.render_ui_guidelines_md → .s7/shared/ui-guidelines.md",),
    "db-conventions": ("delivery_packs.render_team_pack → .s7/shared/db-conventions.md",),
    "ui-starter-css": ("delivery_packs.render_team_pack → .s7/shared/ui/app.css",),
    "ui-layout-thymeleaf": ("delivery_packs.render_team_pack → .s7/shared/ui/layout.html (maven)",),
    "ui-layout-jinja": ("delivery_packs.render_team_pack → .s7/shared/ui/layout.html (pytest)",),
    "ci-maven": ("ci_bootstrap.bootstrap → .github/workflows/s7-ci.yml (maven)",),
    "ci-pytest": ("ci_bootstrap.bootstrap → .github/workflows/s7-ci.yml (pytest)",),
    "scaffold-maven-pom": ("ci_bootstrap.bootstrap(scaffold=True) → pom.xml (new repos only)",),
    "scaffold-maven-smoke-test": (
        "ci_bootstrap.bootstrap(scaffold=True) → src/test/java/smoke/BuildSmokeTest.java",
    ),
    "scaffold-pytest-requirements": (
        "ci_bootstrap.bootstrap(scaffold=True) → requirements.txt (new repos only)",
    ),
    "scaffold-pytest-config": (
        "ci_bootstrap.bootstrap(scaffold=True) → pyproject.toml (new repos only)",
    ),
    "scaffold-pytest-smoke-test": (
        "ci_bootstrap.bootstrap(scaffold=True) → tests/test_build_smoke.py",
    ),
    "release-doc-theme": ("release_doc.render_html → release document HTML",),
    "roles": ("roles_config.effective_permissions → roles.require on every engine call",),
    "llm-settings": ("llm_settings.for_stage → every model call of a run",),
    "pricing": ("kpi.cost_per_release (reports None until token usage is measured)",),
    "identity": ("ui-guidelines tokens, ui-starter-css, release-doc-theme",),
    "github": (
        "integrations.check_repo_url → Engine.intake_connect_repo (host, owner allowlist)",
        "integrations.require_repo_creation → Engine.intake_create_new_app_repo",
        "integrations.refused_branch_names → publication.check_branch",
        "admin Repositories page → gh auth status (login only, never a token)",
    ),
}


def describe(root: Path | None = None) -> dict[str, Any]:
    """The four layers as one JSON payload for the API, the CLI and the app.
    Rule-based: derived from the files and the registry above, never an AI
    claim about the system."""
    files = load_all(root)
    latest = latest_versions(root)
    by_skill_workflows: dict[str, list[str]] = {}
    by_rules_workflows: dict[str, list[str]] = {}
    for wf in WORKFLOWS:
        by_rules_workflows.setdefault(wf["rules"], []).append(wf["id"])
        for sid in wf["skills"]:
            by_skill_workflows.setdefault(sid, []).append(wf["id"])

    by_task_workflows: dict[str, list[str]] = {}
    for wf in WORKFLOWS:
        for tid in wf.get("tasks", []):
            by_task_workflows.setdefault(tid, []).append(wf["id"])
    base = _root(root)
    is_default = base.resolve() == LAYERS_ROOT.resolve()
    overlay = is_overlay(root)
    default_latest = latest_versions(LAYERS_ROOT) if overlay else latest

    def row(lf: LayerFile) -> dict[str, Any]:
        rec = (latest if (not overlay or lf.source != "default") else default_latest).get(lf.id)
        used_by = {"rules": by_rules_workflows, "skill": by_skill_workflows,
                   "task": by_task_workflows}.get(lf.layer, {})
        return {
            "id": lf.id, "layer": lf.layer, "title": lf.title, "stage": lf.stage,
            "summary": lf.summary,
            "path": (f"s7_delivery/layers/{lf.path}" if is_default else lf.path),
            "sha256": lf.sha256, "short": lf.short, "body": lf.body,
            "variables": list(lf.variables),
            "locked": list(lf.locked),
            "source": lf.source,
            "enters_model_call": lf.layer in PROMPT_LAYERS,
            "consumers": list(CONSUMERS.get(lf.id, ())),
            "version": int(rec["version"]) if rec else 0,
            "recorded": bool(rec) and rec["sha256"] == lf.sha256,
            "recorded_at": rec["recorded_at"] if rec else None,
            "workflows": used_by.get(lf.id, []),
        }

    rules_rows = [row(lf) for lf in files.values() if lf.layer == "rules"]
    skill_rows = [row(lf) for lf in files.values() if lf.layer == "skill"]
    task_rows = [row(lf) for lf in files.values() if lf.layer == "task"]
    playbook_rows = []
    for lf in files.values():
        if lf.layer != "playbook":
            continue
        book = playbook(lf.id, root)
        playbook_rows.append({
            **row(lf), "body": None,
            "change_type": book["change_type"], "trigger": book.get("trigger", ""),
            "steps": book["steps"],
        })
    other_rows = {
        kind: [row(lf) for lf in files.values() if lf.layer == kind]
        for kind in ("standard", "template", "governance", "model", "identity", "integration")
    }
    return {
        "provenance": "rule_based",
        "overlay": is_profile(root),
        "overridden": overridden(root) if overlay else [],
        "layer_groups": [
            {"id": gid, "label": label, "layers": list(kinds)}
            for gid, label, kinds in LAYER_GROUPS
        ],
        "standards": other_rows["standard"],
        "templates": other_rows["template"],
        "governance": other_rows["governance"],
        "models": other_rows["model"],
        "identity": other_rows["identity"],
        "integrations": other_rows["integration"],
        "prompt_mapping": {
            "rules": "Rules layer — the `rules` slot, identical for every call of a lane",
            "role": "Skills layer — the `role` slot, identical for every call of a stage",
            "memory": "supplied per run by the workflow",
            "ref": "supplied per call by the workflow (connected repos' context packs)",
            "task": "supplied per call by the workflow — the only slot that changes",
        },
        "root": str(base),
        "default_set": is_default,
        "rules": rules_rows,
        "skills": skill_rows,
        "tasks": task_rows,
        "playbooks": playbook_rows,
        "workflows": [dict(wf) for wf in WORKFLOWS],
        "workflow_engine": [dict(w) for w in WORKFLOW_ENGINE],
        "orchestrator": [dict(o) for o in ORCHESTRATOR],
        "history": history(root),
        "unrecorded": [lf.id for lf in unrecorded(root)],
    }

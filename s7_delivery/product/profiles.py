"""Delivery profiles — one named, versioned bundle of everything that
configures S7 for a client or project (design: `docs/design-history/plans/
2026-09-07-delivery-profiles.md`).

A profile is a directory under `config/profiles/<name>/` holding
`profile.json` plus the layer files it **overrides**; every file it does not
carry falls through to the committed default set in `s7_delivery/layers/`
(`factory/layers.py` resolves the overlay). The six layers — prompts,
standards, templates, governance, models, identity — share one file shape,
one ledger (`history.jsonl` in the profile), one editor and one audit trail.

Legacy full-copy prompt sets (`config/prompt-sets/<name>/`, created before
profiles existed) still resolve: `root_of()` looks for a profile first and
falls back to the set, so a run created against a set keeps working. New
configuration is always a profile.

Disciplines:

- **Overlay, not copy.** `create()` writes only `profile.json`; the first
  edit of a default file creates the override (copy-on-write in
  `layers.write_body`), and `revert()` removes it again.
- **Every change is a version, every admin action an audit line** — the
  editing goes through `factory/layers.py` and the audit through
  `product/config.py`, never around either.
- **Impact is stated, never guessed.** `impact()` reports what an edit
  touches from the files and the run ledgers: recordings pinned to the
  current bytes (default set only), runs whose generated artifacts pinned an
  older version, and the consumers that read the file.
- **A profile travels as a folder.** `export_zip()` / `import_zip()` move
  exactly the profile directory; an import is validated by loading every
  file through the layer parser before it is accepted.
"""

from __future__ import annotations

import io
import json
import re
import shutil
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from s7_delivery.factory import layers
from s7_delivery.product import prompt_sets
from s7_delivery.product.config import audit, config_root, now_iso

DEFAULT = "default"
META_FILE = layers.PROFILE_META
_NAME_RE = re.compile(r"^[a-z][a-z0-9-]{1,39}$")
# What an exported profile may contain — anything else in a zip is refused.
_ALLOWED_TOP = {META_FILE, layers.HISTORY_FILE, layers.VERSIONS_DIR, *layers._SUBDIR.values()}


class ProfileError(prompt_sets.PromptSetError):
    """Unknown profile, invalid name, or a refused operation. A subclass of
    the legacy `PromptSetError` so every caller that handled an unknown
    prompt set handles an unknown profile the same way."""


def profiles_dir() -> Path:
    return config_root() / "profiles"


def _dir(name: str) -> Path:
    return profiles_dir() / name


def is_profile(name: str) -> bool:
    return (_dir(name) / META_FILE).is_file()


def kind_of(name: str) -> str:
    """`default`, `profile` (overlay) or `legacy-set` (full copy)."""
    if name == DEFAULT:
        return "default"
    if is_profile(name):
        return "profile"
    if prompt_sets.exists(name):
        return "legacy-set"
    raise ProfileError(f"unknown prompt set or delivery profile {name!r}")


def exists(name: str) -> bool:
    try:
        kind_of(name)
    except ProfileError:
        return False
    return True


def root_of(name: str) -> Path:
    """The layer root a run resolves against — the default set, a profile
    directory (overlay) or a legacy full-copy set."""
    kind = kind_of(name)
    if kind == "default":
        return layers.LAYERS_ROOT
    if kind == "profile":
        return _dir(name)
    return prompt_sets.root_of(name)


def meta(name: str) -> dict[str, Any]:
    kind = kind_of(name)
    if kind == "default":
        return {
            "name": DEFAULT, "kind": kind,
            "description": "The committed default set — recording-pinned; "
                           "every profile falls through to it.",
            "base": None, "created_at": None, "created_by": "",
        }
    if kind == "profile":
        data = json.loads((_dir(name) / META_FILE).read_text(encoding="utf-8"))
        return {**data, "kind": kind}
    legacy = prompt_sets.root_of(name) / prompt_sets.META_FILE
    data = json.loads(legacy.read_text(encoding="utf-8"))
    return {**data, "kind": kind, "base": data.get("cloned_from", DEFAULT)}


@contextmanager
def use(name: str) -> Iterator[Path]:
    """Resolve every layer accessor against the profile for the block."""
    root = root_of(name)
    with layers.use(None if root == layers.LAYERS_ROOT else root) as active:
        yield active


def fingerprint(name: str) -> str:
    """One hash over the resolved file set (id → sha256) — the profile's
    effective version, which a run records at creation so a later edit is
    visible as drift rather than silently changing what the run resolves."""
    import hashlib

    files = layers.load_all(root_of(name))
    payload = json.dumps({fid: lf.sha256 for fid, lf in sorted(files.items())}, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# --- listing and describing -------------------------------------------------


def _summary(name: str) -> dict[str, Any]:
    root = root_of(name)
    files = layers.load_all(root)
    overlay = layers.is_profile(root)
    counts = {gid: 0 for gid, _, _ in layers.LAYER_GROUPS}
    for lf in files.values():
        for gid, _, kinds in layers.LAYER_GROUPS:
            if lf.layer in kinds:
                counts[gid] += 1
    return {
        **meta(name),
        "root": str(root),
        "is_default": name == DEFAULT,
        "overlay": overlay,
        "files": len(files),
        "counts": counts,
        "overridden": layers.overridden(root) if overlay else [],
        "unrecorded": [lf.id for lf in layers.unrecorded(root)],
        "versions": len(layers.history(root)),
        "fingerprint": fingerprint(name)[:12],
    }


def list_profiles() -> list[dict[str, Any]]:
    """Default first, then profiles, then any legacy full-copy sets."""
    rows = [_summary(DEFAULT)]
    base = profiles_dir()
    if base.is_dir():
        for child in sorted(base.iterdir()):
            if child.is_dir() and (child / META_FILE).is_file():
                rows.append(_summary(child.name))
    for s in prompt_sets.list_sets():
        if s["name"] != DEFAULT and not is_profile(s["name"]):
            rows.append(_summary(s["name"]))
    return rows


def describe(name: str) -> dict[str, Any]:
    """The profile's resolved view: every layer file with its source
    (default / override / set), version and consumers, grouped for the
    editor. Bodies are included — the editor needs them."""
    root = root_of(name)
    desc = layers.describe(root)
    by_kind: dict[str, list[dict]] = {
        "rules": desc["rules"], "skill": desc["skills"], "task": desc["tasks"],
        "playbook": desc["playbooks"], "standard": desc["standards"],
        "template": desc["templates"], "governance": desc["governance"],
        "model": desc["models"], "identity": desc["identity"],
        "integration": desc["integrations"],
    }
    groups = []
    for gid, label, kinds in layers.LAYER_GROUPS:
        rows = [r for k in kinds for r in by_kind[k]]
        groups.append({
            "id": gid, "label": label, "layers": list(kinds), "files": rows,
            "overridden": sum(1 for r in rows if r["source"] == "override"),
        })
    return {
        **_summary(name),
        "groups": groups,
        "workflows": desc["workflows"],
        "history": desc["history"],
        "provenance": "rule_based",
    }


# --- lifecycle ---------------------------------------------------------------


def create(name: str, *, description: str = "", author: str = "") -> dict[str, Any]:
    """A new overlay profile: `profile.json` only. Nothing is copied — the
    default shows through until a file is edited."""
    if not _NAME_RE.match(name):
        raise ProfileError(
            f"profile name {name!r} must be lowercase kebab-case, 2–40 characters"
        )
    if exists(name):
        raise ProfileError(f"a profile or prompt set named {name!r} already exists")
    target = _dir(name)
    target.mkdir(parents=True, exist_ok=False)
    data = {
        "name": name, "description": description.strip(), "base": DEFAULT,
        "created_at": now_iso(), "created_by": author,
    }
    (target / META_FILE).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    audit(author, "profile.create", name, detail=description.strip(), after=data)
    return _summary(name)


def update_description(name: str, description: str, *, author: str = "") -> dict[str, Any]:
    if kind_of(name) != "profile":
        raise ProfileError(f"{name!r} is not an editable profile")
    path = _dir(name) / META_FILE
    data = json.loads(path.read_text(encoding="utf-8"))
    before = dict(data)
    data["description"] = description.strip()
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    audit(author, "profile.describe", name, before=before, after=data)
    return _summary(name)


def delete(name: str, *, author: str = "", in_use_by: list[str] | None = None) -> None:
    """Remove a profile directory. Refused for the default and while any run
    still names it — the caller supplies those run ids."""
    kind = kind_of(name)
    if kind == "default":
        raise ProfileError("the default profile cannot be deleted")
    if in_use_by:
        raise ProfileError(
            f"profile {name!r} is used by {', '.join(in_use_by)} — reset or "
            "archive those runs first"
        )
    if kind == "legacy-set":
        prompt_sets.delete_set(name, author=author, in_use_by=in_use_by)
        return
    shutil.rmtree(_dir(name))
    audit(author, "profile.delete", name)


# --- editing (thin: the layer module owns the ledger) -------------------------


def _validate_structured(file_id: str, layer: str, body: str) -> None:
    """The structured layers carry the same contract their consumers enforce:
    a model-settings body must pass `llm_settings.validate`, a governance
    body `roles_config.validate` (never an action with no holder), identity
    and pricing their own shape. Refused before anything is written."""
    if layer not in layers.JSON_LAYERS:
        return
    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ProfileError(f"{file_id}: body is not valid JSON: {exc}") from exc
    if file_id == "llm-settings":
        from s7_delivery.product import llm_settings

        llm_settings.validate(data)
    elif file_id == "roles":
        from s7_delivery.product import roles_config

        roles_config.validate(data)
    elif file_id == "identity":
        for key in ("organisation", "short_mark", "product_line", "synthetic_domain", "palette"):
            if not data.get(key):
                raise ProfileError(f"identity: {key!r} is required")
        if not isinstance(data["palette"], dict) or not all(
            isinstance(v, str) and v.startswith("#") for v in data["palette"].values()
        ):
            raise ProfileError("identity: palette must map token names to #hex colours")
    elif file_id == "github":
        from s7_delivery.product import integrations

        integrations.validate(data)
    elif file_id == "pricing":
        rates = data.get("rates")
        if not isinstance(rates, dict):
            raise ProfileError("pricing: 'rates' must be an object keyed provider/model")
        for key, rate in rates.items():
            if not isinstance(rate, dict) or not all(
                isinstance(v, (int, float)) and v >= 0 for v in rate.values()
            ):
                raise ProfileError(f"pricing: rate {key!r} must hold non-negative numbers")


def write(name: str, file_id: str, body: str, *, note: str, author: str = "") -> dict | None:
    root = None if name == DEFAULT else root_of(name)
    lf = layers.get(file_id, root)
    _validate_structured(file_id, lf.layer, body)
    rec = layers.write_body(file_id, body, note=note, author=author, root=root)
    if rec:
        audit(author, "profile.write", f"{name}:{file_id}", detail=note,
              before=rec.get("previous_sha256"), after=rec["sha256"])
    return rec


def revert(name: str, file_id: str, *, note: str, author: str = "") -> dict[str, Any]:
    if kind_of(name) != "profile":
        raise ProfileError("only a delivery profile can revert an override")
    rec = layers.revert_override(file_id, note=note, author=author, root=root_of(name))
    audit(author, "profile.revert", f"{name}:{file_id}", detail=note,
          before=rec.get("previous_sha256"), after=rec["sha256"])
    return rec


# --- impact ---------------------------------------------------------------


def _run_pins(run_dir: Path) -> list[dict[str, Any]]:
    """Every artifact in one run that pinned a layer file version:
    `{artifact, kind, pins: {file_id: "id@vN"}}`. Reads only the run's own
    records; a run generated before pinning existed simply reports none."""
    out: list[dict[str, Any]] = []
    packs = run_dir / "build" / "packs" / "meta.json"
    if packs.is_file():
        try:
            data = json.loads(packs.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = []
        rows = data if isinstance(data, list) else data.get("packs", [])
        for pack in rows:
            if pack.get("pins"):
                out.append({
                    "artifact": pack.get("delivery_pack_id", ""),
                    "kind": "delivery_pack", "version": pack.get("version"),
                    "pins": pack["pins"],
                })
    arch = run_dir / "architecture" / "meta.json"
    if arch.is_file():
        try:
            data = json.loads(arch.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
        if data.get("pins"):
            out.append({
                "artifact": "ARCH-001", "kind": "architecture",
                "version": data.get("version"), "pins": data["pins"],
            })
    return out


def impact(name: str, file_id: str, *, runs_root: Path | None = None) -> dict[str, Any]:
    """What an edit to this file would touch — stated from the files and the
    run ledgers before anything is saved."""
    from s7_delivery.factory import store as store_module
    from s7_delivery.product import recordings, runs_admin

    root = root_of(name)
    lf = layers.get(file_id, root)
    current = layers.pin_ref(file_id, root)
    enters_model_call = lf.layer in layers.PROMPT_LAYERS
    pinned = recordings.pinned_count(lf.body) if (name == DEFAULT and enters_model_call) else 0
    runs_root = runs_root or store_module.RUNS_ROOT
    run_rows = []
    for run_id in runs_admin.runs_using_prompt_set(name, runs_root):
        artifacts = []
        for art in _run_pins(runs_root / run_id):
            ref = art["pins"].get(file_id)
            if ref:
                artifacts.append({
                    "artifact": art["artifact"], "kind": art["kind"],
                    "artifact_version": art["version"], "pinned": ref,
                    "stale": ref != current,
                })
        run_rows.append({
            "run_id": run_id, "artifacts": artifacts,
            "would_go_stale": [a["artifact"] for a in artifacts],
        })
    return {
        "provenance": "rule_based",
        "profile": name, "file_id": file_id, "layer": lf.layer, "source": lf.source,
        "current": current,
        "enters_model_call": enters_model_call,
        "recordings_pinned": pinned,
        "re_record_needed": enters_model_call and name == DEFAULT and pinned > 0,
        "consumers": list(layers.CONSUMERS.get(file_id, ())),
        "runs": run_rows,
    }


# --- export / import ----------------------------------------------------------


def export_zip(name: str) -> bytes:
    """The profile directory, exactly — overrides, ledger, snapshots, meta."""
    if kind_of(name) != "profile":
        raise ProfileError(f"{name!r} is not an exportable profile (only overlay profiles export)")
    base = _dir(name)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(base.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(base).as_posix())
    return buf.getvalue()


def _safe_member(member: str) -> Path:
    rel = Path(member)
    if rel.is_absolute() or ".." in rel.parts or not rel.parts:
        raise ProfileError(f"refusing zip member {member!r}")
    if rel.parts[0] not in _ALLOWED_TOP:
        raise ProfileError(
            f"refusing zip member {member!r} — a profile holds only "
            f"{', '.join(sorted(_ALLOWED_TOP))}"
        )
    return rel


def import_zip(
    data: bytes, *, name: str | None = None, author: str = "", replace: bool = False,
) -> dict[str, Any]:
    """Install a profile from an export. The name comes from the zip's
    `profile.json` unless given; every layer file must parse (a malformed
    import is removed again, never left half-installed)."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ProfileError(f"not a zip file: {exc}") from exc
    members = [m for m in zf.namelist() if not m.endswith("/")]
    if META_FILE not in members:
        raise ProfileError(f"the zip carries no {META_FILE}")
    incoming = json.loads(zf.read(META_FILE).decode("utf-8"))
    target_name = name or incoming.get("name", "")
    if not _NAME_RE.match(target_name or ""):
        raise ProfileError(f"profile name {target_name!r} must be lowercase kebab-case")
    if exists(target_name) and not replace:
        raise ProfileError(f"profile {target_name!r} already exists — pass replace to overwrite")
    if exists(target_name) and kind_of(target_name) != "profile":
        raise ProfileError(f"{target_name!r} is not a profile and cannot be replaced by an import")
    safe = [(m, _safe_member(m)) for m in members]
    target = _dir(target_name)
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    try:
        for member, rel in safe:
            dest = target / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(zf.read(member))
        incoming["name"] = target_name
        incoming.setdefault("base", DEFAULT)
        incoming["imported_at"] = now_iso()
        incoming["imported_by"] = author
        (target / META_FILE).write_text(json.dumps(incoming, indent=2) + "\n", encoding="utf-8")
        layers.load_all(target)  # every override must parse, or the import is refused
    except Exception:
        shutil.rmtree(target, ignore_errors=True)
        raise
    audit(author, "profile.import", target_name,
          detail=f"{len(members)} files" + (" (replaced)" if replace else ""))
    return _summary(target_name)

"""S7 Admin — HTTP layer over the product configuration plane.

Thin, like the Control Centre: every rule lives in `s7_delivery.product.*`
and `s7_delivery.factory.layers`; this module translates HTTP to those calls
and maps their errors to the status codes `docs/admin-api.md` names.

Run with `demo/run_admin.sh`, or:

    uvicorn apps.admin.server:app --port 8730

Auth: when `S7_ADMIN_TOKEN` is set, every `/api/admin/*` request must carry
`X-Admin-Token`. `X-Admin-User` names the actor for the audit ledger
(default `admin`). Nothing here ever returns a credential value.
"""

from __future__ import annotations

import hmac
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from common.llm import LLMError
from common.prompt import PromptLayers
from s7_delivery.factory import layers
from s7_delivery.factory.engine import EngineError
from s7_delivery.factory.layers import LayerError
from s7_delivery.factory.roles import PermissionError_
from s7_delivery.factory.store import StoreError
from s7_delivery.product import (
    config,
    corrections,
    improve,
    llm_settings,
    observability,
    playbooks_admin,
    prompt_sets,
    recordings,
    roles_config,
    runs_admin,
    users,
)
from s7_delivery.product.config import ConfigError
from s7_delivery.product.improve import ImproveError
from s7_delivery.product.playbooks_admin import PlaybookValidationError
from s7_delivery.product.prompt_sets import PromptSetError
from s7_delivery.product.runs_admin import RunNotFound
from s7_delivery.product.users import UserError

STATIC_DIR = Path(__file__).resolve().parent / "web" / "dist"
TOKEN_ENV = "S7_ADMIN_TOKEN"
DEFAULT_ACTOR = "admin"
_LANE_STAGE_KEYS = ("development-lane.developer", "development-lane.tester",
                    "development-lane.reviewer")

app = FastAPI(
    title="S7 Admin",
    description="Operator surface over the product configuration plane: prompt "
    "sets, LLM settings, roles, users, runs and the audit ledger.",
)


# --- error mapping ------------------------------------------------------------


@app.exception_handler(LLMError)
async def _llm_error(_req: Any, exc: LLMError) -> JSONResponse:
    # A proposal is a real model call or nothing: a missing recording, a
    # provider failure or a malformed answer is reported, never papered over.
    return JSONResponse(status_code=502, content={"detail": str(exc)})


@app.exception_handler(ImproveError)
async def _improve_error(_req: Any, exc: ImproveError) -> JSONResponse:
    text = str(exc)
    stale = "changed since" in text or "already" in text
    return JSONResponse(status_code=409 if stale else 400, content={"detail": text})


@app.exception_handler(PromptSetError)
async def _prompt_set_error(_req: Any, exc: PromptSetError) -> JSONResponse:
    text = str(exc)
    if "unknown prompt set" in text:
        return JSONResponse(status_code=404, content={"detail": text})
    if "is used by run" in text or "cannot be deleted" in text:
        return JSONResponse(status_code=409, content={"detail": text})
    return JSONResponse(status_code=400, content={"detail": text})


@app.exception_handler(UserError)
async def _user_error(_req: Any, exc: UserError) -> JSONResponse:
    status = 404 if str(exc).startswith("unknown user") else 400
    return JSONResponse(status_code=status, content={"detail": str(exc)})


@app.exception_handler(ConfigError)
async def _config_error(_req: Any, exc: ConfigError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(PlaybookValidationError)
async def _playbook_validation_error(_req: Any, exc: PlaybookValidationError) -> JSONResponse:
    # 400 with every problem listed — the editor shows them all at once.
    return JSONResponse(status_code=400,
                        content={"detail": str(exc), "problems": exc.problems})


@app.exception_handler(LayerError)
async def _layer_error(_req: Any, exc: LayerError) -> JSONResponse:
    text = str(exc)
    status = 404 if ("no layer file" in text or "has no recorded body" in text) else 400
    return JSONResponse(status_code=status, content={"detail": text})


@app.exception_handler(RunNotFound)
async def _run_not_found(_req: Any, exc: RunNotFound) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(StoreError)
async def _store_error(_req: Any, exc: StoreError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(EngineError)
async def _engine_error(_req: Any, exc: EngineError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(PermissionError_)
async def _permission_error(_req: Any, exc: PermissionError_) -> JSONResponse:
    return JSONResponse(status_code=403, content={"detail": str(exc)})


# --- dependencies -------------------------------------------------------------


def _auth(x_admin_token: str | None = Header(default=None)) -> None:
    expected = os.environ.get(TOKEN_ENV)
    if not expected:
        return
    if not x_admin_token or not hmac.compare_digest(x_admin_token, expected):
        raise HTTPException(status_code=401, detail="admin token missing or wrong")


def _actor(x_admin_user: str | None = Header(default=None)) -> str:
    return (x_admin_user or "").strip() or DEFAULT_ACTOR


router = APIRouter(prefix="/api/admin", dependencies=[Depends(_auth)])


# --- overview -----------------------------------------------------------------


@router.get("/health")
def get_health() -> dict:
    return {"ok": True, "config_root": str(config.config_root())}


@router.get("/overview")
def get_overview() -> dict:
    rows = runs_admin.list_runs()
    by_mode = {m: 0 for m in ("simulation", "demo", "live", "replay")}
    for r in rows:
        by_mode[r["mode"]] = by_mode.get(r["mode"], 0) + 1
    env = llm_settings.describe()["environment"]
    return {
        "runs": {"total": len(rows), "by_mode": by_mode},
        "prompt_sets": len(prompt_sets.list_sets()),
        "users": len(users.list_users()),
        "llm": env,
        "default_set_unrecorded": [lf.id for lf in layers.unrecorded(layers.LAYERS_ROOT)],
        "recent_audit": config.audit_log(10),
    }


# --- prompt sets ----------------------------------------------------------------


class CreateSet(BaseModel):
    name: str
    cloned_from: str = prompt_sets.DEFAULT
    description: str = ""
    note: str = ""


class PatchSet(BaseModel):
    description: str


class PutFile(BaseModel):
    body: str
    note: str


class CreateFile(BaseModel):
    layer: str
    id: str
    title: str
    stage: str
    summary: str
    body: str
    variables: list[str] = []
    note: str


class Rollback(BaseModel):
    to_version: int
    note: str


def _set_root(name: str) -> Path:
    try:
        return prompt_sets.root_of(name)
    except PromptSetError as exc:
        raise HTTPException(status_code=404, detail=f"unknown prompt set {name!r}") from exc


def _file_row(root: Path, file_id: str) -> dict[str, Any]:
    desc = layers.describe(root)
    for key in ("rules", "skills", "tasks", "playbooks"):
        for row in desc[key]:
            if row["id"] == file_id:
                return row
    raise HTTPException(status_code=404, detail=f"no layer file {file_id!r} in this set")


def _file_detail(set_name: str, root: Path, file_id: str) -> dict[str, Any]:
    row = _file_row(root, file_id)
    body = layers.get(file_id, root).body
    pinned = recordings.pinned_count(body) if set_name == prompt_sets.DEFAULT else 0
    return {
        **row,
        "versions": layers.versions_of(file_id, root),
        "placeholders": layers.placeholders_of(body),
        "recordings_pinned": pinned,
    }


@router.get("/prompt-sets")
def get_prompt_sets() -> list[dict]:
    return prompt_sets.list_sets()


@router.post("/prompt-sets", status_code=201)
def post_prompt_set(body: CreateSet, actor: str = Depends(_actor)) -> dict:
    if not prompt_sets.exists(body.cloned_from):
        raise HTTPException(status_code=404,
                            detail=f"unknown prompt set {body.cloned_from!r}")
    return prompt_sets.create_set(
        body.name, cloned_from=body.cloned_from, description=body.description,
        author=actor, note=body.note,
    )


@router.get("/prompt-sets/{set_name}")
def get_prompt_set(set_name: str) -> dict:
    root = _set_root(set_name)
    desc = layers.describe(root)
    return {
        **prompt_sets.describe(set_name),
        "rules": desc["rules"], "skills": desc["skills"], "tasks": desc["tasks"],
        "playbooks": desc["playbooks"], "workflows": desc["workflows"],
    }


@router.patch("/prompt-sets/{set_name}")
def patch_prompt_set(set_name: str, body: PatchSet, actor: str = Depends(_actor)) -> dict:
    _set_root(set_name)
    return prompt_sets.update_description(set_name, body.description, author=actor)


@router.delete("/prompt-sets/{set_name}", status_code=204)
def delete_prompt_set(set_name: str, actor: str = Depends(_actor)) -> Response:
    _set_root(set_name)
    try:
        prompt_sets.delete_set(
            set_name, author=actor, in_use_by=runs_admin.runs_using_prompt_set(set_name),
        )
    except PromptSetError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return Response(status_code=204)


@router.get("/prompt-sets/{set_name}/history")
def get_prompt_set_history(set_name: str) -> list[dict]:
    return layers.history(_set_root(set_name))


@router.get("/prompt-sets/{set_name}/files/{file_id}")
def get_prompt_file(set_name: str, file_id: str) -> dict:
    return _file_detail(set_name, _set_root(set_name), file_id)


@router.put("/prompt-sets/{set_name}/files/{file_id}")
def put_prompt_file(set_name: str, file_id: str, body: PutFile,
                    actor: str = Depends(_actor)) -> dict:
    root = _set_root(set_name)
    before = _file_row(root, file_id)
    record = layers.write_body(file_id, body.body, note=body.note, author=actor, root=root)
    if record is not None:
        config.audit(actor, "prompt.write", f"{set_name}/{file_id}",
                     detail=f"v{record['version']}: {record['note']}",
                     before={"sha256": before["sha256"]}, after={"sha256": record["sha256"]})
    return {"record": record, "unchanged": record is None,
            "file": _file_detail(set_name, root, file_id)}


@router.post("/prompt-sets/{set_name}/files", status_code=201)
def post_prompt_file(set_name: str, body: CreateFile, actor: str = Depends(_actor)) -> dict:
    root = _set_root(set_name)
    record = layers.create_file(
        body.layer, body.id, title=body.title, stage=body.stage, summary=body.summary,
        body=body.body, variables=body.variables, note=body.note, author=actor, root=root,
    )
    config.audit(actor, "prompt.create", f"{set_name}/{body.id}",
                 detail=f"{body.layer} v1: {record['note']}",
                 after={"sha256": record["sha256"]})
    return _file_detail(set_name, root, body.id)


@router.get("/prompt-sets/{set_name}/files/{file_id}/versions/{version}")
def get_prompt_file_version(set_name: str, file_id: str, version: int) -> dict:
    root = _set_root(set_name)
    _file_row(root, file_id)
    text = layers.version_body(file_id, version, root)
    if text is None:
        raise HTTPException(status_code=404,
                            detail=f"{file_id}: version {version} has no recorded body")
    return {"version": version, "body": text}


@router.get("/prompt-sets/{set_name}/files/{file_id}/diff")
def get_prompt_file_diff(set_name: str, file_id: str,
                         from_version: int = Query(alias="from"),
                         to_version: int = Query(alias="to")) -> dict:
    root = _set_root(set_name)
    _file_row(root, file_id)
    return {"from": from_version, "to": to_version,
            "diff": layers.diff(file_id, from_version, to_version, root)}


@router.post("/prompt-sets/{set_name}/files/{file_id}/rollback")
def post_prompt_file_rollback(set_name: str, file_id: str, body: Rollback,
                              actor: str = Depends(_actor)) -> dict:
    root = _set_root(set_name)
    before = _file_row(root, file_id)
    record = layers.rollback(file_id, body.to_version, note=body.note, author=actor, root=root)
    if record is not None:
        config.audit(actor, "prompt.rollback", f"{set_name}/{file_id}",
                     detail=f"to v{body.to_version} as v{record['version']}: {record['note']}",
                     before={"sha256": before["sha256"]}, after={"sha256": record["sha256"]})
    return {"record": record, "unchanged": record is None,
            "file": _file_detail(set_name, root, file_id)}


def _workflow_preview(root: Path, wf: dict[str, Any]) -> dict[str, Any]:
    files = layers.load_all(root)
    rules_body = files[wf["rules"]].body if wf["rules"] in files else ""
    skill_bodies = [files[sid].body for sid in wf["skills"] if sid in files]
    system = PromptLayers(rules=rules_body, role="\n\n".join(skill_bodies), task="").system
    tasks = []
    for tid in wf.get("tasks", []):
        lf = files.get(tid)
        if lf is None:
            continue
        tasks.append({"id": lf.id, "title": lf.title, "variables": list(lf.variables),
                      "body": lf.body})
    keys = _LANE_STAGE_KEYS if wf["id"] == "development-lane" else (wf["id"],)
    return {
        **wf,
        "system_prompt": system or "",
        "tasks": tasks,
        "llm": {key: llm_settings.for_stage(key) for key in keys},
    }


@router.get("/prompt-sets/{set_name}/workflows")
def get_prompt_set_workflows(set_name: str) -> list[dict]:
    root = _set_root(set_name)
    return [_workflow_preview(root, dict(wf)) for wf in layers.WORKFLOWS]


@router.get("/prompt-sets/{set_name}/workflows/{workflow_id}")
def get_prompt_set_workflow(set_name: str, workflow_id: str) -> dict:
    root = _set_root(set_name)
    for wf in layers.WORKFLOWS:
        if wf["id"] == workflow_id:
            return _workflow_preview(root, dict(wf))
    raise HTTPException(status_code=404, detail=f"unknown workflow {workflow_id!r}")


# --- LLM settings, recordings, cache ------------------------------------------


@router.get("/llm")
def get_llm() -> dict:
    return llm_settings.describe()


@router.put("/llm")
def put_llm(body: dict, actor: str = Depends(_actor)) -> dict:
    return llm_settings.save(body, actor=actor)


@router.get("/recordings")
def get_recordings() -> dict:
    return recordings.inventory()


@router.get("/cache")
def get_cache() -> dict:
    return recordings.cache_stats()


@router.delete("/cache")
def delete_cache(actor: str = Depends(_actor)) -> dict:
    return recordings.clear_cache(actor=actor)


# --- roles ----------------------------------------------------------------------


@router.get("/roles")
def get_roles() -> dict:
    return roles_config.describe()


@router.put("/roles")
def put_roles(body: dict, actor: str = Depends(_actor)) -> dict:
    roles_config.save(body, actor=actor)
    return roles_config.describe()


@router.post("/roles/reset")
def post_roles_reset(actor: str = Depends(_actor)) -> dict:
    roles_config.reset(actor=actor)
    return roles_config.describe()


# --- users ----------------------------------------------------------------------


class CreateUser(BaseModel):
    name: str
    role: str
    email: str = ""


class PatchUser(BaseModel):
    name: str | None = None
    email: str | None = None
    role: str | None = None
    active: bool | None = None


@router.get("/users")
def get_users() -> list[dict]:
    return users.list_users()


@router.post("/users", status_code=201)
def post_user(body: CreateUser, actor: str = Depends(_actor)) -> dict:
    return users.create(body.name, body.role, email=body.email, actor=actor)


@router.patch("/users/{user_id}")
def patch_user(user_id: str, body: PatchUser, actor: str = Depends(_actor)) -> dict:
    users.get(user_id)
    return users.update(user_id, actor=actor, name=body.name, email=body.email,
                        role=body.role, active=body.active)


@router.delete("/users/{user_id}", status_code=204)
def delete_user(user_id: str, actor: str = Depends(_actor)) -> Response:
    users.delete(user_id, actor=actor)
    return Response(status_code=204)


# --- runs -----------------------------------------------------------------------


@router.get("/runs")
def get_runs() -> list[dict]:
    return runs_admin.list_runs()


@router.get("/runs/archived")
def get_runs_archived() -> list[dict]:
    return runs_admin.list_archived()


@router.post("/runs/{run_id}/reset")
def post_run_reset(run_id: str, actor: str = Depends(_actor)) -> dict:
    return runs_admin.reset(run_id, actor=actor)


@router.post("/runs/{run_id}/archive")
def post_run_archive(run_id: str, actor: str = Depends(_actor)) -> dict:
    return runs_admin.archive(run_id, actor=actor)


@router.get("/runs/{run_id}/self-healing")
def get_run_self_healing(run_id: str) -> dict:
    """The run's self-healing change records and playbook progress. Moved
    here from the Control Centre (2026-09-03): the engine still opens and
    advances changes on its own, but the view is an operator's, not a
    presenter's. Read-only; gates are observed, never signed from here."""
    from s7_delivery.factory import self_heal
    from s7_delivery.factory.engine import Engine
    from s7_delivery.factory.store import list_runs

    if run_id not in list_runs():
        raise RunNotFound(run_id)
    eng = Engine(run_id)
    with eng._prompt_set():
        return self_heal.view(eng)


@router.delete("/runs/{run_id}", status_code=204)
def delete_run(run_id: str, actor: str = Depends(_actor)) -> Response:
    runs_admin.delete(run_id, actor=actor)
    return Response(status_code=204)


# --- playbooks (structured editing of the self-healing layer) -----------------


class PutPlaybook(BaseModel):
    trigger: str | None = None
    stage: str | None = None
    steps: list[dict[str, Any]]
    note: str


class ValidateSteps(BaseModel):
    steps: list[dict[str, Any]]


@router.get("/playbook-actions")
def get_playbook_actions() -> dict:
    return playbooks_admin.catalogue()


@router.get("/prompt-sets/{set_name}/playbooks")
def get_playbooks(set_name: str) -> list[dict]:
    _set_root(set_name)
    return playbooks_admin.list_playbooks(set_name)


@router.get("/prompt-sets/{set_name}/playbooks/{playbook_id}")
def get_playbook(set_name: str, playbook_id: str) -> dict:
    _set_root(set_name)
    return playbooks_admin.get_playbook(set_name, playbook_id)


@router.put("/prompt-sets/{set_name}/playbooks/{playbook_id}")
def put_playbook(set_name: str, playbook_id: str, body: PutPlaybook,
                 actor: str = Depends(_actor)) -> dict:
    _set_root(set_name)
    return playbooks_admin.save_playbook(
        set_name, playbook_id, steps=body.steps, note=body.note,
        trigger=body.trigger, stage=body.stage, actor=actor,
    )


@router.post("/prompt-sets/{set_name}/playbooks/{playbook_id}/validate")
def post_playbook_validate(set_name: str, playbook_id: str, body: ValidateSteps) -> dict:
    _set_root(set_name)
    playbooks_admin.get_playbook(set_name, playbook_id)  # 404 for an unknown playbook
    return playbooks_admin.validate_steps(body.steps, set_name)


# --- observability (cross-run, derived on read, RULE_BASED) ---------------------


@router.get("/observability")
def get_observability(days: int = 30, prompt_set: str = "") -> dict:
    if prompt_set:
        _set_root(prompt_set)
    return observability.report(days, prompt_set or None)


# --- correction learning (admin only; the Control Centre never sees it) ---------


class ProposeBody(BaseModel):
    prompt_set: str = "default"
    target_id: str
    correction_ids: list[str] | None = None
    days: int | None = None
    learnable_only: bool = True
    note: str = ""


class DecideBody(BaseModel):
    note: str


def _with_state(rec: dict[str, Any]) -> dict[str, Any]:
    return {**rec, "state": improve.current_state(rec)}


def _proposal(set_name: str, proposal_id: str) -> dict[str, Any]:
    _set_root(set_name)
    try:
        return improve.get(set_name, proposal_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"unknown proposal {proposal_id!r}") from exc


@router.get("/learning/overview")
def get_learning_overview(prompt_set: str = "", days: int | None = None) -> dict:
    if prompt_set:
        _set_root(prompt_set)
    summary = corrections.summary(prompt_set=prompt_set or None, days=days)
    proposals = improve.list_proposals(prompt_set or None)
    by_target_pending: dict[str, int] = {}
    for p in proposals:
        if p["status"] == "proposed":
            by_target_pending[p["target_id"]] = by_target_pending.get(p["target_id"], 0) + 1
    rows = corrections.list_corrections(prompt_set=prompt_set or None, days=days,
                                        learnable_only=False)
    targets = []
    root = _set_root(prompt_set) if prompt_set else None
    for t in summary["by_target"]:
        try:
            lf = layers.get(t["target_id"], root)
        except LayerError:
            continue
        last = max((r["timestamp"] for r in rows
                    if t["target_id"] in (r.get("skill_id"), r.get("task_id"))), default=None)
        targets.append({
            "target_id": lf.id, "layer": lf.layer, "stage": lf.stage,
            "corrections_learnable": t["learnable"],
            "corrections_total": t["learnable"] + t["not_learnable"],
            "proposals_pending": by_target_pending.get(lf.id, 0),
            "last_correction": last,
            "version": layers.version_of(lf.id, root)["version"],
        })
    counts = {"proposed": 0, "accepted": 0, "rejected": 0}
    for p in proposals:
        counts[p["status"]] = counts.get(p["status"], 0) + 1
    return {"provenance": "rule_based", "corrections": summary,
            "proposals": counts, "targets": targets}


@router.get("/learning/corrections")
def get_learning_corrections(
    prompt_set: str = "", stage: str = "", target_id: str = "",
    days: int | None = None, learnable_only: bool = True,
) -> list[dict]:
    if prompt_set:
        _set_root(prompt_set)
    return corrections.list_corrections(
        prompt_set=prompt_set or None, stage=stage or None, target_id=target_id or None,
        days=days, learnable_only=learnable_only,
    )


@router.get("/learning/corrections/{correction_id}")
def get_learning_correction(correction_id: str) -> dict:
    try:
        return corrections.get(correction_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=404, detail=f"unknown correction {correction_id!r}"
        ) from exc


@router.get("/learning/proposals")
def get_learning_proposals(prompt_set: str = "", status: str = "") -> list[dict]:
    if prompt_set:
        _set_root(prompt_set)
    return [_with_state(p) for p in improve.list_proposals(prompt_set or None, status or None)]


@router.post("/learning/proposals", status_code=201)
def post_learning_proposal(body: ProposeBody, actor: str = Depends(_actor)) -> dict:
    _set_root(body.prompt_set)
    rows = corrections.list_corrections(
        prompt_set=body.prompt_set, target_id=body.target_id, days=body.days,
        learnable_only=body.learnable_only,
    )
    if body.correction_ids:
        wanted = set(body.correction_ids)
        rows = [r for r in rows if r["correction_id"] in wanted]
        missing = sorted(wanted - {r["correction_id"] for r in rows})
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"corrections not found for this target/filter: {missing}",
            )
    rec = improve.propose(body.prompt_set, body.target_id, rows, actor=actor, note=body.note)
    return _with_state(rec)


@router.get("/learning/proposals/{set_name}/{proposal_id}")
def get_learning_proposal(set_name: str, proposal_id: str) -> dict:
    rec = _proposal(set_name, proposal_id)
    return {**_with_state(rec), "diff": improve.diff(rec)}


@router.post("/learning/proposals/{set_name}/{proposal_id}/accept")
def post_learning_accept(set_name: str, proposal_id: str, body: DecideBody,
                         actor: str = Depends(_actor)) -> dict:
    _proposal(set_name, proposal_id)
    return _with_state(improve.accept(set_name, proposal_id, note=body.note, actor=actor))


@router.post("/learning/proposals/{set_name}/{proposal_id}/reject")
def post_learning_reject(set_name: str, proposal_id: str, body: DecideBody,
                         actor: str = Depends(_actor)) -> dict:
    _proposal(set_name, proposal_id)
    return _with_state(improve.reject(set_name, proposal_id, note=body.note, actor=actor))


# --- audit ----------------------------------------------------------------------


@router.get("/audit")
def get_audit(limit: int = 200, action: str = "") -> list[dict]:
    return config.audit_log(limit, action=action or None)


app.include_router(router)


# --- static shell -----------------------------------------------------------

if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="admin")

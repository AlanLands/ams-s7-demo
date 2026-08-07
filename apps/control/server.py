"""S7 Delivery Control Centre — HTTP layer.

Thin on purpose, like the other two surfaces: every rule (gate conditions,
role permissions, stage transitions) lives in `s7_delivery.factory`, so no
endpoint can be a side door. This module translates HTTP to engine calls.

Run with `demo/run_control.sh`, or:

    uvicorn apps.control.server:app --port 8720

State lives on disk under `artifacts/runs/<run-id>/` — the server holds
nothing in memory, so a browser refresh or server restart loses nothing
(spec §20).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from s7_delivery.factory import seed
from s7_delivery.factory.engine import Engine, EngineError
from s7_delivery.factory.models import DemoMode, Role
from s7_delivery.factory.roles import PermissionError_, actions_for
from s7_delivery.factory.store import StoreError, list_runs

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(
    title="S7 Delivery Control Centre",
    description="Governed AI-assisted delivery: intake → planning → build & "
    "review → quality → release. Customer-safe surface over the factory engine.",
)


@app.exception_handler(EngineError)
async def _engine_error(_req: Any, exc: EngineError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(PermissionError_)
async def _permission_error(_req: Any, exc: PermissionError_) -> JSONResponse:
    return JSONResponse(status_code=403, content={"detail": str(exc)})


@app.exception_handler(StoreError)
async def _store_error(_req: Any, exc: StoreError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


def _engine(run_id: str) -> Engine:
    if run_id not in list_runs():
        raise HTTPException(status_code=404, detail=f"Unknown run {run_id}")
    return Engine(run_id)


def _role(value: str) -> Role:
    try:
        return Role(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Unknown role {value!r}") from exc


# --- scenarios and runs -----------------------------------------------------


@app.get("/api/scenarios")
def get_scenarios() -> list[dict]:
    return [seed.SCENARIO.model_dump(mode="json")]


@app.get("/api/roles")
def get_roles() -> list[dict]:
    return [
        {"role": r.value, "actions": actions_for(r)}
        for r in Role
    ]


@app.get("/api/runs")
def get_runs() -> list[str]:
    return list_runs()


class CreateRun(BaseModel):
    mode: str = "simulation"


@app.post("/api/runs")
def post_runs(body: CreateRun) -> dict:
    try:
        mode = DemoMode(body.mode)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Unknown mode {body.mode!r}") from exc
    if mode is DemoMode.LIVE:
        raise HTTPException(
            status_code=400,
            detail="Live mode is not enabled for the demonstration; use "
            "simulation or replay (spec §20: the demo never depends on a "
            "live model call).",
        )
    eng = Engine.create(mode)
    return eng.state()


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict:
    return _engine(run_id).state()


class RoleBody(BaseModel):
    role: str


@app.post("/api/runs/{run_id}/reset")
def post_reset(run_id: str, body: RoleBody) -> dict:
    eng = _engine(run_id)
    eng.reset(_role(body.role))
    return eng.state()


# --- intake (spec §7) -------------------------------------------------------


@app.post("/api/runs/{run_id}/intake/analyse")
def post_intake_analyse(run_id: str, body: RoleBody) -> dict:
    eng = _engine(run_id)
    eng.intake_analyse(_role(body.role))
    return eng.state()


@app.post("/api/runs/{run_id}/intake/create-epic")
def post_intake_epic(run_id: str, body: RoleBody) -> dict:
    eng = _engine(run_id)
    eng.intake_create_epic(_role(body.role))
    return eng.state()


@app.post("/api/runs/{run_id}/intake/pass-gate")
def post_intake_gate(run_id: str, body: RoleBody) -> dict:
    eng = _engine(run_id)
    eng.intake_pass_gate(_role(body.role))
    return eng.state()


# --- planning (spec §8) -----------------------------------------------------


@app.post("/api/runs/{run_id}/planning/generate")
def post_planning_generate(run_id: str, body: RoleBody) -> dict:
    eng = _engine(run_id)
    eng.planning_generate(_role(body.role))
    return eng.state()


class StoryPatch(BaseModel):
    role: str
    patch: dict


@app.patch("/api/runs/{run_id}/stories/{story_id}")
def patch_story(run_id: str, story_id: str, body: StoryPatch) -> dict:
    eng = _engine(run_id)
    eng.edit_story(_role(body.role), story_id, body.patch)
    return eng.state()


class ReviseBody(BaseModel):
    role: str
    feedback: str


@app.post("/api/runs/{run_id}/planning/revise")
def post_planning_revise(run_id: str, body: ReviseBody) -> dict:
    eng = _engine(run_id)
    eng.planning_revise(_role(body.role), body.feedback)
    return eng.state()


class SignOffBody(BaseModel):
    role: str
    approver: str
    note: str = ""


@app.post("/api/runs/{run_id}/planning/sign-off")
def post_planning_signoff(run_id: str, body: SignOffBody) -> dict:
    eng = _engine(run_id)
    eng.planning_sign_off(_role(body.role), body.approver, body.note)
    return eng.state()


# --- build & independent review (spec §9) -----------------------------------


def _task_action(run_id: str, body: RoleBody, method_name: str, task_id: str) -> dict:
    eng = _engine(run_id)
    getattr(eng, method_name)(_role(body.role), task_id)
    return eng.state()


@app.post("/api/runs/{run_id}/tasks/{task_id}/start")
def post_task_start(run_id: str, task_id: str, body: RoleBody) -> dict:
    return _task_action(run_id, body, "task_start", task_id)


@app.post("/api/runs/{run_id}/tasks/{task_id}/generate-tests")
def post_task_tests(run_id: str, task_id: str, body: RoleBody) -> dict:
    return _task_action(run_id, body, "task_generate_tests", task_id)


@app.post("/api/runs/{run_id}/tasks/{task_id}/develop")
def post_task_develop(run_id: str, task_id: str, body: RoleBody) -> dict:
    return _task_action(run_id, body, "task_develop", task_id)


@app.post("/api/runs/{run_id}/tasks/{task_id}/verify")
def post_task_verify(run_id: str, task_id: str, body: RoleBody) -> dict:
    return _task_action(run_id, body, "task_verify", task_id)


@app.post("/api/runs/{run_id}/tasks/{task_id}/submit-review")
def post_task_submit(run_id: str, task_id: str, body: RoleBody) -> dict:
    return _task_action(run_id, body, "task_submit_review", task_id)


@app.post("/api/runs/{run_id}/tasks/{task_id}/run-to-review")
def post_task_run(run_id: str, task_id: str, body: RoleBody) -> dict:
    return _task_action(run_id, body, "task_run_to_review", task_id)


@app.post("/api/runs/{run_id}/reviews/{task_id}/execute")
def post_review_execute(run_id: str, task_id: str, body: RoleBody) -> dict:
    eng = _engine(run_id)
    eng.review_execute(_role(body.role), task_id)
    return eng.state()


@app.post("/api/runs/{run_id}/reviews/{task_id}/return-to-development")
def post_review_return(run_id: str, task_id: str, body: RoleBody) -> dict:
    eng = _engine(run_id)
    eng.review_return_to_development(_role(body.role), task_id)
    return eng.state()


# --- static shell -----------------------------------------------------------

if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="control")

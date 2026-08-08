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

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from common.llm import LLMError
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


@app.exception_handler(LLMError)
async def _llm_error(_req: Any, exc: LLMError) -> JSONResponse:
    return JSONResponse(status_code=502, content={"detail": str(exc)})


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


MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10MB — demo evidence, not a document store


@app.post("/api/runs/{run_id}/intake/upload-document")
async def post_intake_upload_document(
    run_id: str, role: str = Form(...), file: UploadFile = File(...)
) -> dict:
    eng = _engine(run_id)
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="File exceeds the 10MB demo limit")
    eng.intake_upload_document(_role(role), file.filename or "document", content)
    return eng.state()


@app.get("/api/runs/{run_id}/intake/documents/{name}")
def get_intake_document(run_id: str, name: str) -> FileResponse:
    eng = _engine(run_id)
    path = eng.store.path("intake", "documents", name)  # store.path rejects traversal
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"No document {name!r}")
    return FileResponse(path, filename=name)


class ConnectRepoBody(BaseModel):
    role: str
    url: str


@app.post("/api/runs/{run_id}/intake/connect-repo")
def post_intake_connect_repo(run_id: str, body: ConnectRepoBody) -> dict:
    eng = _engine(run_id)
    eng.intake_connect_repo(_role(body.role), body.url)
    return eng.state()


@app.post("/api/runs/{run_id}/intake/clarify")
def post_intake_clarify(run_id: str, body: RoleBody) -> dict:
    eng = _engine(run_id)
    eng.intake_clarify(_role(body.role))
    return eng.state()


class ClarifyAnswerBody(BaseModel):
    role: str
    answers: list[str]


@app.post("/api/runs/{run_id}/intake/clarify-answer")
def post_intake_clarify_answer(run_id: str, body: ClarifyAnswerBody) -> dict:
    eng = _engine(run_id)
    eng.intake_clarify_answer(_role(body.role), body.answers)
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


class AddStoryBody(BaseModel):
    role: str
    story: dict


@app.post("/api/runs/{run_id}/stories")
def post_story_add(run_id: str, body: AddStoryBody) -> dict:
    eng = _engine(run_id)
    eng.planning_add_story(_role(body.role), body.story)
    return eng.state()


class ImportStoriesBody(BaseModel):
    role: str
    stories: list[dict]


@app.post("/api/runs/{run_id}/stories/import")
def post_stories_import(run_id: str, body: ImportStoriesBody) -> dict:
    eng = _engine(run_id)
    eng.planning_import_stories(_role(body.role), body.stories)
    return eng.state()


_FILE_STAGES = {"planning", "build", "quality", "release"}


def _stage_dir(stage: str) -> str:
    if stage not in _FILE_STAGES:
        raise HTTPException(status_code=404, detail=f"Unknown artifact stage {stage!r}")
    return stage


@app.get("/api/runs/{run_id}/{stage}/files")
def get_stage_files(run_id: str, stage: str) -> list[dict]:
    """A stage's artifacts as they exist on disk — real names, real sizes."""
    eng = _engine(run_id)
    root = eng.store.path(_stage_dir(stage))
    if not root.is_dir():
        return []
    return [
        {"name": p.name, "bytes": p.stat().st_size}
        for p in sorted(root.iterdir())
        if p.is_file()
    ]


@app.get("/api/runs/{run_id}/{stage}/files/{name}")
def get_stage_file(run_id: str, stage: str, name: str) -> FileResponse:
    eng = _engine(run_id)
    path = eng.store.path(_stage_dir(stage), name)  # store.path rejects traversal
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"No {stage} artifact {name!r}")
    media = "text/markdown" if name.endswith(".md") else "application/json"
    return FileResponse(path, media_type=media, filename=name)


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


# --- quality (spec §10) -----------------------------------------------------


@app.post("/api/runs/{run_id}/quality/run")
def post_quality_run(run_id: str, body: RoleBody) -> dict:
    eng = _engine(run_id)
    eng.quality_run(_role(body.role))
    return eng.state()


@app.post("/api/runs/{run_id}/quality/decide")
def post_quality_decide(run_id: str, body: RoleBody) -> dict:
    eng = _engine(run_id)
    eng.quality_decide(_role(body.role))
    return eng.state()


# --- release (spec §11) -----------------------------------------------------


@app.post("/api/runs/{run_id}/release/request-approval")
def post_release_request(run_id: str, body: RoleBody) -> dict:
    eng = _engine(run_id)
    eng.release_request_approval(_role(body.role))
    return eng.state()


class ReleaseApproveBody(BaseModel):
    role: str
    approver: str
    note: str = ""
    decision: str = "approved"


@app.post("/api/runs/{run_id}/release/approve")
def post_release_approve(run_id: str, body: ReleaseApproveBody) -> dict:
    eng = _engine(run_id)
    eng.release_approve(_role(body.role), body.approver, body.note, body.decision)
    return eng.state()


@app.post("/api/runs/{run_id}/release/deploy")
def post_release_deploy(run_id: str, body: RoleBody) -> dict:
    eng = _engine(run_id)
    eng.release_deploy(_role(body.role))
    return eng.state()


@app.post("/api/runs/{run_id}/release/handover")
def post_release_handover(run_id: str, body: RoleBody) -> dict:
    eng = _engine(run_id)
    eng.release_handover(_role(body.role))
    return eng.state()


# --- governance: staleness & self-correction (spec §15, §16) ----------------


@app.post("/api/runs/{run_id}/change/upstream")
def post_upstream_change(run_id: str, body: RoleBody) -> dict:
    eng = _engine(run_id)
    eng.trigger_upstream_change(_role(body.role))
    return eng.state()


@app.post("/api/runs/{run_id}/change/self-correct")
def post_self_correct(run_id: str, body: RoleBody) -> dict:
    eng = _engine(run_id)
    eng.run_self_correction(_role(body.role))
    return eng.state()


@app.get("/api/runs/{run_id}/traceability")
def get_traceability(run_id: str) -> list[dict]:
    return _engine(run_id).traceability()


# --- scripted demo scenarios (spec §20) -------------------------------------


@app.get("/api/demo-scenarios")
def get_demo_scenarios() -> list[str]:
    from s7_delivery.factory.demo import SCENARIOS

    return sorted(SCENARIOS)


@app.post("/api/demo/{action}")
def post_demo(action: str) -> dict:
    """Create a fresh run driven to the named scenario's known state.
    Every step goes through the engine — gates, roles and ledgers all run."""
    from s7_delivery.factory import demo

    eng = demo.load(action)
    return eng.state()


# --- static shell -----------------------------------------------------------

if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="control")

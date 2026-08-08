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

import io
import zipfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from common.llm import LLMError
from s7_delivery.factory import extraction, roles, seed
from s7_delivery.factory.build_phases import PhaseError
from s7_delivery.factory.engine import Engine, EngineError
from s7_delivery.factory.models import DemoMode, Role
from s7_delivery.factory.roles import PermissionError_, actions_for
from s7_delivery.factory.store import StoreError, list_runs

STATIC_DIR = Path(__file__).resolve().parent / "web" / "dist"

app = FastAPI(
    title="S7 Delivery Control Centre",
    description="Governed AI-assisted delivery: intake → planning → build & "
    "review → quality → release. Customer-safe surface over the factory engine.",
)


@app.exception_handler(EngineError)
async def _engine_error(_req: Any, exc: EngineError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(PhaseError)
async def _phase_error(_req: Any, exc: PhaseError) -> JSONResponse:
    # An out-of-order Build & Review action is the same class of refusal as
    # any other engine rule violation.
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


@app.post("/api/runs/{run_id}/intake/route")
def post_intake_route(run_id: str, body: RoleBody) -> dict:
    eng = _engine(run_id)
    eng.intake_route(_role(body.role))
    return eng.state()


class OverrideRouteBody(BaseModel):
    role: str
    verdict: str


@app.post("/api/runs/{run_id}/intake/override-route")
def post_intake_override_route(run_id: str, body: OverrideRouteBody) -> dict:
    eng = _engine(run_id)
    eng.intake_override_route(_role(body.role), body.verdict)
    return eng.state()


@app.post("/api/runs/{run_id}/intake/new-app-setup")
def post_new_app_setup(run_id: str, body: RoleBody) -> dict:
    eng = _engine(run_id)
    eng.intake_new_app_setup(_role(body.role))
    return eng.state()


class NewAppAnswerBody(BaseModel):
    role: str
    answers: list[str]


@app.post("/api/runs/{run_id}/intake/new-app-answer")
def post_new_app_answer(run_id: str, body: NewAppAnswerBody) -> dict:
    eng = _engine(run_id)
    eng.intake_new_app_answer(_role(body.role), body.answers)
    return eng.state()


@app.post("/api/runs/{run_id}/intake/generate-scaffold")
def post_generate_scaffold(run_id: str, body: RoleBody) -> dict:
    eng = _engine(run_id)
    eng.intake_generate_scaffold(_role(body.role))
    return eng.state()


@app.post("/api/runs/{run_id}/intake/create-new-app-repo")
def post_create_new_app_repo(run_id: str, body: RoleBody) -> dict:
    eng = _engine(run_id)
    eng.intake_create_new_app_repo(_role(body.role))
    return eng.state()


@app.post("/api/runs/{run_id}/intake/upload-source")
async def post_intake_upload_source(
    run_id: str, role: str = Form(...), file: UploadFile = File(...)
) -> dict:
    eng = _engine(run_id)
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="File exceeds the 10MB demo limit")
    filename = file.filename or "document"
    try:
        text = extraction.decode_source(filename, content)
    except extraction.ExtractionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    r = _role(role)
    # Check both permissions before either engine call, so a 403 is atomic —
    # no partial write of source.json followed by a refused extraction.
    roles.require("upload_intake_document", r)
    roles.require("run_intake_analysis", r)
    eng.intake_set_source(r, text, filename=filename, source_kind="upload", raw_content=content)
    eng.intake_extract(r)
    return eng.state()


class PasteSourceBody(BaseModel):
    role: str
    text: str


@app.post("/api/runs/{run_id}/intake/paste-source")
def post_intake_paste_source(run_id: str, body: PasteSourceBody) -> dict:
    eng = _engine(run_id)
    r = _role(body.role)
    # Check both permissions before either engine call — see upload-source.
    roles.require("upload_intake_document", r)
    roles.require("run_intake_analysis", r)
    eng.intake_set_source(r, body.text, source_kind="paste")
    eng.intake_extract(r)
    return eng.state()


@app.post("/api/runs/{run_id}/intake/re-extract")
def post_intake_re_extract(run_id: str, body: RoleBody) -> dict:
    eng = _engine(run_id)
    eng.intake_extract(_role(body.role))
    return eng.state()


class ExtractionPatch(BaseModel):
    role: str
    patch: dict


@app.patch("/api/runs/{run_id}/intake/extraction")
def patch_intake_extraction(run_id: str, body: ExtractionPatch) -> dict:
    eng = _engine(run_id)
    eng.intake_edit_extraction(_role(body.role), body.patch)
    return eng.state()


@app.post("/api/runs/{run_id}/intake/finalize-epic")
def post_intake_finalize_epic(run_id: str, body: RoleBody) -> dict:
    eng = _engine(run_id)
    eng.intake_finalize(_role(body.role))
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


@app.post("/api/runs/{run_id}/planning/export-artifacts")
def post_export_artifacts(run_id: str, body: RoleBody) -> dict:
    eng = _engine(run_id)
    eng.planning_export_artifacts(_role(body.role))
    return eng.state()


@app.post("/api/runs/{run_id}/planning/write-to-clone")
def post_write_to_clone(run_id: str, body: RoleBody) -> dict:
    eng = _engine(run_id)
    eng.planning_write_to_clone(_role(body.role))
    return eng.state()


class PushDeliveryBody(BaseModel):
    role: str
    repo_name: str


@app.post("/api/runs/{run_id}/planning/push-delivery-branch")
def post_push_delivery_branch(run_id: str, body: PushDeliveryBody) -> dict:
    eng = _engine(run_id)
    eng.planning_push_delivery_branch(_role(body.role), body.repo_name)
    return eng.state()


@app.get("/api/runs/{run_id}/planning/export.zip")
def get_export_zip(run_id: str) -> StreamingResponse:
    eng = _engine(run_id)
    root = eng.store.path("planning", "export")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if root.is_dir():
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    zf.write(path, path.relative_to(root))
    buf.seek(0)
    return StreamingResponse(
        buf, media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{run_id}-delivery-export.zip"'},
    )


# --- architecture (Build & Review: engineering blueprint) --------------------


def _zip_of(root: Path, run_id: str, filename: str) -> StreamingResponse:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if root.is_dir():
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    zf.write(path, path.relative_to(root))
    buf.seek(0)
    return StreamingResponse(
        buf, media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/runs/{run_id}/architecture/generate")
def post_architecture_generate(run_id: str, body: RoleBody) -> dict:
    eng = _engine(run_id)
    eng.architecture_generate(_role(body.role))
    return eng.state()


@app.post("/api/runs/{run_id}/architecture/revise")
def post_architecture_revise(run_id: str, body: ReviseBody) -> dict:
    eng = _engine(run_id)
    eng.architecture_revise(_role(body.role), body.feedback)
    return eng.state()


class AcceptBody(BaseModel):
    role: str
    approver: str = ""


@app.post("/api/runs/{run_id}/architecture/accept")
def post_architecture_accept(run_id: str, body: AcceptBody) -> dict:
    eng = _engine(run_id)
    eng.architecture_accept(_role(body.role), body.approver)
    return eng.state()


@app.get("/api/runs/{run_id}/architecture/download.zip")
def get_architecture_zip(run_id: str) -> StreamingResponse:
    """The current architecture pack as a portable download — no side effects,
    canonical files stay in the artifact store."""
    eng = _engine(run_id)
    meta = eng.store.read_json_or(None, "architecture", "meta.json")
    if meta is None:
        raise HTTPException(status_code=404, detail="No architecture generated yet")
    root = eng.store.path("architecture", f"v{meta['version']}")
    return _zip_of(root, run_id, f"{run_id}-architecture-v{meta['version']}.zip")


@app.get("/api/runs/{run_id}/artifact-file/{rel_path:path}")
def get_artifact_file(run_id: str, rel_path: str) -> FileResponse:
    """Read-only preview of any file in the run's artifact tree. Every path
    segment passes the store's safe-segment validation — no traversal."""
    eng = _engine(run_id)
    segments = [s for s in rel_path.split("/") if s]
    if not segments:
        raise HTTPException(status_code=404, detail="Empty artifact path")
    path = eng.store.path(*segments)  # rejects unsafe segments + traversal
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"No artifact at {rel_path!r}")
    suffix = path.suffix.lower()
    media = {
        ".md": "text/markdown",
        ".json": "application/json",
        ".txt": "text/plain",
    }.get(suffix, "application/octet-stream")
    return FileResponse(path, media_type=media, filename=path.name)


# --- delivery packs ----------------------------------------------------------


@app.post("/api/runs/{run_id}/delivery-packs/generate")
def post_delivery_packs_generate(run_id: str, body: RoleBody) -> dict:
    eng = _engine(run_id)
    eng.delivery_packs_generate(_role(body.role))
    return eng.state()


@app.get("/api/runs/{run_id}/delivery-packs/{pack_id}/download.zip")
def get_delivery_pack_zip(run_id: str, pack_id: str) -> StreamingResponse:
    """Portable per-team package (spec §8) assembled from the canonical
    artifact tree — download changes no state, canonical files stay put."""
    eng = _engine(run_id)
    pack = next(
        (p for p in eng.store.read_json_or([], "build", "packs", "meta.json")
         if p["delivery_pack_id"] == pack_id),
        None,
    )
    if pack is None:
        raise HTTPException(status_code=404, detail=f"Unknown delivery pack {pack_id}")
    slug = pack["team_slug"]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        team_dir = eng.store.path("build", "packs", slug)
        for path in sorted(team_dir.rglob("*")):
            if path.is_file():
                name = path.name
                # spec §8 layout: team-dependencies.json ships as dependencies.json
                arcname = "dependencies.json" if name == "team-dependencies.json" else name
                zf.write(path, f"{slug}/{arcname}")
        arch_dir = eng.store.path("architecture", f"v{pack['architecture_version']}")
        for name in ("architecture.md", "engineering-rules.md"):
            p = arch_dir / name
            if p.is_file():
                zf.write(p, f"{slug}/architecture/{name}")
        for story_id in pack["story_ids"]:
            sdir = eng.store.path("build", "stories", story_id)
            for path in sorted(sdir.rglob("*")):
                if path.is_file():
                    zf.write(path, f"{slug}/stories/{story_id}/{path.name}")
        for task_id in pack["task_ids"]:
            tdir = eng.store.path("build", "tasks", task_id)
            for path in sorted(tdir.rglob("*")):
                if path.is_file():
                    zf.write(path, f"{slug}/tasks/{task_id}/{path.name}")
    buf.seek(0)
    filename = f"{slug}-delivery-pack-v{pack['version']}.zip"
    return StreamingResponse(
        buf, media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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

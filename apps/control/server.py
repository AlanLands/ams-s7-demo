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
from s7_delivery.factory import extraction, repos, roles, seed
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
    # "project" (epic → design → gate → stories) or "enhancement"
    # (S3-style: user stories enter directly).
    entry_mode: str = "project"


@app.post("/api/runs")
def post_runs(body: CreateRun) -> dict:
    try:
        mode = DemoMode(body.mode)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Unknown mode {body.mode!r}") from exc
    try:
        eng = Engine.create(mode, entry_mode=body.entry_mode)
    except EngineError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
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


@app.post("/api/runs/{run_id}/intake/repos/{name}/remove")
def post_intake_remove_repo(run_id: str, name: str, body: RoleBody) -> dict:
    eng = _engine(run_id)
    eng.intake_remove_repo(_role(body.role), name)
    return eng.state()


class BusinessRuleBody(BaseModel):
    role: str
    text: str


@app.post("/api/runs/{run_id}/intake/business-rules")
def post_intake_add_business_rule(run_id: str, body: BusinessRuleBody) -> dict:
    eng = _engine(run_id)
    eng.intake_add_business_rule(_role(body.role), body.text)
    return eng.state()


@app.post("/api/runs/{run_id}/intake/business-rules/{rule_id}/edit")
def post_intake_edit_business_rule(
    run_id: str, rule_id: str, body: BusinessRuleBody
) -> dict:
    eng = _engine(run_id)
    eng.intake_edit_business_rule(_role(body.role), rule_id, body.text)
    return eng.state()


@app.post("/api/runs/{run_id}/intake/business-rules/{rule_id}/remove")
def post_intake_remove_business_rule(run_id: str, rule_id: str, body: RoleBody) -> dict:
    eng = _engine(run_id)
    eng.intake_remove_business_rule(_role(body.role), rule_id)
    return eng.state()


# --- known-repos registry (global, no run scope — spec: "if I already
# connected the repository once, it should not ask me again if I reset") -----


@app.get("/api/known-repos")
def get_known_repos() -> dict:
    return {"repos": repos.known_repos()}


class ForgetRepoBody(BaseModel):
    role: str
    url: str


@app.post("/api/known-repos/forget")
def post_forget_known_repo(body: ForgetRepoBody) -> dict:
    """Forgetting is the mirror of connecting, so it takes the same
    permission — this endpoint is run-independent, which made it the one
    mutating route with no role check at all."""
    roles.require("connect_repository", _role(body.role))
    return {"removed": repos.forget_repo(body.url)}


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
    # Both engine calls below require the same single permission, checked
    # here before either runs, so a 403 stays atomic — no partial write of
    # source.json followed by a refused extraction.
    roles.require("upload_intake_document", r)
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
    # Single permission checked before either engine call — see upload-source.
    roles.require("upload_intake_document", r)
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


def _pack_zip_entries(eng, pack: dict, prefix: str) -> list[tuple[object, str]]:
    """(path, arcname) pairs for one pack — the canonical file set every pack
    download uses (spec §8 layout)."""
    slug = pack["team_slug"]
    entries: list[tuple[object, str]] = []
    team_dir = eng.store.path("build", "packs", slug)
    for path in sorted(team_dir.rglob("*")):
        if path.is_file():
            name = path.name
            # spec §8 layout: team-dependencies.json ships as dependencies.json
            arcname = "dependencies.json" if name == "team-dependencies.json" else name
            entries.append((path, f"{prefix}/{arcname}"))
    arch_dir = eng.store.path("architecture", f"v{pack['architecture_version']}")
    for name in ("architecture.md", "engineering-rules.md"):
        p = arch_dir / name
        if p.is_file():
            entries.append((p, f"{prefix}/architecture/{name}"))
    for story_id in pack["story_ids"]:
        sdir = eng.store.path("build", "stories", story_id)
        entries += [
            (path, f"{prefix}/stories/{story_id}/{path.name}")
            for path in sorted(sdir.rglob("*")) if path.is_file()
        ]
        # the AC test skeletons + manifest: published with the pack, so they
        # belong in the portable copy of it too
        tdir = eng.store.path("build", "tests", story_id)
        entries += [
            (path, f"{prefix}/tests/{story_id}/{path.name}")
            for path in sorted(tdir.rglob("*")) if path.is_file()
        ]
    for task_id in pack["task_ids"]:
        tdir = eng.store.path("build", "tasks", task_id)
        entries += [
            (path, f"{prefix}/tasks/{task_id}/{path.name}")
            for path in sorted(tdir.rglob("*")) if path.is_file()
        ]
    return entries


def _zip_response(entries: list[tuple[object, str]], filename: str) -> StreamingResponse:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, arcname in entries:
            zf.write(path, arcname)
    buf.seek(0)
    return StreamingResponse(
        buf, media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/runs/{run_id}/tasks/{task_id}/evidence.zip")
def get_task_evidence_zip(run_id: str, task_id: str) -> StreamingResponse:
    """One task's canonical evidence files as a portable download — no side
    effects; the canonical records stay in the artifact store."""
    eng = _engine(run_id)
    task = next(
        (t for t in eng.store.read_json_or([], "build", "tasks.json")
         if t["task_id"] == task_id),
        None,
    )
    if task is None:
        raise HTTPException(status_code=404, detail=f"Unknown task {task_id}")
    tdir = eng.store.path("build", "tasks", task_id)
    entries = [
        (p, f"{task_id}/{p.name}") for p in sorted(tdir.rglob("*")) if p.is_file()
    ]
    if not entries:
        raise HTTPException(status_code=404, detail=f"No evidence files for {task_id}")
    return _zip_response(entries, f"{task['story_id']}-{task_id}-evidence.zip")


@app.get("/api/runs/{run_id}/delivery-packs/download-all.zip")
def get_delivery_packs_zip_all(run_id: str) -> StreamingResponse:
    """Every team pack in one download, under delivery-packs/<team-slug>/ —
    no side effects, canonical files stay put."""
    eng = _engine(run_id)
    packs = eng.store.read_json_or([], "build", "packs", "meta.json")
    if not packs:
        raise HTTPException(status_code=404, detail="No delivery packs generated yet")
    entries: list[tuple[object, str]] = []
    for pack in packs:
        entries += _pack_zip_entries(eng, pack, f"delivery-packs/{pack['team_slug']}")
    return _zip_response(entries, f"{run_id}-delivery-packs.zip")


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
    return _zip_response(
        _pack_zip_entries(eng, pack, slug),
        f"{slug}-delivery-pack-v{pack['version']}.zip",
    )


@app.post("/api/runs/{run_id}/delivery-packs/{pack_id}/publish")
def post_delivery_pack_publish(run_id: str, pack_id: str, body: RoleBody) -> dict:
    eng = _engine(run_id)
    eng.delivery_pack_publish(_role(body.role), pack_id)
    return eng.state()


@app.post("/api/runs/{run_id}/delivery-packs/publish-all")
def post_delivery_packs_publish_all(run_id: str, body: RoleBody) -> dict:
    eng = _engine(run_id)
    eng.delivery_packs_publish_all(_role(body.role))
    return eng.state()


@app.post("/api/runs/{run_id}/delivery-packs/{pack_id}/approve-test-plan")
def post_test_plan_approve(run_id: str, pack_id: str, body: AcceptBody) -> dict:
    eng = _engine(run_id)
    eng.test_plan_approve(_role(body.role), pack_id, body.approver)
    return eng.state()


class AmendTestPlanBody(BaseModel):
    role: str
    story_id: str
    proposal: str


@app.post("/api/runs/{run_id}/delivery-packs/{pack_id}/amend-test-plan")
def post_test_plan_amend(run_id: str, pack_id: str, body: AmendTestPlanBody) -> dict:
    eng = _engine(run_id)
    eng.test_plan_amend(_role(body.role), pack_id, body.story_id, body.proposal)
    return eng.state()


class DeveloperBody(BaseModel):
    role: str
    developer: str


class DemoRerunBody(BaseModel):
    role: str
    story_id: str


@app.post("/api/runs/{run_id}/demo/sync")
def post_demo_sync(run_id: str, body: RoleBody) -> dict:
    eng = _engine(run_id)
    result = eng.demo_sync_advance(_role(body.role))
    return {"result": result, **eng.state()}


@app.post("/api/runs/{run_id}/demo/rerun")
def post_demo_rerun(run_id: str, body: DemoRerunBody) -> dict:
    eng = _engine(run_id)
    result = eng.demo_rerun_story(_role(body.role), body.story_id)
    return {"result": result, **eng.state()}


@app.post("/api/runs/{run_id}/workspaces/sync-git")
def post_workspaces_sync_git(run_id: str, body: RoleBody) -> dict:
    eng = _engine(run_id)
    eng.workspaces_sync_git(_role(body.role))
    return eng.state()


@app.patch("/api/runs/{run_id}/workspaces/{workspace_id}/developer")
def patch_workspace_developer(
    run_id: str, workspace_id: str, body: DeveloperBody
) -> dict:
    eng = _engine(run_id)
    eng.workspace_assign_developer(_role(body.role), workspace_id, body.developer)
    return eng.state()


class OverrideDependencyBody(BaseModel):
    role: str
    reason: str


@app.post("/api/runs/{run_id}/workspaces/{story_id}/override-dependency")
def post_workspace_override_dependency(
    run_id: str, story_id: str, body: OverrideDependencyBody
) -> dict:
    eng = _engine(run_id)
    eng.workspace_override_dependency(_role(body.role), story_id, body.reason)
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


@app.post("/api/runs/{run_id}/release/document")
def post_release_document(run_id: str, body: RoleBody) -> dict:
    eng = _engine(run_id)
    eng.release_document_generate(_role(body.role))
    return eng.state()


@app.get("/api/runs/{run_id}/release/document.html")
def get_release_document_html(run_id: str) -> FileResponse:
    eng = _engine(run_id)
    path = eng.store.path("release", "release-document.html")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Document not generated yet")
    return FileResponse(path, media_type="text/html")


@app.get("/api/runs/{run_id}/release/document.md")
def get_release_document_md(run_id: str) -> FileResponse:
    eng = _engine(run_id)
    path = eng.store.path("release", "release-document.md")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Document not generated yet")
    return FileResponse(
        path, media_type="text/markdown",
        filename=f"release-document-{run_id}.md",
    )


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

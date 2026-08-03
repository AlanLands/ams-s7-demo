"""S7 delivery console — HTTP layer.

Thin on purpose. Every rule that matters (the gate blocking story breakdown,
what an artifact's provenance is) lives in `s7_delivery/pipeline.py`, so it
cannot be bypassed by calling a different endpoint. This module only translates
HTTP to that module and back.

Run it with `demo/run_console.sh`, or:

    uvicorn apps.console.server:app --reload

State is held in memory for a single presenter. That is deliberate for a demo:
no database to seed, and `POST /api/reset` returns it to a known state between
rehearsals.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from s7_delivery.models import ReviewGate
from s7_delivery.pipeline import (
    PipelineError,
    build_state,
    decide,
    initial_gate,
    load_epic,
    to_payload,
)

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(
    title="S7 Delivery Console",
    description="AI-assisted SDLC: epic -> assessment -> design -> review gate -> stories.",
)


class _GateState:
    """The presenter's current review decision.

    Guarded by a lock because uvicorn may serve the reset and the poll from
    different threads, and a half-updated gate is exactly the kind of thing that
    misbehaves once in five demos.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._gate: ReviewGate | None = None

    def get(self) -> ReviewGate:
        with self._lock:
            if self._gate is None:
                self._gate = initial_gate(load_epic().epic.id)
            return self._gate

    def set(self, gate: ReviewGate) -> ReviewGate:
        with self._lock:
            self._gate = gate
            return gate

    def reset(self) -> ReviewGate:
        with self._lock:
            self._gate = initial_gate(load_epic().epic.id)
            return self._gate


_state = _GateState()


class GateRequest(BaseModel):
    decision: str = Field(description="'approved' or 'rejected'")
    reviewer: str = Field(
        description="Who decided. Required — an unattributed gate is a rubber stamp."
    )
    comment: str = ""


def _payload() -> dict[str, Any]:
    return to_payload(build_state(_state.get()))


@app.exception_handler(PipelineError)
async def _pipeline_error_handler(_request: Any, exc: PipelineError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.get("/api/run")
def get_run() -> dict[str, Any]:
    """The complete pipeline state. The console renders entirely from this."""
    return _payload()


@app.post("/api/gate")
def post_gate(request: GateRequest) -> dict[str, Any]:
    """Record the human review decision.

    Approval is what unlocks story breakdown; rejection deliberately leaves it
    locked, so the demo can show the gate actually changing the outcome.
    """
    try:
        gate = decide(
            _state.get().epic_id,
            decision=request.decision,
            reviewer=request.reviewer,
            comment=request.comment,
        )
    except PipelineError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _state.set(gate)
    return _payload()


@app.post("/api/reset")
def post_reset() -> dict[str, Any]:
    """Return the gate to pending — the between-rehearsals reset."""
    _state.reset()
    return _payload()


# Mounted last so the API routes above win. `html=True` serves index.html at /.
if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="console")

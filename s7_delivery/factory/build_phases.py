"""Build & Review phase machine (implementation plan §6, §15.1).

The phase gates the ordering of the *new* Build & Review capabilities —
architecture generation → acceptance → delivery packs → publication →
developer execution — while per-entity state (task status, review result,
pack publication status) stays on the entity records. Invalid transitions
raise `PhaseError`, which the engine surfaces as an `EngineError` (HTTP 409).

Reads never write: a run signed off before this module existed has no
`build/phase.json`, and `read_phase` derives `gate1_approved` from
`run.plan_locked` in memory. The file is only written by `advance`.

Back-edges are deliberate: `architecture_revise` is legal from any phase at or
after `architecture_ready` — the phase drops back to `architecture_ready`
(re-acceptance required) and staleness marks downstream artifacts, but task
and review records are untouched.
"""

from __future__ import annotations

from s7_delivery.factory.models import BuildReviewPhase, now_iso
from s7_delivery.factory.store import RunStore

PHASE_SEGMENTS = ("build", "phase.json")

_P = BuildReviewPhase

# Phases at or after which a capability is available. Order is definitional.
ORDER: tuple[BuildReviewPhase, ...] = (
    _P.GATE1_APPROVED,
    _P.ARCHITECTURE_READY,
    _P.ARCHITECTURE_ACCEPTED,
    _P.DELIVERY_PACKS_READY,
    _P.WORKSPACES_READY,
    _P.DEVELOPER_EXECUTION,
    _P.BUILD_COMPLETE,
)

# from-phase -> set of legal to-phases. `None` = pre-G1 (no phase yet).
ALLOWED: dict[BuildReviewPhase | None, set[BuildReviewPhase]] = {
    None: {_P.GATE1_APPROVED},
    _P.GATE1_APPROVED: {_P.ARCHITECTURE_READY},
    # regenerate (self) or accept
    _P.ARCHITECTURE_READY: {_P.ARCHITECTURE_READY, _P.ARCHITECTURE_ACCEPTED},
    _P.ARCHITECTURE_ACCEPTED: {_P.DELIVERY_PACKS_READY, _P.ARCHITECTURE_READY},
    _P.DELIVERY_PACKS_READY: {
        _P.DELIVERY_PACKS_READY,  # regenerate packs
        _P.WORKSPACES_READY,
        _P.ARCHITECTURE_READY,  # revision back-edge
    },
    _P.WORKSPACES_READY: {
        _P.WORKSPACES_READY,  # further publications
        _P.DEVELOPER_EXECUTION,
        _P.DELIVERY_PACKS_READY,
        _P.ARCHITECTURE_READY,
    },
    _P.DEVELOPER_EXECUTION: {
        _P.DEVELOPER_EXECUTION,
        _P.BUILD_COMPLETE,
        _P.ARCHITECTURE_READY,
    },
    _P.BUILD_COMPLETE: {_P.ARCHITECTURE_READY},
}


class PhaseError(Exception):
    """An out-of-order Build & Review action."""


def read_phase(store: RunStore, *, plan_locked: bool) -> BuildReviewPhase | None:
    """Current phase; derived (never persisted) for pre-module runs."""
    payload = store.read_json_or(None, *PHASE_SEGMENTS)
    if payload and payload.get("phase"):
        return BuildReviewPhase(payload["phase"])
    return _P.GATE1_APPROVED if plan_locked else None


def history(store: RunStore) -> list[dict]:
    payload = store.read_json_or(None, *PHASE_SEGMENTS)
    return list(payload.get("history", [])) if payload else []


def at_least(current: BuildReviewPhase | None, floor: BuildReviewPhase) -> bool:
    """True when `current` is `floor` or later in `ORDER`."""
    if current is None:
        return False
    return ORDER.index(current) >= ORDER.index(floor)


def require_at_least(
    current: BuildReviewPhase | None, floor: BuildReviewPhase, action: str
) -> None:
    if not at_least(current, floor):
        have = current.value if current else "pre-G1 (plan not signed)"
        raise PhaseError(
            f"{action} requires phase '{floor.value}' or later; run is at '{have}'"
        )


def advance(
    store: RunStore,
    current: BuildReviewPhase | None,
    to: BuildReviewPhase,
    *,
    actor: str = "",
) -> None:
    """Persist a validated transition. Self-transitions are recorded too —
    a regeneration is an event worth seeing in the history."""
    if to not in ALLOWED.get(current, set()):
        have = current.value if current else "pre-G1 (plan not signed)"
        raise PhaseError(f"Illegal Build & Review transition: '{have}' → '{to.value}'")
    hist = history(store)
    hist.append({"phase": to.value, "at": now_iso(), "actor": actor})
    store.write_json({"phase": to.value, "history": hist}, *PHASE_SEGMENTS)

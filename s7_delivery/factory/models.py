"""Typed contracts for the governed delivery factory.

Pydantic here (vs the frozen dataclasses in `s7_delivery.models`) because these
objects round-trip through JSON files under `artifacts/runs/` and through the
Control Centre API, and validation at those boundaries is the point. The
pipeline dataclasses stay authoritative for the upstream stages; ids used here
(EPIC-S7-001, story/task/AC ids) refer to the same artifacts.

Provenance discipline: everything the Control Centre displays carries a
`provenance` label. `SIMULATED` is this layer's addition — deterministic
evidence produced by the simulation engine, badged as such wherever shown.
A simulated artifact presented as live AI output is the one failure that
loses the room (CLAUDE.md § Staged output).
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class Provenance(StrEnum):
    HUMAN = "human"
    LIVE_AI = "live_ai"
    REPLAYED_AI = "replayed_ai"
    STAGED = "staged"
    SIMULATED = "simulated"
    # A real, deterministic, non-AI parse of real input (CLAUDE.md § Staged
    # output) — neither fabricated (SIMULATED/STAGED) nor a model call
    # (LIVE_AI/REPLAYED_AI). Used by the rule-based intake extraction parser.
    RULE_BASED = "rule_based"


class DemoMode(StrEnum):
    SIMULATION = "simulation"
    REPLAY = "replay"
    LIVE = "live"


class Status(StrEnum):
    """Statuses for stages, tasks, checks and artifacts (spec §3)."""

    NOT_STARTED = "not_started"
    PLANNED = "planned"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    WAITING_INPUT = "waiting_for_input"
    WAITING_APPROVAL = "waiting_for_approval"
    BLOCKED = "blocked"
    FAILED = "failed"
    PASSED = "passed"
    COMPLETED = "completed"
    STALE = "stale"
    INVALIDATED = "invalidated"


class Stage(StrEnum):
    INTAKE = "intake"
    PLANNING = "planning"
    BUILD_REVIEW = "build_review"
    QUALITY = "quality"
    RELEASE = "release"


STAGE_ORDER: tuple[Stage, ...] = (
    Stage.INTAKE,
    Stage.PLANNING,
    Stage.BUILD_REVIEW,
    Stage.QUALITY,
    Stage.RELEASE,
)


class Role(StrEnum):
    BUSINESS_OWNER = "business_owner"
    DELIVERY_LEAD = "delivery_lead"
    PRODUCT_ANALYST = "product_analyst"
    ENGINEERING_LEAD = "engineering_lead"
    QA_LEAD = "qa_lead"
    INDEPENDENT_REVIEWER = "independent_reviewer"
    RELEASE_MANAGER = "release_manager"
    SUPPORT_LEAD = "support_lead"


class GateId(StrEnum):
    INTAKE = "G0"
    PLAN_SIGNOFF = "G1"
    INDEPENDENT_REVIEW = "G2"
    QUALITY = "G3"
    RELEASE = "G4"


# --- intake ----------------------------------------------------------------


class Requirement(BaseModel):
    request_id: str
    title: str
    business_owner: str
    domain: str
    priority: str
    requested_date: str
    target_release: str
    description: str
    source_type: str
    source_documents: list[str] = []
    provenance: Provenance = Provenance.HUMAN


class RepoRecord(BaseModel):
    """A connected target repository — cloned at connect time, then local."""

    url: str
    name: str
    head_sha: str
    default_branch: str
    file_count: int
    cloned_at: str = Field(default_factory=now_iso)
    provenance: Provenance = Provenance.HUMAN


class RoutingVerdict(BaseModel):
    """Whether a requirement fits the connected repos, or needs a new one."""

    verdict: str  # "routable" | "new_application_needed"
    reasoning: str
    candidate_repos: list[str] = []
    confidence: int | None = None
    overridden_by: str = ""
    overridden_at: str = ""
    provenance: Provenance = Provenance.SIMULATED


class IntakeAnalysis(BaseModel):
    problem_understood: bool
    business_impact: str
    affected_applications: list[str]
    stakeholders: list[str]
    dependencies: list[str]
    risks: list[str]
    clarification_questions: list[str]
    assumptions: list[str]
    # Extracted business rules and a severity-rated risk register (customer
    # wireframe sheet, panels 1 and 5). Simulated like the rest of the analysis.
    business_rules: list[dict] = []
    risk_register: list[dict] = []
    confidence: int | None = None
    provenance: Provenance = Provenance.SIMULATED
    generated_at: str = Field(default_factory=now_iso)


class EpicRecord(BaseModel):
    epic_id: str
    title: str
    business_outcome: str
    estimated_stories: int
    status: Status
    created_by: str
    created_at: str = Field(default_factory=now_iso)
    provenance: Provenance = Provenance.SIMULATED


class RequirementExtraction(BaseModel):
    """The upload/paste intake front door's output — title, objective,
    summary and numbered requirement bullets pulled from real source text.
    `method` is "rule_based" (simulation) or "live_llm" (live mode); the UI
    labels each honestly and never calls the rule-based path "AI"."""

    epic_title: str
    business_objective: str
    requirement_summary: str
    extracted_requirements: list[dict]  # [{"rule_id": "REQ-01", "text": "..."}]
    method: str
    provenance: Provenance
    generated_at: str = Field(default_factory=now_iso)
    edited_by: str | None = None
    edited_at: str | None = None


# --- planning --------------------------------------------------------------


class AcceptanceCriterion(BaseModel):
    ac_id: str
    text: str
    covered_by_code: bool = False
    covered_by_test: bool = False


class FeatureFlag(BaseModel):
    name: str
    default_state: str = "off"


class RollbackPlan(BaseModel):
    method: str
    tested: bool = False


class Story(BaseModel):
    story_id: str
    epic_id: str
    title: str
    purpose: str
    accountable_team: str
    contributing_teams: list[str] = []
    owner: str = ""
    target_application: str
    target_component: str
    target_repository: str
    acceptance_criteria: list[AcceptanceCriterion]
    dependencies: list[str] = []
    impacts: list[str] = []
    feature_flag: FeatureFlag | None = None
    rollback_plan: RollbackPlan | None = None
    task_type: str = "feature"
    estimate: int = 0
    sprint: int = 1
    status: Status = Status.READY
    risk: str = "low"
    version: int = 1
    traces_to: list[str] = []
    provenance: Provenance = Provenance.SIMULATED

    def completeness_gaps(self) -> list[str]:
        """Spec §8E — every story must be complete before Gate 1 can pass."""
        gaps: list[str] = []
        if not self.purpose:
            gaps.append("purpose missing")
        if not self.acceptance_criteria:
            gaps.append("no testable acceptance criteria")
        if not self.accountable_team:
            gaps.append("no accountable team")
        if not self.target_component:
            gaps.append("no target component")
        if self.rollback_plan is None:
            gaps.append("no rollback plan")
        if not self.task_type:
            gaps.append("no task type")
        return gaps


# --- build & review --------------------------------------------------------


class TestCaseRecord(BaseModel):
    test_id: str
    name: str
    ac_id: str
    initial_result: str = "failed"  # test-first: red baseline
    current_result: str = "failed"
    evidence_ref: str = ""


class TaskRecord(BaseModel):
    task_id: str
    story_id: str
    summary: str
    accountable_team: str
    owner: str = ""
    status: Status = Status.NOT_STARTED
    dependencies: list[str] = []
    progress_pct: int = 0
    current_activity: str = ""
    files_changed: int = 0
    lines_added: int = 0
    lines_removed: int = 0
    tests: list[TestCaseRecord] = []
    coverage_pct: int = 0
    change_summary: str = ""
    changed_files: list[str] = []
    commit_ref: str = ""
    pr_ref: str = ""
    ci_status: str = ""
    version: int = 1
    last_activity: str = Field(default_factory=now_iso)
    provenance: Provenance = Provenance.SIMULATED


class BuildReviewPhase(StrEnum):
    """Coarse Build & Review progression (implementation plan §6).

    Gates the *new* capabilities (architecture → packs → publish) in order;
    per-entity states (task status, review result, pack publication status,
    workspace development status) stay on their own records. Absent phase file
    means the run has not passed G1 yet.
    """

    GATE1_APPROVED = "gate1_approved"
    ARCHITECTURE_READY = "architecture_ready"
    ARCHITECTURE_ACCEPTED = "architecture_accepted"
    DELIVERY_PACKS_READY = "delivery_packs_ready"
    WORKSPACES_READY = "workspaces_ready"
    DEVELOPER_EXECUTION = "developer_execution"
    BUILD_COMPLETE = "build_complete"


class ArchitectureMeta(BaseModel):
    """Run-level engineering blueprint metadata. Files live in immutable
    `architecture/v<version>/` directories; this record names the current
    version so a task context referencing v1 stays resolvable after v2."""

    artifact_id: str = "ARCH-001"
    version: int = 1
    status: str = "generated"  # generated | accepted
    generated_at: str = Field(default_factory=now_iso)
    generated_by: str = ""
    accepted_by: str = ""
    accepted_at: str = ""
    revision_note: str = ""
    files: list[str] = []
    provenance: Provenance = Provenance.SIMULATED
    # enrichment (spec 2026-08-09): all derived at render time from real
    # inputs; defaults keep runs stored before this change loading cleanly
    plan_version: int = 0
    content_hash: str = ""  # sha256 over the five files' serialized bytes
    file_sizes: dict[str, int] = {}
    validations: list[dict] = []  # architecture_checks.run_checks output
    landscape: dict = {}  # architecture.landscape output


class DeliveryPack(BaseModel):
    """Per-team governed engineering context (spec §27). References canonical
    artifacts by version — it never copies the canonical architecture tree."""

    delivery_pack_id: str
    run_id: str
    team: str
    team_slug: str
    version: int = 1
    story_ids: list[str] = []
    task_ids: list[str] = []
    architecture_version: int = 1
    plan_version: int = 1
    repository: str = ""
    status: str = "generated"
    publication_status: str = "not_published"  # not_published | published | failed
    published_version: int = 0  # last version that reached the repository
    content_hash: str = ""
    created_at: str = Field(default_factory=now_iso)
    published_at: str = ""
    provenance: Provenance = Provenance.SIMULATED


class DeveloperWorkspace(BaseModel):
    """A human developer's execution surface for one story. S7 provides the
    governed context and collects evidence; the developer owns implementation
    (Human Controlled · AI Assisted)."""

    workspace_id: str
    run_id: str
    team: str
    story_id: str
    repository: str = ""
    branch: str = ""
    developer: str = ""
    delivery_pack_id: str = ""
    delivery_pack_version: int = 1
    base_commit: str = ""
    current_commit: str = ""
    pull_request: str = ""
    ci_status: str = ""
    development_status: str = "provisioned"
    artifact_status: str = "current"  # current | stale
    last_sync_at: str = Field(default_factory=now_iso)
    provenance: Provenance = Provenance.SIMULATED


class GitPublication(BaseModel):
    """One publish of a delivery pack into a developer repository. Canonical
    artifacts always remain in the S7 artifact store — published, not moved.
    `simulated` is the honesty flag: simulation/replay never touch git."""

    publication_id: str
    delivery_pack_id: str
    repository: str
    branch: str
    commit: str = ""
    published_paths: list[str] = []
    status: str = "published"  # published | failed
    simulated: bool = True
    created_at: str = Field(default_factory=now_iso)
    published_at: str = ""
    error_message: str = ""
    provenance: Provenance = Provenance.SIMULATED


class ReviewFinding(BaseModel):
    finding_id: str
    severity: str  # critical | major | minor
    ac_id: str
    summary: str
    detail: str
    # Structured breakdown (wireframe panel 9). Optional — the flat detail
    # remains authoritative when these are empty.
    expected: str = ""
    observed: str = ""
    impact: str = ""
    recommendation: str = ""
    evidence: list[str] = []


class ReviewReport(BaseModel):
    review_id: str
    task_id: str
    reviewer: str
    result: str  # blocked | passed
    critical_gaps: int
    major_gaps: int
    minor_gaps: int
    findings: list[ReviewFinding] = []
    verified_against: list[str] = []
    created_at: str = Field(default_factory=now_iso)
    version: int = 1
    provenance: Provenance = Provenance.SIMULATED


# --- quality ---------------------------------------------------------------


class QualityCheck(BaseModel):
    check_id: str
    name: str
    status: Status
    evidence: str
    owner: str
    completed_at: str = ""
    exception: str = ""


class ExceptionRecord(BaseModel):
    exception_id: str
    description: str
    approved_by: str
    approved_at: str = Field(default_factory=now_iso)


class Risk(BaseModel):
    risk_id: str
    severity: str
    description: str
    status: str = "open"


# --- gates, approvals, release --------------------------------------------


class GateRecord(BaseModel):
    gate_id: GateId
    label: str
    status: Status = Status.NOT_STARTED
    conditions: list[dict] = []
    """[{condition, met, detail}] — the gate is these conditions, not a score."""
    decided_by: str = ""
    decided_at: str = ""
    note: str = ""


class Approval(BaseModel):
    approval_id: str
    subject: str
    role: Role
    approver: str
    decision: str  # approved | rejected
    note: str = ""
    decided_at: str = Field(default_factory=now_iso)


class Deployment(BaseModel):
    deployment_id: str
    environment: str
    pipeline_ref: str
    artifact_count: int
    strategy: str
    status: Status = Status.NOT_STARTED
    smoke_test_status: str = ""
    post_checks: list[str] = []
    deployed_at: str = ""


class SupportHandover(BaseModel):
    support_team: str
    runbook_ref: str
    knowledge_article_ref: str
    monitoring_alerts: list[str]
    escalation_path: str
    known_limitations: list[str]
    hypercare_days: int
    accepted_by: str = ""
    accepted_at: str = ""


# --- governance ------------------------------------------------------------


class ProvenanceRecord(BaseModel):
    event_id: str
    artifact_id: str
    artifact_type: str
    version: int
    sha256: str
    author: str
    timestamp: str = Field(default_factory=now_iso)
    inputs: list[str] = []
    previous_version: int | None = None
    run_id: str
    stage: str
    action: str
    outcome: str


class ActivityEvent(BaseModel):
    timestamp: str = Field(default_factory=now_iso)
    run_id: str
    stage: str
    actor: str
    actor_type: str  # human | service | simulation
    workflow: str = ""
    skill: str = ""
    artifact: str = ""
    duration_s: float = 0.0
    outcome: str = ""
    details: str = ""


class Amendment(BaseModel):
    amendment_id: str
    reason: str
    initiator: str
    affected_artifacts: list[str]
    impact_assessment: str = ""
    required_changes: list[str] = []
    implementation_status: Status = Status.NOT_STARTED
    verification_status: Status = Status.NOT_STARTED
    review_status: Status = Status.NOT_STARTED
    approval: Approval | None = None
    created_at: str = Field(default_factory=now_iso)


class StalenessResult(BaseModel):
    artifact_id: str
    artifact_type: str
    version: int
    status: Status  # STALE or INVALIDATED
    reason: str


# --- run -------------------------------------------------------------------


class StageState(BaseModel):
    stage: Stage
    status: Status = Status.NOT_STARTED
    owner: str = ""
    started_at: str = ""
    completed_at: str = ""


class DeliveryRun(BaseModel):
    run_id: str
    scenario_id: str
    mode: DemoMode = DemoMode.SIMULATION
    status: Status = Status.NOT_STARTED
    created_at: str = Field(default_factory=now_iso)
    stages: list[StageState]
    plan_locked: bool = False
    plan_version: int = 0

    def stage(self, stage: Stage) -> StageState:
        for s in self.stages:
            if s.stage == stage:
                return s
        raise KeyError(stage)


class Scenario(BaseModel):
    scenario_id: str
    title: str
    description: str
    epic_source: str

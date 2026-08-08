export type Provenance =
  | 'human' | 'live_ai' | 'replayed_ai' | 'staged' | 'simulated' | 'rule_based'

export interface ExtractedRequirement {
  rule_id: string
  text: string
}

export interface RequirementExtraction {
  epic_title: string
  business_objective: string
  requirement_summary: string
  extracted_requirements: ExtractedRequirement[]
  method: 'rule_based' | 'live_llm'
  provenance: Provenance
  generated_at: string
  edited_by: string | null
  edited_at: string | null
}

export interface Requirement {
  request_id: string
  title: string
  business_owner: string
  domain: string
  priority: string
  requested_date: string
  target_release: string
  description: string
  source_type: string
  source_documents: string[]
  provenance: Provenance
}

export interface IntakeAnalysis {
  problem_understood: boolean
  business_impact: string
  affected_applications: string[]
  stakeholders: string[]
  dependencies: string[]
  risks: string[]
  clarification_questions: string[]
  assumptions: string[]
  business_rules: { rule_id: string; text: string }[]
  risk_register: Record<string, unknown>[]
  confidence: number | null
  provenance: Provenance
  generated_at: string
}

export interface EpicRecord {
  epic_id: string
  title: string
  business_outcome: string
  estimated_stories: number
  status: string
  created_by: string
  created_at: string
  provenance: Provenance
}

export interface GateCondition {
  condition: string
  met: boolean
  detail: string
}

export interface Gate {
  gate_id: string
  label: string
  status: string
  conditions: GateCondition[]
  decided_by?: string
  decided_at?: string
}

export interface RoutingVerdict {
  verdict: 'routable' | 'new_application_needed'
  reasoning: string
  candidate_repos: string[]
  confidence: number | null
  overridden_by: string
  overridden_at: string
  provenance: Provenance
}

export interface RepoRecord {
  url: string
  name: string
  head_sha: string
  default_branch: string
  file_count: number
  cloned_at: string
  provenance: Provenance
}

export interface SourceRecord {
  text: string
  filename: string | null
  source_kind: 'upload' | 'paste'
  set_at: string
}

export interface ClarificationState {
  pending: string[]
  rounds_used: number
  max_rounds: number
}

export interface NewAppState {
  name?: string
  description?: string
  stack?: string
  pending?: string[]
}

export interface IntakeState {
  requirement?: Requirement
  analysis?: IntakeAnalysis
  epic?: EpicRecord
  extraction?: RequirementExtraction
  source?: SourceRecord
  repos?: RepoRecord[]
  routing?: RoutingVerdict
  clarifications?: ClarificationState
  new_app?: NewAppState
  scaffold?: Record<string, string>
}

export interface StageState {
  stage: string
  status: string
}

export interface RunRecord {
  run_id: string
  mode: 'simulation' | 'replay' | 'live'
  created_at: string
  stages: StageState[]
  status: string
  plan_locked?: boolean
}

export interface TraceRow {
  ac: string
  story?: string
  task?: string
  pr?: string
  tests?: string[]
  review?: string
  review_result?: string
  quality?: string
  deployment?: string
  handover?: string
  requirement?: string
  design?: string
}

export interface ProvenanceRecord {
  artifact_id: string
  artifact_type: string
  version: number
  author: string
  timestamp: string
  stale?: boolean
}

export interface ProvenanceLedgerEntry {
  event_id: string
  artifact_id: string
  artifact_type: string
  version: number
  sha256: string
  author: string
  stage: string
  action: string
  outcome: string
  inputs?: string[]
}

export interface ActivityEvent {
  timestamp: string
  stage: string
  actor: string
  actor_type: string
  artifact?: string
  workflow?: string
  outcome?: string
  details?: string
}

export interface ApprovalRecord {
  approval_id: string
  subject: string
  role: string
  approver: string
  decision: string
  note?: string
  decided_at: string
}

export interface QualityRisk {
  risk_id: string
  severity: string
  description: string
}

export interface QualityCheck {
  check_id: string
  name: string
  status: string
  evidence?: string
  owner: string
}

export interface QualityException {
  exception_id: string
  description: string
  approved_by: string
}

export interface QualityReport {
  checks?: QualityCheck[]
  risks?: QualityRisk[]
  exceptions?: QualityException[]
  quality_score: number
  score_note?: string
  recommendation: string
}

export interface DeploymentRecord {
  status: string
  deployment_id: string
  pipeline_ref: string
  strategy: string
  artifact_count: number
  smoke_test_status: string
  post_checks: string[]
  deployed_at: string
}

export interface HandoverRecord {
  support_team: string
  runbook_ref: string
  knowledge_article_ref: string
  monitoring_alerts: string[]
  escalation_path: string
  known_limitations: string[]
  hypercare_days: number
  accepted_by: string
  accepted_at: string
}

export interface ReleaseRecord {
  release_id: string
  epic_id: string
  version: string
  environment: string
  release_window: string
  feature_flag: string
  rollback_plan: string
  status: string
  deployment?: DeploymentRecord | null
  handover?: HandoverRecord | null
}

export interface StaleArtifact {
  artifact_id: string
  artifact_type: string
  version: number
  reason: string
}

export interface Amendment {
  amendment_id: string
  reason: string
  implementation_status: string
  initiator: string
  impact_assessment: string
  affected_artifacts?: string[]
  required_changes?: string[]
  verification_status: string
}

export interface DesignRecord {
  version: number
}

// --- planning (Epic to Stories / Dependency Map / Routing by Team / Plan
// Summary / Plan Sign-off) --------------------------------------------------
// Canonical shape every planning-stage page reads `data.planning` through.
// Established by consensus across five independently-ported planning pages
// (depGraph.ts's PlanStory, planningHelpers.ts's SignedPlan/PlanConfidence) —
// this promotes those local copies to the shared contract; the pages
// themselves still import from ./depGraph and ./planningHelpers today and can
// be pointed at these instead in a later cleanup pass without any field
// changes, since the shapes are identical.

export interface PlanAcceptanceCriterion {
  ac_id: string
  text: string
  covered_by_code?: boolean
  covered_by_test?: boolean
}

export interface PlanFeatureFlag {
  name: string
  default_state: string
}

export interface PlanRollbackPlan {
  method: string
  tested: boolean
}

export interface PlanStory {
  story_id: string
  epic_id: string
  title: string
  purpose: string
  accountable_team: string
  contributing_teams: string[]
  owner?: string
  target_application: string
  target_component: string
  target_repository: string
  acceptance_criteria: PlanAcceptanceCriterion[]
  dependencies: string[]
  impacts: string[]
  feature_flag: PlanFeatureFlag | null
  rollback_plan: PlanRollbackPlan | null
  task_type: string
  estimate: number
  sprint: number
  status: string
  risk: string
  version?: number
  traces_to?: string[]
  provenance: Provenance
}

export interface SignedPlan {
  plan_version: number
  signed_by: string
  signed_at: string
  note: string
  story_ids: string[]
  story_versions?: Record<string, number>
}

export interface PlanConfidence {
  value: number
  basis: string
  provenance?: Provenance
}

export interface PlanRationale {
  text: string
  provenance?: Provenance
}

export interface PlanningFile {
  name: string
  bytes: number
}

export interface PlanningState {
  plan?: SignedPlan
  stories?: PlanStory[]
  confidence?: PlanConfidence
  rationale?: PlanRationale
}

// --- build (Build Work Queue / Dev Progress / Test Evidence / Independent
// Review) --------------------------------------------------------------------

export interface TaskTestResult {
  test_id: string
  name: string
  ac_id: string
  initial_result: string
  current_result: string
  evidence_ref?: string
}

export interface BuildTask {
  task_id: string
  story_id: string
  status: string
  summary?: string
  owner?: string
  accountable_team?: string
  dependencies?: string[]
  progress_pct: number
  current_activity?: string
  files_changed: number
  lines_added?: number
  lines_removed?: number
  tests?: TaskTestResult[]
  coverage_pct?: number | null
  last_activity?: string
  changed_files?: string[]
  change_summary?: string
  commit_ref?: string
  pr_ref?: string
  version?: number
  provenance?: Provenance
}

export interface ReviewFinding {
  finding_id?: string
  severity: 'critical' | 'major' | 'minor' | 'info'
  ac_id: string
  summary?: string
  expected?: string
  observed?: string
  impact?: string
  recommendation?: string
  evidence?: string[]
  detail?: string
}

export interface ReviewRecord {
  review_id: string
  task_id: string
  reviewer: string
  created_at: string
  verified_against?: string[]
  result: string
  critical_gaps: number
  major_gaps: number
  minor_gaps: number
  findings?: ReviewFinding[]
  version?: number
}

export interface BuildState {
  tasks?: BuildTask[]
  reviews?: ReviewRecord[]
}

export interface RunState {
  run: RunRecord
  scenario?: { title: string; description: string; epic_source: string }
  intake?: IntakeState
  planning?: PlanningState
  build?: BuildState
  gates?: Gate[]
  provenance?: ProvenanceRecord[]
  provenance_ledger?: ProvenanceLedgerEntry[]
  activity?: ActivityEvent[]
  activity_summary?: { counters?: Record<string, number>; total_events?: number; stage_time_s?: Record<string, number> }
  traceability?: TraceRow[]
  approvals?: ApprovalRecord[]
  quality?: QualityReport
  release?: ReleaseRecord
  staleness?: StaleArtifact[]
  amendments?: Amendment[]
  design?: DesignRecord
  [section: string]: unknown
}

export interface RoleInfo {
  role: string
  actions: string[]
}

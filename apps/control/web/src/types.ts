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

export interface AcceptanceCriterion {
  ac_id: string
  text: string
}

export interface StoryRecord {
  story_id: string
  title: string
  purpose?: string
  acceptance_criteria: AcceptanceCriterion[]
  accountable_team?: string
  contributing_teams?: string[]
  target_component?: string
  rollback_plan?: string
  task_type?: string
}

export interface PlanRecord {
  plan_version: number
  story_ids: string[]
}

export interface PlanningState {
  plan?: PlanRecord
  stories?: StoryRecord[]
}

export interface TaskTestResult {
  ac_id: string
  name: string
  current_result: string
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
  files_changed: number
  coverage_pct?: number | null
  tests?: TaskTestResult[]
  last_activity?: string
  changed_files?: string[]
  change_summary?: string
  commit_ref?: string
  pr_ref?: string
  lines_added?: number
  lines_removed?: number
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
  quality?: { risks?: QualityRisk[] }
  staleness?: StaleArtifact[]
  amendments?: Amendment[]
  design?: DesignRecord
  [section: string]: unknown
}

export interface RoleInfo {
  role: string
  actions: string[]
}

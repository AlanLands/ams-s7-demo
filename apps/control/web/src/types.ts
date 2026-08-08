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

export interface RunState {
  run: RunRecord
  scenario?: { title: string; description: string; epic_source: string }
  intake?: IntakeState
  gates?: Gate[]
  provenance?: unknown[]
  activity_summary?: { counters?: Record<string, number>; total_events?: number }
  traceability?: TraceRow[]
  [section: string]: unknown
}

export interface RoleInfo {
  role: string
  actions: string[]
}

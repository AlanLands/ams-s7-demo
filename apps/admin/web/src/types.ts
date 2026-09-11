/** Shapes from docs/admin-api.md — the contract the admin backend
 * (apps/admin/server.py) implements and this UI consumes. */

export type Layer = 'rules' | 'skill' | 'task' | 'playbook'

export interface Overview {
  runs: { total: number; by_mode: Record<string, number> }
  prompt_sets: number
  /** Present once the backend counts delivery profiles: `{count, overlays,
   * legacy_sets}` (the shipped shape) or a bare count. */
  profiles?: number | { count: number; overlays?: number; legacy_sets?: number }
  users: number
  /** Present once the backend counts the known-repositories registry. */
  repositories?: { count: number; run_only?: number }
  llm: { LLM_PROVIDER?: string | null; LLM_MODE?: string | null; effective_mode?: string | null; [k: string]: unknown }
  default_set_unrecorded: string[]
  recent_audit: AuditRow[]
}

export interface SetSummary {
  name: string
  description: string
  cloned_from: string | null
  created_at: string | null
  created_by: string | null
  root: string
  is_default: boolean
  files: number
  counts: { rules: number; skill: number; task: number; playbook: number }
  unrecorded: string[]
  versions: number
}

export interface FileRow {
  id: string
  layer: Layer
  title: string
  stage: string
  summary: string
  path: string
  sha256: string
  short: string
  body: string
  variables: string[]
  version: number
  recorded: boolean
  recorded_at: string | null
  workflows: string[]
}

export interface LedgerLine {
  recorded_at: string
  id: string
  layer: string
  path: string
  version: number
  sha256: string
  previous_sha256: string | null
  author: string
  note: string
}

export interface VersionLine extends LedgerLine {
  /** Absent on the profile routes — treated as true. */
  has_body?: boolean
}

export interface FileDetail extends FileRow {
  versions: VersionLine[]
  placeholders: string[]
  recordings_pinned: number
}

export interface Workflow {
  id: string
  label: string
  entry: string
  stage: string
  gate: string
  rules: string
  skills: string[]
  simulation: string
  live: string
  [k: string]: unknown
}

export interface SetDetail extends SetSummary {
  rules: FileRow[]
  skills: FileRow[]
  tasks: FileRow[]
  playbooks: FileRow[]
  workflows: Workflow[]
}

export interface WorkflowPreview extends Workflow {
  system_prompt: string
  tasks: { id: string; title: string; variables: string[]; body: string }[]
  /** `{provider?, model?}` per the contract; the backend may key it by stage. */
  llm: { provider?: string | null; model?: string | null } | Record<string, { provider?: string | null; model?: string | null }>
}

export interface SaveResult {
  record: LedgerLine | null
  unchanged: boolean
  file: FileDetail
}

export interface LlmStageRow {
  key: string
  label: string
  group: string
  effective: { provider?: string | null; model?: string | null; [k: string]: unknown }
}

export interface LlmProviderRow {
  provider: string
  configured: boolean
  /** What the provider needs from the environment — a list per the contract, a sentence in practice. */
  needs: string[] | string
  env_model: string | null
}

export interface LlmSettings {
  default?: { provider?: string | null; model?: string | null }
  stages?: Record<string, { provider?: string | null; model?: string | null }>
  llm_mode?: 'live' | 'record' | 'replay' | null
  [k: string]: unknown
}

export interface LlmDescribe {
  settings: LlmSettings
  stages: LlmStageRow[]
  providers: LlmProviderRow[]
  environment: Record<string, unknown>
  providers_available: string[]
  modes: string[]
}

export interface RecordingRow {
  name: string
  provider: string | null
  model: string | null
  lane: string | null
  skill: string | null
  prompt_head: string
  size: number
  modified_at: string
}

export interface Recordings {
  replay_dir: string
  count: number
  total_bytes: number
  items: RecordingRow[]
}

export interface CacheStats {
  cache_dir: string
  count: number
  total_bytes: number
}

export interface RoleRow {
  id: string
  label: string
  summary: string
  signs: string[]
  actions: string[]
  overridden: boolean
}

export interface ActionRow {
  action: string
  group: string
  roles: string[]
  default_roles: string[]
  overridden: boolean
}

export interface RolesOverrides {
  permissions?: Record<string, string[]>
  profiles?: Record<string, { label?: string; summary?: string; signs?: string[] }>
}

export interface RolesPayload {
  roles: RoleRow[]
  actions: ActionRow[]
  overrides: RolesOverrides
}

export interface User {
  id: string
  name: string
  email: string | null
  role: string
  active: boolean
  created_at: string
}

export interface RunRow {
  run_id: string
  mode: string
  entry_mode: string
  prompt_set: string
  /** The delivery profile the run resolves against (same name as prompt_set). */
  profile?: { name: string; kind: ProfileKind } | null
  status: string
  created_at: string
  stages: { stage: string; status: string }[]
  size_bytes: number
  archived: boolean
  archive?: string
}

export interface AuditRow {
  at: string
  actor: string
  action: string
  target: string
  detail: string | Record<string, unknown> | null
  before_sha256: string | null
  after_sha256: string | null
}

/* --- Playbooks (structured editing of the self-healing layer) ------------ */

export type StepKind = 'mechanical' | 'gate'

export interface ActionInfo {
  action: string
  kind: StepKind
  label: string
  description: string
  /** Gate: who normally signs. */
  default_role: string | null
  /** Gate: roles.permitted_roles(action). */
  permitted_roles: string[]
}

export interface PlaybookActions {
  mechanical: ActionInfo[]
  gate: ActionInfo[]
  roles: { id: string; label: string }[]
  change_types: string[]
}

export interface PlaybookStep {
  step_id: string
  kind: StepKind
  action: string
  label: string
  detail?: string
  /** Gate only, required. */
  role?: string
  /** Mechanical only, optional. */
  as_role?: string
}

export interface PlaybookDetail extends FileRow {
  change_type: string
  trigger: string
  stage: string
  steps: PlaybookStep[]
  versions: VersionLine[]
  /** How many runs' self-healing records pin this playbook id. */
  usage: { runs: number; changes: number }
}

export interface PlaybookSaveResult {
  record: LedgerLine | null
  unchanged: boolean
  playbook: PlaybookDetail
}

export interface PlaybookValidation {
  ok: boolean
  problems: string[]
  /** Not in the contract's shape, but the contract names "warn, do not refuse" cases — accept them if sent. */
  warnings?: string[]
}

/* --- Run self-healing (GET /runs/{id}/self-healing, read-only) ----------- */

/** One playbook step as the engine walked it (factory/self_heal.py). Every
 * field beyond step_id/kind/action/label/status is optional here: the
 * contract is what the engine writes today, and the view tolerates less. */
export interface SelfHealStep {
  step_id: string
  kind: StepKind
  action: string
  label: string
  detail?: string | null
  /** Gate: the role that records it. */
  role?: string | null
  /** Mechanical: the role the engine acts as. */
  as_role?: string | null
  status: 'pending' | 'waiting' | 'done' | 'failed' | string
  executed_at?: string | null
  /** Alias some payloads use for executed_at. */
  at?: string | null
  outcome?: string | null
  provenance?: string | null
}

/** An activity-ledger event attributed to a change (artifact == change_id). */
export interface SelfHealEvent {
  timestamp?: string
  at?: string
  stage?: string
  actor?: string
  actor_type?: string
  artifact?: string
  workflow?: string
  outcome?: string
  details?: string
  [k: string]: unknown
}

/** A change record: the human change made after plan lock, the playbook
 * pinned to it, and how far it has run. */
export interface SelfHealChange {
  change_id: string
  change_type?: string
  title?: string
  stage?: string
  playbook_id?: string
  playbook_version?: number
  playbook_sha256?: string
  playbook_recorded?: boolean
  /** Nested form, if a payload sends it instead of the flat fields. */
  playbook?: { id?: string; version?: number; sha256?: string } | null
  initiator?: string
  reason?: string
  created_at?: string
  trigger?: { artifact_id?: string; version?: number } | null
  trigger_artifact?: string
  trigger_version?: number
  scope?: { pack_id?: string | null; story_id?: string | null; pack_version?: number | null } | null
  amendment_id?: string
  impact?: { stale?: string[]; count?: number; assessed_at?: string | null } | null
  stale?: string[]
  steps?: SelfHealStep[]
  status: 'open' | 'completed' | string
  completed_at?: string | null
  waiting_on?: string | null
  blocked_step?: string | null
  done_steps?: number
  events?: SelfHealEvent[]
}

export interface SelfHealPlaybook {
  playbook_id: string
  title?: string
  summary?: string
  change_type?: string
  trigger?: string
  stage?: string
  version?: number
  recorded?: boolean
  sha256?: string
  short?: string
  steps?: PlaybookStep[]
}

export interface SelfHealView {
  provenance: string
  summary: { open?: number; waiting_on_human?: number; completed?: number; failed?: number }
  stale_now?: string[]
  changes?: SelfHealChange[]
  playbooks?: SelfHealPlaybook[]
}

/* --- Observability (cross-run, derived on read, RULE_BASED) -------------- */

export interface ObsStageRow {
  stage: string
  calls: number
  cached: number
  failed: number
  avg_latency_s: number | null
  input_tokens: number | null
  output_tokens: number | null
}

export interface ObsModelRow {
  provider: string | null
  model: string | null
  calls: number
  cached: number
  input_tokens: number | null
  output_tokens: number | null
}

export interface ObsDayRow {
  day: string
  calls: number
  cached: number
  failed: number
}

export interface ObsFailure {
  ts: string
  stage: string | null
  provider: string | null
  model: string | null
  error: string
}

export interface ObsGateRow {
  gate: string
  passed: number
  blocked: number
  pending: number
}

export interface Observability {
  provenance: string
  window: { days: number; from: string; to: string }
  llm: {
    source: string
    calls: number
    live_calls: number
    cached_calls: number
    failed_calls: number
    cache_hit_ratio: number | null
    tokens: { input: number | null; output: number | null; cache_read: number | null; cache_write: number | null }
    cache_read_ratio: number | null
    by_stage: ObsStageRow[]
    by_model: ObsModelRow[]
    by_day: ObsDayRow[]
    recent_failures: ObsFailure[]
  }
  runs: {
    total: number
    by_mode: Record<string, number>
    by_prompt_set: Record<string, number>
    by_status: Record<string, number>
  }
  gates: ObsGateRow[]
  self_healing: {
    changes: number
    completed: number
    open: number
    failed: number
    by_change_type: { change_type: string; count: number; completed: number; avg_steps_done: number | null }[]
    by_playbook_version: { playbook_id: string; version: number | null; count: number }[]
    gates_waiting: { role: string; count: number }[]
  }
  review: {
    tasks_reviewed: number
    first_time_right: number
    first_time_right_ratio: number | null
    returned_to_development: number
  }
  prompts: {
    sets: number
    versions_recorded: number
    unrecorded_default: string[]
    edits_last_window: number
  }
  cost: { value: number | null; reason: string }
}

/* --- Correction learning (admin only; invisible to the Control Centre) --- */

/** One human edit of an artifact, appended by the engine to the run's
 * corrections.jsonl. `learnable` is true only when the original was model
 * output (live_ai / replayed_ai) — correcting a seed or a rule-based
 * rendering is still an edit, but teaching a prompt to reproduce it is not
 * learning. */
export interface Correction {
  correction_id: string
  run_id: string
  prompt_set: string
  timestamp: string
  stage: string
  skill_id: string
  skill: string
  task_id: string
  artifact_id: string
  artifact_type: string
  field: string
  before: unknown
  after: unknown
  original_provenance: string
  learnable: boolean
  author: string
  source: string
}

export interface CorrectionsSummary {
  provenance: string
  total: number
  learnable: number
  by_stage: { stage: string; learnable: number; not_learnable: number; last: string | null }[]
  by_target: { target_id: string; learnable: number; not_learnable: number }[]
  runs: string[]
}

export interface LearningTarget {
  target_id: string
  layer: 'skill' | 'task' | string
  stage: string
  corrections_learnable: number
  corrections_total: number
  proposals_pending: number
  last_correction: string | null
  version: number
}

export interface LearningOverview {
  provenance: string
  corrections: CorrectionsSummary
  proposals: { proposed: number; accepted: number; rejected: number }
  targets: LearningTarget[]
}

export type ProposalStatus = 'proposed' | 'accepted' | 'rejected'

/** Whether the proposal still applies to the file as it is now and, after
 * acceptance, whether committed recordings carry the new text. */
export interface ProposalState {
  file_exists: boolean
  stale: boolean
  current_version?: number
  current_sha256?: string
  re_record: null | 're-recorded' | 'awaiting re-record (LLM_MODE=record)' | string
  old_recordings_pinned?: number | null
}

export interface Proposal {
  proposal_id: string
  prompt_set: string
  target_id: string
  target_layer: 'skill' | 'task' | string
  base_version: number
  base_sha256: string
  corrections: string[]
  revised_body: string
  rationale: string
  learned: string[]
  warnings: string[]
  /** Always a genuine call: there is no simulated proposal. */
  provenance: 'live_ai' | 'replayed_ai' | string
  skill: string
  llm: {
    provider: string | null
    model: string | null
    usage: { input_tokens?: number | null; output_tokens?: number | null; cache_read_tokens?: number | null; cache_write_tokens?: number | null; [k: string]: unknown }
  }
  status: ProposalStatus
  created_at: string
  created_by: string
  note: string
  decided_at: string | null
  decided_by: string | null
  decision_note: string | null
  resulting_version: number | null
  state: ProposalState
}

export interface ProposalDetail extends Proposal {
  /** Unified diff, current → proposed, from the server's difflib. */
  diff: string
}

export interface ProposeBody {
  prompt_set: string
  target_id: string
  correction_ids?: string[]
  days?: number
  learnable_only?: boolean
  note?: string
}

/* --- Delivery profiles (one bundle, seven layers, overlay over default) -- */

export type ProfileKind = 'default' | 'profile' | 'legacy-set'
export type ProfileLayer = 'rules' | 'skill' | 'task' | 'playbook' | 'standard' | 'template' | 'governance' | 'model' | 'identity' | 'integration' | 'asset'
export type ProfileGroupId = 'prompts' | 'standards' | 'templates' | 'governance' | 'models' | 'identity' | 'integrations'
/** Where a resolved file comes from: the committed default set, an
 * override stored in the profile, or a legacy full-copy set. */
export type FileSource = 'default' | 'override' | 'set'

export interface ProfileSummary {
  name: string
  kind: ProfileKind
  description: string
  base: string | null
  created_at: string | null
  created_by: string | null
  root: string
  is_default: boolean
  overlay: boolean
  files: number
  counts: Record<ProfileGroupId, number>
  overridden: string[]
  unrecorded: string[]
  versions: number
  fingerprint: string
}

export interface ProfileFileRow {
  id: string
  layer: ProfileLayer
  title: string
  stage: string
  summary: string
  path: string
  sha256: string
  short: string
  body: string
  /** Assets only: the path this file publishes to under `.s7/assets/`. */
  dest: string
  /** Assets only: the full repository path, e.g. `.s7/assets/db/baseline.sql`. */
  publishes_to: string
  /** `{{variables}}` the workflow supplies; a body may only reference these. */
  variables: string[]
  /** Literal tokens that must survive every edit. */
  locked: string[]
  source: FileSource
  enters_model_call: boolean
  consumers: string[]
  version: number
  recorded: boolean
  recorded_at: string | null
  workflows: string[]
}

export interface ProfileGroup {
  id: ProfileGroupId | string
  label: string
  layers: ProfileLayer[]
  files: ProfileFileRow[]
  overridden: number
}

export interface ProfileDetail extends ProfileSummary {
  groups: ProfileGroup[]
  workflows: Workflow[]
  history: LedgerLine[]
}

export interface ImpactArtifact {
  artifact: string
  kind: string
  artifact_version: number | string | null
  pinned: string
  stale: boolean
}

export interface ImpactRun {
  run_id: string
  artifacts: ImpactArtifact[]
  would_go_stale: string[]
}

/** What an edit to a file would touch — from files and run ledgers, never guessed. */
export interface Impact {
  profile: string
  file_id: string
  layer: ProfileLayer
  source: FileSource
  current: string
  enters_model_call: boolean
  recordings_pinned: number
  re_record_needed: boolean
  consumers: string[]
  runs: ImpactRun[]
}

export interface ProfileFileDetail {
  file: ProfileFileRow
  versions: VersionLine[]
  placeholders: string[]
  recordings_pinned: number
  impact: Impact
}

/** PUT / rollback / revert / create all answer with the file as it now is
 * and the ledger line recorded — null when the server found nothing changed. */
export interface ProfileSaveResult {
  file: ProfileFileRow
  version: LedgerLine | null
}

export interface ProfileNewFile {
  layer: ProfileLayer
  id: string
  title: string
  stage: string
  summary: string
  body: string
  variables: string[]
  locked: string[]
  note: string
  /** Assets only — where the file publishes to under `.s7/assets/`. */
  dest?: string
}

/* --- Assets (project artifacts published into the developer's repo) ------ */

export interface NewAsset {
  id: string
  dest: string
  title: string
  summary: string
  body: string
  note: string
  stage?: string
}

export interface AssetBrowseFile {
  path: string
  bytes: number
  importable: boolean
  reason: string
  preview: string
  suggested_id?: string
  suggested_dest?: string
}

export interface AssetBrowseResult {
  repository: string
  ref: string
  subdir: string
  files: AssetBrowseFile[]
  truncated: boolean
  importable: number
}

export interface AssetSelection {
  path: string
  id?: string
  dest?: string
  title?: string
  summary?: string
}

export interface AssetImportResult {
  repository: string
  ref: string
  created: { id: string; path: string }[]
  warnings: { id: string; path: string; warnings: string[] }[]
  files: ProfileFileRow[]
}

/** A created asset, with anything the safety scan wants a human to look at. */
export interface AssetCreateResult extends ProfileSaveResult {
  warnings: string[]
}

/* --- Repositories and the GitHub integration (Operations → Repositories) -- */

/** One run that names the repository in its intake/repos.json. */
export interface RepoRunRef {
  run_id: string
  mode: string
  status: string
  profile: string
  ci_bootstrap_status: string
  default_branch: string
}

/** A known repository: the cross-run registry entry (artifacts/known_repos.json)
 * joined with the runs that use it. `in_registry: false` means a run names
 * it but the registry forgot it — shown as "run only". Extra registry
 * fields (head_sha, cloned_at, file_count, provenance…) pass through. */
export interface RepoRow {
  url: string
  name: string
  kind: 'https' | 'ssh' | 'local' | string
  host: string
  owner: string
  default_branch: string
  ci_bootstrap_status: string
  stack: string
  in_registry: boolean
  runs: RepoRunRef[]
  run_count: number
  /** Newest `repository.test` audit line for the url; null when never probed. */
  last_check: { at: string; reachable: boolean; detail: string } | null
  last_connected_at?: string
  head_sha?: string
  cloned_at?: string
  file_count?: number
  provenance?: string
  [k: string]: unknown
}

export interface RepositoriesPayload {
  provenance: string
  registry_path: string
  repositories: RepoRow[]
}

/** `git ls-remote` on demand — never run by a run, only by an operator. */
export interface RepoTestResult {
  url: string
  reachable: boolean
  default_branch: string
  heads: number
  error: string
  checked_at: string
  kind?: string
  host?: string
  owner?: string
  repo?: string
}

export interface GithubSettings {
  host: string
  allowed_owners: string[]
  allow_local_paths: boolean
  allow_repo_creation: boolean
  refuse_branch_names: string[]
  expected_gh_login: string
}

/** `gh auth status` as the admin sees it: whether a login exists and who it
 * is. No token is ever requested or shown. */
export interface GhStatus {
  available: boolean
  authenticated: boolean
  login: string
  host: string
  error: string
  expected_login: string
  login_matches: boolean | null
  checked_at: string
}

export interface GithubIntegration {
  profile: string
  source: FileSource
  settings: GithubSettings
  gh: GhStatus
  consumers: string[]
}

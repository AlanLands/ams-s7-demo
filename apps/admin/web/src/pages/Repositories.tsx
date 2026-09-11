import { Fragment, useState } from 'react'
import { ChevronDown, ChevronRight, PenLine, Plug, RefreshCw, Trash2 } from 'lucide-react'
import { ApiError, api } from '../api'
import { useLoad, LoadError } from '../hooks'
import { ActionMenu, Badge, Button, Card, ConfirmPanel, Empty, Field, Loading, Notice, PageHeader, SectionHead, TableWrap, fmtTime } from '../components/ui'
import { useAdmin } from '../state/AdminContext'
import { SourceBadge } from './ProfileEditor'
import type { GhStatus, RepoRow, RepoTestResult } from '../types'

/* Repositories — the cross-run known-repositories registry the Control
 * Centre's reconnect chips read, joined with the runs that use each one,
 * plus the GitHub integration layer as a profile resolves it and the gh
 * CLI's own login status. Connecting a repository stays a per-run action
 * in the Control Centre; nothing here clones, pushes or touches a run.
 * Credentials never live in S7 — only whether a gh login exists is shown. */

const GITHUB_FILE = 'github'

/** `bootstrapped:<stack>` / `push_failed` / `unsupported_stack` / '' — the
 * strings `factory/ci_bootstrap.py` writes at connect time. */
function BootstrapBadge({ status }: { status: string }) {
  if (!status) return <Badge variant="neutral" soft label="not bootstrapped" title="No CI bootstrap record — the repository was never connected by a live run" />
  if (status.startsWith('bootstrapped:')) return <Badge variant="success" label="CI bootstrapped" title={`CI workflow pushed for the ${status.split(':', 2)[1]} stack`} />
  if (status === 'push_failed') return <Badge variant="danger" label="bootstrap push failed" title="The CI workflow could not be pushed at connect time" />
  if (status === 'unsupported_stack') return <Badge variant="warning" label="unsupported stack" title="No CI workflow exists for this stack; evidence must arrive another way" />
  return <Badge variant="neutral" label={status.replaceAll('_', ' ')} />
}

function KindBadge({ kind }: { kind: string }) {
  if (kind === 'https') return <Badge variant="info" label="https" />
  if (kind === 'ssh') return <Badge variant="info" label="ssh" />
  if (kind === 'local') return <Badge variant="neutral" label="local path" title="A path on this machine, not a hosted repository" />
  return <Badge variant="neutral" label={kind || 'unknown'} />
}

/* --- GitHub integration ---------------------------------------------------- */

function GhStatusLine({ gh }: { gh: GhStatus }) {
  if (!gh.available) return <span className="chips"><Badge variant="danger" label="gh not on PATH" />{gh.error ? <span className="hint">{gh.error}</span> : null}</span>
  if (!gh.authenticated) return <span className="chips"><Badge variant="danger" label="not authenticated" /><span className="hint">{gh.error || 'gh auth status reported no login'}</span></span>
  return (
    <span className="chips">
      <Badge variant="success" label={gh.login ? `authenticated as ${gh.login}` : 'authenticated'} title={gh.host ? `gh auth status --hostname ${gh.host}` : undefined} />
      {gh.expected_login ? (
        gh.login_matches
          ? <Badge variant="success" soft label="matches expected login" />
          : <Badge variant="warning" label={`expected ${gh.expected_login}`} title="The profile names a different gh login than the one logged in" />
      ) : null}
    </span>
  )
}

function GithubCard({ profiles }: { profiles: string[] }) {
  const { openEditor } = useAdmin()
  const [profile, setProfile] = useState('default')
  const { data, error, loading, reload } = useLoad(() => api.integrations.github(profile).catch((err: unknown) => {
    if (err instanceof ApiError && err.status === 404) return null
    throw err
  }), [profile])

  const s = data?.settings
  return (
    <Card
      title="GitHub integration"
      description="What this profile lets S7 do with the tenant's git hosting, and whether the gh CLI on this machine is logged in. Credentials never live in S7 — only the login's existence and name are shown."
      actions={<>
        <Button variant="secondary" size="sm" icon={<RefreshCw />} onClick={reload} disabled={loading} title="Re-run gh auth status">Check gh</Button>
        <Button variant="secondary" size="sm" icon={<PenLine />} onClick={() => openEditor(profile, GITHUB_FILE)} title={`Open integrations/${GITHUB_FILE} in the profile editor`}>Edit in profile editor</Button>
      </>}
    >
      <div className="form-grid" style={{ marginBottom: 16 }}>
        <Field label="Profile" htmlFor="gh-profile" help="The delivery profile whose integration settings are shown; a run resolves against the profile it was created from.">
          <select id="gh-profile" value={profile} onChange={(e) => setProfile(e.target.value)}>
            {(profiles.length ? profiles : ['default']).map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </Field>
      </div>

      {loading && !data ? <Loading what="Reading the integration settings and gh status" /> : null}
      {error ? <Notice tone="danger" title="Could not read the GitHub integration." actions={<Button variant="secondary" size="sm" onClick={reload}>Retry</Button>}>{error}</Notice> : null}
      {!loading && !error && data === null ? <Empty bare title="Not available on this backend" hint="The integrations route does not resolve on this server." /> : null}

      {data && s ? (
        <div className="kv tight">
          <span className="k">Source</span>
          <span className="v chips"><SourceBadge source={data.source} /><span className="mono hint">integrations/{GITHUB_FILE}</span></span>
          <span className="k">Host</span>
          <span className="v mono">{s.host}</span>
          <span className="k">Allowed owners</span>
          <span className="v chips">
            {s.allowed_owners.length
              ? s.allowed_owners.map((o) => <Badge key={o} variant="info" mono label={o} />)
              : <span className="muted">any owner on {s.host}</span>}
          </span>
          <span className="k">Local paths</span>
          <span className="v">{s.allow_local_paths ? <Badge variant="success" soft label="allowed" /> : <Badge variant="warning" label="refused" title="A run may only connect a hosted repository" />}</span>
          <span className="k">Repo creation</span>
          <span className="v">{s.allow_repo_creation ? <Badge variant="success" soft label="allowed" title="New-application onboarding may run gh repo create" /> : <Badge variant="warning" label="refused" title="New-application repos must be created by hand and connected by URL" />}</span>
          <span className="k">Refused branches</span>
          <span className="v chips">
            {s.refuse_branch_names.length
              ? s.refuse_branch_names.map((b) => <Badge key={b} variant="neutral" mono label={b} />)
              : <span className="muted">none named — publication still refuses the repository's recorded default branch</span>}
          </span>
          <span className="k">Expected login</span>
          <span className="v">{s.expected_gh_login ? <span className="mono">{s.expected_gh_login}</span> : <span className="muted">any authenticated gh login</span>}</span>
          <span className="k">gh status</span>
          <span className="v">
            <GhStatusLine gh={data.gh} />
            <span className="sub">checked {fmtTime(data.gh.checked_at)}</span>
          </span>
          <span className="k">Read by</span>
          <span className="v chips">
            {data.consumers.length ? data.consumers.map((c) => <Badge key={c} variant="neutral" mono label={c} />) : <span className="muted">no consumer declares this file</span>}
          </span>
        </div>
      ) : null}
    </Card>
  )
}

/* --- known repositories --------------------------------------------------- */

function TestResultLine({ result }: { result: RepoTestResult }) {
  if (result.reachable) {
    return (
      <Notice tone="success" title="Reachable.">
        Default branch <span className="mono">{result.default_branch || '(none reported)'}</span>, {result.heads} head{result.heads === 1 ? '' : 's'}
        {result.owner ? <> — <span className="mono">{result.owner}/{result.repo}</span> on <span className="mono">{result.host}</span></> : null}.
        <span className="sub">git ls-remote at {fmtTime(result.checked_at)}; nothing was cloned.</span>
      </Notice>
    )
  }
  return <Notice tone="danger" title="Not reachable.">{result.error || 'git ls-remote reported no error text.'}<span className="sub">checked {fmtTime(result.checked_at)}</span></Notice>
}

/** The newest audited probe of the repository. A repository deleted on its
 * host stays visibly gone here after one Test connection. */
function StatusCell({ check }: { check: RepoRow['last_check'] }) {
  if (!check) return <span className="muted" title="Never probed — Test connection runs git ls-remote">not checked</span>
  const when = `checked ${fmtTime(check.at)}`
  if (check.reachable) {
    return <><Badge variant="success" soft label="reachable" title={when} /><span className="sub">{when}</span></>
  }
  const gone = /not found|does not exist|could not read/i.test(check.detail)
  return (
    <>
      <Badge variant="danger" label={gone ? 'not found' : 'not reachable'} title={check.detail || when} />
      <span className="sub" title={check.detail}>{gone ? 'deleted, renamed or private on the host' : check.detail.slice(0, 60) || 'no error text'} · {when}</span>
    </>
  )
}

function RunsCell({ row, open, onToggle }: { row: RepoRow; open: boolean; onToggle: () => void }) {
  const n = row.run_count ?? row.runs.length
  if (n === 0) return <span className="muted">none</span>
  return (
    <button type="button" className="expand-btn" aria-expanded={open} onClick={onToggle} title={open ? 'Hide runs' : 'Show runs'}>
      {open ? <ChevronDown aria-hidden="true" /> : <ChevronRight aria-hidden="true" />}
      {n} run{n === 1 ? '' : 's'}
    </button>
  )
}

export function RepositoriesPage() {
  const { run, fail, busy } = useAdmin()
  const { data, error, loading, reload } = useLoad(() => api.repositories.list())
  const { data: profileList } = useLoad(() => api.profiles.list().catch(() => []))
  const [openRuns, setOpenRuns] = useState<Record<string, boolean>>({})
  const [testing, setTesting] = useState<string | null>(null)
  const [results, setResults] = useState<Record<string, RepoTestResult>>({})
  const [confirmForget, setConfirmForget] = useState<string | null>(null)

  const profiles = (profileList ?? []).map((p) => p.name)

  const doTest = async (url: string) => {
    setTesting(url)
    try {
      const result = await api.repositories.test(url)
      setResults((r) => ({ ...r, [url]: result }))
      reload() // the probe is audited; the row's status column reads the ledger
    } catch (err) {
      fail(err, 'Test connection')
    } finally {
      setTesting(null)
    }
  }

  const doForget = async (url: string) => {
    const ok = await run(async () => { await api.repositories.forget(url); return true }, 'Forgotten from the registry')
    setConfirmForget(null)
    if (ok) reload()
  }

  const COLS = 8
  const rows = data?.repositories ?? []

  return (
    <>
      <PageHeader
        title="Repositories"
        description={<>
          Repositories are connected per run in the Control Centre, where a run clones them and grounds its analysis on them.
          This page is the cross-run <b>known-repositories registry</b> those reconnect chips read, joined with the runs that use
          each one, plus the GitHub integration a profile allows. Nothing here clones, pushes or touches a run, and credentials
          never live in S7 — the gh CLI's own login is used and only its status is shown.
        </>}
        actions={<Button variant="secondary" size="sm" icon={<RefreshCw />} onClick={reload} disabled={loading}>Refresh</Button>}
      />

      <GithubCard profiles={profiles} />

      <SectionHead
        title="Known repositories"
        description="Every repository a successful connect remembered, newest first, plus any a run still names that the registry forgot (marked run only)."
        right={data ? <Badge variant="neutral" label={data.provenance.toUpperCase().replaceAll('_', ' ')} title="Read from files, derived on read — never an AI output" /> : null}
      />

      {loading && !data ? <Loading what="Reading the registry and the run files" /> : null}
      {error ? <LoadError what="the repositories" error={error} onRetry={reload} /> : null}
      {data && rows.length === 0 ? (
        <Empty title="No repositories yet" hint="Connect one to a run in the Control Centre; every successful connect is remembered here." />
      ) : null}

      {data && rows.length > 0 ? (
        <TableWrap label="Known repositories">
          <table>
            <thead>
              <tr>
                <th>Repository</th><th>Kind</th><th>Default branch</th><th>Stack</th><th>Runs</th><th>Registry</th><th>Status</th>
                <th className="actions-col"><span className="sr-only">Actions</span></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const key = r.url
                const isTesting = testing === key
                const result = results[key]
                // The registry keeps no bootstrap record of its own; the
                // newest run that connected the repository does.
                const boot = r.ci_bootstrap_status || r.runs[0]?.ci_bootstrap_status || ''
                const stack = r.stack || (boot.startsWith('bootstrapped:') ? boot.split(':', 2)[1] : '')
                return (
                  <Fragment key={key}>
                    <tr>
                      <td style={{ minWidth: 240, maxWidth: 420 }}>
                        <b>{r.name || r.url}</b>
                        <span className="sub mono trunc" title={r.url}>{r.url}</span>
                        {r.last_connected_at || r.head_sha ? (
                          <span className="sub">
                            {r.last_connected_at ? `connected ${fmtTime(r.last_connected_at)}` : null}
                            {r.head_sha ? <span className="mono" title={`HEAD at last connect: ${String(r.head_sha)}`}>{r.last_connected_at ? ' · ' : ''}head {String(r.head_sha).slice(0, 8)}</span> : null}
                          </span>
                        ) : null}
                      </td>
                      <td>
                        <KindBadge kind={r.kind} />
                        {r.host || r.owner ? <span className="sub mono">{r.host}{r.owner ? `/${r.owner}` : ''}</span> : null}
                      </td>
                      <td className="mono nowrap">{r.default_branch || <span className="muted">—</span>}</td>
                      <td>
                        {stack ? <span className="mono">{stack}</span> : <span className="muted">—</span>}
                        <span className="sub"><BootstrapBadge status={boot} /></span>
                      </td>
                      <td className="nowrap">
                        <RunsCell row={r} open={Boolean(openRuns[key])} onToggle={() => setOpenRuns((o) => ({ ...o, [key]: !o[key] }))} />
                      </td>
                      <td>
                        {r.in_registry
                          ? <Badge variant="success" soft label="in registry" title="Offered as a reconnect chip in the Control Centre" />
                          : <Badge variant="neutral" label="run only" title="A run names this repository but the registry does not; it is not offered as a reconnect chip" />}
                      </td>
                      <td className="nowrap"><StatusCell check={r.last_check} /></td>
                      <td className="actions-col">
                        <div className="cell-actions">
                          <Button variant="secondary" size="sm" icon={<Plug />} onClick={() => void doTest(key)} busy={isTesting} disabled={testing !== null && !isTesting} title="git ls-remote — reachability and the default branch, nothing cloned">Test connection</Button>
                          <ActionMenu label={`More actions for ${r.name || r.url}`} items={[
                            { label: 'Forget from registry', icon: <Trash2 />, danger: true, disabled: !r.in_registry,
                              title: !r.in_registry
                                ? `Not in the registry — named by ${r.runs.map((x) => x.run_id).join(', ') || 'a run'}; archive or delete those runs (Runs page) to drop it`
                                : undefined,
                              onSelect: () => setConfirmForget(key) },
                          ]} />
                        </div>
                      </td>
                    </tr>
                    {openRuns[key] && r.runs.length > 0 && (
                      <tr className="cor-detail">
                        <td colSpan={COLS}>
                          <ul className="impact-runs" aria-label={`Runs using ${r.name || r.url}`}>
                            {r.runs.map((x) => (
                              <li key={x.run_id}>
                                <span className="mono"><b>{x.run_id}</b></span>
                                <span className="chips">
                                  <Badge variant="neutral" label={x.mode || 'unknown mode'} />
                                  <Badge variant="neutral" mono label={x.profile || 'default'} title="Delivery profile the run resolves against" />
                                  {x.status ? <Badge status={x.status} /> : null}
                                  {x.default_branch ? <span className="hint sm">branch <span className="mono">{x.default_branch}</span></span> : null}
                                  <BootstrapBadge status={x.ci_bootstrap_status} />
                                </span>
                              </li>
                            ))}
                          </ul>
                        </td>
                      </tr>
                    )}
                    {result && (
                      <tr>
                        <td colSpan={COLS} style={{ paddingTop: 0 }}>
                          <TestResultLine result={result} />
                        </td>
                      </tr>
                    )}
                    {confirmForget === key && (
                      <tr className="sel">
                        <td colSpan={COLS} style={{ paddingTop: 0 }}>
                          <ConfirmPanel
                            danger
                            message={<>Forget <b className="mono">{r.url}</b> from the registry? Runs that connected it keep their own record; it stops being offered as a reconnect chip until a run connects it again.</>}
                            confirmLabel="Forget"
                            busy={busy}
                            onConfirm={() => void doForget(key)}
                            onCancel={() => setConfirmForget(null)}
                          />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                )
              })}
            </tbody>
          </table>
        </TableWrap>
      ) : null}

      {data ? (
        <div className="hint" style={{ marginTop: 8 }}>
          Registry <code className="mono">{data.registry_path}</code> — written on every successful connect, gitignored, outliving every run.
          {' '}Connect and remove repositories per run on the Control Centre's Intake page.
        </div>
      ) : null}
    </>
  )
}

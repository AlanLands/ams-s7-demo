import { ArrowRight, Cpu, FileText, GraduationCap, PlayCircle, RefreshCw, Users } from 'lucide-react'
import { ApiError, api } from '../api'
import { useLoad, LoadError } from '../hooks'
import { Badge, Button, Card, Empty, Loading, Notice, PageHeader, SectionHead, StatCard, TableWrap, fmtTime, humanize } from '../components/ui'
import { useAdmin } from '../state/AdminContext'
import type { AuditRow, LearningOverview } from '../types'

/** The correction-learning figures, all time and every set. A 404 (route
 * not on this backend) hides the card rather than showing an error. */
function LearningCard() {
  const { goTo } = useAdmin()
  const { data, error, loading } = useLoad<LearningOverview | null>(() => api.learning.overview().catch((err: unknown) => {
    if (err instanceof ApiError && err.status === 404) return null
    throw err
  }))
  if (loading && !data) return <Card title="Correction learning"><Loading what="Reading the correction ledgers" /></Card>
  if (error) return <Card title="Correction learning"><div className="hint">Could not read the correction ledgers: {error}</div></Card>
  if (!data) return null
  const c = data.corrections
  return (
    <Card title="Correction learning" description="Admin-only: what people corrected, and proposals waiting for a decision. Invisible in the Control Centre."
      actions={<Button variant="ghost" size="sm" icon={<ArrowRight />} onClick={() => goTo('learning')}>Open</Button>}>
      <div className="kv tight">
        <span className="k">Corrections</span><span className="v">{c.total} recorded, <b>{c.learnable}</b> learnable{c.total > 0 && c.learnable === 0 ? <span className="sub">none of a model output — nothing to learn from yet</span> : null}</span>
        <span className="k">Proposals pending</span><span className="v">{data.proposals.proposed}{data.proposals.proposed > 0 ? <span className="sub">awaiting accept or reject</span> : null}</span>
        <span className="k">Decided</span><span className="v">{data.proposals.accepted} accepted, {data.proposals.rejected} rejected</span>
      </div>
      {data.proposals.proposed > 0 ? (
        <div className="btn-row" style={{ marginTop: 12 }}>
          <Button variant="primary" size="sm" icon={<GraduationCap />} onClick={() => goTo('learning')}>Review {data.proposals.proposed} proposal{data.proposals.proposed === 1 ? '' : 's'}</Button>
        </div>
      ) : null}
    </Card>
  )
}

function shortHash(h: string | null | undefined): string {
  return h ? h.slice(0, 8) : '∅'
}

export function AuditTable({ rows, compact }: { rows: AuditRow[]; compact?: boolean }) {
  if (!rows.length) return <Empty title="No audit rows yet" hint="The ledger fills as changes are made here." />
  return (
    <TableWrap label="Audit ledger">
      <table>
        <thead>
          <tr>
            <th>When</th><th>Actor</th><th>Action</th><th>Target</th>
            {!compact && <th>Detail</th>}
            {!compact && <th>Before → after</th>}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={`${r.at}-${i}`}>
              <td className="mono nowrap">{fmtTime(r.at)}</td>
              <td>{r.actor || <span className="muted">—</span>}</td>
              <td><Badge variant="neutral" label={r.action} mono /></td>
              <td className="mono"><span className="trunc" title={r.target || undefined}>{r.target || '—'}</span></td>
              {!compact && (
                <td className="small pre">
                  {r.detail == null ? <span className="muted">—</span> : typeof r.detail === 'string' ? r.detail : JSON.stringify(r.detail)}
                </td>
              )}
              {!compact && (
                <td className="mono nowrap" title={r.before_sha256 || r.after_sha256 ? `${r.before_sha256 ?? '∅'} → ${r.after_sha256 ?? '∅'}` : undefined}>
                  {r.before_sha256 || r.after_sha256 ? `${shortHash(r.before_sha256)} → ${shortHash(r.after_sha256)}` : <span className="muted">—</span>}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </TableWrap>
  )
}

export function Overview() {
  const { goTo, openEditor } = useAdmin()
  const { data, error, loading, reload } = useLoad(() => api.overview())

  const header = (
    <PageHeader
      title="Overview"
      description="The operator surface over the product's configuration plane. Nothing on this page is an AI output — every figure is counted from files."
      actions={<Button variant="secondary" size="sm" icon={<RefreshCw />} onClick={reload} disabled={loading}>Refresh</Button>}
    />
  )

  if (loading && !data) return <>{header}<Loading what="Loading overview" /></>
  if (error) return <>{header}<LoadError what="the overview" error={error} onRetry={reload} /></>
  if (!data) return null

  const modes = Object.entries(data.runs.by_mode ?? {})
  const modeSub = modes.length ? modes.map(([m, n]) => `${m} ${n}`).join(', ') : 'no runs'
  const llmMode = data.llm.effective_mode ?? data.llm.LLM_MODE ?? '—'
  const provider = data.llm.LLM_PROVIDER ?? '—'

  return (
    <>
      {header}

      <div className="stat-row">
        <StatCard icon={<PlayCircle />} value={String(data.runs.total)} label="Runs" sub={modeSub} accent="red" />
        <StatCard icon={<FileText />} value={String(data.prompt_sets)} label="Prompt sets" sub="including default" accent="blue" />
        <StatCard icon={<Users />} value={String(data.users)} label="Users" sub="act-as identities" accent="green" />
        <StatCard icon={<Cpu />} value={String(llmMode)} label="Effective LLM mode" sub={`provider ${provider}`} accent="purple" />
      </div>

      {data.default_set_unrecorded.length > 0 ? (
        <Notice tone="warning" title="Default prompt set has unrecorded changes."
          actions={<Button variant="secondary" size="sm" onClick={() => openEditor('default')}>Open the default set</Button>}>
          <span className="mono">{data.default_set_unrecorded.join(', ')}</span> differ from their last ledger line. The test suite refuses
          an unrecorded file, and committed recordings hash the recorded text — record or roll back before a live or replay run.
        </Notice>
      ) : (
        <Notice tone="success" title="Default prompt set is fully recorded.">Every file matches its last ledger line.</Notice>
      )}

      <div className="grid cols-2" style={{ marginTop: 24 }}>
        <Card title="Runs by mode" actions={<Button variant="ghost" size="sm" icon={<ArrowRight />} onClick={() => goTo('runs')}>Manage runs</Button>}>
          {modes.length === 0 ? <div className="hint">No runs on disk.</div> : (
            <div className="kv tight">
              {modes.map(([m, n]) => (
                <div key={m} style={{ display: 'contents' }}>
                  <span className="k">{humanize(m)}</span><span className="v">{n}</span>
                </div>
              ))}
            </div>
          )}
        </Card>
        <Card title="LLM environment" actions={<Button variant="ghost" size="sm" icon={<ArrowRight />} onClick={() => goTo('llm')}>LLM settings</Button>}>
          <div className="kv tight">
            {Object.entries(data.llm).map(([k, v]) => (
              <div key={k} style={{ display: 'contents' }}>
                <span className="k mono">{k}</span><span className="v mono">{v == null || v === '' ? <span className="muted">—</span> : String(v)}</span>
              </div>
            ))}
          </div>
        </Card>
        <LearningCard />
      </div>

      <SectionHead
        title="Recent audit"
        description="Last 10 rows of config/audit.jsonl"
        right={<Button variant="ghost" size="sm" icon={<ArrowRight />} onClick={() => goTo('audit')}>Full audit</Button>}
      />
      <AuditTable rows={data.recent_audit} compact />
    </>
  )
}

import { useMemo, useState } from 'react'
import { Database, Eraser, HardDrive, RefreshCw, Search } from 'lucide-react'
import { api } from '../api'
import { useLoad, LoadError } from '../hooks'
import { Badge, Button, Card, ConfirmPanel, Empty, Loading, PageHeader, SectionHead, StatCard, TableWrap, fmtBytes, fmtTime } from '../components/ui'
import { useAdmin } from '../state/AdminContext'

export function RecordingsPage() {
  const { run, busy } = useAdmin()
  const rec = useLoad(() => api.recordings())
  const cache = useLoad(() => api.cache.stats())
  const [confirm, setConfirm] = useState(false)
  const [filter, setFilter] = useState('')

  const items = useMemo(() => {
    const all = rec.data?.items ?? []
    const q = filter.trim().toLowerCase()
    if (!q) return all
    return all.filter((r) => [r.name, r.provider, r.model, r.lane, r.skill, r.prompt_head].some((v) => (v ?? '').toLowerCase().includes(q)))
  }, [rec.data, filter])

  const clear = async () => {
    const res = await run(() => api.cache.clear(), undefined)
    setConfirm(false)
    if (res) { cache.reload() }
  }

  return (
    <>
      <PageHeader
        title="Recordings & Cache"
        description="Two stores, two rules: committed replay recordings are a deliverable and are never deleted here; the ephemeral live cache is spend-avoidance and can be cleared."
        actions={<Button variant="secondary" size="sm" icon={<RefreshCw />} onClick={() => { rec.reload(); cache.reload() }} disabled={rec.loading}>Refresh</Button>}
      />

      <div className="stat-row">
        <StatCard icon={<Database />} value={rec.data ? String(rec.data.count) : '—'} label="Committed recordings" sub={rec.data ? fmtBytes(rec.data.total_bytes) : 'loading'} accent="blue" />
        <StatCard icon={<HardDrive />} value={cache.data ? String(cache.data.count) : '—'} label="Ephemeral cache entries" sub={cache.data ? fmtBytes(cache.data.total_bytes) : 'loading'} accent="orange" />
      </div>

      <div className="grid cols-2">
        <Card title="Committed replay recordings" actions={<Badge variant="success" label="Read-only here" />}>
          <div className="kv tight">
            <span className="k">Directory</span><span className="v mono">{rec.data?.replay_dir ?? '—'}</span>
            <span className="k">Env var</span><span className="v mono">LLM_REPLAY_DIR</span>
          </div>
          <p className="hint" style={{ marginTop: 12 }}>
            These let a fresh clone run offline with no API key. A recording is keyed on the full prompt text, so editing a
            prompt file (in the default set) makes its recordings miss until re-recorded with <code>LLM_MODE=record</code>.
            Nothing on this page deletes a recording.
          </p>
        </Card>
        <Card title="Ephemeral live cache" actions={
          <Button variant="danger" size="sm" icon={<Eraser />} onClick={() => setConfirm(true)} disabled={!cache.data || cache.data.count === 0}>Clear cache</Button>
        }>
          <div className="kv tight">
            <span className="k">Directory</span><span className="v mono">{cache.data?.cache_dir ?? '—'}</span>
            <span className="k">Env var</span><span className="v mono">LLM_CACHE_DIR</span>
            <span className="k">Entries</span><span className="v">{cache.data ? `${cache.data.count} (${fmtBytes(cache.data.total_bytes)})` : '—'}</span>
          </div>
          <p className="hint" style={{ marginTop: 12 }}>Live-mode responses cached to avoid paying twice for the same call. Gitignored; safe to clear — the next live call simply pays again.</p>
          {cache.error ? <div className="fld-group"><div className="err">Could not load cache stats: {cache.error}</div></div> : null}
          {confirm && (
            <ConfirmPanel
              danger
              message={<>Remove {cache.data?.count ?? 0} cached live response{cache.data?.count === 1 ? '' : 's'} from <span className="mono">{cache.data?.cache_dir}</span>? Committed recordings are untouched.</>}
              confirmLabel="Clear cache"
              busy={busy}
              onConfirm={clear}
              onCancel={() => setConfirm(false)}
            />
          )}
        </Card>
      </div>

      <SectionHead
        title="Recordings"
        description="Lane is the rules file whose body prefixes the system prompt; skill is the skill whose body follows it."
        right={
          <div className="search-box">
            <Search aria-hidden="true" />
            <input type="search" value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Filter by name, provider, lane, skill…" style={{ width: 300 }} aria-label="Filter recordings" />
          </div>
        }
      />
      {rec.loading && !rec.data ? <Loading what="Loading recordings" /> : null}
      {rec.error ? <LoadError what="recordings" error={rec.error} onRetry={rec.reload} /> : null}
      {rec.data && rec.data.count === 0 ? (
        <Empty title="No committed recordings" hint={<>Record a live run with <code>LLM_MODE=record</code> and commit <span className="mono">{rec.data.replay_dir}</span>.</>} />
      ) : null}
      {rec.data && rec.data.count > 0 ? (
        <>
          <TableWrap label="Committed recordings">
            <table>
              <thead><tr><th>Name</th><th>Provider</th><th>Model</th><th>Lane</th><th>Skill</th><th>Prompt head</th><th className="num">Size</th><th>Modified</th></tr></thead>
              <tbody>
                {items.map((r) => (
                  <tr key={r.name}>
                    <td className="mono"><span className="trunc" title={r.name} style={{ maxWidth: 220 }}>{r.name}</span></td>
                    <td className="mono">{r.provider ?? '—'}</td>
                    <td className="mono">{r.model ?? '—'}</td>
                    <td className="mono">{r.lane ?? '—'}</td>
                    <td className="mono">{r.skill ?? '—'}</td>
                    <td><span className="trunc small" title={r.prompt_head} style={{ maxWidth: 360 }}>{r.prompt_head}</span></td>
                    <td className="num">{fmtBytes(r.size)}</td>
                    <td className="nowrap">{fmtTime(r.modified_at)}</td>
                  </tr>
                ))}
                {items.length === 0 && <tr><td colSpan={8}><Empty bare title="No recordings match" hint="Try a shorter filter — it matches name, provider, model, lane, skill and prompt head." /></td></tr>}
              </tbody>
            </table>
          </TableWrap>
          <div className="table-foot"><span>{items.length} of {rec.data.count} recordings, {fmtBytes(rec.data.total_bytes)} total</span></div>
        </>
      ) : null}
    </>
  )
}

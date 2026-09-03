import { useEffect, useMemo, useRef, useState } from 'react'
import { RefreshCw, Table2 } from 'lucide-react'
import { ApiError, api } from '../api'
import { useLoad, LoadError } from '../hooks'
import { Badge, Button, Card, Empty, Field, Loading, Notice, PageHeader, SectionHead, TableWrap, fmtTime, humanize } from '../components/ui'
import { useAdmin } from '../state/AdminContext'
import type { ObsDayRow, ObsGateRow, Observability } from '../types'

/* Cross-run figures, every one counted from files and derived on read.
 * The rule of the page: a null is a word ("unreported", "not measured"),
 * never a zero — the backend leaves unmeasured things unset rather than
 * inventing them (CLAUDE.md § Determinism), and the UI keeps it that way. */

const WINDOWS = [7, 30, 90] as const

const fmtInt = (n: number | null | undefined): string | null => (n == null ? null : Math.round(n).toLocaleString())
const fmtPct = (r: number | null | undefined): string | null => (r == null ? null : `${Math.round(r * 100)}%`)
const fmtSec = (s: number | null | undefined): string | null => (s == null ? null : `${s < 10 ? s.toFixed(2) : s.toFixed(1)} s`)

/** A value or its honest absence. */
function Val({ v, word = 'unreported' }: { v: string | null; word?: string }) {
  return v == null ? <span className="na">{word}</span> : <>{v}</>
}

/** Stat tile per the data-viz contract: label, value, optional sub-line.
 * A null value renders as the word, smaller and muted, never as 0. */
function Tile({ label, value, sub, word = 'unreported' }: { label: string; value: string | null; sub?: React.ReactNode; word?: string }) {
  return (
    <div className="tile">
      <div className="l">{label}</div>
      <div className={`v${value == null ? ' na' : ''}`}>{value ?? word}</div>
      {sub ? <div className="s">{sub}</div> : null}
    </div>
  )
}

function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null)
  const [w, setW] = useState(720)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const ro = new ResizeObserver((entries) => { for (const e of entries) setW(Math.max(280, Math.floor(e.contentRect.width))) })
    ro.observe(el)
    setW(Math.max(280, Math.floor(el.getBoundingClientRect().width)))
    return () => ro.disconnect()
  }, [])
  return { ref, w }
}

function niceStep(max: number): number {
  if (max <= 0) return 1
  const raw = max / 3
  const p = 10 ** Math.floor(Math.log10(raw))
  const m = raw / p
  const s = m <= 1 ? 1 : m <= 2 ? 2 : m <= 5 ? 5 : 10
  return s * p
}

const SERIES = [
  { key: 'live', label: 'Live', color: 'var(--viz-live)' },
  { key: 'cached', label: 'Cached', color: 'var(--viz-cached)' },
  { key: 'failed', label: 'Failed', color: 'var(--viz-failed)' },
] as const

function split(r: ObsDayRow) {
  const failed = Math.max(0, r.failed ?? 0)
  const cached = Math.max(0, r.cached ?? 0)
  const live = Math.max(0, (r.calls ?? 0) - cached - failed)
  return { live, cached, failed, total: live + cached + failed }
}

/** Stacked columns by day, live / cached / failed. Thin marks (≤ 24px), a
 * 2px surface gap between segments, rounded data-end, hairline grid,
 * a hover tooltip with keyboard focus on every column, and a table twin. */
function CallsByDay({ rows }: { rows: ObsDayRow[] }) {
  const { ref, w } = useWidth<HTMLDivElement>()
  const [hover, setHover] = useState<number | null>(null)
  const [table, setTable] = useState(false)
  const data = useMemo(() => rows.map((r) => ({ ...r, ...split(r) })), [rows])
  const max = Math.max(0, ...data.map((d) => d.total))
  if (!data.length || max === 0) return <Empty bare title="No LLM calls in this window" hint="The telemetry ledger has no rows for these days." />

  const step = niceStep(max)
  const top = Math.ceil(max / step) * step
  const ticks = Array.from({ length: Math.round(top / step) + 1 }, (_, i) => i * step)
  const PAD_L = 44, PAD_R = 12, PAD_T = 16, PLOT_H = 200, AXIS_H = 28
  const H = PAD_T + PLOT_H + AXIS_H
  const plotW = Math.max(40, w - PAD_L - PAD_R)
  const band = plotW / data.length
  const barW = Math.min(24, Math.max(4, band * 0.6))
  const y = (v: number) => PAD_T + PLOT_H - (v / top) * PLOT_H
  const every = data.length <= 10 ? 1 : data.length <= 31 ? 5 : 15
  const labelFor = (i: number) => (i === 0 || i === data.length - 1 || i % every === 0)

  const h = hover != null ? data[hover] : null
  const tipX = hover != null ? PAD_L + band * hover + band / 2 : 0

  return (
    <div className="viz">
      <div className="viz-head">
        <div className="legend" aria-label="Series">
          {SERIES.map((s) => <span key={s.key}><i style={{ background: s.color }} aria-hidden="true" />{s.label}</span>)}
        </div>
        <Button variant="ghost" size="sm" icon={<Table2 />} onClick={() => setTable((t) => !t)} aria-pressed={table}>{table ? 'Hide table' : 'Show table'}</Button>
      </div>
      <div className="colchart" ref={ref}>
        <svg width={w} height={H} viewBox={`0 0 ${w} ${H}`} role="img" aria-label={`LLM calls by day, ${data.length} days, peak ${max} calls`}>
          {ticks.map((t) => (
            <g key={t}>
              <line x1={PAD_L} x2={w - PAD_R} y1={y(t)} y2={y(t)} className={t === 0 ? 'axis' : 'grid'} />
              <text x={PAD_L - 8} y={y(t)} className="tick" textAnchor="end" dominantBaseline="middle">{t.toLocaleString()}</text>
            </g>
          ))}
          {data.map((d, i) => {
            const x = PAD_L + band * i + (band - barW) / 2
            const segs = [
              { key: 'live', v: d.live, color: 'var(--viz-live)' },
              { key: 'cached', v: d.cached, color: 'var(--viz-cached)' },
              { key: 'failed', v: d.failed, color: 'var(--viz-failed)' },
            ].filter((s) => s.v > 0)
            let acc = 0
            const shapes = segs.map((s, k) => {
              const y0 = y(acc), y1 = y(acc + s.v)
              acc += s.v
              const last = k === segs.length - 1
              const gap = k === 0 ? 0 : 2
              const topY = y1, botY = y0 - gap
              const hgt = Math.max(0, botY - topY)
              if (last && hgt >= 4) {
                const r = 4
                const path = `M${x},${botY} L${x},${topY + r} Q${x},${topY} ${x + r},${topY} L${x + barW - r},${topY} Q${x + barW},${topY} ${x + barW},${topY + r} L${x + barW},${botY} Z`
                return <path key={s.key} d={path} fill={s.color} />
              }
              return <rect key={s.key} x={x} y={topY} width={barW} height={hgt} fill={s.color} />
            })
            const label = `${d.day}: ${d.total} call${d.total === 1 ? '' : 's'} — ${d.live} live, ${d.cached} cached, ${d.failed} failed`
            return (
              <g key={d.day}>
                {shapes}
                {labelFor(i) ? <text x={PAD_L + band * i + band / 2} y={PAD_T + PLOT_H + 18} className="tick" textAnchor="middle">{d.day.slice(5)}</text> : null}
                <rect className="hit" x={PAD_L + band * i} y={PAD_T} width={band} height={PLOT_H} fill="transparent" tabIndex={0} role="img" aria-label={label}
                  onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)} onFocus={() => setHover(i)} onBlur={() => setHover(null)}>
                  <title>{label}</title>
                </rect>
              </g>
            )
          })}
        </svg>
        {h ? (
          <div className="tip" style={{ left: tipX, top: y(h.total) - 8 }} role="status">
            <b>{h.day}</b> — {h.total} call{h.total === 1 ? '' : 's'}<br />
            {h.live} live, {h.cached} cached, {h.failed} failed
          </div>
        ) : null}
      </div>
      {table ? (
        <TableWrap label="LLM calls by day" className="viz-table">
          <table>
            <thead><tr><th>Day</th><th className="num">Calls</th><th className="num">Live</th><th className="num">Cached</th><th className="num">Failed</th></tr></thead>
            <tbody>
              {data.map((d) => <tr key={d.day}><td className="mono">{d.day}</td><td className="num">{d.total}</td><td className="num">{d.live}</td><td className="num">{d.cached}</td><td className="num">{d.failed}</td></tr>)}
            </tbody>
          </table>
        </TableWrap>
      ) : null}
    </div>
  )
}

/** Horizontal bars for one measure across categories — single hue, value
 * as text beside every bar. */
function BarList({ rows, label, empty }: { rows: { label: string; value: number }[]; label: string; empty: string }) {
  const max = Math.max(0, ...rows.map((r) => r.value))
  if (!rows.length) return <div className="hint">{empty}</div>
  return (
    <div className="barlist" role="list" aria-label={label}>
      {rows.map((r) => (
        <div key={r.label} role="listitem" className="barlist-row" aria-label={`${r.label}: ${r.value}`}>
          <span className="lb" title={r.label}>{r.label}</span>
          <span className="track" aria-hidden="true"><span className="fill" style={{ width: max ? `${(r.value / max) * 100}%` : 0 }} /></span>
          <span className="n">{r.value.toLocaleString()}</span>
        </div>
      ))}
    </div>
  )
}

const recordRows = (rec: Record<string, number> | undefined, pretty = true) =>
  Object.entries(rec ?? {}).map(([k, v]) => ({ label: pretty ? humanize(k) : k, value: v })).sort((a, b) => b.value - a.value)

const GATE_SERIES = [
  { key: 'passed', label: 'Passed', color: 'var(--viz-passed)' },
  { key: 'pending', label: 'Pending', color: 'var(--viz-pending)' },
  { key: 'blocked', label: 'Blocked', color: 'var(--viz-blocked)' },
] as const

function GateRows({ gates }: { gates: ObsGateRow[] }) {
  if (!gates.length) return <div className="hint">No gate records in this window.</div>
  const max = Math.max(1, ...gates.map((g) => g.passed + g.pending + g.blocked))
  return (
    <>
      <div className="legend" style={{ marginBottom: 12 }} aria-label="Series">
        {GATE_SERIES.map((s) => <span key={s.key}><i style={{ background: s.color }} aria-hidden="true" />{s.label}</span>)}
      </div>
      <div className="gaterow" role="list" aria-label="Gate outcomes">
        {gates.map((g) => {
          const total = g.passed + g.pending + g.blocked
          return (
            <div key={g.gate} role="listitem" className="gaterow-row" aria-label={`${g.gate}: ${g.passed} passed, ${g.pending} pending, ${g.blocked} blocked`}>
              <span className="mono">{g.gate}</span>
              <span className="gbar" aria-hidden="true" style={{ width: `${(total / max) * 100}%` }}>
                {GATE_SERIES.map((s) => g[s.key] > 0 ? <span key={s.key} style={{ flex: g[s.key], background: s.color }} /> : null)}
              </span>
              <span className="n">{g.passed} passed, {g.pending} pending, {g.blocked} blocked</span>
            </div>
          )
        })}
      </div>
    </>
  )
}

type ObsState = { data: Observability | null; missing: boolean }

export function ObservabilityPage() {
  const { goTo } = useAdmin()
  const [days, setDays] = useState<number>(30)
  const [promptSet, setPromptSet] = useState('')
  const sets = useLoad(() => api.promptSets.list())
  const { data: st, error, loading, reload } = useLoad<ObsState>(() => api.observability(days, promptSet).then((data) => ({ data, missing: false })).catch((err: unknown) => {
    if (err instanceof ApiError && err.status === 404) return { data: null, missing: true }
    throw err
  }), [days, promptSet])
  const d = st?.data ?? null

  const header = (
    <PageHeader
      title="Observability"
      description={<>Cross-run figures for the chosen window — counted from files · <span className="mono">RULE_BASED</span>: the telemetry ledger, each run's records and gate files, and the prompt sets' ledgers. Where a source does not report something the figure reads <em>unreported</em> or <em>not measured</em>, never 0. Nothing here is an AI claim.</>}
      actions={<>
        <Badge variant="info" mono label={(d?.provenance ?? 'rule_based').toUpperCase()} title="Derived on read from files" />
        <Button variant="secondary" size="sm" icon={<RefreshCw />} onClick={reload} disabled={loading}>Refresh</Button>
      </>}
    />
  )

  const filters = (
    <div className="filter-row">
      <Field label="Window" htmlFor="obs-days">
        <select id="obs-days" value={days} onChange={(e) => setDays(Number(e.target.value))}>
          {WINDOWS.map((n) => <option key={n} value={n}>Last {n} days</option>)}
        </select>
      </Field>
      <Field label="Prompt set" htmlFor="obs-set">
        <select id="obs-set" value={promptSet} onChange={(e) => setPromptSet(e.target.value)}>
          <option value="">All sets</option>
          {(sets.data ?? []).map((s) => <option key={s.name} value={s.name}>{s.name}{s.is_default ? ' (default)' : ''}</option>)}
        </select>
      </Field>
      {d ? <span className="hint" style={{ paddingBottom: 10 }}>{fmtTime(d.window?.from)} → {fmtTime(d.window?.to)}</span> : null}
    </div>
  )

  if (loading && !st) return <>{header}{filters}<Loading what="Counting" /></>
  if (error) return <>{header}{filters}<LoadError what="observability" error={error} onRetry={reload} /></>
  if (st?.missing || !d) {
    return (
      <>
        {header}{filters}
        <Empty title="Observability is not available on this backend yet"
          hint={<>The admin API answered 404 for <span className="mono">GET /api/admin/observability</span>. Until that route lands, the Overview page still carries run counts and the recent audit.</>}
          action={<div className="btn-row"><Button variant="secondary" size="sm" onClick={reload}>Check again</Button><Button variant="ghost" size="sm" onClick={() => goTo('overview')}>Open the overview</Button></div>} />
      </>
    )
  }

  const llm = d.llm
  const sh = d.self_healing
  const rv = d.review
  const pr = d.prompts
  const tokens = llm.tokens ?? { input: null, output: null, cache_read: null, cache_write: null }

  return (
    <>
      {header}
      {filters}

      <SectionHead title="LLM calls" description={<>From <span className="mono">{llm.source}</span>. A cached call is served from the ephemeral cache or a committed recording; a failed call raised.</>} />
      <div className="tiles">
        <Tile label="Calls" value={fmtInt(llm.calls)} sub={`in ${d.window?.days ?? days} days`} />
        <Tile label="Live / cached" value={`${fmtInt(llm.live_calls) ?? '—'} / ${fmtInt(llm.cached_calls) ?? '—'}`} sub="real network calls / served from cache or recording" />
        <Tile label="Failed" value={fmtInt(llm.failed_calls)} sub={llm.failed_calls ? 'see recent failures below' : 'no call raised'} />
        <Tile label="Cache-hit ratio" value={fmtPct(llm.cache_hit_ratio)} sub="cached calls over all calls" />
        <Tile label="Cache-read ratio" value={fmtPct(llm.cache_read_ratio)} sub={llm.cache_read_ratio == null ? 'the provider did not report cache token counts' : 'cache-read tokens over input + cache-read'} />
      </div>
      <div className="grid cols-2" style={{ marginTop: 16 }}>
        <Card title="Calls by day" description="Stacked live, cached and failed; hover or focus a column for its counts.">
          <CallsByDay rows={llm.by_day ?? []} />
        </Card>
        <Card title="Tokens" description="Summed from what each provider reported — blank when it reported nothing.">
          <div className="kv tight">
            <span className="k">Input</span><span className="v"><Val v={fmtInt(tokens.input)} /></span>
            <span className="k">Output</span><span className="v"><Val v={fmtInt(tokens.output)} /></span>
            <span className="k">Cache read</span><span className="v"><Val v={fmtInt(tokens.cache_read)} /></span>
            <span className="k">Cache write</span><span className="v"><Val v={fmtInt(tokens.cache_write)} /></span>
          </div>
          <div className="section-head" style={{ margin: '20px 0 8px' }}><div><h3>Recent failures</h3><div className="desc">Last {Math.min(10, (llm.recent_failures ?? []).length) || 10}, newest first</div></div></div>
          {(llm.recent_failures ?? []).length === 0 ? <div className="hint">No failed calls in this window.</div> : (
            <ul className="fail-list" aria-label="Recent failures">
              {llm.recent_failures.map((f, i) => (
                <li key={`${f.ts}-${i}`}>
                  <div className="who"><span>{fmtTime(f.ts)}</span>{f.stage ? <Badge variant="neutral" soft label={f.stage} /> : null}<span className="mono">{[f.provider, f.model].filter(Boolean).join(' / ') || '—'}</span></div>
                  <div className="pre small">{f.error}</div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
      <div className="grid cols-2" style={{ marginTop: 16 }}>
        <Card title="By stage" flush>
          {(llm.by_stage ?? []).length === 0 ? <Empty bare title="No calls by stage" /> : (
            <TableWrap label="LLM calls by stage">
              <table>
                <thead><tr><th>Stage</th><th className="num">Calls</th><th className="num">Cached</th><th className="num">Failed</th><th className="num">Avg latency</th><th className="num">In tokens</th><th className="num">Out tokens</th></tr></thead>
                <tbody>
                  {llm.by_stage.map((r) => (
                    <tr key={r.stage}>
                      <td className="mono">{r.stage}</td><td className="num">{r.calls}</td><td className="num">{r.cached}</td><td className="num">{r.failed}</td>
                      <td className="num"><Val v={fmtSec(r.avg_latency_s)} /></td><td className="num"><Val v={fmtInt(r.input_tokens)} /></td><td className="num"><Val v={fmtInt(r.output_tokens)} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
          )}
        </Card>
        <Card title="By model" flush>
          {(llm.by_model ?? []).length === 0 ? <Empty bare title="No calls by model" /> : (
            <TableWrap label="LLM calls by model">
              <table>
                <thead><tr><th>Provider</th><th>Model</th><th className="num">Calls</th><th className="num">Cached</th><th className="num">In tokens</th><th className="num">Out tokens</th></tr></thead>
                <tbody>
                  {llm.by_model.map((r, i) => (
                    <tr key={`${r.provider}/${r.model}/${i}`}>
                      <td>{r.provider ?? <span className="muted">—</span>}</td><td className="mono">{r.model ?? <span className="muted">—</span>}</td>
                      <td className="num">{r.calls}</td><td className="num">{r.cached}</td><td className="num"><Val v={fmtInt(r.input_tokens)} /></td><td className="num"><Val v={fmtInt(r.output_tokens)} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
          )}
        </Card>
      </div>

      <SectionHead title="Runs" description={`${d.runs?.total ?? 0} run${d.runs?.total === 1 ? '' : 's'} on disk, from each run's run.json.`} />
      <div className="grid cols-3">
        <Card title="By mode" compact><BarList label="Runs by mode" rows={recordRows(d.runs?.by_mode)} empty="No runs." /></Card>
        <Card title="By prompt set" compact><BarList label="Runs by prompt set" rows={recordRows(d.runs?.by_prompt_set, false)} empty="No runs." /></Card>
        <Card title="By status" compact><BarList label="Runs by status" rows={recordRows(d.runs?.by_status)} empty="No runs." /></Card>
      </div>

      <SectionHead title="Gates" description="G0 intake through G4 release, from each run's gate records — a gate that blocked for real is counted as blocked." />
      <Card><GateRows gates={d.gates ?? []} /></Card>

      <SectionHead title="Self-healing" description="Change records from governance/self_healing.json — each pins the playbook version it ran." />
      <div className="tiles">
        <Tile label="Changes" value={fmtInt(sh?.changes)} />
        <Tile label="Open" value={fmtInt(sh?.open)} sub="stopped at a gate" />
        <Tile label="Completed" value={fmtInt(sh?.completed)} />
        <Tile label="Failed" value={fmtInt(sh?.failed)} />
      </div>
      <div className="grid cols-3" style={{ marginTop: 16 }}>
        <Card title="By change type" compact flush>
          {(sh?.by_change_type ?? []).length === 0 ? <Empty bare title="No changes" /> : (
            <TableWrap label="Changes by type">
              <table>
                <thead><tr><th>Change type</th><th className="num">Count</th><th className="num">Done</th><th className="num">Avg steps</th></tr></thead>
                <tbody>{sh.by_change_type.map((r) => <tr key={r.change_type}><td className="mono">{r.change_type}</td><td className="num">{r.count}</td><td className="num">{r.completed}</td><td className="num"><Val v={r.avg_steps_done == null ? null : r.avg_steps_done.toFixed(1)} /></td></tr>)}</tbody>
              </table>
            </TableWrap>
          )}
        </Card>
        <Card title="By playbook version" compact flush>
          {(sh?.by_playbook_version ?? []).length === 0 ? <Empty bare title="No playbook pinned" /> : (
            <TableWrap label="Changes by playbook version">
              <table>
                <thead><tr><th>Playbook</th><th className="num">Version</th><th className="num">Changes</th></tr></thead>
                <tbody>{sh.by_playbook_version.map((r, i) => <tr key={`${r.playbook_id}@${r.version}/${i}`}><td className="mono">{r.playbook_id}</td><td className="num">{r.version == null ? <span className="na">unrecorded</span> : `v${r.version}`}</td><td className="num">{r.count}</td></tr>)}</tbody>
              </table>
            </TableWrap>
          )}
        </Card>
        <Card title="Gates waiting, by role" compact>
          <BarList label="Gates waiting by role" rows={(sh?.gates_waiting ?? []).map((g) => ({ label: humanize(g.role), value: g.count }))} empty="No playbook is waiting on a human." />
        </Card>
      </div>

      <SectionHead title="Independent review" description="Review verdicts per task — first-time-right is a task approved on its first review attempt." />
      <div className="tiles">
        <Tile label="First-time-right ratio" value={fmtPct(rv?.first_time_right_ratio)} sub={rv?.tasks_reviewed ? `${rv.first_time_right} of ${rv.tasks_reviewed} reviewed` : 'no task has been reviewed in this window'} />
        <Tile label="Tasks reviewed" value={fmtInt(rv?.tasks_reviewed)} />
        <Tile label="First-time right" value={fmtInt(rv?.first_time_right)} />
        <Tile label="Returned to development" value={fmtInt(rv?.returned_to_development)} />
      </div>

      <SectionHead title="Prompts" description="Prompt sets and their ledgers; edits are ledger lines recorded inside the window, across every set." />
      <div className="tiles">
        <Tile label="Sets" value={fmtInt(pr?.sets)} sub="including default" />
        <Tile label="Versions recorded" value={fmtInt(pr?.versions_recorded)} sub="ledger lines, all time" />
        <Tile label="Edits in window" value={fmtInt(pr?.edits_last_window)} />
        <Tile label="Unrecorded default files" value={fmtInt((pr?.unrecorded_default ?? []).length)} sub={(pr?.unrecorded_default ?? []).length ? <span className="mono">{pr.unrecorded_default.join(', ')}</span> : 'every default file matches its ledger'} />
      </div>
      {(pr?.unrecorded_default ?? []).length ? (
        <div style={{ marginTop: 12 }}>
          <Notice tone="warning" title="Unrecorded default files." actions={<Button variant="secondary" size="sm" onClick={() => goTo('prompt_sets')}>Open prompt sets</Button>}>The test suite refuses these until they are recorded or rolled back.</Notice>
        </div>
      ) : null}

      <SectionHead title="Cost" />
      <Card title="Cost per release" description="A delivery KPI (CLAUDE.md § Metrics) that only counts when it can be evidenced.">
        <div className="cost-na">
          <span className="na big">{d.cost?.value == null ? 'not measured' : String(d.cost.value)}</span>
          <span className="hint">{d.cost?.reason || 'pricing table deliberately empty'}. Token counts above are real where reported; multiplying them by a price this system does not hold would be an invented number.</span>
        </div>
      </Card>
    </>
  )
}

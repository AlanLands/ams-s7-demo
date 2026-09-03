import { useEffect, useMemo, useState } from 'react'
import { apiGet } from '../api'
import { Prov } from '../components/Badge'
import { SectionTitle } from '../components/SectionTitle'
import { useRun } from '../state/RunContext'
import type { DeliverySystem as DeliverySystemPayload, LayerFileRow } from '../types'

/** Governance → Delivery System: the four layers the AI delivery operates
 * as — Rules and Skills as versioned files, the workflow engine, and the two
 * orchestrator surfaces — plus which skill versions actually ran in this
 * run. Everything here is derived from files and the registry (RULE_BASED);
 * nothing on this page is an AI claim about the system. */

const LAYER_CARDS: { key: 'rules' | 'skills' | 'workflows' | 'orchestrator'; title: string; blurb: string }[] = [
  { key: 'rules', title: 'Rules', blurb: 'The stable prefix every model call of a lane starts with. One file per lane, loaded identically.' },
  { key: 'skills', title: 'Skills', blurb: 'One file per stage: the role text that specialises a call. Versioned; the thing an amendment changes.' },
  { key: 'workflows', title: 'Workflows', blurb: 'The engine: role check → gate check → write → provenance append → activity append. Gates are named conditions.' },
  { key: 'orchestrator', title: 'Orchestrator', blurb: 'Two thin surfaces over one engine — the app where a human decides or reads, the CLI where an agent executes.' },
]

// Hashes are case-sensitive identifiers: keep them out of the badge's uppercase.
const CHIP_STYLE = { textTransform: 'none' as const }

function VersionChip({ row }: { row: LayerFileRow }) {
  if (!row.recorded) {
    return <span className="badge st-blocked" style={CHIP_STYLE} title={`content ${row.short} has no ledger line`}>unrecorded · {row.short}</span>
  }
  return <span className="badge st-passed" style={CHIP_STYLE} title={`sha256 ${row.sha256}`}>v{row.version} · {row.short}</span>
}

function LayerTable({ rows, kind }: { rows: LayerFileRow[]; kind: 'rules' | 'skill' }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {[kind === 'rules' ? 'Rules file' : 'Skill', 'Stage', 'Version', 'Used by', 'Text'].map((h) => <th key={h}>{h}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td>
                <div><b>{r.title}</b></div>
                <div className="mono hint">{r.id}</div>
                <div className="hint">{r.summary}</div>
              </td>
              <td>{r.stage}</td>
              <td><VersionChip row={r} /></td>
              <td className="mono">{r.workflows.join(', ') || '—'}</td>
              <td>
                <details>
                  <summary className="hint" style={{ cursor: 'pointer' }}>show verbatim</summary>
                  <pre style={{ whiteSpace: 'pre-wrap', margin: '6px 0 0', fontSize: 12.5, lineHeight: 1.45, maxWidth: 520 }}>{r.body}</pre>
                  <div className="mono hint">{r.path}</div>
                </details>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function DeliverySystem() {
  const { data } = useRun()
  const [sys, setSys] = useState<DeliverySystemPayload | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    apiGet<DeliverySystemPayload>('/api/delivery-system')
      .then((payload) => { if (!cancelled) setSys(payload) })
      .catch((err: Error) => { if (!cancelled) setError(err.message) })
    return () => { cancelled = true }
  }, [])

  // Which skill versions ran in this run — from the activity ledger, where
  // every live call records `id@vN`. Simulation and demo runs make no model
  // call, so the honest answer there is "none".
  const ranHere = useMemo(() => {
    const counts = new Map<string, { n: number; workflows: Set<string> }>()
    for (const ev of data?.activity ?? []) {
      const skill = (ev as { skill?: string }).skill
      if (!skill) continue
      for (const ref of skill.split(',').map((s) => s.trim()).filter(Boolean)) {
        const entry = counts.get(ref) ?? { n: 0, workflows: new Set<string>() }
        entry.n += 1
        if (ev.workflow) entry.workflows.add(ev.workflow)
        counts.set(ref, entry)
      }
    }
    return [...counts.entries()].sort((a, b) => a[0].localeCompare(b[0]))
  }, [data?.activity])

  if (error) {
    return (
      <section>
        <SectionTitle title="Delivery System" />
        <div className="card bad">Could not load the delivery system: {error}</div>
      </section>
    )
  }
  if (!sys) return null

  const counts: Record<string, string> = {
    rules: `${sys.rules.length} files`,
    skills: `${sys.skills.length} files`,
    workflows: `${sys.workflows.length} workflows`,
    orchestrator: `${sys.orchestrator.length} surfaces`,
  }
  const mode = data?.run?.mode ?? 'simulation'

  return (
    <section>
      <div className="section-title">
        <h2>Delivery System — four layers</h2>
        <Prov provenance={sys.provenance} />
      </div>
      <p className="hint">
        Rules, skills, workflows and orchestrator are separated so AI delivery runs as a governed
        engineering system. The first two layers are files in the repository, loaded verbatim into
        every model call and versioned in an append-only ledger; changing them is a recorded
        amendment, not an edit.
      </p>

      {sys.unrecorded.length > 0 && (
        <div className="card warn">
          <b>Unrecorded changes.</b> {sys.unrecorded.join(', ')} differ from their last recorded
          version. Record them before any live run: <code>python -m s7_delivery layers record --note "…"</code>
        </div>
      )}

      <div className="grid cols-4">
        {LAYER_CARDS.map((c) => (
          <div className="card" key={c.key}>
            <div className="card-head"><b>{c.title}</b><span className="hint">{counts[c.key]}</span></div>
            <div className="hint">{c.blurb}</div>
          </div>
        ))}
      </div>

      <SectionTitle
        title="How the layers become a prompt"
        hint="The prompt-prefix convention in common/prompt.py, filled from the layers — most stable first"
      />
      <div className="card">
        <div className="kv">
          {Object.entries(sys.prompt_mapping).map(([slot, meaning]) => (
            <div key={slot} style={{ display: 'contents' }}>
              <b className="mono">{slot}</b>
              <span>{meaning}</span>
            </div>
          ))}
        </div>
      </div>

      <SectionTitle title="Rules layer" hint="Identical for every call of a lane — the cached prefix" />
      <LayerTable rows={sys.rules} kind="rules" />

      <SectionTitle title="Skills layer" hint="One per stage; the role slot of every call" />
      <LayerTable rows={sys.skills} kind="skill" />

      <SectionTitle
        title="Workflows layer"
        hint="Which rules and skill each workflow assembles, the gate that consumes its output, and what each run mode really does"
      />
      <div className="table-wrap">
        <table>
          <thead>
            <tr>{['Workflow', 'Stage', 'Gate', 'Rules', 'Skills', 'In simulation / demo', 'In live / replay'].map((h) => <th key={h}>{h}</th>)}</tr>
          </thead>
          <tbody>
            {sys.workflows.map((wf) => (
              <tr key={wf.id}>
                <td>
                  <div><b>{wf.label}</b></div>
                  <div className="mono hint">{wf.entry}</div>
                </td>
                <td>{wf.stage}</td>
                <td>{wf.gate}</td>
                <td className="mono">{wf.rules}</td>
                <td className="mono">{wf.skills.join(', ') || '—'}</td>
                <td className="hint">{wf.simulation}</td>
                <td className="hint">{wf.live}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="grid cols-4" style={{ marginTop: 12 }}>
        {sys.workflow_engine.map((w) => (
          <div className="card" key={w.where}>
            <div className="mono"><b>{w.where}</b></div>
            <div className="hint">{w.role}</div>
          </div>
        ))}
      </div>

      <SectionTitle title="Orchestrator layer" hint="Neither surface holds logic — both render the same engine" />
      <div className="grid cols-2">
        {sys.orchestrator.map((o) => (
          <div className="card" key={o.surface}>
            <div className="card-head"><b>{o.label}</b><span className="badge st-passed">{o.surface}</span></div>
            <div className="mono hint">{o.where}</div>
            <div>{o.role}</div>
          </div>
        ))}
      </div>

      <SectionTitle
        title="Skill versions that ran in this run"
        hint="From the activity ledger — every live call records id@vN; nothing is inferred"
      />
      {ranHere.length === 0 ? (
        <div className="card">
          <b>None.</b>{' '}
          {mode === 'live' || mode === 'replay'
            ? 'No model-backed workflow has run yet in this run.'
            : `This is a ${mode} run: it makes no model call, so no skill executed. Skills run in live and replay runs only.`}
        </div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead><tr>{['Skill @ version', 'Calls', 'Workflows'].map((h) => <th key={h}>{h}</th>)}</tr></thead>
            <tbody>
              {ranHere.map(([ref, e]) => (
                <tr key={ref}>
                  <td className="mono">{ref}</td>
                  <td>{e.n}</td>
                  <td className="mono">{[...e.workflows].join(', ')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <SectionTitle title="Version ledger" hint="Append-only. A version number exists only because a ledger line issued it." />
      <div className="table-wrap">
        <table>
          <thead><tr>{['Recorded', 'File', 'Layer', 'Version', 'SHA-256', 'Author', 'Note'].map((h) => <th key={h}>{h}</th>)}</tr></thead>
          <tbody>
            {[...sys.history].reverse().map((h, i) => (
              <tr key={`${h.id}-${h.version}-${i}`}>
                <td className="mono">{h.recorded_at}</td>
                <td className="mono">{h.id}</td>
                <td>{h.layer}</td>
                <td>v{h.version}</td>
                <td className="mono" title={h.sha256}>{h.sha256.slice(0, 10)}…</td>
                <td>{h.author || '—'}</td>
                <td className="hint">{h.note}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

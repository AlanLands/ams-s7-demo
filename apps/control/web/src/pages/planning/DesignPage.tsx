import { useEffect, useRef, useState } from 'react'
import mermaid from 'mermaid'
import { Prov } from '../../components/Badge'
import { NotBuilt } from '../../components/NotBuilt'
import { SectionTitle } from '../../components/SectionTitle'
import { useRun } from '../../state/RunContext'

/** The client-named design step: DFD + relationship diagrams rendered from
 * the run's design artifact. Curated MapleSure content in simulation/demo
 * (SIMULATED), a rule-based derivation from the plan in live/replay
 * (RULE_BASED). Mermaid is bundled at build time — no CDN (hard rule 4). */

mermaid.initialize({ startOnLoad: false, securityLevel: 'strict', theme: 'neutral' })

function Diagram({ id, mermaidText }: { id: string; mermaidText: string }) {
  const ref = useRef<HTMLDivElement>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    mermaid.render(`mmd-${id}-${Date.now()}`, mermaidText)
      .then(({ svg }) => {
        if (!cancelled && ref.current) ref.current.innerHTML = svg
      })
      .catch((err: Error) => { if (!cancelled) setError(err.message) })
    return () => { cancelled = true }
  }, [id, mermaidText])

  if (error) {
    return <pre className="mono" style={{ whiteSpace: 'pre-wrap' }}>{mermaidText}</pre>
  }
  return <div ref={ref} style={{ overflowX: 'auto' }} />
}

export function DesignPage() {
  const { data } = useRun()
  if (!data) return null
  const design = data.design
  if (!design) {
    return (
      <section>
        <SectionTitle title="Design" />
        <NotBuilt name="Design" phase="the Planning stage — generate the draft plan first" />
      </section>
    )
  }

  const diagrams = design.diagrams
  const rules = design.rules ?? {}

  return (
    <section>
      <div className="section-title">
        <h2>{design.title ?? 'Design'}</h2>
        <Prov provenance={design.provenance} />
      </div>
      <p className="hint">
        {`${design.design_id ?? 'DES-001'} · v${design.version} — the design step sits between the epic and its stories; the human gate signs off on it with the plan.`}
      </p>
      {diagrams ? (
        <>
          <div className="card" style={{ marginTop: 14 }}>
            <h3>{diagrams.dfd.title}</h3>
            <Diagram id="dfd" mermaidText={diagrams.dfd.mermaid} />
            {diagrams.dfd.notes ? <p className="hint">{diagrams.dfd.notes}</p> : null}
          </div>
          <div className="card" style={{ marginTop: 14 }}>
            <h3>{diagrams.relationship.title}</h3>
            <Diagram id="rel" mermaidText={diagrams.relationship.mermaid} />
            {diagrams.relationship.notes ? <p className="hint">{diagrams.relationship.notes}</p> : null}
          </div>
        </>
      ) : (
        <div className="card" style={{ marginTop: 14 }}>
          <p className="hint">
            This run's design artifact predates diagram support — regenerate the plan to produce them.
          </p>
        </div>
      )}
      {Object.keys(rules).length ? (
        <div className="card" style={{ marginTop: 14 }}>
          <h3>Design decisions</h3>
          <div className="kv" style={{ gridTemplateColumns: '160px 1fr' }}>
            {Object.entries(rules).map(([k, v]) => (
              <span key={k} style={{ display: 'contents' }}>
                <b>{k.replaceAll('_', ' ')}</b><span>{String(v)}</span>
              </span>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  )
}

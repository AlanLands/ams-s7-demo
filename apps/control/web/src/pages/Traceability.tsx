import { useState } from 'react'
import { Badge } from '../components/Badge'
import { NotBuilt } from '../components/NotBuilt'
import { SectionTitle } from '../components/SectionTitle'
import { useRun } from '../state/RunContext'
import type { TraceRow } from '../types'

export function Traceability() {
  const { data } = useRun()
  const [traceSel, setTraceSel] = useState<string | null>(null)
  if (!data) return null

  const rows = (data.traceability as TraceRow[] | undefined) ?? []
  if (!rows.length) {
    return <NotBuilt name="Traceability" phase="the Planning stage — the chain builds as artifacts exist" />
  }

  const selected = rows.find((row) => row.ac === traceSel)

  return (
    <section>
      <SectionTitle
        title="Traceability matrix"
        hint="Requirement → design → story → criterion → task → change → test → review → quality → deployment → handover"
      />
      {selected ? (
        <div className="card highlight" style={{ marginBottom: '14px' }}>
          <h3>Chain for {selected.ac}</h3>
          <p className="mono" style={{ marginTop: '8px' }}>
            {[
              selected.requirement,
              selected.design,
              selected.story,
              selected.ac,
              selected.task,
              selected.pr,
              ...(selected.tests ?? []),
              selected.review,
              selected.quality,
              selected.deployment,
              selected.handover,
            ].filter(Boolean).join(' → ')}
          </p>
        </div>
      ) : null}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              {['Story', 'Criterion', 'Task', 'Change', 'Tests', 'Review', 'Quality', 'Deploy', 'Handover'].map((heading) => (
                <th key={heading}>{heading}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.ac} style={{ cursor: 'pointer' }} onClick={() => setTraceSel(row.ac)}>
                <td className="mono">{row.story}</td>
                <td className="mono">{row.ac}</td>
                <td className="mono">{row.task ?? '—'}</td>
                <td className="mono">{row.pr ?? '—'}</td>
                <td className="mono">{(row.tests ?? []).join(', ') || '—'}</td>
                <td>
                  {row.review ? (
                    <span>
                      <span className="mono">{`${row.review} `}</span>
                      <Badge status={row.review_result === 'passed' ? 'passed' : 'blocked'} />
                    </span>
                  ) : '—'}
                </td>
                <td className="mono">{row.quality ?? '—'}</td>
                <td className="mono">{row.deployment ?? '—'}</td>
                <td className="mono">{row.handover ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

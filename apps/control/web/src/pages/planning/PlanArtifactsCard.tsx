import { useEffect, useState } from 'react'
import { apiGet } from '../../api'
import { useRun } from '../../state/RunContext'
import type { PlanningFile } from '../../types'

const ARTIFACT_DESCRIPTIONS: Record<string, string> = {
  'plan.json': 'Signed plan in machine-readable format',
  'plan.md': 'Human-readable plan',
  'stories.json': 'User stories and details',
  'design.json': 'Design decisions the stories derive from',
  'confidence.json': 'Planning model self-assessment (simulated)',
  'revision-notes.json': 'Requested AI revisions',
}

function downloadPlanningFile(runId: string, name: string) {
  const a = document.createElement('a')
  a.href = `/api/runs/${runId}/planning/files/${name}`
  a.download = name
  document.body.appendChild(a)
  a.click()
  a.remove()
}

export function PlanArtifactsCard({ showDownloadAll = true }: { showDownloadAll?: boolean }) {
  const { data, runId } = useRun()
  const [files, setFiles] = useState<PlanningFile[]>([])
  const locked = data?.run.plan_locked

  useEffect(() => {
    if (!runId) return
    let cancelled = false
    apiGet<PlanningFile[]>(`/api/runs/${runId}/planning/files`)
      .then((f) => { if (!cancelled) setFiles(f) })
      .catch(() => { if (!cancelled) setFiles([]) })
    return () => { cancelled = true }
  }, [runId, data])

  return (
    <div className="card">
      <div className="card-head">
        <h3>{`Plan Artifacts ${locked ? '(Locked on Approval)' : '(Draft)'}`}</h3>
        {showDownloadAll && files.length ? (
          <button
            type="button"
            className="outline"
            onClick={() => files.forEach((f, i) => setTimeout(() => runId && downloadPlanningFile(runId, f.name), i * 250))}
          >
            ⬇ Download All Artifacts
          </button>
        ) : null}
      </div>
      {files.length === 0 ? (
        <p className="hint">No planning artifacts on disk yet — generate the draft plan first.</p>
      ) : (
        <ul className="artifact-list">
          {files.map((f) => (
            <li key={f.name}>
              <span className="file-ico">{f.name.endsWith('.md') ? '▤' : '{}'}</span>
              <div className="file-meta">
                <code>{`planning/${f.name}`}</code>
                <span className="hint">{ARTIFACT_DESCRIPTIONS[f.name] ?? 'Planning artifact'}</span>
              </div>
              <span className="hint mono">{`${Math.max(1, Math.round(f.bytes / 1024))} KB`}</span>
              <button
                type="button"
                className="icon-btn"
                title={`Download ${f.name}`}
                onClick={() => runId && downloadPlanningFile(runId, f.name)}
              >⬇</button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

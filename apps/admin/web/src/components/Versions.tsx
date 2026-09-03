import { useEffect, useState } from 'react'
import { Eye, GitCompare, History } from 'lucide-react'
import { api } from '../api'
import { Badge, Button, Card, ConfirmPanel, Empty, Field, fmtTime } from './ui'
import { useAdmin } from '../state/AdminContext'
import type { FileRow, SaveResult, VersionLine } from '../types'

/* The version ledger, shared by the prompt editor and the playbook editor.
 * A playbook is a layer file, so its timeline, diff and rollback are the
 * file routes with the playbook id — one component, two callers. */

export function VersionChip({ row }: { row: Pick<FileRow, 'recorded' | 'version' | 'short' | 'sha256'> }) {
  if (!row.recorded) return <Badge variant="warning" label="unrecorded" title={`content ${row.short} has no ledger line`} />
  return <Badge variant="success" label={`v${row.version}`} title={`sha256 ${row.sha256}`} />
}

/** Unified diff, one line per row. Colour is never the only signal: each
 * line keeps its +/- glyph in a gutter and a left border. Rendered from
 * the server's own `difflib` output, never recomputed client-side. */
export function DiffView({ text }: { text: string }) {
  if (!text.trim()) return <div className="hint">No differences between these versions.</div>
  return (
    <>
      <div className="diff-legend" aria-hidden="true">
        <span><i className="add">+</i> added</span>
        <span><i className="del">−</i> removed</span>
      </div>
      <div className="diff" role="region" aria-label="Unified diff" tabIndex={0}>
        {text.split('\n').map((ln, i) => {
          let cls = ''
          let glyph = ' '
          let content = ln
          if (ln.startsWith('+++') || ln.startsWith('---')) cls = 'meta'
          else if (ln.startsWith('@@')) cls = 'hunk'
          else if (ln.startsWith('+')) { cls = 'add'; glyph = '+'; content = ln.slice(1) }
          else if (ln.startsWith('-')) { cls = 'del'; glyph = '−'; content = ln.slice(1) }
          else if (ln.startsWith(' ')) content = ln.slice(1)
          return (
            <div key={i} className={`ln ${cls}`}>
              <span className="g">{glyph}</span>
              <span className="c">{content || ' '}</span>
            </div>
          )
        })}
      </div>
    </>
  )
}

/** Timeline newest first; pick two → unified diff; view a body; roll back
 * in its own panel with a note. Rolling back records a new version. */
export function VersionsCard({ set, id, version, recorded, versions, onApplied }: {
  set: string
  id: string
  version: number
  recorded: boolean
  versions: VersionLine[]
  onApplied: (res: SaveResult, verb: string) => void
}) {
  const { run, busy } = useAdmin()
  const [pick, setPick] = useState<number[]>([])
  const [diff, setDiff] = useState<{ from: number; to: number; diff: string } | null>(null)
  const [rollbackTo, setRollbackTo] = useState<number | null>(null)
  const [rollbackNote, setRollbackNote] = useState('')
  const [viewVersion, setViewVersion] = useState<{ version: number; body: string } | null>(null)

  useEffect(() => { setPick([]); setDiff(null); setRollbackTo(null); setViewVersion(null) }, [set, id, version])

  const togglePick = (v: number) => {
    setDiff(null)
    setPick((p) => p.includes(v) ? p.filter((x) => x !== v) : [...p, v].slice(-2))
  }
  const showDiff = async () => {
    if (pick.length !== 2) return
    const [a, b] = [...pick].sort((x, y) => x - y)
    const res = await run(() => api.promptSets.diff(set, id, a, b))
    if (res) { setViewVersion(null); setDiff(res) }
  }
  const doRollback = async () => {
    if (rollbackTo == null || !rollbackNote.trim()) return
    const res = await run(() => api.promptSets.rollback(set, id, rollbackTo, rollbackNote.trim()))
    if (res) { onApplied(res, `rolled back to v${rollbackTo}, recorded`); setRollbackTo(null); setRollbackNote('') }
  }
  const peek = async (v: number) => {
    const res = await run(() => api.promptSets.version(set, id, v))
    if (res) { setDiff(null); setViewVersion(res) }
  }

  const sorted = [...versions].sort((a, b) => b.version - a.version)

  return (
    <Card
      title="Versions"
      description="Append-only ledger, newest first. Select two versions to compare; rolling back records a new version rather than rewriting history."
      actions={<Button variant="secondary" size="sm" icon={<GitCompare />} onClick={showDiff} disabled={pick.length !== 2}>
        {pick.length === 2 ? `Compare v${Math.min(...pick)} → v${Math.max(...pick)}` : 'Compare selected'}
      </Button>}
    >
      {sorted.length === 0 ? <Empty bare title="No ledger lines yet" hint="This file has never been recorded — save it with a note to record v1." /> : (
        <ol className="timeline" aria-label="Version history">
          {sorted.map((v) => {
            const isCurrent = v.version === version && recorded
            return (
              <li key={v.version} className={isCurrent ? 'current' : ''}>
                <input type="checkbox" aria-label={`Select v${v.version} to compare`} checked={pick.includes(v.version)} onChange={() => togglePick(v.version)} disabled={!v.has_body && !pick.includes(v.version)} title={v.has_body ? undefined : 'No body recorded for this version'} />
                <span className="ver">v{v.version}{isCurrent ? <span className="sub">current</span> : null}</span>
                <div>
                  <div className="note">{v.note || <span className="muted">No note</span>}</div>
                  <div className="who">
                    <span>{v.author || '—'}</span>
                    <span>{fmtTime(v.recorded_at)}</span>
                    <span className="mono sm" title={v.sha256}>{v.sha256.slice(0, 10)}</span>
                  </div>
                </div>
                <div className="cell-actions">
                  <Button variant="ghost" size="sm" icon={<Eye />} onClick={() => peek(v.version)} disabled={!v.has_body}>View</Button>
                  <Button variant="ghost" size="sm" icon={<History />} onClick={() => { setRollbackTo(v.version); setRollbackNote('') }} disabled={!v.has_body || isCurrent}>Roll back</Button>
                </div>
              </li>
            )
          })}
        </ol>
      )}
      {rollbackTo != null && (
        <div className="sub-panel">
          <div className="card-head"><h4>Roll back to v{rollbackTo}</h4></div>
          <ConfirmPanel
            message={<>The v{rollbackTo} body becomes <b>v{version + 1}</b> — the ledger keeps every line.</>}
            confirmLabel={`Roll back to v${rollbackTo}`}
            busy={busy}
            onConfirm={doRollback}
            onCancel={() => setRollbackTo(null)}
          >
            <Field label="Note" htmlFor="rb-note" required help="Becomes the ledger line for the rolled-back version.">
              <input data-autofocus id="rb-note" type="text" value={rollbackNote} onChange={(e) => setRollbackNote(e.target.value)} placeholder="Why roll back"
                onKeyDown={(e) => { if (e.key === 'Enter' && rollbackNote.trim()) void doRollback() }} />
            </Field>
          </ConfirmPanel>
        </div>
      )}
      {diff && (
        <div className="sub-panel">
          <div className="card-head">
            <h4>Changes v{diff.from} → v{diff.to}</h4>
            <Button variant="ghost" size="sm" onClick={() => setDiff(null)}>Close</Button>
          </div>
          <DiffView text={diff.diff} />
        </div>
      )}
      {viewVersion && (
        <div className="sub-panel">
          <div className="card-head">
            <h4>Body at v{viewVersion.version}</h4>
            <Button variant="ghost" size="sm" onClick={() => setViewVersion(null)}>Close</Button>
          </div>
          <pre className="prompt-preview">{viewVersion.body}</pre>
        </div>
      )}
    </Card>
  )
}

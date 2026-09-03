import { Fragment, useCallback, useState } from 'react'
import { Archive, HeartPulse, RefreshCw, RotateCcw, Trash2 } from 'lucide-react'
import { api } from '../api'
import { useLoad, LoadError } from '../hooks'
import { ActionMenu, Badge, Button, ConfirmPanel, Empty, IconButton, Loading, PageHeader, SectionHead, TableWrap, fmtBytes, fmtTime } from '../components/ui'
import { useAdmin } from '../state/AdminContext'
import { HealSummaryChips, SelfHealingDrawer } from './RunSelfHealing'
import type { RunRow, SelfHealView } from '../types'

type Pending = { id: string; op: 'reset' | 'archive' | 'delete' }

function StageChips({ stages }: { stages: RunRow['stages'] }) {
  if (!stages?.length) return <span className="muted">—</span>
  return (
    <div className="chips">
      {stages.map((s) => <Badge key={s.stage} status={s.status} label={s.stage.replaceAll('_', ' ')} title={`${s.stage}: ${s.status.replaceAll('_', ' ')}`} />)}
    </div>
  )
}

export function RunsPage() {
  const { run, busy } = useAdmin()
  const active = useLoad(() => api.runs.list())
  const archived = useLoad(() => api.runs.archived())
  const [pending, setPending] = useState<Pending | null>(null)
  // Self-healing is fetched per run only when its drawer opens; the table
  // never pays for it. What the drawer fetched is kept so the row can show
  // the counts afterwards.
  const [healOpen, setHealOpen] = useState<RunRow | null>(null)
  const [heal, setHeal] = useState<Record<string, SelfHealView>>({})
  const onHealLoaded = useCallback((view: SelfHealView) => {
    setHeal((h) => (healOpen ? { ...h, [healOpen.run_id]: view } : h))
  }, [healOpen])
  const closeHeal = useCallback(() => setHealOpen(null), [])

  const reloadAll = () => { active.reload(); archived.reload() }

  const perform = async () => {
    if (!pending) return
    const { id, op } = pending
    let ok: unknown
    if (op === 'reset') ok = await run(() => api.runs.reset(id), `${id} reset to its seeded state`)
    else if (op === 'archive') ok = await run(() => api.runs.archive(id), `${id} archived`)
    else ok = await run(async () => { await api.runs.remove(id); return true }, `${id} deleted`)
    setPending(null)
    if (ok) reloadAll()
  }

  const messages: Record<Pending['op'], (r: RunRow) => React.ReactNode> = {
    reset: (r) => <>Reset <b className="mono">{r.run_id}</b> to its seeded state? Mode, entry mode and prompt set are preserved; every stage, gate and ledger in the run is recreated from seed.</>,
    archive: (r) => <>Move <b className="mono">{r.run_id}</b> under <span className="mono">artifacts/runs-archive-&lt;date&gt;/</span>? It disappears from the Control Centre's run list but stays on disk.</>,
    delete: (r) => <>Delete <b className="mono">{r.run_id}</b> ({fmtBytes(r.size_bytes)}) permanently? This removes the run's artifact tree — archive instead if the evidence may still be wanted.</>,
  }

  return (
    <>
      <PageHeader
        title="Runs"
        description="Every run on disk under artifacts/runs/. Reset, archive and delete are audited with the acting name."
        actions={<Button variant="secondary" size="sm" icon={<RefreshCw />} onClick={reloadAll} disabled={active.loading}>Refresh</Button>}
      />
      {active.loading && !active.data ? <Loading what="Loading runs" /> : null}
      {active.error ? <LoadError what="runs" error={active.error} onRetry={active.reload} /> : null}
      {active.data && active.data.length === 0 ? <Empty title="No active runs" hint="The Control Centre creates one on first load." /> : null}
      {active.data && active.data.length > 0 ? (
        <TableWrap label="Active runs">
          <table>
            <thead><tr><th>Run</th><th>Mode</th><th>Entry</th><th>Prompt set</th><th>Status</th><th>Created</th><th className="num">Size</th><th>Stages</th><th>Self-healing</th><th className="actions-col"><span className="sr-only">Actions</span></th></tr></thead>
            <tbody>
              {active.data.map((r) => (
                <Fragment key={r.run_id}>
                <tr>
                  <td className="mono nowrap"><b>{r.run_id}</b></td>
                  <td><Badge variant="neutral" label={r.mode} /></td>
                  <td>{r.entry_mode ?? 'project'}</td>
                  <td className="mono">{r.prompt_set ?? 'default'}</td>
                  <td><Badge status={r.status || 'not_started'} /></td>
                  <td className="nowrap">{fmtTime(r.created_at)}</td>
                  <td className="num">{fmtBytes(r.size_bytes)}</td>
                  <td style={{ minWidth: 280 }}><StageChips stages={r.stages} /></td>
                  <td className="nowrap">
                    <span className="sh-cell">
                      <IconButton label={`Self-healing for ${r.run_id}`} icon={<HeartPulse />} size="sm" onClick={() => setHealOpen(r)} />
                      {heal[r.run_id] ? <HealSummaryChips view={heal[r.run_id]} /> : null}
                    </span>
                  </td>
                  <td className="actions-col">
                    <ActionMenu label={`Actions for ${r.run_id}`} items={[
                      { label: 'Self-healing', icon: <HeartPulse />, onSelect: () => setHealOpen(r) },
                      { label: 'Reset to seed', icon: <RotateCcw />, onSelect: () => setPending({ id: r.run_id, op: 'reset' }) },
                      { label: 'Archive', icon: <Archive />, onSelect: () => setPending({ id: r.run_id, op: 'archive' }) },
                      { label: 'Delete', icon: <Trash2 />, danger: true, onSelect: () => setPending({ id: r.run_id, op: 'delete' }) },
                    ]} />
                  </td>
                </tr>
                {pending?.id === r.run_id && (
                  <tr className="sel">
                    <td colSpan={10} style={{ paddingTop: 0 }}>
                      <ConfirmPanel
                        danger={pending.op === 'delete'}
                        message={messages[pending.op](r)}
                        confirmLabel={pending.op === 'reset' ? 'Reset run' : pending.op === 'archive' ? 'Archive run' : 'Delete run'}
                        busy={busy}
                        onConfirm={perform}
                        onCancel={() => setPending(null)}
                      />
                    </td>
                  </tr>
                )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </TableWrap>
      ) : null}

      <SectionHead title="Archived runs" description="Under artifacts/runs-archive-<date>/ — kept on disk, invisible to the Control Centre." />
      {archived.loading && !archived.data ? <Loading what="Loading archived runs" /> : null}
      {archived.error ? <LoadError what="archived runs" error={archived.error} onRetry={archived.reload} /> : null}
      {archived.data && archived.data.length === 0 ? <Empty title="No archived runs" hint="Archive a run above to keep its evidence on disk without showing it in the Control Centre." /> : null}
      {archived.data && archived.data.length > 0 ? (
        <TableWrap label="Archived runs">
          <table>
            <thead><tr><th>Run</th><th>Archive</th><th>Mode</th><th>Entry</th><th>Prompt set</th><th>Status</th><th>Created</th><th className="num">Size</th></tr></thead>
            <tbody>
              {archived.data.map((r) => (
                <tr key={`${r.archive}-${r.run_id}`}>
                  <td className="mono nowrap">{r.run_id}</td>
                  <td className="mono"><span className="trunc" title={r.archive ?? undefined}>{r.archive ?? '—'}</span></td>
                  <td><Badge variant="neutral" label={r.mode} /></td>
                  <td>{r.entry_mode ?? 'project'}</td>
                  <td className="mono">{r.prompt_set ?? 'default'}</td>
                  <td><Badge status={r.status || 'not_started'} /></td>
                  <td className="nowrap">{fmtTime(r.created_at)}</td>
                  <td className="num">{fmtBytes(r.size_bytes)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableWrap>
      ) : null}

      {healOpen ? <SelfHealingDrawer run={healOpen} onClose={closeHeal} onLoaded={onHealLoaded} /> : null}
    </>
  )
}

import { useState } from 'react'
import { RefreshCw } from 'lucide-react'
import { api } from '../api'
import { useLoad, LoadError } from '../hooks'
import { Button, Field, Loading, PageHeader } from '../components/ui'
import { AuditTable } from './Overview'

const ACTIONS = [
  'prompt_set.create', 'prompt_set.delete', 'prompt_set.describe',
  'prompt.write', 'prompt.create', 'prompt.rollback', 'playbook.write',
  'prompt.propose', 'prompt.accept_proposal', 'prompt.reject_proposal',
  'llm_settings.save', 'cache.clear', 'roles.save', 'roles.reset',
  'user.create', 'user.update', 'user.delete',
  'run.reset', 'run.archive', 'run.delete',
]

export function AuditPage() {
  const [action, setAction] = useState('')
  const [limit, setLimit] = useState(200)
  const { data, error, loading, reload } = useLoad(() => api.audit(limit, action), [limit, action])

  return (
    <>
      <PageHeader
        title="Audit"
        description="config/audit.jsonl, newest first — who changed what, with the content hash before and after."
        actions={<Button variant="secondary" size="sm" icon={<RefreshCw />} onClick={reload} disabled={loading}>Refresh</Button>}
      />
      <div className="filter-row">
        <Field label="Action" htmlFor="audit-action">
          <select id="audit-action" value={action} onChange={(e) => setAction(e.target.value)}>
            <option value="">All actions</option>
            {ACTIONS.map((a) => <option key={a} value={a}>{a}</option>)}
          </select>
        </Field>
        <Field label="Show up to" htmlFor="audit-limit">
          <select id="audit-limit" value={limit} onChange={(e) => setLimit(Number(e.target.value))}>
            {[50, 100, 200, 500, 1000].map((n) => <option key={n} value={n}>{n} rows</option>)}
          </select>
        </Field>
      </div>
      {loading && !data ? <Loading what="Loading audit" /> : null}
      {error ? <LoadError what="the audit ledger" error={error} onRetry={reload} /> : null}
      {data ? (
        <>
          <AuditTable rows={data} />
          <div className="table-foot"><span>{data.length} row{data.length === 1 ? '' : 's'}{action ? ` for ${action}` : ''}</span></div>
        </>
      ) : null}
    </>
  )
}

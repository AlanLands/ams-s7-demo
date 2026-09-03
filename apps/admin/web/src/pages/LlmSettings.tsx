import { Fragment, useEffect, useMemo, useState } from 'react'
import { Save, Undo2 } from 'lucide-react'
import { ApiError, api } from '../api'
import { useLoad, LoadError } from '../hooks'
import { Badge, Button, Card, Empty, Field, Loading, Notice, PageHeader, SectionHead, TableWrap, humanize } from '../components/ui'
import { useAdmin } from '../state/AdminContext'
import type { LlmDescribe, LlmSettings } from '../types'

type Pair = { provider: string; model: string }

const GROUP_ORDER = ['intake', 'planning', 'build_review', 'legacy']

function ProviderModel({ id, value, providers, onChange, placeholderModel, labelPrefix }: {
  id: string; value: Pair; providers: string[]; onChange: (v: Pair) => void; placeholderModel?: string; labelPrefix: string
}) {
  return (
    <div className="provider-row">
      <select id={`${id}-provider`} aria-label={`${labelPrefix} provider`} value={value.provider} onChange={(e) => onChange({ ...value, provider: e.target.value })}>
        <option value="">Inherit</option>
        {providers.map((p) => <option key={p} value={p}>{p}</option>)}
      </select>
      <input id={`${id}-model`} type="text" className="mono-input" aria-label={`${labelPrefix} model`} value={value.model} placeholder={placeholderModel ?? 'inherit'} onChange={(e) => onChange({ ...value, model: e.target.value })} spellCheck={false} autoComplete="off" />
    </div>
  )
}

function fromSettings(d: LlmDescribe): { def: Pair; stages: Record<string, Pair>; mode: string } {
  const s = d.settings ?? {}
  const def: Pair = { provider: s.default?.provider ?? '', model: s.default?.model ?? '' }
  const stages: Record<string, Pair> = {}
  for (const row of d.stages) {
    const st = s.stages?.[row.key]
    stages[row.key] = { provider: st?.provider ?? '', model: st?.model ?? '' }
  }
  return { def, stages, mode: s.llm_mode ?? '' }
}

export function LlmSettingsPage() {
  const { run, fail, notify, busy } = useAdmin()
  const { data, setData, error, loading, reload } = useLoad(() => api.llm.describe())
  const [def, setDef] = useState<Pair>({ provider: '', model: '' })
  const [stages, setStages] = useState<Record<string, Pair>>({})
  const [mode, setMode] = useState('')
  const [validation, setValidation] = useState<string | null>(null)

  useEffect(() => {
    if (!data) return
    const f = fromSettings(data)
    setDef(f.def); setStages(f.stages); setMode(f.mode); setValidation(null)
  }, [data])

  const groups = useMemo(() => {
    if (!data) return []
    const byGroup = new Map<string, typeof data.stages>()
    for (const row of data.stages) {
      const list = byGroup.get(row.group) ?? []
      list.push(row)
      byGroup.set(row.group, list)
    }
    const keys = [...byGroup.keys()].sort((a, b) => {
      const ia = GROUP_ORDER.indexOf(a), ib = GROUP_ORDER.indexOf(b)
      return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib)
    })
    return keys.map((k) => ({ group: k, rows: byGroup.get(k)! }))
  }, [data])

  const dirty = useMemo(() => {
    if (!data) return false
    const f = fromSettings(data)
    if (f.def.provider !== def.provider || f.def.model !== def.model || f.mode !== mode) return true
    return Object.keys(stages).some((k) => stages[k].provider !== (f.stages[k]?.provider ?? '') || stages[k].model !== (f.stages[k]?.model ?? ''))
  }, [data, def, stages, mode])

  const discard = () => {
    if (!data) return
    const f = fromSettings(data)
    setDef(f.def); setStages(f.stages); setMode(f.mode); setValidation(null)
  }

  const save = async () => {
    const body: LlmSettings = {
      default: { provider: def.provider || null, model: def.model || null },
      stages: Object.fromEntries(Object.entries(stages)
        .filter(([, v]) => v.provider || v.model)
        .map(([k, v]) => [k, { provider: v.provider || null, model: v.model || null }])),
      llm_mode: (mode || null) as LlmSettings['llm_mode'],
    }
    setValidation(null)
    try {
      await run(async () => {
        try {
          await api.llm.save(body)
        } catch (err) {
          if (err instanceof ApiError && err.status === 400) { setValidation(err.message); return }
          throw err
        }
        const fresh = await api.llm.describe()
        setData(fresh)
        notify('LLM settings saved — applies to the next model call, no restart')
      })
    } catch (err) {
      fail(err)
    }
  }

  const header = (
    <PageHeader
      title="LLM Settings"
      description="Provider and model per stage, on top of the environment. Credentials never appear here — provider status is a boolean."
      actions={<>
        <Button variant="secondary" size="sm" icon={<Undo2 />} onClick={discard} disabled={!dirty}>Discard changes</Button>
        <Button variant="primary" size="sm" icon={<Save />} onClick={save} disabled={!dirty} busy={busy}>Save settings</Button>
      </>}
    />
  )

  if (loading && !data) return <>{header}<Loading what="Loading LLM settings" /></>
  if (error) return <>{header}<LoadError what="LLM settings" error={error} onRetry={reload} /></>
  if (!data) return null

  const effectiveDefault = data.stages[0]?.effective
  const envMode = String(data.environment?.LLM_MODE ?? '') || '(unset)'

  return (
    <>
      {header}

      {validation && (
        <div style={{ marginBottom: 16 }}>
          <Notice tone="danger" title="Refused by validation (400).">{validation}</Notice>
        </div>
      )}
      {dirty && !validation && (
        <div style={{ marginBottom: 16 }}>
          <Notice tone="warning" title="Unsaved changes.">Save settings to apply them to the next model call, or discard.</Notice>
        </div>
      )}

      <div className="grid cols-2">
        <Card title="Default provider and model" description="Used by every stage that does not override it. Blank inherits the environment (LLM_PROVIDER / LLM_MODEL).">
          <ProviderModel id="llm-default" labelPrefix="Default" value={def} providers={data.providers_available} onChange={setDef} placeholderModel={effectiveDefault?.model ?? undefined} />
        </Card>
        <Card title="Mode override" description="Replay never makes a network call; record always calls live and refreshes the recording.">
          <Field label="LLM mode" htmlFor="llm-mode" help={`Blank follows the environment (LLM_MODE=${envMode}).`}>
            <select id="llm-mode" value={mode} onChange={(e) => setMode(e.target.value)}>
              <option value="">Environment ({envMode})</option>
              {(data.modes ?? ['live', 'record', 'replay']).map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
          </Field>
        </Card>
      </div>

      <SectionHead title="Per-stage overrides" description="The effective value is what a call from that stage actually uses after the default and the environment are applied." />
      {groups.length === 0 ? <Empty title="No stages reported" hint="The backend reports no stages to override." /> : (
        <TableWrap label="Per-stage overrides">
          <table>
            <thead><tr><th>Stage</th><th>Override</th><th>Effective</th></tr></thead>
            <tbody>
              {groups.map((g) => (
                <Fragment key={g.group}>
                  <tr className="grp"><td colSpan={3}>{humanize(g.group)}</td></tr>
                  {g.rows.map((row) => {
                    const overridden = Boolean(stages[row.key]?.provider || stages[row.key]?.model)
                    return (
                      <tr key={row.key}>
                        <td>
                          <b>{row.label}</b>
                          <span className="sub mono">{row.key}</span>
                        </td>
                        <td style={{ minWidth: 360 }}>
                          <ProviderModel id={`llm-${row.key}`} labelPrefix={row.label} value={stages[row.key] ?? { provider: '', model: '' }} providers={data.providers_available}
                            onChange={(v) => setStages((s) => ({ ...s, [row.key]: v }))} placeholderModel={row.effective?.model ?? undefined} />
                        </td>
                        <td className="mono nowrap">
                          {row.effective?.provider ?? '—'} / {row.effective?.model ?? '—'}
                          {overridden && <Badge variant="warning" label="Overridden" />}
                        </td>
                      </tr>
                    )
                  })}
                </Fragment>
              ))}
            </tbody>
          </table>
        </TableWrap>
      )}

      <SectionHead title="Provider status" description="Whether each provider's credentials and endpoint are present in the environment — values are never shown." />
      <TableWrap label="Provider status">
        <table>
          <thead><tr><th>Provider</th><th>Configured</th><th>Needs</th><th>Environment model</th></tr></thead>
          <tbody>
            {data.providers.map((p) => (
              <tr key={p.provider}>
                <td className="mono">{p.provider}</td>
                <td>{p.configured ? <Badge variant="success" label="Configured" /> : <Badge variant="warning" label="Not configured" />}</td>
                <td className="mono sm">{Array.isArray(p.needs) ? (p.needs.join(', ') || '—') : (p.needs || '—')}</td>
                <td className="mono">{p.env_model ?? <span className="muted">—</span>}</td>
              </tr>
            ))}
            {data.providers.length === 0 && <tr><td colSpan={4} className="muted">No providers reported.</td></tr>}
          </tbody>
        </table>
      </TableWrap>

      <SectionHead title="Environment" description="What the process was started with — the floor these settings sit on." />
      <Card>
        <div className="kv">
          {Object.entries(data.environment ?? {}).map(([k, v]) => (
            <div key={k} style={{ display: 'contents' }}>
              <span className="k mono">{k}</span>
              <span className="v mono">{v == null || v === '' ? <span className="muted">(unset)</span> : typeof v === 'boolean' ? (v ? 'true' : 'false') : String(v)}</span>
            </div>
          ))}
          {Object.keys(data.environment ?? {}).length === 0 && <span className="muted">Nothing reported.</span>}
        </div>
      </Card>
    </>
  )
}

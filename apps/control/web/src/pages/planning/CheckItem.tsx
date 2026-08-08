// Ported verbatim from `function checkItem(ok, label, extra)` in
// apps/control/static/app.js (~line 355-360).
export function CheckItem({ ok, label, extra }: { ok: boolean; label: string; extra?: string | number | null }) {
  return (
    <li>
      <span className={`tick ${ok ? 'ok' : 'no'}`}>{ok ? '✓' : '·'}</span>
      {label}
      {extra != null ? <span className="state ok mono">{String(extra)}</span> : null}
    </li>
  )
}

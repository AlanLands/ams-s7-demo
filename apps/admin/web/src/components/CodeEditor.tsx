import { useMemo, useRef } from 'react'

/* The one monospace editor, shared by the profile editor and any form that
 * takes a file body. Prompt bodies are prose, so soft wrap is the default;
 * the gutter numbers logical lines and is shown only when wrapping is off,
 * where its rows line up with what is on screen. */

// Task bodies use `{{name}}` (factory/layers.py `placeholders_of`); the
// server's own list is authoritative for the saved text, this is the
// live check on what is being typed.
const PLACEHOLDER = /\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}/g

export function usedPlaceholders(body: string): string[] {
  const out = new Set<string>()
  for (const m of body.matchAll(PLACEHOLDER)) out.add(m[1])
  return [...out].sort()
}

/** Locked tokens are literal substrings the Control Centre depends on; an
 * edit may move them but not drop them. */
export function missingLocked(body: string, locked: string[]): string[] {
  return locked.filter((tok) => tok && !body.includes(tok))
}

/** Monospace editor with a line-number gutter, a resize handle and
 * Ctrl/Cmd+S. */
export function CodeEditor({ id, value, onChange, onSave, dirty, invalid, ariaLabel, height, wrap }: {
  id: string
  value: string
  onChange: (v: string) => void
  onSave?: () => void
  dirty?: boolean
  invalid?: boolean
  ariaLabel: string
  height?: number
  wrap: boolean
}) {
  const gutter = useRef<HTMLDivElement>(null)
  const lines = useMemo(() => value.split('\n').length, [value])
  const onScroll = (e: React.UIEvent<HTMLTextAreaElement>) => {
    if (gutter.current) gutter.current.scrollTop = e.currentTarget.scrollTop
  }
  const onKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') { e.preventDefault(); onSave?.() }
  }
  return (
    <div className={`code-editor${dirty ? ' dirty' : ''}${invalid ? ' invalid' : ''}${wrap ? ' wrap' : ''}`} style={height ? { height } : undefined}>
      <div className="gutter" ref={gutter} aria-hidden="true">
        {Array.from({ length: lines }, (_, i) => <div key={i}>{i + 1}</div>)}
      </div>
      <textarea id={id} value={value} onChange={(e) => onChange(e.target.value)} onScroll={onScroll} onKeyDown={onKey} spellCheck={false} aria-label={ariaLabel} aria-invalid={invalid || undefined} />
    </div>
  )
}

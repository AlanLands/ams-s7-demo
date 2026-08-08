import { useRef, useState } from 'react'
import { useRun } from '../../state/RunContext'

const ACCEPT = '.txt,.md,.pdf,.docx'
const MAX_BYTES = 10 * 1024 * 1024

function extForName(name: string) {
  return name.split('.').pop()?.toUpperCase() ?? 'FILE'
}

function formatBytes(n: number) {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}

export function SourceRequirementCard() {
  const { data, uploadAct, act } = useRun()
  const [tab, setTab] = useState<'upload' | 'paste'>('upload')
  const [dragOver, setDragOver] = useState(false)
  const [pendingFile, setPendingFile] = useState<File | null>(null)
  const [pasteText, setPasteText] = useState('')
  const [busy, setBusy] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const source = data?.intake?.source

  async function submitFile(file: File) {
    if (file.size > MAX_BYTES) return
    setBusy(true)
    const form = new FormData()
    form.append('file', file)
    await uploadAct('/intake/upload-source', form, `${file.name} extracted`)
    setBusy(false)
    setPendingFile(null)
  }

  function handleFiles(files: FileList | null) {
    const file = files?.[0]
    if (!file) return
    setPendingFile(file)
    submitFile(file)
  }

  async function submitPaste() {
    if (!pasteText.trim()) return
    setBusy(true)
    await act('/intake/paste-source', { text: pasteText }, 'Text extracted')
    setBusy(false)
  }

  return (
    <div className="card">
      <h3>1. Source Requirement</h3>
      <p className="hint">Upload file or paste requirement text</p>
      <div className="tabs" style={{ marginTop: 10 }}>
        <button type="button" className={tab === 'upload' ? 'on' : ''} onClick={() => setTab('upload')}>Upload File</button>
        <button type="button" className={tab === 'paste' ? 'on' : ''} onClick={() => setTab('paste')}>Paste Text</button>
      </div>

      {tab === 'upload' ? (
        <div>
          <div
            className={`dropzone${dragOver ? ' drag-over' : ''}`}
            onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => { e.preventDefault(); setDragOver(false); handleFiles(e.dataTransfer.files) }}
          >
            <div className="dropzone-icon" aria-hidden="true">⬆</div>
            <p>Drag &amp; drop your file here</p>
            <p className="hint">or</p>
            <button type="button" className="outline" onClick={() => inputRef.current?.click()}>Browse File</button>
            <input
              ref={inputRef}
              type="file"
              accept={ACCEPT}
              style={{ display: 'none' }}
              onChange={(e) => handleFiles(e.target.files)}
            />
            <p className="hint" style={{ marginTop: 10 }}>Supported formats: PDF, DOCX, TXT, MD</p>
            <p className="hint">Max file size: 10 MB</p>
          </div>

          {(pendingFile || source?.filename) && (
            <div className="file-row">
              <span className="chip tag">{extForName(pendingFile?.name ?? source?.filename ?? '')}</span>
              <span className="mono">{pendingFile?.name ?? source?.filename}</span>
              {pendingFile && <span className="hint">{formatBytes(pendingFile.size)}</span>}
              {busy ? <span className="hint">Uploading…</span> : source && <span className="prov prov-human">✓ Uploaded</span>}
            </div>
          )}
          {source && !source.filename && (
            <div className="file-row">
              <span className="mono">(pasted text)</span>
              <span className="chip tag">{source.text.length.toLocaleString()} chars</span>
            </div>
          )}
        </div>
      ) : (
        <div>
          <label className="fld" htmlFor="intake-paste">Paste epic / requirement</label>
          <textarea
            id="intake-paste"
            rows={8}
            placeholder="Paste your business epic, change request or requirement here…"
            value={pasteText}
            onChange={(e) => setPasteText(e.target.value)}
          />
          <button type="button" className="primary sq block" style={{ marginTop: 10 }} disabled={busy || !pasteText.trim()} onClick={submitPaste}>
            Extract with AI
          </button>
        </div>
      )}
    </div>
  )
}

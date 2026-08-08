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

interface Props {
  extracting: boolean
  onExtractStart: () => void
  onExtractEnd: (ok: boolean, message?: string) => void
}

export function SourceRequirementCard({ extracting, onExtractStart, onExtractEnd }: Props) {
  const { data, uploadAct, act } = useRun()
  const [tab, setTab] = useState<'upload' | 'paste'>('upload')
  const [dragOver, setDragOver] = useState(false)
  const [pendingFile, setPendingFile] = useState<File | null>(null)
  const [pasteText, setPasteText] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const source = data?.intake?.source
  const busy = extracting

  async function submitFile(file: File) {
    if (file.size > MAX_BYTES) return
    onExtractStart()
    const form = new FormData()
    form.append('file', file)
    const ok = await uploadAct('/intake/upload-source', form, `${file.name} extracted`)
    onExtractEnd(ok, ok ? undefined : 'Extraction could not be completed')
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
    onExtractStart()
    const ok = await act('/intake/paste-source', { text: pasteText }, 'Text extracted')
    onExtractEnd(ok, ok ? undefined : 'Extraction could not be completed')
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
        <div className="tab-body">
          <div
            className={`dropzone${dragOver ? ' drag-over' : ''}`}
            onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => { e.preventDefault(); setDragOver(false); handleFiles(e.dataTransfer.files) }}
          >
            <div className="dropzone-icon" aria-hidden="true">
              <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                <path d="M6.6 16A4.3 4.3 0 0 1 6 7.5a6 6 0 0 1 11.7 1.3A3.7 3.7 0 0 1 17.4 16" />
                <path d="M12 12v8" />
                <path d="m8.6 15.4 3.4-3.4 3.4 3.4" />
              </svg>
            </div>
            <p>Drag &amp; drop your file here</p>
            <p className="hint">or</p>
            <button type="button" className="primary sq" onClick={() => inputRef.current?.click()}>Browse File</button>
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

          <div className="note-box">
            <span aria-hidden="true">ⓘ</span>
            <p>Make sure your document contains the business requirement or epic with the scope and key details.</p>
          </div>
        </div>
      ) : (
        <div className="tab-body">
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

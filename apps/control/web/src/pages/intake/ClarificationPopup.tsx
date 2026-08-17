import { useEffect, useRef, useState } from 'react'
import { Modal } from '../../components/Modal'
import { Prov } from '../../components/Badge'
import { useRun } from '../../state/RunContext'
import type { Provenance } from '../../types'

/** Auto-opening clarification dialog: the moment an analysis run leaves
 * open questions, the AI asks the business directly — no separate "ask"
 * button. Dismissing keeps the questions pending (the inline card in the
 * analysis section remains); a fresh round re-opens the popup. */
export function ClarificationPopup() {
  const { data, act } = useRun()
  const clar = data?.intake?.clarifications
  const analysis = data?.intake?.analysis
  const [answers, setAnswers] = useState<string[]>([])
  const [dismissedKey, setDismissedKey] = useState<string | null>(null)
  const pendingKey = clar?.pending?.length ? clar.pending.join('|') : null
  const lastKey = useRef<string | null>(null)

  useEffect(() => {
    if (pendingKey && pendingKey !== lastKey.current) {
      lastKey.current = pendingKey
      setAnswers([])
    }
  }, [pendingKey])

  if (!clar || !pendingKey || dismissedKey === pendingKey) return null
  const provenance = (clar.provenance ?? analysis?.provenance ?? 'simulated') as Provenance

  return (
    <Modal
      title="AI Clarification — questions for the Business"
      onClose={() => setDismissedKey(pendingKey)}
    >
      <p className="hint" style={{ marginTop: 4 }}>
        The analysis left open questions <Prov provenance={provenance} /> — answer them (or leave
        blank to record a stated assumption) so planning works from the business&apos;s own words.
        Round {clar.rounds_used} of {clar.max_rounds}.
      </p>
      {clar.pending.map((q, i) => (
        <div key={q} style={{ marginTop: 10 }}>
          <p style={{ marginBottom: 4 }}>{q}</p>
          <input
            type="text"
            style={{ width: '100%' }}
            placeholder="Answer (blank = stated assumption)" aria-label="Answer (blank = stated assumption)"
            value={answers[i] ?? ''}
            onChange={(e) =>
              setAnswers((prev) => {
                const next = [...prev]
                next[i] = e.target.value
                return next
              })
            }
          />
        </div>
      ))}
      <div className="actions-row" style={{ marginTop: 14, justifyContent: 'flex-end' }}>
        <button type="button" className="ghost" onClick={() => setDismissedKey(pendingKey)}>
          Answer later
        </button>
        <button
          type="button"
          className="primary sq"
          onClick={async () => {
            const filled = clar.pending.map((_, i) => answers[i] ?? '')
            if (await act('/intake/clarify-answer', { answers: filled }, 'Answers recorded')) {
              setAnswers([])
            }
          }}
        >
          Submit Answers
        </button>
      </div>
    </Modal>
  )
}

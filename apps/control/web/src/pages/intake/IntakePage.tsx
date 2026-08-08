import { useState } from 'react'
import { useRun } from '../../state/RunContext'
import { SourceRequirementCard } from './SourceRequirementCard'
import { ExtractionCard } from './ExtractionCard'
import { AdvancedAnalysisSection } from './AdvancedAnalysisSection'

export function IntakePage() {
  const { data, act } = useRun()
  const [extracting, setExtracting] = useState(false)
  const [extractError, setExtractError] = useState<string | null>(null)
  if (!data) return null
  const epic = data.intake?.epic

  async function retryExtraction() {
    setExtracting(true)
    setExtractError(null)
    const ok = await act('/intake/re-extract', {}, 'Retrying extraction')
    setExtracting(false)
    if (!ok) setExtractError('Extraction could not be completed')
  }

  return (
    <section className="intake-page">
      <div>
        <div className="page-head intake-head">
          <div>
            <h2>Intake — Requirement Input</h2>
            <p className="hint">Upload your business epic or requirement. AI will extract key information and structure it for planning.</p>
          </div>
          <div className="epic-id-chip">
            <span className="hdr-label">Epic ID</span>
            {epic ? <span className="mono">{epic.epic_id}</span> : <span className="hint">Not created</span>}
          </div>
        </div>

        <div className="intake-grid">
          <SourceRequirementCard
            extracting={extracting}
            onExtractStart={() => { setExtracting(true); setExtractError(null) }}
            onExtractEnd={(ok, message) => { setExtracting(false); if (!ok) setExtractError(message ?? 'Extraction failed') }}
          />
          <span className="intake-arrow" aria-hidden="true">→</span>
          <ExtractionCard extracting={extracting} extractError={extractError} onRetry={retryExtraction} />
        </div>

        <AdvancedAnalysisSection />

        <div className="card info-bar">
          <p>The extracted epic will be used by AI Planner to create stories, acceptance criteria, dependencies and route work to teams.</p>
        </div>
      </div>
    </section>
  )
}

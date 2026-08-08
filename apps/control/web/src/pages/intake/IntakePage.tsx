import { useRun } from '../../state/RunContext'
import { SourceRequirementCard } from './SourceRequirementCard'
import { ExtractionCard } from './ExtractionCard'
import { AiActivityPanel } from './AiActivityPanel'
import { AdvancedAnalysisSection } from './AdvancedAnalysisSection'

export function IntakePage() {
  const { data } = useRun()
  if (!data) return null
  const epic = data.intake?.epic

  return (
    <section className="page-with-rail intake-page">
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
          <SourceRequirementCard />
          <span className="intake-arrow" aria-hidden="true">→</span>
          <ExtractionCard />
        </div>

        <AdvancedAnalysisSection />

        <div className="card info-bar">
          <p>The extracted epic will be used by AI Planner to create stories, acceptance criteria, dependencies and route work to teams.</p>
        </div>
      </div>
      <AiActivityPanel />
    </section>
  )
}

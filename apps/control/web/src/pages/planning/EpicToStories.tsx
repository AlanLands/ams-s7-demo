import { useRun } from '../../state/RunContext'
import { EpicDetailsCard } from './EpicDetailsCard'
import { Gate1Rail } from './Gate1Rail'
import { KpiTiles } from './KpiTiles'
import { planningOf } from './planningHelpers'
import { PlanningAssistantCards } from './PlanningAssistantCards'
import { StoriesPanel } from './StoriesPanel'

// Ported from `function renderEpicToStories()` in apps/control/static/app.js
// (~line 1285-1304). The rail is `gate1Rail()`, already ported as the shared
// `Gate1Rail` component sibling planning pages will also mount; everything
// else on this page (epic details + add/import/suggest actions, the AI
// planning assistant pair, the KPI tiles, and the editable stories panel) is
// specific to this page and lives in its own file here.
export function EpicToStories() {
  const { data } = useRun()
  if (!data) return null

  const stories = planningOf(data).stories ?? []
  const locked = Boolean(data.run.plan_locked)

  return (
    <section className="page-with-rail">
      <div>
        <div className="page-head" style={{ marginBottom: 16 }}>
          <h2>Epic to Stories (AI Decomposition)</h2>
          <span className="hint">
            The planning model decomposes the epic into testable user stories and maps teams and dependencies. Humans edit, extend and sign off.
          </span>
        </div>
        <EpicDetailsCard stories={stories} />
        {stories.length ? (
          <>
            <PlanningAssistantCards stories={stories} />
            <KpiTiles stories={stories} />
            <StoriesPanel stories={stories} editable={!locked} />
          </>
        ) : (
          <div className="card" style={{ marginTop: 14 }}>
            <p>No stories yet. Use “AI Suggest Stories” above once the intake gate (G0) has passed.</p>
          </div>
        )}
      </div>
      <aside className="rail">
        <Gate1Rail />
      </aside>
    </section>
  )
}

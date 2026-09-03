import { useRun } from '../../state/RunContext'
import { EpicSummaryStrip } from './EpicSummaryStrip'
import { KpiTiles } from './KpiTiles'
import { planningOf } from './planningHelpers'
import { StoriesPanel } from './StoriesPanel'

// Redesigned 2026-08-09: the page carries a compact epic strip, the KPI
// tiles, and the stories panel (whose toolbar owns every list action) — the
// old EpicDetailsCard grid and PlanningAssistantCards checklist pair were the
// "too much information" and are gone from this page; their content survives
// on Plan Summary and in the Gate 1 rail checklist. Editing an AI-generated
// story is now the page's primary gesture: any row or card opens
// EditStoryDrawer.
export function EpicToStories() {
  const { data, act } = useRun()
  if (!data) return null

  const stories = planningOf(data).stories ?? []
  const locked = Boolean(data.run.plan_locked)
  const epic = data.intake?.epic

  return (
    <section>
      <div>
        <div className="page-head" style={{ marginBottom: 16 }}>
          <h2>Epic to Stories (AI Decomposition)</h2>
          <span className="hint">
            AI suggests stories from the epic. Review and edit any story before sign-off — click a row to open it.
          </span>
        </div>
        <EpicSummaryStrip />
        {stories.length ? (
          <>
            <KpiTiles stories={stories} />
            <StoriesPanel stories={stories} editable={!locked} />
          </>
        ) : (
          <div className="card empty-stories">
            {data?.run?.entry_mode === 'enhancement' ? (
              <>
                <p>
                  Enhancement entry — work arrives as user stories from the backlog (no epic, no
                  decomposition) and converges with the project lane at plan sign-off.
                </p>
                <button
                  type="button"
                  className="primary sq"
                  title="Loads the enhancement backlog through the engine (scripted in simulation/demo; live runs import real backlog stories instead)"
                  onClick={() => act('/planning/generate', {}, 'Backlog stories loaded')}
                >
                  Load backlog stories
                </button>
              </>
            ) : epic ? (
              <>
                <p>No stories yet — generate the AI draft decomposition to start planning.</p>
                <button
                  type="button"
                  className="primary sq"
                  title="Generates the draft decomposition through the engine (simulation mode is deterministic)"
                  onClick={() => act('/planning/generate', {}, 'Draft stories generated')}
                >
                  ✦ AI Suggest Stories
                </button>
              </>
            ) : (
              <p>No epic yet — complete the Intake stage first (analyse, create epic, pass gate G0).</p>
            )}
          </div>
        )}
      </div>
    </section>
  )
}

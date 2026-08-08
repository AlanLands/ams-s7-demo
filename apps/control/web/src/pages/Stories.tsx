import { Prov } from '../components/Badge'
import { NotBuilt } from '../components/NotBuilt'
import { SectionTitle } from '../components/SectionTitle'
import { useRun } from '../state/RunContext'

export function Stories() {
  const { data } = useRun()
  const stories = data?.planning?.stories ?? []

  if (stories.length === 0) {
    return <NotBuilt name="Epics & Stories" phase="the Planning stage — generate the draft plan first" />
  }

  return (
    <section>
      <SectionTitle title="Epics & Stories" hint="EPIC-S7-001 decomposition — demonstration data" />
      <div className="grid cols-2">
        {stories.map((story) => (
          <div className="card" key={story.story_id}>
            <div className="section-title">
              <h3><span className="mono">{`${story.story_id} `}</span>{story.title}</h3>
              <Prov provenance={story.provenance} />
            </div>
            <p className="hint">{story.purpose}</p>
            <div className="kv" style={{ marginTop: '10px' }}>
              <b>Team</b>
              <span>
                {story.accountable_team + (story.contributing_teams.length
                  ? ` (+ ${story.contributing_teams.join(', ')})`
                  : '')}
              </span>
              <b>Component</b><span>{story.target_component}</span>
              <b>Repository</b><code>{story.target_repository}</code>
              <b>Feature flag</b><span>{story.feature_flag ? <code>{story.feature_flag.name}</code> : '—'}</span>
              <b>Rollback</b><span>{story.rollback_plan?.method ?? '—'}</span>
              <b>Version</b><span>{`v${story.version}`}</span>
            </div>
            <h3 style={{ marginTop: '12px' }}>Acceptance criteria</h3>
            <ul className="plain">
              {story.acceptance_criteria.map((criterion) => (
                <li key={criterion.ac_id}>
                  <span className="mono">{`${criterion.ac_id} `}</span>{criterion.text}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </section>
  )
}

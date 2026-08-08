import { useRun } from '../state/RunContext'

const PLANNING_SUBS: [string, string][] = [
  ['epic_to_stories', 'Epic to Stories'],
  ['dependency_map', 'Dependency Map'],
  ['routing_by_team', 'Routing by Team'],
  ['plan_summary', 'Plan Summary'],
  ['plan_signoff', 'Plan Sign-off'],
]
const BUILD_SUBS: [string, string][] = [
  ['build_work_queue', 'Work Queue'],
  ['dev_progress', 'Development Progress'],
  ['test_evidence', 'Test Evidence'],
  ['independent_review', 'Independent Review'],
]
const NAV: [string, string, string?][] = [
  ['nav-run', 'Run'],
  ['overview', 'Overview', '▦'],
  ['intake', 'Intake', '⭳'],
  ['planning', 'Planning', '▤'],
  ['build_review', 'Build & Review', '⚒'],
  ['quality', 'Quality', '✓'],
  ['release', 'Release', '➤'],
  ['nav-detail', 'Detail'],
  ['stories', 'Epics & Stories', '❖'],
  ['traceability', 'Traceability', '⇄'],
  ['artifacts', 'Artifacts', '▣'],
  ['approvals', 'Approvals', '✍'],
  ['nav-gov', 'Governance'],
  ['activity', 'Activity Log', '◷'],
  ['provenance', 'Provenance', '⛓'],
  ['risks', 'Risks & Alerts', '⚠'],
  ['reports', 'Reports', '▥'],
  ['settings', 'Settings', '⚙'],
]
const GROUPS: Record<string, { subs: [string, string][]; sections: Set<string>; landing: string }> = {
  planning: { subs: PLANNING_SUBS, sections: new Set(['planning', ...PLANNING_SUBS.map(([k]) => k)]), landing: 'epic_to_stories' },
  build_review: { subs: BUILD_SUBS, sections: new Set(['build_review', ...BUILD_SUBS.map(([k]) => k)]), landing: 'build_work_queue' },
}

export function SideNav() {
  const { section, goTo } = useRun()
  return (
    <nav className="sidenav" aria-label="Sections">
      {NAV.map(([key, label, icon]) => {
        if (key.startsWith('nav-')) {
          return <div className="nav-group" key={key}>{label}</div>
        }
        const group = GROUPS[key]
        const inGroup = Boolean(group && group.sections.has(section))
        return (
          <div key={key} style={{ display: 'contents' }}>
            <button
              type="button"
              className={key === section || inGroup ? 'active' : ''}
              onClick={() => goTo(group ? group.landing : key)}
            >
              {icon && <span className="nav-ico">{icon}</span>}
              {label}
              {group && <span className="caret">{inGroup ? '▲' : '▼'}</span>}
            </button>
            {group && inGroup && group.subs.map(([sub, subLabel]) => (
              <button
                key={sub}
                type="button"
                className={`sub ${sub === section ? 'active' : ''}`}
                onClick={() => goTo(sub)}
              >
                {subLabel}
              </button>
            ))}
          </div>
        )
      })}
    </nav>
  )
}

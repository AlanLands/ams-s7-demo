import {
  Activity, ChartColumn, Cpu, Database, FileText, GraduationCap, LayoutDashboard, ListChecks, PenLine, PlayCircle, ShieldCheck, Users,
} from 'lucide-react'
import { useAdmin, type Section } from '../state/AdminContext'

type Item = { key: Section; label: string; icon: React.ReactNode }

const GROUPS: { title: string; items: Item[] }[] = [
  {
    title: 'Product',
    items: [
      { key: 'overview', label: 'Overview', icon: <LayoutDashboard /> },
      { key: 'prompt_sets', label: 'Prompt Sets', icon: <FileText /> },
      { key: 'playbooks', label: 'Playbooks', icon: <ListChecks /> },
      { key: 'learning', label: 'Correction Learning', icon: <GraduationCap /> },
      { key: 'llm', label: 'LLM Settings', icon: <Cpu /> },
      { key: 'recordings', label: 'Recordings & Cache', icon: <Database /> },
    ],
  },
  {
    title: 'People',
    items: [
      { key: 'roles', label: 'Roles & Permissions', icon: <ShieldCheck /> },
      { key: 'users', label: 'Users', icon: <Users /> },
    ],
  },
  {
    title: 'Operations',
    items: [
      { key: 'runs', label: 'Runs', icon: <PlayCircle /> },
      { key: 'observability', label: 'Observability', icon: <ChartColumn /> },
      { key: 'audit', label: 'Audit', icon: <Activity /> },
    ],
  },
]

export function SideNav() {
  const { section, editingSet, goTo, openEditor, configRoot } = useAdmin()
  return (
    <nav className="sidenav" aria-label="Sections">
      {GROUPS.map((g) => (
        <div key={g.title} style={{ display: 'contents' }}>
          <div className="nav-group" aria-hidden="true">{g.title}</div>
          {g.items.map((it) => {
            const active = section === it.key || (it.key === 'prompt_sets' && section === 'prompt_editor' && !editingSet)
            return (
              <div key={it.key} style={{ display: 'contents' }}>
                <button type="button" className="nav-item" aria-current={active ? 'page' : undefined} title={it.label} onClick={() => goTo(it.key)}>
                  <span className="nav-ico" aria-hidden="true">{it.icon}</span>
                  <span className="nav-label">{it.label}</span>
                </button>
                {it.key === 'prompt_sets' && editingSet && (
                  <button
                    type="button"
                    className="nav-item sub"
                    aria-current={section === 'prompt_editor' ? 'page' : undefined}
                    onClick={() => openEditor(editingSet)}
                    title={`Prompt editor — ${editingSet}`}
                  >
                    <span className="nav-ico" aria-hidden="true"><PenLine /></span>
                    <span className="nav-label">Editor <span className="mono">{editingSet}</span></span>
                  </button>
                )}
              </div>
            )
          })}
        </div>
      ))}
      <div className="nav-foot">
        Configuration plane <code>{configRoot ?? 'config/'}</code>
        <br />Every change is recorded: prompt edits in the set's ledger, everything else in the audit.
      </div>
    </nav>
  )
}

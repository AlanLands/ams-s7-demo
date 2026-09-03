import { AdminProvider, useAdmin } from './state/AdminContext'
import { Header } from './components/Header'
import { SideNav } from './components/SideNav'
import { BusyOverlay, ErrorPopup, Toast } from './components/ui'
import { Overview } from './pages/Overview'
import { PromptSets } from './pages/PromptSets'
import { PromptEditor } from './pages/PromptEditor'
import { LlmSettingsPage } from './pages/LlmSettings'
import { RecordingsPage } from './pages/Recordings'
import { RolesPage } from './pages/Roles'
import { UsersPage } from './pages/Users'
import { RunsPage } from './pages/Runs'
import { AuditPage } from './pages/Audit'
import { PlaybooksPage } from './pages/Playbooks'
import { ObservabilityPage } from './pages/Observability'
import { LearningPage } from './pages/Learning'

function Shell() {
  const { section } = useAdmin()
  let Page: () => React.ReactElement | null = Overview
  switch (section) {
    case 'prompt_sets': Page = PromptSets; break
    case 'prompt_editor': Page = PromptEditor; break
    case 'playbooks': Page = PlaybooksPage; break
    case 'learning': Page = LearningPage; break
    case 'llm': Page = LlmSettingsPage; break
    case 'recordings': Page = RecordingsPage; break
    case 'roles': Page = RolesPage; break
    case 'users': Page = UsersPage; break
    case 'runs': Page = RunsPage; break
    case 'observability': Page = ObservabilityPage; break
    case 'audit': Page = AuditPage; break
    default: Page = Overview
  }
  return (
    <>
      <a className="skip-link" href="#main">Skip to content</a>
      <Header />
      <div className="layout">
        <SideNav />
        <main id="main" tabIndex={-1}>
          <div className="page">
            <Page />
          </div>
        </main>
      </div>
      <Toast />
      <BusyOverlay />
      <ErrorPopup />
    </>
  )
}

export default function App() {
  return (
    <AdminProvider>
      <Shell />
    </AdminProvider>
  )
}

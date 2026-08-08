import { RunProvider, useRun } from './state/RunContext'
import { Header } from './components/Header'
import { Stepper } from './components/Stepper'
import { SideNav } from './components/SideNav'
import { Toast } from './components/Toast'
import { NotYetPorted } from './components/NotYetPorted'
import { Overview } from './pages/Overview'
import { IntakePage } from './pages/intake/IntakePage'
import { Traceability } from './pages/Traceability'
import { Artifacts } from './pages/Artifacts'
import { Provenance } from './pages/Provenance'
import { Activity } from './pages/Activity'
import { Reports } from './pages/Reports'

const PAGES: Record<string, () => React.ReactElement | null> = {
  overview: Overview,
  intake: IntakePage,
  traceability: Traceability,
  artifacts: Artifacts,
  provenance: Provenance,
  activity: Activity,
  reports: Reports,
  // epic_to_stories: EpicToStories,   — wired in Phase 3
  // ...remaining Phase-3 pages wired as each is ported
}

function Shell() {
  const { section } = useRun()
  const Page = PAGES[section] ?? (() => <NotYetPorted section={section} />)
  return (
    <>
      <Header />
      <Stepper />
      <div className="layout">
        <SideNav />
        <main id="main">
          <Page />
        </main>
      </div>
      <Toast />
      <footer className="foot">
        <div className="foot-row">
          <span className="foot-brand">S7 Delivery Control Centre&ensp;·&ensp;v2.1.0&ensp;·&ensp;🛡 Secure</span>
          <span className="foot-badges">
            <span className="foot-badge">👥 Governed</span>
            <span className="foot-badge">⛓ Traceable</span>
            <span className="foot-badge">✍ Human-approved</span>
            <span className="foot-badge">▤ Audit-ready</span>
            <span className="foot-badge">✓ Release-safe</span>
          </span>
          <span className="foot-right">Demo Environment</span>
        </div>
        <div className="foot-row small">
          <span className="foot-ai">AI generated · Rules validated · Human governed · Evidence recorded</span>
          <span className="foot-center">
            MapleSure Insurance is fictional; all data on this surface is demonstration data. Artifacts are
            labelled with their provenance — <span className="prov prov-simulated">SIMULATED</span> evidence is
            produced by the deterministic demo engine, <span className="prov prov-human">HUMAN</span> marks a
            person's own input. All times in local time.
          </span>
        </div>
      </footer>
    </>
  )
}

export default function App() {
  return (
    <RunProvider>
      <Shell />
    </RunProvider>
  )
}

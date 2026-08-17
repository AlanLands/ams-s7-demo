import { RunProvider, useRun } from './state/RunContext'
import { Header } from './components/Header'
import { Stepper } from './components/Stepper'
import { SideNav } from './components/SideNav'
import { Toast } from './components/Toast'
import { BusyOverlay } from './components/BusyOverlay'
import { ErrorPopup } from './components/ErrorPopup'
import { NotYetPorted } from './components/NotYetPorted'
import { Overview } from './pages/Overview'
import { IntakePage } from './pages/intake/IntakePage'
import { DesignPage } from './pages/planning/DesignPage'
import { Scorecard } from './pages/Scorecard'
import { Traceability } from './pages/Traceability'
import { Artifacts } from './pages/Artifacts'
import { Provenance } from './pages/Provenance'
import { Activity } from './pages/Activity'
import { Reports } from './pages/Reports'
import { Approvals } from './pages/Approvals'
import { Risks } from './pages/Risks'
import { Settings } from './pages/Settings'
import { EpicToStories } from './pages/planning/EpicToStories'
import { DependencyMap } from './pages/planning/DependencyMap'
import { RoutingByTeam } from './pages/planning/RoutingByTeam'
import { PlanSummary } from './pages/planning/PlanSummary'
import { PlanSignoff } from './pages/planning/PlanSignoff'
import { BuildOverview } from './pages/build/BuildOverview'
import { Architecture } from './pages/build/Architecture'
import { DeliveryPacks } from './pages/build/DeliveryPacks'
import { DeveloperWorkspaces } from './pages/build/DeveloperWorkspaces'
import { TestEvidence } from './pages/build/TestEvidence'
import { IndependentReview } from './pages/build/IndependentReview'
import { BuildSummaryPage } from './pages/build/BuildSummary'
import { Stories } from './pages/Stories'
import { Quality } from './pages/Quality'
import { Release } from './pages/Release'

const PAGES: Record<string, () => React.ReactElement | null> = {
  overview: Overview,
  intake: IntakePage,
  traceability: Traceability,
  artifacts: Artifacts,
  provenance: Provenance,
  activity: Activity,
  reports: Reports,
  scorecard: Scorecard,
  approvals: Approvals,
  risks: Risks,
  settings: Settings,
  epic_to_stories: EpicToStories,
  design: DesignPage,
  dependency_map: DependencyMap,
  routing_by_team: RoutingByTeam,
  plan_summary: PlanSummary,
  plan_signoff: PlanSignoff,
  stories: Stories,
  quality: Quality,
  release: Release,
  build_overview: BuildOverview,
  architecture: Architecture,
  delivery_packs: DeliveryPacks,
  workspaces: DeveloperWorkspaces,
  test_evidence: TestEvidence,
  independent_review: IndependentReview,
  build_summary: BuildSummaryPage,
  // Aliases so a browser holding a stale localStorage section value — from
  // the vanilla app or from the pre-redesign Build & Review pages — still
  // lands somewhere real instead of NotYetPorted.
  planning: EpicToStories,
  build_review: BuildOverview,
  work: BuildOverview,
  build_work_queue: BuildOverview,
  dev_progress: DeveloperWorkspaces,
}

function Shell() {
  const { section, data } = useRun()
  const demoRun = data?.run?.mode === 'demo'
  const Page = PAGES[section] ?? (() => <NotYetPorted section={section} />)
  return (
    <>
      <a className="skip-link" href="#main">Skip to content</a>
      <Header />
      <Stepper />
      <div className="layout">
        <SideNav />
        <main id="main">
          <Page />
        </main>
      </div>
      <Toast />
      <BusyOverlay />
      <ErrorPopup />
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
            labelled with their provenance — {demoRun
              ? <span className="prov prov-demo">DEMO</span>
              : <span className="prov prov-simulated">SIMULATED</span>} evidence is
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

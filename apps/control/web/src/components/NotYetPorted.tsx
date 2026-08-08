export function NotYetPorted({ section }: { section: string }) {
  return (
    <section>
      <div className="section-title"><h2>{section}</h2></div>
      <div className="card warn">
        <h3>Not yet ported to React</h3>
        <p>This section still exists in the vanilla-JS Control Centre (`apps/control/static/app.js`) and has not been migrated to the new React app yet. It is not user-visible — production continues to serve the vanilla app until every section is ported (see the migration plan's Phase 4).</p>
      </div>
    </section>
  )
}

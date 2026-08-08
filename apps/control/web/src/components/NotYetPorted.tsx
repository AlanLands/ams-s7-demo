export function NotYetPorted({ section }: { section: string }) {
  return (
    <section>
      <div className="section-title"><h2>{section}</h2></div>
      <div className="card warn">
        <h3>Unknown section</h3>
        <p>"{section}" isn't a recognized page. This usually means a stale value in your browser's saved
          navigation state — try selecting a page from the sidebar.</p>
      </div>
    </section>
  )
}

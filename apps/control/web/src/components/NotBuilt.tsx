import { SectionTitle } from './SectionTitle'

export function NotBuilt({ name, phase }: { name: string; phase: string }) {
  return (
    <section>
      <SectionTitle title={name} />
      <div className="card warn">
        <h3>Not built in this phase</h3>
        <p>
          {name} lands in {phase} of the implementation plan. This panel is a placeholder, deliberately not a mock — nothing on this surface pretends to be evidence it does not have.
        </p>
      </div>
    </section>
  )
}

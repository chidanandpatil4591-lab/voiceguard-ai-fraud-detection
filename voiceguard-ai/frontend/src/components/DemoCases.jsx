import { Bot, CheckCircle2, HelpCircle, UserRound } from 'lucide-react'

const CASES = [
  { id: 'human', label: 'Human voice', icon: UserRound },
  { id: 'synthetic', label: 'AI-generated voice', icon: Bot },
  { id: 'no-speech', label: 'No speech', icon: HelpCircle },
]

export default function DemoCases({ busy, onSelect }) {
  return (
    <section className="demo-cases" aria-labelledby="demo-cases-title">
      <div>
        <p className="eyebrow">PRESENTATION MODE</p>
        <h2 id="demo-cases-title">Show a known case</h2>
        <p>These repeatable fixtures use the same backend detector as uploaded audio.</p>
      </div>
      <div className="demo-case-buttons">
        {CASES.map(({ id, label, icon: Icon }) => (
          <button key={id} type="button" onClick={() => onSelect(id)} disabled={busy}>
            <Icon size={16} />
            {label}
            <CheckCircle2 size={14} />
          </button>
        ))}
      </div>
    </section>
  )
}
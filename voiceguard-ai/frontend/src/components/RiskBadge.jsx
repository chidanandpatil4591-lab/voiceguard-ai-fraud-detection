/**
 * RiskBadge — coloured pill displaying the risk level string.
 *
 * Props
 * -----
 * level : 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL' | undefined
 */
export function RiskBadge({ level }) {
  const tone = (level || 'pending').toLowerCase()
  return (
    <span className={`risk-badge ${tone}`}>{level || 'PENDING'}</span>
  )
}

/**
 * Stat — single labelled numeric value for the result stats row.
 *
 * Props
 * -----
 * label  : string
 * value  : string | number
 * suffix : string   (optional)
 * accent : string   (optional CSS class)
 */
export function Stat({ label, value, suffix = '', accent = '' }) {
  return (
    <div className="stat">
      <span>{label}</span>
      <strong className={accent}>
        {value}
        {suffix && <small>{suffix}</small>}
      </strong>
    </div>
  )
}

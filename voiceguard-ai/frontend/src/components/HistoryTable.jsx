import { Clock3, Trash2, UserRound } from 'lucide-react'
import { RiskBadge } from './RiskBadge'

/**
 * HistoryTable — audit trail of completed analyses with delete support.
 *
 * Props
 * -----
 * history    : array of analysis records
 * onDelete   : (analysisId) => void
 * onRefresh  : () => void
 */
export default function HistoryTable({ history, onDelete, onRefresh }) {
  const fmt = (v) =>
    Number.isFinite(Number(v)) ? Number(v).toFixed(1) : '0.0'

  return (
    <section className="panel history-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">05 / AUDIT TRAIL</p>
          <h2>Analysis history</h2>
        </div>
        <button className="icon-button" title="Refresh history" onClick={onRefresh}>
          ↺
        </button>
      </div>

      {history.length ? (
        <div className="history-table">
          <div className="history-head">
            <span>TIME</span>
            <span>FILE</span>
            <span>AI PROBABILITY</span>
            <span>RISK</span>
            <span>LEVEL</span>
            <span>MODE</span>
            <span></span>
          </div>
          {history.map((item) => (
            <div className="history-row" key={item.id}>
              <span>
                <Clock3 size={14} />
                {new Date(item.created_at).toLocaleTimeString([], {
                  hour: '2-digit',
                  minute: '2-digit',
                })}
              </span>
              <b title={item.filename}>{item.filename}</b>
              <span>{fmt(item.synthetic_probability)}%</span>
              <strong>{item.risk_score}/100</strong>
              <RiskBadge level={item.risk_level} />
              <span className="mode-text">{item.detection_mode}</span>
              <button
                className="delete-button"
                title="Delete record"
                onClick={() => onDelete(item.id)}
              >
                <Trash2 size={14} />
              </button>
            </div>
          ))}
        </div>
      ) : (
        <div className="history-empty">
          <UserRound size={20} />
          No completed analyses yet.
        </div>
      )}
    </section>
  )
}

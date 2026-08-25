import { Activity, AlertTriangle, CheckCircle2, ShieldCheck } from 'lucide-react'

/**
 * DashboardStats — top-of-page summary cards showing aggregate metrics.
 *
 * Props
 * -----
 * stats : { total_analyses, average_risk_score, critical_count,
 *            high_count, medium_count, low_count } | null
 */
export default function DashboardStats({ stats }) {
  if (!stats) return null

  return (
    <div className="dash-stats">
      <div className="dash-stat-card">
        <Activity size={16} />
        <div>
          <strong>{stats.total_analyses}</strong>
          <span>Total analyses</span>
        </div>
      </div>

      <div className="dash-stat-card">
        <AlertTriangle size={16} className="icon-critical" />
        <div>
          <strong className="critical-text">{stats.critical_count}</strong>
          <span>Critical threats</span>
        </div>
      </div>

      <div className="dash-stat-card">
        <AlertTriangle size={16} className="icon-high" />
        <div>
          <strong className="high-text">{stats.high_count}</strong>
          <span>High risk</span>
        </div>
      </div>

      <div className="dash-stat-card">
        <ShieldCheck size={16} className="icon-safe" />
        <div>
          <strong>{stats.low_count}</strong>
          <span>Low risk / safe</span>
        </div>
      </div>

      <div className="dash-stat-card">
        <CheckCircle2 size={16} />
        <div>
          <strong>{Number(stats.average_risk_score).toFixed(1)}</strong>
          <span>Avg risk score</span>
        </div>
      </div>
    </div>
  )
}

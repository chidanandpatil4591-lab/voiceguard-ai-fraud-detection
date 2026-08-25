import { AlertTriangle, X } from 'lucide-react'

/**
 * AlertBanner — in-app notification shown when analysis risk is HIGH or CRITICAL.
 *
 * Props
 * -----
 * alerts   : array of alert event objects
 * onDismiss : (alertId) => void
 */
export default function AlertBanner({ alerts, onDismiss }) {
  if (!alerts || alerts.length === 0) return null

  return (
    <div className="alert-banners" role="alert" aria-live="assertive">
      {alerts.map((alert) => (
        <div
          key={alert.id || alert.analysis_id}
          className={`alert-banner alert-${alert.level.toLowerCase()}`}
        >
          <AlertTriangle size={18} />
          <div className="alert-body">
            <strong>{alert.level} RISK ALERT</strong>
            <span>{alert.recommended_action}</span>
            {alert.indicators?.length > 0 && (
              <ul className="alert-indicators">
                {alert.indicators.slice(0, 3).map((ind) => (
                  <li key={ind}>{ind}</li>
                ))}
              </ul>
            )}
          </div>
          <button
            className="alert-dismiss"
            onClick={() => onDismiss(alert.id || alert.analysis_id)}
            aria-label="Dismiss alert"
          >
            <X size={15} />
          </button>
        </div>
      ))}
    </div>
  )
}

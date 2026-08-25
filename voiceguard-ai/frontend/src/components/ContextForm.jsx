import { AlertTriangle } from 'lucide-react'
import { RiskBadge } from './RiskBadge'

/**
 * ContextForm — caller and transaction context enrichment panel.
 *
 * Props
 * -----
 * context       : object   — current form values
 * onChange      : (patch) => void
 * onSubmit      : (e) => void
 * busy          : bool
 * contextResult : object | null
 */
export default function ContextForm({
  context,
  onChange,
  onSubmit,
  busy,
  contextResult,
}) {
  const riskTone = (level = 'LOW') => level.toLowerCase()

  return (
    <section className="panel protection-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">04 / TRANSACTION PROTECTION</p>
          <h2>Context changes the stakes.</h2>
          <p className="panel-description">
            Combine voice signals with caller and transaction context before
            authorising a sensitive request.
          </p>
        </div>
        <span className="protection-icon">
          <AlertTriangle size={23} />
        </span>
      </div>

      <form className="context-form" onSubmit={onSubmit}>
        <label>
          Caller name
          <input
            value={context.caller_name}
            onChange={(e) => onChange({ caller_name: e.target.value })}
            required
            maxLength={120}
          />
        </label>

        <label>
          Transaction type
          <select
            value={context.transaction_type}
            onChange={(e) => onChange({ transaction_type: e.target.value })}
          >
            <option value="fund_transfer">Fund transfer</option>
            <option value="credential_reset">Credential reset</option>
            <option value="payment_change">Payment change</option>
            <option value="other">Other</option>
          </select>
        </label>

        <label>
          Amount (INR)
          <input
            type="number"
            min="0"
            step="1"
            value={context.transaction_amount}
            onChange={(e) => onChange({ transaction_amount: e.target.value })}
          />
        </label>

        <label>
          Scenario
          <select
            value={context.scenario}
            onChange={(e) => onChange({ scenario: e.target.value })}
          >
            <option value="default">Default</option>
            <option value="banking">Banking</option>
            <option value="enterprise">Enterprise</option>
            <option value="government">Government</option>
          </select>
        </label>

        <label className="toggle-label">
          <input
            type="checkbox"
            checked={context.caller_known}
            onChange={(e) => onChange({ caller_known: e.target.checked })}
          />
          <span>Known caller</span>
        </label>

        <label className="toggle-label">
          <input
            type="checkbox"
            checked={context.urgent_request}
            onChange={(e) => onChange({ urgent_request: e.target.checked })}
          />
          <span>Urgent request</span>
        </label>

        <label className="toggle-label">
          <input
            type="checkbox"
            checked={context.sensitive_information_requested}
            onChange={(e) =>
              onChange({ sensitive_information_requested: e.target.checked })
            }
          />
          <span>Sensitive information requested</span>
        </label>

        <button className="secondary-button ctx-submit" disabled={busy}>
          {busy ? 'Calculating…' : 'Calculate contextual risk'}
        </button>
      </form>

      {contextResult && (
        <div className={`context-result ${riskTone(contextResult.risk_level)}`}>
          <div>
            <span>FINAL RISK</span>
            <strong>
              {contextResult.final_risk_score}
              <small>/100</small>
            </strong>
          </div>
          <div>
            <RiskBadge level={contextResult.risk_level} />
            <p>{contextResult.recommended_action}</p>
          </div>
          <div className="context-flags">
            {contextResult.indicators.map((ind) => (
              <span key={ind}>
                <AlertTriangle size={13} />
                {ind}
              </span>
            ))}
          </div>
        </div>
      )}
    </section>
  )
}

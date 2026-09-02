import { AlertTriangle, CheckCircle2, Download, FileAudio } from 'lucide-react'
import { RiskBadge, Stat } from './RiskBadge'

/**
 * VoiceAssessment — renders the voice analysis result panel.
 *
 * Props
 * -----
 * result       : analysis result object | null
 * liveResult   : rolling real-time result | null
 * isLive       : bool — prefer live result when true
 * liveStatus   : string — e.g. "LIVE · 3.0 SEC"
 * onDownload   : () => void
 */
export default function VoiceAssessment({
  result,
  liveResult,
  isLive,
  liveStatus,
  onDownload,
}) {
  const display = isLive && liveResult ? liveResult : result

  const fmt = (v) =>
    Number.isFinite(Number(v)) ? Number(v).toFixed(1) : '0.0'

  function verdictFor(assessment) {
    if (!assessment) return 'PENDING'
    if (assessment.synthetic_probability >= 60) return 'AI-GENERATED'
    if (assessment.human_probability >= 70) return 'HUMAN-LIKELY'
    return 'UNVERIFIED'
  }

  return (
    <section className="panel result-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">02 / VOICE ASSESSMENT</p>
          <h2>Signal verdict</h2>
          {liveStatus && isLive && (
            <small className="live-status">{liveStatus}</small>
          )}
          {display && (
            <strong className={`verdict-label ${verdictFor(display).toLowerCase()}`}>
              {verdictFor(display)}
            </strong>
          )}
        </div>
        {display && <RiskBadge level={display.risk_level} />}
      </div>

      {display ? (
        <>
          {/* Probability row */}
          <div className="probability-row">
            <div>
              <span>Human probability</span>
              <strong className="human-value">
                {fmt(display.human_probability)}<small>%</small>
              </strong>
            </div>
            <div>
              <span>AI-generated voice probability</span>
              <strong>
                {fmt(display.synthetic_probability)}<small>%</small>
              </strong>
            </div>
          </div>

          {/* Risk meter */}
          <div className="meter" role="progressbar" aria-valuenow={display.synthetic_probability} aria-valuemin={0} aria-valuemax={100}>
            <span style={{ width: `${display.synthetic_probability}%` }} />
          </div>

          {/* Stats row */}
          <div className="result-stats">
            <Stat label="Risk score" value={display.risk_score} suffix="/100" accent="risk-number" />
            <Stat label="Confidence" value={display.confidence} suffix="%" />
            <Stat label="Mode" value={display.detection_mode} />
          </div>

          {/* Action box */}
          <div className="action-box">
            <AlertTriangle size={18} />
            <div>
              <span>RECOMMENDED ACTION</span>
              <strong>{display.recommended_action}</strong>
            </div>
          </div>

          {/* Indicators */}
          <div className="indicators">
            <span>DETECTED INDICATORS</span>
            {display.indicators.map((ind) => (
              <div key={ind}>
                <CheckCircle2 size={15} />
                {ind}
              </div>
            ))}
          </div>

          {/* Feature telemetry */}
          {result?.features && !isLive && (
            <div className="feature-telemetry">
              <p className="eyebrow" style={{ marginTop: '22px' }}>ACOUSTIC FINGERPRINT — EVIDENCE v3</p>
              <div className="feature-bars">
                {[
                  ['Jitter ×1000', result.features.jitter * 1000],
                  ['Shimmer ×100', result.features.shimmer * 100],
                  ['HNR (dB)', result.features.harmonic_to_noise_ratio],
                  ['F0 range (Hz)', result.features.f0_range],
                  ['Spectral flux', result.features.spectral_flux_mean],
                  ['MFCC Δ-std', result.features.mfcc_delta_std],
                  ['RMS modulation', result.features.rms_modulation * 100],
                  ['HF band ratio %', result.features.sub_band_ratio_high * 100],
                  ['Spectral flatness', result.features.spectral_flatness * 100],
                  ['Silence ratio %', result.features.silence_ratio * 100],
                ].map(([label, value]) => (
                  <div className="feature-row" key={label}>
                    <span>{label}</span>
                    <div>
                      <i style={{ width: `${Math.min(100, Math.abs(Number(value)))}%` }} />
                    </div>
                    <b>{Number(value).toFixed(2)}</b>
                  </div>
                ))}
              </div>
              <div className="telemetry-meta">
                {result.duration_seconds?.toFixed(2)} SEC · {result.sample_rate} HZ
              </div>
            </div>
          )}

          {/* Download button */}
          {result && onDownload && (
            <button className="download-button" type="button" onClick={onDownload}>
              <Download size={15} /> Download incident brief
            </button>
          )}
        </>
      ) : (
        <div className="empty-state">
          <FileAudio size={38} />
          <strong>Awaiting a recording</strong>
          <span>Your acoustic assessment will appear here.</span>
        </div>
      )}
    </section>
  )
}

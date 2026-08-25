import { useCallback, useEffect, useState } from 'react'
import { Activity, AlertTriangle, PhoneCall, RefreshCw, ShieldCheck, Zap } from 'lucide-react'

import AlertBanner from './components/AlertBanner'
import AudioDropzone from './components/AudioDropzone'
import ContextForm from './components/ContextForm'
import DashboardStats from './components/DashboardStats'
import HistoryTable from './components/HistoryTable'
import LiveCapture from './components/LiveCapture'
import VoiceAssessment from './components/VoiceAssessment'

import {
  analyzeAudio,
  analyzeContext,
  deleteHistory,
  fetchHistory,
  fetchStats,
} from './services/api'

// ---------------------------------------------------------------------------
// Initial state
// ---------------------------------------------------------------------------

const INITIAL_CONTEXT = {
  caller_name: 'CEO',
  caller_known: false,
  transaction_type: 'fund_transfer',
  transaction_amount: 1500000,
  urgent_request: true,
  sensitive_information_requested: true,
  scenario: 'banking',
}

// ---------------------------------------------------------------------------
// App
// ---------------------------------------------------------------------------

export default function App() {
  const [file, setFile] = useState(null)
  const [result, setResult] = useState(null)
  const [history, setHistory] = useState([])
  const [stats, setStats] = useState(null)
  const [context, setContext] = useState(INITIAL_CONTEXT)
  const [contextResult, setContextResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const [contextBusy, setContextBusy] = useState(false)
  const [error, setError] = useState('')
  const [liveResult, setLiveResult] = useState(null)
  const [liveStatus, setLiveStatus] = useState('')
  const [isLive, setIsLive] = useState(false)
  const [alerts, setAlerts] = useState([])

  // ------- data fetchers ---------------------------------------------------

  const refreshHistory = useCallback(async () => {
    try {
      setHistory(await fetchHistory())
    } catch (err) {
      setError(err.message)
    }
  }, [])

  const refreshStats = useCallback(async () => {
    try {
      setStats(await fetchStats())
    } catch {
      // stats are non-critical; fail silently
    }
  }, [])

  useEffect(() => {
    refreshHistory()
    refreshStats()
  }, [refreshHistory, refreshStats])

  // ------- live recording callbacks ----------------------------------------

  function handleLiveResult(update) {
    setLiveResult(update)
    setLiveStatus(`LIVE · ${Number(update.stream_seconds).toFixed(1)} SEC`)
    setIsLive(true)
  }

  function handleLiveFile(capturedFile) {
    setFile(capturedFile)
    setIsLive(false)
  }

  function handleLiveError(msg) {
    setError(msg)
  }

  // ------- analysis --------------------------------------------------------

  async function handleAnalyze(event) {
    event.preventDefault()
    if (!file) { setError('Please upload or record an audio file.'); return }
    setBusy(true)
    setError('')
    setResult(null)
    setContextResult(null)
    try {
      const analysis = await analyzeAudio(file)
      setResult(analysis)
      // Surface alert events from backend
      if (analysis.alert_events?.length) {
        setAlerts((prev) => [...analysis.alert_events, ...prev])
      }
      await refreshHistory()
      await refreshStats()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function handleContext(event) {
    event.preventDefault()
    setContextBusy(true)
    setError('')
    try {
      const res = await analyzeContext({
        ...context,
        transaction_amount: Number(context.transaction_amount),
        voice_synthetic_probability: result?.synthetic_probability ?? 0,
        voice_risk_score: result?.risk_score ?? 0,
      })
      setContextResult(res)
      if (res.alert_events?.length) {
        setAlerts((prev) => [...res.alert_events, ...prev])
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setContextBusy(false)
    }
  }

  // ------- history delete --------------------------------------------------

  async function handleDeleteHistory(id) {
    try {
      await deleteHistory(id)
      setHistory((prev) => prev.filter((item) => item.id !== id))
      await refreshStats()
    } catch (err) {
      setError(err.message)
    }
  }

  // ------- alert dismiss ---------------------------------------------------

  function handleDismissAlert(alertId) {
    setAlerts((prev) => prev.filter((a) => (a.id || a.analysis_id) !== alertId))
  }

  // ------- incident brief download -----------------------------------------

  function downloadIncidentBrief() {
    if (!result) return
    const fmt = (v) => (Number.isFinite(Number(v)) ? Number(v).toFixed(1) : '0.0')
    const lines = [
      'VOICEGUARD AI — INCIDENT BRIEF',
      `Generated  : ${new Date().toLocaleString()}`,
      `Recording  : ${result.filename}`,
      `Duration   : ${result.duration_seconds?.toFixed(2)}s @ ${result.sample_rate} Hz`,
      `Voice risk : ${result.risk_score}/100 (${result.risk_level})`,
      `AI voice probability : ${fmt(result.synthetic_probability)}%`,
      `Human probability    : ${fmt(result.human_probability)}%`,
      `Confidence           : ${fmt(result.confidence)}%`,
      `Detection mode       : ${result.detection_mode}`,
      `Recommended action   : ${contextResult?.recommended_action || result.recommended_action}`,
      `Indicators : ${(contextResult?.indicators || result.indicators).join('; ')}`,
      '',
      'PRIVACY NOTE: This brief contains assessment metadata only.',
      'No audio was retained; raw uploads are deleted immediately after processing.',
    ]
    const blob = new Blob([lines.join('\n')], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `voiceguard-incident-${result.analysis_id || 'brief'}.txt`
    link.click()
    URL.revokeObjectURL(url)
  }

  // ------- render ----------------------------------------------------------

  return (
    <div className="app-shell">
      {/* ── Top bar ── */}
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark"><ShieldCheck size={20} /></span>
          <div>
            <b>VOICEGUARD <em>AI</em></b>
            <span>VOICE INTEGRITY OPERATIONS</span>
          </div>
        </div>
        <div className="topbar-right">
          <span className="live-dot" />
          LOCAL ANALYSIS NODE
          <span className="topbar-divider" />
          <span className="mode-chip">EVIDENCE v3</span>
        </div>
      </header>

      <main className="dashboard">
        {/* ── Intro ── */}
        <section className="intro">
          <div>
            <p className="kicker">REAL-TIME DEFENCE CONSOLE / SIH 2024</p>
            <h1>Voice integrity,<br /><span>made visible.</span></h1>
            <p className="lede">
              Detect AI-generated and cloned voices in real time — before a
              high-impact conversation becomes a fraud incident.
              Supports Indian accents, multilingual contexts, and diverse
              deployment scenarios.
            </p>
          </div>
          <div className="intro-signal">
            <Activity size={18} />
            <span>ENGINE STATUS</span>
            <strong>READY</strong>
            <small>Log-odds evidence model · 10 acoustic dimensions</small>
          </div>
        </section>

        {/* ── Dashboard stats ── */}
        <DashboardStats stats={stats} />

        {/* ── In-app alerts ── */}
        <AlertBanner alerts={alerts} onDismiss={handleDismissAlert} />

        {/* ── Error banner ── */}
        {error && (
          <div className="error-banner" role="alert">
            <AlertTriangle size={17} />
            {error}
            <button onClick={() => setError('')}>Dismiss</button>
          </div>
        )}

        {/* ── Workspace grid: upload + result ── */}
        <section className="workspace-grid">
          {/* Upload panel */}
          <form className="panel upload-panel" onSubmit={handleAnalyze}>
            <div className="panel-heading">
              <div>
                <p className="eyebrow">01 / AUDIO INTAKE</p>
                <h2>Analyse a recording</h2>
              </div>
            </div>

            <AudioDropzone
              file={file}
              onChange={(f) => { setFile(f); setError('') }}
              disabled={busy}
            />

            <LiveCapture
              onLiveResult={handleLiveResult}
              onFile={handleLiveFile}
              onError={handleLiveError}
              disabled={busy}
            />

            <button className="primary-button" disabled={busy}>
              {busy ? (
                <><RefreshCw className="spin" size={17} /> Extracting acoustic signals…</>
              ) : (
                <><Zap size={17} /> Analyse voice</>
              )}
            </button>

            <div className="privacy-note">
              <ShieldCheck size={15} />
              <span>
                Privacy-first pipeline —&nbsp;
                <b>audio deleted immediately after processing</b>
              </span>
            </div>
          </form>

          {/* Assessment panel */}
          <VoiceAssessment
            result={result}
            liveResult={liveResult}
            isLive={isLive}
            liveStatus={liveStatus}
            onDownload={downloadIncidentBrief}
          />
        </section>

        {/* ── Context analysis ── */}
        <ContextForm
          context={context}
          onChange={(patch) => setContext((prev) => ({ ...prev, ...patch }))}
          onSubmit={handleContext}
          busy={contextBusy}
          contextResult={contextResult}
        />

        {/* ── Response playbook ── */}
        {result && (
          <div className="response-playbook">
            <div>
              <p className="eyebrow">RESPONSE WORKFLOW</p>
              <h3>Verify before you authorise.</h3>
              <p>
                Place the request on hold, call the known number independently,
                and require a second approval for sensitive actions.
                For Indian banking scenarios, follow RBI OTP + call-back guidelines.
              </p>
            </div>
            <div className="response-actions">
              <span><PhoneCall size={16} /> Independent call-back</span>
            </div>
          </div>
        )}

        {/* ── Audit trail ── */}
        <HistoryTable
          history={history}
          onDelete={handleDeleteHistory}
          onRefresh={refreshHistory}
        />
      </main>

      <footer>
        <span>
          VOICEGUARD AI — AI-Powered Voice Cloning Detection &amp; Prevention
        </span>
        <span>
          Supports Indian accents &amp; multilingual contexts ·
          Acoustic assessment only — not a guarantee of authenticity ·
          AICTE SIH 2024
        </span>
      </footer>
    </div>
  )
}

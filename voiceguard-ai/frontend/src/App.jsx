import { useEffect, useRef, useState } from 'react'
import { Activity, AlertTriangle, AudioLines, CheckCircle2, Clock3, Download, FileAudio, Mic, PhoneCall, RefreshCw, ShieldCheck, Square, UploadCloud, UserRound, Zap } from 'lucide-react'
import { analyzeAudio, analyzeContext, fetchHistory, realtimeSocketUrl } from './services/api'

const initialContext = {
  caller_name: 'CEO', caller_known: false, transaction_type: 'fund_transfer',
  transaction_amount: 1500000, urgent_request: true,
  sensitive_information_requested: true,
}

function riskTone(level = 'LOW') {
  return level.toLowerCase()
}

function Stat({ label, value, suffix = '', accent = '' }) {
  return <div className="stat"><span>{label}</span><strong className={accent}>{value}<small>{suffix}</small></strong></div>
}

function RiskBadge({ level }) {
  return <span className={`risk-badge ${riskTone(level)}`}>{level || 'PENDING'}</span>
}

export default function App() {
  const [file, setFile] = useState(null)
  const [result, setResult] = useState(null)
  const [history, setHistory] = useState([])
  const [context, setContext] = useState(initialContext)
  const [contextResult, setContextResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const [contextBusy, setContextBusy] = useState(false)
  const [error, setError] = useState('')
  const [recording, setRecording] = useState(false)
  const [recordingSeconds, setRecordingSeconds] = useState(0)
  const [liveResult, setLiveResult] = useState(null)
  const [liveStatus, setLiveStatus] = useState('')
  const recorderRef = useRef(null)
  const streamRef = useRef(null)
  const chunksRef = useRef([])
  const timerRef = useRef(null)
  const audioContextRef = useRef(null)
  const realtimeSocketRef = useRef(null)

  async function refreshHistory() {
    try { setHistory(await fetchHistory()) } catch (requestError) { setError(requestError.message) }
  }

  useEffect(() => { refreshHistory() }, [])
  useEffect(() => () => {
    clearInterval(timerRef.current)
    streamRef.current?.getTracks().forEach((track) => track.stop())
    audioContextRef.current?.close()
    realtimeSocketRef.current?.close()
  }, [])

  async function startRecording() {
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      setError('Live capture is not supported in this browser. Please upload an audio recording instead.')
      return
    }
    try {
      setError('')
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mimeType = ['audio/webm;codecs=opus', 'audio/ogg;codecs=opus'].find((type) => MediaRecorder.isTypeSupported(type))
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined)
      const audioContext = new AudioContext()
      const realtimeSocket = new WebSocket(realtimeSocketUrl())
      const processor = audioContext.createScriptProcessor(4096, 1, 1)
      const silentOutput = audioContext.createGain()
      silentOutput.gain.value = 0
      const source = audioContext.createMediaStreamSource(stream)
      realtimeSocket.onopen = () => realtimeSocket.send(JSON.stringify({ type: 'start', sample_rate: audioContext.sampleRate }))
      realtimeSocket.onmessage = (event) => {
        const update = JSON.parse(event.data)
        if (update.status === 'update') {
          setLiveResult(update)
          setLiveStatus(`LIVE / ${update.stream_seconds.toFixed(1)} SEC`)
        }
      }
      processor.onaudioprocess = (event) => {
        if (realtimeSocket.readyState === WebSocket.OPEN) {
          realtimeSocket.send(event.inputBuffer.getChannelData(0).slice().buffer)
        }
      }
      source.connect(processor)
      processor.connect(silentOutput)
      silentOutput.connect(audioContext.destination)
      streamRef.current = stream
      audioContextRef.current = audioContext
      realtimeSocketRef.current = realtimeSocket
      chunksRef.current = []
      recorder.ondataavailable = (event) => { if (event.data.size) chunksRef.current.push(event.data) }
      recorder.onstop = () => {
        const type = recorder.mimeType || 'audio/webm'
        const extension = type.includes('ogg') ? 'ogg' : 'webm'
        setFile(new File([new Blob(chunksRef.current, { type })], `live-capture-${Date.now()}.${extension}`, { type }))
        stream.getTracks().forEach((track) => track.stop())
        processor.disconnect()
        silentOutput.disconnect()
        source.disconnect()
        audioContext.close()
        if (realtimeSocket.readyState === WebSocket.OPEN) realtimeSocket.send(JSON.stringify({ type: 'end' }))
        realtimeSocket.close()
        clearInterval(timerRef.current)
        setRecording(false)
      }
      recorder.start()
      recorderRef.current = recorder
      setRecordingSeconds(0)
      timerRef.current = setInterval(() => setRecordingSeconds((seconds) => seconds + 1), 1000)
      setRecording(true)
    } catch {
      setError('Microphone permission was not granted. Please allow access or upload a recording.')
    }
  }

  function stopRecording() {
    if (recorderRef.current?.state === 'recording') recorderRef.current.stop()
  }

  async function handleAnalyze(event) {
    event.preventDefault()
    if (!file) { setError('Please upload an audio file.'); return }
    setBusy(true); setError('')
    try {
      const analysis = await analyzeAudio(file)
      setResult(analysis)
      await refreshHistory()
    } catch (requestError) { setError(requestError.message) } finally { setBusy(false) }
  }

  async function handleContext(event) {
    event.preventDefault(); setContextBusy(true); setError('')
    try {
      setContextResult(await analyzeContext({
        ...context,
        transaction_amount: Number(context.transaction_amount),
        voice_synthetic_probability: result?.synthetic_probability || 0,
        voice_risk_score: result?.risk_score || 0,
      }))
    } catch (requestError) { setError(requestError.message) } finally { setContextBusy(false) }
  }

  function downloadIncidentBrief() {
    if (!result) return
    const report = [
      'VOICEGUARD AI / INCIDENT BRIEF',
      `Generated: ${new Date().toLocaleString()}`,
      `Recording: ${result.filename}`,
      `Voice risk: ${result.risk_score}/100 (${result.risk_level})`,
      `Synthetic voice probability: ${result.synthetic_probability}%`,
      `Recommended action: ${contextResult?.recommended_action || result.recommended_action}`,
      `Indicators: ${(contextResult?.indicators || result.indicators).join('; ')}`,
      'Privacy note: This brief contains assessment metadata only; no audio is included.',
    ].join('\n')
    const url = URL.createObjectURL(new Blob([report], { type: 'text/plain' }))
    const link = document.createElement('a')
    link.href = url
    link.download = `voiceguard-incident-${result.analysis_id || 'brief'}.txt`
    link.click()
    URL.revokeObjectURL(url)
  }

  const featureEntries = result ? [
    ['MFCC texture', result.features.mfcc_1_std],
    ['Spectral spread', result.features.spectral_bandwidth_mean],
    ['Pitch variation', result.features.pitch_std],
    ['Voice activity', (1 - result.features.silence_ratio) * 100],
    ['Energy consistency', result.features.rms_energy_std * 100],
  ] : []
  const displayResult = recording && liveResult ? liveResult : result

  return <div className="app-shell">
    <header className="topbar">
      <div className="brand"><span className="brand-mark"><ShieldCheck size={20} /></span><div><b>VOICEGUARD <em>AI</em></b><span>VOICE INTEGRITY OPERATIONS</span></div></div>
      <div className="topbar-right"><span className="live-dot" /> LOCAL ANALYSIS NODE <span className="topbar-divider" /> <span className="mode-chip">DEMO MODE</span></div>
    </header>

    <main className="dashboard">
      <section className="intro"><div><p className="kicker">REAL-TIME DEFENSE CONSOLE / 01</p><h1>Voice integrity,<br /><span>made visible.</span></h1><p className="lede">Assess acoustic signals for voice impersonation risk before a high-impact conversation becomes a high-impact incident.</p></div><div className="intro-signal"><Activity size={18} /><span>ENGINE STATUS</span><strong>READY</strong><small>CPU inference / local only</small></div></section>

      {error && <div className="error-banner"><AlertTriangle size={17} />{error}<button onClick={() => setError('')}>Dismiss</button></div>}

      <section className="workspace-grid">
        <form className="panel upload-panel" onSubmit={handleAnalyze}>
          <div className="panel-heading"><div><p className="eyebrow">01 / AUDIO INTAKE</p><h2>Analyze a recording</h2></div><AudioLines className="panel-icon" /></div>
          <label className={`dropzone ${file ? 'has-file' : ''}`}>
            <input type="file" accept=".wav,.mp3,.m4a,.flac,.ogg,audio/*" onChange={(event) => { setFile(event.target.files[0]); setError('') }} />
            {file ? <><CheckCircle2 size={29} /><strong>{file.name}</strong><span>{(file.size / 1024 / 1024).toFixed(2)} MB / ready for analysis</span></> : <><UploadCloud size={29} /><strong>Drop a voice recording here</strong><span>WAV, MP3, M4A, FLAC, OGG or WebM / max 25 MB</span><small>Raw audio is deleted after processing.</small></>}
          </label>
          <button type="button" className="secondary-button" onClick={recording ? stopRecording : startRecording} disabled={busy}>{recording ? <><Square size={16} /> Stop live capture ({recordingSeconds}s)</> : <><Mic size={16} /> Start live capture</>}</button>
          <button className="primary-button" disabled={busy}>{busy ? <><RefreshCw className="spin" size={17} /> Extracting acoustic signals...</> : <><Zap size={17} /> Analyze voice</>}</button>
          <div className="privacy-note"><ShieldCheck size={15} /><span>Privacy-first pipeline <b>Temporary processing only</b></span></div>
        </form>

        <section className="panel result-panel">
          <div className="panel-heading"><div><p className="eyebrow">02 / VOICE ASSESSMENT</p><h2>Signal verdict</h2>{liveStatus && recording && <small className="live-status">{liveStatus}</small>}</div>{displayResult && <RiskBadge level={displayResult.risk_level} />}</div>
          {displayResult ? <><div className="probability-row"><div><span>AI-generated voice probability</span><strong>{displayResult.synthetic_probability}<small>%</small></strong></div><div><span>Human probability</span><strong className="human-value">{displayResult.human_probability}<small>%</small></strong></div></div><div className="meter"><span style={{ width: `${displayResult.synthetic_probability}%` }} /></div><div className="result-stats"><Stat label="Risk score" value={displayResult.risk_score} suffix="/100" accent="risk-number" /><Stat label="Confidence" value={displayResult.confidence} suffix="%" /><Stat label="Mode" value={displayResult.detection_mode} /></div><div className="action-box"><AlertTriangle size={18} /><div><span>RECOMMENDED ACTION</span><strong>{displayResult.recommended_action}</strong></div></div><div className="indicators"><span>DETECTED INDICATORS</span>{displayResult.indicators.map((indicator) => <div key={indicator}><CheckCircle2 size={15} />{indicator}</div>)}</div></> : <div className="empty-state"><FileAudio size={38} /><strong>Awaiting a recording</strong><span>Your acoustic assessment will appear here.</span></div>}
        </section>
      </section>

      {result && <section className="panel features-panel"><div className="panel-heading"><div><p className="eyebrow">03 / FEATURE TELEMETRY</p><h2>Acoustic fingerprint</h2></div><span className="subtle-label">{result.duration_seconds.toFixed(2)} SEC / {result.sample_rate} HZ</span></div><div className="feature-bars">{featureEntries.map(([label, value]) => <div className="feature-row" key={label}><span>{label}</span><div><i style={{ width: `${Math.min(100, Math.abs(value))}%` }} /></div><b>{Number(value).toFixed(2)}</b></div>)}</div></section>}

      <section className="panel protection-panel"><div className="panel-heading"><div><p className="eyebrow">04 / TRANSACTION PROTECTION MODE</p><h2>Context changes the stakes.</h2><p className="panel-description">Combine voice signals with caller and transaction context before authorizing a sensitive request.</p></div><span className="protection-icon"><ShieldCheck size={23} /></span></div><form className="context-form" onSubmit={handleContext}><label>Caller name<input value={context.caller_name} onChange={(e) => setContext({ ...context, caller_name: e.target.value })} /></label><label>Transaction type<select value={context.transaction_type} onChange={(e) => setContext({ ...context, transaction_type: e.target.value })}><option value="fund_transfer">Fund transfer</option><option value="credential_reset">Credential reset</option><option value="payment_change">Payment change</option><option value="other">Other</option></select></label><label>Amount (INR)<input type="number" min="0" value={context.transaction_amount} onChange={(e) => setContext({ ...context, transaction_amount: e.target.value })} /></label><label className="toggle-label"><input type="checkbox" checked={context.caller_known} onChange={(e) => setContext({ ...context, caller_known: e.target.checked })} /><span>Known caller</span></label><label className="toggle-label"><input type="checkbox" checked={context.urgent_request} onChange={(e) => setContext({ ...context, urgent_request: e.target.checked })} /><span>Urgent request</span></label><label className="toggle-label"><input type="checkbox" checked={context.sensitive_information_requested} onChange={(e) => setContext({ ...context, sensitive_information_requested: e.target.checked })} /><span>Sensitive information requested</span></label><button className="secondary-button" disabled={contextBusy}>{contextBusy ? 'Calculating...' : 'Calculate contextual risk'}</button></form>{contextResult && <div className={`context-result ${riskTone(contextResult.risk_level)}`}><div><span>FINAL RISK</span><strong>{contextResult.final_risk_score}<small>/100</small></strong></div><div><RiskBadge level={contextResult.risk_level} /><p>{contextResult.recommended_action}</p></div><div className="context-flags">{contextResult.indicators.map((indicator) => <span key={indicator}><AlertTriangle size={13} />{indicator}</span>)}</div></div>}{result && <div className="response-playbook"><div><p className="eyebrow">RESPONSE WORKFLOW</p><h3>Verify before you authorize.</h3><p>Place the request on hold, call the known number independently, and require a second approval for sensitive actions.</p></div><div className="response-actions"><span><PhoneCall size={16} /> Independent call-back</span><button type="button" onClick={downloadIncidentBrief}><Download size={16} /> Download incident brief</button></div></div>}</section>

      <section className="panel history-panel"><div className="panel-heading"><div><p className="eyebrow">05 / AUDIT TRAIL</p><h2>Analysis history</h2></div><button className="icon-button" title="Refresh history" onClick={refreshHistory}><RefreshCw size={17} /></button></div>{history.length ? <div className="history-table"><div className="history-head"><span>TIME</span><span>FILE</span><span>AI PROBABILITY</span><span>RISK</span><span>LEVEL</span><span>MODE</span></div>{history.map((item) => <div className="history-row" key={item.id}><span><Clock3 size={14} />{new Date(item.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span><b>{item.filename}</b><span>{item.synthetic_probability}%</span><strong>{item.risk_score}/100</strong><RiskBadge level={item.risk_level} /><span className="mode-text">{item.detection_mode}</span></div>)}</div> : <div className="history-empty"><UserRound size={20} />No completed analyses yet.</div>}</section>
    </main>
    <footer><span>VOICEGUARD AI / LOCAL HACKATHON MVP</span><span>Baseline acoustic assessment / not a guarantee of authenticity</span></footer>
  </div>
}

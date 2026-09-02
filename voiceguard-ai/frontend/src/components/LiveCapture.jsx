import { useEffect, useRef, useState } from 'react'
import { Mic, Square } from 'lucide-react'
import { realtimeSocketUrl } from '../services/api'

/**
 * LiveCapture — microphone recording with real-time WebSocket streaming.
 *
 * Uses AudioWorklet where available, with a ScriptProcessorNode fallback
 * for older browsers.
 *
 * Props
 * -----
 * onLiveResult : (update) => void   — called on each rolling assessment
 * onFile       : (File) => void     — called with the recorded file on stop
 * onError      : (msg) => void
 * disabled     : bool
 */
export default function LiveCapture({ onLiveResult, onFile, onError, disabled = false }) {
  const [recording, setRecording] = useState(false)
  const [seconds, setSeconds] = useState(0)
  const [liveStatus, setLiveStatus] = useState('')

  const recorderRef = useRef(null)
  const streamRef = useRef(null)
  const chunksRef = useRef([])
  const timerRef = useRef(null)
  const audioContextRef = useRef(null)
  const socketRef = useRef(null)
  const processorRef = useRef(null)

  // Cleanup on unmount
  useEffect(() => () => _cleanup(), [])

  function _cleanup() {
    clearInterval(timerRef.current)
    processorRef.current?.disconnect()
    streamRef.current?.getTracks().forEach((t) => t.stop())
    audioContextRef.current?.close()
    if (socketRef.current?.readyState === WebSocket.OPEN) {
      socketRef.current.close()
    }
  }

  function _sendPCM(channelData) {
    if (socketRef.current?.readyState === WebSocket.OPEN) {
      socketRef.current.send(channelData.slice().buffer)
    }
  }

  async function _attachScriptProcessor(audioContext, source) {
    // Fallback for browsers without AudioWorklet support
    const processor = audioContext.createScriptProcessor(4096, 1, 1)
    const silentGain = audioContext.createGain()
    silentGain.gain.value = 0
    processor.onaudioprocess = (e) => _sendPCM(e.inputBuffer.getChannelData(0))
    source.connect(processor)
    processor.connect(silentGain)
    silentGain.connect(audioContext.destination)
    processorRef.current = processor
    return processor
  }

  async function _attachWorklet(audioContext, source) {
    // Inline worklet code as a blob URL to avoid needing a separate file
    const workletCode = `
      class PCMSender extends AudioWorkletProcessor {
        process(inputs) {
          const channel = inputs[0]?.[0]
          if (channel) this.port.postMessage(channel)
          return true
        }
      }
      registerProcessor('pcm-sender', PCMSender)
    `
    const blob = new Blob([workletCode], { type: 'application/javascript' })
    const blobUrl = URL.createObjectURL(blob)
    await audioContext.audioWorklet.addModule(blobUrl)
    URL.revokeObjectURL(blobUrl)
    const workletNode = new AudioWorkletNode(audioContext, 'pcm-sender')
    workletNode.port.onmessage = (e) => _sendPCM(e.data)
    source.connect(workletNode)
    processorRef.current = workletNode
    return workletNode
  }

  async function startRecording() {
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      onError('Live capture is not supported in this browser. Please upload a recording.')
      return
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mimeType = ['audio/webm;codecs=opus', 'audio/ogg;codecs=opus'].find(
        (t) => MediaRecorder.isTypeSupported(t),
      )
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined)
      const audioContext = new AudioContext()
      const source = audioContext.createMediaStreamSource(stream)
      const socket = new WebSocket(realtimeSocketUrl())

      socket.onopen = () =>
        socket.send(JSON.stringify({ type: 'start', sample_rate: audioContext.sampleRate }))
      socket.onmessage = (e) => {
        const update = JSON.parse(e.data)
        if (update.status === 'update') {
          onLiveResult(update)
          setLiveStatus(`LIVE · ${Number(update.stream_seconds).toFixed(1)} SEC`)
        }
      }
      socket.onerror = () => onError('Real-time socket error. Falling back to file upload.')

      // Prefer AudioWorklet; fall back to deprecated ScriptProcessorNode
      if (audioContext.audioWorklet) {
        await _attachWorklet(audioContext, source)
      } else {
        await _attachScriptProcessor(audioContext, source)
      }

      chunksRef.current = []
      recorder.ondataavailable = (e) => { if (e.data.size) chunksRef.current.push(e.data) }
      recorder.onstop = () => {
        const type = recorder.mimeType || 'audio/webm'
        const ext = type.includes('ogg') ? 'ogg' : 'webm'
        onFile(
          new File(
            [new Blob(chunksRef.current, { type })],
            `live-capture-${Date.now()}.${ext}`,
            { type },
          ),
        )
        stream.getTracks().forEach((t) => t.stop())
        processorRef.current?.disconnect()
        if (socket.readyState === WebSocket.OPEN) {
          socket.send(JSON.stringify({ type: 'end' }))
        }
        socket.close()
        audioContext.close()
        clearInterval(timerRef.current)
        setRecording(false)
        setLiveStatus('')
      }

      recorder.start()
      recorderRef.current = recorder
      streamRef.current = stream
      audioContextRef.current = audioContext
      socketRef.current = socket
      setSeconds(0)
      timerRef.current = setInterval(() => setSeconds((s) => s + 1), 1000)
      setRecording(true)
    } catch {
      onError('Microphone permission denied. Please allow access or upload a recording.')
    }
  }

  function stopRecording() {
    if (recorderRef.current?.state === 'recording') recorderRef.current.stop()
  }

  return (
    <div className="live-capture">
      <button
        type="button"
        className="secondary-button"
        onClick={recording ? stopRecording : startRecording}
        disabled={disabled}
      >
        {recording ? (
          <><Square size={16} /> Stop live capture ({seconds}s)</>
        ) : (
          <><Mic size={16} /> Start live capture</>
        )}
      </button>
      {!recording && !liveStatus && (
        <span className="capture-hint">Speak clearly for 3–5 seconds</span>
      )}
      {liveStatus && <span className="live-status-chip">{liveStatus}</span>}
    </div>
  )
}

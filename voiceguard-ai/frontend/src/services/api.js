/**
 * VoiceGuard AI — API service layer.
 *
 * VITE_API_URL should point to the deployed FastAPI service, e.g.
 * https://voiceguard-api.example.com/api.  Falls back to /api for
 * same-origin serving (production) or the local proxy (development).
 */

const API_BASE = (import.meta.env.VITE_API_URL || '/api').replace(/\/$/, '')

/**
 * Shared fetch wrapper. Parses JSON and throws meaningful errors.
 */
async function request(path, options = {}) {
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers: {
        'x-tunnel-skip-browser-warning': 'true',
        ...(options.headers || {}),
      },
    })

    let payload
    const contentType = response.headers.get('content-type') || ''
    if (contentType.includes('application/json')) {
      payload = await response.json()
    } else {
      payload = { detail: await response.text() }
    }

    if (!response.ok) {
      throw new Error(payload?.detail || `Server error ${response.status}`)
    }
    return payload
  } catch (error) {
    if (error instanceof TypeError) {
      throw new Error('Cannot reach the backend server. Is it running?')
    }
    throw error
  }
}

// ---------------------------------------------------------------------------
// Voice analysis
// ---------------------------------------------------------------------------

export function analyzeAudio(file) {
  const formData = new FormData()
  formData.append('file', file)
  return request('/analyze', { method: 'POST', body: formData })
}

export function fetchDemoCase(caseName) {
  return request(`/demo/${encodeURIComponent(caseName)}`)
}

export function analyzeContext(payload) {
  return request('/analyze/context', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

// ---------------------------------------------------------------------------
// History
// ---------------------------------------------------------------------------

export function fetchHistory(limit = 50) {
  return request(`/history?limit=${limit}`)
}

export function deleteHistory(analysisId) {
  return request(`/history/${analysisId}`, { method: 'DELETE' })
}

// ---------------------------------------------------------------------------
// Dashboard
// ---------------------------------------------------------------------------

export function fetchStats() {
  return request('/stats')
}

// ---------------------------------------------------------------------------
// Speaker voiceprint
// ---------------------------------------------------------------------------

export function enrollSpeaker(speakerId, file) {
  const formData = new FormData()
  formData.append('file', file)
  return request(`/speakers/${encodeURIComponent(speakerId)}/enroll`, {
    method: 'POST',
    body: formData,
  })
}

export function verifySpeaker(speakerId, file) {
  const formData = new FormData()
  formData.append('file', file)
  return request(`/speakers/${encodeURIComponent(speakerId)}/verify`, {
    method: 'POST',
    body: formData,
  })
}

// ---------------------------------------------------------------------------
// Real-time WebSocket URL
// ---------------------------------------------------------------------------

export function realtimeSocketUrl() {
  if (API_BASE.startsWith('http')) {
    return `${API_BASE.replace(/^http/, 'ws')}/realtime`
  }
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${window.location.host}${API_BASE}/realtime`
}

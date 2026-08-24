// VITE_API_URL should point to the deployed FastAPI service, for example
// https://voiceguard-api.example.com/api. The local address remains the
// default so the existing development workflow works without configuration.
const API_URL = (import.meta.env.VITE_API_URL || '/api').replace(/\/$/, '')

async function request(path, options = {}) {
  try {
    const response = await fetch(`${API_URL}${path}`, {
      ...options,
      headers: { 'x-tunnel-skip-browser-warning': 'true', ...(options.headers || {}) },
    })
    const payload = await response.json()
    if (!response.ok) throw new Error(payload.detail || 'Unable to process the request.')
    return payload
  } catch (error) {
    if (error instanceof TypeError) throw new Error('Backend server is not running.')
    throw error
  }
}

export function analyzeAudio(file) {
  const formData = new FormData()
  formData.append('file', file)
  return request('/analyze', { method: 'POST', body: formData })
}

export function fetchHistory() {
  return request('/history')
}

export function analyzeContext(payload) {
  return request('/analyze/context', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function realtimeSocketUrl() {
  if (API_URL.startsWith('http')) return `${API_URL.replace(/^http/, 'ws')}/realtime`
  return `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}${API_URL}/realtime`
}

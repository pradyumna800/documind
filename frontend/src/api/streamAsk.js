import { API_BASE_URL } from './client'

/**
 * Attempts to get a fresh access token using the stored refresh token.
 * Mirrors the same refresh logic in client.js's axios interceptor, but
 * streamAsk() can't reuse that interceptor directly since it uses raw
 * fetch() instead of axios (see the comment below on why).
 */
async function refreshAccessToken() {
  const refreshToken = localStorage.getItem('refresh_token')
  if (!refreshToken) return null

  try {
    const response = await fetch(`${API_BASE_URL}/auth/refresh/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh: refreshToken }),
    })
    if (!response.ok) return null
    const data = await response.json()
    localStorage.setItem('access_token', data.access)
    return data.access
  } catch {
    return null
  }
}

/**
 * Consumes the Server-Sent Events stream from POST /conversations/:id/ask-stream/.
 * Uses raw fetch() + ReadableStream rather than axios, because axios (being
 * XHR-based in the browser) doesn't expose a readable stream of the
 * response body as it arrives — fetch does, which is what actually lets us
 * update the UI token-by-token instead of waiting for the whole response.
 *
 * Because this bypasses axios, it also bypasses axios's automatic 401-retry
 * interceptor in client.js — so a session open longer than the access
 * token's lifetime (1 hour) would otherwise fail here even while every
 * other part of the app (which does use axios) kept working fine. This
 * retries once with a refreshed token before giving up, matching the same
 * behavior the rest of the app already has.
 *
 * Callbacks:
 *   onSources(sources)   — called once, as soon as retrieval finishes
 *   onChunk(text)         — called repeatedly as text streams in
 *   onDone()              — called once, when the stream ends normally
 *   onError(message)      — called if the stream fails or the server reports an error
 */
export async function streamAsk(conversationId, { question, documentIds, mode }, { onSources, onChunk, onDone, onError }, _isRetry = false) {
  const token = localStorage.getItem('access_token')

  let response
  try {
    response = await fetch(`${API_BASE_URL}/conversations/${conversationId}/ask-stream/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ question, document_ids: documentIds, mode }),
    })
  } catch (err) {
    onError('Could not reach the server.')
    return
  }

  if (response.status === 401 && !_isRetry) {
    const newToken = await refreshAccessToken()
    if (newToken) {
      return streamAsk(conversationId, { question, documentIds, mode }, { onSources, onChunk, onDone, onError }, true)
    }
    // Refresh token itself is expired/invalid too — a genuine re-login is needed.
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    window.location.href = '/login'
    return
  }

  if (!response.ok || !response.body) {
    onError('Something went wrong while starting the response.')
    return
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { value, done } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })

    // SSE events are separated by a blank line ("\n\n"). Process every
    // complete event in the buffer, and keep any trailing partial event
    // for the next chunk (a single read() can split an event mid-way).
    let boundary
    while ((boundary = buffer.indexOf('\n\n')) !== -1) {
      const rawEvent = buffer.slice(0, boundary)
      buffer = buffer.slice(boundary + 2)

      if (!rawEvent.startsWith('data:')) continue
      let payload
      try {
        payload = JSON.parse(rawEvent.slice(5).trim())
      } catch {
        continue
      }

      if (payload.type === 'sources') onSources(payload.sources || [])
      else if (payload.type === 'chunk') onChunk(payload.content || '')
      else if (payload.type === 'error') onError(payload.detail || 'Something went wrong.')
      else if (payload.type === 'done') onDone()
    }
  }
}

import { API_BASE_URL } from './client'

/**
 * Consumes the Server-Sent Events stream from POST /conversations/:id/ask-stream/.
 * Uses raw fetch() + ReadableStream rather than axios, because axios (being
 * XHR-based in the browser) doesn't expose a readable stream of the
 * response body as it arrives — fetch does, which is what actually lets us
 * update the UI token-by-token instead of waiting for the whole response.
 *
 * Callbacks:
 *   onSources(sources)   — called once, as soon as retrieval finishes
 *   onChunk(text)         — called repeatedly as text streams in
 *   onDone()              — called once, when the stream ends normally
 *   onError(message)      — called if the stream fails or the server reports an error
 */
export async function streamAsk(conversationId, { question, documentIds, mode }, { onSources, onChunk, onDone, onError }) {
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

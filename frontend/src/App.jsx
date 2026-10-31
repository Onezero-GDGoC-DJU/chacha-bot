import { useEffect, useState } from 'react'
import './tokens.css'
import './components.css'

const MAX_MESSAGE_CHARS = 4000

async function fetchHistory(sessionId) {
  const res = await fetch(`/api/sessions/${sessionId}/messages`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

async function sendChat(sessionId, messageId, content) {
  const res = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      sessionId,
      messageId,
      message: content,
    }),
  })

  const result = await res.json().catch(() => null)

  if (res.status === 429) {
    const error = new Error('요청이 많아요. 잠시 후 다시 시도해 주세요.')
    error.code = 'RATE_LIMITED'
    throw error
  }

  if (!res.ok) {
    const error = new Error(
      result?.error?.message || '답변을 받지 못했어요.',
    )
    error.status = res.status
    error.code = result?.error?.code
    throw error
  }

  return result.message
}

function createUUID() {
  if (crypto.randomUUID) return crypto.randomUUID()

  const bytes = crypto.getRandomValues(new Uint8Array(16))
  bytes[6] = (bytes[6] & 0x0f) | 0x40
  bytes[8] = (bytes[8] & 0x3f) | 0x80

  const hex = Array.from(bytes, (byte) =>
    byte.toString(16).padStart(2, '0'),
  ).join('')

  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}

function getOrCreateSessionId() {
  try {
    const savedId = localStorage.getItem('chacha.sessionId')
    if (savedId) return savedId

    const newId = createUUID()
    localStorage.setItem('chacha.sessionId', newId)
    return newId
  } catch {
    return createUUID()
  }
}
function App() {
  const [sessionId] = useState(getOrCreateSessionId)
  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(true)
  const [historyError, setHistoryError] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)
  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)
  const [sendError, setSendError] = useState(null)

  async function handleSend(content = draft, retryMessage = null) {
    const trimmedContent = content.trim()

    if (
      !trimmedContent ||
      trimmedContent.length > MAX_MESSAGE_CHARS ||
      sending ||
      loading ||
      historyError
    ) {
      return
    }

    const userMessage = retryMessage ?? {
      id: createUUID(),
      role: 'user',
      content: trimmedContent,
      createdAt: new Date().toISOString(),
    }

    if (!retryMessage) {
      setMessages((current) => [...current, userMessage])
      setDraft('')
    }

    setSendError(null)
    setSending(true)

    try {
      const assistantMessage = await sendChat(
        sessionId,
        userMessage.id,
        userMessage.content,
      )
      setMessages((current) => [...current, assistantMessage])
    } catch (error) {
      if (error.code === 'ALREADY_ANSWERED') {
        setReloadKey((key) => key + 1)
        return
      }

      const retryable = !['INVALID_REQUEST', 'BLOCKED'].includes(error.code)

      setSendError({
        message: error.code ? error.message : '답변을 받지 못했어요.',
        retryable,
      })
    } finally {
      setSending(false)
    }
  }

  useEffect(() => {
    let cancelled = false

    setLoading(true)
    setHistoryError(false)

    fetchHistory(sessionId)
      .then((result) => {
        if (!cancelled) setMessages(result.messages)
      })
      .catch(() => {
        if (!cancelled) setHistoryError(true)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [sessionId, reloadKey])

  const lastMessage = messages[messages.length - 1]
  const unanswered = lastMessage?.role === 'user'

  return (
    <div className="chat-app">
      <header className="chat-header">
        <h1 className="chat-header__title">chacha</h1>
      </header>

      {loading ? (
        <main className="chat-body chat-body--top">
          <section className="chat-thread">
            <div className="skeleton" aria-hidden="true">
              <div className="skeleton__bubble" />
              <div className="skeleton__lines">
                <div className="skeleton__line" />
                <div className="skeleton__line" />
                <div className="skeleton__line" />
              </div>
            </div>
          </section>
        </main>
      ) : historyError ? (
        <main className="chat-body">
          <section className="chat-thread">
            <div className="msg-error" role="alert">
              <p className="msg-error__text">대화를 불러오지 못했어요.</p>
              <button
                className="btn-retry"
                type="button"
                onClick={() => setReloadKey((key) => key + 1)}
              >
                다시 시도
              </button>
            </div>
          </section>
        </main>
      ) : messages.length === 0 ? (
        <main className="chat-body chat-body--center">
          <section className="chat-thread empty-state">
            <h2 className="empty-state__title">무엇이든 물어보세요</h2>
            <p className="empty-state__description">
              궁금한 내용을 입력해 대화를 시작해 보세요.
            </p>
          </section>
        </main>
      ) : (
        <main className="chat-body">
          <section className="chat-thread" role="log" aria-live="polite">
            <div className="time-divider">오늘</div>

            {messages.map((message) =>
              message.role === 'user' ? (
                <div className="msg-user" key={message.id}>
                  <div className="msg-user__bubble">{message.content}</div>
                </div>
              ) : (
                <article className="msg-ai" key={message.id}>
                  <p>{message.content}</p>
                </article>
              ),
            )}

            {sending && (
              <div
                className="typing-indicator"
                role="status"
                aria-label="답변 생성 중"
              >
                <span />
                <span />
                <span />
              </div>
            )}

            {unanswered && !sending && (
              <div className="msg-error" role="alert">
                <p className="msg-error__text">
                  {sendError?.message ?? '답변을 받지 못했어요.'}
                </p>

                {sendError?.retryable !== false && (
                  <button
                    className="btn-retry"
                    type="button"
                    onClick={() => handleSend(lastMessage.content, lastMessage)}
                    disabled={sending}
                  >
                    다시 시도
                  </button>
                )}
              </div>
            )}
          </section>
        </main>
      )}

      <footer className="chat-footer">
        <div className="composer">
          <textarea
            className="composer__input"
            aria-label="메시지 입력"
            placeholder="메시지를 입력하세요"
            rows={1}
            value={draft}
            maxLength={MAX_MESSAGE_CHARS}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.nativeEvent.isComposing || event.keyCode === 229) return

              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault()
                handleSend()
              }
            }}
          />
          <button
            className="send-button"
            type="button"
            aria-label="보내기"
            onClick={() => handleSend()}
            disabled={!draft.trim() || draft.trim().length > MAX_MESSAGE_CHARS || sending || loading || historyError}
          >
            ↑
          </button>
        </div>
        <p className="chat-footer__disclaimer">chacha는 실수할 수 있어요.</p>
      </footer>
    </div>
  )
}

export default App
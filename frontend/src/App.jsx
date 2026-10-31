import { useEffect, useState } from 'react'
import './tokens.css'
import './components.css'

async function fetchHistory(sessionId) {
  const res = await fetch(`/api/sessions/${sessionId}/messages`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
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

            {unanswered && (
              <div className="msg-error" role="alert">
                <p className="msg-error__text">답변을 받지 못했어요.</p>
                <button className="btn-retry" type="button">
                  다시 시도
                </button>
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
            disabled
          />
          <button
            className="send-button"
            type="button"
            aria-label="보내기"
            disabled
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
import { useEffect, useState } from 'react'
import './tokens.css'
import './components.css'

const MOCK_MESSAGES = [
  {
    id: '1',
    role: 'user',
    content: '안녕!',
    status: 'done',
    replyTo: null,
    createdAt: '2026-10-30T09:00:00Z',
  },
  {
    id: '2',
    role: 'assistant',
    content: '안녕하세요! 저는 chacha예요. 무엇을 도와드릴까요?',
    status: 'done',
    replyTo: '1',
    createdAt: '2026-10-30T09:00:02Z',
  },  
]

async function getMockHistory(sessionId) {
  await new Promise((resolve) => setTimeout(resolve, 700))

  return { sessionId, messages: MOCK_MESSAGES }
}

function getOrCreateSessionId() {
  try {
    const savedId = localStorage.getItem('chacha.sessionId')
    if (savedId) return savedId

    const newId = crypto.randomUUID()
    localStorage.setItem('chacha.sessionId', newId)
    return newId
  } catch {
    return crypto.randomUUID()
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

    getMockHistory(sessionId)
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
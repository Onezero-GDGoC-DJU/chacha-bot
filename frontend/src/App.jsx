import { Fragment, useEffect, useLayoutEffect, useRef, useState } from 'react'
import Markdown from './Markdown'
import { formatDividerTime, needsTimeDivider } from './time'
import './tokens.css'
import './components.css'
import './App.css'

const MAX_MESSAGE_CHARS = 4000
// 남은 글자 수가 이보다 적어지면 입력창 아래에 글자 수를 보여줘요
const CHAR_COUNTER_THRESHOLD = 200
// 맨 아래에서 이 거리 안쪽을 보고 있을 때만 새 메시지를 따라 스크롤해요 (명세서 F4)
const SCROLL_STICK_THRESHOLD = 80
const SKELETON_COUNT = 2

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

// 백엔드(파이썬)와 같은 기준으로 세도록 이모지도 한 글자로 세요
function countChars(text) {
  return Array.from(text.trim()).length
}

function isNearBottom(element) {
  return (
    element.scrollHeight - element.scrollTop - element.clientHeight <=
    SCROLL_STICK_THRESHOLD
  )
}

// "오늘"/"어제" 기준 시각. 탭을 열어 둔 채 자정이 지나거나, 다시 탭으로 돌아오면 새로 계산해요
function useNow() {
  const [now, setNow] = useState(() => new Date())

  useEffect(() => {
    const nextMidnight = new Date(now)
    nextMidnight.setHours(24, 0, 0, 0)
    const timer = setTimeout(() => setNow(new Date()), nextMidnight - now)

    function handleVisibilityChange() {
      if (document.visibilityState === 'visible') setNow(new Date())
    }
    document.addEventListener('visibilitychange', handleVisibilityChange)

    return () => {
      clearTimeout(timer)
      document.removeEventListener('visibilitychange', handleVisibilityChange)
    }
  }, [now])

  return now
}

function ErrorIcon() {
  return (
    <svg className="msg-error__icon" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2" />
      <path d="M12 7.5v5.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      <circle cx="12" cy="16.5" r="1.25" fill="currentColor" />
    </svg>
  )
}

function RetryIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M20 12a8 8 0 1 1-2.34-5.66M20 4v5h-5" />
    </svg>
  )
}

function SendIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.25" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 19V5M5 12l7-7 7 7" />
    </svg>
  )
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
  const now = useNow()

  const bodyRef = useRef(null)
  const inputRef = useRef(null)
  const stickToBottomRef = useRef(true)

  function reloadHistory() {
    setLoading(true)
    setHistoryError(false)
    setReloadKey((key) => key + 1)
  }

  async function handleSend(content = draft, retryMessage = null) {
    const trimmedContent = content.trim()

    if (
      !trimmedContent ||
      countChars(trimmedContent) > MAX_MESSAGE_CHARS ||
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

    // 내가 보낸 메시지는 위로 올려 읽던 중이어도 맨 아래로 내려가요
    stickToBottomRef.current = true
    setSendError(null)
    setSending(true)

    try {
      const assistantMessage = await sendChat(
        sessionId,
        userMessage.id,
        userMessage.content,
      )
      setMessages((current) => [
        // 방금 보낸 메시지의 시간은 내 컴퓨터 시계라서, 서버 시계(답변 시간)로 맞춰요.
        // 두 시계가 어긋나도 질문과 답변 사이에 시간 구분선이 잘못 생기지 않아요.
        // 이력에서 다시 시도한 메시지는 이미 서버 시간이라 그대로 둬요.
        ...current.map((message) =>
          !retryMessage && message.id === userMessage.id
            ? { ...message, createdAt: assistantMessage.createdAt }
            : message,
        ),
        assistantMessage,
      ])
    } catch (error) {
      if (error.code === 'ALREADY_ANSWERED') {
        reloadHistory()
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

  // loading, historyError는 처음 값(true, false)과 reloadHistory()에서 정해요
  useEffect(() => {
    let cancelled = false
    stickToBottomRef.current = true

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

  // 화면을 그린 직후, 맨 아래를 보고 있었다면 새 내용까지 스크롤해요
  useLayoutEffect(() => {
    const body = bodyRef.current
    if (body && stickToBottomRef.current) {
      body.scrollTop = body.scrollHeight
    }
  }, [messages, sending, sendError, loading])

  // field-sizing: content를 지원하지 않는 브라우저(Firefox 등)는 JS로 높이를 맞춰요 (디자인 spec 5장)
  useLayoutEffect(() => {
    const input = inputRef.current
    if (!input || CSS.supports('field-sizing', 'content')) return

    input.style.height = 'auto'
    input.style.height = `${input.scrollHeight}px`
  }, [draft])

  const lastMessage = messages[messages.length - 1]
  const unanswered = lastMessage?.role === 'user'

  const draftChars = countChars(draft)
  const remainingChars = MAX_MESSAGE_CHARS - draftChars
  const canSend =
    draftChars > 0 &&
    remainingChars >= 0 &&
    !sending &&
    !loading &&
    !historyError

  return (
    <div className="chat-app">
      <header className="chat-header">
        <h1 className="chat-header__title">chacha</h1>
      </header>

      {loading ? (
        <main className="chat-body chat-body--top">
          <section className="chat-thread">
            {Array.from({ length: SKELETON_COUNT }, (_, index) => (
              <div className="skeleton" aria-hidden="true" key={index}>
                <div className="skeleton__bubble" />
                <div className="skeleton__lines">
                  <div className="skeleton__line" />
                  <div className="skeleton__line" />
                  <div className="skeleton__line" />
                </div>
              </div>
            ))}
          </section>
        </main>
      ) : historyError ? (
        <main className="chat-body">
          <section className="chat-thread">
            <div className="msg-error" role="alert">
              <ErrorIcon />
              <p className="msg-error__text">대화를 불러오지 못했어요.</p>
              <button
                className="btn-retry"
                type="button"
                onClick={reloadHistory}
              >
                <RetryIcon />
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
        <main
          className="chat-body"
          ref={bodyRef}
          onScroll={(event) => {
            stickToBottomRef.current = isNearBottom(event.currentTarget)
          }}
        >
          <section className="chat-thread" role="log" aria-live="polite">
            {messages.map((message, index) => (
              <Fragment key={message.id}>
                {needsTimeDivider(messages[index - 1], message) && (
                  <div className="time-divider">
                    {formatDividerTime(message.createdAt, now)}
                  </div>
                )}

                {message.role === 'user' ? (
                  <div className="msg-user">
                    <div className="msg-user__bubble">{message.content}</div>
                  </div>
                ) : (
                  <article className="msg-ai">
                    <Markdown>{message.content}</Markdown>
                  </article>
                )}
              </Fragment>
            ))}

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
                <ErrorIcon />
                <p className="msg-error__text">
                  {sendError?.message ?? '답변을 받지 못했어요.'}
                </p>

                {sendError?.retryable !== false && (
                  <button
                    className="btn-retry"
                    type="button"
                    onClick={() => handleSend(lastMessage.content, lastMessage)}
                  >
                    <RetryIcon />
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
            ref={inputRef}
            className="composer__input"
            aria-label="메시지 입력"
            aria-describedby="char-counter"
            placeholder="메시지를 입력하세요"
            rows={1}
            value={draft}
            // 제한을 넘은 만큼은 보여주되(남은 글자 수 표시), 아주 큰 붙여 넣기는 막아요
            maxLength={MAX_MESSAGE_CHARS * 2}
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
            disabled={!canSend}
          >
            <SendIcon />
          </button>
        </div>

        <p
          id="char-counter"
          className={
            remainingChars < 0
              ? 'chat-footer__counter chat-footer__counter--over'
              : 'chat-footer__counter'
          }
          hidden={remainingChars > CHAR_COUNTER_THRESHOLD}
        >
          {remainingChars < 0
            ? `${MAX_MESSAGE_CHARS.toLocaleString()}자를 ${(-remainingChars).toLocaleString()}자 넘었어요`
            : `${remainingChars.toLocaleString()}자 남았어요`}
        </p>

        <p className="chat-footer__disclaimer">chacha는 실수할 수 있어요.</p>
      </footer>
    </div>
  )
}

export default App

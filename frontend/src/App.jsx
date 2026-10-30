import './tokens.css'
import './components.css'

const messages = [
  { id: '1', role: 'user', content: '안녕, 너는 어떤 챗봇이야?' },
  {
    id: '2',
    role: 'assistant',
    content: '안녕하세요! 저는 chacha예요. 무엇을 도와드릴까요?',
  },
]
function App() {
  return (
    <div className="chat-app">
      <header className="chat-header">
        <h1 className="chat-header__title">chacha</h1>
      </header>

      {messages.length === 0 ? (
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
          <button className="send-button" type="button" aria-label="보내기" disabled>
            ↑
          </button>
        </div>
        <p className="chat-footer__disclaimer">chacha는 실수할 수 있어요.</p>
      </footer>
    </div>
  )
}

export default App
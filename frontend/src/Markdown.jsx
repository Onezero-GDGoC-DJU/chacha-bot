import { memo, useEffect, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

// 보안: react-markdown은 기본 설정에서 원본 HTML을 렌더링하지 않아요(명세서 F4).
// rehype-raw를 추가하면 AI 답변 속 <script>, onerror가 실행될 수 있으니 넣지 않아요.

const COPIED_LABEL_MS = 1500

// navigator.clipboard는 HTTPS나 localhost에서만 있고 권한이 막혀 있을 수도 있어서,
// 실패하면 예전 방식(execCommand)으로 한 번 더 시도해요
async function copyText(text) {
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text)
      return
    } catch {
      // 아래 대체 방법으로 넘어가요
    }
  }

  // 임시 textarea를 선택하면 포커스가 옮겨가니, 복사한 뒤 원래 자리(복사 버튼)로 돌려놔요
  const previousFocus = document.activeElement
  const textarea = document.createElement('textarea')
  textarea.value = text
  textarea.setAttribute('readonly', '')
  textarea.style.position = 'fixed'
  textarea.style.opacity = '0'
  document.body.appendChild(textarea)
  textarea.select()
  const copied = document.execCommand('copy')
  textarea.remove()
  previousFocus?.focus?.()

  if (!copied) throw new Error('복사 실패')
}

// ```python 코드 블록 → <pre><code class="language-python"> 로 들어와요
function CodeBlock({ children }) {
  const [copied, setCopied] = useState(false)

  const code = children?.props ?? {}
  const language = /language-(\S+)/.exec(code.className ?? '')?.[1] ?? 'text'
  const text = String(code.children ?? '').replace(/\n$/, '')

  useEffect(() => {
    if (!copied) return

    const timer = setTimeout(() => setCopied(false), COPIED_LABEL_MS)
    return () => clearTimeout(timer)
  }, [copied])

  async function handleCopy() {
    try {
      await copyText(text)
      setCopied(true)
    } catch {
      // 복사에 실패하면 라벨을 바꾸지 않아요
    }
  }

  return (
    <div className="code-block">
      <div className="code-block__header">
        <span>{language}</span>
        <button className="code-block__copy" type="button" onClick={handleCopy}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
            <rect x="9" y="9" width="11" height="11" rx="2" />
            <path d="M5 15V6a2 2 0 0 1 2-2h8" />
          </svg>
          {copied ? '복사됨' : '복사'}
        </button>
      </div>
      <pre>{children}</pre>
    </div>
  )
}

// 답변 속 링크는 새 탭으로 열고, 열린 페이지가 이 창에 접근하지 못하게 해요
// javascript: 같은 위험한 주소는 react-markdown이 빈 값으로 바꿔서, 그때는 글자로만 보여줘요
function MarkdownLink({ href, children }) {
  if (!href) return <span>{children}</span>

  return (
    <a href={href} target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  )
}

const remarkPlugins = [remarkGfm]

const components = {
  pre: CodeBlock,
  a: MarkdownLink,
}

function Markdown({ children }) {
  return (
    <ReactMarkdown remarkPlugins={remarkPlugins} components={components}>
      {children}
    </ReactMarkdown>
  )
}

// 입력창에 타이핑할 때마다 App 전체가 다시 그려져요.
// memo로 감싸서 답변 내용(children)이 바뀔 때만 마크다운을 다시 해석해요.
export default memo(Markdown)

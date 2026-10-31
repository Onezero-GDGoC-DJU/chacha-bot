// 시간 구분선 규칙
// - 디자인 spec 5장: 대화의 첫 메시지 위, 이전 메시지와 30분 이상 차이 날 때
// - 명세서 F4: 날짜가 바뀌는 지점
// 두 조건을 모두 적용해요.

const DIVIDER_GAP_MS = 30 * 60 * 1000

function toDate(createdAt) {
  const date = new Date(createdAt)
  return Number.isNaN(date.getTime()) ? null : date
}

export function needsTimeDivider(previous, current) {
  const currentDate = toDate(current.createdAt)
  if (!currentDate) return false
  if (!previous) return true

  const previousDate = toDate(previous.createdAt)
  if (!previousDate) return true

  return (
    currentDate - previousDate >= DIVIDER_GAP_MS ||
    currentDate.toDateString() !== previousDate.toDateString()
  )
}

// "오늘 오후 2:48", "어제 오전 9:05", "10월 29일 오후 2:48", "2025년 10월 29일 오후 2:48"
export function formatDividerTime(createdAt, now = new Date()) {
  const date = toDate(createdAt)
  if (!date) return ''

  const time = date.toLocaleTimeString('ko-KR', {
    hour: 'numeric',
    minute: '2-digit',
  })

  const yesterday = new Date(now)
  yesterday.setDate(now.getDate() - 1)

  if (date.toDateString() === now.toDateString()) return `오늘 ${time}`
  if (date.toDateString() === yesterday.toDateString()) return `어제 ${time}`

  const day = date.toLocaleDateString('ko-KR', {
    year: date.getFullYear() === now.getFullYear() ? undefined : 'numeric',
    month: 'long',
    day: 'numeric',
  })

  return `${day} ${time}`
}

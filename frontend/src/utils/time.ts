// 接口里的时间按 UTC 保存。没有时区标记时也按 UTC 解析，再换成浏览器本地时间。

const pad = (part: number) => String(part).padStart(2, '0')

export const parseApiDate = (value: string) => {
  const text = value.trim()
  const hasZone = /(?:Z|[+-]\d{2}:\d{2})$/.test(text)
  return new Date(hasZone ? text : `${text}Z`)
}

export const formatLocalDateTime = (value: string) => {
  const date = parseApiDate(value)
  if (Number.isNaN(date.getTime())) return value
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
}

export const formatLocalClock = (value: string) => {
  const date = parseApiDate(value)
  if (Number.isNaN(date.getTime())) return value.slice(11, 16)
  return `${pad(date.getHours())}:${pad(date.getMinutes())}`
}

export const formatLocalClockWithSeconds = (value: string) => {
  const date = parseApiDate(value)
  if (Number.isNaN(date.getTime())) return value.slice(11, 19)
  return `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
}

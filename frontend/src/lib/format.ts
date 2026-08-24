export function localIsoDate(date = new Date()): string {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

export function formatDate(value: string, options?: Intl.DateTimeFormatOptions): string {
  const [year = 0, month = 1, day = 1] = value.slice(0, 10).split('-').map(Number)
  const parsed = new Date(year, month - 1, day)
  const isCalendarDate = /^\d{4}-\d{2}-\d{2}/.test(value)
    && Number.isFinite(parsed.valueOf())
    && parsed.getFullYear() === year
    && parsed.getMonth() === month - 1
    && parsed.getDate() === day
  if (!isCalendarDate) return value || '—'
  return new Intl.DateTimeFormat(undefined, options ?? { weekday: 'short', day: 'numeric', month: 'short' }).format(parsed)
}

export function formatLongDate(value: string): string {
  return formatDate(value, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })
}

export function formatPace(seconds?: number | null): string {
  if (!seconds || !Number.isFinite(seconds)) return '—'
  const minutes = Math.floor(seconds / 60)
  return `${minutes}:${String(Math.round(seconds % 60)).padStart(2, '0')}`
}

export function formatDuration(minutes?: number | null): string {
  if (minutes == null || !Number.isFinite(minutes)) return '—'
  return formatClockTime(minutes * 60)
}

export function formatRaceTime(seconds?: number | null): string {
  if (!seconds) return 'Not enough data'
  return formatClockTime(seconds)
}

/**
 * Parse a duration entered as total minutes, M:SS, or H:MM:SS.
 * Two colon-separated parts are deliberately always minutes and seconds.
 */
export function parseDurationInput(value: string): number | null {
  const input = value.trim()
  if (!input) return null
  if (/^\d+(?:\.\d+)?$/.test(input)) {
    const minutes = Number(input)
    return Number.isFinite(minutes) ? minutes : null
  }
  const parts = input.split(':')
  if ((parts.length !== 2 && parts.length !== 3) || parts.some((part) => !/^\d+$/.test(part))) return null
  const values = parts.map(Number)
  const seconds = values.at(-1)!
  const minutes = values.at(-2)!
  if (seconds >= 60 || (parts.length === 3 && minutes >= 60)) return null
  const totalSeconds = parts.length === 2
    ? minutes * 60 + seconds
    : values[0]! * 3600 + minutes * 60 + seconds
  return totalSeconds / 60
}

function formatClockTime(seconds: number): string {
  const rounded = Math.max(0, Math.round(seconds))
  const hours = Math.floor(rounded / 3600)
  const minutes = Math.floor((rounded % 3600) / 60)
  const remaining = rounded % 60
  if (hours === 0) return `${minutes}:${String(remaining).padStart(2, '0')}`
  return `${hours}:${String(minutes).padStart(2, '0')}:${String(remaining).padStart(2, '0')}`
}

export function startOfWeek(date = new Date()): Date {
  const copy = new Date(date)
  const day = copy.getDay()
  const offset = day === 0 ? -6 : 1 - day
  copy.setDate(copy.getDate() + offset)
  copy.setHours(0, 0, 0, 0)
  return copy
}

export function addDays(date: Date, amount: number): Date {
  const copy = new Date(date)
  copy.setDate(copy.getDate() + amount)
  return copy
}

export function weekDates(anchor: Date): string[] {
  const start = startOfWeek(anchor)
  return Array.from({ length: 7 }, (_, index) => localIsoDate(addDays(start, index)))
}

export function formatNumber(value?: number | null, digits = 0): string {
  if (value == null || Number.isNaN(value)) return '—'
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: digits, minimumFractionDigits: digits }).format(value)
}

export function recordLabel(value: Record<string, unknown> | string): string {
  if (typeof value === 'string') return value
  return Object.entries(value).map(([key, item]) => {
    const display = key.endsWith('duration_minutes') && typeof item === 'number' ? formatDuration(item) : String(item)
    return `${key.replaceAll('_', ' ')}: ${display}`
  }).join('\n')
}

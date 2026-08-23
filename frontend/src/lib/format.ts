export function localIsoDate(date = new Date()): string {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

export function formatDate(value: string, options?: Intl.DateTimeFormatOptions): string {
  const [year = 0, month = 1, day = 1] = value.slice(0, 10).split('-').map(Number)
  return new Intl.DateTimeFormat(undefined, options ?? { weekday: 'short', day: 'numeric', month: 'short' }).format(new Date(year, month - 1, day))
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
  if (minutes == null) return '—'
  if (minutes < 60) return `${Math.round(minutes)} min`
  const hours = Math.floor(minutes / 60)
  const remainder = Math.round(minutes % 60)
  return remainder ? `${hours}h ${remainder}m` : `${hours}h`
}

export function formatRaceTime(seconds?: number | null): string {
  if (!seconds) return 'Not enough data'
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const remaining = Math.round(seconds % 60)
  return hours ? `${hours}:${String(minutes).padStart(2, '0')}:${String(remaining).padStart(2, '0')}` : `${minutes}:${String(remaining).padStart(2, '0')}`
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
  return Object.entries(value).map(([key, item]) => `${key.replaceAll('_', ' ')}: ${String(item)}`).join('\n')
}

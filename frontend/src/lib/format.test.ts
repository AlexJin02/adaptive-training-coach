import { describe, expect, it } from 'vitest'
import { formatDuration, formatPace, formatRaceTime, parseDurationInput, weekDates } from './format'

describe('training display formats', () => {
  it('formats pace and race estimates without false decimals', () => {
    expect(formatPace(312)).toBe('5:12')
    expect(formatRaceTime(5399)).toBe('1:29:59')
    expect(formatRaceTime(754)).toBe('12:34')
    expect(formatRaceTime(null)).toBe('Not enough data')
  })

  it('formats every recorded duration as hours, minutes and seconds', () => {
    expect(formatDuration(45)).toBe('45:00')
    expect(formatDuration(65 + 1 / 60)).toBe('1:05:01')
    expect(formatDuration(null)).toBe('—')
  })

  it('parses plain minutes, M:SS and H:MM:SS without ambiguity', () => {
    expect(parseDurationInput('45')).toBe(45)
    expect(parseDurationInput('45:00')).toBe(45)
    expect(parseDurationInput('1:05:01')).toBeCloseTo(65 + 1 / 60)
    expect(parseDurationInput('1:60')).toBeNull()
    expect(parseDurationInput('1:60:00')).toBeNull()
  })

  it('creates Monday-through-Sunday calendar windows', () => {
    const dates = weekDates(new Date(2026, 7, 23))
    expect(dates).toEqual(['2026-08-17', '2026-08-18', '2026-08-19', '2026-08-20', '2026-08-21', '2026-08-22', '2026-08-23'])
  })
})

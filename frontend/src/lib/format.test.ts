import { describe, expect, it } from 'vitest'
import { formatPace, formatRaceTime, weekDates } from './format'

describe('training display formats', () => {
  it('formats pace and race estimates without false decimals', () => {
    expect(formatPace(312)).toBe('5:12')
    expect(formatRaceTime(5399)).toBe('1:29:59')
    expect(formatRaceTime(null)).toBe('Not enough data')
  })

  it('creates Monday-through-Sunday calendar windows', () => {
    const dates = weekDates(new Date(2026, 7, 23))
    expect(dates).toEqual(['2026-08-17', '2026-08-18', '2026-08-19', '2026-08-20', '2026-08-21', '2026-08-22', '2026-08-23'])
  })
})

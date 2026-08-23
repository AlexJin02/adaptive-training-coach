import { describe, expect, it } from 'vitest'
import type { CompletedSession } from '../types'
import { buildRecentLoadSeries } from './LoadReadinessPage'

describe('recent session load series', () => {
  it('takes the newest 14 items from the newest-first API and presents them chronologically', () => {
    const sessions: CompletedSession[] = Array.from({ length: 16 }, (_, index) => ({
      id: index + 1,
      date: `2026-08-${String(16 - index).padStart(2, '0')}`,
      workout_kind: 'RUNNING',
      session_type: 'Easy',
      duration_minutes: 30,
      rpe: 3,
      srpe_load: 90 + index,
    }))

    const series = buildRecentLoadSeries(sessions)

    expect(series).toHaveLength(14)
    expect(series.map((point) => point.date)).toEqual([
      '2026-08-03', '2026-08-04', '2026-08-05', '2026-08-06', '2026-08-07',
      '2026-08-08', '2026-08-09', '2026-08-10', '2026-08-11', '2026-08-12',
      '2026-08-13', '2026-08-14', '2026-08-15', '2026-08-16',
    ])
  })
})

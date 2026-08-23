import type { ApiCapabilities, TodayDashboard } from '../types'
import { vi } from 'vitest'

export const capabilitiesOff: ApiCapabilities = {
  ai_configured: false,
  image_extraction: false,
  text_extraction: false,
  transcription: false,
  note_processing: false,
  ai_session_analysis: false,
  ai_adaptation: false,
  ai_weekly_review: false,
  ai_planner: false,
  reason: 'No OpenAI API key is configured.',
}

export const todayFixture: TodayDashboard = {
  date: '2026-08-23',
  goal: { id: 1, goal_type: 'HALF_MARATHON', description: 'Sub 1:30', target_value: '1:29:59', is_current: true },
  running_phase: 'AEROBIC_BASE',
  climbing_phase: 'MAX_STRENGTH',
  running_readiness: { sport: 'RUNNING', label: 'GOOD', value: 8.1, components: [{ domain: 'CARDIOVASCULAR', value: 8.4, label: 'GOOD' }, { domain: 'LOWER_BODY', value: 7.8, label: 'GOOD' }] },
  climbing_readiness: { sport: 'CLIMBING', label: 'MODERATE', value: 6.2, components: [{ domain: 'FINGER_FOREARM', value: 5.5, label: 'MODERATE' }, { domain: 'NEURAL', value: 6.8, label: 'MODERATE' }] },
  sessions: [],
  fatigue_warnings: [],
  pending_adaptations: [],
}

export function installFetchMock(): ReturnType<typeof vi.fn> {
  const mock = vi.fn(async (input: RequestInfo | URL) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
    let body: unknown = { items: [] }
    if (url.includes('/capabilities')) body = capabilitiesOff
    else if (url.includes('/today')) body = todayFixture
    else if (url.includes('/settings')) body = {
      gym_name: 'Home Gym', grade_display: 'BOTH', retain_screenshots: false, retain_audio: false,
      engine: { base_stress_divisor: 90, base_stress_cap: 10, hard_attempt_threshold: 10, hard_attempt_increment: 0.015, hard_attempt_cap: 1.25, readiness_good_threshold: 7.5, readiness_moderate_threshold: 5, half_lives: { CARDIOVASCULAR: 18, LOWER_BODY: 30, FINGER_FOREARM: 36, PULLING_UPPER_BODY: 30, NEURAL: 24, SYSTEMIC: 18 } },
    }
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
  vi.stubGlobal('fetch', mock)
  return mock
}

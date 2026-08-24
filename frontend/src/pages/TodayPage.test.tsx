import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { CapabilityProvider } from '../app/CapabilityProvider'
import { localIsoDate } from '../lib/format'
import { capabilitiesOff } from '../test/fixtures'
import { TodayPage } from './TodayPage'

afterEach(() => { vi.unstubAllGlobals() })

it('pairs a Calendar plan with a pending Strava activity and opens the existing review', async () => {
  const today = localIsoDate()
  const plan = { id: 8, date: today, workout_kind: 'RUNNING', session_type: 'QUALITY', title: 'Threshold 4 × 8', status: 'PLANNED', planned_duration_minutes: 60, planned_distance_km: 11, target_rpe: 7, description: 'Stay controlled.', structured_blocks: [{ phase: 'Main', description: '4 × 8 min @ 4:15–4:20/km · 2 min jog' }] }
  const imported = { id: 31, provider: 'STRAVA', external_activity_id: '987654', date: today, start_time: '07:15', title: 'Morning Run', suggested_session_type: 'QUALITY', distance_km: 10.8, elapsed_time_seconds: 3222, moving_time_seconds: 3210, average_pace_seconds_per_km: 298, average_hr: 164, max_hr: 181, cadence: 175, needs_review: true, imported_at: `${today}T08:00:00Z`, laps: [], planned_session: plan }
  const mock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    const body = url.includes('/capabilities') ? { ...capabilitiesOff, transcription: false }
      : { date: today, sessions: [{ id: 'plan-8', date: today, planned: plan, completed: null, status: 'PLANNED' }], imported_runs: [imported] }
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
  vi.stubGlobal('fetch', mock)
  const user = userEvent.setup()
  render(<MemoryRouter><CapabilityProvider><TodayPage /></CapabilityProvider></MemoryRouter>)

  expect(await screen.findByText('Threshold 4 × 8')).toBeInTheDocument()
  expect(screen.getByText('4 × 8 min @ 4:15–4:20/km · 2 min jog')).toBeInTheDocument()
  expect(screen.getByText('NEEDS REVIEW')).toBeInTheDocument()
  expect(screen.getByText('10.80 km')).toBeInTheDocument()
  expect(screen.getByText('53:42')).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Complete Review' }))
  expect(within(screen.getByRole('dialog', { name: 'Post-Run Review' })).getByText(/Matched planned session/)).toBeInTheDocument()
})

it('shows multiple completed sessions, an unplanned label, comparison and subjective evidence', async () => {
  const today = localIsoDate()
  const plan = { id: 8, date: today, workout_kind: 'RUNNING', session_type: 'QUALITY', title: '5 × 1 km', status: 'COMPLETED', planned_distance_km: 10, target_rpe: 8, structured_blocks: [{ phase: 'Main', raw_text: '5 × 1 km @ 3:55–4:00/km' }] }
  const completed = { id: 50, planned_session_id: 8, date: today, workout_kind: 'RUNNING', session_type: 'QUALITY', title: '5 × 1 km', duration_minutes: 54, distance_km: 10.8, average_pace_seconds_per_km: 298, average_hr: 164, max_hr: 181, rpe: 7, splits: [{ distance_km: 1, elapsed_time_seconds: 239 }], subjective_feedback_text: '后两组腿开始变沉，但整体仍然能够控制。' }
  const climbing = { id: 51, planned_session_id: null, date: today, workout_kind: 'CLIMBING', session_type: 'BOARD', title: 'TB2 Hard Session', duration_minutes: 105, rpe: 8, board_name: 'Tension Board 2', angle: 40, climbing_attempts: [{ grade: '7A', attempts: 7, sends: 0 }] }
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ date: today, sessions: [{ id: 'plan-8', date: today, planned: plan, completed, status: 'COMPLETED' }, { id: 'completed-51', date: today, planned: null, completed: climbing, status: 'COMPLETED' }], imported_runs: [] }), { status: 200, headers: { 'Content-Type': 'application/json' } })))
  render(<MemoryRouter><TodayPage /></MemoryRouter>)

  expect(await screen.findByText('Session 1')).toBeInTheDocument()
  expect(screen.getByText('Session 2')).toBeInTheDocument()
  expect(screen.getByText('Planned vs actual')).toBeInTheDocument()
  expect(screen.getByText('3:59')).toBeInTheDocument()
  expect(screen.getByText('后两组腿开始变沉，但整体仍然能够控制。')).toBeInTheDocument()
  expect(screen.getByText('UNPLANNED SESSION')).toBeInTheDocument()
  expect(screen.getByText('7A · 7 attempts · 0 sends')).toBeInTheDocument()
})

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { CapabilityProvider } from '../app/CapabilityProvider'
import { WorkoutLogPage } from './WorkoutLogPage'
import { capabilitiesOff, installFetchMock } from '../test/fixtures'
import type { WorkoutExtraction } from '../types'

describe('workout import degradation', () => {
  beforeEach(() => { installFetchMock() })
  afterEach(() => { vi.unstubAllGlobals() })

  it('keeps manual logging available when screenshot AI is unavailable', async () => {
    const user = userEvent.setup()
    render(<MemoryRouter initialEntries={['/workouts?action=image']}><CapabilityProvider><WorkoutLogPage /></CapabilityProvider></MemoryRouter>)
    expect(await screen.findByText('Screenshot extraction unavailable')).toBeInTheDocument()
    expect(screen.getByText(/No OpenAI API key/i)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Use manual workout form' }))
    expect(screen.getByLabelText(/^Duration/)).toHaveValue('45:00')
    expect(screen.getByLabelText(/RPE \(1–10\)/)).toHaveValue(3)
  })

  it('maps bouldering imports explicitly and preserves reviewed RPE and split detail', async () => {
    const extraction: WorkoutExtraction = {
      workout_kind: extracted(null),
      activity_type: extracted('Bouldering'),
      session_type: extracted('Limit Bouldering'),
      title: extracted('Limit session'),
      date: extracted('2026-08-23'),
      distance_km: extracted(null),
      duration_minutes: extracted(120),
      rpe: extracted(8),
      average_pace: extracted(null),
      average_hr: extracted(148),
      max_hr: extracted(172),
      elevation_m: extracted(null),
      cadence: extracted(null),
      power_w: extracted(null),
      board_name: extracted(null),
      angle: extracted(null),
      splits: extracted(['1 km — 5:00', '1 km — 4:55']),
      intervals: extracted(['4 × 6 min']),
      notes: extracted('Hard board session'),
    }
    const mock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
      const body = url.includes('/capabilities') ? { ...capabilitiesOff, ai_configured: true, text_extraction: true }
        : url.includes('/ai/workouts/extract-text') ? extraction
          : url.includes('/completed-sessions') && init?.method === 'POST' ? { id: 42 }
          : { items: [] }
      return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
    })
    vi.stubGlobal('fetch', mock)
    const user = userEvent.setup()
    render(<MemoryRouter initialEntries={['/workouts?action=text']}><CapabilityProvider><WorkoutLogPage /></CapabilityProvider></MemoryRouter>)
    await user.type(await screen.findByLabelText(/Describe the session/), 'Limit bouldering for two hours, RPE 8.')
    await user.click(screen.getByRole('button', { name: 'Create preview' }))
    expect(await screen.findByText('Review every field')).toBeInTheDocument()
    expect(screen.getByLabelText('RPE (1–10)')).toHaveValue(8)
    expect(screen.getByLabelText(/^Duration/)).toHaveValue('2:00:00')
    expect(screen.getByLabelText('Date')).toHaveAttribute('type', 'date')
    await user.click(screen.getByRole('button', { name: 'Save workout' }))
    const post = mock.mock.calls.find(([input, init]) => String(input).includes('/completed-sessions') && init?.method === 'POST')
    expect(post).toBeDefined()
    const payload = JSON.parse(String(post?.[1]?.body)) as Record<string, unknown>
    expect(payload).toMatchObject({ workout_kind: 'CLIMBING', session_type: 'BOULDERING', rpe: 8, max_hr: 172 })
    expect(payload.splits).toEqual([{ description: '1 km — 5:00' }, { description: '1 km — 4:55' }])
    expect(payload.interval_blocks).toEqual([{ description: '4 × 6 min' }])
  })

  it('records CrossFit supporting work with exercise, reps, load and RPE', async () => {
    const mock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => new Response(JSON.stringify(init?.method === 'POST' ? { id: 9 } : { items: [] }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
    vi.stubGlobal('fetch', mock)
    const user = userEvent.setup()
    render(<MemoryRouter><CapabilityProvider><WorkoutLogPage /></CapabilityProvider></MemoryRouter>)

    await user.click(await screen.findByRole('button', { name: 'Log workout' }))
    await user.selectOptions(screen.getByLabelText('Activity'), 'CROSSFIT_CONDITIONING')
    await user.type(screen.getByLabelText('Workout name'), 'Fran')
    await user.clear(screen.getByLabelText('Rounds'))
    await user.type(screen.getByLabelText('Rounds'), '3')
    await user.type(screen.getByLabelText('Result / time'), '12:34')
    await user.selectOptions(screen.getByLabelText('Exercise 1'), 'deadlift')
    await user.clear(screen.getByLabelText('Reps'))
    await user.type(screen.getByLabelText('Reps'), '10')
    await user.type(screen.getByLabelText('Load'), '60')
    await user.type(screen.getByLabelText('RPE'), '7')
    await user.click(screen.getByRole('button', { name: 'Save workout' }))

    await waitFor(() => expect(mock.mock.calls.some(([, init]) => init?.method === 'POST')).toBe(true))
    const post = mock.mock.calls.find(([, init]) => init?.method === 'POST')
    const payload = JSON.parse(String(post?.[1]?.body)) as Record<string, unknown>
    expect(payload).toMatchObject({ workout_kind: 'CROSSFIT_CONDITIONING', workout_name: 'Fran', rounds: 3, result_time: '12:34', duration_minutes: 45 })
    expect(payload.strength_sets).toEqual([{ exercise: 'deadlift', sets: '3', reps: '10', load: '60', rpe: '7', rir: '' }])
  })

  it('shows returned running, climbing and strength detail in the session modal', async () => {
    const session = {
      id: 12, date: '2026-08-23', workout_kind: 'CROSSFIT_CONDITIONING', session_type: 'Mixed detail', duration_minutes: 45, rpe: 8, srpe_load: 360,
      workout_name: 'Engine test', rounds: 4, result_time_seconds: 754,
      splits: [{ distance_km: 1, time: '4:15' }], interval_blocks: [{ phase: 'Main', detail: '4 × 1 km' }],
      climbing_attempts: [{ problem: 'Blue 7', grade: 'V7', attempts: 3 }], strength_sets: [{ exercise: 'deadlift', reps: 5, load_kg: 100 }],
      ai_analysis: { execution_summary: 'x'.repeat(250), confidence: 'LOW' },
    }
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ items: [session] }), { status: 200, headers: { 'Content-Type': 'application/json' } })))
    const user = userEvent.setup()
    render(<MemoryRouter><WorkoutLogPage /></MemoryRouter>)

    await user.click(await screen.findByRole('button', { name: 'View Mixed detail' }))
    const detail = within(screen.getByRole('dialog', { name: 'Mixed Detail' }))
    expect(detail.getByText('Engine test')).toBeInTheDocument()
    expect(detail.getByText('12:34')).toBeInTheDocument()
    expect(detail.getByText('Splits')).toBeInTheDocument()
    expect(detail.getByText('Intervals')).toBeInTheDocument()
    expect(detail.getByText('Climbing attempts')).toBeInTheDocument()
    expect(detail.getByText('Strength sets')).toBeInTheDocument()
    expect(detail.getByText(/exercise: deadlift/)).toBeInTheDocument()
    expect(detail.queryByText((content) => content.startsWith('x'))).not.toBeInTheDocument()
  })

  it('requires irreversible confirmation before deleting a workout', async () => {
    const session = { id: 7, date: '2026-08-23', workout_kind: 'RUNNING', session_type: 'Easy', duration_minutes: 45, rpe: 3, srpe_load: 135 }
    const mock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => new Response(JSON.stringify(init?.method === 'DELETE' ? { deleted: true, id: 7 } : { items: [session] }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
    vi.stubGlobal('fetch', mock)
    const user = userEvent.setup()
    render(<MemoryRouter><WorkoutLogPage /></MemoryRouter>)

    await user.click(await screen.findByRole('button', { name: 'View Easy' }))
    await user.click(screen.getByRole('button', { name: 'Delete workout' }))
    expect(mock.mock.calls.some(([, init]) => init?.method === 'DELETE')).toBe(false)
    expect(screen.getByText(/cannot be undone/i)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Delete permanently' }))
    await waitFor(() => expect(mock.mock.calls.some(([, init]) => init?.method === 'DELETE')).toBe(true))
  })
})

function extracted<T>(value: T) {
  return { value, confidence: 'HIGH' as const, source: 'visible text' }
}

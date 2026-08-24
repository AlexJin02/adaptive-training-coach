import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { weekDates } from '../lib/format'
import { CalendarPage } from './CalendarPage'

describe('calendar planning', () => {
  afterEach(() => { vi.unstubAllGlobals() })

  it('opens an empty day with the clicked date selected', async () => {
    installCalendarFetchMock()
    const user = userEvent.setup()
    render(<MemoryRouter><CalendarPage /></MemoryRouter>)

    const emptyDays = await screen.findAllByRole('button', { name: 'Plan or rest' })
    await user.click(emptyDays[0]!)

    const days = weekDates(new Date())
    expect(screen.getByLabelText('Date')).toHaveValue(days[0])
    await user.click(screen.getByRole('button', { name: 'Close' }))
    await user.click(emptyDays[1]!)
    expect(screen.getByLabelText('Date')).toHaveValue(days[1])
  })

  it.each([
    ['Max Hangs', 'Max Hangs'],
    ['Weighted Pull-ups', 'Weighted Pull-ups'],
    ['Deadlift', 'Deadlift'],
  ])('sends %s as a structured strength demand', async (sessionType, exercise) => {
    const mock = installCalendarFetchMock()
    const user = userEvent.setup()
    render(<MemoryRouter><CalendarPage /></MemoryRouter>)

    const emptyDays = await screen.findAllByRole('button', { name: 'Plan or rest' })
    await user.click(emptyDays[0]!)
    expect(screen.getByLabelText(/^Duration/)).toHaveValue('45:00')
    await user.selectOptions(screen.getByLabelText('Activity'), 'STRENGTH')
    await user.selectOptions(screen.getByLabelText('Session type'), sessionType)
    expect(screen.getByLabelText('Planned exercise 1')).toHaveValue(exercise)
    await user.click(screen.getByRole('button', { name: 'Add to plan' }))

    await waitFor(() => expect(mock.mock.calls.some(([, init]) => init?.method === 'POST')).toBe(true))
    const post = mock.mock.calls.find(([, init]) => init?.method === 'POST')
    const payload = JSON.parse(String(post?.[1]?.body)) as Record<string, unknown>
    expect(payload).toMatchObject({ date: weekDates(new Date())[0], workout_kind: 'STRENGTH', session_type: sessionType })
    expect(payload.structured_blocks).toEqual([{ exercise }])
  })

  it('sends a quality running prescription as a structured Main block', async () => {
    const mock = installCalendarFetchMock()
    const user = userEvent.setup()
    render(<MemoryRouter><CalendarPage /></MemoryRouter>)

    const emptyDays = await screen.findAllByRole('button', { name: 'Plan or rest' })
    await user.click(emptyDays[0]!)
    await user.selectOptions(screen.getByLabelText('Session type'), 'QUALITY')
    const prescription = '4 × 8 min @ 4:15/km, HR <= 172, 2 min recovery'
    await user.type(screen.getByLabelText('Session structure / notes'), prescription)
    await user.click(screen.getByRole('button', { name: 'Add to plan' }))

    await waitFor(() => expect(mock.mock.calls.some(([, init]) => init?.method === 'POST')).toBe(true))
    const post = mock.mock.calls.find(([, init]) => init?.method === 'POST')
    const payload = JSON.parse(String(post?.[1]?.body)) as Record<string, unknown>
    expect(payload).toMatchObject({ workout_kind: 'RUNNING', session_type: 'QUALITY', description: prescription })
    expect(payload.structured_blocks).toEqual([{ phase: 'Main', description: prescription }])
  })

  it('shows planned prescription and linked Strava actual evidence together', async () => {
    const date = weekDates(new Date())[0]!
    const entry = {
      id: 'planned-8', date, status: 'COMPLETED',
      planned: { id: 8, date, workout_kind: 'RUNNING', session_type: 'QUALITY', title: 'Threshold 4 x 8', status: 'COMPLETED', planned_duration_minutes: 60, planned_distance_km: 11, target_rpe: 7, structured_blocks: [{ label: 'Main', raw_text: '4 x 8 min threshold' }] },
      completed: { id: 50, planned_session_id: 8, date, workout_kind: 'RUNNING', session_type: 'QUALITY', title: 'Threshold 4 x 8', duration_minutes: 51.67, distance_km: 10, rpe: 7, average_pace_seconds_per_km: 300, average_hr: 148, max_hr: 172, splits: [{ lap_index: 1, distance_km: 1, elapsed_time_seconds: 305 }], subjective_feedback_text: '心肺受控，最後兩圈腿有點沉。', subjective_feedback_source: 'VOICE' },
    }
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ items: [entry] }), { status: 200, headers: { 'Content-Type': 'application/json' } })))
    const user = userEvent.setup()
    render(<MemoryRouter><CalendarPage /></MemoryRouter>)

    const title = await screen.findByText('Threshold 4 x 8')
    await user.click(title.closest('article')!)
    const detail = within(screen.getByRole('dialog', { name: 'Session Detail' }))
    expect(detail.getByText('Full prescription')).toBeInTheDocument()
    expect(detail.getByText('4 x 8 min threshold')).toBeInTheDocument()
    expect(detail.getByText('Actual result')).toBeInTheDocument()
    expect(detail.getByText('How this run felt')).toBeInTheDocument()
    expect(detail.getByText('心肺受控，最後兩圈腿有點沉。')).toBeInTheDocument()
    expect(detail.getByText(/lap index: 1/)).toBeInTheDocument()
  })

  it('opens a requested planned session from the Today deep link', async () => {
    const date = weekDates(new Date())[0]!
    const entry = {
      id: 'planned-8', date, status: 'PLANNED', completed: null,
      planned: { id: 8, date, workout_kind: 'RUNNING', session_type: 'EASY', title: 'Aerobic Run', status: 'PLANNED', planned_duration_minutes: 45, structured_blocks: [] },
    }
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ items: [entry] }), { status: 200, headers: { 'Content-Type': 'application/json' } })))

    render(<MemoryRouter initialEntries={['/calendar?session_id=8']}><CalendarPage /></MemoryRouter>)

    expect(await screen.findByRole('dialog', { name: 'Session Detail' })).toBeInTheDocument()
    expect(within(screen.getByRole('dialog', { name: 'Session Detail' })).getByText('Aerobic Run')).toBeInTheDocument()
  })
})

function installCalendarFetchMock(): ReturnType<typeof vi.fn> {
  const mock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => new Response(JSON.stringify(init?.method === 'POST' ? { id: 1 } : { items: [] }), { status: init?.method === 'POST' ? 201 : 200, headers: { 'Content-Type': 'application/json' } }))
  vi.stubGlobal('fetch', mock)
  return mock
}

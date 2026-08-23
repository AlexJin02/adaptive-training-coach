import { render, screen, waitFor } from '@testing-library/react'
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
    await user.selectOptions(screen.getByLabelText('Session type'), 'Threshold')
    const prescription = '4 × 8 min @ 4:15/km, HR <= 172, 2 min recovery'
    await user.type(screen.getByLabelText('Session structure / notes'), prescription)
    await user.click(screen.getByRole('button', { name: 'Add to plan' }))

    await waitFor(() => expect(mock.mock.calls.some(([, init]) => init?.method === 'POST')).toBe(true))
    const post = mock.mock.calls.find(([, init]) => init?.method === 'POST')
    const payload = JSON.parse(String(post?.[1]?.body)) as Record<string, unknown>
    expect(payload).toMatchObject({ workout_kind: 'RUNNING', session_type: 'Threshold', description: prescription })
    expect(payload.structured_blocks).toEqual([{ phase: 'Main', description: prescription }])
  })
})

function installCalendarFetchMock(): ReturnType<typeof vi.fn> {
  const mock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => new Response(JSON.stringify(init?.method === 'POST' ? { id: 1 } : { items: [] }), { status: init?.method === 'POST' ? 201 : 200, headers: { 'Content-Type': 'application/json' } }))
  vi.stubGlobal('fetch', mock)
  return mock
}

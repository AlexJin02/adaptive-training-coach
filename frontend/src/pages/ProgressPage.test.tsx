import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { ProgressPage } from './ProgressPage'

afterEach(() => { vi.unstubAllGlobals() })

it('labels easy pace and heart rate clearly without race predictions or LT2 proxy', async () => {
  const progress = {
    running: {
      monthly_mileage: [],
      weekly_mileage: [],
      rolling_volume: [],
      run_frequency: 3,
      sessions_by_type: [{ label: 'EASY', value: 2 }, { label: 'QUALITY', value: 1 }],
      easy_efficiency: [
        { date: '2026-08-15', value: 320, secondary: 151, label: 'Strava' },
        { date: '2026-08-08', value: 325, secondary: 150, label: 'Strava' },
        { date: '2026-08-01', value: 330, secondary: 149, label: 'Strava' },
      ],
      easy_efficiency_band: '147–153 bpm',
      easy_efficiency_warning: 'Only comparable easy runs are included.',
    },
    climbing: {
      tb2_benchmarks: [],
      gym_sets: [],
      session_count: 0,
      total_duration_minutes: 0,
      weekly_sessions: [],
      monthly_sessions: [],
      sessions_by_type: [],
      grade_attempts: [],
      grade_sends: [],
    },
  }
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(progress), { status: 200, headers: { 'Content-Type': 'application/json' } })))

  render(<MemoryRouter><ProgressPage /></MemoryRouter>)

  expect(await screen.findByText('147–153 bpm')).toBeInTheDocument()
  expect(screen.queryByText(/race predictions/i)).not.toBeInTheDocument()
  expect(screen.queryByText(/LT2 development/i)).not.toBeInTheDocument()
  expect(screen.getAllByText('5:20/km').length).toBeGreaterThan(0)
  expect(screen.getAllByText('151 bpm').length).toBeGreaterThan(0)
  const plottedPoints = [...document.querySelectorAll('.chart-point')]
  expect(plottedPoints[0]).toHaveAttribute('aria-label', expect.stringContaining('Aug 1'))
  expect(plottedPoints.at(-1)).toHaveAttribute('aria-label', expect.stringContaining('Aug 15'))
})

it('updates the current gym set, starts a new set and summarizes the two hardest completed colours', async () => {
  const progress = {
    running: { monthly_mileage: [], weekly_mileage: [], rolling_volume: [], run_frequency: 0, sessions_by_type: [], easy_efficiency: [] },
    climbing: {
      tb2_benchmarks: [], session_count: 2, total_duration_minutes: 180, weekly_sessions: [], monthly_sessions: [], sessions_by_type: [], grade_attempts: [], grade_sends: [],
      gym_sets: [
        { id: 1, gym: 'Home Gym', start_date: '2026-07-01', end_date: '2026-07-31', is_active: false, progress: [
          { colour: 'Yellow', ordinal: 1, sent_count: 8 }, { colour: 'Green', ordinal: 2, sent_count: 6 }, { colour: 'Purple', ordinal: 3, sent_count: 5 }, { colour: 'Grey', ordinal: 4, sent_count: 4 }, { colour: 'Blue', ordinal: 5, sent_count: 3 }, { colour: 'Red', ordinal: 6, sent_count: 0 }, { colour: 'Black', ordinal: 7, sent_count: 1 },
        ] },
        { id: 2, gym: 'Home Gym', start_date: '2026-08-01', end_date: null, is_active: true, progress: [
          { colour: 'Yellow', ordinal: 1, sent_count: 8 }, { colour: 'Green', ordinal: 2, sent_count: 7 }, { colour: 'Purple', ordinal: 3, sent_count: 6 }, { colour: 'Grey', ordinal: 4, sent_count: 5 }, { colour: 'Blue', ordinal: 5, sent_count: 3 }, { colour: 'Red', ordinal: 6, sent_count: 2 }, { colour: 'Black', ordinal: 7, sent_count: 0 },
        ] },
      ],
    },
  }
  const mock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const body = url.includes('/settings') ? { gym_name: 'Home Gym' } : progress
    return new Response(JSON.stringify(body), { status: init?.method === 'POST' ? 201 : 200, headers: { 'Content-Type': 'application/json' } })
  })
  vi.stubGlobal('fetch', mock)
  const user = userEvent.setup()
  render(<MemoryRouter><ProgressPage /></MemoryRouter>)

  await user.click(await screen.findByRole('tab', { name: 'Climbing' }))
  const currentCard = screen.getByText(/Home Gym · Aug 2026 · CURRENT/).closest('.card')
  expect(currentCard).not.toBeNull()
  const currentHighlights = within(currentCard!.querySelector('.gym-set-highlights') as HTMLElement)
  expect(currentHighlights.getByText('Red')).toBeInTheDocument()
  expect(currentHighlights.getByText('2 sent')).toBeInTheDocument()
  expect(currentHighlights.getByText('Blue')).toBeInTheDocument()
  expect(currentHighlights.getByText('3 sent')).toBeInTheDocument()

  await user.click(screen.getByRole('button', { name: 'Update current set' }))
  const updateDialog = within(screen.getByRole('dialog', { name: 'Update current set' }))
  await user.clear(updateDialog.getByLabelText('Black sent'))
  await user.type(updateDialog.getByLabelText('Black sent'), '1')
  await user.click(updateDialog.getByRole('button', { name: 'Save progress' }))
  await waitFor(() => expect(mock.mock.calls.some(([input, init]) => String(input).includes('/climbing/gym-sets/2/progress') && init?.method === 'PATCH')).toBe(true))

  await user.click(await screen.findByRole('button', { name: 'New set' }))
  const newSetDialog = within(screen.getByRole('dialog', { name: 'Start a new gym set' }))
  expect(newSetDialog.getByLabelText('Gym')).toHaveValue('Home Gym')
  await user.click(newSetDialog.getByRole('button', { name: 'Start new set' }))
  await waitFor(() => expect(mock.mock.calls.some(([input, init]) => String(input).includes('/climbing/gym-sets') && init?.method === 'POST')).toBe(true))
})

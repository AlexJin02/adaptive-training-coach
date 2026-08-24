import { render, screen } from '@testing-library/react'
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

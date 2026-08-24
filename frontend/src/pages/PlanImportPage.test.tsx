import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { PlanImportPage } from './PlanImportPage'

const markdown = '# TRAINING_WEEKLY_PLAN_V1\nWEEK_START: 2026-09-07\nWEEK_END: 2026-09-13'
const preview = {
  cadence: 'WEEKLY', period_start: '2026-09-07', period_end: '2026-09-13', warnings: [], can_import: true,
  sessions: [{ date: '2026-09-08', day: 'TUESDAY', session_number: 1, workout_kind: 'RUNNING', session_type: 'QUALITY', title: 'Intervals', raw_workout_text: '3 sets x 5 x 1 km @ 3:30/km', structured_blocks: [], planned_distance_km: 15, target_rpe_min: 7, target_rpe_max: 8 }],
}

describe('external plan import', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('requires a preview before importing sessions to Calendar', async () => {
    const mock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.includes('/monthly/current')) return new Response('null', { status: 200, headers: { 'Content-Type': 'application/json' } })
      const body = init?.method === 'POST' && url.endsWith('/import') ? { ...preview, import_id: 3, imported_session_ids: [91] } : preview
      return new Response(JSON.stringify(body), { status: init?.method === 'POST' && url.endsWith('/import') ? 201 : 200, headers: { 'Content-Type': 'application/json' } })
    })
    vi.stubGlobal('fetch', mock)
    const user = userEvent.setup()
    render(<MemoryRouter><PlanImportPage /></MemoryRouter>)

    expect(screen.queryByRole('button', { name: 'Import to Calendar' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('tab', { name: 'Import Plan' }))
    await user.type(screen.getByLabelText('Plan Markdown'), markdown)
    await user.click(screen.getByRole('button', { name: 'Parse Plan' }))
    expect(await screen.findByText(/Tuesday, Sep 8.*Intervals/)).toBeInTheDocument()
    expect(screen.getByText(/3 sets x 5 x 1 km/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Import to Calendar' }))
    expect(await screen.findByText(/1 session\(s\) imported to Calendar/)).toBeInTheDocument()
    expect(mock.mock.calls.filter(([input]) => String(input).endsWith('/import'))).toHaveLength(1)
  })

  it('renders the current monthly block as a readable plan and keeps raw import secondary', async () => {
    const monthly = {
      id: 8, month_start: '2026-09-01', month_end: '2026-09-30', status: 'ACTIVE',
      content: {
        month: '2026-09',
        running: { phase: 'Volume Build', monthly_objective: 'Build sustainable aerobic volume.', sessions_per_week: 4, session_structure: [{ session_type: 'EASY', sessions_per_week: 2 }, { session_type: 'QUALITY', sessions_per_week: 1 }], weekly_distance_targets: [{ week: 1, distance_km: 36 }, { week: 2, distance_km: 39 }, { week: 3, distance_km: 42 }, { week: 4, distance_km: 35 }], quality_guidance: 'Controlled threshold development.', long_run_guidance: '- Week 1: 14 km', long_run_targets: [{ week: 1, distance_km: 14 }, { week: 2, distance_km: 15 }], key_principles: ['Keep most running easy.'], other_notes: '' },
        climbing: { phase: 'Board Strength', sessions_per_week: 3, target_structure: [{ session_type: 'BOARD', sessions_per_week: 1 }], board_focus: 'Hard Tension Board 2 climbing.', key_principles: ['Prioritise attempt quality.'], other_notes: '' },
        auxiliary: { strength: 'One short supporting session.', mobility: 'As needed.' }, general_notes: 'Week 4 is lower volume.', raw_plan_text: '# TRAINING_MONTHLY_PLAN_V1\nMONTH: 2026-09',
      },
    }
    const mock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/monthly/current')) return new Response(JSON.stringify(monthly), { status: 200, headers: { 'Content-Type': 'application/json' } })
      return new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } })
    })
    vi.stubGlobal('fetch', mock)
    const user = userEvent.setup()
    render(<MemoryRouter><PlanImportPage /></MemoryRouter>)

    expect(await screen.findByText('SEPTEMBER 2026')).toBeInTheDocument()
    expect(screen.getAllByText('Volume Build').length).toBeGreaterThan(0)
    expect(screen.getByRole('table', { name: 'Weekly running mileage targets' })).toHaveTextContent('42 km')
    expect(screen.getByText('Hard Tension Board 2 climbing.')).toBeInTheDocument()
    expect(screen.queryByText(/TRAINING_MONTHLY_PLAN_V1/)).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'View Raw Import' }))
    expect(screen.getByText(/# TRAINING_MONTHLY_PLAN_V1/)).toBeInTheDocument()
    await user.click(screen.getAllByRole('button', { name: 'Close' }).at(0)!)
    await user.click(screen.getByRole('tab', { name: 'Import Plan' }))
    expect(screen.getByText('Current Monthly Block')).toBeInTheDocument()
    expect(screen.getByText('1 Board session recommended')).toBeInTheDocument()
  })
})

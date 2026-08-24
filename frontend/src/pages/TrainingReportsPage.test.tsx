import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { TrainingReportsPage } from './TrainingReportsPage'

describe('fixed training reports', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('generates deterministic weekly Markdown without an AI planning action', async () => {
    const report = '# TRAINING_WEEKLY_REPORT_V1\n\n## RUNNING_SUMMARY\nTOTAL_DISTANCE_KM: 42'
    const mock = vi.fn(async (input: RequestInfo | URL) => {
      void input
      return new Response(report, { status: 200, headers: { 'Content-Type': 'text/plain' } })
    })
    vi.stubGlobal('fetch', mock)
    const user = userEvent.setup()
    render(<MemoryRouter><TrainingReportsPage /></MemoryRouter>)

    await user.click(screen.getByRole('button', { name: 'Generate report' }))

    expect(await screen.findByText(/TOTAL_DISTANCE_KM: 42/)).toBeInTheDocument()
    expect(mock.mock.calls[0]?.[0]).toContain('/training-reports/weekly')
    expect(screen.queryByRole('button', { name: /Review & Generate/i })).not.toBeInTheDocument()
  })
})

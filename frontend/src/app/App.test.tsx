import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { App } from './App'
import { CapabilityProvider } from './CapabilityProvider'
import { ThemeProvider } from './ThemeProvider'
import { installFetchMock } from '../test/fixtures'

function renderApp(path = '/workouts'): void {
  render(<MemoryRouter initialEntries={[path]}><ThemeProvider><CapabilityProvider><App /></CapabilityProvider></ThemeProvider></MemoryRouter>)
}

describe('application shell', () => {
  beforeEach(() => { installFetchMock() })
  afterEach(() => { vi.unstubAllGlobals(); window.localStorage.clear() })

  it('renders the factual logger and simplified primary destinations', async () => {
    renderApp()
    expect(await screen.findByRole('heading', { name: 'Workout Log' })).toBeInTheDocument()
    const labels = ['Quick Log', 'Calendar', 'Progress', 'Workout Log', 'Training Reports', 'Training Plan', 'Training Notes', 'Settings']
    for (const label of labels) expect(screen.getAllByRole('link', { name: label }).length).toBeGreaterThan(0)
    expect(screen.queryByRole('link', { name: 'Load & Readiness' })).not.toBeInTheDocument()
  })

  it('navigates to the workout logger without a page reload', async () => {
    const user = userEvent.setup()
    renderApp()
    await screen.findByRole('heading', { name: 'Workout Log' })
    await user.click(screen.getByRole('link', { name: 'Workout Log' }))
    expect(await screen.findByRole('heading', { name: 'Workout Log' })).toBeInTheDocument()
    expect(screen.getByText(/Fast entry for completed training/i)).toBeInTheDocument()
  })

  it('redirects the retired Review & Plan route to fixed training reports', async () => {
    renderApp('/review-plan')
    expect(await screen.findByRole('heading', { name: 'Training Reports' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Weekly' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Monthly' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Generate report' })).toBeInTheDocument()
  })
})

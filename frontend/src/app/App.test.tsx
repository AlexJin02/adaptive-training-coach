import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { App } from './App'
import { CapabilityProvider } from './CapabilityProvider'
import { ThemeProvider } from './ThemeProvider'
import { installFetchMock } from '../test/fixtures'

function renderApp(path = '/today'): void {
  render(<MemoryRouter initialEntries={[path]}><ThemeProvider><CapabilityProvider><App /></CapabilityProvider></ThemeProvider></MemoryRouter>)
}

describe('application shell', () => {
  beforeEach(() => { installFetchMock() })
  afterEach(() => { vi.unstubAllGlobals(); window.localStorage.clear() })

  it('renders the Today dashboard and all nine primary destinations', async () => {
    renderApp()
    expect(await screen.findByRole('heading', { name: /August 23, 2026/i })).toBeInTheDocument()
    const labels = ['Today / Coach', 'Calendar', 'Athlete State', 'Load & Readiness', 'Progress', 'Workout Log', 'Training Notes', 'Review & Plan', 'Settings']
    for (const label of labels) expect(screen.getAllByRole('link', { name: label }).length).toBeGreaterThan(0)
    expect(screen.getByText('Half Marathon')).toBeInTheDocument()
    expect(screen.getByText('No current conflicts')).toBeInTheDocument()
  })

  it('navigates to the workout logger without a page reload', async () => {
    const user = userEvent.setup()
    renderApp()
    await screen.findByText('No current conflicts')
    await user.click(screen.getByRole('link', { name: 'Workout Log' }))
    expect(await screen.findByRole('heading', { name: 'Workout Log' })).toBeInTheDocument()
    expect(screen.getByText(/Fast entry for completed training/i)).toBeInTheDocument()
  })

  it('combines weekly and monthly planning in Review & Plan', async () => {
    renderApp('/review-plan')
    expect(await screen.findByRole('heading', { name: 'Review & Plan' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Weekly' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Monthly' })).toBeInTheDocument()
    for (const button of screen.getAllByRole('button', { name: 'Review & Generate Next Week' })) expect(button).toBeDisabled()
  })
})

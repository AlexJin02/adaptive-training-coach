import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { BarChart, ChartEmpty, GradePyramid, LineChart } from './charts'

describe('auditable charts', () => {
  it('shows an explicit no-data state instead of inventing a trend', () => {
    render(<ChartEmpty />)
    expect(screen.getByText('No comparable data yet')).toBeInTheDocument()
  })

  it('provides an accessible description for a verified time series', () => {
    render(<LineChart label="Verified grade" data={[{ date: '2026-08-01', value: 5 }, { date: '2026-10-01', value: 6 }]} />)
    expect(screen.getByRole('img', { name: 'Verified grade over time' })).toBeInTheDocument()
  })

  it('renders multiple sessions on one day without duplicate React keys', () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined)
    const sameDay = [{ date: '2026-08-23', value: 12 }, { date: '2026-08-23', value: 18 }]

    try {
      render(<LineChart label="Session load" data={sameDay} />)
      render(<BarChart label="Daily load" data={sameDay} />)
      expect(consoleError.mock.calls.flat().join(' ')).not.toContain('Encountered two children with the same key')
    } finally {
      consoleError.mockRestore()
    }
  })

  it('retains colour labels when rendering a gym pyramid', () => {
    render(<GradePyramid rows={[{ label: 'Yellow', value: 8, available: 8, colour: '#e8cf4a' }, { label: 'Blue', value: 1, available: 6, colour: '#4f91ee' }]} mode="percent" />)
    expect(screen.getByText('Yellow')).toBeInTheDocument()
    expect(screen.getByText('100%')).toBeInTheDocument()
    expect(screen.getByText('17%')).toBeInTheDocument()
  })
})

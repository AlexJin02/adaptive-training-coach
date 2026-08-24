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

  it('renders categorical labels without treating them as dates', () => {
    render(<BarChart label="Session count" data={[{ date: 'EASY', value: 3, label: 'EASY' }, { date: 'QUALITY', value: 1, label: 'QUALITY' }]} />)
    expect(screen.getAllByText('EASY').length).toBeGreaterThan(0)
    expect(screen.getAllByText('QUALITY').length).toBeGreaterThan(0)
  })

  it('supports ordinal grade labels on the vertical axis', () => {
    const grades = ['6B+', '6C', '6C+', '7A']
    render(<LineChart label="Verified grade" data={[{ date: '2026-08-01', value: 1 }, { date: '2026-09-01', value: 3 }]} yDomain={[0, 3]} yTicks={[0, 1, 2, 3]} formatYAxisValue={(value) => grades[value] ?? '—'} />)
    expect(screen.getByText('6C')).toBeInTheDocument()
    expect(screen.getByText('6C+')).toBeInTheDocument()
    expect(screen.getByText('7A')).toBeInTheDocument()
  })

  it('can reverse the vertical axis so lower pace values appear higher', () => {
    const { container } = render(<LineChart label="Easy pace" data={[{ date: '2026-08-01', value: 330 }, { date: '2026-08-08', value: 300 }]} reverseY />)
    const points = [...container.querySelectorAll('.chart-point circle:not(.chart-hit-area)')]
    const slowerY = Number(points[0]?.getAttribute('cy'))
    const fasterY = Number(points[1]?.getAttribute('cy'))
    expect(fasterY).toBeLessThan(slowerY)
  })

  it('exposes formatted values on hover and keyboard focus targets', () => {
    const { container } = render(<><LineChart label="Mileage" data={[{ date: '2026-08-01', value: 12.5 }]} formatValue={(value) => `${value} km`} /><BarChart label="Sessions" data={[{ date: 'EASY', value: 3 }]} formatValue={(value) => `${value} runs`} /></>)
    const hoverValues = [...container.querySelectorAll('.chart-hover-value')].map((element) => element.textContent)
    expect(hoverValues).toContain('12.5 km')
    expect(hoverValues).toContain('3 runs')
    expect(container.querySelectorAll('.chart-hover-target[tabindex="0"]')).toHaveLength(2)
  })

  it('retains colour labels when rendering a gym pyramid', () => {
    render(<GradePyramid rows={[{ label: 'Yellow', value: 8, available: 8, colour: '#e8cf4a' }, { label: 'Blue', value: 1, available: 6, colour: '#4f91ee' }]} mode="percent" />)
    expect(screen.getByText('Yellow')).toBeInTheDocument()
    expect(screen.getByText('100%')).toBeInTheDocument()
    expect(screen.getByText('17%')).toBeInTheDocument()
  })
})

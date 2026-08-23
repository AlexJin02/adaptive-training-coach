import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { SettingsPage } from './SettingsPage'

describe('athlete climbing goals', () => {
  afterEach(() => { vi.unstubAllGlobals() })

  it('keeps TB2 and outdoor bouldering goals separate in the profile contract', async () => {
    const profile = {
      id: 1, display_name: 'Athlete', timezone: 'Europe/London', running_phase: 'AEROBIC_BASE', climbing_phase: 'MAX_STRENGTH',
      tb2_long_term_goal: 'V9–V10', outdoor_boulder_goal: 'V10', bouldering_goal: 'V9–V10',
    }
    const mock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const body = init?.method === 'PATCH' ? JSON.parse(String(init.body))
        : url.includes('/athlete/profile') ? profile
          : url.includes('/settings') ? { gym_name: 'Home Gym', grade_display: 'BOTH', retain_screenshots: false, retain_audio: false }
            : { items: [] }
      return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
    })
    vi.stubGlobal('fetch', mock)
    const user = userEvent.setup()
    render(<SettingsPage />)

    const tb2 = await screen.findByLabelText('TB2 long-term goal')
    const outdoor = screen.getByLabelText('Outdoor bouldering goal')
    expect(tb2).toHaveValue('V9–V10')
    expect(outdoor).toHaveValue('V10')
    await user.clear(tb2)
    await user.type(tb2, 'V11')
    await user.clear(outdoor)
    await user.type(outdoor, 'V12')
    await user.click(screen.getByRole('button', { name: 'Save profile' }))

    await waitFor(() => expect(mock.mock.calls.some(([, init]) => init?.method === 'PATCH')).toBe(true))
    const patchCall = mock.mock.calls.find(([, init]) => init?.method === 'PATCH')
    const payload = JSON.parse(String(patchCall?.[1]?.body)) as Record<string, unknown>
    expect(payload).toMatchObject({ tb2_long_term_goal: 'V11', outdoor_boulder_goal: 'V12' })
    expect(payload).not.toHaveProperty('bouldering_goal')
  })
})

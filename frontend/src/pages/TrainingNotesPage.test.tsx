import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { TrainingNotesPage } from './TrainingNotesPage'

describe('training-note filters', () => {
  afterEach(() => { vi.unstubAllGlobals() })

  it('sends the explicit tag filter to the backend query', async () => {
    const mock = vi.fn(async (input: RequestInfo | URL) => {
      void input
      return new Response(JSON.stringify({ items: [] }), { status: 200, headers: { 'Content-Type': 'application/json' } })
    })
    vi.stubGlobal('fetch', mock)
    const user = userEvent.setup()
    render(<TrainingNotesPage />)

    await screen.findByText('No training notes')
    await user.type(screen.getByLabelText('Tag filter'), 'threshold')

    await waitFor(() => expect(mock.mock.calls.some(([input]) => String(input).includes('/training-notes?tag=threshold'))).toBe(true))
  })
})

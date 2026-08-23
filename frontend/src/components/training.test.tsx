import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AdaptationCard, ReadinessCard } from './training'
import type { AdaptationProposal, ReadinessSummary } from '../types'

describe('adaptation proposal editing', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('sends edited plan fields as structured JSON and leaves the displayed original intact', async () => {
    const proposal: AdaptationProposal = {
      id: 9,
      session_id: 4,
      session_title: 'Thursday threshold',
      action: 'REDUCE_VOLUME',
      original_plan: { date: '2026-08-27', duration_minutes: 90, description: '3 × 2 km' },
      proposed_plan: { date: '2026-08-28', duration_minutes: 60, description: '4 × 6 min' },
      reason: 'Lower-body fatigue is high.',
      evidence: ['Tuesday RPE 9'],
      confidence: 'MODERATE',
      source: 'RULE_ENGINE',
      status: 'PENDING',
    }
    const fetchMock = vi.fn(async (...request: [RequestInfo | URL, RequestInit?]) => {
      void request
      return new Response(JSON.stringify({ ...proposal, status: 'EDITED' }), { status: 200, headers: { 'Content-Type': 'application/json' } })
    })
    vi.stubGlobal('fetch', fetchMock)
    const user = userEvent.setup()
    render(<AdaptationCard proposal={proposal} />)
    expect(screen.getByText(/duration minutes: 90/i)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Edit' }))
    const editor = screen.getByLabelText(/Proposed plan JSON/)
    fireEvent.change(editor, { target: { value: JSON.stringify({ date: '2026-08-29', duration_minutes: 50, description: 'Controlled threshold' }) } })
    await user.click(screen.getByRole('button', { name: 'Apply edited plan' }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    const init = fetchMock.mock.calls[0]?.[1]
    if (!init) throw new Error('Expected adaptation decision request options')
    const body = JSON.parse(String(init.body)) as { proposed_plan: Record<string, unknown> }
    expect(body.proposed_plan).toMatchObject({ date: '2026-08-29', duration_minutes: 50 })
    expect(screen.getByText(/duration minutes: 90/i)).toBeInTheDocument()
  })

  it('does not mark an unchanged Apply action as an edited proposal', async () => {
    const proposal: AdaptationProposal = {
      id: 10,
      session_id: 5,
      session_title: 'Easy run',
      action: 'REDUCE_VOLUME',
      original_plan: { planned_duration_minutes: 60 },
      proposed_plan: { planned_duration_minutes: 48 },
      reason: 'Systemic fatigue is high.',
      evidence: ['SYSTEMIC fatigue 8.0'],
      confidence: 'HIGH',
      source: 'RULE_ENGINE',
      status: 'PENDING',
    }
    const fetchMock = vi.fn(async (...request: [RequestInfo | URL, RequestInit?]) => {
      void request
      return new Response(JSON.stringify({ ...proposal, status: 'ACCEPTED' }), { status: 200, headers: { 'Content-Type': 'application/json' } })
    })
    vi.stubGlobal('fetch', fetchMock)
    const user = userEvent.setup()
    render(<AdaptationCard proposal={proposal} />)
    await user.click(screen.getByRole('button', { name: 'Apply' }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit | undefined
    const body = JSON.parse(String(init?.body)) as { decision: string; proposed_plan?: unknown }
    expect(body).toEqual({ decision: 'ACCEPT' })
  })
})

describe('readiness audit detail', () => {
  it('shows LOCAL_SORENESS and its backend-provided moderation evidence', () => {
    const readiness: ReadinessSummary = {
      sport: 'CLIMBING', value: 6.8, label: 'MODERATE', explanation: 'Finger soreness caps climbing readiness at MODERATE.',
      subjective_delta: -0.25, local_soreness_penalty: 0.6, warnings: ['Finger soreness caps climbing readiness at MODERATE.'],
      components: [
        { domain: 'FINGER_FOREARM', value: 7.8, label: 'GOOD' },
        { domain: 'PULLING_UPPER_BODY', value: 7.6, label: 'GOOD' },
        { domain: 'NEURAL', value: 7.5, label: 'GOOD' },
        { domain: 'SYSTEMIC', value: 7.7, label: 'GOOD' },
        { domain: 'LOCAL_SORENESS', value: 4.5, label: 'LOW' },
      ],
    }

    render(<ReadinessCard sport="CLIMBING" readiness={readiness} />)

    expect(screen.getAllByText('MODERATE')).toHaveLength(2)
    expect(screen.getByText('Local Soreness')).toBeInTheDocument()
    expect(screen.getByText('Subjective delta')).toBeInTheDocument()
    expect(screen.getByText('-0.25')).toBeInTheDocument()
    expect(screen.getByText('Local soreness penalty')).toBeInTheDocument()
    expect(screen.getByText('−0.60')).toBeInTheDocument()
    expect(screen.getAllByText('Finger soreness caps climbing readiness at MODERATE.')).toHaveLength(2)
  })
})

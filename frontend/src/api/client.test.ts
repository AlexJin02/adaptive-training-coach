import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from './client'

describe('API request timeouts', () => {
  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('allows mobile audio transcription to finish after the default request timeout', async () => {
    vi.useFakeTimers()
    const requestSignals: AbortSignal[] = []
    vi.stubGlobal('fetch', vi.fn((_input: RequestInfo | URL, init?: RequestInit) => {
      const requestSignal = init?.signal as AbortSignal
      requestSignals.push(requestSignal)
      return new Promise<Response>((resolve, reject) => {
        const completion = window.setTimeout(() => resolve(new Response(JSON.stringify({ transcript: '完成转写' }), { status: 200, headers: { 'Content-Type': 'application/json' } })), 25_000)
        requestSignal?.addEventListener('abort', () => {
          window.clearTimeout(completion)
          reject(new DOMException('Aborted', 'AbortError'))
        })
      })
    }))

    const transcription = api.transcribeWorkoutInput(new Blob(['audio'], { type: 'audio/mp4' }))
    await vi.advanceTimersByTimeAsync(20_001)
    expect(requestSignals[0]?.aborted).toBe(false)
    await vi.advanceTimersByTimeAsync(5_000)
    await expect(transcription).resolves.toEqual({ transcript: '完成转写' })
  })

  it('allows workout structuring to finish after the default request timeout', async () => {
    vi.useFakeTimers()
    const requestSignals: AbortSignal[] = []
    vi.stubGlobal('fetch', vi.fn((_input: RequestInfo | URL, init?: RequestInit) => {
      const requestSignal = init?.signal as AbortSignal
      requestSignals.push(requestSignal)
      return new Promise<Response>((resolve, reject) => {
        const completion = window.setTimeout(() => resolve(new Response(JSON.stringify({ workout_kind: {} }), { status: 200, headers: { 'Content-Type': 'application/json' } })), 25_000)
        requestSignal?.addEventListener('abort', () => {
          window.clearTimeout(completion)
          reject(new DOMException('Aborted', 'AbortError'))
        })
      })
    }))

    const extraction = api.extractWorkoutText('今天跑步 45 分鐘')
    await vi.advanceTimersByTimeAsync(20_001)
    expect(requestSignals[0]?.aborted).toBe(false)
    await vi.advanceTimersByTimeAsync(5_000)
    await expect(extraction).resolves.toEqual({ workout_kind: {} })
  })

  it('allows weekly planning to run beyond the normal API timeout', async () => {
    vi.useFakeTimers()
    const requestSignals: AbortSignal[] = []
    vi.stubGlobal('fetch', vi.fn((_input: RequestInfo | URL, init?: RequestInit) => {
      const requestSignal = init?.signal as AbortSignal
      requestSignals.push(requestSignal)
      return new Promise<Response>((resolve, reject) => {
        const completion = window.setTimeout(() => resolve(new Response(JSON.stringify({ id: 9 }), { status: 200, headers: { 'Content-Type': 'application/json' } })), 65_000)
        requestSignal?.addEventListener('abort', () => {
          window.clearTimeout(completion)
          reject(new DOMException('Aborted', 'AbortError'))
        })
      })
    }))

    const planning = api.generateWeeklyPlan('2026-09-28')
    await vi.advanceTimersByTimeAsync(60_001)
    expect(requestSignals[0]?.aborted).toBe(false)
    await vi.advanceTimersByTimeAsync(5_000)
    await expect(planning).resolves.toEqual({ id: 9 })
  })
})

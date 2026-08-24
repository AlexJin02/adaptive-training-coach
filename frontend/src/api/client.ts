import type {
  AdaptationProposal,
  ApiCapabilities,
  AppSettings,
  ApiList,
  AthleteProfile,
  CalendarEntry,
  ClimbingState,
  CompletedSession,
  FatigueValue,
  Goal,
  GymSet,
  ImportedRunningActivity,
  MonthlyPlanContent,
  MonthlyTrainingBlock,
  PlannedSession,
  PlanParsePreview,
  ReviewPlanProposal,
  ProgressData,
  ReadinessSummary,
  RecoveryCheckIn,
  RunningState,
  TB2Benchmark,
  TodayDashboard,
  TrainingNote,
  WeeklyReview,
  WorkoutExtraction,
} from '../types'

// Production is always served by FastAPI as a one-origin app (including Tailscale phone access).
// Only Vite development may point directly at the local backend.
const API_BASE = (import.meta.env.PROD ? '/api/v1' : import.meta.env.VITE_API_BASE_URL ?? '/api/v1').replace(/\/$/, '')

function audioUploadFilename(file: Blob, stem: string): string {
  const mediaType = (file.type.split(';', 1)[0] ?? '').toLowerCase()
  const extensions: Record<string, string> = {
    'audio/mp4': 'm4a',
    'audio/m4a': 'm4a',
    'audio/x-m4a': 'm4a',
    'audio/mpeg': 'mp3',
    'audio/mp3': 'mp3',
    'audio/ogg': 'ogg',
    'audio/wav': 'wav',
    'audio/x-wav': 'wav',
    'audio/flac': 'flac',
    'audio/webm': 'webm',
  }
  const extension = extensions[mediaType] ?? 'webm'
  return `${stem}.${extension}`
}

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly fieldErrors?: Record<string, string[]>
  readonly retryable: boolean
  readonly requestId?: string

  constructor(message: string, status = 0, details?: Record<string, unknown>) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = typeof details?.code === 'string' ? details.code : status === 0 ? 'NETWORK_ERROR' : 'API_ERROR'
    this.fieldErrors = details?.field_errors as Record<string, string[]> | undefined
    this.retryable = details?.retryable === true || status === 0 || status >= 500
    this.requestId = typeof details?.request_id === 'string' ? details.request_id : undefined
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), 20_000)
  try {
    const isForm = init.body instanceof FormData
    const response = await fetch(`${API_BASE}${path}`, {
      ...init,
      signal: init.signal ?? controller.signal,
      headers: {
        Accept: 'application/json',
        ...(isForm ? {} : { 'Content-Type': 'application/json' }),
        ...init.headers,
      },
    })
    if (!response.ok) {
      let details: Record<string, unknown> = {}
      try {
        details = (await response.json()) as Record<string, unknown>
      } catch {
        details = {}
      }
      const validationDetail = Array.isArray(details.detail)
        ? details.detail.map((item) => {
          if (!item || typeof item !== 'object') return null
          const row = item as { loc?: unknown; msg?: unknown }
          const location = Array.isArray(row.loc) ? row.loc.filter((part) => part !== 'body').join('.') : ''
          const message = typeof row.msg === 'string' ? row.msg.replace(/^Value error,\s*/i, '') : ''
          return message ? `${location ? `${location}: ` : ''}${message}` : null
        }).filter(Boolean).join('; ')
        : ''
      const message = typeof details.detail === 'string' ? details.detail : validationDetail || (typeof details.message === 'string' ? details.message : `Request failed (${response.status})`)
      throw new ApiError(message, response.status, details)
    }
    if (response.status === 204) return undefined as T
    return (await response.json()) as T
  } catch (error) {
    if (error instanceof ApiError) throw error
    if (error instanceof DOMException && error.name === 'AbortError') throw new ApiError('The request timed out. Your unsaved input is still here.')
    throw new ApiError(error instanceof Error ? error.message : 'Unable to reach the local server.')
  } finally {
    window.clearTimeout(timeout)
  }
}

async function download(path: string): Promise<Blob> {
  const response = await fetch(`${API_BASE}${path}`, { headers: { Accept: 'application/octet-stream' } })
  if (!response.ok) throw new ApiError(`Download failed (${response.status})`, response.status)
  return response.blob()
}

async function requestText(path: string): Promise<string> {
  const response = await fetch(`${API_BASE}${path}`, { headers: { Accept: 'text/plain' } })
  if (!response.ok) throw new ApiError(`Request failed (${response.status})`, response.status)
  return response.text()
}

const json = (body: unknown): string => JSON.stringify(body)

export const api = {
  capabilities: () => request<ApiCapabilities>('/capabilities'),
  today: (date?: string) => request<TodayDashboard>(`/today${date ? `?date=${encodeURIComponent(date)}` : ''}`),
  calendar: (start: string, end: string) => request<ApiList<CalendarEntry>>(`/calendar?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`),
  profile: () => request<AthleteProfile>('/athlete/profile'),
  saveProfile: (body: Partial<AthleteProfile>) => request<AthleteProfile>('/athlete/profile', { method: 'PATCH', body: json(body) }),
  goals: () => request<ApiList<Goal>>('/goals'),
  saveGoal: (body: Partial<Goal>) => request<Goal>('/goals', { method: 'POST', body: json(body) }),
  runningState: () => request<RunningState>('/athlete-state/running'),
  climbingState: () => request<ClimbingState>('/athlete-state/climbing'),
  setRunningPhase: (phase: string) => request<RunningState>('/athlete-state/running/phase', { method: 'PATCH', body: json({ phase }) }),
  setClimbingPhase: (phase: string) => request<ClimbingState>('/athlete-state/climbing/phase', { method: 'PATCH', body: json({ phase }) }),
  plannedSessions: (start?: string, end?: string) => request<ApiList<PlannedSession>>(`/planned-sessions${start && end ? `?start=${start}&end=${end}` : ''}`),
  createPlannedSession: (body: Partial<PlannedSession>) => request<PlannedSession>('/planned-sessions', { method: 'POST', body: json(body) }),
  updatePlannedSession: (id: string | number, body: Partial<PlannedSession>) => request<PlannedSession>(`/planned-sessions/${id}`, { method: 'PATCH', body: json(body) }),
  deletePlannedSession: (id: string | number) => request<{ deleted: boolean; id: number }>(`/planned-sessions/${id}`, { method: 'DELETE' }),
  skipPlannedSession: (id: string | number) => request<{ session: PlannedSession; adaptations: AdaptationProposal[] }>(`/planned-sessions/${id}/skip`, { method: 'POST', body: '{}' }),
  completedSessions: () => request<ApiList<CompletedSession>>('/completed-sessions'),
  stravaRunInbox: () => request<ApiList<ImportedRunningActivity>>('/integrations/strava/runs/inbox'),
  syncStravaRuns: () => request<ApiList<ImportedRunningActivity> & { imported: number; restored: number; enriched: number }>('/integrations/strava/sync', { method: 'POST', body: '{}' }),
  completeStravaRun: (id: string | number, body: { session_type: string; title?: string; rpe: number; subjective_feedback_text?: string | null; subjective_feedback_source?: 'VOICE' | 'TEXT' | 'NONE' }) => request<CompletedSession>(`/integrations/strava/runs/${id}/complete`, { method: 'POST', body: json(body) }),
  createCompletedSession: (body: Record<string, unknown>) => request<Record<string, unknown>>('/completed-sessions', { method: 'POST', body: json(body) }),
  deleteCompletedSession: (id: string | number) => request<{ deleted: boolean; id: number }>(`/completed-sessions/${id}`, { method: 'DELETE' }),
  fatigue: () => request<ApiList<FatigueValue>>('/load-readiness/fatigue'),
  readiness: () => request<ApiList<ReadinessSummary>>('/load-readiness/readiness'),
  saveRecoveryCheckIn: (body: RecoveryCheckIn) => request<RecoveryCheckIn>('/recovery-checkins', { method: 'POST', body: json(body) }),
  progress: (range: string) => request<ProgressData>(`/progress?range=${encodeURIComponent(range)}`),
  weeklyReport: (weekStart: string) => requestText(`/training-reports/weekly?week_start=${encodeURIComponent(weekStart)}`),
  monthlyReport: (month: string) => requestText(`/training-reports/monthly?month=${encodeURIComponent(month)}`),
  planTemplate: (cadence: 'weekly' | 'monthly') => requestText(`/training-plans/template/${cadence}`),
  parsePlan: (cadence: 'WEEKLY' | 'MONTHLY', markdown: string) => request<PlanParsePreview>('/training-plans/parse', { method: 'POST', body: json({ cadence, markdown }) }),
  importPlan: (cadence: 'WEEKLY' | 'MONTHLY', markdown: string) => request<PlanParsePreview>('/training-plans/import', { method: 'POST', body: json({ cadence, markdown }) }),
  currentMonthlyBlock: () => request<MonthlyTrainingBlock | null>('/training-plans/monthly/current'),
  updateMonthlyBlock: (id: number, content: Omit<MonthlyPlanContent, 'month' | 'raw_plan_text'>) => request<MonthlyTrainingBlock>(`/training-plans/monthly/${id}`, { method: 'PATCH', body: json(content) }),
  adaptations: () => request<ApiList<AdaptationProposal>>('/adaptations'),
  proposeAdaptation: () => request<ApiList<AdaptationProposal>>('/adaptations/propose', { method: 'POST', body: '{}' }),
  decideAdaptation: (id: string | number, decision: 'ACCEPT' | 'REJECT', proposedPlan?: Record<string, unknown> | string) => request<AdaptationProposal>(`/adaptations/${id}/decision`, { method: 'POST', body: json({ decision, proposed_plan: proposedPlan }) }),
  tb2Benchmarks: () => request<ApiList<TB2Benchmark>>('/climbing/tb2-benchmarks'),
  createTb2Benchmark: (body: Partial<TB2Benchmark>) => request<TB2Benchmark>('/climbing/tb2-benchmarks', { method: 'POST', body: json(body) }),
  createGymSet: (body: Partial<GymSet>) => request<GymSet>('/climbing/gym-sets', { method: 'POST', body: json(body) }),
  updateGymProgress: (setId: string | number, body: Record<string, unknown>) => request<GymSet>(`/climbing/gym-sets/${setId}/progress`, { method: 'PATCH', body: json(body) }),
  saveRouteBenchmark: (body: Record<string, unknown>) => request<Record<string, unknown>>('/climbing/route-benchmark', { method: 'PUT', body: json(body) }),
  notes: (query = '') => request<ApiList<TrainingNote>>(`/training-notes${query ? `?${query}` : ''}`),
  createNote: (body: Partial<TrainingNote>) => request<TrainingNote>('/training-notes', { method: 'POST', body: json(body) }),
  createCoachingPrinciple: (body: { principle: string; source_note_id: string | number }) => request<Record<string, unknown>>('/coaching-principles', { method: 'POST', body: json(body) }),
  processNote: (body: Record<string, unknown>) => request<Partial<TrainingNote>>('/ai/notes/process', { method: 'POST', body: json(body) }),
  transcribeNote: (file: Blob, retain = false) => {
    const data = new FormData()
    data.append('audio', file, audioUploadFilename(file, 'training-note'))
    data.append('retain_raw', String(retain))
    return request<{ transcript: string }>('/ai/notes/transcribe', { method: 'POST', body: data })
  },
  transcribeRunningFeedback: (file: Blob) => {
    const data = new FormData()
    data.append('audio', file, audioUploadFilename(file, 'running-feedback'))
    data.append('retain_raw', 'false')
    return request<{ transcript: string }>('/ai/running-feedback/transcribe', { method: 'POST', body: data })
  },
  transcribeWorkoutInput: (file: Blob) => {
    const data = new FormData()
    data.append('audio', file, audioUploadFilename(file, 'workout-input'))
    return request<{ transcript: string }>('/ai/workouts/transcribe', { method: 'POST', body: data })
  },
  extractWorkoutText: (text: string) => request<WorkoutExtraction>('/ai/workouts/extract-text', { method: 'POST', body: json({ text }) }),
  extractWorkoutImage: (file: File, retain = false) => {
    const data = new FormData()
    data.append('image', file)
    data.append('retain_raw', String(retain))
    return request<WorkoutExtraction>('/ai/workouts/extract-image', { method: 'POST', body: data })
  },
  weeklyReviews: () => request<ApiList<WeeklyReview>>('/weekly-reviews'),
  generateWeeklyReview: (weekStart: string) => request<WeeklyReview>('/weekly-reviews/generate', { method: 'POST', body: json({ week_start: weekStart }) }),
  reviewPlanProposals: (cadence?: 'WEEKLY' | 'MONTHLY') => request<ApiList<ReviewPlanProposal>>(`/review-plan/proposals${cadence ? `?cadence=${cadence}` : ''}`),
  generateWeeklyPlan: (weekStart: string) => request<ReviewPlanProposal>('/review-plan/weekly/generate', { method: 'POST', body: json({ week_start: weekStart }) }),
  generateMonthlyPlan: (monthStart: string) => request<ReviewPlanProposal>('/review-plan/monthly/generate', { method: 'POST', body: json({ month_start: monthStart }) }),
  editReviewPlan: (id: string | number, proposedPlan: Record<string, unknown>) => request<ReviewPlanProposal>(`/review-plan/proposals/${id}`, { method: 'PATCH', body: json({ proposed_plan: proposedPlan }) }),
  approveReviewPlan: (id: string | number) => request<ReviewPlanProposal>(`/review-plan/proposals/${id}/approve`, { method: 'POST', body: '{}' }),
  cancelReviewPlan: (id: string | number) => request<ReviewPlanProposal>(`/review-plan/proposals/${id}/cancel`, { method: 'POST', body: '{}' }),
  createBackup: () => download('/data/backup'),
  exportCsv: (entity: string) => download(`/data/export/${encodeURIComponent(entity)}.csv`),
  restoreBackup: (file: File) => {
    const data = new FormData()
    data.append('backup', file)
    return request<{ restored: boolean; records: number }>('/data/restore', { method: 'POST', body: data })
  },
  seedDemo: () => request<{ created: number }>('/demo/seed', { method: 'POST', body: '{}' }),
  removeDemo: () => request<{ removed: number }>('/demo', { method: 'DELETE' }),
  settings: () => request<AppSettings>('/settings'),
  saveSettings: (body: Partial<AppSettings>) => request<AppSettings>('/settings', { method: 'PATCH', body: json(body) }),
}

export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}

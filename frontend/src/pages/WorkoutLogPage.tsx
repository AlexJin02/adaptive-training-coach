import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import { useResource } from '../api/hooks'
import { useCapabilities } from '../app/CapabilityProvider'
import { Icon } from '../components/Icon'
import { Button, Card, ConfidencePill, EmptyState, ErrorPanel, Field, FormActions, InlineNotice, LoadingGrid, Modal, PageHeader, Pill, SelectField, Tabs, TextAreaField, formatEnum } from '../components/ui'
import { formatDate, formatDuration, formatNumber, formatPace, formatRaceTime, localIsoDate, parseDurationInput, recordLabel } from '../lib/format'
import type { CompletedSession, ExtractionField, ImportedRunningActivity, WorkoutExtraction, WorkoutKind } from '../types'

const runningTypes = ['EASY', 'LONG_RUN', 'QUALITY', 'RACE']
const climbingTypes = ['BOULDERING', 'SPORT_CLIMBING', 'BOARD']
const styleTags = ['crimp', 'sloper', 'pinch', 'compression', 'coordination', 'dyno', 'slab', 'vertical', 'overhang', 'roof', 'technical', 'powerful', 'heel hook', 'toe hook']
const exerciseOptions = ['weighted pull-up', 'pull-up', 'one-arm pull-up progression', 'squat', 'deadlift', 'bench', 'overhead press', 'row', 'hangboard', 'core', 'custom exercise']

type LogMode = 'manual' | 'image' | 'text'

export function WorkoutLogPage(): React.JSX.Element {
  const [params, setParams] = useSearchParams()
  const requested = params.get('action')
  const requestedPlanId = params.get('planned_session_id') ?? ''
  const requestedSessionId = params.get('session_id') ?? ''
  const initialMode: LogMode = requested === 'image' ? 'image' : requested === 'text' ? 'text' : 'manual'
  const [modalOpen, setModalOpen] = useState(Boolean(requested))
  const [mode, setMode] = useState<LogMode>(initialMode)
  const [filter, setFilter] = useState<'ALL' | WorkoutKind>('ALL')
  const [sessionType, setSessionType] = useState('ALL')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [search, setSearch] = useState('')
  const resource = useResource(api.completedSessions, [])
  useEffect(() => {
    if (requested) {
      setMode(requested === 'image' ? 'image' : requested === 'text' ? 'text' : 'manual')
      setModalOpen(true)
    }
  }, [requested])
  const close = () => { setModalOpen(false); setParams({}) }
  const sessionTypes = useMemo(() => [...new Set((resource.data?.items ?? []).map((session) => session.session_type))].sort(), [resource.data])
  const items = useMemo(() => (resource.data?.items ?? []).filter((session) => (filter === 'ALL' || session.workout_kind === filter) && (sessionType === 'ALL' || session.session_type === sessionType) && (!dateFrom || session.date >= dateFrom) && (!dateTo || session.date <= dateTo) && (!search || `${session.title ?? ''} ${session.session_type} ${session.notes ?? ''}`.toLowerCase().includes(search.toLowerCase()))), [dateFrom, dateTo, filter, resource.data, search, sessionType])

  return <div className="page workouts-page">
    <PageHeader eyebrow="EVIDENCE" title="Workout Log" description="Fast entry for completed training, with optional detail when it matters." actions={<div className="button-row"><Button variant="ghost" icon="upload" onClick={() => { setMode('image'); setModalOpen(true) }}>Import</Button><Button icon="plus" onClick={() => { setMode('manual'); setModalOpen(true) }}>Log workout</Button></div>} />
    <RunInbox onCompleted={() => resource.reload()} />
    <Card className="filter-bar workout-filters"><div className="search-field"><Icon name="search" /><input aria-label="Search workouts" placeholder="Search sessions or notes" value={search} onChange={(event) => setSearch(event.target.value)} /></div><Field label="From" type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} /><Field label="To" type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} /><SelectField label="Sport" className="compact-field" value={filter} onChange={(event) => setFilter(event.target.value as typeof filter)}><option value="ALL">All sports</option><option value="RUNNING">Running</option><option value="CLIMBING">Climbing</option><option value="STRENGTH">Strength</option><option value="CROSSFIT_CONDITIONING">CrossFit / conditioning</option><option value="MOBILITY_RECOVERY">Mobility / recovery</option></SelectField><SelectField label="Session type" className="compact-field" value={sessionType} onChange={(event) => setSessionType(event.target.value)}><option value="ALL">All session types</option>{sessionTypes.map((type) => <option key={type} value={type}>{formatEnum(type)}</option>)}</SelectField></Card>
    {resource.loading ? <LoadingGrid count={5} /> : resource.error ? <ErrorPanel message={resource.error.message} onRetry={resource.reload} /> : items.length ? <div className="workout-table"><div className="workout-row workout-head"><span>Date</span><span>Activity</span><span>Session</span><span>Duration</span><span>Details</span></div>{items.map((session) => <WorkoutRow key={session.id} session={session} initialOpen={String(session.id) === requestedSessionId} onClose={() => { if (String(session.id) === requestedSessionId) setParams({}) }} onChanged={resource.reload} />)}</div> : <EmptyState icon="workouts" title="No matching workouts" message="A basic session only needs date and duration. RPE and detailed evidence are optional." action={<Button icon="plus" onClick={() => setModalOpen(true)}>Log first workout</Button>} />}
    <Modal open={modalOpen} title="Record completed training" onClose={close} wide>
      <Tabs label="Workout input method" value={mode} onChange={setMode} items={[{ value: 'manual', label: 'Manual' }, { value: 'image', label: 'Screenshot' }, { value: 'text', label: 'Quick text' }]} />
      {mode === 'manual' ? <ManualWorkoutForm initial={{ planned_session_id: requestedPlanId }} onSaved={() => { close(); resource.reload() }} /> : mode === 'image' ? <ScreenshotImport onSaved={() => { close(); resource.reload() }} onManual={() => setMode('manual')} /> : <TextImport onSaved={() => { close(); resource.reload() }} onManual={() => setMode('manual')} />}
    </Modal>
  </div>
}

function RunInbox({ onCompleted }: { onCompleted: () => void }): React.JSX.Element {
  const { capabilities } = useCapabilities()
  const resource = useResource(api.stravaRunInbox, [])
  const [selected, setSelected] = useState<ImportedRunningActivity | null>(null)
  const [syncing, setSyncing] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const sync = async () => {
    setSyncing(true); setMessage(null)
    try {
      const result = await api.syncStravaRuns()
      const updates = [
        result.imported ? `${result.imported} new run${result.imported === 1 ? '' : 's'} added` : null,
        result.restored ? `${result.restored} missing Workout Log run${result.restored === 1 ? '' : 's'} returned` : null,
        result.enriched ? `${result.enriched} run${result.enriched === 1 ? '' : 's'} updated with Strava performance data` : null,
      ].filter(Boolean)
      setMessage(updates.length ? `${updates.join(' · ')} for review.` : 'Strava and Workout Log are up to date.')
      resource.setData({ items: result.items, total: result.total })
    } catch (reason) {
      setMessage(reason instanceof ApiError ? reason.message : 'Unable to sync Strava.')
    } finally { setSyncing(false) }
  }
  const complete = () => {
    setSelected(null)
    resource.reload()
    onCompleted()
  }
  const items = resource.data?.items ?? []
  return <Card className="run-inbox">
    <div className="run-inbox-heading"><div><span className="eyebrow">STRAVA</span><h2>Run Inbox</h2><p>Imported runs stay here until you add RPE and confirm the completed workout.</p></div><Button variant="ghost" icon="arrow" disabled={syncing || !capabilities.strava_sync_configured} onClick={() => void sync()}>{syncing ? 'Syncing…' : 'Sync Strava'}</Button></div>
    {!capabilities.strava_sync_configured && <InlineNotice title="Strava sync is not configured">{capabilities.strava_sync_reason ?? 'Add Strava credentials to the backend .env, then restart the server.'}</InlineNotice>}
    {message && <InlineNotice tone={message.includes('Unable') || message.includes('failed') ? 'warning' : 'success'}>{message}</InlineNotice>}
    {resource.loading ? <LoadingGrid count={1} /> : resource.error ? <ErrorPanel message={resource.error.message} onRetry={resource.reload} /> : items.length ? <div className="run-inbox-list">{items.map((run) => <article className="run-inbox-item" key={run.id}><div><strong>{run.title}</strong><span>{formatDate(run.date)}{run.start_time ? ` · ${run.start_time.slice(0, 5)}` : ''}</span>{run.planned_session ? <small>Matched: {run.planned_session.title}</small> : <small>Standalone run · no planned session matched</small>}</div><div className="run-inbox-metrics"><span><strong>{formatNumber(run.distance_km, 2)}</strong> km</span><span><strong>{formatRaceTime(run.elapsed_time_seconds)}</strong> elapsed</span><span><strong>{formatPace(run.average_pace_seconds_per_km)}</strong> /km</span></div><Button onClick={() => setSelected(run)}>Complete Review</Button></article>)}</div> : <p className="muted">No Strava runs are waiting for review.</p>}
    <Modal open={Boolean(selected)} title="Post-Run Review" onClose={() => setSelected(null)} wide>{selected && <StravaRunReview run={selected} onSaved={complete} />}</Modal>
  </Card>
}

export function StravaRunReview({ run, onSaved }: { run: ImportedRunningActivity; onSaved: () => void }): React.JSX.Element {
  const [sessionType, setSessionType] = useState(run.suggested_session_type)
  const [title, setTitle] = useState(run.planned_session?.title ?? run.title)
  const [rpe, setRpe] = useState<number | null>(null)
  const [feedbackText, setFeedbackText] = useState('')
  const [feedbackSource, setFeedbackSource] = useState<'VOICE' | 'TEXT' | 'NONE'>('NONE')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const save = async () => {
    if (rpe == null) { setError('Choose an RPE from 1 to 10 before saving.'); return }
    setBusy(true); setError(null)
    try {
      await api.completeStravaRun(run.id, { session_type: sessionType, title: title.trim() || run.title, rpe, subjective_feedback_text: feedbackText.trim() || null, subjective_feedback_source: feedbackText.trim() ? feedbackSource === 'NONE' ? 'TEXT' : feedbackSource : 'NONE' })
      onSaved()
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : 'Unable to save this imported run.')
    } finally { setBusy(false) }
  }
  return <div className="post-run-review stack-form">
    {run.planned_session ? <InlineNotice tone="success" title="Matched planned session">{run.planned_session.title} · {formatEnum(run.planned_session.session_type)}. Saving will mark this Calendar session completed while preserving its prescription.</InlineNotice> : <InlineNotice title="Standalone run">No same-date planned running session was available. Saving will create a standalone completed workout.</InlineNotice>}
    <Card title="Objective activity data"><div className="form-grid four"><div><span className="field-label">Date</span><strong>{formatDate(run.date)}</strong></div><div><span className="field-label">Distance</span><strong>{formatNumber(run.distance_km, 2)} km</strong></div><div><span className="field-label">Elapsed time</span><strong>{formatRaceTime(run.elapsed_time_seconds)}</strong></div><div><span className="field-label">Average pace</span><strong>{formatPace(run.average_pace_seconds_per_km)} /km</strong></div><div><span className="field-label">Average HR</span><strong>{run.average_hr ?? 'Not available'}</strong></div><div><span className="field-label">Max HR</span><strong>{run.max_hr ?? 'Not available'}</strong></div><div><span className="field-label">Elevation</span><strong>{run.elevation_m != null ? `${formatNumber(run.elevation_m)} m` : 'Not available'}</strong></div><div><span className="field-label">Cadence</span><strong>{run.cadence != null ? `${formatNumber(run.cadence)} spm` : 'Not available'}</strong></div></div></Card>
    <div className="form-grid two"><SelectField label="Run type" value={sessionType} onChange={(event) => setSessionType(event.target.value as typeof sessionType)}>{runningTypes.map((item) => <option key={item} value={item}>{formatEnum(item)}</option>)}</SelectField><Field label="Workout title" value={title} onChange={(event) => setTitle(event.target.value)} /></div>
    <StravaLapTable run={run} />
    <fieldset className="rpe-picker"><legend>RPE · required</legend><p className="muted">1 is very easy; 10 is maximal.</p><div>{Array.from({ length: 10 }, (_, index) => index + 1).map((value) => <button type="button" aria-pressed={rpe === value} className={rpe === value ? 'selected' : ''} key={value} onClick={() => setRpe(value)}>{value}</button>)}</div></fieldset>
    <RunningFeedbackRecorder text={feedbackText} source={feedbackSource} onChange={(text, source) => { setFeedbackText(text); setFeedbackSource(source) }} />
    {error && <InlineNotice tone="warning">{error} The run remains in your Inbox.</InlineNotice>}
    <FormActions><Button disabled={busy || rpe == null} onClick={() => void save()}>{busy ? 'Saving…' : 'Save Completed Workout'}</Button></FormActions>
  </div>
}

function StravaLapTable({ run }: { run: ImportedRunningActivity }): React.JSX.Element {
  if (!run.laps.length) return <Card title="Strava laps"><p className="muted">No lap data was available for this activity.</p></Card>
  return <Card title="Strava laps"><div className="lap-table"><div className="lap-row lap-head"><span>Lap</span><span>Distance</span><span>Elapsed</span><span>Pace</span><span>Avg HR</span><span>Cadence</span></div>{run.laps.map((lap) => <div className="lap-row" key={lap.lap_index}><span data-label="Lap">{lap.lap_index}</span><span data-label="Distance">{formatNumber(lap.distance_km, 2)} km</span><span data-label="Elapsed">{formatRaceTime(lap.elapsed_time_seconds)}</span><span data-label="Pace">{formatPace(lap.pace_seconds_per_km)} /km</span><span data-label="Avg HR">{lap.average_hr ?? '—'}</span><span data-label="Cadence">{lap.cadence != null ? `${formatNumber(lap.cadence)} spm` : '—'}</span></div>)}</div></Card>
}

function WorkoutRow({ session, onChanged, initialOpen = false, onClose }: { session: CompletedSession; onChanged: () => void; initialOpen?: boolean; onClose?: () => void }): React.JSX.Element {
  const [open, setOpen] = useState(initialOpen)
  useEffect(() => { if (initialOpen) setOpen(true) }, [initialOpen])
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const strength = session.strength
  const strengthSets = session.strength_sets ?? strength?.sets ?? []
  const workoutName = session.workout_name ?? strength?.workout_name
  const rounds = session.rounds ?? strength?.rounds
  const resultTime = session.result_time_seconds ?? strength?.result_time_seconds
  const closeDetail = () => { setOpen(false); onClose?.() }
  const deleteRecord = async () => { setBusy(true); setError(null); try { await api.deleteCompletedSession(session.id); closeDetail(); onChanged() } catch (reason) { setError(reason instanceof ApiError ? reason.message : 'Unable to delete this workout.') } finally { setBusy(false) } }
  return <>
    <article className="workout-row"><span data-label="Date">{formatDate(session.date)}</span><span data-label="Activity"><Pill tone={session.workout_kind === 'RUNNING' ? 'run' : session.workout_kind === 'CLIMBING' ? 'climb' : 'neutral'}>{formatEnum(session.workout_kind)}</Pill>{session.is_demo && <Pill tone="moderate">DEMO</Pill>}</span><span data-label="Session"><strong>{session.title ?? formatEnum(session.session_type)}</strong><small>{session.distance_km ? `${formatNumber(session.distance_km, 1)} km` : session.board_name ?? session.gym_or_crag ?? workoutName ?? ''}</small></span><span data-label="Duration">{formatDuration(session.duration_minutes)}<small>{session.rpe ? `RPE ${session.rpe}` : 'RPE not recorded'}</small></span><span data-label="Details"><Button variant="ghost" aria-label={`View ${session.title ?? session.session_type}`} icon="chevron" onClick={() => setOpen(true)} /></span></article>
    <Modal open={open} title={session.title ?? formatEnum(session.session_type)} onClose={closeDetail} wide><div className="stack-form">
      {session.is_demo && <Pill tone="moderate">DEMO DATA</Pill>}
      <div className="form-grid three"><div><span className="field-label">Date</span><strong>{formatDate(session.date)}</strong></div><div><span className="field-label">Duration</span><strong>{formatDuration(session.duration_minutes)}</strong></div><div><span className="field-label">RPE</span><strong>{session.rpe ?? 'Not recorded'}</strong></div>{session.distance_km != null && <div><span className="field-label">Distance</span><strong>{formatNumber(session.distance_km, 2)} km</strong></div>}{session.average_hr != null && <div><span className="field-label">Heart rate</span><strong>{session.average_hr} avg{session.max_hr ? ` · ${session.max_hr} max` : ''}</strong></div>}{session.cadence != null && <div><span className="field-label">Cadence</span><strong>{formatNumber(session.cadence)} spm</strong></div>}{session.gym_or_crag && <div><span className="field-label">Gym / crag</span><strong>{session.gym_or_crag}</strong></div>}{session.board_name && <div><span className="field-label">Board</span><strong>{session.board_name}{session.angle != null ? ` · ${session.angle}°` : ''}</strong></div>}{workoutName && <div><span className="field-label">Workout</span><strong>{workoutName}</strong></div>}{rounds != null && <div><span className="field-label">Rounds</span><strong>{formatNumber(rounds, 1)}</strong></div>}{resultTime != null && <div><span className="field-label">Result time</span><strong>{formatRaceTime(resultTime)}</strong></div>}</div>
      <CompletedLapTable records={session.splits} />
      <DetailRecords title="Intervals" records={session.interval_blocks} />
      <ClimbingAttemptTable records={session.climbing_attempts} />
      <DetailRecords title="Strength sets" records={strengthSets} />
      {session.notes && <Card title="Session notes"><p>{session.notes}</p></Card>}
      {session.subjective_feedback_text && <Card title="How this run felt"><p>{session.subjective_feedback_text}</p><p className="card-note">{session.subjective_feedback_source === 'VOICE' ? 'Voice transcript, reviewed by athlete' : 'Written by athlete'}</p></Card>}
      {error && <InlineNotice tone="warning">{error}</InlineNotice>}
      {confirmDelete ? <InlineNotice tone="warning" title="Permanently delete this workout?"><p>This cannot be undone. The workout and its detailed evidence will be removed, and training calculations will be updated.</p><div className="button-row"><Button variant="ghost" disabled={busy} onClick={() => setConfirmDelete(false)}>Cancel</Button><Button variant="danger" disabled={busy} onClick={() => void deleteRecord()}>{busy ? 'Deleting…' : 'Delete permanently'}</Button></div></InlineNotice> : <FormActions><Button variant="danger" onClick={() => setConfirmDelete(true)}>Delete workout</Button></FormActions>}
    </div></Modal>
  </>
}

function CompletedLapTable({ records }: { records?: Array<Record<string, unknown>> }): React.JSX.Element | null {
  if (!records?.length) return null
  return <Card title="Lap details"><div className="lap-table completed-lap-table">
    <div className="lap-row completed-lap-row lap-head"><span>Lap</span><span>Distance</span><span>Elapsed</span><span>Pace</span><span>Avg HR</span><span>Cadence</span></div>
    {records.map((record, index) => {
      const distance = numberFrom(record.distance_km ?? record.distance)
      const elapsedSeconds = numberFrom(record.elapsed_time_seconds)
      const elapsedText = elapsedSeconds != null ? formatRaceTime(elapsedSeconds) : stringFrom(record.time ?? record.elapsed_time)
      const explicitPace = numberFrom(record.pace_seconds_per_km)
      const calculatedPace = explicitPace ?? (distance && elapsedText ? durationTextSeconds(elapsedText) / distance : null)
      const paceText = calculatedPace != null && Number.isFinite(calculatedPace) ? `${formatPace(calculatedPace)} /km` : paceString(record.pace)
      const heartRate = numberFrom(record.average_hr ?? record.hr)
      const cadence = numberFrom(record.cadence)
      return <div className="lap-row completed-lap-row" key={`${String(record.lap_index ?? index + 1)}-${index}`}>
        <span data-label="Lap">{String(record.lap_index ?? index + 1)}</span>
        <span data-label="Distance">{distance != null ? `${formatNumber(distance, 2)} km` : '—'}</span>
        <span data-label="Elapsed">{elapsedText || '—'}</span>
        <span data-label="Pace">{paceText || '—'}</span>
        <span data-label="Avg HR">{heartRate != null ? `${formatNumber(heartRate)} bpm` : '—'}</span>
        <span data-label="Cadence">{cadence != null ? `${formatNumber(cadence)} spm` : '—'}</span>
      </div>
    })}
  </div></Card>
}

function ClimbingAttemptTable({ records }: { records?: Array<Record<string, unknown>> }): React.JSX.Element | null {
  if (!records?.length) return null
  return <Card title="Climbing attempts"><div className="attempt-table">
    <div className="attempt-row attempt-head"><span>Problem</span><span>Grade</span><span>Attempts</span><span>Sends</span><span>Result</span><span>Styles</span></div>
    {records.map((record, index) => {
      const sent = record.sent === true
      const sends = numberFrom(record.send_count ?? record.sends) ?? (sent ? 1 : 0)
      const styles = Array.isArray(record.style_tags ?? record.styles) ? (record.style_tags ?? record.styles) as unknown[] : []
      const result = stringFrom(record.outcome) || (record.flash === true ? 'Flash' : record.repeat === true ? 'Repeat' : record.project === true ? 'Project' : sent || sends > 0 ? 'Sent' : 'Not sent')
      return <div className="attempt-row" key={`${String(record.id ?? record.problem ?? index)}-${index}`}>
        <span data-label="Problem">{stringFrom(record.problem) || `Problem ${index + 1}`}</span>
        <span data-label="Grade">{stringFrom(record.grade ?? record.grade_or_colour ?? record.colour) || '—'}</span>
        <span data-label="Attempts">{numberFrom(record.attempts ?? record.attempt_count) ?? '—'}</span>
        <span data-label="Sends">{sends}</span>
        <span data-label="Result">{formatEnum(result)}</span>
        <span data-label="Styles">{styles.length ? styles.map(String).join(', ') : '—'}</span>
      </div>
    })}
  </div></Card>
}

function numberFrom(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim() && Number.isFinite(Number(value))) return Number(value)
  return null
}

function stringFrom(value: unknown): string {
  return typeof value === 'string' ? value.trim() : ''
}

function durationTextSeconds(value: string): number {
  return (parseDurationInput(value) ?? Number.NaN) * 60
}

function paceString(value: unknown): string {
  if (typeof value === 'number' && Number.isFinite(value)) return `${formatPace(value)} /km`
  const text = stringFrom(value)
  if (!text) return ''
  return /\/km$/i.test(text) ? text.replace(/\/km$/i, ' /km') : `${text} /km`
}

function DetailRecords({ title, records }: { title: string; records?: Array<Record<string, unknown>> }): React.JSX.Element | null {
  if (!records?.length) return null
  return <Card title={title}>{records.map((record, index) => <pre className="detail-json" key={index}>{recordLabel(record)}</pre>)}</Card>
}

interface WorkoutDraft {
  date: string; start_time: string; workout_kind: WorkoutKind; session_type: string; title: string; duration_minutes: string; rpe: string; notes: string; planned_session_id: string
  distance_km: string; average_pace: string; average_hr: string; max_hr: string; elevation_m: string; cadence: string; power_w: string
  gym_or_crag: string; board_name: string; angle: string; hard_attempts: string; max_attempted: string; max_sent: string
  workout_name: string; rounds: string; result_time: string
}

const initialDraft: WorkoutDraft = { date: localIsoDate(), start_time: '', workout_kind: 'RUNNING', session_type: 'EASY', title: 'Easy Run', duration_minutes: '45:00', rpe: '3', notes: '', planned_session_id: '', distance_km: '', average_pace: '', average_hr: '', max_hr: '', elevation_m: '', cadence: '', power_w: '', gym_or_crag: '', board_name: '', angle: '', hard_attempts: '', max_attempted: '', max_sent: '', workout_name: '', rounds: '', result_time: '' }

function ManualWorkoutForm({ onSaved, initial }: { onSaved: () => void; initial?: Partial<WorkoutDraft> }): React.JSX.Element {
  const [form, setForm] = useState<WorkoutDraft>({ ...initialDraft, ...initial })
  const planned = useResource(api.plannedSessions, [])
  const [intervals, setIntervals] = useState([{ phase: 'Warmup', detail: '15 min easy' }, { phase: 'Main', detail: '6 × 1 km @ target pace · 90 sec jog' }, { phase: 'Cooldown', detail: '10 min easy' }])
  const [splits, setSplits] = useState<{ distance: string; time: string; hr: string }[]>([])
  const [problems, setProblems] = useState<{ problem: string; grade: string; attempts: string; send_count: string; styles: string[] }[]>([])
  const [exercises, setExercises] = useState([{ exercise: 'weighted pull-up', sets: '3', reps: '5', load: '', rpe: '', rir: '' }])
  const [advanced, setAdvanced] = useState(false)
  const [feedbackText, setFeedbackText] = useState('')
  const [feedbackSource, setFeedbackSource] = useState<'VOICE' | 'TEXT' | 'NONE'>('NONE')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const typeOptions = form.workout_kind === 'RUNNING' ? runningTypes : form.workout_kind === 'CLIMBING' ? climbingTypes : form.workout_kind === 'STRENGTH' ? ['Strength'] : form.workout_kind === 'CROSSFIT_CONDITIONING' ? ['CrossFit / Conditioning'] : ['Mobility / Recovery']
  const set = (key: keyof WorkoutDraft, value: string) => setForm((current) => ({ ...current, [key]: value }))
  const changeKind = (kind: WorkoutKind) => setForm((current) => ({ ...current, workout_kind: kind, session_type: kind === 'RUNNING' ? 'EASY' : kind === 'CLIMBING' ? 'BOULDERING' : kind === 'STRENGTH' ? 'Strength' : kind === 'CROSSFIT_CONDITIONING' ? 'CrossFit / Conditioning' : 'Mobility / Recovery' }))
  const submit = async (event: FormEvent) => {
    event.preventDefault(); setError(null)
    const duration = parseDurationInput(form.duration_minutes); const rpe = form.rpe === '' ? null : Number(form.rpe)
    if (duration == null || duration < 1) { setError('Duration must be at least one minute and use minutes, M:SS, or H:MM:SS.'); return }
    if (rpe != null && (!Number.isFinite(rpe) || rpe < 1 || rpe > 10)) { setError('When entered, RPE must be between 1 and 10.'); return }
    setBusy(true)
    const numericOrNull = (value: string) => value === '' ? null : Number(value)
    const payload = {
      date: form.date, start_time: form.start_time || null, workout_kind: form.workout_kind, session_type: form.session_type, title: form.title || null, duration_minutes: duration, rpe, notes: form.notes || null, planned_session_id: form.planned_session_id || null,
      distance_km: numericOrNull(form.distance_km), average_pace: form.average_pace || null, average_hr: numericOrNull(form.average_hr), max_hr: numericOrNull(form.max_hr), elevation_m: numericOrNull(form.elevation_m), cadence: numericOrNull(form.cadence), power_w: numericOrNull(form.power_w),
      gym_or_crag: form.gym_or_crag || null, board_name: form.session_type === 'BOARD' ? form.board_name || null : null, angle: form.session_type === 'BOARD' ? numericOrNull(form.angle) : null, hard_attempts: numericOrNull(form.hard_attempts), max_attempted: form.max_attempted || null, max_sent: form.max_sent || null,
      workout_name: form.workout_name || null, rounds: numericOrNull(form.rounds), result_time: form.result_time || null,
      interval_blocks: form.workout_kind === 'RUNNING' ? intervals : [], splits: form.workout_kind === 'RUNNING' ? splits : [], climbing_attempts: form.workout_kind === 'CLIMBING' ? problems : [], strength_sets: ['STRENGTH', 'CROSSFIT_CONDITIONING'].includes(form.workout_kind) ? exercises : [],
      subjective_feedback_text: form.workout_kind === 'RUNNING' ? feedbackText.trim() || null : null,
      subjective_feedback_source: form.workout_kind === 'RUNNING' && feedbackText.trim() ? feedbackSource === 'NONE' ? 'TEXT' : feedbackSource : 'NONE',
    }
    try { await api.createCompletedSession(payload); onSaved() }
    catch (reason) { setError(reason instanceof ApiError ? reason.message : 'Unable to save workout.') }
    finally { setBusy(false) }
  }
  return <form className="stack-form workout-form" onSubmit={(event) => void submit(event)}>
    <InlineNotice>Date and duration are required factual observations. RPE and detailed metrics are optional; no load or readiness score is calculated.</InlineNotice>
    <div className="form-grid three">
      <SelectField label="Activity" value={form.workout_kind} onChange={(event) => changeKind(event.target.value as WorkoutKind)}><option value="RUNNING">Running</option><option value="CLIMBING">Climbing</option><option value="STRENGTH">Strength</option><option value="CROSSFIT_CONDITIONING">CrossFit / conditioning</option><option value="MOBILITY_RECOVERY">Mobility / recovery</option></SelectField>
      <SelectField label="Session type" value={form.session_type} onChange={(event) => set('session_type', event.target.value)}>{typeOptions.map((item) => <option key={item} value={item}>{formatEnum(item)}</option>)}</SelectField>
      <Field label="Title" value={form.title} onChange={(event) => set('title', event.target.value)} placeholder="Threshold — 4 × 8 min" />
      <Field label="Date" required type="date" value={form.date} onChange={(event) => set('date', event.target.value)} />
      <Field label="Start time" type="time" value={form.start_time} onChange={(event) => set('start_time', event.target.value)} />
      <Field label="Duration" required inputMode="numeric" placeholder="45:00 or 1:05:01" value={form.duration_minutes} onChange={(event) => set('duration_minutes', event.target.value)} hint="Use M:SS or H:MM:SS. A plain number is treated as minutes." />
      <Field label="RPE (1–10) · optional" type="number" min="1" max="10" value={form.rpe} onChange={(event) => set('rpe', event.target.value)} hint="Stored as a raw observation only." />
      <SelectField label="Linked planned session" value={form.planned_session_id} onChange={(event) => set('planned_session_id', event.target.value)} hint="Links plan and actual without deleting either record."><option value="">Extra / unplanned workout</option>{form.planned_session_id && !planned.data?.items.some((session) => String(session.id) === form.planned_session_id) && <option value={form.planned_session_id}>Planned session #{form.planned_session_id}</option>}{planned.data?.items.map((session) => <option key={session.id} value={session.id}>{session.date} · {session.title}</option>)}</SelectField>
    </div>
    {form.workout_kind === 'RUNNING' && <RunningFields form={form} set={set} advanced={advanced} intervals={intervals} setIntervals={setIntervals} splits={splits} setSplits={setSplits} />}
    {form.workout_kind === 'CLIMBING' && <ClimbingFields form={form} set={set} advanced={advanced} problems={problems} setProblems={setProblems} />}
    {form.workout_kind === 'CROSSFIT_CONDITIONING' && <div className="form-grid three"><Field label="Workout name" value={form.workout_name} onChange={(event) => set('workout_name', event.target.value)} /><Field label="Rounds" type="number" min="0" value={form.rounds} onChange={(event) => set('rounds', event.target.value)} /><Field label="Result / time" inputMode="numeric" placeholder="12:34 or 1:05:01" value={form.result_time} onChange={(event) => set('result_time', event.target.value)} /></div>}
    {(form.workout_kind === 'STRENGTH' || form.workout_kind === 'CROSSFIT_CONDITIONING') && <StrengthFields exercises={exercises} setExercises={setExercises} />}
    {(form.workout_kind === 'RUNNING' || form.workout_kind === 'CLIMBING') && <Button type="button" variant="ghost" icon={advanced ? 'chevron' : 'plus'} onClick={() => setAdvanced((value) => !value)}>{advanced ? 'Hide optional detail' : 'Add splits / attempts / metrics'}</Button>}
    {form.workout_kind === 'RUNNING' && <RunningFeedbackRecorder text={feedbackText} source={feedbackSource} onChange={(text, source) => { setFeedbackText(text); setFeedbackSource(source) }} />}
    <TextAreaField label="Notes" rows={4} value={form.notes} onChange={(event) => set('notes', event.target.value)} placeholder="Execution, feel, conditions, pain-free observations…" />
    {error && <InlineNotice tone="warning">{error}</InlineNotice>}
    <FormActions><Button type="submit" disabled={busy}>{busy ? 'Saving…' : 'Save workout'}</Button></FormActions>
  </form>
}

function RunningFields({ form, set, advanced, intervals, setIntervals, splits, setSplits }: { form: WorkoutDraft; set: (key: keyof WorkoutDraft, value: string) => void; advanced: boolean; intervals: { phase: string; detail: string }[]; setIntervals: React.Dispatch<React.SetStateAction<{ phase: string; detail: string }[]>>; splits: { distance: string; time: string; hr: string }[]; setSplits: React.Dispatch<React.SetStateAction<{ distance: string; time: string; hr: string }[]>> }): React.JSX.Element {
  const structured = form.session_type === 'QUALITY'
  return <><div className="form-grid four"><Field label="Distance (km)" type="number" min="0" step="0.01" value={form.distance_km} onChange={(event) => set('distance_km', event.target.value)} /><Field label="Average pace" placeholder="5:12 /km" value={form.average_pace} onChange={(event) => set('average_pace', event.target.value)} /><Field label="Average HR" type="number" min="0" value={form.average_hr} onChange={(event) => set('average_hr', event.target.value)} /><Field label="Max HR" type="number" min="0" value={form.max_hr} onChange={(event) => set('max_hr', event.target.value)} /></div>{advanced && <div className="form-grid three"><Field label="Elevation (m)" type="number" value={form.elevation_m} onChange={(event) => set('elevation_m', event.target.value)} /><Field label="Cadence (spm)" type="number" value={form.cadence} onChange={(event) => set('cadence', event.target.value)} /><Field label="Power (W)" type="number" value={form.power_w} onChange={(event) => set('power_w', event.target.value)} /></div>}{structured && <div className="subform"><div className="subform-header"><div><strong>Structured blocks</strong><span>Warm-up, main work and cooldown</span></div><Button type="button" variant="ghost" icon="plus" onClick={() => setIntervals((current) => [...current, { phase: 'Main', detail: '' }])}>Block</Button></div>{intervals.map((block, index) => <div className="inline-editor" key={`${block.phase}-${index}`}><select aria-label={`Block ${index + 1} phase`} value={block.phase} onChange={(event) => setIntervals((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, phase: event.target.value } : item))}><option>Warmup</option><option>Main</option><option>Cooldown</option></select><input aria-label={`Block ${index + 1} detail`} value={block.detail} onChange={(event) => setIntervals((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, detail: event.target.value } : item))} /><Button type="button" variant="ghost" icon="trash" aria-label="Remove block" onClick={() => setIntervals((current) => current.filter((_, itemIndex) => itemIndex !== index))} /></div>)}</div>}{advanced && <div className="subform"><div className="subform-header"><div><strong>Splits</strong><span>Optional lap evidence</span></div><Button type="button" variant="ghost" icon="plus" onClick={() => setSplits((current) => [...current, { distance: '1', time: '', hr: '' }])}>Split</Button></div>{splits.map((split, index) => <div className="inline-editor four" key={index}><input aria-label={`Split ${index + 1} distance`} placeholder="km" value={split.distance} onChange={(event) => setSplits((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, distance: event.target.value } : item))} /><input aria-label={`Split ${index + 1} time`} placeholder="time" value={split.time} onChange={(event) => setSplits((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, time: event.target.value } : item))} /><input aria-label={`Split ${index + 1} HR`} placeholder="HR" value={split.hr} onChange={(event) => setSplits((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, hr: event.target.value } : item))} /><Button type="button" variant="ghost" icon="trash" aria-label="Remove split" onClick={() => setSplits((current) => current.filter((_, itemIndex) => itemIndex !== index))} /></div>)}</div>}</>
}

function ClimbingFields({ form, set, advanced, problems, setProblems }: { form: WorkoutDraft; set: (key: keyof WorkoutDraft, value: string) => void; advanced: boolean; problems: { problem: string; grade: string; attempts: string; send_count: string; styles: string[] }[]; setProblems: React.Dispatch<React.SetStateAction<{ problem: string; grade: string; attempts: string; send_count: string; styles: string[] }[]>> }): React.JSX.Element {
  return <><div className="form-grid four"><Field label="Gym / crag" value={form.gym_or_crag} onChange={(event) => set('gym_or_crag', event.target.value)} />{form.session_type === 'BOARD' && <><SelectField label="Board" value={form.board_name} onChange={(event) => set('board_name', event.target.value)}><option value="">Not specified</option><option>Tension Board 2</option><option>Kilter Board</option><option>MoonBoard</option><option>Other</option></SelectField><Field label="Angle (°)" type="number" min="0" max="90" value={form.angle} onChange={(event) => set('angle', event.target.value)} /></>}<Field label="Hard attempts" type="number" min="0" value={form.hard_attempts} onChange={(event) => set('hard_attempts', event.target.value)} /><Field label="Max attempted grade / colour" value={form.max_attempted} onChange={(event) => set('max_attempted', event.target.value)} /><Field label="Max sent grade / colour" value={form.max_sent} onChange={(event) => set('max_sent', event.target.value)} /></div>{advanced && <div className="subform"><div className="subform-header"><div><strong>Grade / colour performance</strong><span>Record attempts and sends without calculating load</span></div><Button type="button" variant="ghost" icon="plus" onClick={() => setProblems((current) => [...current, { problem: '', grade: '', attempts: '1', send_count: '0', styles: [] }])}>Grade</Button></div>{problems.map((problem, index) => <div className="problem-editor" key={index}><div className="inline-editor four"><input aria-label={`Problem ${index + 1}`} placeholder="problem / colour" value={problem.problem} onChange={(event) => setProblems((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, problem: event.target.value } : item))} /><input aria-label={`Problem ${index + 1} grade`} placeholder="grade" value={problem.grade} onChange={(event) => setProblems((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, grade: event.target.value } : item))} /><input aria-label={`Problem ${index + 1} attempts`} type="number" min="1" value={problem.attempts} onChange={(event) => setProblems((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, attempts: event.target.value } : item))} /><input aria-label={`Problem ${index + 1} sends`} type="number" min="0" value={problem.send_count} onChange={(event) => setProblems((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, send_count: event.target.value } : item))} /></div><div className="tag-picker">{styleTags.map((tag) => <button className={problem.styles.includes(tag) ? 'selected' : ''} type="button" key={tag} onClick={() => setProblems((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, styles: item.styles.includes(tag) ? item.styles.filter((value) => value !== tag) : [...item.styles, tag] } : item))}>{tag}</button>)}</div></div>)}</div>}</>
}

function StrengthFields({ exercises, setExercises }: { exercises: { exercise: string; sets: string; reps: string; load: string; rpe: string; rir: string }[]; setExercises: React.Dispatch<React.SetStateAction<{ exercise: string; sets: string; reps: string; load: string; rpe: string; rir: string }[]>> }): React.JSX.Element {
  const update = (index: number, key: keyof (typeof exercises)[number], value: string) => setExercises((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, [key]: value } : item))
  return <div className="subform"><div className="subform-header"><div><strong>Exercise sets</strong><span>Stored as supporting training details</span></div><Button type="button" variant="ghost" icon="plus" onClick={() => setExercises((current) => [...current, { exercise: 'custom exercise', sets: '', reps: '', load: '', rpe: '', rir: '' }])}>Exercise</Button></div>{exercises.map((item, index) => <div className="strength-row" key={index}><select aria-label={`Exercise ${index + 1}`} value={item.exercise} onChange={(event) => update(index, 'exercise', event.target.value)}>{exerciseOptions.map((exercise) => <option key={exercise}>{exercise}</option>)}</select><input aria-label="Sets" placeholder="sets" type="number" min="0" value={item.sets} onChange={(event) => update(index, 'sets', event.target.value)} /><input aria-label="Reps" placeholder="reps" type="number" min="0" value={item.reps} onChange={(event) => update(index, 'reps', event.target.value)} /><input aria-label="Load" placeholder="kg" type="number" min="0" value={item.load} onChange={(event) => update(index, 'load', event.target.value)} /><input aria-label="RPE" placeholder="RPE" type="number" min="1" max="10" value={item.rpe} onChange={(event) => update(index, 'rpe', event.target.value)} /><input aria-label="RIR" placeholder="RIR" type="number" min="0" value={item.rir} onChange={(event) => update(index, 'rir', event.target.value)} /></div>)}</div>
}

function ScreenshotImport({ onSaved, onManual }: { onSaved: () => void; onManual: () => void }): React.JSX.Element {
  const { capabilities } = useCapabilities(); const [file, setFile] = useState<File | null>(null); const [retain, setRetain] = useState(false); const [result, setResult] = useState<WorkoutExtraction | null>(null); const [busy, setBusy] = useState(false); const [error, setError] = useState<string | null>(null)
  const extract = async () => { if (!file) return; setBusy(true); setError(null); try { setResult(await api.extractWorkoutImage(file, retain)) } catch (reason) { setError(reason instanceof ApiError ? reason.message : 'Image extraction failed.') } finally { setBusy(false) } }
  if (!capabilities.image_extraction) return <div className="degraded-flow"><InlineNotice tone="warning" title="Screenshot extraction unavailable">{capabilities.reason ?? 'Configure an OpenAI vision model in the backend environment.'}</InlineNotice><Button icon="edit" onClick={onManual}>Use manual workout form</Button></div>
  if (result) return <ExtractionPreview result={result} onBack={() => setResult(null)} onSaved={onSaved} />
  return <div className="import-flow"><label className="drop-zone"><Icon name="upload" size={32} /><strong>{file ? file.name : 'Choose a Garmin, Strava or similar screenshot'}</strong><span>PNG, JPEG or WebP · extraction never saves a workout automatically</span><input type="file" accept="image/png,image/jpeg,image/webp" onChange={(event) => setFile(event.target.files?.[0] ?? null)} /></label><label className="switch-row"><input type="checkbox" checked={retain} onChange={(event) => setRetain(event.target.checked)} /><span><strong>Retain raw screenshot locally</strong><small>Off by default. Otherwise deleted after successful extraction.</small></span></label>{error && <InlineNotice tone="warning" title="Extraction failed">{error} Your image has not been saved as a workout.</InlineNotice>}<FormActions><Button disabled={!file || busy} onClick={() => void extract()}>{busy ? 'Extracting…' : 'Extract fields'}</Button></FormActions></div>
}

function TextImport({ onSaved, onManual }: { onSaved: () => void; onManual: () => void }): React.JSX.Element {
  const { capabilities } = useCapabilities(); const [text, setText] = useState(''); const [result, setResult] = useState<WorkoutExtraction | null>(null); const [busy, setBusy] = useState(false); const [error, setError] = useState<string | null>(null)
  const extract = async () => { setBusy(true); setError(null); try { setResult(await api.extractWorkoutText(text)) } catch (reason) { setError(reason instanceof ApiError ? reason.message : 'Text extraction failed.') } finally { setBusy(false) } }
  if (!capabilities.text_extraction) return <div className="degraded-flow"><InlineNotice tone="warning" title="Natural-language extraction unavailable">{capabilities.reason ?? 'AI is not configured.'} Your core logger is still available.</InlineNotice><Button icon="edit" onClick={onManual}>Use manual workout form</Button></div>
  if (result) return <ExtractionPreview result={result} onBack={() => setResult(null)} onSaved={onSaved} />
  return <div className="import-flow"><TextAreaField label="Describe the session" rows={7} value={text} onChange={(event) => setText(event.target.value)} placeholder="今天爬了两个小时，主要是 limit bouldering。整体 RPE 8。\n\nor\n\n10 km easy, 52 min, avg HR 146, RPE 3." hint="Type or dictate in Chinese, English, or mixed training vocabulary." /><QuickTextVoiceRecorder disabled={!capabilities.transcription} onTranscript={(transcript) => setText((current) => current.trim() ? `${current.trim()}\n${transcript}` : transcript)} />{error && <InlineNotice tone="warning">{error} Your text remains available to edit or copy.</InlineNotice>}<FormActions><Button disabled={!text.trim() || busy} onClick={() => void extract()}>{busy ? 'Structuring…' : 'Create preview'}</Button></FormActions></div>
}

function QuickTextVoiceRecorder({ disabled, onTranscript }: { disabled: boolean; onTranscript: (text: string) => void }): React.JSX.Element {
  const recorderRef = useRef<MediaRecorder | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const [recording, setRecording] = useState(false)
  const [audio, setAudio] = useState<Blob | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const start = async () => {
    setError(null)
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') { setError('Audio recording is not supported in this browser.'); return }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream; chunksRef.current = []
      const recorder = new MediaRecorder(stream)
      recorderRef.current = recorder
      recorder.ondataavailable = (event) => { if (event.data.size) chunksRef.current.push(event.data) }
      recorder.onstop = () => { setAudio(new Blob(chunksRef.current, { type: recorder.mimeType || 'audio/webm' })); stream.getTracks().forEach((track) => track.stop()); streamRef.current = null }
      recorder.start(); setRecording(true)
    } catch { setError('Microphone access was denied or unavailable.') }
  }
  const stop = () => { recorderRef.current?.stop(); recorderRef.current = null; setRecording(false) }
  const remove = () => { if (recording) stop(); setAudio(null); setError(null) }
  const transcribe = async () => {
    if (!audio) return
    setBusy(true); setError(null)
    try { const result = await api.transcribeWorkoutInput(audio); onTranscript(result.transcript); setAudio(null) } catch (reason) { setError(reason instanceof ApiError ? reason.message : 'Unable to transcribe this recording.') } finally { setBusy(false) }
  }
  return <Card className="quick-text-voice" title="Voice input"><p className="muted">Optional. The transcript is inserted above for editing before extraction.</p><div className="button-row">{recording ? <Button variant="danger" onClick={stop}>Stop</Button> : <Button icon="mic" disabled={disabled || busy} onClick={() => void start()}>{audio ? 'Re-record' : 'Record'}</Button>}{audio && <Button disabled={busy} onClick={() => void transcribe()}>{busy ? 'Transcribing…' : 'Insert transcript'}</Button>}{audio && <Button variant="ghost" disabled={busy} onClick={remove}>Delete recording</Button>}</div>{disabled && <InlineNotice title="Voice input unavailable">Configure the backend OpenAI API key to enable transcription.</InlineNotice>}{error && <InlineNotice tone="warning">{error}</InlineNotice>}</Card>
}

const extractionLabels: Record<keyof WorkoutExtraction, string> = { workout_kind: 'Workout kind', activity_type: 'Activity label', session_type: 'Session type', title: 'Title', date: 'Date', distance_km: 'Distance (km)', duration_minutes: 'Duration', rpe: 'RPE (1–10)', average_pace: 'Average pace', average_hr: 'Average HR', max_hr: 'Max HR', elevation_m: 'Elevation (m)', cadence: 'Cadence (spm)', power_w: 'Power (W)', board_name: 'Board', angle: 'Angle (°)', splits: 'Splits', intervals: 'Intervals', notes: 'Notes' }

function missingField<T>(source = 'not detected'): ExtractionField<T | null> { return { value: null, confidence: 'LOW', source } }

function normaliseExtractedSessionType(kind: WorkoutKind | null, value: unknown): string | null {
  const key = String(value ?? '').trim().toLowerCase().replace(/[\s_/-]+/g, ' ')
  if (kind === 'RUNNING') {
    if (/^(easy|easy run|recovery|recovery run|z2|zone 2|aerobic run)$/.test(key)) return 'EASY'
    if (/^(long|long run|lr|long aerobic run)$/.test(key)) return 'LONG_RUN'
    if (/^(race|time trial|5k race|10k race|half marathon|marathon|比赛|比賽|测试赛|測試賽)$/.test(key)) return 'RACE'
    if (/threshold|tempo|interval|vo2|fartlek|hill|speed|pace|quality|强度课|強度課|间歇|間歇|阈值|閾值|节奏跑|節奏跑/.test(key)) return 'QUALITY'
    return runningTypes.includes(String(value ?? '') as (typeof runningTypes)[number]) ? String(value) : null
  }
  if (kind === 'CLIMBING') {
    if (/board|tension|tb2|kilter|moonboard/.test(key)) return 'BOARD'
    if (/sport|lead|top rope/.test(key)) return 'SPORT_CLIMBING'
    if (/boulder|technique|volume|power|outdoor/.test(key)) return 'BOULDERING'
    return climbingTypes.includes(String(value ?? '') as (typeof climbingTypes)[number]) ? String(value) : null
  }
  return String(value ?? '').trim() || null
}

function normaliseExtraction(result: WorkoutExtraction): WorkoutExtraction {
  const workoutKind = resolveWorkoutKind(result.workout_kind?.value, result.activity_type?.value, result.session_type?.value)
  const rawType = result.session_type ?? missingField<string>()
  const normalisedType = normaliseExtractedSessionType(workoutKind, rawType.value)
  return {
    ...result,
    workout_kind: result.workout_kind ?? missingField<WorkoutKind>(),
    session_type: { ...rawType, value: normalisedType, source: normalisedType && normalisedType !== rawType.value ? `${rawType.source}; normalised to strict type` : rawType.source },
    title: result.title ?? missingField<string>(),
    rpe: result.rpe ?? missingField<number>(),
    max_hr: result.max_hr ?? missingField<number>(),
    board_name: result.board_name ?? missingField<string>(),
    angle: result.angle ?? missingField<number>(),
    splits: result.splits ?? missingField<string[]>(),
    intervals: result.intervals ?? missingField<string[]>(),
  }
}

function extractionInputProps(key: keyof WorkoutExtraction): { type?: string; min?: number; max?: number; step?: number | string } {
  if (key === 'date') return { type: 'date' }
  if (key === 'duration_minutes') return { type: 'text' }
  if (['distance_km', 'rpe', 'average_hr', 'max_hr', 'elevation_m', 'cadence', 'power_w', 'angle'].includes(key)) {
    return { type: 'number', min: key === 'elevation_m' ? undefined : key === 'rpe' ? 1 : 0, max: key === 'rpe' ? 10 : undefined, step: ['average_hr', 'max_hr'].includes(key) ? 1 : 'any' }
  }
  return { type: 'text' }
}

function isIsoDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false
  const parsed = new Date(`${value}T00:00:00Z`)
  return !Number.isNaN(parsed.valueOf()) && parsed.toISOString().slice(0, 10) === value
}

function isPace(value: string): boolean {
  return /^\d{1,3}:\d{2}(?:\.\d+)?(?:\s*\/km)?$/i.test(value.trim()) || /^\d+(?:\.\d+)?$/.test(value.trim())
}

function resolveWorkoutKind(explicit: unknown, activity: unknown, sessionType: unknown): WorkoutKind | null {
  const exact = String(explicit ?? '').toUpperCase().replaceAll(' ', '_')
  if (['RUNNING', 'CLIMBING', 'STRENGTH', 'CROSSFIT_CONDITIONING', 'MOBILITY_RECOVERY'].includes(exact)) return exact as WorkoutKind
  const text = `${String(activity ?? '')} ${String(sessionType ?? '')}`.toLowerCase()
  if (/boulder|climb|tension|tb2|lead|top rope|board|crag/.test(text)) return 'CLIMBING'
  if (/crossfit|conditioning|wod/.test(text)) return 'CROSSFIT_CONDITIONING'
  if (/strength|weight|deadlift|squat|pull-up|hangboard|bench|press/.test(text)) return 'STRENGTH'
  if (/mobility|recovery|stretch|yoga/.test(text)) return 'MOBILITY_RECOVERY'
  if (/run|jog|easy|threshold|tempo|interval|fartlek|race|marathon/.test(text)) return 'RUNNING'
  return null
}

function ExtractionPreview({ result, onBack, onSaved }: { result: WorkoutExtraction; onBack: () => void; onSaved: () => void }): React.JSX.Element {
  const [fields, setFields] = useState(() => normaliseExtraction(result)); const [busy, setBusy] = useState(false); const [error, setError] = useState<string | null>(null); const [feedbackText, setFeedbackText] = useState(''); const [feedbackSource, setFeedbackSource] = useState<'VOICE' | 'TEXT' | 'NONE'>('NONE')
  const [durationText, setDurationText] = useState(() => typeof result.duration_minutes?.value === 'number' ? formatDuration(result.duration_minutes.value) : '')
  const workoutKind = resolveWorkoutKind(fields.workout_kind?.value, fields.activity_type?.value, fields.session_type?.value)
  const entries = (Object.entries(fields) as [keyof WorkoutExtraction, ExtractionField<unknown>][]).filter(([key]) => !['board_name', 'angle'].includes(key) || (workoutKind === 'CLIMBING' && fields.session_type.value === 'BOARD'))
  const update = (key: keyof WorkoutExtraction, rawValue: string) => setFields((current) => {
    const numeric = ['distance_km', 'duration_minutes', 'rpe', 'average_hr', 'max_hr', 'elevation_m', 'cadence', 'power_w', 'angle'].includes(key)
    const collection = key === 'splits' || key === 'intervals'
    const value = numeric ? rawValue === '' ? null : Number(rawValue) : collection ? rawValue.split(/[;\n]/).map((item) => item.trim()).filter(Boolean) : rawValue || null
    return { ...current, [key]: { ...current[key], value, source: 'user correction' } } as WorkoutExtraction
  })
  const confirm = async () => {
    setError(null)
    const value = <T,>(key: keyof WorkoutExtraction) => (fields[key] as ExtractionField<T> | undefined)?.value
    const workoutKind = resolveWorkoutKind(value('workout_kind'), value('activity_type'), value('session_type'))
    const duration = parseDurationInput(durationText)
    const rpe = value<number>('rpe')
    const sessionDate = value<string>('date') ?? localIsoDate()
    const averageHr = value<number>('average_hr')
    const maxHr = value<number>('max_hr')
    const averagePace = value<string>('average_pace')
    if (!workoutKind) { setError('Choose a valid workout kind before saving.'); return }
    const sessionType = normaliseExtractedSessionType(workoutKind, value<string>('session_type'))
    if (!sessionType) { setError('Choose a valid Session Type from the dropdown before saving.'); return }
    if (!isIsoDate(sessionDate)) { setError('Date must use YYYY-MM-DD format.'); return }
    if (duration == null || duration <= 0) { setError('Duration must use minutes, M:SS, or H:MM:SS.'); return }
    if (rpe != null && (rpe < 1 || rpe > 10)) { setError('When present, RPE must be between 1 and 10.'); return }
    if ((averageHr != null && !Number.isInteger(averageHr)) || (maxHr != null && !Number.isInteger(maxHr))) { setError('Heart-rate values must be whole bpm numbers.'); return }
    if (averagePace && !isPace(averagePace)) { setError('Average pace must use M:SS /km format, for example 5:20 /km.'); return }
    setBusy(true)
    const splits = value<string[]>('splits') ?? []
    const intervals = value<string[]>('intervals') ?? []
    const reviewedFields: WorkoutExtraction = { ...fields, duration_minutes: { ...fields.duration_minutes, value: duration } }
    try { await api.createCompletedSession({ date: sessionDate, workout_kind: workoutKind, session_type: sessionType, title: value<string>('title'), duration_minutes: duration, rpe, distance_km: value<number>('distance_km'), average_pace: averagePace, average_hr: averageHr, max_hr: maxHr, elevation_m: value<number>('elevation_m'), cadence: value<number>('cadence'), power_w: value<number>('power_w'), board_name: workoutKind === 'CLIMBING' && sessionType === 'BOARD' ? value<string>('board_name') : null, angle: workoutKind === 'CLIMBING' && sessionType === 'BOARD' ? value<number>('angle') : null, splits: splits.map((description) => ({ description })), interval_blocks: intervals.map((description) => ({ description })), notes: value<string>('notes'), extraction_reviewed: true, extraction_fields: reviewedFields, subjective_feedback_text: feedbackText.trim() || null, subjective_feedback_source: feedbackText.trim() ? feedbackSource === 'NONE' ? 'TEXT' : feedbackSource : 'NONE' }); onSaved() } catch (reason) { setError(reason instanceof ApiError ? reason.message : 'Unable to confirm workout.') } finally { setBusy(false) }
  }
  return <div className="preview-flow"><InlineNotice title="Review every field">Session Type is always a strict dropdown. Dates use YYYY-MM-DD, duration uses M:SS or H:MM:SS, pace uses M:SS /km, and unknown values remain blank.</InlineNotice><div className="extraction-table"><div className="extraction-row head"><span>Field</span><span>Extracted value</span><span>Confidence</span><span>Source</span></div>{entries.map(([key, field]) => <div className="extraction-row" key={key}><strong>{extractionLabels[key]}</strong>{key === 'workout_kind' ? <select aria-label={extractionLabels[key]} value={extractionDisplayValue(field.value)} onChange={(event) => update(key, event.target.value)}><option value="">Choose activity</option><option value="RUNNING">Running</option><option value="CLIMBING">Climbing</option><option value="STRENGTH">Strength</option><option value="CROSSFIT_CONDITIONING">CrossFit / conditioning</option><option value="MOBILITY_RECOVERY">Mobility / recovery</option></select> : key === 'session_type' && workoutKind === 'RUNNING' ? <select aria-label={extractionLabels[key]} value={extractionDisplayValue(field.value)} onChange={(event) => update(key, event.target.value)}><option value="">Choose running type</option>{runningTypes.map((item) => <option key={item} value={item}>{formatEnum(item)}</option>)}</select> : key === 'session_type' && workoutKind === 'CLIMBING' ? <select aria-label={extractionLabels[key]} value={extractionDisplayValue(field.value)} onChange={(event) => update(key, event.target.value)}><option value="">Choose climbing type</option>{climbingTypes.map((item) => <option key={item} value={item}>{formatEnum(item)}</option>)}</select> : <input aria-label={extractionLabels[key]} {...extractionInputProps(key)} inputMode={key === 'duration_minutes' ? 'numeric' : undefined} value={key === 'duration_minutes' ? durationText : extractionDisplayValue(field.value)} placeholder={key === 'duration_minutes' ? '45:00 or 1:05:01' : 'Not detected'} onChange={(event) => key === 'duration_minutes' ? setDurationText(event.target.value) : update(key, event.target.value)} />}<ConfidencePill value={field.confidence} /><span>{field.source}</span></div>)}</div>{workoutKind === 'RUNNING' && <RunningFeedbackRecorder text={feedbackText} source={feedbackSource} onChange={(text, source) => { setFeedbackText(text); setFeedbackSource(source) }} />}{error && <InlineNotice tone="warning">{error}</InlineNotice>}<FormActions><Button variant="ghost" onClick={onBack}>Back</Button><Button disabled={busy} onClick={() => void confirm()}>{busy ? 'Saving…' : 'Save workout'}</Button></FormActions></div>
}

function RunningFeedbackRecorder({ text, source, onChange }: { text: string; source: 'VOICE' | 'TEXT' | 'NONE'; onChange: (text: string, source: 'VOICE' | 'TEXT' | 'NONE') => void }): React.JSX.Element {
  const { capabilities } = useCapabilities()
  const recorderRef = useRef<MediaRecorder | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const [recording, setRecording] = useState(false)
  const [audio, setAudio] = useState<Blob | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const start = async () => {
    setError(null)
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') { setError('Audio recording is not supported in this browser.'); return }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream; chunksRef.current = []
      const recorder = new MediaRecorder(stream)
      recorderRef.current = recorder
      recorder.ondataavailable = (event) => { if (event.data.size) chunksRef.current.push(event.data) }
      recorder.onstop = () => { setAudio(new Blob(chunksRef.current, { type: recorder.mimeType || 'audio/webm' })); stream.getTracks().forEach((track) => track.stop()); streamRef.current = null }
      recorder.start(); setRecording(true)
    } catch { setError('Microphone access was denied or unavailable.') }
  }
  const stop = () => { recorderRef.current?.stop(); recorderRef.current = null; setRecording(false) }
  const remove = () => { if (recording) stop(); setAudio(null); onChange('', 'NONE'); setError(null) }
  const transcribe = async () => {
    if (!audio) return
    setBusy(true); setError(null)
    try { const result = await api.transcribeRunningFeedback(audio); onChange(result.transcript, 'VOICE'); setAudio(null) } catch (reason) { setError(reason instanceof ApiError ? reason.message : 'Unable to transcribe this recording.') } finally { setBusy(false) }
  }
  return <Card className="running-feedback-card" title="How did this run feel?"><p className="muted">Optional. Record a short note, review the transcript, or type directly. Saving the workout does not require feedback.</p><div className="button-row">{recording ? <Button variant="danger" onClick={stop}>Stop</Button> : <Button icon="mic" disabled={!capabilities.transcription} onClick={() => void start()}>{audio || source === 'VOICE' ? 'Re-record' : 'Record'}</Button>}{audio && <Button disabled={busy} onClick={() => void transcribe()}>{busy ? 'Transcribing…' : 'Transcribe'}</Button>}{(audio || text) && <Button variant="ghost" onClick={remove}>Delete</Button>}</div>{!capabilities.transcription && <InlineNotice title="Voice transcription unavailable">You can still type feedback below or save without it.</InlineNotice>}{error && <InlineNotice tone="warning">{error} Your workout has not been saved yet.</InlineNotice>}<TextAreaField label="Transcript" rows={5} value={text} onChange={(event) => onChange(event.target.value, event.target.value.trim() ? source === 'VOICE' ? 'VOICE' : 'TEXT' : 'NONE')} placeholder="前半程很輕鬆；第六公里後腿有點沉。RPE 大約 7。" hint="Editable text is the source of truth. Raw audio is not retained after successful transcription." /></Card>
}

function extractionDisplayValue(value: unknown): string | number {
  if (Array.isArray(value)) return value.join('; ')
  return typeof value === 'string' || typeof value === 'number' ? value : ''
}

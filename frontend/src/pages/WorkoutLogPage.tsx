import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import { useResource } from '../api/hooks'
import { useCapabilities } from '../app/CapabilityProvider'
import { Icon } from '../components/Icon'
import { Button, Card, ConfidencePill, EmptyState, ErrorPanel, Field, FormActions, InlineNotice, LoadingGrid, Modal, PageHeader, Pill, SelectField, Tabs, TextAreaField, formatEnum } from '../components/ui'
import { formatDate, formatDuration, formatNumber, formatRaceTime, localIsoDate, recordLabel } from '../lib/format'
import type { CompletedSession, ExtractionField, WorkoutExtraction, WorkoutKind } from '../types'

const runningTypes = ['Easy', 'Recovery', 'Long Run', 'Steady', 'Progression', 'Threshold', 'Tempo', 'Cruise Intervals', 'VO2max', 'Intervals', 'Hill Repeats', 'Fartlek', 'Strides', 'HM Pace', 'Marathon Pace', 'Time Trial', 'Race']
const climbingTypes = ['Bouldering', 'Tension Board', 'Sport / Lead', 'Top Rope', 'Technique', 'Limit Bouldering', 'Power', 'Power Endurance', 'Easy Volume', 'Outdoor']
const styleTags = ['crimp', 'sloper', 'pinch', 'compression', 'coordination', 'dyno', 'slab', 'vertical', 'overhang', 'roof', 'technical', 'powerful', 'heel hook', 'toe hook']
const exerciseOptions = ['weighted pull-up', 'pull-up', 'one-arm pull-up progression', 'squat', 'deadlift', 'bench', 'overhead press', 'row', 'hangboard', 'core', 'custom exercise']

type LogMode = 'manual' | 'image' | 'text'

export function WorkoutLogPage(): React.JSX.Element {
  const [params, setParams] = useSearchParams()
  const requested = params.get('action')
  const requestedPlanId = params.get('planned_session_id') ?? ''
  const initialMode: LogMode = requested === 'image' ? 'image' : requested === 'text' ? 'text' : 'manual'
  const [modalOpen, setModalOpen] = useState(Boolean(requested))
  const [mode, setMode] = useState<LogMode>(initialMode)
  const [filter, setFilter] = useState<'ALL' | WorkoutKind>('ALL')
  const [search, setSearch] = useState('')
  const resource = useResource(api.completedSessions, [])
  useEffect(() => {
    if (requested) {
      setMode(requested === 'image' ? 'image' : requested === 'text' ? 'text' : 'manual')
      setModalOpen(true)
    }
  }, [requested])
  const close = () => { setModalOpen(false); setParams({}) }
  const items = useMemo(() => (resource.data?.items ?? []).filter((session) => (filter === 'ALL' || session.workout_kind === filter) && (!search || `${session.title ?? ''} ${session.session_type} ${session.notes ?? ''}`.toLowerCase().includes(search.toLowerCase()))), [filter, resource.data, search])

  return <div className="page workouts-page">
    <PageHeader eyebrow="EVIDENCE" title="Workout Log" description="Fast entry for completed training, with optional detail when it matters." actions={<div className="button-row"><Button variant="ghost" icon="upload" onClick={() => { setMode('image'); setModalOpen(true) }}>Import</Button><Button icon="plus" onClick={() => { setMode('manual'); setModalOpen(true) }}>Log workout</Button></div>} />
    <Card className="filter-bar"><div className="search-field"><Icon name="search" /><input aria-label="Search workouts" placeholder="Search sessions or notes" value={search} onChange={(event) => setSearch(event.target.value)} /></div><SelectField label="Activity filter" className="compact-field" value={filter} onChange={(event) => setFilter(event.target.value as typeof filter)}><option value="ALL">All activities</option><option value="RUNNING">Running</option><option value="CLIMBING">Climbing</option><option value="STRENGTH">Strength</option><option value="CROSSFIT_CONDITIONING">CrossFit / conditioning</option><option value="MOBILITY_RECOVERY">Mobility / recovery</option></SelectField></Card>
    {resource.loading ? <LoadingGrid count={5} /> : resource.error ? <ErrorPanel message={resource.error.message} onRetry={resource.reload} /> : items.length ? <div className="workout-table"><div className="workout-row workout-head"><span>Date</span><span>Activity</span><span>Session</span><span>Duration</span><span>Load</span><span>Details</span></div>{items.map((session) => <WorkoutRow key={session.id} session={session} />)}</div> : <EmptyState icon="workouts" title="No matching workouts" message="A basic session only needs date, duration and RPE. Add detail when it improves the evidence." action={<Button icon="plus" onClick={() => setModalOpen(true)}>Log first workout</Button>} />}
    <Modal open={modalOpen} title="Record completed training" onClose={close} wide>
      <Tabs label="Workout input method" value={mode} onChange={setMode} items={[{ value: 'manual', label: 'Manual' }, { value: 'image', label: 'Screenshot' }, { value: 'text', label: 'Quick text' }]} />
      {mode === 'manual' ? <ManualWorkoutForm initial={{ planned_session_id: requestedPlanId }} onSaved={() => { close(); resource.reload() }} /> : mode === 'image' ? <ScreenshotImport onSaved={() => { close(); resource.reload() }} onManual={() => setMode('manual')} /> : <TextImport onSaved={() => { close(); resource.reload() }} onManual={() => setMode('manual')} />}
    </Modal>
  </div>
}

function WorkoutRow({ session }: { session: CompletedSession }): React.JSX.Element {
  const [open, setOpen] = useState(false)
  const strength = session.strength
  const strengthSets = session.strength_sets ?? strength?.sets ?? []
  const workoutName = session.workout_name ?? strength?.workout_name
  const rounds = session.rounds ?? strength?.rounds
  const resultTime = session.result_time_seconds ?? strength?.result_time_seconds
  return <>
    <article className="workout-row"><span data-label="Date">{formatDate(session.date)}</span><span data-label="Activity"><Pill tone={session.workout_kind === 'RUNNING' ? 'run' : session.workout_kind === 'CLIMBING' ? 'climb' : 'neutral'}>{formatEnum(session.workout_kind)}</Pill>{session.is_demo && <Pill tone="moderate">DEMO</Pill>}</span><span data-label="Session"><strong>{session.title ?? session.session_type}</strong><small>{session.distance_km ? `${formatNumber(session.distance_km, 1)} km` : session.gym_or_crag ?? workoutName ?? ''}</small></span><span data-label="Duration">{formatDuration(session.duration_minutes)}<small>{session.rpe ? `RPE ${session.rpe}` : 'RPE missing'}</small></span><span data-label="Load">{session.srpe_load != null ? `${Math.round(session.srpe_load)} AU` : '—'}</span><span data-label="Details"><Button variant="ghost" aria-label={`View ${session.title ?? session.session_type}`} icon="chevron" onClick={() => setOpen(true)} /></span></article>
    <Modal open={open} title={session.title ?? formatEnum(session.session_type)} onClose={() => setOpen(false)}><div className="stack-form">
      {session.is_demo && <Pill tone="moderate">DEMO DATA</Pill>}
      <div className="form-grid three"><div><span className="field-label">Date</span><strong>{formatDate(session.date)}</strong></div><div><span className="field-label">Duration</span><strong>{formatDuration(session.duration_minutes)}</strong></div><div><span className="field-label">RPE / load</span><strong>{session.rpe ?? 'Missing'}{session.srpe_load != null ? ` · ${Math.round(session.srpe_load)} AU` : ''}</strong></div>{session.distance_km != null && <div><span className="field-label">Distance</span><strong>{formatNumber(session.distance_km, 2)} km</strong></div>}{session.average_hr != null && <div><span className="field-label">Heart rate</span><strong>{session.average_hr} avg{session.max_hr ? ` · ${session.max_hr} max` : ''}</strong></div>}{session.gym_or_crag && <div><span className="field-label">Gym / crag</span><strong>{session.gym_or_crag}</strong></div>}{workoutName && <div><span className="field-label">Workout</span><strong>{workoutName}</strong></div>}{rounds != null && <div><span className="field-label">Rounds</span><strong>{formatNumber(rounds, 1)}</strong></div>}{resultTime != null && <div><span className="field-label">Result time</span><strong>{formatRaceTime(resultTime)}</strong></div>}</div>
      <DetailRecords title="Splits" records={session.splits} />
      <DetailRecords title="Intervals" records={session.interval_blocks} />
      <DetailRecords title="Climbing attempts" records={session.climbing_attempts} />
      <DetailRecords title="Strength sets" records={strengthSets} />
      {session.notes && <Card title="Session notes"><p>{session.notes}</p></Card>}
      {session.ai_analysis && <Card title="AI session analysis"><pre className="detail-json">{recordLabel(session.ai_analysis)}</pre><p className="card-note">Evidence-based enrichment only; deterministic rules remain binding.</p></Card>}
      {!session.ai_analysis && <InlineNotice>AI analysis is not available for this session. Recorded metrics and deterministic load remain complete.</InlineNotice>}
    </div></Modal>
  </>
}

function DetailRecords({ title, records }: { title: string; records?: Array<Record<string, unknown>> }): React.JSX.Element | null {
  if (!records?.length) return null
  return <Card title={title}>{records.map((record, index) => <pre className="detail-json" key={index}>{recordLabel(record)}</pre>)}</Card>
}

interface WorkoutDraft {
  date: string; start_time: string; workout_kind: WorkoutKind; session_type: string; duration_minutes: string; rpe: string; notes: string; planned_session_id: string
  distance_km: string; average_pace: string; average_hr: string; max_hr: string; elevation_m: string; cadence: string; power_w: string
  gym_or_crag: string; hard_attempts: string; max_attempted: string; max_sent: string
  workout_name: string; rounds: string; result_time: string
}

const initialDraft: WorkoutDraft = { date: localIsoDate(), start_time: '', workout_kind: 'RUNNING', session_type: 'Easy', duration_minutes: '45', rpe: '3', notes: '', planned_session_id: '', distance_km: '', average_pace: '', average_hr: '', max_hr: '', elevation_m: '', cadence: '', power_w: '', gym_or_crag: '', hard_attempts: '', max_attempted: '', max_sent: '', workout_name: '', rounds: '', result_time: '' }

function ManualWorkoutForm({ onSaved, initial }: { onSaved: () => void; initial?: Partial<WorkoutDraft> }): React.JSX.Element {
  const [form, setForm] = useState<WorkoutDraft>({ ...initialDraft, ...initial })
  const planned = useResource(api.plannedSessions, [])
  const [intervals, setIntervals] = useState([{ phase: 'Warmup', detail: '15 min easy' }, { phase: 'Main', detail: '6 × 1 km @ target pace · 90 sec jog' }, { phase: 'Cooldown', detail: '10 min easy' }])
  const [splits, setSplits] = useState<{ distance: string; time: string; hr: string }[]>([])
  const [problems, setProblems] = useState<{ problem: string; grade: string; attempts: string; outcome: string; styles: string[] }[]>([])
  const [exercises, setExercises] = useState([{ exercise: 'weighted pull-up', sets: '3', reps: '5', load: '', rpe: '', rir: '' }])
  const [advanced, setAdvanced] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const typeOptions = form.workout_kind === 'RUNNING' ? runningTypes : form.workout_kind === 'CLIMBING' ? climbingTypes : form.workout_kind === 'STRENGTH' ? ['Strength'] : form.workout_kind === 'CROSSFIT_CONDITIONING' ? ['CrossFit / Conditioning'] : ['Mobility / Recovery']
  const set = (key: keyof WorkoutDraft, value: string) => setForm((current) => ({ ...current, [key]: value }))
  const changeKind = (kind: WorkoutKind) => setForm((current) => ({ ...current, workout_kind: kind, session_type: kind === 'RUNNING' ? 'Easy' : kind === 'CLIMBING' ? 'Bouldering' : kind === 'STRENGTH' ? 'Strength' : kind === 'CROSSFIT_CONDITIONING' ? 'CrossFit / Conditioning' : 'Mobility / Recovery' }))
  const submit = async (event: FormEvent) => {
    event.preventDefault(); setError(null)
    const duration = Number(form.duration_minutes); const rpe = form.rpe === '' ? null : Number(form.rpe)
    if (!duration || duration < 1) { setError('Duration must be at least one minute.'); return }
    if (rpe != null && (!Number.isFinite(rpe) || rpe < 1 || rpe > 10)) { setError('When entered, RPE must be between 1 and 10.'); return }
    setBusy(true)
    const numericOrNull = (value: string) => value === '' ? null : Number(value)
    const payload = {
      date: form.date, start_time: form.start_time || null, workout_kind: form.workout_kind, session_type: form.session_type, duration_minutes: duration, rpe, notes: form.notes || null, planned_session_id: form.planned_session_id || null,
      distance_km: numericOrNull(form.distance_km), average_pace: form.average_pace || null, average_hr: numericOrNull(form.average_hr), max_hr: numericOrNull(form.max_hr), elevation_m: numericOrNull(form.elevation_m), cadence: numericOrNull(form.cadence), power_w: numericOrNull(form.power_w),
      gym_or_crag: form.gym_or_crag || null, hard_attempts: numericOrNull(form.hard_attempts), max_attempted: form.max_attempted || null, max_sent: form.max_sent || null,
      workout_name: form.workout_name || null, rounds: numericOrNull(form.rounds), result_time: form.result_time || null,
      interval_blocks: form.workout_kind === 'RUNNING' ? intervals : [], splits: form.workout_kind === 'RUNNING' ? splits : [], climbing_attempts: form.workout_kind === 'CLIMBING' ? problems : [], strength_sets: ['STRENGTH', 'CROSSFIT_CONDITIONING'].includes(form.workout_kind) ? exercises : [],
    }
    try { await api.createCompletedSession(payload); onSaved() }
    catch (reason) { setError(reason instanceof ApiError ? reason.message : 'Unable to save workout.') }
    finally { setBusy(false) }
  }
  return <form className="stack-form workout-form" onSubmit={(event) => void submit(event)}>
    <InlineNotice>Required for load: date, duration and RPE. More detail is optional.</InlineNotice>
    <div className="form-grid three">
      <SelectField label="Activity" value={form.workout_kind} onChange={(event) => changeKind(event.target.value as WorkoutKind)}><option value="RUNNING">Running</option><option value="CLIMBING">Climbing</option><option value="STRENGTH">Strength</option><option value="CROSSFIT_CONDITIONING">CrossFit / conditioning</option><option value="MOBILITY_RECOVERY">Mobility / recovery</option></SelectField>
      <SelectField label="Session type" value={form.session_type} onChange={(event) => set('session_type', event.target.value)}>{typeOptions.map((item) => <option key={item}>{item}</option>)}</SelectField>
      <Field label="Date" required type="date" value={form.date} onChange={(event) => set('date', event.target.value)} />
      <Field label="Start time" type="time" value={form.start_time} onChange={(event) => set('start_time', event.target.value)} />
      <Field label="Duration (minutes)" required type="number" min="1" value={form.duration_minutes} onChange={(event) => set('duration_minutes', event.target.value)} />
      <Field label="RPE (1–10) · optional" type="number" min="1" max="10" value={form.rpe} onChange={(event) => set('rpe', event.target.value)} hint={form.duration_minutes && form.rpe ? `Preview: ${Number(form.duration_minutes) * Number(form.rpe)} AU` : 'Load remains unavailable until RPE is recorded.'} />
      <SelectField label="Linked planned session" value={form.planned_session_id} onChange={(event) => set('planned_session_id', event.target.value)} hint="Links plan and actual without deleting either record."><option value="">Extra / unplanned workout</option>{form.planned_session_id && !planned.data?.items.some((session) => String(session.id) === form.planned_session_id) && <option value={form.planned_session_id}>Planned session #{form.planned_session_id}</option>}{planned.data?.items.map((session) => <option key={session.id} value={session.id}>{session.date} · {session.title}</option>)}</SelectField>
    </div>
    {form.workout_kind === 'RUNNING' && <RunningFields form={form} set={set} advanced={advanced} intervals={intervals} setIntervals={setIntervals} splits={splits} setSplits={setSplits} />}
    {form.workout_kind === 'CLIMBING' && <ClimbingFields form={form} set={set} advanced={advanced} problems={problems} setProblems={setProblems} />}
    {form.workout_kind === 'CROSSFIT_CONDITIONING' && <div className="form-grid three"><Field label="Workout name" value={form.workout_name} onChange={(event) => set('workout_name', event.target.value)} /><Field label="Rounds" type="number" min="0" value={form.rounds} onChange={(event) => set('rounds', event.target.value)} /><Field label="Result / time" value={form.result_time} onChange={(event) => set('result_time', event.target.value)} /></div>}
    {(form.workout_kind === 'STRENGTH' || form.workout_kind === 'CROSSFIT_CONDITIONING') && <StrengthFields exercises={exercises} setExercises={setExercises} />}
    {(form.workout_kind === 'RUNNING' || form.workout_kind === 'CLIMBING') && <Button type="button" variant="ghost" icon={advanced ? 'chevron' : 'plus'} onClick={() => setAdvanced((value) => !value)}>{advanced ? 'Hide optional detail' : 'Add splits / attempts / metrics'}</Button>}
    <TextAreaField label="Notes" rows={4} value={form.notes} onChange={(event) => set('notes', event.target.value)} placeholder="Execution, feel, conditions, pain-free observations…" />
    {error && <InlineNotice tone="warning">{error}</InlineNotice>}
    <FormActions><Button type="submit" disabled={busy}>{busy ? 'Saving and recalculating…' : 'Save workout'}</Button></FormActions>
  </form>
}

function RunningFields({ form, set, advanced, intervals, setIntervals, splits, setSplits }: { form: WorkoutDraft; set: (key: keyof WorkoutDraft, value: string) => void; advanced: boolean; intervals: { phase: string; detail: string }[]; setIntervals: React.Dispatch<React.SetStateAction<{ phase: string; detail: string }[]>>; splits: { distance: string; time: string; hr: string }[]; setSplits: React.Dispatch<React.SetStateAction<{ distance: string; time: string; hr: string }[]>> }): React.JSX.Element {
  const structured = ['Threshold', 'Cruise Intervals', 'VO2max', 'Intervals', 'Hill Repeats', 'HM Pace', 'Marathon Pace'].includes(form.session_type)
  return <><div className="form-grid four"><Field label="Distance (km)" type="number" min="0" step="0.01" value={form.distance_km} onChange={(event) => set('distance_km', event.target.value)} /><Field label="Average pace" placeholder="5:12 /km" value={form.average_pace} onChange={(event) => set('average_pace', event.target.value)} /><Field label="Average HR" type="number" min="0" value={form.average_hr} onChange={(event) => set('average_hr', event.target.value)} /><Field label="Max HR" type="number" min="0" value={form.max_hr} onChange={(event) => set('max_hr', event.target.value)} /></div>{advanced && <div className="form-grid three"><Field label="Elevation (m)" type="number" value={form.elevation_m} onChange={(event) => set('elevation_m', event.target.value)} /><Field label="Cadence" type="number" value={form.cadence} onChange={(event) => set('cadence', event.target.value)} /><Field label="Power (W)" type="number" value={form.power_w} onChange={(event) => set('power_w', event.target.value)} /></div>}{structured && <div className="subform"><div className="subform-header"><div><strong>Structured blocks</strong><span>Warm-up, main work and cooldown</span></div><Button type="button" variant="ghost" icon="plus" onClick={() => setIntervals((current) => [...current, { phase: 'Main', detail: '' }])}>Block</Button></div>{intervals.map((block, index) => <div className="inline-editor" key={`${block.phase}-${index}`}><select aria-label={`Block ${index + 1} phase`} value={block.phase} onChange={(event) => setIntervals((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, phase: event.target.value } : item))}><option>Warmup</option><option>Main</option><option>Cooldown</option></select><input aria-label={`Block ${index + 1} detail`} value={block.detail} onChange={(event) => setIntervals((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, detail: event.target.value } : item))} /><Button type="button" variant="ghost" icon="trash" aria-label="Remove block" onClick={() => setIntervals((current) => current.filter((_, itemIndex) => itemIndex !== index))} /></div>)}</div>}{advanced && <div className="subform"><div className="subform-header"><div><strong>Splits</strong><span>Optional lap evidence</span></div><Button type="button" variant="ghost" icon="plus" onClick={() => setSplits((current) => [...current, { distance: '1', time: '', hr: '' }])}>Split</Button></div>{splits.map((split, index) => <div className="inline-editor four" key={index}><input aria-label={`Split ${index + 1} distance`} placeholder="km" value={split.distance} onChange={(event) => setSplits((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, distance: event.target.value } : item))} /><input aria-label={`Split ${index + 1} time`} placeholder="time" value={split.time} onChange={(event) => setSplits((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, time: event.target.value } : item))} /><input aria-label={`Split ${index + 1} HR`} placeholder="HR" value={split.hr} onChange={(event) => setSplits((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, hr: event.target.value } : item))} /><Button type="button" variant="ghost" icon="trash" aria-label="Remove split" onClick={() => setSplits((current) => current.filter((_, itemIndex) => itemIndex !== index))} /></div>)}</div>}</>
}

function ClimbingFields({ form, set, advanced, problems, setProblems }: { form: WorkoutDraft; set: (key: keyof WorkoutDraft, value: string) => void; advanced: boolean; problems: { problem: string; grade: string; attempts: string; outcome: string; styles: string[] }[]; setProblems: React.Dispatch<React.SetStateAction<{ problem: string; grade: string; attempts: string; outcome: string; styles: string[] }[]>> }): React.JSX.Element {
  return <><div className="form-grid four"><Field label="Gym / crag" value={form.gym_or_crag} onChange={(event) => set('gym_or_crag', event.target.value)} /><Field label="Hard attempts" type="number" min="0" value={form.hard_attempts} onChange={(event) => set('hard_attempts', event.target.value)} /><Field label="Max attempted grade / colour" value={form.max_attempted} onChange={(event) => set('max_attempted', event.target.value)} /><Field label="Max sent grade / colour" value={form.max_sent} onChange={(event) => set('max_sent', event.target.value)} /></div>{advanced && <div className="subform"><div className="subform-header"><div><strong>Problem details</strong><span>Optional — quick session logging remains valid</span></div><Button type="button" variant="ghost" icon="plus" onClick={() => setProblems((current) => [...current, { problem: '', grade: '', attempts: '1', outcome: 'send', styles: [] }])}>Problem</Button></div>{problems.map((problem, index) => <div className="problem-editor" key={index}><div className="inline-editor four"><input aria-label={`Problem ${index + 1}`} placeholder="problem / colour" value={problem.problem} onChange={(event) => setProblems((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, problem: event.target.value } : item))} /><input aria-label={`Problem ${index + 1} grade`} placeholder="grade" value={problem.grade} onChange={(event) => setProblems((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, grade: event.target.value } : item))} /><input aria-label={`Problem ${index + 1} attempts`} type="number" min="1" value={problem.attempts} onChange={(event) => setProblems((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, attempts: event.target.value } : item))} /><select aria-label={`Problem ${index + 1} result`} value={problem.outcome} onChange={(event) => setProblems((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, outcome: event.target.value } : item))}><option value="send">Send</option><option value="flash">Flash</option><option value="repeat">Repeat</option><option value="project">Project</option></select></div><div className="tag-picker">{styleTags.map((tag) => <button className={problem.styles.includes(tag) ? 'selected' : ''} type="button" key={tag} onClick={() => setProblems((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, styles: item.styles.includes(tag) ? item.styles.filter((value) => value !== tag) : [...item.styles, tag] } : item))}>{tag}</button>)}</div></div>)}</div>}</>
}

function StrengthFields({ exercises, setExercises }: { exercises: { exercise: string; sets: string; reps: string; load: string; rpe: string; rir: string }[]; setExercises: React.Dispatch<React.SetStateAction<{ exercise: string; sets: string; reps: string; load: string; rpe: string; rir: string }[]>> }): React.JSX.Element {
  const update = (index: number, key: keyof (typeof exercises)[number], value: string) => setExercises((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, [key]: value } : item))
  return <div className="subform"><div className="subform-header"><div><strong>Exercise sets</strong><span>Used only to map supporting fatigue</span></div><Button type="button" variant="ghost" icon="plus" onClick={() => setExercises((current) => [...current, { exercise: 'custom exercise', sets: '', reps: '', load: '', rpe: '', rir: '' }])}>Exercise</Button></div>{exercises.map((item, index) => <div className="strength-row" key={index}><select aria-label={`Exercise ${index + 1}`} value={item.exercise} onChange={(event) => update(index, 'exercise', event.target.value)}>{exerciseOptions.map((exercise) => <option key={exercise}>{exercise}</option>)}</select><input aria-label="Sets" placeholder="sets" type="number" min="0" value={item.sets} onChange={(event) => update(index, 'sets', event.target.value)} /><input aria-label="Reps" placeholder="reps" type="number" min="0" value={item.reps} onChange={(event) => update(index, 'reps', event.target.value)} /><input aria-label="Load" placeholder="kg" type="number" min="0" value={item.load} onChange={(event) => update(index, 'load', event.target.value)} /><input aria-label="RPE" placeholder="RPE" type="number" min="1" max="10" value={item.rpe} onChange={(event) => update(index, 'rpe', event.target.value)} /><input aria-label="RIR" placeholder="RIR" type="number" min="0" value={item.rir} onChange={(event) => update(index, 'rir', event.target.value)} /></div>)}</div>
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
  return <div className="import-flow"><TextAreaField label="Describe the session" rows={7} value={text} onChange={(event) => setText(event.target.value)} placeholder="今天爬了两个小时，主要是 limit bouldering。整体 RPE 8。\n\nor\n\n10 km easy, 52 min, avg HR 146, RPE 3." hint="Chinese, English and mixed terminology are supported." />{error && <InlineNotice tone="warning">{error} Your text remains available to edit or copy.</InlineNotice>}<FormActions><Button disabled={!text.trim() || busy} onClick={() => void extract()}>{busy ? 'Structuring…' : 'Create preview'}</Button></FormActions></div>
}

const extractionLabels: Record<keyof WorkoutExtraction, string> = { workout_kind: 'Workout kind', activity_type: 'Activity label', session_type: 'Session type', date: 'Date', distance_km: 'Distance (km)', duration_minutes: 'Duration (minutes)', rpe: 'RPE (1–10)', average_pace: 'Average pace', average_hr: 'Average HR', max_hr: 'Max HR', elevation_m: 'Elevation (m)', cadence: 'Cadence', power_w: 'Power (W)', splits: 'Splits', intervals: 'Intervals', notes: 'Notes' }

function missingField<T>(source = 'not detected'): ExtractionField<T | null> { return { value: null, confidence: 'LOW', source } }

function normaliseExtraction(result: WorkoutExtraction): WorkoutExtraction {
  return {
    ...result,
    workout_kind: result.workout_kind ?? missingField<WorkoutKind>(),
    session_type: result.session_type ?? missingField<string>(),
    rpe: result.rpe ?? missingField<number>(),
    max_hr: result.max_hr ?? missingField<number>(),
    splits: result.splits ?? missingField<string[]>(),
    intervals: result.intervals ?? missingField<string[]>(),
  }
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
  const [fields, setFields] = useState(() => normaliseExtraction(result)); const [busy, setBusy] = useState(false); const [error, setError] = useState<string | null>(null)
  const entries = Object.entries(fields) as [keyof WorkoutExtraction, ExtractionField<unknown>][]
  const update = (key: keyof WorkoutExtraction, rawValue: string) => setFields((current) => {
    const numeric = ['distance_km', 'duration_minutes', 'rpe', 'average_hr', 'max_hr', 'elevation_m', 'cadence', 'power_w'].includes(key)
    const collection = key === 'splits' || key === 'intervals'
    const value = numeric ? rawValue === '' ? null : Number(rawValue) : collection ? rawValue.split(/[;\n]/).map((item) => item.trim()).filter(Boolean) : rawValue || null
    return { ...current, [key]: { ...current[key], value, source: 'user correction' } } as WorkoutExtraction
  })
  const confirm = async () => {
    setError(null)
    const value = <T,>(key: keyof WorkoutExtraction) => (fields[key] as ExtractionField<T> | undefined)?.value
    const workoutKind = resolveWorkoutKind(value('workout_kind'), value('activity_type'), value('session_type'))
    const duration = value<number>('duration_minutes')
    const rpe = value<number>('rpe')
    if (!workoutKind) { setError('Choose a valid workout kind before saving.'); return }
    if (!duration || duration <= 0) { setError('Duration is required before saving an imported workout.'); return }
    if (rpe != null && (rpe < 1 || rpe > 10)) { setError('When present, RPE must be between 1 and 10.'); return }
    setBusy(true)
    const splits = value<string[]>('splits') ?? []
    const intervals = value<string[]>('intervals') ?? []
    try { await api.createCompletedSession({ date: value<string>('date') ?? localIsoDate(), workout_kind: workoutKind, session_type: value<string>('session_type') ?? value<string>('activity_type') ?? 'Imported workout', duration_minutes: duration, rpe, distance_km: value<number>('distance_km'), average_pace: value<string>('average_pace'), average_hr: value<number>('average_hr'), max_hr: value<number>('max_hr'), elevation_m: value<number>('elevation_m'), cadence: value<number>('cadence'), power_w: value<number>('power_w'), splits: splits.map((description) => ({ description })), interval_blocks: intervals.map((description) => ({ description })), notes: value<string>('notes'), extraction_reviewed: true, extraction_fields: fields }); onSaved() } catch (reason) { setError(reason instanceof ApiError ? reason.message : 'Unable to confirm workout.') } finally { setBusy(false) }
  }
  return <div className="preview-flow"><InlineNotice title="Review every field">Unknown values remain null. Correct anything before confirming; separate splits or intervals with semicolons. Nothing has been saved yet.</InlineNotice><div className="extraction-table"><div className="extraction-row head"><span>Field</span><span>Extracted value</span><span>Confidence</span><span>Source</span></div>{entries.map(([key, field]) => <div className="extraction-row" key={key}><strong>{extractionLabels[key]}</strong><input aria-label={extractionLabels[key]} value={extractionDisplayValue(field.value)} placeholder="Not detected" onChange={(event) => update(key, event.target.value)} /><ConfidencePill value={field.confidence} /><span>{field.source}</span></div>)}</div>{error && <InlineNotice tone="warning">{error}</InlineNotice>}<FormActions><Button variant="ghost" onClick={onBack}>Back</Button><Button disabled={busy} onClick={() => void confirm()}>{busy ? 'Saving…' : 'Confirm and save'}</Button></FormActions></div>
}

function extractionDisplayValue(value: unknown): string | number {
  if (Array.isArray(value)) return value.join('; ')
  return typeof value === 'string' || typeof value === 'number' ? value : ''
}

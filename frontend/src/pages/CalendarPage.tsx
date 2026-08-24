import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import { useResource } from '../api/hooks'
import { Icon } from '../components/Icon'
import { SessionCard } from '../components/training'
import { Button, Card, ErrorPanel, Field, FormActions, InlineNotice, LoadingGrid, Modal, PageHeader, Pill, SelectField, TextAreaField, formatEnum } from '../components/ui'
import { addDays, formatDate, formatDuration, formatNumber, localIsoDate, parseDurationInput, startOfWeek, weekDates } from '../lib/format'
import type { CalendarEntry, PlannedSession, WorkoutKind } from '../types'

const sessionOptions: Record<WorkoutKind, string[]> = {
  RUNNING: ['EASY', 'LONG_RUN', 'QUALITY', 'RACE'],
  CLIMBING: ['BOULDERING', 'SPORT_CLIMBING', 'BOARD'],
  STRENGTH: ['Strength', 'Max Hangs', 'Weighted Pull-ups', 'Deadlift'], CROSSFIT_CONDITIONING: ['CrossFit / Conditioning'], MOBILITY_RECOVERY: ['Mobility / Recovery'],
}

const strengthExerciseOptions = ['Max Hangs', 'Weighted Pull-ups', 'Deadlift', 'Squat', 'Bench', 'Overhead Press', 'Row', 'Hangboard', 'Core']
const structuredRunningTypes = new Set(['QUALITY'])

export function CalendarPage(): React.JSX.Element {
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const [anchor, setAnchor] = useState(() => new Date())
  const days = useMemo(() => weekDates(anchor), [anchor])
  const resource = useResource(() => api.calendar(days[0]!, days[6]!), [days.join('|')])
  const [formOpen, setFormOpen] = useState(params.get('action') === 'new')
  const [formDate, setFormDate] = useState(localIsoDate())
  const [selected, setSelected] = useState<CalendarEntry | null>(null)
  const suggestedDate = days.find((day) => day >= localIsoDate()) ?? days[0]!
  useEffect(() => { if (params.get('action') === 'new') { setFormDate(suggestedDate); setFormOpen(true) } }, [params, suggestedDate])
  const closeForm = () => { setFormOpen(false); setParams({}) }
  const openForm = (date: string) => { setFormDate(date); setFormOpen(true) }
  const start = startOfWeek(anchor)
  const end = addDays(start, 6)
  return <div className="page calendar-page">
    <PageHeader eyebrow="PLAN / ACTUAL" title="Calendar" description="A weekly view that preserves what was planned and what actually happened." actions={<Button icon="plus" onClick={() => openForm(suggestedDate)}>Plan session</Button>} />
    <div className="calendar-toolbar">
      <div className="week-controls"><Button variant="ghost" aria-label="Previous week" onClick={() => setAnchor(addDays(anchor, -7))}>←</Button><div><strong>{formatDate(localIsoDate(start), { month: 'long', day: 'numeric' })} — {formatDate(localIsoDate(end), { month: 'long', day: 'numeric', year: 'numeric' })}</strong><button onClick={() => setAnchor(new Date())}>This week</button></div><Button variant="ghost" aria-label="Next week" onClick={() => setAnchor(addDays(anchor, 7))}>→</Button></div>
      <div className="calendar-legend">{['PLANNED', 'COMPLETED', 'MODIFIED', 'SKIPPED', 'MOVED', 'REPLACED', 'REST'].map((status) => <span key={status}><i className={`status-dot status-${status.toLowerCase()}`} />{formatEnum(status)}</span>)}</div>
    </div>
    {resource.error && <ErrorPanel message={resource.error.message} onRetry={resource.reload} />}
    {resource.loading ? <LoadingGrid count={7} /> : <div className="week-grid">{days.map((day) => {
      const entries = resource.data?.items.filter((entry) => entry.date.slice(0, 10) === day) ?? []
      const isToday = day === localIsoDate()
      return <section className={`calendar-day ${isToday ? 'today' : ''}`} key={day}><header><span>{formatDate(day, { weekday: 'short' })}</span><strong>{Number(day.slice(-2))}</strong>{isToday && <Pill tone="info">TODAY</Pill>}</header><div className="day-sessions">{entries.length ? entries.map((entry) => <SessionCard key={entry.id} entry={entry} compact onOpen={setSelected} onComplete={(id) => navigate(`/workouts?action=complete&planned_session_id=${encodeURIComponent(String(id))}`)} />) : <button className="empty-day" onClick={() => openForm(day)}><Icon name="plus" size={15} />Plan or rest</button>}</div></section>
    })}</div>}
    <div className="calendar-note"><Icon name="info" /><span>Moving or replacing a session creates a linked revision. The original plan is retained in history.</span></div>
    <Modal open={formOpen} title="Plan a session" onClose={closeForm} wide><PlannedSessionForm key={formDate} defaultDate={formDate} onSaved={() => { closeForm(); resource.reload() }} /></Modal>
    <Modal open={Boolean(selected)} title="Session Detail" onClose={() => setSelected(null)} wide>{selected && <SessionDetail entry={selected} onChanged={() => { setSelected(null); resource.reload() }} onComplete={(id) => navigate(`/workouts?action=complete&planned_session_id=${encodeURIComponent(String(id))}`)} />}</Modal>
  </div>
}

function PlannedSessionForm({ defaultDate, onSaved }: { defaultDate: string; onSaved: () => void }): React.JSX.Element {
  const [kind, setKind] = useState<WorkoutKind>('RUNNING')
  const [form, setForm] = useState({ plan_type: 'SESSION' as 'SESSION' | 'REST', date: defaultDate, start_time: '', session_type: 'EASY', title: 'Easy Run', description: '', planned_duration_minutes: '45:00', planned_distance_km: '', target_rpe: '3', priority: 'NORMAL', is_locked: false })
  const [strengthExercises, setStrengthExercises] = useState<string[]>([''])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const updateKind = (next: WorkoutKind) => { setKind(next); const sessionType = sessionOptions[next][0] ?? ''; setForm((current) => ({ ...current, session_type: sessionType, title: sessionType })); setStrengthExercises(['']) }
  const updateSessionType = (sessionType: string) => {
    setForm((current) => ({ ...current, session_type: sessionType, title: current.title === current.session_type ? sessionType : current.title }))
    if (kind === 'STRENGTH' && strengthExerciseOptions.includes(sessionType)) setStrengthExercises((current) => [sessionType, ...current.slice(1)])
  }
  const submit = async (event: FormEvent) => {
    event.preventDefault(); setError(null)
    const resting = form.plan_type === 'REST'
    const plannedDuration = resting ? null : parseDurationInput(form.planned_duration_minutes)
    if (!resting && (plannedDuration == null || plannedDuration <= 0)) { setError('Duration must use minutes, M:SS, or H:MM:SS.'); return }
    setBusy(true)
    try {
      const structuredBlocks = !resting && kind === 'STRENGTH'
        ? strengthExercises.filter(Boolean).map((exercise) => ({ exercise }))
        : !resting && kind === 'RUNNING' && structuredRunningTypes.has(form.session_type) && form.description.trim()
          ? [{ phase: 'Main', description: form.description.trim() }]
          : []
      await api.createPlannedSession({ date: form.date, start_time: resting ? null : form.start_time || null, workout_kind: resting ? 'MOBILITY_RECOVERY' : kind, session_type: resting ? 'Rest' : form.session_type, title: resting ? 'Rest' : form.title, description: form.description || null, planned_duration_minutes: plannedDuration, planned_distance_km: resting ? null : Number(form.planned_distance_km) || null, target_rpe: resting ? null : Number(form.target_rpe) || null, priority: form.priority as PlannedSession['priority'], status: resting ? 'REST' : 'PLANNED', structured_blocks: structuredBlocks, is_locked: form.is_locked })
      onSaved()
    } catch (reason) { setError(reason instanceof ApiError ? reason.message : 'Unable to create the session.') }
    finally { setBusy(false) }
  }
  return <form className="stack-form" onSubmit={(event) => void submit(event)}>
    <div className="form-grid three">
      <SelectField label="Plan type" value={form.plan_type} onChange={(event) => setForm((current) => ({ ...current, plan_type: event.target.value as 'SESSION' | 'REST' }))}><option value="SESSION">Training session</option><option value="REST">Rest day</option></SelectField>
      <SelectField label="Activity" disabled={form.plan_type === 'REST'} value={kind} onChange={(event) => updateKind(event.target.value as WorkoutKind)}>{Object.keys(sessionOptions).map((value) => <option key={value} value={value}>{formatEnum(value)}</option>)}</SelectField>
      <SelectField label="Session type" disabled={form.plan_type === 'REST'} value={form.session_type} onChange={(event) => updateSessionType(event.target.value)}>{sessionOptions[kind].map((value) => <option key={value} value={value}>{formatEnum(value)}</option>)}</SelectField>
      <Field label="Title" required={form.plan_type !== 'REST'} disabled={form.plan_type === 'REST'} value={form.plan_type === 'REST' ? 'Rest' : form.title} onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))} />
      <Field label="Date" type="date" required value={form.date} onChange={(event) => setForm((current) => ({ ...current, date: event.target.value }))} />
      <Field label="Start time" type="time" disabled={form.plan_type === 'REST'} value={form.start_time} onChange={(event) => setForm((current) => ({ ...current, start_time: event.target.value }))} />
      <SelectField label="Priority" disabled={form.plan_type === 'REST'} value={form.priority} onChange={(event) => setForm((current) => ({ ...current, priority: event.target.value }))}><option>LOW</option><option>NORMAL</option><option>HIGH</option></SelectField>
      <Field label="Duration" inputMode="numeric" placeholder="45:00 or 1:05:01" disabled={form.plan_type === 'REST'} value={form.planned_duration_minutes} onChange={(event) => setForm((current) => ({ ...current, planned_duration_minutes: event.target.value }))} hint="M:SS or H:MM:SS; plain numbers mean minutes." />
      <Field label="Distance (km)" type="number" min="0" step="0.1" disabled={form.plan_type === 'REST' || kind !== 'RUNNING'} value={form.planned_distance_km} onChange={(event) => setForm((current) => ({ ...current, planned_distance_km: event.target.value }))} />
      <Field label="Target RPE" type="number" min="1" max="10" disabled={form.plan_type === 'REST'} value={form.target_rpe} onChange={(event) => setForm((current) => ({ ...current, target_rpe: event.target.value }))} />
    </div>
    {form.plan_type !== 'REST' && kind === 'STRENGTH' && <div className="subform"><div className="subform-header"><div><strong>Planned exercises</strong><span>Stored as factual supporting-work details.</span></div><Button type="button" variant="ghost" icon="plus" onClick={() => setStrengthExercises((current) => [...current, ''])}>Exercise</Button></div>{strengthExercises.map((exercise, index) => <div className="inline-editor" key={index}><select aria-label={`Planned exercise ${index + 1}`} value={exercise} onChange={(event) => setStrengthExercises((current) => current.map((item, itemIndex) => itemIndex === index ? event.target.value : item))}><option value="">Not specified</option>{strengthExerciseOptions.map((option) => <option key={option}>{option}</option>)}</select><span className="field-hint">Kept with the planned prescription.</span><Button type="button" variant="ghost" icon="trash" aria-label={`Remove planned exercise ${index + 1}`} onClick={() => setStrengthExercises((current) => current.length === 1 ? [''] : current.filter((_, itemIndex) => itemIndex !== index))} /></div>)}</div>}
    <TextAreaField label="Session structure / notes" rows={4} value={form.description} onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))} placeholder="4 × 8 min @ 4:15/km, HR <= 172, 2 min recovery" />
    <label className="switch-row"><input type="checkbox" checked={form.is_locked} onChange={(event) => setForm((current) => ({ ...current, is_locked: event.target.checked }))} /><span><strong>Lock this session</strong><small>Marks this session as fixed when reviewing or importing a plan.</small></span></label>
    {error && <InlineNotice tone="warning">{error}</InlineNotice>}
    <FormActions><Button type="submit" disabled={busy}>{busy ? 'Saving…' : 'Add to plan'}</Button></FormActions>
  </form>
}

function SessionDetail({ entry, onChanged, onComplete }: { entry: CalendarEntry; onChanged: () => void; onComplete: (id: string | number) => void }): React.JSX.Element {
  const plan = entry.planned
  const actual = entry.completed
  const [editing, setEditing] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const remove = async () => {
    if (!plan) return
    setBusy(true); setError(null)
    try { await api.deletePlannedSession(plan.id); onChanged() }
    catch (reason) { setError(reason instanceof ApiError ? reason.message : 'Unable to remove this session.') }
    finally { setBusy(false) }
  }
  if (editing && plan) return <PlannedSessionEditForm plan={plan} onCancel={() => setEditing(false)} onSaved={onChanged} />
  const session = actual ?? plan
  if (!session) return <InlineNotice>Rest day</InlineNotice>
  return <div className="session-detail stack-form">
    <div className="session-detail-heading"><div><Pill tone={session.workout_kind === 'RUNNING' ? 'run' : session.workout_kind === 'CLIMBING' ? 'climb' : 'neutral'}>{formatEnum(session.session_type)}</Pill><h2>{session.title ?? formatEnum(session.session_type)}</h2><p>{formatDate(session.date, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}</p></div><Pill>{entry.status}</Pill></div>
    <div className="form-grid four"><div><span className="field-label">Distance</span><strong>{(actual?.distance_km ?? plan?.planned_distance_km) != null ? `${formatNumber(actual?.distance_km ?? plan?.planned_distance_km, 1)} km` : 'N/A'}</strong></div><div><span className="field-label">Duration</span><strong>{formatDuration(actual?.duration_minutes ?? plan?.planned_duration_minutes)}</strong></div><div><span className="field-label">Target RPE</span><strong>{plan?.target_rpe ?? actual?.rpe ?? 'N/A'}</strong></div><div><span className="field-label">Start</span><strong>{session.start_time?.slice(0, 5) ?? 'Any time'}</strong></div></div>
    {plan?.structured_blocks?.length ? <div className="prescription"><h3>Full prescription</h3>{plan.structured_blocks.map((block, index) => <PrescriptionBlock block={block} key={index} />)}</div> : plan?.description ? <Card title="Workout"><p className="pre-wrap">{plan.description}</p></Card> : <InlineNotice>No structured workout prescription was provided.</InlineNotice>}
    {plan?.description && plan.structured_blocks?.length ? <Card title="Notes"><p className="pre-wrap">{plan.description}</p></Card> : null}
    {actual && <InlineNotice tone="success">This planned session has a linked completed workout. Open Workout Log for the recorded evidence.</InlineNotice>}
    {error && <InlineNotice tone="warning">{error}</InlineNotice>}
    {plan && !actual && entry.status !== 'REST' && <FormActions><Button variant="danger" disabled={busy} onClick={() => void remove()}>{busy ? 'Removing…' : 'Delete'}</Button><Button variant="ghost" onClick={() => setEditing(true)}>Edit</Button><Button onClick={() => onComplete(plan.id)}>Mark Complete</Button></FormActions>}
    {plan && !actual && entry.status === 'REST' && <FormActions><Button variant="danger" disabled={busy} onClick={() => void remove()}>Delete</Button><Button variant="ghost" onClick={() => setEditing(true)}>Edit</Button></FormActions>}
    {plan && !actual && <p className="card-note">Delete removes the session from the active Calendar while preserving its revision history.</p>}
  </div>
}

function PrescriptionBlock({ block }: { block: Record<string, unknown> }): React.JSX.Element {
  const title = formatEnum(String(block.label ?? block.segment_kind ?? 'Segment'))
  const raw = String(block.raw_text ?? block.notes ?? '')
  const sets = typeof block.sets === 'number' ? block.sets : 1
  const reps = typeof block.repetitions === 'number' ? block.repetitions : null
  const distance = typeof block.distance_km === 'number' ? `${block.distance_km} km` : null
  const paceMin = typeof block.target_pace_min === 'string' ? block.target_pace_min : null
  const paceMax = typeof block.target_pace_max === 'string' ? block.target_pace_max : null
  const recovery = typeof block.recovery_duration_seconds === 'number' ? block.recovery_duration_seconds : null
  const hrMin = typeof block.target_hr_min === 'number' ? block.target_hr_min : null
  const hrMax = typeof block.target_hr_max === 'number' ? block.target_hr_max : null
  return <Card title={title}><p>{raw || 'N/A'}</p>{reps && <p><strong>Main set:</strong> {sets > 1 ? `${sets} × (` : ''}{reps} × {distance ?? 'repetition'}{sets > 1 ? ')' : ''}</p>}{paceMin && <p><strong>Target pace:</strong> {paceMin}{paceMax && paceMax !== paceMin ? `–${paceMax}` : ''}/km</p>}{(hrMin != null || hrMax != null) && <p><strong>Target HR:</strong> {hrMin != null && hrMax != null ? `${hrMin}–${hrMax} bpm` : `≤ ${hrMax ?? hrMin} bpm`}</p>}{recovery != null && <p><strong>Recovery:</strong> {recovery >= 60 ? `${recovery / 60} min` : `${recovery} sec`} easy between {block.recovery_scope === 'SET' ? 'sets' : 'repetitions'}</p>}{sets > 1 && reps ? <ol>{Array.from({ length: sets }, (_, index) => <li key={index}>Set {index + 1}: {reps} × {distance ?? 'repetition'}{paceMin ? ` @ ${paceMin}/km` : ''}</li>)}</ol> : null}</Card>
}

function PlannedSessionEditForm({ plan, onCancel, onSaved }: { plan: PlannedSession; onCancel: () => void; onSaved: () => void }): React.JSX.Element {
  const [form, setForm] = useState({ date: plan.date, session_type: plan.session_type, title: plan.title, description: plan.description ?? '', duration: plan.planned_duration_minutes != null ? formatDuration(plan.planned_duration_minutes) : '', distance: plan.planned_distance_km?.toString() ?? '', rpe: plan.target_rpe?.toString() ?? '', blocks: JSON.stringify(plan.structured_blocks ?? [], null, 2) })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const options = sessionOptions[plan.workout_kind]
  const submit = async (event: FormEvent) => {
    event.preventDefault(); setError(null)
    const duration = form.duration ? parseDurationInput(form.duration) : null
    let blocks: Array<Record<string, unknown>>
    try { const parsed: unknown = JSON.parse(form.blocks); if (!Array.isArray(parsed)) throw new Error(); blocks = parsed as Array<Record<string, unknown>> } catch { setError('Workout structure must be a JSON array. Human-readable details remain in Description.'); return }
    setBusy(true)
    try { await api.updatePlannedSession(plan.id, { date: form.date, workout_kind: plan.workout_kind, session_type: form.session_type, title: form.title, description: form.description, planned_duration_minutes: duration, planned_distance_km: form.distance ? Number(form.distance) : null, target_rpe: form.rpe ? Number(form.rpe) : null, structured_blocks: blocks }); onSaved() }
    catch (reason) { setError(reason instanceof ApiError ? reason.message : 'Unable to edit this session.') }
    finally { setBusy(false) }
  }
  return <form className="stack-form" onSubmit={(event) => void submit(event)}><div className="form-grid three"><Field label="Date" type="date" value={form.date} onChange={(event) => setForm((current) => ({ ...current, date: event.target.value }))} /><SelectField label="Type" value={form.session_type} onChange={(event) => setForm((current) => ({ ...current, session_type: event.target.value }))}>{options.map((item) => <option key={item} value={item}>{formatEnum(item)}</option>)}</SelectField><Field label="Title" value={form.title} onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))} /><Field label="Distance (km)" type="number" min="0" step="0.1" value={form.distance} onChange={(event) => setForm((current) => ({ ...current, distance: event.target.value }))} /><Field label="Duration" value={form.duration} onChange={(event) => setForm((current) => ({ ...current, duration: event.target.value }))} /><Field label="Target RPE" type="number" min="1" max="10" value={form.rpe} onChange={(event) => setForm((current) => ({ ...current, rpe: event.target.value }))} /></div><TextAreaField label="Full prescription / notes" rows={7} value={form.description} onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))} /><TextAreaField label="Structured workout blocks" rows={10} value={form.blocks} onChange={(event) => setForm((current) => ({ ...current, blocks: event.target.value }))} hint="Edit structured pace, HR, recovery and segment fields. Revision history is preserved." />{error && <InlineNotice tone="warning">{error}</InlineNotice>}<FormActions><Button type="button" variant="ghost" onClick={onCancel}>Cancel</Button><Button type="submit" disabled={busy}>{busy ? 'Saving…' : 'Save changes'}</Button></FormActions></form>
}

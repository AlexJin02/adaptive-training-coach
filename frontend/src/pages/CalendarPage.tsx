import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import { useResource } from '../api/hooks'
import { Icon } from '../components/Icon'
import { SessionCard } from '../components/training'
import { Button, ErrorPanel, Field, FormActions, InlineNotice, LoadingGrid, Modal, PageHeader, Pill, SelectField, TextAreaField, formatEnum } from '../components/ui'
import { addDays, formatDate, localIsoDate, startOfWeek, weekDates } from '../lib/format'
import type { PlannedSession, WorkoutKind } from '../types'

const sessionOptions: Record<WorkoutKind, string[]> = {
  RUNNING: ['Easy', 'Recovery', 'Long Run', 'Steady', 'Progression', 'Threshold', 'Tempo', 'Cruise Intervals', 'VO2max', 'Intervals', 'Hill Repeats', 'Fartlek', 'Strides', 'HM Pace', 'Marathon Pace', 'Time Trial', 'Race'],
  CLIMBING: ['Bouldering', 'Tension Board', 'Sport / Lead', 'Top Rope', 'Technique', 'Limit Bouldering', 'Power', 'Power Endurance', 'Easy Volume', 'Outdoor'],
  STRENGTH: ['Strength', 'Max Hangs', 'Weighted Pull-ups', 'Deadlift'], CROSSFIT_CONDITIONING: ['CrossFit / Conditioning'], MOBILITY_RECOVERY: ['Mobility / Recovery'],
}

const strengthExerciseOptions = ['Max Hangs', 'Weighted Pull-ups', 'Deadlift', 'Squat', 'Bench', 'Overhead Press', 'Row', 'Hangboard', 'Core']
const structuredRunningTypes = new Set(['Threshold', 'Tempo', 'Cruise Intervals', 'VO2max', 'Intervals', 'Hill Repeats', 'HM Pace', 'Marathon Pace'])

export function CalendarPage(): React.JSX.Element {
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const [anchor, setAnchor] = useState(() => new Date())
  const days = useMemo(() => weekDates(anchor), [anchor])
  const resource = useResource(() => api.calendar(days[0]!, days[6]!), [days.join('|')])
  const [formOpen, setFormOpen] = useState(params.get('action') === 'new')
  const [formDate, setFormDate] = useState(localIsoDate())
  const [actionError, setActionError] = useState<string | null>(null)
  const suggestedDate = days.find((day) => day >= localIsoDate()) ?? days[0]!
  useEffect(() => { if (params.get('action') === 'new') { setFormDate(suggestedDate); setFormOpen(true) } }, [params, suggestedDate])
  const closeForm = () => { setFormOpen(false); setParams({}) }
  const openForm = (date: string) => { setFormDate(date); setFormOpen(true) }
  const start = startOfWeek(anchor)
  const end = addDays(start, 6)
  const skipSession = async (id: string | number) => {
    setActionError(null)
    try { await api.skipPlannedSession(id); resource.reload() }
    catch (reason) { setActionError(reason instanceof ApiError ? reason.message : 'Unable to skip the session.') }
  }

  return <div className="page calendar-page">
    <PageHeader eyebrow="PLAN / ACTUAL" title="Calendar" description="A weekly view that preserves what was planned and what actually happened." actions={<Button icon="plus" onClick={() => openForm(suggestedDate)}>Plan session</Button>} />
    <div className="calendar-toolbar">
      <div className="week-controls"><Button variant="ghost" aria-label="Previous week" onClick={() => setAnchor(addDays(anchor, -7))}>←</Button><div><strong>{formatDate(localIsoDate(start), { month: 'long', day: 'numeric' })} — {formatDate(localIsoDate(end), { month: 'long', day: 'numeric', year: 'numeric' })}</strong><button onClick={() => setAnchor(new Date())}>This week</button></div><Button variant="ghost" aria-label="Next week" onClick={() => setAnchor(addDays(anchor, 7))}>→</Button></div>
      <div className="calendar-legend">{['PLANNED', 'COMPLETED', 'MODIFIED', 'SKIPPED', 'MOVED', 'REPLACED', 'REST'].map((status) => <span key={status}><i className={`status-dot status-${status.toLowerCase()}`} />{formatEnum(status)}</span>)}</div>
    </div>
    {actionError && <InlineNotice tone="warning">{actionError}</InlineNotice>}
    {resource.error && <ErrorPanel message={resource.error.message} onRetry={resource.reload} />}
    {resource.loading ? <LoadingGrid count={7} /> : <div className="week-grid">{days.map((day) => {
      const entries = resource.data?.items.filter((entry) => entry.date.slice(0, 10) === day) ?? []
      const isToday = day === localIsoDate()
      return <section className={`calendar-day ${isToday ? 'today' : ''}`} key={day}><header><span>{formatDate(day, { weekday: 'short' })}</span><strong>{Number(day.slice(-2))}</strong>{isToday && <Pill tone="info">TODAY</Pill>}</header><div className="day-sessions">{entries.length ? entries.map((entry) => <SessionCard key={entry.id} entry={entry} compact onComplete={(id) => navigate(`/workouts?action=complete&planned_session_id=${encodeURIComponent(String(id))}`)} onSkip={(id) => void skipSession(id)} />) : <button className="empty-day" onClick={() => openForm(day)}><Icon name="plus" size={15} />Plan or rest</button>}</div></section>
    })}</div>}
    <div className="calendar-note"><Icon name="info" /><span>Moving or replacing a session creates a linked revision. The original plan is retained in history.</span></div>
    <Modal open={formOpen} title="Plan a session" onClose={closeForm} wide><PlannedSessionForm key={formDate} defaultDate={formDate} onSaved={() => { closeForm(); resource.reload() }} /></Modal>
  </div>
}

function PlannedSessionForm({ defaultDate, onSaved }: { defaultDate: string; onSaved: () => void }): React.JSX.Element {
  const [kind, setKind] = useState<WorkoutKind>('RUNNING')
  const [form, setForm] = useState({ plan_type: 'SESSION' as 'SESSION' | 'REST', date: defaultDate, start_time: '', session_type: 'Easy', title: 'Easy run', description: '', planned_duration_minutes: '45', planned_distance_km: '', target_rpe: '3', priority: 'NORMAL' })
  const [strengthExercises, setStrengthExercises] = useState<string[]>([''])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const updateKind = (next: WorkoutKind) => { setKind(next); const sessionType = sessionOptions[next][0] ?? ''; setForm((current) => ({ ...current, session_type: sessionType, title: sessionType })); setStrengthExercises(['']) }
  const updateSessionType = (sessionType: string) => {
    setForm((current) => ({ ...current, session_type: sessionType, title: current.title === current.session_type ? sessionType : current.title }))
    if (kind === 'STRENGTH' && strengthExerciseOptions.includes(sessionType)) setStrengthExercises((current) => [sessionType, ...current.slice(1)])
  }
  const submit = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setError(null)
    try {
      const resting = form.plan_type === 'REST'
      const structuredBlocks = !resting && kind === 'STRENGTH'
        ? strengthExercises.filter(Boolean).map((exercise) => ({ exercise }))
        : !resting && kind === 'RUNNING' && structuredRunningTypes.has(form.session_type) && form.description.trim()
          ? [{ phase: 'Main', description: form.description.trim() }]
          : []
      await api.createPlannedSession({ date: form.date, start_time: resting ? null : form.start_time || null, workout_kind: resting ? 'MOBILITY_RECOVERY' : kind, session_type: resting ? 'Rest' : form.session_type, title: resting ? 'Rest' : form.title, description: form.description || null, planned_duration_minutes: resting ? null : Number(form.planned_duration_minutes) || null, planned_distance_km: resting ? null : Number(form.planned_distance_km) || null, target_rpe: resting ? null : Number(form.target_rpe) || null, priority: form.priority as PlannedSession['priority'], status: resting ? 'REST' : 'PLANNED', structured_blocks: structuredBlocks })
      onSaved()
    } catch (reason) { setError(reason instanceof ApiError ? reason.message : 'Unable to create the session.') }
    finally { setBusy(false) }
  }
  return <form className="stack-form" onSubmit={(event) => void submit(event)}>
    <div className="form-grid three">
      <SelectField label="Plan type" value={form.plan_type} onChange={(event) => setForm((current) => ({ ...current, plan_type: event.target.value as 'SESSION' | 'REST' }))}><option value="SESSION">Training session</option><option value="REST">Rest day</option></SelectField>
      <SelectField label="Activity" disabled={form.plan_type === 'REST'} value={kind} onChange={(event) => updateKind(event.target.value as WorkoutKind)}>{Object.keys(sessionOptions).map((value) => <option key={value} value={value}>{formatEnum(value)}</option>)}</SelectField>
      <SelectField label="Session type" disabled={form.plan_type === 'REST'} value={form.session_type} onChange={(event) => updateSessionType(event.target.value)}>{sessionOptions[kind].map((value) => <option key={value}>{value}</option>)}</SelectField>
      <Field label="Title" required={form.plan_type !== 'REST'} disabled={form.plan_type === 'REST'} value={form.plan_type === 'REST' ? 'Rest' : form.title} onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))} />
      <Field label="Date" type="date" required value={form.date} onChange={(event) => setForm((current) => ({ ...current, date: event.target.value }))} />
      <Field label="Start time" type="time" disabled={form.plan_type === 'REST'} value={form.start_time} onChange={(event) => setForm((current) => ({ ...current, start_time: event.target.value }))} />
      <SelectField label="Priority" disabled={form.plan_type === 'REST'} value={form.priority} onChange={(event) => setForm((current) => ({ ...current, priority: event.target.value }))}><option>LOW</option><option>NORMAL</option><option>HIGH</option></SelectField>
      <Field label="Duration (minutes)" type="number" min="1" disabled={form.plan_type === 'REST'} value={form.planned_duration_minutes} onChange={(event) => setForm((current) => ({ ...current, planned_duration_minutes: event.target.value }))} />
      <Field label="Distance (km)" type="number" min="0" step="0.1" disabled={form.plan_type === 'REST' || kind !== 'RUNNING'} value={form.planned_distance_km} onChange={(event) => setForm((current) => ({ ...current, planned_distance_km: event.target.value }))} />
      <Field label="Target RPE" type="number" min="1" max="10" disabled={form.plan_type === 'REST'} value={form.target_rpe} onChange={(event) => setForm((current) => ({ ...current, target_rpe: event.target.value }))} />
    </div>
    {form.plan_type !== 'REST' && kind === 'STRENGTH' && <div className="subform"><div className="subform-header"><div><strong>Planned exercises</strong><span>Structured exercise names let the interference engine recognise finger, pulling and lower-body demand.</span></div><Button type="button" variant="ghost" icon="plus" onClick={() => setStrengthExercises((current) => [...current, ''])}>Exercise</Button></div>{strengthExercises.map((exercise, index) => <div className="inline-editor" key={index}><select aria-label={`Planned exercise ${index + 1}`} value={exercise} onChange={(event) => setStrengthExercises((current) => current.map((item, itemIndex) => itemIndex === index ? event.target.value : item))}><option value="">Not specified</option>{strengthExerciseOptions.map((option) => <option key={option}>{option}</option>)}</select><span className="field-hint">Used for shared fatigue-domain conflict checks.</span><Button type="button" variant="ghost" icon="trash" aria-label={`Remove planned exercise ${index + 1}`} onClick={() => setStrengthExercises((current) => current.length === 1 ? [''] : current.filter((_, itemIndex) => itemIndex !== index))} /></div>)}</div>}
    <TextAreaField label="Session structure / notes" rows={4} value={form.description} onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))} placeholder="4 × 8 min @ 4:15/km, HR <= 172, 2 min recovery" />
    {error && <InlineNotice tone="warning">{error}</InlineNotice>}
    <FormActions><Button type="submit" disabled={busy}>{busy ? 'Saving…' : 'Add to plan'}</Button></FormActions>
  </form>
}

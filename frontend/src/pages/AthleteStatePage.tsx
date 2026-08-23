import { useState, type FormEvent } from 'react'
import { api, ApiError } from '../api/client'
import { useResource, type ResourceState } from '../api/hooks'
import { GradePyramid } from '../components/charts'
import { Icon } from '../components/Icon'
import { Button, Card, ConfidencePill, EmptyState, ErrorPanel, Field, FormActions, InlineNotice, LoadingGrid, Metric, Modal, PageHeader, Pill, SectionHeading, SelectField, Tabs, TextAreaField, formatEnum } from '../components/ui'
import { formatDate, formatNumber, formatPace, formatRaceTime, localIsoDate } from '../lib/format'
import type { AppSettings, ClimbingPhase, ClimbingState, GymColourProgress, GymSet, RunningPhase, RunningState } from '../types'

const runningPhases: RunningPhase[] = ['AEROBIC_BASE', 'VOLUME_BUILD', 'THRESHOLD_BUILD', 'HALF_MARATHON_SPECIFIC', 'MARATHON_SPECIFIC', 'TAPER', 'RECOVERY_TRANSITION']
const climbingPhases: ClimbingPhase[] = ['TECHNIQUE_VOLUME', 'LIMIT_BOULDERING', 'MAX_STRENGTH', 'POWER', 'POWER_ENDURANCE', 'LEAD_SPECIFIC', 'PERFORMANCE', 'RECOVERY']
const colours = ['Yellow', 'Green', 'Purple', 'Grey', 'Blue', 'Red', 'Black'] as const
const colourHex: Record<string, string> = { Yellow: '#e8cf4a', Green: '#48b87b', Purple: '#9c78e8', Grey: '#83909f', Blue: '#4f91ee', Red: '#e15e64', Black: '#323946' }
const grades = ['5+', '6A', '6A+', '6B', '6B+', '6C', '6C+', '7A', '7A+', '7B', '7B+', '7C', '7C+', '8A', '8A+', 'V3', 'V4', 'V5', 'V6', 'V7', 'V8', 'V9', 'V10']

export function AthleteStatePage(): React.JSX.Element {
  const [tab, setTab] = useState<'running' | 'climbing'>('running')
  const running = useResource(api.runningState, [])
  const climbing = useResource(api.climbingState, [])
  const settings = useResource(api.settings, [])
  return <div className="page athlete-page">
    <PageHeader eyebrow="WHERE AM I NOW?" title="Athlete State" description="Measured and estimated state for the two primary sports. Strength contributes fatigue, not a separate state." />
    <Tabs label="Athlete state sport" value={tab} onChange={setTab} items={[{ value: 'running', label: 'Running' }, { value: 'climbing', label: 'Climbing' }]} />
    {tab === 'running' ? <RunningStateView resource={running} /> : <ClimbingStateView resource={climbing} defaultGym={settings.data?.gym_name ?? ''} gradeDisplay={settings.data?.grade_display ?? 'BOTH'} />}
  </div>
}

function RunningStateView({ resource }: { resource: ResourceState<RunningState> }): React.JSX.Element {
  const data = resource.data
  const [phaseBusy, setPhaseBusy] = useState(false)
  const changePhase = async (phase: RunningPhase) => {
    setPhaseBusy(true)
    try { await api.setRunningPhase(phase); resource.reload() } finally { setPhaseBusy(false) }
  }
  if (resource.loading) return <LoadingGrid count={6} />
  if (resource.error) return <ErrorPanel message={resource.error.message} onRetry={resource.reload} />
  if (!data) return <EmptyState title="No running state yet" message="Log a run to begin building an auditable running state." />
  return <div className="state-stack">
    <section><SectionHeading title="Volume" description="Calendar periods and rolling windows are intentionally separate." /><div className="metric-grid five">
      <Card><Metric label="Current month" value={formatNumber(data.current_month_km, 1)} unit="km" /></Card>
      <Card><Metric label="Previous month" value={formatNumber(data.previous_month_km, 1)} unit="km" /></Card>
      <Card><Metric label="Rolling 7 days" value={formatNumber(data.rolling_7d_km, 1)} unit="km" /></Card>
      <Card><Metric label="Rolling 28 days" value={formatNumber(data.rolling_28d_km, 1)} unit="km" /></Card>
      <Card><Metric label="28d weekly avg" value={formatNumber(data.rolling_28d_weekly_average_km, 1)} unit="km/wk" detail="28-day distance ÷ 4" /></Card>
    </div></section>
    <div className="state-feature-grid">
      <Card className="estimate-card">
        <div className="card-header"><h2>Estimated 10K</h2><ConfidencePill value={data.estimated_10k.confidence} /></div>
        <strong className="hero-metric">{formatRaceTime(data.estimated_10k.value)}</strong>
        {data.estimated_10k.value ? <><p>{data.estimated_10k.source ?? 'Source not recorded'}{data.estimated_10k.source_date ? ` · ${formatDate(data.estimated_10k.source_date)}` : ''}</p>{data.estimated_10k.formula && <Pill>{data.estimated_10k.formula}</Pill>}</> : <p>Race or repeatable quality-session evidence is required before showing an estimate.</p>}
        {data.estimated_10k.evidence?.length ? <ul className="evidence-list compact">{data.estimated_10k.evidence.map((item) => <li key={item}>{item}</li>)}</ul> : null}
      </Card>
      <Card>
        <div className="card-header"><h2>LT1 range</h2><ConfidencePill value={data.lt1_confidence} /></div>
        <div className="threshold-grid"><Metric label="Pace" value={data.lt1_pace_range ? `${formatPace(data.lt1_pace_range[0])}–${formatPace(data.lt1_pace_range[1])}` : 'Not enough data'} unit={data.lt1_pace_range ? '/km' : undefined} /><Metric label="Heart rate" value={data.lt1_hr_range ? `${data.lt1_hr_range[0]}–${data.lt1_hr_range[1]}` : '—'} unit={data.lt1_hr_range ? 'bpm' : undefined} /></div><p className="card-note">{data.lt1_source ?? 'LT1 is displayed as a range to avoid false precision.'}</p>
      </Card>
      <Card>
        <div className="card-header"><h2>LT2 estimate</h2><ConfidencePill value={data.lt2_confidence} /></div>
        <div className="threshold-grid"><Metric label="Pace" value={formatPace(data.lt2_pace_seconds_per_km)} unit={data.lt2_pace_seconds_per_km ? '/km' : undefined} /><Metric label="Heart rate" value={data.lt2_hr ?? '—'} unit={data.lt2_hr ? 'bpm' : undefined} /></div><p className="card-note">{data.lt2_source ?? 'No threshold source recorded'}{data.lt2_updated_at ? ` · Updated ${formatDate(data.lt2_updated_at)}` : ''}</p>
      </Card>
    </div>
    <div className="two-column">
      <Card title="Running phase"><SelectField label="Current phase" value={data.phase} disabled={phaseBusy} onChange={(event) => void changePhase(event.target.value as RunningPhase)}>{runningPhases.map((phase) => <option key={phase} value={phase}>{formatEnum(phase)}</option>)}</SelectField><InlineNotice>Phase changes are manual. AI may recommend a phase, but cannot silently change it.</InlineNotice></Card>
      <Card title="Mileage progression"><div className="capacity-flow"><div><span>Current capacity</span><strong>{formatNumber(data.current_capacity_km, 1)} km/wk</strong></div><Icon name="arrow" /><div><span>Current block</span><strong>{formatNumber(data.current_block_min_km, 0)}–{formatNumber(data.current_block_max_km, 0)} km/wk</strong></div><Icon name="arrow" /><div><span>Long-term</span><strong>{formatNumber(data.long_term_min_km, 0)}–{formatNumber(data.long_term_max_km, 0)} km/wk</strong></div></div><div className="decision-row"><span>Current decision</span><Pill tone={data.progression_decision === 'BUILD' ? 'good' : data.progression_decision === 'DELOAD' ? 'low' : 'moderate'}>{data.progression_decision ?? 'HOLD'}</Pill></div>{data.progression_evidence?.length ? <ul className="evidence-list compact">{data.progression_evidence.map((item) => <li key={item}>{item}</li>)}</ul> : null}</Card>
    </div>
  </div>
}

function ClimbingStateView({ resource, defaultGym, gradeDisplay }: { resource: ResourceState<ClimbingState>; defaultGym: string; gradeDisplay: AppSettings['grade_display'] }): React.JSX.Element {
  const data = resource.data
  const [tb2Open, setTb2Open] = useState(false)
  const [setOpen, setSetOpen] = useState(false)
  const [progressOpen, setProgressOpen] = useState(false)
  const [routeOpen, setRouteOpen] = useState(false)
  const [phaseBusy, setPhaseBusy] = useState(false)
  const changePhase = async (phase: ClimbingPhase) => { setPhaseBusy(true); try { await api.setClimbingPhase(phase); resource.reload() } finally { setPhaseBusy(false) } }
  if (resource.loading) return <LoadingGrid count={5} />
  if (resource.error) return <ErrorPanel message={resource.error.message} onRetry={resource.reload} />
  if (!data) return <EmptyState title="No climbing state yet" message="Create a gym set or record a TB2 benchmark to establish climbing state." />
  const gymRows = data.current_gym_set?.progress.map((row) => ({ label: row.colour, value: row.sent_count, available: row.available_problem_count, colour: colourHex[row.colour] })) ?? []
  const hardest = [...(data.current_gym_set?.progress ?? [])].reverse().find((item) => item.sent_count > 0)?.colour
  return <div className="state-stack">
    <div className="state-feature-grid climbing-features">
      <Card className="benchmark-card">
        <div className="card-header"><h2>Tension Board 2</h2><Button variant="ghost" icon="plus" onClick={() => setTb2Open(true)}>Benchmark</Button></div>
        {data.latest_tb2 ? <>{data.latest_tb2.is_demo && <Pill tone="moderate">DEMO DATA</Pill>}<div className="benchmark-value"><strong>{data.latest_tb2.verified_grade}</strong><span>verified</span></div><div className="benchmark-meta"><Metric label="Estimated" value={data.latest_tb2.estimated_grade ?? '—'} /><Metric label="Angle" value={`${data.latest_tb2.angle}°`} /><Metric label="Date" value={formatDate(data.latest_tb2.date)} /></div>{data.latest_tb2.notes && <p className="card-note">{data.latest_tb2.notes}</p>}</> : <EmptyState icon="climb" title="No TB2 benchmark" message="Record verified and estimated grades separately, including board angle." />}
      </Card>
      <Card className="phase-card" title="Climbing phase"><SelectField label="Current phase" value={data.phase} disabled={phaseBusy} onChange={(event) => void changePhase(event.target.value as ClimbingPhase)}>{climbingPhases.map((phase) => <option key={phase} value={phase}>{formatEnum(phase)}</option>)}</SelectField><InlineNotice>Running and climbing phases can progress independently.</InlineNotice></Card>
      <Card title="Route benchmark"><div className="threshold-grid"><Metric label="Top rope" value={data.route_benchmark?.top_rope_verified_grade ?? '—'} /><Metric label="Lead" value={data.route_benchmark?.lead_verified_grade ?? '—'} /><Metric label="Target" value={data.route_benchmark?.target_grade ?? '—'} /></div><Button variant="ghost" icon="edit" onClick={() => setRouteOpen(true)}>Update benchmark</Button></Card>
    </div>
    <Card className="gym-set-card">
      <SectionHeading title={data.current_gym_set ? `${data.current_gym_set.gym} · Current set${data.current_gym_set.is_demo ? ' · DEMO' : ''}` : 'Home gym set'} description={data.current_gym_set ? `Active since ${formatDate(data.current_gym_set.start_date)} · Hardest current colour: ${hardest ?? 'none yet'}` : 'Each reset creates a new immutable historical set.'} action={<div className="button-row">{data.current_gym_set && <Button variant="ghost" icon="edit" onClick={() => setProgressOpen(true)}>Update sends</Button>}<Button icon="plus" onClick={() => setSetOpen(true)}>New set</Button></div>} />
      {gymRows.length ? <GradePyramid rows={gymRows} /> : <EmptyState title="No current set" message="Create the current gym set. Progress starts at zero without deleting prior sets." />}
    </Card>
    <InlineNotice title="Grade handling">Grade ordinals are used only for sorting and graph placement. They are not treated as linear physiological measurements.</InlineNotice>
    <Modal open={tb2Open} title="Record TB2 benchmark" onClose={() => setTb2Open(false)}><TB2Form gradeDisplay={gradeDisplay} onSaved={() => { setTb2Open(false); resource.reload() }} /></Modal>
    <Modal open={setOpen} title="Start a new gym set" onClose={() => setSetOpen(false)}><NewGymSetForm currentGym={data.current_gym_set?.gym ?? defaultGym} onSaved={() => { setSetOpen(false); resource.reload() }} /></Modal>
    <Modal open={progressOpen} title="Update current set" onClose={() => setProgressOpen(false)} wide>{data.current_gym_set && <GymProgressForm gymSet={data.current_gym_set} onSaved={() => { setProgressOpen(false); resource.reload() }} />}</Modal>
    <Modal open={routeOpen} title="Route benchmark" onClose={() => setRouteOpen(false)}><RouteForm initial={data.route_benchmark ?? {}} onSaved={() => { setRouteOpen(false); resource.reload() }} /></Modal>
  </div>
}

function TB2Form({ onSaved, gradeDisplay }: { onSaved: () => void; gradeDisplay: AppSettings['grade_display'] }): React.JSX.Element {
  const defaultVerified = gradeDisplay === 'V_SCALE' ? 'V5' : '6C'
  const defaultEstimated = gradeDisplay === 'V_SCALE' ? 'V6' : '6C+'
  const [form, setForm] = useState({ date: localIsoDate(), angle: '40', verified_grade: defaultVerified, estimated_grade: defaultEstimated, notes: '' })
  const availableGrades = gradeDisplay === 'FONT' ? grades.filter((grade) => !grade.startsWith('V')) : gradeDisplay === 'V_SCALE' ? grades.filter((grade) => grade.startsWith('V')) : grades
  const [error, setError] = useState<string | null>(null); const [busy, setBusy] = useState(false)
  const submit = async (event: FormEvent) => { event.preventDefault(); setBusy(true); setError(null); try { await api.createTb2Benchmark({ date: form.date, board: 'TB2', angle: Number(form.angle), verified_grade: form.verified_grade, estimated_grade: form.estimated_grade || null, notes: form.notes || null }); onSaved() } catch (reason) { setError(reason instanceof ApiError ? reason.message : 'Unable to save benchmark.') } finally { setBusy(false) } }
  return <form className="stack-form" onSubmit={(event) => void submit(event)}><div className="form-grid two"><Field label="Date" type="date" required value={form.date} onChange={(event) => setForm({ ...form, date: event.target.value })} /><Field label="Board angle" type="number" min="0" max="70" required value={form.angle} onChange={(event) => setForm({ ...form, angle: event.target.value })} /><SelectField label="Verified grade" value={form.verified_grade} onChange={(event) => setForm({ ...form, verified_grade: event.target.value })}>{availableGrades.map((grade) => <option key={grade}>{grade}</option>)}</SelectField><SelectField label="Estimated grade" value={form.estimated_grade} onChange={(event) => setForm({ ...form, estimated_grade: event.target.value })}><option value="">Unknown</option>{availableGrades.map((grade) => <option key={grade}>{grade}</option>)}</SelectField></div><TextAreaField label="Notes" rows={3} value={form.notes} onChange={(event) => setForm({ ...form, notes: event.target.value })} />{error && <InlineNotice tone="warning">{error}</InlineNotice>}<FormActions><Button type="submit" disabled={busy}>{busy ? 'Saving…' : 'Save benchmark'}</Button></FormActions></form>
}

function NewGymSetForm({ currentGym, onSaved }: { currentGym: string; onSaved: () => void }): React.JSX.Element {
  const [gym, setGym] = useState(currentGym); const [date, setDate] = useState(localIsoDate()); const [notes, setNotes] = useState(''); const [busy, setBusy] = useState(false); const [error, setError] = useState<string | null>(null)
  const submit = async (event: FormEvent) => { event.preventDefault(); setBusy(true); setError(null); const progress: GymColourProgress[] = colours.map((colour, index) => ({ colour, ordinal: index + 1, sent_count: 0, available_problem_count: null })); try { await api.createGymSet({ gym, start_date: date, notes: notes || null, progress }); onSaved() } catch (reason) { setError(reason instanceof ApiError ? reason.message : 'Unable to create set.') } finally { setBusy(false) } }
  return <form className="stack-form" onSubmit={(event) => void submit(event)}><InlineNotice tone="warning" title="Historical data is preserved">Starting a new set closes the current set and starts all seven colour counts at zero.</InlineNotice><Field label="Gym" required value={gym} onChange={(event) => setGym(event.target.value)} /><Field label="Start date" type="date" required value={date} onChange={(event) => setDate(event.target.value)} /><TextAreaField label="Notes" rows={3} value={notes} onChange={(event) => setNotes(event.target.value)} />{error && <InlineNotice tone="warning">{error}</InlineNotice>}<FormActions><Button type="submit" disabled={busy || !gym.trim()}>{busy ? 'Starting…' : 'Start new set'}</Button></FormActions></form>
}

function GymProgressForm({ gymSet, onSaved }: { gymSet: GymSet; onSaved: () => void }): React.JSX.Element {
  const [rows, setRows] = useState(() => colours.map((colour, index) => gymSet.progress.find((item) => item.colour === colour) ?? { colour, ordinal: index + 1, sent_count: 0, available_problem_count: null }))
  const [busy, setBusy] = useState(false); const [error, setError] = useState<string | null>(null)
  const update = (index: number, key: 'sent_count' | 'available_problem_count', value: string) => setRows((current) => current.map((row, rowIndex) => rowIndex === index ? { ...row, [key]: value === '' ? key === 'sent_count' ? 0 : null : Number(value) } : row))
  const submit = async (event: FormEvent) => { event.preventDefault(); setBusy(true); setError(null); try { await api.updateGymProgress(gymSet.id, { progress: rows }); onSaved() } catch (reason) { setError(reason instanceof ApiError ? reason.message : 'Unable to update sends.') } finally { setBusy(false) } }
  return <form className="stack-form" onSubmit={(event) => void submit(event)}><div className="gym-progress-editor"><div className="gym-row heading"><span>Colour</span><span>Sent</span><span>Available · optional</span><span>Completion</span></div>{rows.map((row, index) => <div className="gym-row" key={row.colour}><strong><i style={{ background: colourHex[row.colour] }} />{row.colour}</strong><input aria-label={`${row.colour} sent`} type="number" min="0" value={row.sent_count} onChange={(event) => update(index, 'sent_count', event.target.value)} /><input aria-label={`${row.colour} available`} type="number" min="0" value={row.available_problem_count ?? ''} onChange={(event) => update(index, 'available_problem_count', event.target.value)} /><span>{row.available_problem_count ? `${Math.round(row.sent_count / row.available_problem_count * 100)}%` : '—'}</span></div>)}</div>{error && <InlineNotice tone="warning">{error}</InlineNotice>}<FormActions><Button type="submit" disabled={busy}>{busy ? 'Saving…' : 'Save progress'}</Button></FormActions></form>
}

function RouteForm({ initial, onSaved }: { initial: { top_rope_verified_grade?: string | null; lead_verified_grade?: string | null; target_grade?: string | null }; onSaved: () => void }): React.JSX.Element {
  const [form, setForm] = useState({ top_rope_verified_grade: initial.top_rope_verified_grade ?? '', lead_verified_grade: initial.lead_verified_grade ?? '', target_grade: initial.target_grade ?? '' }); const [busy, setBusy] = useState(false); const [error, setError] = useState<string | null>(null)
  const submit = async (event: FormEvent) => { event.preventDefault(); setBusy(true); setError(null); try { await api.saveRouteBenchmark({ ...form, last_updated: localIsoDate() }); onSaved() } catch (reason) { setError(reason instanceof ApiError ? reason.message : 'Unable to save route benchmark.') } finally { setBusy(false) } }
  return <form className="stack-form" onSubmit={(event) => void submit(event)}><div className="form-grid"><Field label="Verified top-rope grade" value={form.top_rope_verified_grade} onChange={(event) => setForm({ ...form, top_rope_verified_grade: event.target.value })} /><Field label="Verified lead grade" value={form.lead_verified_grade} onChange={(event) => setForm({ ...form, lead_verified_grade: event.target.value })} /><Field label="Target grade" value={form.target_grade} onChange={(event) => setForm({ ...form, target_grade: event.target.value })} /></div>{error && <InlineNotice tone="warning">{error}</InlineNotice>}<FormActions><Button type="submit" disabled={busy}>{busy ? 'Saving…' : 'Save benchmark'}</Button></FormActions></form>
}

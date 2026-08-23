import { useMemo, useState, type FormEvent } from 'react'
import { api, ApiError } from '../api/client'
import { formatDuration, formatNumber, recordLabel } from '../lib/format'
import type { AdaptationProposal, CalendarEntry, ReadinessSummary, RecoveryCheckIn, Sport } from '../types'
import { Button, Card, Field, FormActions, InlineNotice, Meter, Modal, Pill, ReadinessPill, TextAreaField, formatEnum } from './ui'
import { Icon } from './Icon'

export function ReadinessCard({ readiness, sport }: { readiness?: ReadinessSummary | null; sport: Sport }): React.JSX.Element {
  const accent = sport === 'RUNNING' ? 'run' : 'climb'
  const fallback: ReadinessSummary = { sport, label: 'MODERATE', components: [] }
  const value = readiness ?? fallback
  const showExplanation = Boolean(value.explanation || value.subjective_delta != null || value.local_soreness_penalty != null || value.warnings?.length)
  return <Card className={`readiness-card readiness-${accent}`}>
    <div className="readiness-heading"><div className="sport-icon"><Icon name={sport === 'RUNNING' ? 'run' : 'climb'} size={24} /></div><div><span>{sport === 'RUNNING' ? 'Running' : 'Climbing'} readiness</span><strong>{value.label}</strong></div><ReadinessPill value={value.label} /></div>
    {value.components.length ? <div className="readiness-components">{value.components.map((component) => <div key={component.domain}><span>{formatEnum(component.domain)}</span><Meter value={component.value} tone={accent} /></div>)}</div> : <p className="muted">Complete sessions and recovery check-ins to establish readiness.</p>}
    {showExplanation && <div className="card-note readiness-explanation">
      {value.explanation && <p>{value.explanation}</p>}
      <div className="readiness-adjustments">
        {value.subjective_delta != null && <span><small>Subjective delta</small><strong>{signedNumber(value.subjective_delta)}</strong></span>}
        {value.local_soreness_penalty != null && <span><small>Local soreness penalty</small><strong>−{formatNumber(value.local_soreness_penalty, 2)}</strong></span>}
      </div>
      {value.warnings?.length ? <ul className="readiness-warnings">{value.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul> : null}
    </div>}
  </Card>
}

function signedNumber(value: number): string {
  return `${value > 0 ? '+' : ''}${formatNumber(value, 2)}`
}

const statusTone: Record<string, 'good' | 'moderate' | 'low' | 'neutral'> = {
  COMPLETED: 'good', MODIFIED: 'moderate', SKIPPED: 'low', REPLACED: 'moderate', MOVED: 'moderate', PLANNED: 'neutral', REST: 'neutral',
}

export function SessionCard({ entry, compact = false, onComplete, onSkip }: { entry: CalendarEntry; compact?: boolean; onComplete?: (plannedSessionId: string | number) => void; onSkip?: (plannedSessionId: string | number) => void }): React.JSX.Element {
  const session = entry.completed ?? entry.planned
  if (!session) return <div className="session-card session-rest"><span className="session-time">—</span><div><strong>Rest</strong><p>Recovery day</p></div><Pill>REST</Pill></div>
  const isCompleted = Boolean(entry.completed)
  const duration = entry.completed?.duration_minutes ?? entry.planned?.planned_duration_minutes
  const distance = entry.completed?.distance_km ?? entry.planned?.planned_distance_km
  return <article className={`session-card ${isCompleted ? 'is-completed' : ''} ${compact ? 'compact' : ''}`}>
    <span className="session-time">{session.start_time?.slice(0, 5) ?? 'Any time'}</span>
    <div className={`session-sport sport-${session.workout_kind.toLowerCase()}`}><Icon name={session.workout_kind === 'RUNNING' ? 'run' : session.workout_kind === 'CLIMBING' ? 'climb' : 'workouts'} size={18} /></div>
    <div className="session-copy"><strong>{'title' in session && session.title ? session.title : formatEnum(session.session_type)}</strong><p>{formatEnum(session.workout_kind)}{duration ? ` · ${formatDuration(duration)}` : ''}{distance ? ` · ${formatNumber(distance, 1)} km` : ''}</p>{entry.planned && entry.completed && !compact && <small>Planned: {entry.planned.title} · Actual: {entry.completed.title ?? formatEnum(entry.completed.session_type)}</small>}</div>
    <div className="session-actions">{session.is_demo && <Pill tone="moderate">DEMO</Pill>}{entry.planned?.is_locked && <Pill tone="info">LOCKED</Pill>}<Pill tone={statusTone[entry.status] ?? 'neutral'}>{entry.status}</Pill>{entry.planned && !entry.completed && entry.status !== 'REST' && onComplete && <Button variant="ghost" icon="check" onClick={() => onComplete(entry.planned!.id)}>Complete</Button>}{entry.planned && !entry.completed && ['PLANNED', 'MODIFIED'].includes(entry.status) && onSkip && <Button variant="ghost" icon="close" onClick={() => onSkip(entry.planned!.id)}>Skip</Button>}</div>
  </article>
}

export function AdaptationCard({ proposal, onChanged }: { proposal: AdaptationProposal; onChanged?: () => void }): React.JSX.Element {
  const [editing, setEditing] = useState(false)
  const [proposed, setProposed] = useState(() => JSON.stringify(typeof proposal.proposed_plan === 'string' ? { description: proposal.proposed_plan } : proposal.proposed_plan, null, 2))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const decide = async (decision: 'ACCEPT' | 'REJECT', edited = false) => {
    setError(null)
    let plan: Record<string, unknown> | undefined
    if (edited) {
      try {
        const parsed: unknown = JSON.parse(proposed)
        if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error('not an object')
        plan = parsed as Record<string, unknown>
      } catch {
        setError('The edited plan must be a valid JSON object so date, duration and other fields remain structured.')
        return
      }
    }
    setBusy(true)
    try {
      await api.decideAdaptation(proposal.id, decision, plan)
      setEditing(false)
      onChanged?.()
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : 'Unable to save the decision.')
    } finally { setBusy(false) }
  }
  return <Card className="adaptation-card">
    <div className="adaptation-top"><div><span className="eyebrow">{proposal.session_title}</span><h3>{formatEnum(proposal.action)}</h3></div><div className="proposal-badges"><Pill tone={proposal.source === 'RULE_ENGINE' ? 'info' : 'neutral'}>{formatEnum(proposal.source)}</Pill><Pill tone={proposal.confidence === 'HIGH' ? 'good' : proposal.confidence === 'LOW' ? 'low' : 'moderate'}>{proposal.confidence} CONF.</Pill></div></div>
    <div className="plan-diff"><div><span>OLD</span><pre>{recordLabel(proposal.original_plan)}</pre></div><Icon name="arrow" /><div><span>NEW</span><pre>{recordLabel(proposal.proposed_plan)}</pre></div></div>
    <div className="proposal-reason"><strong>Reason</strong><p>{proposal.reason}</p></div>
    <div className="evidence-list"><strong>Evidence</strong><ul>{proposal.evidence.map((item) => <li key={item}>{item}</li>)}</ul></div>
    {error && <InlineNotice tone="warning">{error}</InlineNotice>}
    {proposal.status === 'PENDING' || !proposal.status ? <FormActions><Button disabled={busy} onClick={() => void decide('ACCEPT')}>Apply</Button><Button disabled={busy} onClick={() => void decide('REJECT')}>Reject</Button><Button icon="edit" variant="ghost" disabled={busy} onClick={() => setEditing(true)}>Edit</Button></FormActions> : <InlineNotice tone="success">Decision recorded: {proposal.status}</InlineNotice>}
    <Modal open={editing} title="Edit proposed session" onClose={() => setEditing(false)}>
      <TextAreaField label="Proposed plan JSON" value={proposed} rows={10} onChange={(event) => setProposed(event.target.value)} hint="Edit structured fields such as date or duration. The original plan remains unchanged in history." />
      <FormActions><Button variant="ghost" onClick={() => setEditing(false)}>Cancel</Button><Button disabled={busy || !proposed.trim()} onClick={() => void decide('ACCEPT', true)}>Apply edited plan</Button></FormActions>
    </Modal>
  </Card>
}

const sorenessAreas = ['finger', 'elbow', 'shoulder', 'back', 'hip', 'knee', 'calf', 'ankle'] as const

export function RecoveryForm({ onSaved }: { onSaved?: () => void }): React.JSX.Element {
  const [form, setForm] = useState<RecoveryCheckIn>({ date: new Date().toISOString().slice(0, 10), soreness: {} })
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const numeric = (key: keyof RecoveryCheckIn, value: string) => setForm((current) => ({ ...current, [key]: value === '' ? null : Number(value) }))
  const scoreFields = useMemo(() => [
    ['sleep_quality', 'Sleep quality', '1', '5'], ['energy', 'Energy', '1', '5'], ['motivation', 'Motivation', '1', '5'], ['stress', 'Stress', '1', '5'], ['general_soreness', 'General soreness', '0', '10'],
  ] as const, [])
  const submit = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setMessage(null)
    try { await api.saveRecoveryCheckIn(form); setMessage('Recovery check-in saved. Readiness will be recalculated.'); onSaved?.() }
    catch (reason) { setMessage(reason instanceof ApiError ? reason.message : 'Unable to save check-in.') }
    finally { setBusy(false) }
  }
  return <form onSubmit={(event) => void submit(event)} className="stack-form">
    <div className="form-grid three">
      <Field label="Date" type="date" required value={form.date} onChange={(event) => setForm((current) => ({ ...current, date: event.target.value }))} />
      <Field label="Sleep duration" type="number" min="0" max="24" step="0.25" placeholder="hours" value={form.sleep_duration_hours ?? ''} onChange={(event) => numeric('sleep_duration_hours', event.target.value)} />
      {scoreFields.map(([key, label, min, max]) => <Field key={key} label={label} type="number" min={min} max={max} value={(form[key] as number | null | undefined) ?? ''} onChange={(event) => numeric(key, event.target.value)} />)}
      <Field label="Resting HR" type="number" min="20" max="220" value={form.resting_hr ?? ''} onChange={(event) => numeric('resting_hr', event.target.value)} />
      <Field label="HRV" type="number" min="0" value={form.hrv ?? ''} onChange={(event) => numeric('hrv', event.target.value)} />
    </div>
    <div><span className="field-label">Area soreness · optional (0–10)</span><div className="soreness-grid">{sorenessAreas.map((area) => <label key={area}><span>{formatEnum(area)}</span><input type="number" min="0" max="10" value={form.soreness?.[area] ?? ''} onChange={(event) => setForm((current) => ({ ...current, soreness: { ...current.soreness, [area]: event.target.value === '' ? undefined : Number(event.target.value) } }))} /></label>)}</div></div>
    {message && <InlineNotice tone={message.includes('saved') ? 'success' : 'warning'}>{message}</InlineNotice>}
    <FormActions><Button type="submit" disabled={busy}>{busy ? 'Saving…' : 'Save check-in'}</Button></FormActions>
  </form>
}

import { useMemo, useState } from 'react'
import { api, ApiError } from '../api/client'
import { useResource } from '../api/hooks'
import { useCapabilities } from '../app/CapabilityProvider'
import { Button, Card, EmptyState, ErrorPanel, FormActions, InlineNotice, LoadingGrid, Metric, PageHeader, Pill, Tabs, TextAreaField } from '../components/ui'
import { formatDate, formatDuration, formatNumber, localIsoDate, startOfWeek } from '../lib/format'
import type { MonthlyBlockPreview, ReviewPlanProposal, WeeklyPlanPreview } from '../types'

type Cadence = 'WEEKLY' | 'MONTHLY'

function currentMonthStart(): string {
  return `${localIsoDate().slice(0, 7)}-01`
}

export function WeeklyReviewPage(): React.JSX.Element {
  const { capabilities } = useCapabilities()
  const resource = useResource(api.reviewPlanProposals, [])
  const [cadence, setCadence] = useState<Cadence>('WEEKLY')
  const [weekStart, setWeekStart] = useState(localIsoDate(startOfWeek()))
  const [monthStart, setMonthStart] = useState(currentMonthStart())
  const [selectedId, setSelectedId] = useState<string | number | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const proposals = useMemo(() => (resource.data?.items ?? []).filter((item) => item.cadence === cadence), [cadence, resource.data])
  const selected = proposals.find((item) => item.id === selectedId) ?? proposals[0]
  const periodStart = cadence === 'WEEKLY' ? weekStart : monthStart

  const generate = async () => {
    setBusy(true); setError(null); setMessage(null)
    try {
      const result = cadence === 'WEEKLY' ? await api.generateWeeklyPlan(weekStart) : await api.generateMonthlyPlan(monthStart)
      resource.setData((current) => current ? { ...current, items: [result, ...current.items] } : { items: [result] })
      setSelectedId(result.id)
    } catch (reason) { setError(reason instanceof ApiError ? reason.message : 'Unable to generate this review and plan.') } finally { setBusy(false) }
  }

  const update = (proposal: ReviewPlanProposal) => resource.setData((current) => current ? { ...current, items: current.items.map((item) => item.id === proposal.id ? proposal : item) } : current)
  const approve = async (proposal: ReviewPlanProposal) => { setBusy(true); setError(null); try { update(await api.approveReviewPlan(proposal.id)); setMessage(proposal.cadence === 'WEEKLY' ? 'Approved sessions were added to Calendar. Existing sessions were preserved.' : 'The next monthly training block is now active. Athlete phases were not silently changed.') } catch (reason) { setError(reason instanceof ApiError ? reason.message : 'Unable to approve this plan.') } finally { setBusy(false) } }
  const cancel = async (proposal: ReviewPlanProposal) => { setBusy(true); setError(null); try { update(await api.cancelReviewPlan(proposal.id)); setMessage('Preview cancelled. Calendar and athlete state were unchanged.') } catch (reason) { setError(reason instanceof ApiError ? reason.message : 'Unable to cancel this preview.') } finally { setBusy(false) } }

  return <div className="page review-page">
    <PageHeader eyebrow="PLAN → TRAIN → REVIEW → ADAPT" title="Review & Plan" description="Review completed evidence, preview the next planning layer, then approve it explicitly." actions={<div className="review-controls"><label><span>{cadence === 'WEEKLY' ? 'Week starting' : 'Month starting'}</span><input type={cadence === 'WEEKLY' ? 'date' : 'month'} value={cadence === 'WEEKLY' ? weekStart : monthStart.slice(0, 7)} onChange={(event) => cadence === 'WEEKLY' ? setWeekStart(event.target.value) : setMonthStart(`${event.target.value}-01`)} /></label><Button icon="refresh" disabled={busy || !capabilities.ai_planner} onClick={() => void generate()}>{busy ? 'Generating…' : cadence === 'WEEKLY' ? 'Review & Generate Next Week' : 'Review & Plan Next Month'}</Button></div>} />
    <Tabs label="Planning period" value={cadence} onChange={setCadence} items={[{ value: 'WEEKLY', label: 'Weekly' }, { value: 'MONTHLY', label: 'Monthly' }]} />
    {!capabilities.ai_planner && <InlineNotice tone="warning" title="Planner unavailable">Configure the backend OpenAI API key and planner model. Workout logging, load, fatigue, readiness, and short-term adaptation still work without it.</InlineNotice>}
    {error && <InlineNotice tone="warning" title="Planning request failed">{error} No Calendar session or monthly block was changed.</InlineNotice>}
    {message && <InlineNotice tone="success">{message}</InlineNotice>}
    {resource.loading ? <LoadingGrid count={4} /> : resource.error ? <ErrorPanel message={resource.error.message} onRetry={resource.reload} /> : selected ? <div className="review-layout"><aside className="review-history"><strong>{cadence === 'WEEKLY' ? 'Weekly' : 'Monthly'} history</strong>{proposals.map((proposal) => <button key={proposal.id} className={selected.id === proposal.id ? 'active' : ''} onClick={() => setSelectedId(proposal.id)}><span>{formatDate(proposal.period_start, cadence === 'WEEKLY' ? { month: 'short', day: 'numeric' } : { month: 'long', year: 'numeric' })}</span><Pill tone={proposal.status === 'APPROVED' ? 'good' : proposal.status === 'CANCELLED' ? 'neutral' : 'info'}>{proposal.status}</Pill></button>)}</aside><ProposalDocument proposal={selected} busy={busy} onApprove={approve} onCancel={cancel} onUpdate={update} onRegenerate={() => void generate()} /></div> : <EmptyState icon="review" title={`No ${cadence.toLowerCase()} review & plan yet`} message={`The selected ${cadence.toLowerCase()} period starts ${formatDate(periodStart)}. Generation first aggregates measured training deterministically.`} action={<Button icon="refresh" disabled={!capabilities.ai_planner || busy} onClick={() => void generate()}>{cadence === 'WEEKLY' ? 'Review & Generate Next Week' : 'Review & Plan Next Month'}</Button>} />}
  </div>
}

function ProposalDocument({ proposal, busy, onApprove, onCancel, onUpdate, onRegenerate }: { proposal: ReviewPlanProposal; busy: boolean; onApprove: (proposal: ReviewPlanProposal) => Promise<void>; onCancel: (proposal: ReviewPlanProposal) => Promise<void>; onUpdate: (proposal: ReviewPlanProposal) => void; onRegenerate: () => void }): React.JSX.Element {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(JSON.stringify(proposal.proposed_plan, null, 2))
  const [editError, setEditError] = useState<string | null>(null)
  const saveEdit = async () => {
    setEditError(null)
    try { const parsed = JSON.parse(draft) as Record<string, unknown>; onUpdate(await api.editReviewPlan(proposal.id, parsed)); setEditing(false) } catch (reason) { setEditError(reason instanceof ApiError ? reason.message : 'The edited plan must be valid JSON matching the preview structure.') }
  }
  return <article className="review-document">
    <header><div><span className="eyebrow">{proposal.cadence} · {formatDate(proposal.period_start)}–{formatDate(proposal.period_end)}</span><h2>{proposal.review.summary}</h2></div><Pill tone="info">{proposal.model ?? 'configured planner'}</Pill></header>
    <div className="review-section-grid"><AnalysisCard title="Running" text={proposal.review.running_analysis} /><AnalysisCard title="Climbing" text={proposal.review.climbing_analysis} /><AnalysisCard title="Recovery" text={proposal.review.recovery_analysis} /></div>
    {proposal.review.goal_progress && <Card title="Goal progress"><p>{proposal.review.goal_progress}</p></Card>}
    <Card title="Key findings"><ul className="review-list">{proposal.review.key_findings.map((item) => <li key={item}>{item}</li>)}</ul></Card>
    {editing ? <Card title="Edit preview"><InlineNotice>Only this preview changes. Nothing is written to Calendar or the monthly block until Approve.</InlineNotice><TextAreaField label="Structured plan JSON" rows={22} value={draft} onChange={(event) => setDraft(event.target.value)} />{editError && <InlineNotice tone="warning">{editError}</InlineNotice>}<FormActions><Button variant="ghost" onClick={() => { setEditing(false); setDraft(JSON.stringify(proposal.proposed_plan, null, 2)) }}>Cancel edit</Button><Button onClick={() => void saveEdit()}>Save preview edit</Button></FormActions></Card> : proposal.cadence === 'WEEKLY' ? <WeeklyPreview plan={proposal.proposed_plan as WeeklyPlanPreview} /> : <MonthlyPreview block={proposal.proposed_plan as MonthlyBlockPreview} />}
    {proposal.status === 'PREVIEW' ? <FormActions><Button variant="ghost" disabled={busy} onClick={() => void onCancel(proposal)}>Cancel</Button><Button variant="ghost" disabled={busy} onClick={() => setEditing(true)}>Edit</Button><Button variant="ghost" disabled={busy} onClick={onRegenerate}>Regenerate</Button><Button disabled={busy} onClick={() => void onApprove(proposal)}>Approve</Button></FormActions> : <InlineNotice tone={proposal.status === 'APPROVED' ? 'success' : 'info'}>{proposal.status === 'APPROVED' ? 'Approved. This preview is preserved as planning history.' : 'Cancelled. No proposed changes were applied.'}</InlineNotice>}
  </article>
}

function AnalysisCard({ title, text }: { title: string; text: string }): React.JSX.Element { return <Card title={title}><p>{text}</p></Card> }

function WeeklyPreview({ plan }: { plan: WeeklyPlanPreview }): React.JSX.Element {
  return <div className="planning-preview"><Card title="Next week"><div className="metric-grid three"><Metric label="Running target" value={formatNumber(plan.running_target_km, 1)} unit="km" /><Metric label="Sessions" value={plan.sessions.length} /><Metric label="Warnings" value={plan.warnings.length} /></div><p>{plan.summary}</p></Card><div className="review-section-grid"><ListCard title="Running objectives" items={plan.running_objectives} /><ListCard title="Climbing objectives" items={plan.climbing_objectives} /><ListCard title="Warnings" items={plan.warnings} /></div><Card title="Detailed weekly sessions"><div className="plan-session-preview">{plan.sessions.map((session, index) => <article key={`${session.date}-${index}`}><div><strong>{formatDate(session.date, { weekday: 'short', month: 'short', day: 'numeric' })} · {session.title}</strong><span>{session.workout_kind} · {session.session_type}</span></div><p>{session.description}</p><small>{session.planned_distance_km != null ? `${formatNumber(session.planned_distance_km, 1)} km · ` : ''}{session.planned_duration_minutes != null ? `${formatDuration(session.planned_duration_minutes)} · ` : ''}{session.target_rpe != null ? `RPE ${session.target_rpe}` : 'RPE not specified'}</small></article>)}</div></Card><InlineNotice>Approve adds non-conflicting sessions. Existing and locked Calendar sessions are preserved.</InlineNotice></div>
}

function MonthlyPreview({ block }: { block: MonthlyBlockPreview }): React.JSX.Element {
  return <div className="planning-preview"><Card title="Next month training block"><div className="metric-grid three"><Metric label="Running phase" value={block.running_phase.replaceAll('_', ' ')} /><Metric label="Climbing phase" value={block.climbing_phase.replaceAll('_', ' ')} /><Metric label="Weekly targets" value={block.weekly_running_volume_targets.length} /></div><p><strong>Weekly running volume:</strong> {block.weekly_running_volume_targets.map((value) => `${formatNumber(value, 1)} km`).join(' · ') || 'Not enough data'}</p></Card><div className="review-section-grid"><ListCard title="Running objectives" items={block.running_objectives} /><ListCard title="Climbing objectives" items={block.climbing_objectives} /><ListCard title="Climbing focus" items={block.climbing_focus} /></div><Card title="Block guidance"><p><strong>Quality:</strong> {block.quality_session_guidance}</p><p><strong>Long run:</strong> {block.long_run_guidance}</p><p><strong>Climbing frequency:</strong> {block.climbing_frequency_guidance}</p><p><strong>Supporting strength:</strong> {block.supporting_strength_guidance}</p></Card><div className="review-section-grid"><ListCard title="Progress when" items={block.progression_criteria} /><ListCard title="Hold when" items={block.hold_criteria} /><ListCard title="Deload when" items={block.deload_criteria} /></div><InlineNotice>Approve saves this block. Detailed daily workouts are generated by the Weekly Planner; athlete phases remain explicit user-controlled state.</InlineNotice></div>
}

function ListCard({ title, items }: { title: string; items: string[] }): React.JSX.Element { return <Card title={title}>{items.length ? <ul className="review-list">{items.map((item) => <li key={item}>{item}</li>)}</ul> : <p className="muted">Not enough data.</p>}</Card> }

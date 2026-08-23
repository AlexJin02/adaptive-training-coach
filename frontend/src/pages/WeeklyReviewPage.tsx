import { useMemo, useState } from 'react'
import { api, ApiError } from '../api/client'
import { useResource } from '../api/hooks'
import { useCapabilities } from '../app/CapabilityProvider'
import { Donut } from '../components/charts'
import { Icon } from '../components/Icon'
import { Button, Card, EmptyState, ErrorPanel, InlineNotice, LoadingGrid, Metric, PageHeader, Pill, SectionHeading } from '../components/ui'
import { formatDate, formatNumber, localIsoDate, startOfWeek } from '../lib/format'
import type { WeeklyReview } from '../types'

export function WeeklyReviewPage(): React.JSX.Element {
  const { capabilities } = useCapabilities()
  const resource = useResource(api.weeklyReviews, [])
  const currentMonday = localIsoDate(startOfWeek())
  const [weekStart, setWeekStart] = useState(currentMonday)
  const [selectedId, setSelectedId] = useState<string | number | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const reviews = useMemo(() => resource.data?.items ?? [], [resource.data])
  const selected = useMemo(() => reviews.find((review) => review.id === selectedId) ?? reviews.find((review) => review.week_start === weekStart) ?? reviews[0], [reviews, selectedId, weekStart])
  const generate = async () => { setBusy(true); setError(null); try { const result = await api.generateWeeklyReview(weekStart); resource.setData((current) => current ? { ...current, items: [result, ...current.items.filter((item) => item.id !== result.id)] } : { items: [result] }); setSelectedId(result.id) } catch (reason) { setError(reason instanceof ApiError ? reason.message : 'Unable to generate review.') } finally { setBusy(false) } }
  return <div className="page review-page">
    <PageHeader eyebrow="WEEKLY FEEDBACK LOOP" title="Weekly Review" description="What happened, what it means, and the smallest concrete changes for next week." actions={<div className="review-controls"><label><span>Week starting</span><input type="date" value={weekStart} onChange={(event) => setWeekStart(event.target.value)} /></label><Button icon="refresh" disabled={busy} onClick={() => void generate()}>{busy ? 'Generating…' : selected?.week_start === weekStart ? 'Regenerate review' : 'Generate review'}</Button></div>} />
    {!capabilities.ai_weekly_review && <InlineNotice title="Deterministic review mode">Core totals, compliance and trends remain available without an API key. AI narrative enhancement is currently unavailable.</InlineNotice>}
    {error && <InlineNotice tone="warning" title="Review generation failed">{error} Existing reviews and recorded sessions remain unchanged.</InlineNotice>}
    {resource.loading ? <LoadingGrid count={5} /> : resource.error ? <ErrorPanel message={resource.error.message} onRetry={resource.reload} /> : reviews.length && selected ? <div className="review-layout"><aside className="review-history"><SectionHeading title="History" />{reviews.map((review) => <button key={review.id} className={selected.id === review.id ? 'active' : ''} onClick={() => setSelectedId(review.id)}><span>Week of</span><strong>{formatDate(review.week_start, { month: 'short', day: 'numeric', year: 'numeric' })}</strong><Pill tone={review.status === 'FINAL' ? 'good' : 'neutral'}>{review.status ?? 'GENERATED'}</Pill></button>)}</aside><ReviewDocument review={selected} /></div> : <EmptyState icon="review" title="No weekly reviews yet" message="Generate a review after a training week. Basic statistics work even when AI is not configured." action={<Button icon="refresh" onClick={() => void generate()}>Generate this week</Button>} />}
  </div>
}

function ReviewDocument({ review }: { review: WeeklyReview }): React.JSX.Element {
  const complianceTotal = Object.values(review.compliance).reduce((sum, value) => sum + value, 0)
  return <article className="review-document">
    <header><div><span className="eyebrow">WEEK OF {formatDate(review.week_start, { month: 'long', day: 'numeric', year: 'numeric' }).toUpperCase()}</span><h2>Training review</h2></div><Pill tone={review.source === 'AI' ? 'info' : 'neutral'}>{review.source ?? 'RULE_ENGINE'} SUMMARY</Pill></header>
    <div className="metric-grid five review-metrics"><Card><Metric label="Training time" value={Math.round(review.summary.total_training_minutes / 60 * 10) / 10} unit="h" /></Card><Card><Metric label="Running" value={formatNumber(review.summary.running_distance_km, 1)} unit="km" /></Card><Card><Metric label="Climbing" value={Math.round(review.summary.climbing_minutes / 60 * 10) / 10} unit="h" /></Card><Card><Metric label="Strength" value={review.summary.strength_sessions} unit="sessions" /></Card><Card><Metric label="Rest" value={review.summary.rest_days} unit="days" /></Card></div>
    <Card className="compliance-card"><SectionHeading title="Compliance" description="Planned and actual training remain separate." /><div className="compliance-content"><Donut value={review.compliance.completed} total={Math.max(1, review.compliance.planned)} label="Completed as planned" detail={`${review.compliance.completed}/${review.compliance.planned}`} /><div className="compliance-bars">{Object.entries(review.compliance).map(([label, value]) => <div key={label}><span>{label}</span><div><i style={{ width: `${complianceTotal ? value / complianceTotal * 100 : 0}%` }} /></div><strong>{value}</strong></div>)}</div></div></Card>
    <div className="review-section-grid"><ReviewSection icon="run" title="Running" items={review.running} /><ReviewSection icon="climb" title="Climbing" items={review.climbing} /><ReviewSection icon="heart" title="Recovery" items={review.recovery} /></div>
    <ReviewSection icon="target" title="Key findings" items={review.key_findings} prominent />
    <ReviewSection icon="arrow" title="Next week" items={review.next_week} prominent />
    <InlineNotice>Recommendations are planning guidance, not medical diagnosis. Persistent pain or health concerns require an appropriate professional.</InlineNotice>
  </article>
}

function ReviewSection({ icon, title, items, prominent = false }: { icon: 'run' | 'climb' | 'heart' | 'target' | 'arrow'; title: string; items: string[]; prominent?: boolean }): React.JSX.Element {
  return <Card className={prominent ? 'review-prominent' : ''}><div className="review-section-title"><Icon name={icon} /><h3>{title}</h3></div>{items.length ? <ul className="review-list">{items.map((item) => <li key={item}>{item}</li>)}</ul> : <p className="muted">No evidence-backed findings for this section.</p>}</Card>
}

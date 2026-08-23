import { useState } from 'react'
import { api } from '../api/client'
import { useResource } from '../api/hooks'
import { BarChart } from '../components/charts'
import { Icon } from '../components/Icon'
import { ReadinessCard, RecoveryForm } from '../components/training'
import { Button, Card, EmptyState, ErrorPanel, InlineNotice, LoadingGrid, Meter, Modal, PageHeader, Pill, SectionHeading, formatEnum } from '../components/ui'
import type { CompletedSession, FatigueDomain, FatigueValue, ReadinessSummary, SeriesPoint } from '../types'

const domainMeta: Record<FatigueDomain, { short: string; sport: string; description: string }> = {
  CARDIOVASCULAR: { short: 'Cardio', sport: 'Running', description: 'Aerobic and cardiovascular stress' },
  LOWER_BODY: { short: 'Lower body', sport: 'Running', description: 'Leg and impact-related fatigue' },
  FINGER_FOREARM: { short: 'Finger / forearm', sport: 'Climbing', description: 'Local finger and forearm stress' },
  PULLING_UPPER_BODY: { short: 'Pulling', sport: 'Climbing', description: 'Back, arm and pulling-chain stress' },
  NEURAL: { short: 'Neural', sport: 'Shared', description: 'High-intensity coordination and recruitment' },
  SYSTEMIC: { short: 'Systemic', sport: 'Shared', description: 'Whole-system training stress' },
}

export function buildRecentLoadSeries(sessions: CompletedSession[]): SeriesPoint[] {
  return sessions.slice(0, 14).reverse().map((session) => ({
    date: session.date,
    value: session.srpe_load ?? session.duration_minutes * (session.rpe ?? 0),
    label: session.title ?? session.session_type,
  }))
}

export function LoadReadinessPage(): React.JSX.Element {
  const fatigue = useResource(api.fatigue, [])
  const readiness = useResource(api.readiness, [])
  const sessions = useResource(api.completedSessions, [])
  const [checkInOpen, setCheckInOpen] = useState(false)
  const running = readiness.data?.items.find((item) => item.sport === 'RUNNING')
  const climbing = readiness.data?.items.find((item) => item.sport === 'CLIMBING')
  const loadSeries = buildRecentLoadSeries(sessions.data?.items ?? [])
  const anyError = fatigue.error ?? readiness.error ?? sessions.error
  const loading = fatigue.loading || readiness.loading || sessions.loading

  return <div className="page load-page">
    <PageHeader eyebrow="LOAD / FATIGUE / READINESS" title="Load & Readiness" description="Transparent planning heuristics, split by sport and linked through six shared fatigue domains." actions={<Button icon="heart" onClick={() => setCheckInOpen(true)}>Recovery check-in</Button>} />
    {anyError && <ErrorPanel message={anyError.message} onRetry={() => { fatigue.reload(); readiness.reload(); sessions.reload() }} />}
    {loading ? <LoadingGrid count={5} /> : <>
      <div className="two-column readiness-grid"><ReadinessCard sport="RUNNING" readiness={running} /><ReadinessCard sport="CLIMBING" readiness={climbing} /></div>
      <section>
        <SectionHeading title="Current fatigue domains" description="Displayed values are capped at 10; the latent state continues above the cap and decays over time." />
        {fatigue.data?.items.length ? <div className="fatigue-grid">{fatigue.data.items.map((item) => <FatigueCard key={item.domain} item={item} />)}</div> : <EmptyState icon="activity" title="No fatigue state yet" message="Log a workout with duration and RPE to calculate domain stress." />}
      </section>
      <div className="analytics-grid">
        <Card title="Recent session load"><BarChart data={loadSeries} label="sRPE load (AU)" /><p className="chart-footnote">Session load = duration in minutes × RPE. AU is useful longitudinally, not an exact physiological measurement.</p></Card>
        <Card title="Interference watch"><InterferenceWatch fatigue={fatigue.data?.items ?? []} readiness={readiness.data?.items ?? []} /></Card>
      </div>
      <Card title="How this model works" subtle><div className="method-grid"><div><strong>1 · Normalise</strong><p>Session stress starts at min(10, sRPE ÷ 90).</p></div><div><strong>2 · Map</strong><p>Session type distributes stress across six configurable domains.</p></div><div><strong>3 · Decay</strong><p>Each domain persists with an exponential half-life.</p></div><div><strong>4 · Interpret</strong><p>Sport-specific fatigue plus modest recovery modifiers produce GOOD / MODERATE / LOW.</p></div></div><InlineNotice>These are configurable planning heuristics, not biological constants or medical measurements.</InlineNotice></Card>
    </>}
    <Modal open={checkInOpen} title="Recovery check-in" onClose={() => setCheckInOpen(false)} wide><RecoveryForm onSaved={() => { setCheckInOpen(false); fatigue.reload(); readiness.reload() }} /></Modal>
  </div>
}

function FatigueCard({ item }: { item: FatigueValue }): React.JSX.Element {
  const meta = domainMeta[item.domain]
  const level = item.display_label ?? 'RECORDED'
  const elevated = item.is_high === true
  return <Card className="fatigue-card"><div className="fatigue-card-top"><span className="domain-icon"><Icon name={item.domain === 'FINGER_FOREARM' || item.domain === 'PULLING_UPPER_BODY' ? 'climb' : item.domain === 'NEURAL' ? 'brain' : 'activity'} /></span><div><strong>{meta.short}</strong><small>{meta.sport}</small></div><Pill tone={elevated ? 'low' : level === 'MODERATE' ? 'moderate' : 'good'}>{formatEnum(level)}</Pill></div><Meter value={item.display_value} tone={elevated ? 'warning' : meta.sport === 'Climbing' ? 'climb' : 'run'} /><p>{meta.description}</p><span className="half-life">Decay half-life: {item.half_life_hours ?? '—'}h</span></Card>
}

function InterferenceWatch({ fatigue, readiness }: { fatigue: FatigueValue[]; readiness: ReadinessSummary[] }): React.JSX.Element {
  const high = fatigue.filter((item) => item.is_high === true)
  const low = readiness.filter((item) => item.label === 'LOW')
  if (!high.length && !low.length) return <div className="all-clear large"><Icon name="check" /><div><strong>No major conflicts detected</strong><p>Current domain fatigue is compatible with normal planning. Still use soreness and session execution as context.</p></div></div>
  return <div className="conflict-list">{high.map((item) => <div key={item.domain}><Icon name="warning" /><div><strong>{formatEnum(item.domain)} is high</strong><p>Avoid stacking another session that heavily stresses this domain.</p></div></div>)}{low.map((item) => <div key={item.sport}><Icon name="warning" /><div><strong>{formatEnum(item.sport)} readiness is low</strong><p>Inspect the next hard or high-priority session before training.</p></div></div>)}</div>
}

import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import { useResource } from '../api/hooks'
import { AdaptationCard, ReadinessCard, RecoveryForm, SessionCard } from '../components/training'
import { Button, Card, EmptyState, ErrorPanel, InlineNotice, LoadingGrid, Modal, PageHeader, Pill, SectionHeading, formatEnum } from '../components/ui'
import { Icon } from '../components/Icon'
import { formatLongDate, localIsoDate } from '../lib/format'

export function TodayPage(): React.JSX.Element {
  const navigate = useNavigate()
  const today = localIsoDate()
  const resource = useResource(() => api.today(today), [today])
  const history = useResource(api.adaptations, [])
  const [recoveryOpen, setRecoveryOpen] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [adapting, setAdapting] = useState(false)
  const [adaptError, setAdaptError] = useState<string | null>(null)
  const dashboard = resource.data

  const propose = async () => {
    setAdapting(true); setAdaptError(null)
    try { await api.proposeAdaptation(); resource.reload(); history.reload() }
    catch (reason) { setAdaptError(reason instanceof ApiError ? reason.message : 'Unable to inspect the upcoming plan.') }
    finally { setAdapting(false) }
  }

  return <div className="page today-page">
    <PageHeader eyebrow="TODAY / COACH" title={formatLongDate(today)} description="Your current plan, readiness and conservative next move." actions={<Button variant="ghost" icon="clock" onClick={() => setHistoryOpen(true)}>Adaptation history</Button>} />

    {!resource.loading && resource.error && <ErrorPanel message={resource.error.message} onRetry={resource.reload} />}

    {resource.loading ? <LoadingGrid count={4} /> : <>
      <section className="coach-strip">
        <div><span>PRIMARY GOAL</span><strong>{dashboard?.goal ? formatEnum(dashboard.goal.goal_type) : 'No current goal'}</strong><small>{dashboard?.goal?.target_value ?? 'Set one clear priority in Settings'}</small></div>
        <div><span>RUNNING PHASE</span><strong>{dashboard ? formatEnum(dashboard.running_phase) : '—'}</strong></div>
        <div><span>CLIMBING PHASE</span><strong>{dashboard ? formatEnum(dashboard.climbing_phase) : '—'}</strong></div>
      </section>

      <div className="two-column readiness-grid">
        <ReadinessCard sport="RUNNING" readiness={dashboard?.running_readiness} />
        <ReadinessCard sport="CLIMBING" readiness={dashboard?.climbing_readiness} />
      </div>

      <section className="quick-actions" aria-label="Quick actions">
        <button onClick={() => navigate('/workouts?action=complete')}><span><Icon name="check" /></span><strong>Complete workout</strong><small>Log planned or extra work</small></button>
        <button onClick={() => navigate('/workouts?action=image')}><span><Icon name="upload" /></span><strong>Import screenshot</strong><small>Extract, review, confirm</small></button>
        <button onClick={() => navigate('/workouts?action=text')}><span><Icon name="bolt" /></span><strong>Quick log</strong><small>Natural-language entry</small></button>
        <button onClick={() => void propose()} disabled={adapting}><span><Icon name="brain" /></span><strong>{adapting ? 'Inspecting plan…' : 'Adapt plan'}</strong><small>Review the next seven days</small></button>
        <button onClick={() => setRecoveryOpen(true)}><span><Icon name="heart" /></span><strong>Recovery check-in</strong><small>Optional, takes one minute</small></button>
      </section>
      {adaptError && <InlineNotice tone="warning" title="Plan inspection unavailable">{adaptError} The deterministic schedule remains unchanged.</InlineNotice>}

      <div className="today-content-grid">
        <Card className="schedule-card">
          <SectionHeading title="Today's planned sessions" description="Original plan and completed work remain distinct." action={<Button variant="ghost" icon="plus" onClick={() => navigate('/calendar?action=new')}>Plan session</Button>} />
          <div className="session-list">{dashboard?.sessions.length ? dashboard.sessions.map((entry) => <SessionCard key={entry.id} entry={entry} onComplete={(id) => navigate(`/workouts?action=complete&planned_session_id=${encodeURIComponent(String(id))}`)} />) : <EmptyState icon="calendar" title="Nothing planned today" message="Rest is valid. Add a session only if it supports the current plan." />}</div>
        </Card>
        <div className="side-stack">
          <Card title="Fatigue watch">
            {dashboard?.fatigue_warnings.length ? <ul className="warning-list">{dashboard.fatigue_warnings.map((warning) => <li key={warning}><Icon name="warning" size={17} /><span>{warning}</span></li>)}</ul> : <div className="all-clear"><Icon name="check" /><div><strong>No current conflicts</strong><p>Recent load does not conflict with today's plan.</p></div></div>}
          </Card>
          <Card title="Planning principle" subtle><p className="quote">“Progress one primary variable at a time, and only after repeated evidence.”</p><p className="muted">Training notes never modify your plan unless you explicitly approve them for coaching.</p></Card>
        </div>
      </div>

      <section className="proposal-section">
        <SectionHeading title="Adaptation proposals" description="Nothing changes until you apply a visible diff." />
        {dashboard?.pending_adaptations.length ? <div className="proposal-grid">{dashboard.pending_adaptations.map((proposal) => <AdaptationCard key={proposal.id} proposal={proposal} onChanged={resource.reload} />)}</div> : <EmptyState icon="target" title="No pending changes" message="The current plan is being kept. Complete a workout or inspect the next seven days to generate a proposal." />}
      </section>
    </>}

    <Modal open={recoveryOpen} title="Recovery check-in" onClose={() => setRecoveryOpen(false)} wide><RecoveryForm onSaved={() => { setRecoveryOpen(false); resource.reload() }} /></Modal>
    <Modal open={historyOpen} title="Adaptation history" onClose={() => setHistoryOpen(false)} wide>
      {history.loading ? <LoadingGrid /> : history.error ? <ErrorPanel message={history.error.message} onRetry={history.reload} /> : history.data?.items.length ? <div className="history-list">{history.data.items.map((item) => <article key={item.id}><div><Pill tone={item.status === 'ACCEPTED' ? 'good' : item.status === 'REJECTED' ? 'low' : 'neutral'}>{item.status ?? 'PENDING'}</Pill><strong>{item.session_title}</strong></div><span>{formatEnum(item.action)} · {item.source} · {item.created_at?.slice(0, 10) ?? ''}</span><p>{item.reason}</p></article>)}</div> : <EmptyState title="No adaptations recorded" message="Every proposed, accepted and rejected plan change will appear here." />}
    </Modal>
  </div>
}

import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { useResource } from '../api/hooks'
import { Button, Card, EmptyState, ErrorPanel, LoadingGrid, Modal, PageHeader, Pill, formatEnum } from '../components/ui'
import { formatDuration, formatLongDate, formatNumber, formatPace, formatRaceTime, localIsoDate, recordLabel } from '../lib/format'
import type { CalendarEntry, CompletedSession, ImportedRunningActivity, PlannedSession } from '../types'
import { StravaRunReview } from './WorkoutLogPage'

interface TodayRow {
  id: string
  plan?: PlannedSession | null
  completed?: CompletedSession | null
  imported?: ImportedRunningActivity | null
  unplanned: boolean
}

const activePlanStatuses = new Set(['PLANNED', 'MODIFIED', 'COMPLETED'])

export function TodayPage(): React.JSX.Element {
  const navigate = useNavigate()
  const today = localIsoDate()
  const resource = useResource(() => api.today(today), [today])
  const [reviewing, setReviewing] = useState<ImportedRunningActivity | null>(null)
  const rows = useMemo(() => buildTodayRows(resource.data?.sessions ?? [], resource.data?.imported_runs ?? []), [resource.data])
  const hasPlan = rows.some((row) => row.plan)

  const reviewed = () => {
    setReviewing(null)
    resource.reload()
  }

  return <div className="page todays-training-page">
    <PageHeader eyebrow="HOME" title="Today's Training" description={formatLongDate(today)} />
    {resource.loading ? <LoadingGrid count={2} /> : resource.error ? <ErrorPanel message={resource.error.message} onRetry={resource.reload} /> : <>
      {!hasPlan && <Card className="rest-day-card"><span className="eyebrow">REST DAY</span><h2>No planned training today.</h2>{rows.length ? <p>An unplanned activity is shown below.</p> : <p>Recover, or use Workout Log if you complete something unplanned.</p>}</Card>}
      {rows.length ? <div className="today-session-stack">{rows.map((row, index) => <section className="today-session" key={row.id}>
        {rows.length > 1 && <h2>Session {index + 1}</h2>}
        <div className="today-plan-result-grid">
          <TodayPlan plan={row.plan} onOpen={(id) => navigate(`/calendar?session_id=${encodeURIComponent(String(id))}`)} />
          <TodayResult completed={row.completed} imported={row.imported} unplanned={row.unplanned} onReview={setReviewing} onOpen={(id) => navigate(`/workouts?session_id=${encodeURIComponent(String(id))}`)} />
        </div>
        {row.plan && row.completed && <PlanActualComparison plan={row.plan} completed={row.completed} />}
      </section>)}</div> : hasPlan ? null : <EmptyState title="No training activity yet" message="Today's completed work or imported Strava activity will appear here automatically." />}
    </>}
    <Modal open={Boolean(reviewing)} title="Post-Run Review" onClose={() => setReviewing(null)} wide>{reviewing && <StravaRunReview run={reviewing} onSaved={reviewed} />}</Modal>
  </div>
}

function buildTodayRows(entries: CalendarEntry[], importedRuns: ImportedRunningActivity[]): TodayRow[] {
  const activeEntries = entries.filter((entry) => !entry.planned || activePlanStatuses.has(entry.status))
  const linkedImports = new Set<number>()
  const rows = activeEntries.map((entry): TodayRow => {
    const imported = entry.planned && !entry.completed
      ? importedRuns.find((run) => String(run.planned_session?.id) === String(entry.planned?.id)) ?? null
      : null
    if (imported) linkedImports.add(imported.id)
    return {
      id: entry.id,
      plan: entry.planned,
      completed: entry.completed,
      imported,
      unplanned: !entry.planned,
    }
  })
  for (const run of importedRuns) {
    if (linkedImports.has(run.id)) continue
    rows.push({ id: `imported-${run.id}`, imported: run, unplanned: true })
  }
  return rows
}

function TodayPlan({ plan, onOpen }: { plan?: PlannedSession | null; onOpen: (id: PlannedSession['id']) => void }): React.JSX.Element {
  if (!plan) return <Card className="today-half-card today-plan-card"><div className="today-card-heading"><span>TODAY'S PLAN</span><Pill>—</Pill></div><div className="today-empty-result"><strong>No planned session</strong><p>This activity was not linked to a Calendar plan.</p></div></Card>
  const blocks = plan.structured_blocks ?? []
  return <Card className="today-half-card today-plan-card">
    <div className="today-card-heading"><span>TODAY'S PLAN</span><Pill>PLANNED</Pill></div>
    <div className="today-session-heading"><span>{formatEnum(plan.session_type)}</span><h2>{plan.title}</h2></div>
    <div className="today-key-metrics">
      {plan.planned_distance_km != null && <Metric label="Distance" value={`${formatNumber(plan.planned_distance_km, 1)} km`} />}
      {plan.planned_duration_minutes != null && <Metric label="Duration" value={formatDuration(plan.planned_duration_minutes)} />}
      {plan.target_rpe != null && <Metric label="Target RPE" value={String(plan.target_rpe)} />}
    </div>
    {blocks.length ? <div className="today-prescription">{blocks.map((block, index) => <div key={index}><strong>{blockHeading(block)}</strong><p>{blockSummary(block)}</p></div>)}</div> : null}
    {plan.description && <div className="today-notes"><strong>{blocks.length ? 'Notes' : 'Workout'}</strong><p>{plan.description}</p></div>}
    <Button variant="ghost" onClick={() => onOpen(plan.id)}>View Full Session</Button>
  </Card>
}

function TodayResult({ completed, imported, unplanned, onReview, onOpen }: { completed?: CompletedSession | null; imported?: ImportedRunningActivity | null; unplanned: boolean; onReview: (run: ImportedRunningActivity) => void; onOpen: (id: CompletedSession['id']) => void }): React.JSX.Element {
  if (imported) return <Card className="today-half-card today-result-card needs-review">
    <div className="today-card-heading"><span>TODAY'S RESULT</span><Pill tone="moderate">NEEDS REVIEW</Pill></div>
    {unplanned && <span className="unplanned-label">UNPLANNED SESSION</span>}
    <div className="today-session-heading"><span>ACTIVITY IMPORTED</span><h2>{imported.title}</h2></div>
    <div className="today-key-metrics four"><Metric label="Distance" value={`${formatNumber(imported.distance_km, 2)} km`} /><Metric label="Elapsed" value={formatRaceTime(imported.elapsed_time_seconds)} /><Metric label="Avg pace" value={`${formatPace(imported.average_pace_seconds_per_km)}/km`} /><Metric label="Avg HR" value={imported.average_hr != null ? String(imported.average_hr) : '—'} /></div>
    <Button onClick={() => onReview(imported)}>Complete Review</Button>
  </Card>
  if (!completed) return <Card className="today-half-card today-result-card"><div className="today-card-heading"><span>TODAY'S RESULT</span><Pill>PLANNED</Pill></div><div className="today-empty-result"><strong>Not completed yet</strong><p>Completed or imported training will appear here.</p></div></Card>

  const isRunning = completed.workout_kind === 'RUNNING'
  const isClimbing = completed.workout_kind === 'CLIMBING'
  const laps = isRunning && completed.session_type === 'QUALITY' ? usefulLaps(completed.splits ?? []) : []
  return <Card className="today-half-card today-result-card completed">
    <div className="today-card-heading"><span>TODAY'S RESULT</span><Pill tone="good">COMPLETED ✓</Pill></div>
    {unplanned && <span className="unplanned-label">UNPLANNED SESSION</span>}
    <div className="today-session-heading"><span>{formatEnum(completed.session_type)}</span><h2>{completed.title ?? formatEnum(completed.session_type)}</h2></div>
    <div className="today-key-metrics four">
      {completed.distance_km != null && <Metric label="Distance" value={`${formatNumber(completed.distance_km, 2)} km`} />}
      <Metric label="Duration" value={formatDuration(completed.duration_minutes)} />
      {completed.average_pace_seconds_per_km != null && <Metric label="Avg pace" value={`${formatPace(completed.average_pace_seconds_per_km)}/km`} />}
      {completed.average_hr != null && <Metric label="Avg HR" value={String(completed.average_hr)} />}
      {completed.max_hr != null && <Metric label="Max HR" value={String(completed.max_hr)} />}
      {completed.rpe != null && <Metric label="RPE" value={String(completed.rpe)} />}
      {isClimbing && completed.board_name && <Metric label="Board" value={`${completed.board_name}${completed.angle != null ? ` · ${completed.angle}°` : ''}`} />}
    </div>
    {laps.length ? <div className="today-main-set"><strong>MAIN SET</strong>{laps.map((lap, index) => <div key={index}><span>{lap.distance}</span><b>{lap.time}</b></div>)}</div> : null}
    {isClimbing && completed.climbing_attempts?.length ? <div className="today-attempts"><strong>PERFORMANCE</strong>{summarizeAttempts(completed.climbing_attempts).map((summary) => <p key={summary}>{summary}</p>)}</div> : null}
    {completed.subjective_feedback_text && <div className="today-subjective"><strong>SUBJECTIVE</strong><p>{completed.subjective_feedback_text}</p></div>}
    <Button variant="ghost" onClick={() => onOpen(completed.id)}>View Full Result</Button>
  </Card>
}

function PlanActualComparison({ plan, completed }: { plan: PlannedSession; completed: CompletedSession }): React.JSX.Element | null {
  const rows: Array<[string, string, string]> = []
  const main = primaryBlock(plan.structured_blocks ?? [])
  if (main) rows.push(['Main set', main, completed.splits?.length ? `${completed.splits.length} recorded lap${completed.splits.length === 1 ? '' : 's'}` : completed.interval_blocks?.length ? `${completed.interval_blocks.length} recorded block${completed.interval_blocks.length === 1 ? '' : 's'}` : 'Not recorded'])
  if (plan.planned_distance_km != null && completed.distance_km != null) rows.push(['Distance', `${formatNumber(plan.planned_distance_km, 1)} km`, `${formatNumber(completed.distance_km, 2)} km`])
  const targetPace = plannedPace(plan.structured_blocks ?? [])
  if (targetPace && completed.average_pace_seconds_per_km != null) rows.push(['Pace', targetPace, `${formatPace(completed.average_pace_seconds_per_km)}/km avg`])
  if (plan.target_rpe != null && completed.rpe != null) rows.push(['RPE', `${plan.target_rpe} target`, String(completed.rpe)])
  if (!rows.length) return null
  return <Card className="today-comparison" title="Planned vs actual"><div className="comparison-table"><div className="comparison-row comparison-head"><span /><span>Planned</span><span>Actual</span></div>{rows.map(([label, planned, actual]) => <div className="comparison-row" key={label}><strong>{label}</strong><span>{planned}</span><span>{actual}</span></div>)}</div><p className="chart-footnote">Factual comparison only—no performance score or fatigue interpretation.</p></Card>
}

function Metric({ label, value }: { label: string; value: string }): React.JSX.Element {
  return <div><span>{label}</span><strong>{value}</strong></div>
}

function blockHeading(block: Record<string, unknown>): string {
  return formatEnum(String(block.phase ?? block.label ?? block.segment_kind ?? block.exercise ?? 'Session detail'))
}

function blockSummary(block: Record<string, unknown>): string {
  const text = block.raw_text ?? block.raw_workout_text ?? block.description ?? block.detail ?? block.notes
  if (typeof text === 'string' && text.trim()) return text
  return recordLabel(block)
}

function primaryBlock(blocks: Array<Record<string, unknown>>): string | null {
  const block = blocks.find((item) => /main|quality|interval|threshold/i.test(String(item.phase ?? item.label ?? item.segment_kind ?? ''))) ?? blocks[0]
  return block ? blockSummary(block) : null
}

function plannedPace(blocks: Array<Record<string, unknown>>): string | null {
  for (const block of blocks) {
    const low = block.target_pace_min ?? block.target_pace_min_seconds_per_km
    const high = block.target_pace_max ?? block.target_pace_max_seconds_per_km
    const format = (value: unknown) => typeof value === 'number' ? formatPace(value) : typeof value === 'string' ? value.replace(/\/km$/i, '') : null
    const left = format(low)
    const right = format(high)
    if (left) return `${left}${right && right !== left ? `–${right}` : ''}/km`
  }
  return null
}

function usefulLaps(rows: Array<Record<string, unknown>>): Array<{ distance: string; time: string }> {
  return rows.flatMap((row) => {
    const distance = typeof row.distance_km === 'number' ? `${formatNumber(row.distance_km, 2)} km` : null
    const time = typeof row.elapsed_time_seconds === 'number' ? formatRaceTime(row.elapsed_time_seconds) : typeof row.pace_seconds_per_km === 'number' ? `${formatPace(row.pace_seconds_per_km)}/km` : null
    return distance && time ? [{ distance, time }] : []
  }).slice(0, 12)
}

function summarizeAttempts(rows: Array<Record<string, unknown>>): string[] {
  const grouped = new Map<string, { attempts: number; sends: number }>()
  const unstructured: string[] = []
  for (const row of rows) {
    const grade = String(row.grade ?? row.grade_or_colour ?? row.colour ?? '').trim()
    if (!grade) { unstructured.push(recordLabel(row)); continue }
    const current = grouped.get(grade) ?? { attempts: 0, sends: 0 }
    current.attempts += numericValue(row.attempts ?? row.attempt_count) ?? 1
    const explicitSends = numericValue(row.sends ?? row.send_count)
    current.sends += explicitSends ?? (row.sent === true || String(row.result ?? '').toUpperCase() === 'SEND' ? 1 : 0)
    grouped.set(grade, current)
  }
  return [...grouped.entries()].map(([grade, values]) => `${grade} · ${values.attempts} attempts · ${values.sends} sends`).concat(unstructured)
}

function numericValue(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim() && Number.isFinite(Number(value))) return Number(value)
  return null
}

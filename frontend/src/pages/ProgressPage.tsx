import { useState } from 'react'
import { api } from '../api/client'
import { useResource } from '../api/hooks'
import { BarChart, GradePyramid, LineChart } from '../components/charts'
import { Button, Card, EmptyState, ErrorPanel, InlineNotice, LoadingGrid, Metric, PageHeader, SectionHeading, Tabs } from '../components/ui'
import { formatDate, formatDuration, formatPace } from '../lib/format'
import type { GymSet, ProgressData } from '../types'

const fontGrades = ['5', '5+', '6A', '6A+', '6B', '6B+', '6C', '6C+', '7A', '7A+', '7B', '7B+', '7C', '7C+', '8A', '8A+', '8B']
const vGrades = ['V0', 'V1', 'V2', 'V3', 'V4', 'V5', 'V6', 'V7', 'V8', 'V9', 'V10', 'V11', 'V12']
const colours: Record<string, string> = { Yellow: '#e8cf4a', Green: '#48b87b', Purple: '#9c78e8', Grey: '#83909f', Blue: '#4f91ee', Red: '#e15e64', Black: '#323946' }

export function ProgressPage(): React.JSX.Element {
  const [sport, setSport] = useState<'running' | 'climbing'>('running')
  const [range, setRange] = useState<'4w' | '3m' | '6m' | '1y'>('3m')
  const resource = useResource(() => api.progress(range), [range])
  return <div className="page progress-page">
    <PageHeader eyebrow="LONGITUDINAL ANALYSIS" title="Progress" description="Retrospective trends only. This page never changes upcoming training." actions={<div className="range-picker" aria-label="Time range">{(['4w', '3m', '6m', '1y'] as const).map((item) => <Button key={item} variant={range === item ? 'primary' : 'ghost'} onClick={() => setRange(item)}>{item === '4w' ? '4 weeks' : item === '3m' ? '3 months' : item === '6m' ? '6 months' : '1 year'}</Button>)}</div>} />
    <Tabs label="Progress sport" value={sport} onChange={setSport} items={[{ value: 'running', label: 'Running' }, { value: 'climbing', label: 'Climbing' }]} />
    {resource.loading ? <LoadingGrid count={4} /> : resource.error ? <ErrorPanel message={resource.error.message} onRetry={resource.reload} /> : resource.data ? sport === 'running' ? <RunningProgress data={resource.data.running} /> : <ClimbingProgress data={resource.data.climbing} /> : <EmptyState title="No progress data" message="Verified sessions and benchmarks will appear here." />}
  </div>
}

function RunningProgress({ data }: { data: ProgressData['running'] }): React.JSX.Element {
  return <div className="chart-grid">
    <Card title="Running frequency"><Metric label="Runs in selected period" value={data.run_frequency} /></Card>
    <Card title="Sessions by type"><BarChart data={data.sessions_by_type.map((item) => ({ date: item.label, value: item.value, label: item.label }))} label="Session count" /></Card>
    <Card title="Weekly mileage"><BarChart data={data.weekly_mileage} label="7-day distance" formatValue={(value) => `${value.toFixed(1)} km`} /></Card>
    <Card title="Monthly mileage"><BarChart data={data.monthly_mileage} label="Calendar-month distance" formatValue={(value) => `${value.toFixed(1)} km`} /><p className="chart-footnote">Calendar months are not mixed with rolling windows.</p></Card>
    <Card title="Rolling volume"><LineChart data={data.rolling_volume} label="7-day mileage" secondaryLabel="28-day weekly average" formatValue={(value) => `${value.toFixed(1)} km`} /></Card>
    <EasyRunningEfficiency data={data.easy_efficiency} band={data.easy_efficiency_band} warning={data.easy_efficiency_warning} />
  </div>
}

function EasyRunningEfficiency({ data, band, warning }: { data: ProgressData['running']['easy_efficiency']; band?: string | null; warning?: string | null }): React.JSX.Element {
  const chronological = [...data].sort((left, right) => left.date.localeCompare(right.date))
  const pace = chronological.map((point) => ({ ...point, secondary: null }))
  return <Card className="wide-chart" title="Easy running efficiency">
    <div className="metric-grid two"><Metric label="Comparison heart-rate band" value={band ?? 'Not enough data'} /><Metric label="Pace interpretation" value="Lower min/km = faster" /></div>
    <LineChart data={pace} label="Average pace at comparable easy HR" formatValue={(value) => `${formatPace(value)}/km`} formatYAxisValue={(value) => formatPace(value)} reverseY />
    {chronological.length ? <div className="performance-table"><div className="performance-row performance-head"><span>Date</span><span>Average pace</span><span>Average heart rate</span><span>Source</span></div>{chronological.map((point) => <div className="performance-row" key={point.date}><span>{formatDate(point.date)}</span><strong>{formatPace(point.value)}/km</strong><span>{point.secondary != null ? `${Math.round(point.secondary)} bpm` : '—'}</span><span>{point.label ?? 'Workout Log'}</span></div>)}</div> : null}
    {warning && <InlineNotice tone="warning">{warning}</InlineNotice>}
  </Card>
}

function ClimbingProgress({ data }: { data: ProgressData['climbing'] }): React.JSX.Element {
  return <div className="progress-stack">
    <div className="metric-grid three"><Metric label="Climbing sessions" value={data.session_count} /><Metric label="Total duration" value={formatDuration(data.total_duration_minutes)} /><Metric label="Session types recorded" value={data.sessions_by_type.filter((item) => item.value > 0).length} /></div>
    <div className="chart-grid"><Card title="Weekly climbing frequency"><BarChart data={data.weekly_sessions} label="Sessions per week" /></Card><Card title="Monthly climbing frequency"><BarChart data={data.monthly_sessions} label="Sessions per month" /></Card><Card title="Sessions by type"><BarChart data={data.sessions_by_type.map((item) => ({ date: item.label, value: item.value, label: item.label }))} label="Sessions" /></Card><Card title="Grade / colour attempts"><BarChart data={data.grade_attempts.map((item) => ({ date: item.label, value: item.value, label: item.label }))} label="Attempts" /></Card><Card title="Grade / colour sends"><BarChart data={data.grade_sends.map((item) => ({ date: item.label, value: item.value, label: item.label }))} label="Sends" /></Card></div>
    <Card title="Tension Board 2 benchmarks"><TB2AngleCharts benchmarks={data.tb2_benchmarks} />{data.tb2_benchmarks.length ? <div className="benchmark-table"><div className="table-row table-head"><span>Date</span><span>Angle</span><span>Verified</span><span>Estimated</span></div>{data.tb2_benchmarks.map((item) => <div className="table-row" key={item.id}><span>{formatDate(item.date)}{item.is_demo ? ' · DEMO' : ''}</span><span>{item.angle}°</span><strong>{item.verified_grade}</strong><span>{item.estimated_grade ?? '—'}</span></div>)}</div> : null}<InlineNotice>Board angles and grade systems are charted separately. Ordinals only place labels in order; spacing does not imply linear physiological improvement.</InlineNotice></Card>
    <section><SectionHeading title="Home-gym set comparison" description="Grade pyramids preserve the distribution instead of collapsing climbing into one score." />{data.gym_sets.length ? <GymSetComparison sets={data.gym_sets} /> : <EmptyState title="No completed gym sets" message="Set comparisons appear after a reset has preserved historical colour progress." />}</section>
  </div>
}

function TB2AngleCharts({ benchmarks }: { benchmarks: ProgressData['climbing']['tb2_benchmarks'] }): React.JSX.Element {
  const groups = new Map<string, typeof benchmarks>()
  for (const benchmark of benchmarks) {
    const scale = benchmark.verified_grade.toUpperCase().startsWith('V') ? 'V scale' : 'Font'
    const key = `${benchmark.angle}° · ${scale}`
    groups.set(key, [...(groups.get(key) ?? []), benchmark])
  }
  if (!groups.size) return <EmptyState title="No verified TB2 benchmarks" message="Record benchmark date, angle and verified grade to begin the chart." />
  return <div className="tb2-angle-grid">{[...groups.entries()].map(([label, rows]) => {
    const scale = label.endsWith('V scale') ? vGrades : fontGrades
    const points = rows.sort((a, b) => a.date.localeCompare(b.date)).flatMap((benchmark) => {
      const verified = benchmark.verified_grade.toUpperCase()
      const estimated = benchmark.estimated_grade?.toUpperCase()
      const verifiedIndex = scale.indexOf(verified)
      if (verifiedIndex < 0) return []
      return [{ date: benchmark.date, value: verifiedIndex, secondary: estimated && scale.includes(estimated) ? scale.indexOf(estimated) : null, label: benchmark.verified_grade }]
    })
    if (!points.length) return <section key={label}><h3>{label}</h3><InlineNotice tone="warning">No grades in this group match the supported chart scale; the raw benchmark remains in the table below.</InlineNotice></section>
    const gradeValues = points.flatMap((point) => point.secondary == null ? [point.value] : [point.value, point.secondary])
    const lowest = Math.min(...gradeValues)
    const highest = Math.max(...gradeValues)
    const domain: [number, number] = lowest === highest
      ? [Math.max(0, lowest - 1), Math.min(scale.length - 1, highest + 1)]
      : [lowest, highest]
    const step = Math.max(1, Math.ceil((domain[1] - domain[0]) / 5))
    const gradeTicks = Array.from({ length: Math.floor((domain[1] - domain[0]) / step) + 1 }, (_, index) => domain[0] + index * step)
    if (gradeTicks.at(-1) !== domain[1]) gradeTicks.push(domain[1])
    const gradeLabel = (value: number) => scale[Math.round(value)] ?? '—'
    return <section key={label}><h3>{label}</h3><LineChart data={points} label="Verified grade" secondaryLabel="Estimated grade" formatValue={gradeLabel} yDomain={domain} yTicks={gradeTicks} formatYAxisValue={gradeLabel} /></section>
  })}</div>
}

function GymSetComparison({ sets }: { sets: GymSet[] }): React.JSX.Element {
  const [mode, setMode] = useState<'absolute' | 'percent'>('absolute')
  return <><div className="mode-toggle"><Button variant={mode === 'absolute' ? 'primary' : 'ghost'} onClick={() => setMode('absolute')}>Absolute sends</Button><Button variant={mode === 'percent' ? 'primary' : 'ghost'} onClick={() => setMode('percent')}>Completion %</Button></div><div className="gym-comparison-grid">{sets.map((set) => <Card key={set.id} title={`${set.gym} · ${formatDate(set.start_date, { month: 'short', year: 'numeric' })}${set.is_demo ? ' · DEMO' : ''}`}><GradePyramid mode={mode} rows={set.progress.map((row) => ({ label: row.colour, value: row.sent_count, available: row.available_problem_count, colour: colours[row.colour] }))} />{mode === 'percent' && !set.progress.some((row) => row.available_problem_count) && <p className="chart-footnote">Available counts were not recorded for this set.</p>}</Card>)}</div></>
}

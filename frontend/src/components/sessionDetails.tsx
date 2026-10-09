import { formatPace, formatNumber, formatRaceTime, parseDurationInput } from '../lib/format'
import { Card, formatEnum } from './ui'

export function CompletedLapTable({ records }: { records?: Array<Record<string, unknown>> }): React.JSX.Element | null {
  if (!records?.length) return null
  return <Card title="Lap details"><div className="lap-table completed-lap-table">
    <div className="lap-row completed-lap-row lap-head"><span>Lap</span><span>Distance</span><span>Elapsed</span><span>Pace</span><span>Avg HR</span><span>Cadence</span></div>
    {records.map((record, index) => {
      const distance = numberFrom(record.distance_km ?? record.distance)
      const elapsedSeconds = numberFrom(record.elapsed_time_seconds)
      const elapsedText = elapsedSeconds != null ? formatRaceTime(elapsedSeconds) : stringFrom(record.time ?? record.elapsed_time)
      const explicitPace = numberFrom(record.pace_seconds_per_km)
      const calculatedPace = explicitPace ?? (distance && elapsedText ? durationTextSeconds(elapsedText) / distance : null)
      const paceText = calculatedPace != null && Number.isFinite(calculatedPace) ? `${formatPace(calculatedPace)} /km` : paceString(record.pace)
      const heartRate = numberFrom(record.average_hr ?? record.hr)
      const cadence = numberFrom(record.cadence)
      return <div className="lap-row completed-lap-row" key={`${String(record.lap_index ?? index + 1)}-${index}`}>
        <span data-label="Lap">{String(record.lap_index ?? index + 1)}</span>
        <span data-label="Distance">{distance != null ? `${formatNumber(distance, 2)} km` : '—'}</span>
        <span data-label="Elapsed">{elapsedText || '—'}</span>
        <span data-label="Pace">{paceText || '—'}</span>
        <span data-label="Avg HR">{heartRate != null ? `${formatNumber(heartRate)} bpm` : '—'}</span>
        <span data-label="Cadence">{cadence != null ? `${formatNumber(cadence)} spm` : '—'}</span>
      </div>
    })}
  </div></Card>
}

export function ClimbingAttemptTable({ records }: { records?: Array<Record<string, unknown>> }): React.JSX.Element | null {
  if (!records?.length) return null
  return <Card title="Climbing attempts"><div className="attempt-table">
    <div className="attempt-row attempt-head"><span>Problem</span><span>Grade</span><span>Attempts</span><span>Sends</span><span>Result</span><span>Styles</span></div>
    {records.map((record, index) => {
      const sent = record.sent === true
      const sends = numberFrom(record.send_count ?? record.sends) ?? (sent ? 1 : 0)
      const styles = Array.isArray(record.style_tags ?? record.styles) ? (record.style_tags ?? record.styles) as unknown[] : []
      const result = stringFrom(record.outcome) || (record.flash === true ? 'Flash' : record.repeat === true ? 'Repeat' : record.project === true ? 'Project' : sent || sends > 0 ? 'Sent' : 'Not sent')
      return <div className="attempt-row" key={`${String(record.id ?? record.problem ?? index)}-${index}`}>
        <span data-label="Problem">{stringFrom(record.problem) || `Problem ${index + 1}`}</span>
        <span data-label="Grade">{stringFrom(record.grade ?? record.grade_or_colour ?? record.colour) || '—'}</span>
        <span data-label="Attempts">{numberFrom(record.attempts ?? record.attempt_count) ?? '—'}</span>
        <span data-label="Sends">{sends}</span>
        <span data-label="Result">{formatEnum(result)}</span>
        <span data-label="Styles">{styles.length ? styles.map(String).join(', ') : '—'}</span>
      </div>
    })}
  </div></Card>
}

function numberFrom(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim() && Number.isFinite(Number(value))) return Number(value)
  return null
}

function stringFrom(value: unknown): string {
  return typeof value === 'string' ? value.trim() : ''
}

function durationTextSeconds(value: string): number {
  return (parseDurationInput(value) ?? Number.NaN) * 60
}

function paceString(value: unknown): string {
  if (typeof value === 'number' && Number.isFinite(value)) return `${formatPace(value)} /km`
  const text = stringFrom(value)
  if (!text) return ''
  return /\/km$/i.test(text) ? text.replace(/\/km$/i, ' /km') : `${text} /km`
}

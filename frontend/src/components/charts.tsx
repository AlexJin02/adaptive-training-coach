import { useId } from 'react'
import type { SeriesPoint } from '../types'
import { formatDate, formatNumber } from '../lib/format'

const WIDTH = 720
const HEIGHT = 250
const PAD = { left: 46, right: 18, top: 20, bottom: 38 }

function extent(values: number[]): [number, number] {
  if (!values.length) return [0, 1]
  const min = Math.min(...values)
  const max = Math.max(...values)
  if (min === max) return [Math.max(0, min - 1), max + 1]
  const margin = (max - min) * 0.12
  return [Math.max(0, min - margin), max + margin]
}

function xAt(index: number, length: number): number {
  return PAD.left + (length <= 1 ? 0 : index / (length - 1)) * (WIDTH - PAD.left - PAD.right)
}

function yAt(value: number, min: number, max: number, reverse = false): number {
  const ratio = reverse ? (value - min) / (max - min) : (max - value) / (max - min)
  return PAD.top + ratio * (HEIGHT - PAD.top - PAD.bottom)
}

function Axis({ min, max, data, yTicks, formatYValue = (value) => formatNumber(value, max < 20 ? 1 : 0), reverseY = false }: { min: number; max: number; data: SeriesPoint[]; yTicks?: number[]; formatYValue?: (value: number) => string; reverseY?: boolean }): React.JSX.Element {
  const ticks = yTicks ?? [max, max - (max - min) * .25, max - (max - min) * .5, max - (max - min) * .75, min]
  return <g className="chart-axis">
    {ticks.map((value) => {
      const y = yAt(value, min, max, reverseY)
      return <g key={value}><line x1={PAD.left} y1={y} x2={WIDTH - PAD.right} y2={y} /><text x={PAD.left - 8} y={y + 4} textAnchor="end">{formatYValue(value)}</text></g>
    })}
    {data.map((point, index) => {
      if (index !== 0 && index !== data.length - 1 && index % Math.ceil(data.length / 5) !== 0) return null
      return <text key={`${point.date}-${index}`} x={xAt(index, data.length)} y={HEIGHT - 11} textAnchor={index === 0 ? 'start' : index === data.length - 1 ? 'end' : 'middle'}>{formatDate(point.date, { month: 'short', day: 'numeric' })}</text>
    })}
  </g>
}

export function LineChart({ data, label, secondaryLabel, formatValue = (value) => formatNumber(value, 1), yDomain, yTicks, formatYAxisValue, reverseY = false }: { data: SeriesPoint[]; label: string; secondaryLabel?: string; formatValue?: (value: number) => string; yDomain?: [number, number]; yTicks?: number[]; formatYAxisValue?: (value: number) => string; reverseY?: boolean }): React.JSX.Element {
  const id = useId().replaceAll(':', '')
  if (!data.length) return <ChartEmpty />
  const values = data.flatMap((point) => point.secondary == null ? [point.value] : [point.value, point.secondary])
  const [min, max] = yDomain ?? extent(values)
  const primary = data.map((point, index) => `${xAt(index, data.length)},${yAt(point.value, min, max, reverseY)}`).join(' ')
  const secondaryPoints = data.filter((point) => point.secondary != null)
  const secondary = secondaryPoints.map((point) => `${xAt(data.indexOf(point), data.length)},${yAt(point.secondary ?? 0, min, max, reverseY)}`).join(' ')
  return <div className="chart-wrap">
    <div className="chart-legend"><span><i className="legend-primary" />{label}</span>{secondaryLabel && <span><i className="legend-secondary" />{secondaryLabel}</span>}</div>
    <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label={`${label} over time`}>
      <defs><linearGradient id={`area-${id}`} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="var(--accent)" stopOpacity=".25"/><stop offset="1" stopColor="var(--accent)" stopOpacity="0"/></linearGradient></defs>
      <Axis min={min} max={max} data={data} yTicks={yTicks} formatYValue={formatYAxisValue} reverseY={reverseY} />
      <polyline points={primary} className="chart-line chart-primary" />
      {secondary && <polyline points={secondary} className="chart-line chart-secondary" />}
      {data.map((point, index) => {
        const x = xAt(index, data.length)
        const primaryY = yAt(point.value, min, max, reverseY)
        const secondaryY = point.secondary == null ? null : yAt(point.secondary, min, max, reverseY)
        const description = `${formatDate(point.date)} · ${label}: ${formatValue(point.value)}${point.secondary != null ? ` · ${secondaryLabel}: ${formatValue(point.secondary)}` : ''}${point.confidence ? ` · ${point.confidence} confidence` : ''}`
        return <g key={`${point.date}-${index}`} className="chart-point chart-hover-target" tabIndex={0} aria-label={description}>
          <circle className="chart-hit-area" cx={x} cy={primaryY} r="14" />
          <circle cx={x} cy={primaryY} r="4"><title>{description}</title></circle>
          <text className="chart-hover-value" x={x} y={Math.max(PAD.top + 11, primaryY - 10)} textAnchor="middle">{formatValue(point.value)}</text>
          {secondaryY != null && <><circle className="secondary-point" cx={x} cy={secondaryY} r="3" /><text className="chart-hover-value chart-hover-secondary" x={x} y={Math.min(HEIGHT - PAD.bottom - 5, secondaryY + 16)} textAnchor="middle">{formatValue(point.secondary ?? 0)}</text></>}
        </g>
      })}
    </svg>
  </div>
}

export function BarChart({ data, label, formatValue = (value) => formatNumber(value, 1) }: { data: SeriesPoint[]; label: string; formatValue?: (value: number) => string }): React.JSX.Element {
  if (!data.length) return <ChartEmpty />
  const max = Math.max(...data.map((point) => point.value), 1)
  const innerWidth = WIDTH - PAD.left - PAD.right
  const slot = innerWidth / data.length
  const barWidth = Math.min(60, slot * 0.65)
  return <div className="chart-wrap"><div className="chart-legend"><span><i className="legend-primary" />{label}</span></div><svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label={`${label} bar chart`}>
    <Axis min={0} max={max} data={data} />
    {data.map((point, index) => {
      const height = (point.value / max) * (HEIGHT - PAD.top - PAD.bottom)
      const x = PAD.left + slot * index + (slot - barWidth) / 2
      const y = HEIGHT - PAD.bottom - height
      const description = `${formatDate(point.date)} · ${formatValue(point.value)}`
      return <g key={`${point.date}-${index}`} className="chart-bar-point chart-hover-target" tabIndex={0} aria-label={description}><rect className="chart-bar" x={x} y={y} width={barWidth} height={height} rx="4"><title>{description}</title></rect><text className="chart-hover-value" x={x + barWidth / 2} y={Math.max(PAD.top + 11, y - 8)} textAnchor="middle">{formatValue(point.value)}</text></g>
    })}
  </svg></div>
}

export function GradePyramid({ rows, mode = 'absolute' }: { rows: { label: string; value: number; available?: number | null; colour?: string }[]; mode?: 'absolute' | 'percent' }): React.JSX.Element {
  const values = rows.map((row) => mode === 'percent' && row.available ? (row.value / row.available) * 100 : row.value)
  const max = Math.max(...values, 1)
  return <div className="grade-pyramid" role="img" aria-label={`Gym set ${mode === 'percent' ? 'completion percentages' : 'send counts'}`}>
    {rows.map((row, index) => {
      const value = values[index] ?? 0
      return <div className="pyramid-row" key={row.label}><span>{row.label}</span><div className="pyramid-track"><i style={{ width: `${(value / max) * 100}%`, background: row.colour }} /></div><strong>{mode === 'percent' ? `${Math.round(value)}%` : row.available ? `${row.value}/${row.available}` : row.value}</strong></div>
    })}
  </div>
}

export function Donut({ value, total, label, detail }: { value: number; total: number; label: string; detail: string }): React.JSX.Element {
  const percent = total ? Math.min(100, Math.max(0, (value / total) * 100)) : 0
  return <div className="donut" style={{ '--donut-value': `${percent * 3.6}deg` } as React.CSSProperties}><div><strong>{Math.round(percent)}%</strong><span>{detail}</span></div><p>{label}</p></div>
}

export function ChartEmpty(): React.JSX.Element {
  return <div className="chart-empty"><span>No comparable data yet</span><small>The chart appears when enough verified sessions are available.</small></div>
}

import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import { Button, Card, Field, FormActions, InlineNotice, PageHeader, Tabs } from '../components/ui'
import { localIsoDate, startOfWeek } from '../lib/format'

type ReportCadence = 'WEEKLY' | 'MONTHLY'

function saveText(text: string, filename: string, type: string): void {
  const url = URL.createObjectURL(new Blob([text], { type }))
  const anchor = document.createElement('a')
  anchor.href = url; anchor.download = filename; anchor.click(); URL.revokeObjectURL(url)
}

export function TrainingReportsPage(): React.JSX.Element {
  const navigate = useNavigate()
  const [cadence, setCadence] = useState<ReportCadence>('WEEKLY')
  const [weekStart, setWeekStart] = useState(localIsoDate(startOfWeek()))
  const [month, setMonth] = useState(localIsoDate().slice(0, 7))
  const [report, setReport] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const generate = async () => {
    setBusy(true); setError(null); setMessage(null)
    try { setReport(cadence === 'WEEKLY' ? await api.weeklyReport(weekStart) : await api.monthlyReport(month)) }
    catch (reason) { setError(reason instanceof ApiError ? reason.message : 'Unable to generate the report.') }
    finally { setBusy(false) }
  }
  const filename = cadence === 'WEEKLY' ? `training-week-${weekStart}` : `training-month-${month}`
  const copy = async () => { await navigator.clipboard.writeText(report); setMessage('Report copied to clipboard.') }
  return <div className="page reports-page">
    <PageHeader eyebrow="FACTUAL EXPORT" title="Training Reports" description="Deterministic Markdown built from stored training evidence. No GPT call is required." actions={<Button icon="upload" variant="ghost" onClick={() => navigate('/plans')}>Import AI Plan</Button>} />
    <Tabs label="Report period" value={cadence} onChange={(value) => { setCadence(value); setReport(''); setMessage(null) }} items={[{ value: 'WEEKLY', label: 'Weekly' }, { value: 'MONTHLY', label: 'Monthly' }]} />
    <Card title={cadence === 'WEEKLY' ? 'Weekly report period' : 'Monthly report period'}><div className="report-controls">{cadence === 'WEEKLY' ? <Field label="Week starting Monday" type="date" value={weekStart} onChange={(event) => setWeekStart(event.target.value)} /> : <Field label="Month" type="month" value={month} onChange={(event) => setMonth(event.target.value)} />}<Button disabled={busy} onClick={() => void generate()}>{busy ? 'Generating…' : 'Generate report'}</Button></div></Card>
    {error && <InlineNotice tone="warning">{error}</InlineNotice>}
    {message && <InlineNotice tone="success">{message}</InlineNotice>}
    {report ? <Card title={report.split('\n')[0]?.replace('# ', '') ?? 'Report'}><FormActions><Button variant="ghost" onClick={() => void copy()}>Copy</Button><Button icon="download" variant="ghost" onClick={() => saveText(report, `${filename}.md`, 'text/markdown')}>Download .md</Button><Button icon="download" variant="ghost" onClick={() => saveText(report, `${filename}.txt`, 'text/plain')}>Download .txt</Button></FormActions><pre className="markdown-document">{report}</pre></Card> : <InlineNotice>Choose a period and generate a stable report. Missing values are shown as N/A; sections are never silently omitted.</InlineNotice>}
  </div>
}

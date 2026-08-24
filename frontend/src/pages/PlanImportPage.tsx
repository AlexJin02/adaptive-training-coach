import { useState, type ReactNode } from 'react'
import { api, ApiError } from '../api/client'
import { useResource } from '../api/hooks'
import { Button, Card, EmptyState, ErrorPanel, Field, FormActions, InlineNotice, LoadingGrid, Modal, PageHeader, Pill, Tabs, TextAreaField, formatEnum } from '../components/ui'
import { formatDate, formatDuration, formatNumber } from '../lib/format'
import type { MonthlyPlanContent, MonthlySessionStructureItem, MonthlyTrainingBlock, MonthlyWeekTarget, PlanParsePreview } from '../types'

type Cadence = 'WEEKLY' | 'MONTHLY'
type PageSection = 'CURRENT' | 'IMPORT'

function downloadText(text: string, filename: string): void {
  const url = URL.createObjectURL(new Blob([text], { type: 'text/markdown' }))
  const anchor = document.createElement('a'); anchor.href = url; anchor.download = filename; anchor.click(); URL.revokeObjectURL(url)
}

function specified(value?: string | null): string {
  const cleaned = value?.trim()
  return cleaned && cleaned.toUpperCase() !== 'N/A' ? cleaned : 'Not specified'
}

function count(value: number | null): string {
  if (value == null) return 'Not specified'
  return Number.isInteger(value) ? String(value) : formatNumber(value, 1)
}

function distance(value: number): string {
  return formatNumber(value, Number.isInteger(value) ? 0 : 1)
}

function targetTrail(targets: MonthlyWeekTarget[]): string {
  return targets.length ? targets.map((item) => distance(item.distance_km)).join(' → ') : 'Not specified'
}

function guidanceWithoutWeekTargets(value: string): string {
  return value.split('\n').filter((line) => !/^\s*-\s*Week\s*\d+\s*:/i.test(line)).join('\n').trim()
}

function monthTitle(block: MonthlyTrainingBlock | MonthlyPlanContent): string {
  const month = 'content' in block ? block.content.month || block.month_start.slice(0, 7) : block.month
  const parsed = new Date(`${month}-01T12:00:00`)
  return Number.isNaN(parsed.valueOf()) ? month || 'MONTHLY PLAN' : parsed.toLocaleDateString(undefined, { month: 'long', year: 'numeric' }).toUpperCase()
}

function StructureList({ items }: { items: MonthlySessionStructureItem[] }): React.JSX.Element {
  if (!items.length) return <p className="monthly-unspecified">Not specified</p>
  return <div className="monthly-structure-list">{items.map((item) => <div key={item.session_type}><strong>{formatEnum(item.session_type)}</strong><span>{count(item.sessions_per_week)} / week</span></div>)}</div>
}

function TargetTable({ targets, label }: { targets: MonthlyWeekTarget[]; label: string }): React.JSX.Element {
  if (!targets.length) return <p className="monthly-unspecified">Not specified</p>
  return <div className="monthly-table-wrap"><table className="monthly-target-table" aria-label={label}><thead><tr><th>Week</th><th>Target</th></tr></thead><tbody>{targets.map((item) => <tr key={item.week}><td>Week {item.week}</td><td>{distance(item.distance_km)} km</td></tr>)}</tbody></table></div>
}

function PlanField({ label, children }: { label: string; children: ReactNode }): React.JSX.Element {
  return <section className="monthly-plan-field"><h3>{label}</h3>{children}</section>
}

function PrincipleList({ items }: { items: string[] }): React.JSX.Element {
  return items.length ? <ul className="monthly-principles">{items.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul> : <p className="monthly-unspecified">Not specified</p>
}

export function MonthlyPlanView({ block, actions, compact = false }: { block: MonthlyTrainingBlock | MonthlyPlanContent; actions?: ReactNode; compact?: boolean }): React.JSX.Element {
  const content = 'content' in block ? block.content : block
  const running = content.running
  const climbing = content.climbing
  if (compact) return <Card className="monthly-context" title="Current Monthly Block"><div className="monthly-context-grid"><div><span>Running</span><strong>{specified(running.phase)}</strong><small>{currentWeekTarget('content' in block ? block : null, running.weekly_distance_targets)}</small></div><div><span>Climbing</span><strong>{climbing.sessions_per_week == null ? 'Not specified' : `${count(climbing.sessions_per_week)} sessions / week`}</strong><small>{boardRecommendation(climbing.target_structure)}</small></div></div></Card>
  return <div className="monthly-plan-view">
    <div className="monthly-plan-heading"><div><p className="eyebrow">CURRENT MONTHLY PLAN</p><h2>{monthTitle(block)}</h2></div>{actions && <div className="button-row">{actions}</div>}</div>
    <Card className="monthly-glance" title={`${monthTitle(block).replace(/ \d{4}$/, '')} AT A GLANCE`}>
      <div className="monthly-glance-grid">
        <PlanField label="Running"><strong>{running.sessions_per_week == null ? 'Not specified' : `${count(running.sessions_per_week)} sessions / week`}</strong><span>{targetTrail(running.weekly_distance_targets)}{running.weekly_distance_targets.length ? ' km' : ''}</span></PlanField>
        <PlanField label="Climbing"><strong>{climbing.sessions_per_week == null ? 'Not specified' : `${count(climbing.sessions_per_week)} sessions / week`}</strong></PlanField>
        <PlanField label="Running emphasis"><strong>{specified(running.phase)}</strong></PlanField>
        <PlanField label="Climbing emphasis"><strong>{specified(climbing.phase)}</strong></PlanField>
        <PlanField label="Key running session"><strong>{structureSummary(running.session_structure, 'QUALITY', 'Quality')}</strong></PlanField>
        <PlanField label="Long run"><strong>{targetTrail(running.long_run_targets)}{running.long_run_targets.length ? ' km' : ''}</strong></PlanField>
      </div>
    </Card>
    <Card className="monthly-sport-card running-card" title="RUNNING">
      <div className="monthly-two-up"><PlanField label="Phase"><p>{specified(running.phase)}</p></PlanField><PlanField label="Sessions / week"><p>{count(running.sessions_per_week)}</p></PlanField></div>
      <PlanField label="Main Goal"><p className="pre-wrap">{specified(running.monthly_objective)}</p></PlanField>
      <div className="monthly-two-up"><PlanField label="Weekly Mileage Targets"><TargetTable targets={running.weekly_distance_targets} label="Weekly running mileage targets" /></PlanField><PlanField label="Recommended Weekly Structure"><StructureList items={running.session_structure} /></PlanField></div>
      <PlanField label="Quality Focus"><p className="pre-wrap">{specified(running.quality_guidance)}</p></PlanField>
      <PlanField label="Long Run Progression"><TargetTable targets={running.long_run_targets} label="Long run progression" />{guidanceWithoutWeekTargets(running.long_run_guidance) ? <p className="pre-wrap monthly-guidance-note">{guidanceWithoutWeekTargets(running.long_run_guidance)}</p> : null}</PlanField>
      <PlanField label="Key Running Principles"><PrincipleList items={running.key_principles} /></PlanField>
      {running.other_notes && running.other_notes.toUpperCase() !== 'N/A' ? <PlanField label="Other Running Notes"><p className="pre-wrap">{running.other_notes}</p></PlanField> : null}
    </Card>
    <Card className="monthly-sport-card climbing-card" title="CLIMBING">
      <div className="monthly-two-up"><PlanField label="Phase"><p>{specified(climbing.phase)}</p></PlanField><PlanField label="Sessions / week"><p>{count(climbing.sessions_per_week)}</p></PlanField></div>
      <PlanField label="Suggested Weekly Structure"><StructureList items={climbing.target_structure} /></PlanField>
      <PlanField label="Board Focus"><p className="pre-wrap">{specified(climbing.board_focus)}</p></PlanField>
      <PlanField label="Key Climbing Principles"><PrincipleList items={climbing.key_principles} /></PlanField>
      {climbing.other_notes && climbing.other_notes.toUpperCase() !== 'N/A' ? <PlanField label="Other Climbing Notes"><p className="pre-wrap">{climbing.other_notes}</p></PlanField> : null}
    </Card>
    <Card title="AUXILIARY"><div className="monthly-two-up"><PlanField label="Strength"><p className="pre-wrap">{specified(content.auxiliary.strength)}</p></PlanField><PlanField label="Mobility"><p className="pre-wrap">{specified(content.auxiliary.mobility)}</p></PlanField></div><InlineNotice>Auxiliary work supports running and climbing; it is not a third primary sport.</InlineNotice></Card>
    {content.general_notes && content.general_notes.toUpperCase() !== 'N/A' ? <Card title="GENERAL NOTES"><p className="pre-wrap">{content.general_notes}</p></Card> : null}
  </div>
}

function structureSummary(items: MonthlySessionStructureItem[], type: string, label: string): string {
  const match = items.find((item) => item.session_type === type)
  return match ? `${count(match.sessions_per_week)} ${label} / week` : 'Not specified'
}

function boardRecommendation(items: MonthlySessionStructureItem[]): string {
  const match = items.find((item) => item.session_type.includes('BOARD'))
  return match ? `${count(match.sessions_per_week)} Board session recommended` : 'Board frequency not specified'
}

function currentWeekTarget(block: MonthlyTrainingBlock | null, targets: MonthlyWeekTarget[]): string {
  if (!targets.length) return 'Weekly distance not specified'
  const firstTarget = targets[0] as MonthlyWeekTarget
  const today = new Date()
  const planMonth = block?.content.month || block?.month_start.slice(0, 7)
  const currentMonth = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}`
  const wantedWeek = planMonth === currentMonth ? Math.ceil(today.getDate() / 7) : firstTarget.week
  const target = targets.find((item) => item.week === wantedWeek) ?? firstTarget
  return `Week ${target.week} target: ${distance(target.distance_km)} km`
}

export function PlanImportPage(): React.JSX.Element {
  const currentBlock = useResource(api.currentMonthlyBlock, [])
  const [section, setSection] = useState<PageSection>('CURRENT')
  const [cadence, setCadence] = useState<Cadence>('WEEKLY')
  const [markdown, setMarkdown] = useState('')
  const [preview, setPreview] = useState<PlanParsePreview | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [showRaw, setShowRaw] = useState(false)
  const [showEdit, setShowEdit] = useState(false)
  const parse = async () => { setBusy(true); setError(null); setMessage(null); try { setPreview(await api.parsePlan(cadence, markdown)) } catch (reason) { setError(reason instanceof ApiError ? reason.message : 'Unable to parse this plan.') } finally { setBusy(false) } }
  const importPlan = async () => { setBusy(true); setError(null); try { const result = await api.importPlan(cadence, markdown); setPreview(result); if (cadence === 'MONTHLY') { currentBlock.reload(); setSection('CURRENT') } setMessage(cadence === 'WEEKLY' ? `${result.imported_session_ids?.length ?? 0} session(s) imported to Calendar. Existing sessions were not overwritten.` : 'Monthly training block saved. No daily Calendar sessions were created.'); } catch (reason) { setError(reason instanceof ApiError ? reason.message : 'Unable to import this plan.') } finally { setBusy(false) } }
  const template = async (action: 'copy' | 'download') => { const text = await api.planTemplate(cadence.toLowerCase() as 'weekly' | 'monthly'); if (action === 'copy') { await navigator.clipboard.writeText(text); setMessage('Template copied to clipboard.') } else downloadText(text, cadence === 'WEEKLY' ? 'TRAINING_WEEKLY_PLAN_V1.md' : 'TRAINING_MONTHLY_PLAN_V1.md') }
  const openReplacement = () => { setCadence('MONTHLY'); setMarkdown(''); setPreview(null); setMessage(null); setSection('IMPORT') }
  return <div className="page plan-import-page">
    <PageHeader eyebrow="STRUCTURED BLOCKS → WEEKLY CALENDAR" title="Training Plan" description="Review the current monthly strategy or deterministically parse and import an external plan. Rendering never calls OpenAI." />
    <Tabs label="Training Plan section" value={section} onChange={setSection} items={[{ value: 'CURRENT', label: 'Current Monthly Plan' }, { value: 'IMPORT', label: 'Import Plan' }]} />
    {section === 'CURRENT' ? <>
      {currentBlock.loading ? <LoadingGrid count={3} /> : currentBlock.error ? <ErrorPanel message={currentBlock.error.message} onRetry={currentBlock.reload} /> : currentBlock.data ? <MonthlyPlanView block={currentBlock.data} actions={<><Button onClick={() => setShowEdit(true)}>Edit Plan</Button><Button variant="ghost" onClick={openReplacement}>Replace Plan</Button><Button variant="ghost" onClick={() => setShowRaw(true)}>View Raw Import</Button></>} /> : <EmptyState title="No monthly plan imported" message="Import a TRAINING_MONTHLY_PLAN_V1 to create your current strategic training block." action={<Button onClick={() => { setCadence('MONTHLY'); setSection('IMPORT') }}>Import Monthly Plan</Button>} />}
      {message && <InlineNotice tone="success">{message}</InlineNotice>}
    </> : <>
      <Tabs label="Plan cadence" value={cadence} onChange={(value) => { setCadence(value); setPreview(null); setMessage(null) }} items={[{ value: 'WEEKLY', label: 'Weekly Plan' }, { value: 'MONTHLY', label: 'Monthly Plan' }]} />
      {cadence === 'WEEKLY' && currentBlock.data ? <MonthlyPlanView block={currentBlock.data} compact /> : null}
      <Card title="Official template"><div className="button-row"><Button variant="ghost" onClick={() => void template('copy')}>Copy {cadence === 'WEEKLY' ? 'Weekly' : 'Monthly'} Template</Button><Button icon="download" variant="ghost" onClick={() => void template('download')}>Download Template</Button></div></Card>
      <Card title="Paste AI-generated training plan"><TextAreaField label="Plan Markdown" rows={22} value={markdown} onChange={(event) => { setMarkdown(event.target.value); setPreview(null) }} placeholder={cadence === 'WEEKLY' ? '# TRAINING_WEEKLY_PLAN_V1' : '# TRAINING_MONTHLY_PLAN_V1'} /><FormActions><Button variant="ghost" onClick={() => { setMarkdown(''); setPreview(null); setError(null) }}>Clear</Button><Button disabled={busy || !markdown.trim()} onClick={() => void parse()}>{busy ? 'Parsing…' : 'Parse Plan'}</Button></FormActions></Card>
      {error && <InlineNotice tone="warning">{error}</InlineNotice>}
      {message && <InlineNotice tone="success">{message}</InlineNotice>}
      {preview ? <PlanPreview preview={preview} busy={busy} onImport={() => void importPlan()} /> : <EmptyState title="No preview yet" message="Paste a plan and choose Parse Plan. Nothing is saved before Import to Calendar / Save Monthly Block." />}
    </>}
    <Modal open={showRaw} title="Original Monthly Plan Import" onClose={() => setShowRaw(false)} wide><pre className="markdown-document">{currentBlock.data?.content.raw_plan_text || 'Original import is not available for this block.'}</pre><FormActions><Button onClick={() => setShowRaw(false)}>Close</Button></FormActions></Modal>
    {currentBlock.data ? <EditMonthlyPlanModal key={currentBlock.data.id} block={currentBlock.data} open={showEdit} onClose={() => setShowEdit(false)} onSaved={(updated) => { currentBlock.setData(updated); setShowEdit(false); setMessage('Monthly plan updated. The previous version remains archived.') }} /> : null}
  </div>
}

function PlanPreview({ preview, busy, onImport }: { preview: PlanParsePreview; busy: boolean; onImport: () => void }): React.JSX.Element {
  return <div className="plan-preview-stack"><Card title="Validation"><div className="button-row"><Pill tone={preview.can_import ? 'good' : 'low'}>{preview.can_import ? 'READY TO IMPORT' : 'FIX REQUIRED'}</Pill><span>{formatDate(preview.period_start)}–{formatDate(preview.period_end)}</span></div>{preview.warnings.length ? <ul>{preview.warnings.map((warning, index) => <li key={`${warning}-${index}`}>{warning}</li>)}</ul> : <p>No validation warnings.</p>}</Card>
    {preview.cadence === 'WEEKLY' ? <Card title="Calendar session preview"><div className="plan-session-preview">{preview.sessions?.map((session) => <article key={`${session.date}-${session.session_number}`}><div><strong>{formatDate(session.date, { weekday: 'long', month: 'short', day: 'numeric' })} · {session.title}</strong><span>{formatEnum(session.session_type)} · {formatEnum(session.workout_kind)}</span></div><p className="pre-wrap">{session.raw_workout_text || 'No workout details'}</p><small>{session.planned_distance_km != null ? `${formatNumber(session.planned_distance_km, 1)} km · ` : ''}{session.planned_duration_minutes != null ? `${formatDuration(session.planned_duration_minutes)} · ` : ''}{session.target_rpe_min != null ? `RPE ${session.target_rpe_min}${session.target_rpe_max !== session.target_rpe_min ? `–${session.target_rpe_max}` : ''}` : 'RPE N/A'}</small></article>)}</div></Card> : preview.block ? <><MonthlyPlanView block={preview.block} /><InlineNotice>This saves one strategic monthly block. It does not create daily Calendar sessions.</InlineNotice></> : null}
    {!preview.import_id && <FormActions><Button disabled={busy || !preview.can_import} onClick={onImport}>{preview.cadence === 'WEEKLY' ? 'Import to Calendar' : 'Save Monthly Block'}</Button></FormActions>}
  </div>
}

interface EditDraft {
  runningPhase: string; runningObjective: string; runningSessions: string; runningStructure: string; mileage: string; quality: string; longRuns: string; runningPrinciples: string; runningNotes: string
  climbingPhase: string; climbingSessions: string; climbingStructure: string; boardFocus: string; climbingPrinciples: string; climbingNotes: string
  strength: string; mobility: string; generalNotes: string
}

function structureLines(items: MonthlySessionStructureItem[]): string { return items.map((item) => `${item.session_type}: ${count(item.sessions_per_week)}`).join('\n') }
function targetLines(items: MonthlyWeekTarget[]): string { return items.map((item) => `Week ${item.week}: ${distance(item.distance_km)} km`).join('\n') }
function principleLines(items: string[]): string { return items.join('\n') }
function draftFrom(content: MonthlyPlanContent): EditDraft { return { runningPhase: content.running.phase, runningObjective: content.running.monthly_objective, runningSessions: content.running.sessions_per_week?.toString() ?? '', runningStructure: structureLines(content.running.session_structure), mileage: targetLines(content.running.weekly_distance_targets), quality: content.running.quality_guidance, longRuns: content.running.long_run_targets.length ? targetLines(content.running.long_run_targets) : content.running.long_run_guidance, runningPrinciples: principleLines(content.running.key_principles), runningNotes: content.running.other_notes, climbingPhase: content.climbing.phase, climbingSessions: content.climbing.sessions_per_week?.toString() ?? '', climbingStructure: structureLines(content.climbing.target_structure), boardFocus: content.climbing.board_focus, climbingPrinciples: principleLines(content.climbing.key_principles), climbingNotes: content.climbing.other_notes, strength: content.auxiliary.strength, mobility: content.auxiliary.mobility, generalNotes: content.general_notes } }
function parseTargets(text: string): MonthlyWeekTarget[] | null { const lines = text.split('\n').map((line) => line.trim()).filter(Boolean); const items = lines.map((line) => line.match(/^Week\s*(\d+)\s*:\s*(\d+(?:\.\d+)?)\s*(?:km)?$/i)); return items.some((item) => !item) ? null : items.map((item) => ({ week: Number(item?.[1]), distance_km: Number(item?.[2]) })) }
function parseStructure(text: string): MonthlySessionStructureItem[] | null { const lines = text.split('\n').map((line) => line.trim()).filter(Boolean); const items = lines.map((line) => line.match(/^(.+?)\s*:\s*(\d+(?:\.\d+)?)$/)); return items.some((item) => !item) ? null : items.map((item) => ({ session_type: item?.[1]?.trim().toUpperCase().replace(/[^A-Z0-9]+/g, '_') ?? '', sessions_per_week: Number(item?.[2]) })) }
function lines(text: string): string[] { return text.split('\n').map((line) => line.trim().replace(/^[-•]\s*/, '')).filter(Boolean) }
function optionalNumber(text: string): number | null { return text.trim() === '' ? null : Number(text) }

function EditMonthlyPlanModal({ block, open, onClose, onSaved }: { block: MonthlyTrainingBlock; open: boolean; onClose: () => void; onSaved: (block: MonthlyTrainingBlock) => void }): React.JSX.Element | null {
  const [draft, setDraft] = useState<EditDraft>(() => draftFrom(block.content))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  if (!open) return null
  const update = (field: keyof EditDraft, value: string) => setDraft((current) => ({ ...current, [field]: value }))
  const save = async () => {
    const mileage = parseTargets(draft.mileage); const longRuns = parseTargets(draft.longRuns); const runningStructure = parseStructure(draft.runningStructure); const climbingStructure = parseStructure(draft.climbingStructure)
    const structuredLongRuns = /^\s*Week\s*\d+/im.test(draft.longRuns)
    if (!mileage || !runningStructure || !climbingStructure || (structuredLongRuns && !longRuns)) { setError('Check list formats. Use “Week 1: 36 km” for distances and “EASY: 2” for session structure.'); return }
    const runningSessions = optionalNumber(draft.runningSessions); const climbingSessions = optionalNumber(draft.climbingSessions)
    if ([runningSessions, climbingSessions].some((value) => value != null && (!Number.isFinite(value) || value < 0 || value > 14))) { setError('Sessions per week must be between 0 and 14, or left blank.'); return }
    setSaving(true); setError(null)
    try {
      const updated = await api.updateMonthlyBlock(block.id, { running: { phase: draft.runningPhase, monthly_objective: draft.runningObjective, sessions_per_week: runningSessions, session_structure: runningStructure, weekly_distance_targets: mileage, quality_guidance: draft.quality, long_run_guidance: longRuns ? draft.longRuns : draft.longRuns, long_run_targets: longRuns ?? [], key_principles: lines(draft.runningPrinciples), other_notes: draft.runningNotes }, climbing: { phase: draft.climbingPhase, sessions_per_week: climbingSessions, target_structure: climbingStructure, board_focus: draft.boardFocus, key_principles: lines(draft.climbingPrinciples), other_notes: draft.climbingNotes }, auxiliary: { strength: draft.strength, mobility: draft.mobility }, general_notes: draft.generalNotes })
      onSaved(updated)
    } catch (reason) { setError(reason instanceof ApiError ? reason.message : 'Unable to update this monthly plan.') } finally { setSaving(false) }
  }
  return <Modal open title="Edit Monthly Plan" onClose={onClose} wide><div className="stack-form monthly-edit-form">
    <h3>Running</h3><div className="form-grid two"><Field label="Phase" value={draft.runningPhase} onChange={(event) => update('runningPhase', event.target.value)} /><Field label="Sessions / week" type="number" min="0" max="14" step="0.5" value={draft.runningSessions} onChange={(event) => update('runningSessions', event.target.value)} /></div><TextAreaField label="Monthly objective" value={draft.runningObjective} onChange={(event) => update('runningObjective', event.target.value)} /><div className="form-grid two"><TextAreaField label="Session structure" hint="One per line, e.g. EASY: 2" value={draft.runningStructure} onChange={(event) => update('runningStructure', event.target.value)} /><TextAreaField label="Weekly mileage" hint="One per line, e.g. Week 1: 36 km" value={draft.mileage} onChange={(event) => update('mileage', event.target.value)} /></div><TextAreaField label="Quality guidance" value={draft.quality} onChange={(event) => update('quality', event.target.value)} /><TextAreaField label="Long-run progression or guidance" hint="Use Week 1: 14 km lines for structured targets, or enter guidance text." value={draft.longRuns} onChange={(event) => update('longRuns', event.target.value)} /><TextAreaField label="Key running principles" hint="One principle per line" value={draft.runningPrinciples} onChange={(event) => update('runningPrinciples', event.target.value)} /><TextAreaField label="Other running notes" value={draft.runningNotes} onChange={(event) => update('runningNotes', event.target.value)} />
    <h3>Climbing</h3><div className="form-grid two"><Field label="Phase" value={draft.climbingPhase} onChange={(event) => update('climbingPhase', event.target.value)} /><Field label="Sessions / week" type="number" min="0" max="14" step="0.5" value={draft.climbingSessions} onChange={(event) => update('climbingSessions', event.target.value)} /></div><TextAreaField label="Weekly structure" hint="One per line, e.g. BOARD: 1" value={draft.climbingStructure} onChange={(event) => update('climbingStructure', event.target.value)} /><TextAreaField label="Board focus" value={draft.boardFocus} onChange={(event) => update('boardFocus', event.target.value)} /><TextAreaField label="Key climbing principles" hint="One principle per line" value={draft.climbingPrinciples} onChange={(event) => update('climbingPrinciples', event.target.value)} /><TextAreaField label="Other climbing notes" value={draft.climbingNotes} onChange={(event) => update('climbingNotes', event.target.value)} />
    <h3>Auxiliary & Notes</h3><div className="form-grid two"><TextAreaField label="Strength" value={draft.strength} onChange={(event) => update('strength', event.target.value)} /><TextAreaField label="Mobility" value={draft.mobility} onChange={(event) => update('mobility', event.target.value)} /></div><TextAreaField label="General notes" value={draft.generalNotes} onChange={(event) => update('generalNotes', event.target.value)} />
    {error && <InlineNotice tone="warning">{error}</InlineNotice>}<FormActions><Button variant="ghost" onClick={onClose}>Cancel</Button><Button disabled={saving} onClick={() => void save()}>{saving ? 'Saving…' : 'Save Plan'}</Button></FormActions>
  </div></Modal>
}

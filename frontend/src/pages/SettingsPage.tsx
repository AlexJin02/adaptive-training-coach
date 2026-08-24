import { useEffect, useState, type FormEvent } from 'react'
import { api, ApiError, saveBlob } from '../api/client'
import { useResource } from '../api/hooks'
import { useCapabilities } from '../app/CapabilityProvider'
import { useTheme } from '../app/ThemeProvider'
import { Icon } from '../components/Icon'
import { Button, Card, Field, FormActions, InlineNotice, LoadingGrid, Modal, PageHeader, Pill, SelectField, Tabs, TextAreaField, formatEnum } from '../components/ui'
import { formatRaceTime, parseDurationInput } from '../lib/format'
import type { AppSettings, AthleteProfile, FatigueDomain, Goal, GoalType } from '../types'

type SettingsTab = 'profile' | 'goal' | 'system' | 'data'
const defaultSettings: AppSettings = { gym_name: 'Home Gym', grade_display: 'BOTH', retain_screenshots: false, retain_audio: false, engine: { base_stress_divisor: 90, base_stress_cap: 10, hard_attempt_threshold: 10, hard_attempt_increment: 0.015, hard_attempt_cap: 1.25, readiness_good_threshold: 7.5, readiness_moderate_threshold: 5, half_lives: { CARDIOVASCULAR: 18, LOWER_BODY: 30, FINGER_FOREARM: 36, PULLING_UPPER_BODY: 30, NEURAL: 24, SYSTEMIC: 18 } } }

function normaliseSettings(input: Partial<AppSettings> | null): AppSettings {
  const engine = input?.engine
  return {
    ...defaultSettings,
    ...input,
    engine: {
      ...defaultSettings.engine,
      ...engine,
      half_lives: { ...defaultSettings.engine.half_lives, ...(engine?.half_lives ?? {}) },
    },
  }
}

export function SettingsPage(): React.JSX.Element {
  const [tab, setTab] = useState<SettingsTab>('profile')
  const profile = useResource(api.profile, [])
  const goals = useResource(api.goals, [])
  const settings = useResource(api.settings, [])
  const loading = profile.loading || goals.loading || settings.loading
  const effectiveSettings = normaliseSettings(settings.data)
  return <div className="page settings-page">
    <PageHeader eyebrow="LOCAL CONTROL" title="Settings" description="Athlete goals, import tools, privacy defaults and local data controls." />
    <Tabs label="Settings section" value={tab} onChange={setTab} items={[{ value: 'profile', label: 'Athlete profile' }, { value: 'goal', label: 'Primary goal' }, { value: 'system', label: 'App & AI tools' }, { value: 'data', label: 'Data' }]} />
    {loading ? <LoadingGrid count={4} /> : tab === 'profile' ? <ProfileSettings initial={profile.data} onSaved={profile.reload} /> : tab === 'goal' ? <GoalSettings initial={goals.data?.items.find((goal) => goal.is_current) ?? goals.data?.items[0] ?? null} onSaved={goals.reload} /> : tab === 'system' ? <SystemSettings initial={effectiveSettings} onSaved={settings.reload} /> : <DataSettings settings={effectiveSettings} onChanged={() => { settings.reload(); profile.reload(); goals.reload() }} />}
  </div>
}

function ProfileSettings({ initial, onSaved }: { initial: AthleteProfile | null; onSaved: () => void }): React.JSX.Element {
  const initialForm = normaliseProfile(initial)
  const [form, setForm] = useState<Partial<AthleteProfile>>(initialForm)
  const [times, setTimes] = useState(() => profileTimeValues(initialForm))
  const [busy, setBusy] = useState(false); const [message, setMessage] = useState<string | null>(null)
  useEffect(() => { const profile = normaliseProfile(initial); setForm(profile); setTimes(profileTimeValues(profile)) }, [initial])
  const number = (key: keyof AthleteProfile, value: string) => setForm((current) => ({ ...current, [key]: value === '' ? null : Number(value) }))
  const text = (key: keyof AthleteProfile, value: string) => setForm((current) => ({ ...current, [key]: value }))
  const submit = async (event: FormEvent) => {
    event.preventDefault(); setMessage(null)
    const payload = { ...form }
    for (const key of profileTimeKeys) {
      const input = times[key].trim()
      const minutes = parseDurationInput(input)
      if (input && minutes == null) { setMessage('Running times must use minutes, M:SS, or H:MM:SS.'); return }
      payload[key] = minutes == null ? null : Math.round(minutes * 60)
    }
    delete payload.bouldering_goal
    setBusy(true)
    try { await api.saveProfile(payload); setMessage('Athlete profile saved.'); onSaved() } catch (reason) { setMessage(reason instanceof ApiError ? reason.message : 'Unable to save profile.') } finally { setBusy(false) }
  }
  return <form className="settings-stack" onSubmit={(event) => void submit(event)}>
    <Card title="Athlete"><div className="form-grid two"><Field label="Display name" required value={form.display_name ?? ''} onChange={(event) => text('display_name', event.target.value)} /><Field label="Timezone" required value={form.timezone ?? ''} onChange={(event) => text('timezone', event.target.value)} /></div></Card>
    <Card title="Running baseline & goals"><InlineNotice>Enter time as M:SS or H:MM:SS; seconds no longer need to be calculated. A plain number is treated as minutes.</InlineNotice><div className="form-grid three"><Field label="Current HM performance" inputMode="numeric" placeholder="1:45:00" value={times.current_half_marathon_seconds} onChange={(event) => setTimes((current) => ({ ...current, current_half_marathon_seconds: event.target.value }))} /><Field label="Current monthly volume (km)" type="number" min="0" value={form.current_monthly_km ?? ''} onChange={(event) => number('current_monthly_km', event.target.value)} /><Field label="Long-term monthly goal (km)" type="number" min="0" value={form.long_term_monthly_km ?? ''} onChange={(event) => number('long_term_monthly_km', event.target.value)} /><Field label="Stable weekly minimum (km)" type="number" min="0" value={form.stable_weekly_min_km ?? ''} onChange={(event) => number('stable_weekly_min_km', event.target.value)} /><Field label="Stable weekly maximum (km)" type="number" min="0" value={form.stable_weekly_max_km ?? ''} onChange={(event) => number('stable_weekly_max_km', event.target.value)} /><Field label="Primary HM goal" inputMode="numeric" placeholder="1:29:59" value={times.half_marathon_primary_goal_seconds} onChange={(event) => setTimes((current) => ({ ...current, half_marathon_primary_goal_seconds: event.target.value }))} /><Field label="Stretch HM goal" inputMode="numeric" placeholder="1:25:00" value={times.half_marathon_stretch_goal_seconds} onChange={(event) => setTimes((current) => ({ ...current, half_marathon_stretch_goal_seconds: event.target.value }))} /><Field label="Marathon goal" inputMode="numeric" placeholder="3:15:00" value={times.marathon_goal_seconds} onChange={(event) => setTimes((current) => ({ ...current, marathon_goal_seconds: event.target.value }))} /></div></Card>
    <Card title="Climbing baseline & goals"><div className="form-grid three"><Field label="TB2 verified" value={form.tb2_verified_grade ?? ''} onChange={(event) => text('tb2_verified_grade', event.target.value)} /><Field label="TB2 estimated" value={form.tb2_estimated_grade ?? ''} onChange={(event) => text('tb2_estimated_grade', event.target.value)} /><Field label="Current top rope" value={form.top_rope_grade ?? ''} onChange={(event) => text('top_rope_grade', event.target.value)} /><Field label="TB2 long-term goal" value={form.tb2_long_term_goal ?? ''} onChange={(event) => text('tb2_long_term_goal', event.target.value)} /><Field label="Outdoor bouldering goal" value={form.outdoor_boulder_goal ?? ''} onChange={(event) => text('outdoor_boulder_goal', event.target.value)} /><Field label="Route goal" value={form.route_goal ?? ''} onChange={(event) => text('route_goal', event.target.value)} /></div></Card>
    {message && <InlineNotice tone={message.includes('saved') ? 'success' : 'warning'}>{message}</InlineNotice>}<FormActions><Button type="submit" disabled={busy}>{busy ? 'Saving…' : 'Save profile'}</Button></FormActions>
  </form>
}

const profileTimeKeys = ['current_half_marathon_seconds', 'half_marathon_primary_goal_seconds', 'half_marathon_stretch_goal_seconds', 'marathon_goal_seconds'] as const

function profileTimeValues(profile: Partial<AthleteProfile>): Record<(typeof profileTimeKeys)[number], string> {
  return Object.fromEntries(profileTimeKeys.map((key) => [key, profile[key] ? formatRaceTime(profile[key]) : ''])) as Record<(typeof profileTimeKeys)[number], string>
}

function normaliseProfile(initial: AthleteProfile | null): Partial<AthleteProfile> {
  const fallback: Partial<AthleteProfile> = { display_name: 'Athlete', timezone: Intl.DateTimeFormat().resolvedOptions().timeZone, running_phase: 'AEROBIC_BASE', climbing_phase: 'TECHNIQUE_VOLUME', tb2_long_term_goal: 'V9–V10', outdoor_boulder_goal: 'V10' }
  if (!initial) return fallback
  return { ...initial, tb2_long_term_goal: initial.tb2_long_term_goal ?? initial.bouldering_goal ?? 'V9–V10', outdoor_boulder_goal: initial.outdoor_boulder_goal ?? 'V10' }
}

function GoalSettings({ initial, onSaved }: { initial: Goal | null; onSaved: () => void }): React.JSX.Element {
  const [form, setForm] = useState({ goal_type: (initial?.goal_type ?? 'HALF_MARATHON') as GoalType, description: initial?.description ?? 'Build toward a sustainable sub-1:30 half marathon', target_value: initial?.target_value ?? '1:29:59', target_date: initial?.target_date ?? '', current_status: initial?.current_status ?? 'ACTIVE', notes: initial?.notes ?? '' })
  const [busy, setBusy] = useState(false); const [message, setMessage] = useState<string | null>(null)
  useEffect(() => { if (initial) setForm({ goal_type: initial.goal_type, description: initial.description, target_value: initial.target_value ?? '', target_date: initial.target_date ?? '', current_status: initial.current_status ?? 'ACTIVE', notes: initial.notes ?? '' }) }, [initial])
  const submit = async (event: FormEvent) => { event.preventDefault(); setBusy(true); setMessage(null); try { await api.saveGoal({ ...form, target_date: form.target_date || null, notes: form.notes || null, is_current: true }); setMessage('Primary goal saved. Any previous current goal remains in history but is no longer active.'); onSaved() } catch (reason) { setMessage(reason instanceof ApiError ? reason.message : 'Unable to save goal.') } finally { setBusy(false) } }
  return <form className="settings-stack" onSubmit={(event) => void submit(event)}><Card title="Exactly one current primary goal"><InlineNotice title="No percentage weighting">Running and climbing records remain available concurrently. The current goal is included in exported training reports.</InlineNotice><div className="form-grid two"><SelectField label="Goal type" value={form.goal_type} onChange={(event) => setForm({ ...form, goal_type: event.target.value as GoalType })}><option value="RUNNING_MILEAGE">Running mileage</option><option value="HALF_MARATHON">Half marathon</option><option value="MARATHON">Marathon</option><option value="BOULDERING">Bouldering</option><option value="LEAD_CLIMBING">Lead climbing</option></SelectField><Field label="Target value" value={form.target_value} onChange={(event) => setForm({ ...form, target_value: event.target.value })} /><Field label="Target date" type="date" value={form.target_date} onChange={(event) => setForm({ ...form, target_date: event.target.value })} /><SelectField label="Status" value={form.current_status} onChange={(event) => setForm({ ...form, current_status: event.target.value })}><option>ACTIVE</option><option>PAUSED</option><option>ACHIEVED</option><option>ARCHIVED</option></SelectField></div><TextAreaField label="Description" required rows={3} value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} /><TextAreaField label="Notes" rows={4} value={form.notes} onChange={(event) => setForm({ ...form, notes: event.target.value })} /></Card>{message && <InlineNotice tone={message.includes('saved') ? 'success' : 'warning'}>{message}</InlineNotice>}<FormActions><Button type="submit" disabled={busy}>{busy ? 'Saving…' : 'Set primary goal'}</Button></FormActions></form>
}

function SystemSettings({ initial, onSaved }: { initial: AppSettings; onSaved: () => void }): React.JSX.Element {
  const { capabilities, connected, reload } = useCapabilities(); const { theme, toggleTheme } = useTheme(); const [form, setForm] = useState(initial); const [busy, setBusy] = useState(false); const [message, setMessage] = useState<string | null>(null)
  useEffect(() => setForm(initial), [initial])
  const save = async () => { setBusy(true); setMessage(null); try { await api.saveSettings({ gym_name: form.gym_name, grade_display: form.grade_display, retain_screenshots: form.retain_screenshots, retain_audio: form.retain_audio }); setMessage('Application settings saved.'); onSaved() } catch (reason) { setMessage(reason instanceof ApiError ? reason.message : 'Unable to save settings.') } finally { setBusy(false) } }
  const features = [['Screenshot extraction', capabilities.image_extraction], ['Text workout extraction', capabilities.text_extraction], ['Voice transcription', capabilities.transcription], ['Note organisation', capabilities.note_processing]] as const
  return <div className="settings-stack"><Card title="Appearance & gym"><div className="form-grid two"><Field label="Home gym name" value={form.gym_name} onChange={(event) => setForm({ ...form, gym_name: event.target.value })} /><SelectField label="Climbing grade display" value={form.grade_display} onChange={(event) => setForm({ ...form, grade_display: event.target.value as AppSettings['grade_display'] })}><option value="FONT">Fontainebleau</option><option value="V_SCALE">V scale</option><option value="BOTH">Both</option></SelectField></div><div className="theme-row"><span><strong>Colour theme</strong><small>Uses system preference initially and persists locally.</small></span><Button variant="ghost" icon={theme === 'dark' ? 'moon' : 'sun'} onClick={toggleTheme}>{formatEnum(theme)}</Button></div></Card><Card title="Privacy defaults"><label className="switch-row"><input type="checkbox" checked={form.retain_screenshots} onChange={(event) => setForm({ ...form, retain_screenshots: event.target.checked })} /><span><strong>Retain imported screenshots</strong><small>Off by default; delete after successful extraction.</small></span></label><label className="switch-row"><input type="checkbox" checked={form.retain_audio} onChange={(event) => setForm({ ...form, retain_audio: event.target.checked })} /><span><strong>Retain voice-note audio</strong><small>Off by default; delete after successful transcription.</small></span></label></Card><Card title="Backend & AI status"><div className="system-status"><div><span className={`connection-dot ${connected ? 'connected' : ''}`} /><div><strong>{connected ? 'Local backend connected' : 'Local backend unavailable'}</strong><small>{capabilities.ai_configured ? `Configured model: ${capabilities.model ?? 'server default'}` : capabilities.reason ?? 'No API key configured'}</small></div></div><Button variant="ghost" icon="refresh" onClick={reload}>Refresh</Button></div><div className="capability-grid">{features.map(([label, available]) => <div key={label}><Icon name={available ? 'check' : 'close'} /><span>{label}</span><Pill tone={available ? 'good' : 'neutral'}>{available ? 'READY' : 'OFF'}</Pill></div>)}</div><InlineNotice>API keys and model environment variables are backend-only and are never entered, stored or exposed here.</InlineNotice></Card>{message && <InlineNotice tone={message.includes('saved') ? 'success' : 'warning'}>{message}</InlineNotice>}<FormActions><Button disabled={busy} onClick={() => void save()}>{busy ? 'Saving…' : 'Save app settings'}</Button></FormActions></div>
}

function DataSettings({ settings, onChanged }: { settings: AppSettings; onChanged: () => void }): React.JSX.Element {
  const [restoreOpen, setRestoreOpen] = useState(false); const [demoBusy, setDemoBusy] = useState(false); const [message, setMessage] = useState<string | null>(null)
  const backup = async () => { try { saveBlob(await api.createBackup(), `adaptive-training-coach-${new Date().toISOString().slice(0, 10)}.json`) } catch (reason) { setMessage(reason instanceof ApiError ? reason.message : 'Backup failed.') } }
  const exportCsv = async (entity: string) => { try { saveBlob(await api.exportCsv(entity), `${entity}.csv`) } catch (reason) { setMessage(reason instanceof ApiError ? reason.message : 'Export failed.') } }
  const demo = async (remove: boolean) => { setDemoBusy(true); setMessage(null); try { if (remove) { const result = await api.removeDemo(); setMessage(`Removed ${result.removed} demo records.`) } else { const result = await api.seedDemo(); setMessage(`Created ${result.created} labelled demo records.`) } onChanged() } catch (reason) { setMessage(reason instanceof ApiError ? reason.message : 'Demo data operation failed.') } finally { setDemoBusy(false) } }
  return <div className="settings-stack"><Card title="Local database"><div className="database-banner"><Icon name="database" size={30} /><div><strong>{settings.database_path ?? 'Managed by local backend'}</strong><span>SQLite · local by default · no cloud hosting required</span></div></div></Card><div className="two-column"><Card title="Full backup & restore"><p>Backups preserve relational history, settings and flexible nested details in JSON.</p><div className="button-row"><Button icon="download" onClick={() => void backup()}>Download JSON backup</Button><Button variant="ghost" icon="upload" onClick={() => setRestoreOpen(true)}>Restore</Button></div></Card><Card title="CSV exports"><p>Export useful factual data for analysis outside the application.</p><div className="button-grid"><Button variant="ghost" onClick={() => void exportCsv('workouts')}>Workouts</Button><Button variant="ghost" onClick={() => void exportCsv('benchmarks')}>Benchmarks</Button><Button variant="ghost" onClick={() => void exportCsv('notes')}>Notes</Button></div></Card></div><Card title="Optional demo data"><div className="demo-row"><div><Pill tone="moderate">DEMO</Pill><div><strong>{settings.demo_data_present ? 'Demo data is present' : 'No demo data installed'}</strong><p>Several labelled weeks exercise factual charts, reports and notes. Demo records are removable.</p></div></div>{settings.demo_data_present ? <Button variant="danger" icon="trash" disabled={demoBusy} onClick={() => void demo(true)}>Remove demo data</Button> : <Button icon="plus" disabled={demoBusy} onClick={() => void demo(false)}>Install demo data</Button>}</div></Card>{message && <InlineNotice tone={message.includes('failed') || message.includes('Unable') ? 'warning' : 'success'}>{message}</InlineNotice>}<Modal open={restoreOpen} title="Restore a backup" onClose={() => setRestoreOpen(false)}><RestoreForm onRestored={() => { setRestoreOpen(false); onChanged() }} /></Modal></div>
}

function RestoreForm({ onRestored }: { onRestored: () => void }): React.JSX.Element {
  const [file, setFile] = useState<File | null>(null); const [confirm, setConfirm] = useState(''); const [busy, setBusy] = useState(false); const [error, setError] = useState<string | null>(null)
  const restore = async () => { if (!file || confirm !== 'RESTORE') return; setBusy(true); setError(null); try { await api.restoreBackup(file); onRestored() } catch (reason) { setError(reason instanceof ApiError ? reason.message : 'Restore failed validation.') } finally { setBusy(false) } }
  return <div className="stack-form"><InlineNotice tone="warning" title="Validate before replacing local state">Create a fresh backup first. The backend validates the JSON before applying any records.</InlineNotice><Field label="Backup file" type="file" accept="application/json,.json" onChange={(event) => setFile(event.target.files?.[0] ?? null)} /><Field label="Type RESTORE to confirm" value={confirm} onChange={(event) => setConfirm(event.target.value)} />{error && <InlineNotice tone="warning">{error}</InlineNotice>}<FormActions><Button variant="ghost" onClick={onRestored}>Cancel</Button><Button variant="danger" disabled={!file || confirm !== 'RESTORE' || busy} onClick={() => void restore()}>{busy ? 'Restoring…' : 'Restore backup'}</Button></FormActions></div>
}

export function EngineSettings({ initial, onSaved }: { initial: AppSettings; onSaved: () => void }): React.JSX.Element {
  const [engine, setEngine] = useState(initial.engine); const [busy, setBusy] = useState(false); const [message, setMessage] = useState<string | null>(null)
  useEffect(() => setEngine(initial.engine), [initial])
  const update = (key: keyof AppSettings['engine'], value: string) => setEngine((current) => ({ ...current, [key]: Number(value) }))
  const save = async () => { setBusy(true); setMessage(null); try { await api.saveSettings({ engine }); setMessage('Training-engine configuration saved.'); onSaved() } catch (reason) { setMessage(reason instanceof ApiError ? reason.message : 'Unable to save engine settings.') } finally { setBusy(false) } }
  const restore = () => setEngine(defaultSettings.engine)
  return <div className="settings-stack"><InlineNotice tone="warning" title="Planning heuristics">These values are auditable engineering defaults, not biological constants. Load and hard-attempt settings apply to future workouts; decay and readiness settings recalculate derived views. Workout history is never erased.</InlineNotice><Card title="Normalised session stress"><div className="form-grid three"><Field label="sRPE divisor" type="number" min="1" value={engine.base_stress_divisor} onChange={(event) => update('base_stress_divisor', event.target.value)} /><Field label="Stress cap" type="number" min="1" value={engine.base_stress_cap} onChange={(event) => update('base_stress_cap', event.target.value)} /><Field label="Hard-attempt threshold" type="number" min="0" value={engine.hard_attempt_threshold} onChange={(event) => update('hard_attempt_threshold', event.target.value)} /><Field label="Attempt increment" type="number" min="0" step="0.001" value={engine.hard_attempt_increment} onChange={(event) => update('hard_attempt_increment', event.target.value)} /><Field label="Attempt multiplier cap" type="number" min="1" step="0.01" value={engine.hard_attempt_cap} onChange={(event) => update('hard_attempt_cap', event.target.value)} /></div></Card><Card title="Fatigue half-lives"><div className="engine-table"><div className="engine-row heading"><span>Domain</span><span>Hours</span></div>{Object.entries(engine.half_lives).map(([domain, hours]) => <div className="engine-row" key={domain}><span>{formatEnum(domain)}</span><input aria-label={`${domain} half-life`} type="number" min="1" value={hours} onChange={(event) => setEngine((current) => ({ ...current, half_lives: { ...current.half_lives, [domain as FatigueDomain]: Number(event.target.value) } }))} /></div>)}</div></Card><Card title="Readiness labels"><div className="form-grid two"><Field label="GOOD threshold" type="number" min="0" max="10" step="0.1" value={engine.readiness_good_threshold} onChange={(event) => update('readiness_good_threshold', event.target.value)} /><Field label="MODERATE threshold" type="number" min="0" max="10" step="0.1" value={engine.readiness_moderate_threshold} onChange={(event) => update('readiness_moderate_threshold', event.target.value)} /></div></Card>{message && <InlineNotice tone={message.includes('saved') ? 'success' : 'warning'}>{message}</InlineNotice>}<FormActions><Button variant="ghost" onClick={restore}>Restore defaults</Button><Button disabled={busy} onClick={() => void save()}>{busy ? 'Saving…' : 'Save engine settings'}</Button></FormActions></div>
}

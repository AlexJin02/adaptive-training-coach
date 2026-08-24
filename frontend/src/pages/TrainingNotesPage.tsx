import { useMemo, useRef, useState, type FormEvent } from 'react'
import { api, ApiError } from '../api/client'
import { useResource } from '../api/hooks'
import { useCapabilities } from '../app/CapabilityProvider'
import { Icon } from '../components/Icon'
import { Button, Card, ConfidencePill, EmptyState, ErrorPanel, Field, FormActions, InlineNotice, LoadingGrid, Modal, PageHeader, Pill, SelectField, Tabs, TextAreaField, formatEnum } from '../components/ui'
import { formatDate } from '../lib/format'
import type { NoteCategory, TrainingNote } from '../types'

const categoryTabs = [
  { value: 'ALL', label: 'All notes' }, { value: 'RUNNING', label: 'Running' }, { value: 'CLIMBING', label: 'Climbing' }, { value: 'STRENGTH_MOBILITY', label: 'Strength & Mobility' },
] as const

export function TrainingNotesPage(): React.JSX.Element {
  const [category, setCategory] = useState<(typeof categoryTabs)[number]['value']>('ALL')
  const [search, setSearch] = useState('')
  const [tag, setTag] = useState('')
  const [sort, setSort] = useState<'newest' | 'oldest'>('newest')
  const [selectedId, setSelectedId] = useState<string | number | null>(null)
  const [editorOpen, setEditorOpen] = useState(false)
  const query = useMemo(() => {
    const params = new URLSearchParams()
    if (category !== 'ALL') params.set('category', category)
    if (tag.trim()) params.set('tag', tag.trim())
    if (search.trim()) params.set('q', search.trim())
    return params.toString()
  }, [category, search, tag])
  const resource = useResource(() => api.notes(query), [query])
  const notes = useMemo(() => [...(resource.data?.items ?? [])].sort((a, b) => sort === 'newest' ? b.created_at.localeCompare(a.created_at) : a.created_at.localeCompare(b.created_at)), [resource.data, sort])
  const selected = notes.find((note) => note.id === selectedId) ?? notes[0]
  return <div className="page notes-page">
    <PageHeader eyebrow="PERSONAL KNOWLEDGE" title="Training Notes" description="Save searchable running, climbing, and strength or mobility notes. Notes do not change training calculations or plans." actions={<Button icon="plus" onClick={() => setEditorOpen(true)}>New note</Button>} />
    <Tabs label="Note category" value={category} onChange={setCategory} items={categoryTabs} />
    <Card className="filter-bar notes-filter"><div className="search-field"><Icon name="search" /><input aria-label="Search notes" placeholder="Search text, title or tags" value={search} onChange={(event) => setSearch(event.target.value)} /></div><Field className="compact-field" label="Tag filter" placeholder="e.g. threshold" value={tag} onChange={(event) => setTag(event.target.value)} /><SelectField className="compact-field" label="Sort" value={sort} onChange={(event) => setSort(event.target.value as typeof sort)}><option value="newest">Newest first</option><option value="oldest">Oldest first</option></SelectField></Card>
    {resource.loading ? <LoadingGrid count={5} /> : resource.error ? <ErrorPanel message={resource.error.message} onRetry={resource.reload} /> : notes.length ? <div className="notes-layout"><div className="note-list">{notes.map((note) => <button key={note.id} className={selected?.id === note.id ? 'active' : ''} onClick={() => setSelectedId(note.id)}><div><Pill tone={note.primary_category === 'RUNNING' ? 'run' : note.primary_category === 'CLIMBING' ? 'climb' : 'neutral'}>{formatEnum(note.primary_category)}</Pill>{note.is_demo && <Pill tone="moderate">DEMO</Pill>}{note.favorite && <Icon name="heart" size={14} />}</div><strong>{note.title}</strong><p>{note.summary || note.cleaned_note}</p><small>{formatDate(note.created_at)} · {note.tags.slice(0, 3).join(' · ')}</small></button>)}</div>{selected && <NoteReader note={selected} />}</div> : <EmptyState icon="notes" title="No training notes" message="Record, review and save a useful training idea. It remains separate from workout evidence." action={<Button icon="mic" onClick={() => setEditorOpen(true)}>Capture a note</Button>} />}
    <Modal open={editorOpen} title="Capture training knowledge" onClose={() => setEditorOpen(false)} wide><NoteCapture onSaved={() => { setEditorOpen(false); resource.reload() }} /></Modal>
  </div>
}

function NoteReader({ note }: { note: TrainingNote }): React.JSX.Element {
  return <article className="note-reader">
    <header><div><Pill tone={note.primary_category === 'RUNNING' ? 'run' : note.primary_category === 'CLIMBING' ? 'climb' : 'neutral'}>{formatEnum(note.primary_category)}</Pill>{note.is_demo && <Pill tone="moderate">DEMO DATA</Pill>}<span>{formatDate(note.created_at, { month: 'long', day: 'numeric', year: 'numeric' })}</span></div><h2>{note.title}</h2>{note.source_title && <p className="note-source">{note.source_title}{note.source_creator ? ` · ${note.source_creator}` : ''}{note.source_url && <> · <a href={note.source_url} target="_blank" rel="noreferrer">Source</a></>}</p>}</header>
    {note.summary && <div className="note-summary"><strong>Summary</strong><p>{note.summary}</p></div>}
    <div className="note-body">{note.cleaned_note.split('\n').map((line, index) => <p key={index}>{line}</p>)}</div>
    {note.key_takeaways.length > 0 && <section><h3>Key takeaways</h3><ul>{note.key_takeaways.map((item) => <li key={item}>{item}</li>)}</ul></section>}
    {note.actionable_ideas.length > 0 && <section><h3>Actionable ideas</h3><ul>{note.actionable_ideas.map((item) => <li key={item}>{item}</li>)}</ul></section>}
    <div className="tag-list">{note.tags.map((tag) => <span key={tag}>#{tag}</span>)}</div>
    <InlineNotice>Personal knowledge only. This note is never applied to the Calendar automatically.</InlineNotice>
  </article>
}

interface NoteDraft {
  primary_category: NoteCategory
  title: string
  raw_input: string
  cleaned_note: string
  summary: string
  key_takeaways: string
  actionable_ideas: string
  tags: string
  source_title: string
  source_creator: string
  source_url: string
  input_type: 'TEXT' | 'VOICE'
  classification_confidence: 'LOW' | 'MODERATE' | 'HIGH' | null
  use_for_coaching: boolean
}

const blankNote: NoteDraft = { primary_category: 'RUNNING', title: '', raw_input: '', cleaned_note: '', summary: '', key_takeaways: '', actionable_ideas: '', tags: '', source_title: '', source_creator: '', source_url: '', input_type: 'TEXT', classification_confidence: null, use_for_coaching: false }

function NoteCapture({ onSaved }: { onSaved: () => void }): React.JSX.Element {
  const { capabilities } = useCapabilities()
  const [mode, setMode] = useState<'text' | 'voice'>('text')
  const [draft, setDraft] = useState<NoteDraft>(blankNote)
  const [stage, setStage] = useState<'capture' | 'review'>('capture')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const process = async (raw: string, inputType: 'TEXT' | 'VOICE') => {
    if (!raw.trim()) return
    setBusy(true); setError(null)
    if (!capabilities.note_processing) {
      setDraft((current) => ({ ...current, raw_input: raw, cleaned_note: raw, title: current.title || 'Untitled training note', input_type: inputType, classification_confidence: null }))
      setStage('review'); setBusy(false); return
    }
    try {
      const processed = await api.processNote({ raw_input: raw, input_type: inputType })
      setDraft((current) => ({ ...current, raw_input: raw, cleaned_note: processed.cleaned_note ?? raw, title: processed.title ?? 'Untitled training note', summary: processed.summary ?? '', key_takeaways: processed.key_takeaways?.join('\n') ?? '', actionable_ideas: processed.actionable_ideas?.join('\n') ?? '', tags: processed.tags?.join(', ') ?? '', primary_category: processed.primary_category ?? 'RUNNING', input_type: inputType, classification_confidence: processed.classification_confidence ?? null, use_for_coaching: false }))
      setStage('review')
    } catch (reason) { setError(reason instanceof ApiError ? reason.message : 'Note processing failed.') }
    finally { setBusy(false) }
  }
  return <div className="note-capture"><Tabs label="Note input" value={mode} onChange={setMode} items={[{ value: 'text', label: 'Text' }, { value: 'voice', label: 'Voice' }]} />{stage === 'capture' ? mode === 'text' ? <TextCapture busy={busy} error={error} onProcess={(raw) => void process(raw, 'TEXT')} ai={capabilities.note_processing} /> : <VoiceCapture busy={busy} error={error} onTranscript={(raw) => void process(raw, 'VOICE')} /> : <NoteReview draft={draft} setDraft={setDraft} onBack={() => setStage('capture')} onSaved={onSaved} />}</div>
}

function TextCapture({ busy, error, onProcess, ai }: { busy: boolean; error: string | null; onProcess: (value: string) => void; ai: boolean }): React.JSX.Element {
  const [raw, setRaw] = useState('')
  return <div className="capture-panel"><TextAreaField label="Raw note" rows={10} value={raw} onChange={(event) => setRaw(event.target.value)} placeholder="Paste or write the idea in Chinese, English, or both…" />{!ai && <InlineNotice title="Manual organisation mode">AI note processing is unavailable. Your text will move to an editable review form.</InlineNotice>}{error && <InlineNotice tone="warning">{error} Your raw text is still here.</InlineNotice>}<FormActions><Button disabled={busy || !raw.trim()} onClick={() => onProcess(raw)}>{busy ? 'Organising…' : ai ? 'Organise note' : 'Review manually'}</Button></FormActions></div>
}

function VoiceCapture({ busy, error, onTranscript }: { busy: boolean; error: string | null; onTranscript: (value: string) => void }): React.JSX.Element {
  const { capabilities } = useCapabilities()
  const recorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const [recording, setRecording] = useState(false)
  const [audio, setAudio] = useState<Blob | null>(null)
  const [localError, setLocalError] = useState<string | null>(null)
  const [retain, setRetain] = useState(false)
  const start = async () => {
    setLocalError(null)
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') { setLocalError('Audio recording is not supported in this browser.'); return }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const recorder = new MediaRecorder(stream)
      chunksRef.current = []
      recorder.ondataavailable = (event) => { if (event.data.size) chunksRef.current.push(event.data) }
      recorder.onstop = () => { setAudio(new Blob(chunksRef.current, { type: recorder.mimeType || 'audio/webm' })); stream.getTracks().forEach((track) => track.stop()) }
      recorderRef.current = recorder; recorder.start(); setRecording(true)
    } catch { setLocalError('Microphone access was denied or unavailable.') }
  }
  const stop = () => { recorderRef.current?.stop(); setRecording(false) }
  const transcribe = async () => {
    if (!audio) return
    try { const result = await api.transcribeNote(audio, retain); onTranscript(result.transcript); if (!retain) setAudio(null) }
    catch (reason) { setLocalError(reason instanceof ApiError ? reason.message : 'Transcription failed.') }
  }
  if (!capabilities.transcription) return <div className="degraded-flow"><InlineNotice tone="warning" title="Voice transcription unavailable">{capabilities.reason ?? 'Configure a transcription model in the backend.'}</InlineNotice><p className="muted">Use the Text tab to preserve the note manually.</p></div>
  return <div className="voice-panel"><div className={`record-orb ${recording ? 'recording' : ''}`}><Icon name="mic" size={34} /><span>{recording ? 'Recording…' : audio ? 'Recording ready' : 'Ready to record'}</span></div><div className="button-row">{recording ? <Button variant="danger" onClick={stop}>Stop</Button> : <Button icon="mic" onClick={() => void start()}>{audio ? 'Record again' : 'Record'}</Button>}{audio && <Button disabled={busy} onClick={() => void transcribe()}>{busy ? 'Transcribing…' : 'Transcribe & organise'}</Button>}</div><label className="switch-row"><input type="checkbox" checked={retain} onChange={(event) => setRetain(event.target.checked)} /><span><strong>Retain raw audio locally</strong><small>Off by default. Audio is deleted after successful transcription.</small></span></label><p className="muted">Domain hints include LT1, LT2, threshold, VO2max, TB2, heel hook, max hangs, power endurance and RPE.</p>{(localError || error) && <InlineNotice tone="warning">{localError ?? error} You can switch to Text without losing saved notes.</InlineNotice>}</div>
}

function NoteReview({ draft, setDraft, onBack, onSaved }: { draft: NoteDraft; setDraft: React.Dispatch<React.SetStateAction<NoteDraft>>; onBack: () => void; onSaved: () => void }): React.JSX.Element {
  const [busy, setBusy] = useState(false); const [error, setError] = useState<string | null>(null)
  const set = (key: keyof NoteDraft, value: string | boolean) => setDraft((current) => ({ ...current, [key]: value }))
  const submit = async (event: FormEvent) => { event.preventDefault(); setBusy(true); setError(null); try { await api.createNote({ primary_category: draft.primary_category, title: draft.title, raw_input: draft.raw_input, cleaned_note: draft.cleaned_note, summary: draft.summary, key_takeaways: lines(draft.key_takeaways), actionable_ideas: lines(draft.actionable_ideas), tags: draft.tags.split(',').map((tag) => tag.trim()).filter(Boolean), source_title: draft.source_title || null, source_creator: draft.source_creator || null, source_url: draft.source_url || null, input_type: draft.input_type, classification_confidence: draft.classification_confidence, use_for_coaching: draft.use_for_coaching }); onSaved() } catch (reason) { setError(reason instanceof ApiError ? reason.message : 'Unable to save note.') } finally { setBusy(false) } }
  return <form className="stack-form" onSubmit={(event) => void submit(event)}><div className="review-banner"><div><span>STRUCTURED PREVIEW</span><strong>Review before saving</strong></div><ConfidencePill value={draft.classification_confidence} /></div><div className="form-grid two"><SelectField label="Primary category" value={draft.primary_category} onChange={(event) => set('primary_category', event.target.value)}><option value="RUNNING">Running</option><option value="CLIMBING">Climbing</option><option value="STRENGTH_MOBILITY">Strength & Mobility</option></SelectField><Field label="Title" required value={draft.title} onChange={(event) => set('title', event.target.value)} /></div><TextAreaField label="Cleaned note" rows={7} required value={draft.cleaned_note} onChange={(event) => set('cleaned_note', event.target.value)} /><TextAreaField label="Short summary" rows={3} value={draft.summary} onChange={(event) => set('summary', event.target.value)} /><div className="form-grid two"><TextAreaField label="Key takeaways" rows={5} hint="One per line" value={draft.key_takeaways} onChange={(event) => set('key_takeaways', event.target.value)} /><TextAreaField label="Actionable ideas" rows={5} hint="One per line" value={draft.actionable_ideas} onChange={(event) => set('actionable_ideas', event.target.value)} /></div><Field label="Tags" value={draft.tags} onChange={(event) => set('tags', event.target.value)} hint="Comma-separated" /><details className="form-details"><summary>Source details</summary><div className="form-grid three"><Field label="Source title" value={draft.source_title} onChange={(event) => set('source_title', event.target.value)} /><Field label="Creator" value={draft.source_creator} onChange={(event) => set('source_creator', event.target.value)} /><Field label="Source URL" type="url" value={draft.source_url} onChange={(event) => set('source_url', event.target.value)} /></div></details><InlineNotice>Notes remain personal knowledge and are not used to calculate or alter training.</InlineNotice>{error && <InlineNotice tone="warning">{error}</InlineNotice>}<FormActions><Button type="button" variant="ghost" onClick={onBack}>Back</Button><Button type="submit" disabled={busy || !draft.title.trim() || !draft.cleaned_note.trim()}>{busy ? 'Saving…' : 'Save note'}</Button></FormActions></form>
}

function lines(value: string): string[] { return value.split('\n').map((line) => line.trim()).filter(Boolean) }

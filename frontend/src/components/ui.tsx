import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from 'react'
import { Icon, type IconName } from './Icon'
import type { Confidence, ReadinessLabel } from '../types'

export function PageHeader({ eyebrow, title, description, actions }: { eyebrow?: string; title: string; description?: string; actions?: ReactNode }): React.JSX.Element {
  return <header className="page-header">
    <div>
      {eyebrow && <p className="eyebrow">{eyebrow}</p>}
      <h1>{title}</h1>
      {description && <p className="page-description">{description}</p>}
    </div>
    {actions && <div className="page-actions">{actions}</div>}
  </header>
}

export function Card({ children, className = '', title, action, subtle = false }: { children: ReactNode; className?: string; title?: string; action?: ReactNode; subtle?: boolean }): React.JSX.Element {
  return <section className={`card ${subtle ? 'card-subtle' : ''} ${className}`}>
    {(title || action) && <div className="card-header">{title && <h2>{title}</h2>}{action}</div>}
    {children}
  </section>
}

export function Button({ children, variant = 'secondary', icon, className = '', ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'secondary' | 'ghost' | 'danger'; icon?: IconName }): React.JSX.Element {
  return <button className={`button button-${variant} ${className}`} {...props}>{icon && <Icon name={icon} size={17} />}{children}</button>
}

export function IconButton({ label, icon, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { label: string; icon: IconName }): React.JSX.Element {
  return <button className="icon-button" aria-label={label} title={label} {...props}><Icon name={icon} /></button>
}

export function Field({ label, hint, error, className = '', ...props }: InputHTMLAttributes<HTMLInputElement> & { label: string; hint?: string; error?: string }): React.JSX.Element {
  return <label className={`field ${className}`}><span className="field-label">{label}</span><input {...props} />{hint && <span className="field-hint">{hint}</span>}{error && <span className="field-error">{error}</span>}</label>
}

export function SelectField({ label, children, hint, className = '', ...props }: SelectHTMLAttributes<HTMLSelectElement> & { label: string; hint?: string; children: ReactNode }): React.JSX.Element {
  return <label className={`field ${className}`}><span className="field-label">{label}</span><select {...props}>{children}</select>{hint && <span className="field-hint">{hint}</span>}</label>
}

export function TextAreaField({ label, hint, className = '', ...props }: TextareaHTMLAttributes<HTMLTextAreaElement> & { label: string; hint?: string }): React.JSX.Element {
  return <label className={`field ${className}`}><span className="field-label">{label}</span><textarea {...props} />{hint && <span className="field-hint">{hint}</span>}</label>
}

export function Pill({ children, tone = 'neutral' }: { children: ReactNode; tone?: 'good' | 'moderate' | 'low' | 'neutral' | 'run' | 'climb' | 'info' }): React.JSX.Element {
  return <span className={`pill pill-${tone}`}>{children}</span>
}

export function ReadinessPill({ value }: { value: ReadinessLabel }): React.JSX.Element {
  return <Pill tone={value === 'GOOD' ? 'good' : value === 'LOW' ? 'low' : 'moderate'}>{value}</Pill>
}

export function ConfidencePill({ value }: { value?: Confidence | null }): React.JSX.Element {
  if (!value) return <Pill>UNRATED</Pill>
  return <Pill tone={value === 'HIGH' ? 'good' : value === 'LOW' ? 'low' : 'moderate'}>{value} CONF.</Pill>
}

export function Metric({ label, value, unit, detail }: { label: string; value: ReactNode; unit?: string; detail?: string }): React.JSX.Element {
  return <div className="metric"><span className="metric-label">{label}</span><div className="metric-value">{value}{unit && <span>{unit}</span>}</div>{detail && <span className="metric-detail">{detail}</span>}</div>
}

export function Meter({ value, max = 10, tone = 'accent', label }: { value: number; max?: number; tone?: 'accent' | 'run' | 'climb' | 'warning'; label?: string }): React.JSX.Element {
  const width = Math.max(0, Math.min(100, (value / max) * 100))
  return <div className="meter-wrap">{label && <span className="sr-only">{label}</span>}<div className="meter"><span className={`meter-fill meter-${tone}`} style={{ width: `${width}%` }} /></div><span className="meter-number">{value.toFixed(1)}</span></div>
}

export function Tabs<T extends string>({ value, onChange, items, label }: { value: T; onChange: (value: T) => void; items: readonly { value: T; label: string }[]; label: string }): React.JSX.Element {
  return <div className="tabs" role="tablist" aria-label={label}>{items.map((item) => <button key={item.value} type="button" role="tab" aria-selected={value === item.value} className={value === item.value ? 'active' : ''} onClick={() => onChange(item.value)}>{item.label}</button>)}</div>
}

export function ErrorPanel({ title = 'Unable to load data', message, onRetry }: { title?: string; message?: string; onRetry?: () => void }): React.JSX.Element {
  return <div className="error-panel" role="alert"><Icon name="warning" /><div><strong>{title}</strong><p>{message ?? 'Check that the local API is running. Your data has not been changed.'}</p></div>{onRetry && <Button variant="ghost" icon="refresh" onClick={onRetry}>Retry</Button>}</div>
}

export function EmptyState({ icon = 'activity', title, message, action }: { icon?: IconName; title: string; message: string; action?: ReactNode }): React.JSX.Element {
  return <div className="empty-state"><span className="empty-icon"><Icon name={icon} size={26} /></span><strong>{title}</strong><p>{message}</p>{action}</div>
}

export function LoadingGrid({ count = 3 }: { count?: number }): React.JSX.Element {
  return <div className="loading-grid" aria-label="Loading">{Array.from({ length: count }, (_, index) => <div className="skeleton" key={index} />)}</div>
}

export function Modal({ open, title, children, onClose, wide = false }: { open: boolean; title: string; children: ReactNode; onClose: () => void; wide?: boolean }): React.JSX.Element | null {
  if (!open) return null
  return <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}>
    <section className={`modal ${wide ? 'modal-wide' : ''}`} role="dialog" aria-modal="true" aria-label={title}>
      <div className="modal-header"><h2>{title}</h2><IconButton label="Close" icon="close" onClick={onClose} /></div>
      <div className="modal-body">{children}</div>
    </section>
  </div>
}

export function InlineNotice({ children, tone = 'info', title }: { children: ReactNode; tone?: 'info' | 'warning' | 'success'; title?: string }): React.JSX.Element {
  return <div className={`inline-notice notice-${tone}`}><Icon name={tone === 'warning' ? 'warning' : tone === 'success' ? 'check' : 'info'} /><div>{title && <strong>{title}</strong>}<div>{children}</div></div></div>
}

export function FormActions({ children }: { children: ReactNode }): React.JSX.Element {
  return <div className="form-actions">{children}</div>
}

export function SectionHeading({ title, description, action }: { title: string; description?: string; action?: ReactNode }): React.JSX.Element {
  return <div className="section-heading"><div><h2>{title}</h2>{description && <p>{description}</p>}</div>{action}</div>
}

export function formatEnum(value: string): string {
  return value.replaceAll('_', ' ').toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase())
}

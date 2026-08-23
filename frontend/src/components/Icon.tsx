import type { SVGProps } from 'react'

export type IconName =
  | 'today' | 'calendar' | 'state' | 'load' | 'progress' | 'workouts' | 'notes' | 'review' | 'settings'
  | 'menu' | 'close' | 'sun' | 'moon' | 'plus' | 'arrow' | 'run' | 'climb' | 'bolt' | 'warning'
  | 'check' | 'upload' | 'mic' | 'download' | 'database' | 'search' | 'chevron' | 'clock' | 'target'
  | 'refresh' | 'edit' | 'trash' | 'more' | 'heart' | 'brain' | 'activity' | 'info'

const paths: Record<IconName, React.ReactNode> = {
  today: <><path d="M4 5h16v15H4z"/><path d="M8 3v4m8-4v4M4 10h16"/></>,
  calendar: <><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4m10-4v4M3 10h18M8 14h.01M12 14h.01M16 14h.01M8 18h.01M12 18h.01"/></>,
  state: <><path d="M4 19V9m6 10V5m6 14v-7m4 7H2"/><circle cx="4" cy="7" r="2"/><circle cx="10" cy="3" r="2"/><circle cx="16" cy="10" r="2"/></>,
  load: <><path d="M3 12h3l2-6 4 12 3-9 2 3h4"/></>,
  progress: <><path d="m4 16 5-5 4 3 7-8"/><path d="M15 6h5v5"/></>,
  workouts: <><path d="M6 7v10m12-10v10M3 10v4m18-4v4M6 12h12"/></>,
  notes: <><path d="M5 3h11l3 3v15H5z"/><path d="M15 3v4h4M8 11h8M8 15h8M8 19h5"/></>,
  review: <><path d="M4 4h16v16H4z"/><path d="m8 12 2 2 5-5m-7 8h8"/></>,
  settings: <><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4V21a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H2.8v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1a1.7 1.7 0 0 0 1.9.3A1.7 1.7 0 0 0 10 3V2.8h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1Z"/></>,
  menu: <path d="M4 7h16M4 12h16M4 17h16"/>,
  close: <path d="m6 6 12 12M18 6 6 18"/>,
  sun: <><circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M4.9 4.9l1.4 1.4m11.4 11.4 1.4 1.4M2 12h2m16 0h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></>,
  moon: <path d="M20 15.3A8.5 8.5 0 0 1 8.7 4 8.5 8.5 0 1 0 20 15.3Z"/>,
  plus: <path d="M12 5v14M5 12h14"/>,
  arrow: <path d="m5 12 14 0m-5-5 5 5-5 5"/>,
  run: <><circle cx="14" cy="4" r="2"/><path d="m10 8 3 2 2 4 4 2M13 10l-3 4-5 2m5-2 2 6"/></>,
  climb: <><path d="M5 21 14 3l5 18"/><circle cx="12" cy="8" r="1"/><circle cx="9" cy="14" r="1"/><circle cx="15" cy="16" r="1"/></>,
  bolt: <path d="m13 2-8 12h7l-1 8 8-12h-7z"/>,
  warning: <><path d="M12 3 2.5 20h19z"/><path d="M12 9v5m0 3h.01"/></>,
  check: <path d="m5 12 4 4L19 6"/>,
  upload: <><path d="M12 16V4m-5 5 5-5 5 5"/><path d="M4 16v4h16v-4"/></>,
  mic: <><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3m-4 0h8"/></>,
  download: <><path d="M12 3v13m-5-5 5 5 5-5"/><path d="M4 20h16"/></>,
  database: <><ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v7c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 12v7c0 1.7 3.6 3 8 3s8-1.3 8-3v-7"/></>,
  search: <><circle cx="10" cy="10" r="6"/><path d="m15 15 5 5"/></>,
  chevron: <path d="m9 6 6 6-6 6"/>,
  clock: <><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></>,
  target: <><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/></>,
  refresh: <><path d="M20 11a8 8 0 0 0-14.8-4M4 3v5h5"/><path d="M4 13a8 8 0 0 0 14.8 4M20 21v-5h-5"/></>,
  edit: <><path d="m14 5 5 5L9 20H4v-5z"/><path d="m12 7 5 5"/></>,
  trash: <><path d="M4 7h16M9 7V4h6v3m3 0-1 14H7L6 7"/><path d="M10 11v6m4-6v6"/></>,
  more: <><circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/></>,
  heart: <path d="M20.8 5.7a5.5 5.5 0 0 0-7.8 0L12 6.8l-1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 22l8.8-8.5a5.5 5.5 0 0 0 0-7.8Z"/>,
  brain: <><path d="M9.5 4A3.5 3.5 0 0 0 6 7.5v1A3.5 3.5 0 0 0 4 15a3.5 3.5 0 0 0 5.5 4M14.5 4A3.5 3.5 0 0 1 18 7.5v1a3.5 3.5 0 0 1 2 6.5 3.5 3.5 0 0 1-5.5 4M12 4v16"/><path d="M8 10h4m0 5h4"/></>,
  activity: <path d="M3 12h4l2-7 5 14 3-7h4"/>,
  info: <><circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10h.01"/></>,
}

export function Icon({ name, size = 20, ...props }: SVGProps<SVGSVGElement> & { name: IconName; size?: number }): React.JSX.Element {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>{paths[name]}</svg>
}

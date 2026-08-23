import { useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { Icon, type IconName } from '../components/Icon'
import { IconButton, Pill } from '../components/ui'
import { useCapabilities } from './CapabilityProvider'
import { useTheme } from './ThemeProvider'

const navigation: { to: string; label: string; short: string; icon: IconName }[] = [
  { to: '/today', label: 'Today / Coach', short: 'Today', icon: 'today' },
  { to: '/calendar', label: 'Calendar', short: 'Calendar', icon: 'calendar' },
  { to: '/athlete-state', label: 'Athlete State', short: 'State', icon: 'state' },
  { to: '/load-readiness', label: 'Load & Readiness', short: 'Load', icon: 'load' },
  { to: '/progress', label: 'Progress', short: 'Progress', icon: 'progress' },
  { to: '/workouts', label: 'Workout Log', short: 'Log', icon: 'workouts' },
  { to: '/notes', label: 'Training Notes', short: 'Notes', icon: 'notes' },
  { to: '/weekly-review', label: 'Weekly Review', short: 'Review', icon: 'review' },
  { to: '/settings', label: 'Settings', short: 'Settings', icon: 'settings' },
]

function Logo(): React.JSX.Element {
  return <div className="logo-mark" aria-hidden="true"><span /><span /><span /></div>
}

export function AppShell(): React.JSX.Element {
  const [menuOpen, setMenuOpen] = useState(false)
  const { theme, toggleTheme } = useTheme()
  const { capabilities, connected } = useCapabilities()
  const mobilePrimary = navigation.filter((item) => ['/today', '/calendar', '/workouts'].includes(item.to))

  return <div className="app-shell">
    <aside className={`sidebar ${menuOpen ? 'sidebar-open' : ''}`}>
      <div className="brand"><Logo /><div><strong>ATC</strong><span>Adaptive Training</span></div><IconButton className="mobile-close" label="Close navigation" icon="close" onClick={() => setMenuOpen(false)} /></div>
      <nav className="side-nav" aria-label="Primary navigation">
        {navigation.map((item) => <NavLink key={item.to} to={item.to} onClick={() => setMenuOpen(false)} className={({ isActive }) => isActive ? 'active' : ''}><Icon name={item.icon} /><span>{item.label}</span></NavLink>)}
      </nav>
      <div className="sidebar-footer">
        <span className={`connection-dot ${connected ? 'connected' : ''}`} />
        <div><strong>{connected ? 'Local API connected' : 'API unavailable'}</strong><span>{capabilities.ai_configured ? 'AI tools enabled' : 'Core tools available'}</span></div>
      </div>
    </aside>
    {menuOpen && <button className="nav-scrim" aria-label="Close navigation" onClick={() => setMenuOpen(false)} />}

    <div className="main-column">
      <header className="topbar">
        <IconButton className="menu-button" label="Open navigation" icon="menu" onClick={() => setMenuOpen(true)} />
        <div className="mobile-brand"><Logo /><strong>ATC</strong></div>
        <div className="topbar-spacer" />
        <Pill tone={capabilities.ai_configured ? 'good' : 'neutral'}>{capabilities.ai_configured ? 'AI READY' : 'LOCAL CORE'}</Pill>
        <IconButton label={`Use ${theme === 'dark' ? 'light' : 'dark'} theme`} icon={theme === 'dark' ? 'sun' : 'moon'} onClick={toggleTheme} />
      </header>
      <main id="main-content"><Outlet /></main>
    </div>

    <nav className="mobile-nav" aria-label="Mobile navigation">
      {mobilePrimary.map((item) => <NavLink key={item.to} to={item.to} className={({ isActive }) => isActive ? 'active' : ''}><Icon name={item.icon} /><span>{item.short}</span></NavLink>)}
      <button type="button" onClick={() => setMenuOpen(true)}><Icon name="more" /><span>More</span></button>
    </nav>
  </div>
}

import { createContext, useContext, useMemo, type ReactNode } from 'react'
import { api } from '../api/client'
import { useResource } from '../api/hooks'
import type { ApiCapabilities } from '../types'

const unavailable: ApiCapabilities = {
  ai_configured: false,
  image_extraction: false,
  text_extraction: false,
  transcription: false,
  note_processing: false,
  ai_session_analysis: false,
  ai_adaptation: false,
  ai_weekly_review: false,
  ai_planner: false,
  reason: 'AI is not configured. Manual tools and the deterministic training engine remain available.',
}

interface CapabilityContextValue {
  capabilities: ApiCapabilities
  loading: boolean
  connected: boolean
  reload: () => void
}

const CapabilityContext = createContext<CapabilityContextValue | null>(null)

export function CapabilityProvider({ children }: { children: ReactNode }): React.JSX.Element {
  const resource = useResource(api.capabilities, [])
  const value = useMemo(() => ({ capabilities: resource.data ?? unavailable, loading: resource.loading, connected: !resource.error, reload: resource.reload }), [resource.data, resource.error, resource.loading, resource.reload])
  return <CapabilityContext.Provider value={value}>{children}</CapabilityContext.Provider>
}

export function useCapabilities(): CapabilityContextValue {
  const value = useContext(CapabilityContext)
  if (!value) throw new Error('useCapabilities must be used inside CapabilityProvider')
  return value
}

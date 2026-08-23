import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { App } from './app/App'
import { CapabilityProvider } from './app/CapabilityProvider'
import { ThemeProvider } from './app/ThemeProvider'
import './styles.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <ThemeProvider>
        <CapabilityProvider>
          <App />
        </CapabilityProvider>
      </ThemeProvider>
    </BrowserRouter>
  </StrictMode>,
)

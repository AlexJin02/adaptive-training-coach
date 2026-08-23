import { Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from './AppShell'
import { TodayPage } from '../pages/TodayPage'
import { CalendarPage } from '../pages/CalendarPage'
import { AthleteStatePage } from '../pages/AthleteStatePage'
import { LoadReadinessPage } from '../pages/LoadReadinessPage'
import { ProgressPage } from '../pages/ProgressPage'
import { WorkoutLogPage } from '../pages/WorkoutLogPage'
import { TrainingNotesPage } from '../pages/TrainingNotesPage'
import { WeeklyReviewPage } from '../pages/WeeklyReviewPage'
import { SettingsPage } from '../pages/SettingsPage'

export function App(): React.JSX.Element {
  return <Routes>
    <Route element={<AppShell />}>
      <Route index element={<Navigate to="/today" replace />} />
      <Route path="today" element={<TodayPage />} />
      <Route path="calendar" element={<CalendarPage />} />
      <Route path="athlete-state" element={<AthleteStatePage />} />
      <Route path="load-readiness" element={<LoadReadinessPage />} />
      <Route path="progress" element={<ProgressPage />} />
      <Route path="workouts" element={<WorkoutLogPage />} />
      <Route path="notes" element={<TrainingNotesPage />} />
      <Route path="review-plan" element={<WeeklyReviewPage />} />
      <Route path="weekly-review" element={<Navigate to="/review-plan" replace />} />
      <Route path="settings" element={<SettingsPage />} />
      <Route path="*" element={<Navigate to="/today" replace />} />
    </Route>
  </Routes>
}

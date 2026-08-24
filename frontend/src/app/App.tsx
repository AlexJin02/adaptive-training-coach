import { Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from './AppShell'
import { CalendarPage } from '../pages/CalendarPage'
import { ProgressPage } from '../pages/ProgressPage'
import { WorkoutLogPage } from '../pages/WorkoutLogPage'
import { TrainingNotesPage } from '../pages/TrainingNotesPage'
import { SettingsPage } from '../pages/SettingsPage'
import { TrainingReportsPage } from '../pages/TrainingReportsPage'
import { PlanImportPage } from '../pages/PlanImportPage'
import { TodayPage } from '../pages/TodayPage'

export function App(): React.JSX.Element {
  return <Routes>
    <Route element={<AppShell />}>
      <Route index element={<Navigate to="/today" replace />} />
      <Route path="quick-log" element={<Navigate to="/today" replace />} />
      <Route path="calendar" element={<CalendarPage />} />
      <Route path="progress" element={<ProgressPage />} />
      <Route path="workouts" element={<WorkoutLogPage />} />
      <Route path="reports" element={<TrainingReportsPage />} />
      <Route path="plans" element={<PlanImportPage />} />
      <Route path="notes" element={<TrainingNotesPage />} />
      <Route path="today" element={<TodayPage />} />
      <Route path="athlete-state" element={<Navigate to="/progress" replace />} />
      <Route path="load-readiness" element={<Navigate to="/progress" replace />} />
      <Route path="review-plan" element={<Navigate to="/reports" replace />} />
      <Route path="weekly-review" element={<Navigate to="/reports" replace />} />
      <Route path="settings" element={<SettingsPage />} />
      <Route path="*" element={<Navigate to="/today" replace />} />
    </Route>
  </Routes>
}

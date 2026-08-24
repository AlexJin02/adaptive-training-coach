export type Sport = 'RUNNING' | 'CLIMBING'
export type RunningSessionType = 'EASY' | 'LONG_RUN' | 'QUALITY' | 'RACE'
export type ClimbingSessionType = 'BOULDERING' | 'SPORT_CLIMBING' | 'BOARD'
export type WorkoutKind = Sport | 'STRENGTH' | 'CROSSFIT_CONDITIONING' | 'MOBILITY_RECOVERY'
export type Confidence = 'LOW' | 'MODERATE' | 'HIGH'
export type ReadinessLabel = 'GOOD' | 'MODERATE' | 'LOW'
export type SessionStatus = 'PLANNED' | 'COMPLETED' | 'MODIFIED' | 'SKIPPED' | 'MOVED' | 'REPLACED' | 'REST' | 'CANCELLED'
export type AdaptationAction = 'KEEP' | 'REDUCE_VOLUME' | 'REDUCE_INTENSITY' | 'MOVE' | 'REPLACE' | 'ADD_RECOVERY' | 'PROGRESS'
export type AdaptationSource = 'RULE_ENGINE' | 'AI' | 'MANUAL'
export type GoalType = 'RUNNING_MILEAGE' | 'HALF_MARATHON' | 'MARATHON' | 'BOULDERING' | 'LEAD_CLIMBING'
export type RunningPhase = 'AEROBIC_BASE' | 'VOLUME_BUILD' | 'THRESHOLD_BUILD' | 'HALF_MARATHON_SPECIFIC' | 'MARATHON_SPECIFIC' | 'TAPER' | 'RECOVERY_TRANSITION'
export type ClimbingPhase = 'TECHNIQUE_VOLUME' | 'LIMIT_BOULDERING' | 'MAX_STRENGTH' | 'POWER' | 'POWER_ENDURANCE' | 'LEAD_SPECIFIC' | 'PERFORMANCE' | 'RECOVERY'
export type FatigueDomain = 'CARDIOVASCULAR' | 'LOWER_BODY' | 'FINGER_FOREARM' | 'PULLING_UPPER_BODY' | 'NEURAL' | 'SYSTEMIC'
export type NoteCategory = 'RUNNING' | 'CLIMBING' | 'STRENGTH_MOBILITY'

export interface ApiCapabilities {
  ai_configured: boolean
  image_extraction: boolean
  text_extraction: boolean
  transcription: boolean
  note_processing: boolean
  ai_session_analysis: boolean
  ai_adaptation: boolean
  ai_weekly_review: boolean
  ai_planner: boolean
  model?: string | null
  planner_model?: string | null
  vision_model?: string | null
  transcription_model?: string | null
  strava_sync_configured?: boolean
  strava_sync_reason?: string | null
  reason?: string | null
}

export interface Goal {
  id: number | string
  goal_type: GoalType
  description: string
  target_value?: string | null
  target_date?: string | null
  current_status?: string | null
  notes?: string | null
  is_current?: boolean
}

export interface AthleteProfile {
  id?: number | string
  display_name: string
  timezone: string
  current_half_marathon_seconds?: number | null
  current_monthly_km?: number | null
  long_term_monthly_km?: number | null
  stable_weekly_min_km?: number | null
  stable_weekly_max_km?: number | null
  half_marathon_primary_goal_seconds?: number | null
  half_marathon_stretch_goal_seconds?: number | null
  marathon_goal_seconds?: number | null
  tb2_verified_grade?: string | null
  tb2_estimated_grade?: string | null
  top_rope_grade?: string | null
  tb2_long_term_goal?: string | null
  outdoor_boulder_goal?: string | null
  /** Legacy API alias for tb2_long_term_goal. */
  bouldering_goal?: string | null
  route_goal?: string | null
  running_phase: RunningPhase
  climbing_phase: ClimbingPhase
}

export interface PlannedSession {
  id: number | string
  date: string
  start_time?: string | null
  workout_kind: WorkoutKind
  session_type: string
  title: string
  description?: string | null
  planned_duration_minutes?: number | null
  planned_distance_km?: number | null
  target_rpe?: number | null
  priority?: 'LOW' | 'NORMAL' | 'HIGH'
  status: SessionStatus
  original_session_id?: number | string | null
  is_demo?: boolean
  is_locked?: boolean
  structured_blocks?: Array<Record<string, unknown>>
}

export interface CompletedSession {
  id: number | string
  date: string
  start_time?: string | null
  workout_kind: WorkoutKind
  session_type: string
  title?: string | null
  duration_minutes: number
  distance_km?: number | null
  rpe?: number | null
  srpe_load?: number | null
  average_pace_seconds_per_km?: number | null
  average_hr?: number | null
  max_hr?: number | null
  elevation_m?: number | null
  cadence?: number | null
  power_w?: number | null
  gym_or_crag?: string | null
  board_name?: string | null
  angle?: number | null
  hard_attempts?: number | null
  max_attempted?: string | null
  max_sent?: string | null
  workout_name?: string | null
  rounds?: number | null
  result_time_seconds?: number | null
  splits?: Array<Record<string, unknown>>
  interval_blocks?: Array<Record<string, unknown>>
  climbing_attempts?: Array<Record<string, unknown>>
  strength_sets?: Array<Record<string, unknown>>
  strength?: {
    workout_name?: string | null
    rounds?: number | null
    result_time_seconds?: number | null
    sets?: Array<Record<string, unknown>>
  } | null
  notes?: string | null
  planned_session_id?: number | string | null
  ai_analysis?: Record<string, unknown> | null
  subjective_feedback_text?: string | null
  subjective_feedback_source?: 'VOICE' | 'TEXT' | 'NONE'
  subjective_feedback_created_at?: string | null
  is_demo?: boolean
}

export interface StravaRunLap {
  lap_index: number
  distance_km: number
  elapsed_time_seconds?: number | null
  pace_seconds_per_km?: number | null
  average_hr?: number | null
  cadence?: number | null
}

export interface ImportedRunningActivity {
  id: number
  provider: 'STRAVA'
  external_activity_id: string
  date: string
  start_time?: string | null
  title: string
  suggested_session_type: RunningSessionType
  distance_km: number
  elapsed_time_seconds: number
  moving_time_seconds?: number | null
  average_pace_seconds_per_km?: number | null
  average_hr?: number | null
  max_hr?: number | null
  elevation_m?: number | null
  cadence?: number | null
  laps: StravaRunLap[]
  best_efforts?: Array<{ name: string; distance_m: number; elapsed_time_seconds: number; moving_time_seconds?: number | null }>
  detail_synced_at?: string | null
  needs_review: boolean
  planned_session?: PlannedSession | null
  completed_session_id?: number | null
  imported_at: string
}

export interface CalendarEntry {
  id: string
  date: string
  planned?: PlannedSession | null
  completed?: CompletedSession | null
  status: SessionStatus
}

export interface ParsedPlanSession {
  date: string
  day: string
  session_number: number
  workout_kind: WorkoutKind
  session_type: string
  title: string
  planned_distance_km?: number | null
  planned_duration_minutes?: number | null
  target_rpe_min?: number | null
  target_rpe_max?: number | null
  target_rpe?: number | null
  description: string
  notes: string
  structured_blocks: Array<Record<string, unknown>>
  raw_workout_text: string
  status: SessionStatus
  board_name?: string | null
  angle?: number | null
}

export interface MonthlyWeekTarget {
  week: number
  distance_km: number
}

export interface MonthlySessionStructureItem {
  session_type: string
  sessions_per_week: number
}

export interface MonthlyPlanContent {
  month: string
  running: {
    phase: string
    monthly_objective: string
    sessions_per_week: number | null
    session_structure: MonthlySessionStructureItem[]
    weekly_distance_targets: MonthlyWeekTarget[]
    quality_guidance: string
    long_run_guidance: string
    long_run_targets: MonthlyWeekTarget[]
    key_principles: string[]
    other_notes: string
  }
  climbing: {
    phase: string
    sessions_per_week: number | null
    target_structure: MonthlySessionStructureItem[]
    board_focus: string
    key_principles: string[]
    other_notes: string
  }
  auxiliary: {
    strength: string
    mobility: string
  }
  general_notes: string
  raw_plan_text: string
}

export interface MonthlyTrainingBlock {
  id: number
  month_start: string
  month_end: string
  content: MonthlyPlanContent
  status: string
}

export interface PlanParsePreview {
  cadence: 'WEEKLY' | 'MONTHLY'
  period_start: string
  period_end: string
  sessions?: ParsedPlanSession[]
  block?: MonthlyPlanContent
  warnings: string[]
  can_import: boolean
  import_id?: number
  imported_session_ids?: number[]
}

export interface ReadinessComponent {
  domain: FatigueDomain | 'LOCAL_SORENESS'
  value: number
  label: ReadinessLabel
}

export interface ReadinessSummary {
  sport: Sport
  value?: number | null
  label: ReadinessLabel
  components: ReadinessComponent[]
  updated_at?: string | null
  explanation?: string | null
  subjective_delta?: number | null
  local_soreness_penalty?: number | null
  warnings?: string[]
}

export interface FatigueValue {
  domain: FatigueDomain
  latent_value: number
  display_value: number
  display_label?: string | null
  is_high?: boolean
  half_life_hours?: number | null
  updated_at?: string | null
}

export interface AdaptationProposal {
  id: number | string
  session_id: number | string
  session_title: string
  action: AdaptationAction
  original_plan: Record<string, unknown> | string
  proposed_plan: Record<string, unknown> | string
  reason: string
  evidence: string[]
  confidence: Confidence
  source: AdaptationSource
  status?: 'PENDING' | 'ACCEPTED' | 'REJECTED' | 'EDITED'
  created_at?: string
}

export interface TodayDashboard {
  date: string
  sessions: CalendarEntry[]
  imported_runs: ImportedRunningActivity[]
}

export interface Estimate<T> {
  value?: T | null
  confidence?: Confidence | null
  source?: string | null
  source_date?: string | null
  formula?: string | null
  evidence?: string[]
}

export interface RunningState {
  current_month_km: number
  previous_month_km: number
  rolling_7d_km: number
  rolling_28d_km: number
  rolling_28d_weekly_average_km: number
  estimated_10k: Estimate<number>
  lt1_pace_range?: [number, number] | null
  lt1_hr_range?: [number, number] | null
  lt1_confidence?: Confidence | null
  lt1_source?: string | null
  lt2_pace_seconds_per_km?: number | null
  lt2_hr?: number | null
  lt2_confidence?: Confidence | null
  lt2_source?: string | null
  lt2_updated_at?: string | null
  phase: RunningPhase
  current_capacity_km?: number | null
  current_block_min_km?: number | null
  current_block_max_km?: number | null
  long_term_min_km?: number | null
  long_term_max_km?: number | null
  progression_decision?: 'BUILD' | 'HOLD' | 'DELOAD' | null
  progression_evidence?: string[]
}

export interface TB2Benchmark {
  id: number | string
  date: string
  board: 'TB2'
  angle: number
  verified_grade: string
  estimated_grade?: string | null
  notes?: string | null
  is_demo?: boolean
}

export interface GymColourProgress {
  colour: 'Yellow' | 'Green' | 'Purple' | 'Grey' | 'Blue' | 'Red' | 'Black'
  ordinal: number
  sent_count: number
  available_problem_count?: number | null
}

export interface GymSet {
  id: number | string
  gym: string
  start_date: string
  end_date?: string | null
  notes?: string | null
  progress: GymColourProgress[]
  is_demo?: boolean
}

export interface RouteBenchmark {
  top_rope_verified_grade?: string | null
  lead_verified_grade?: string | null
  target_grade?: string | null
  last_updated?: string | null
}

export interface ClimbingState {
  phase: ClimbingPhase
  latest_tb2?: TB2Benchmark | null
  current_gym_set?: GymSet | null
  route_benchmark?: RouteBenchmark | null
}

export interface RecoveryCheckIn {
  id?: number | string
  date: string
  sleep_duration_hours?: number | null
  sleep_quality?: number | null
  energy?: number | null
  motivation?: number | null
  stress?: number | null
  general_soreness?: number | null
  soreness?: Partial<Record<'finger' | 'elbow' | 'shoulder' | 'back' | 'hip' | 'knee' | 'calf' | 'ankle', number>>
  resting_hr?: number | null
  hrv?: number | null
}

export interface SeriesPoint {
  date: string
  value: number
  secondary?: number | null
  label?: string
  confidence?: Confidence | null
  source?: string
  external_activity_id?: string
  activity_average_hr?: number | null
  heart_rate_band?: string
  sample_count?: number
}

export interface ProgressData {
  running: {
    monthly_mileage: SeriesPoint[]
    weekly_mileage: SeriesPoint[]
    rolling_volume: SeriesPoint[]
    run_frequency: number
    sessions_by_type: Array<{ label: string; value: number }>
    easy_efficiency: SeriesPoint[]
    easy_efficiency_band?: string | null
    easy_efficiency_warning?: string | null
  }
  climbing: {
    tb2_benchmarks: TB2Benchmark[]
    gym_sets: GymSet[]
    session_count: number
    total_duration_minutes: number
    weekly_sessions: SeriesPoint[]
    monthly_sessions: SeriesPoint[]
    sessions_by_type: Array<{ label: string; value: number }>
    grade_attempts: Array<{ label: string; value: number }>
    grade_sends: Array<{ label: string; value: number }>
  }
}

export interface TrainingNote {
  id: number | string
  created_at: string
  updated_at?: string
  primary_category: NoteCategory
  title: string
  raw_input: string
  cleaned_note: string
  summary: string
  key_takeaways: string[]
  actionable_ideas: string[]
  tags: string[]
  source_title?: string | null
  source_creator?: string | null
  source_url?: string | null
  input_type: 'TEXT' | 'VOICE'
  classification_confidence?: Confidence | null
  use_for_coaching: boolean
  favorite?: boolean
  is_demo?: boolean
}

export interface WeeklyReview {
  id: number | string
  week_start: string
  status?: 'DRAFT' | 'GENERATED' | 'FINAL'
  summary: {
    total_training_minutes: number
    running_distance_km: number
    climbing_minutes: number
    strength_sessions: number
    rest_days: number
  }
  compliance: Record<'planned' | 'completed' | 'modified' | 'skipped' | 'extra', number>
  running: string[]
  climbing: string[]
  recovery: string[]
  key_findings: string[]
  next_week: string[]
  source?: AdaptationSource
}

export interface ReviewPlanProposal {
  id: number | string
  cadence: 'WEEKLY' | 'MONTHLY'
  period_start: string
  period_end: string
  target_start: string
  target_end: string
  deterministic_summary: Record<string, unknown>
  review: {
    summary: string
    running_analysis: string
    climbing_analysis: string
    recovery_analysis: string
    goal_progress?: string
    key_findings: string[]
  }
  proposed_plan: WeeklyPlanPreview | MonthlyBlockPreview
  status: 'PREVIEW' | 'APPROVED' | 'CANCELLED'
  source: 'AI'
  model?: string | null
  approval_result?: Record<string, unknown>
  created_at: string
  approved_at?: string | null
}

export interface WeeklyPlanPreview {
  summary: string
  running_target_km: number
  running_objectives: string[]
  climbing_objectives: string[]
  sessions: Array<{
    date: string
    start_time?: string | null
    workout_kind: WorkoutKind
    session_type: string
    title: string
    description: string
    planned_duration_minutes?: number | null
    planned_distance_km?: number | null
    target_rpe?: number | null
    priority: 'LOW' | 'NORMAL' | 'HIGH'
    structured_blocks: Array<Record<string, unknown>>
  }>
  warnings: string[]
}

export interface MonthlyBlockPreview {
  running_phase: string
  climbing_phase: string
  running_objectives: string[]
  climbing_objectives: string[]
  weekly_running_volume_targets: number[]
  quality_session_guidance: string
  long_run_guidance: string
  climbing_frequency_guidance: string
  climbing_focus: string[]
  supporting_strength_guidance: string
  progression_criteria: string[]
  hold_criteria: string[]
  deload_criteria: string[]
}

export interface ExtractionField<T = string | number | null> {
  value: T
  confidence: Confidence
  source: string
}

export interface WorkoutExtraction {
  workout_kind: ExtractionField<WorkoutKind | null>
  activity_type: ExtractionField<string | null>
  session_type: ExtractionField<string | null>
  title: ExtractionField<string | null>
  date: ExtractionField<string | null>
  distance_km: ExtractionField<number | null>
  duration_minutes: ExtractionField<number | null>
  rpe: ExtractionField<number | null>
  average_pace: ExtractionField<string | null>
  average_hr: ExtractionField<number | null>
  max_hr: ExtractionField<number | null>
  elevation_m: ExtractionField<number | null>
  cadence: ExtractionField<number | null>
  power_w: ExtractionField<number | null>
  board_name: ExtractionField<string | null>
  angle: ExtractionField<number | null>
  splits: ExtractionField<string[] | null>
  intervals: ExtractionField<string[] | null>
  notes?: ExtractionField<string | null>
}

export interface ApiList<T> {
  items: T[]
  total?: number
}

export interface AppSettings {
  gym_name: string
  grade_display: 'FONT' | 'V_SCALE' | 'BOTH'
  retain_screenshots: boolean
  retain_audio: boolean
  database_path?: string | null
  demo_data_present?: boolean
  engine: {
    base_stress_divisor: number
    base_stress_cap: number
    hard_attempt_threshold: number
    hard_attempt_increment: number
    hard_attempt_cap: number
    readiness_good_threshold: number
    readiness_moderate_threshold: number
    half_lives: Record<FatigueDomain, number>
  }
}

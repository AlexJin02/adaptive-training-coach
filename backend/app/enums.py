from enum import StrEnum


class Sport(StrEnum):
    RUNNING = "RUNNING"
    CLIMBING = "CLIMBING"
    STRENGTH = "STRENGTH"
    CROSSFIT_CONDITIONING = "CROSSFIT_CONDITIONING"
    MOBILITY_RECOVERY = "MOBILITY_RECOVERY"


class GoalType(StrEnum):
    RUNNING_MILEAGE = "RUNNING_MILEAGE"
    HALF_MARATHON = "HALF_MARATHON"
    MARATHON = "MARATHON"
    BOULDERING = "BOULDERING"
    LEAD_CLIMBING = "LEAD_CLIMBING"


class RunningPhase(StrEnum):
    AEROBIC_BASE = "AEROBIC_BASE"
    VOLUME_BUILD = "VOLUME_BUILD"
    THRESHOLD_BUILD = "THRESHOLD_BUILD"
    HALF_MARATHON_SPECIFIC = "HALF_MARATHON_SPECIFIC"
    MARATHON_SPECIFIC = "MARATHON_SPECIFIC"
    TAPER = "TAPER"
    RECOVERY_TRANSITION = "RECOVERY_TRANSITION"


class ClimbingPhase(StrEnum):
    TECHNIQUE_VOLUME = "TECHNIQUE_VOLUME"
    LIMIT_BOULDERING = "LIMIT_BOULDERING"
    MAX_STRENGTH = "MAX_STRENGTH"
    POWER = "POWER"
    POWER_ENDURANCE = "POWER_ENDURANCE"
    LEAD_SPECIFIC = "LEAD_SPECIFIC"
    PERFORMANCE = "PERFORMANCE"
    RECOVERY = "RECOVERY"


class RunningWorkoutType(StrEnum):
    EASY = "Easy"
    RECOVERY = "Recovery"
    LONG_RUN = "Long Run"
    STEADY = "Steady"
    PROGRESSION = "Progression"
    THRESHOLD = "Threshold"
    TEMPO = "Tempo"
    CRUISE_INTERVALS = "Cruise Intervals"
    VO2MAX = "VO2max"
    INTERVALS = "Intervals"
    HILL_REPEATS = "Hill Repeats"
    FARTLEK = "Fartlek"
    STRIDES = "Strides"
    HM_PACE = "HM Pace"
    MARATHON_PACE = "Marathon Pace"
    TIME_TRIAL = "Time Trial"
    RACE = "Race"


class ClimbingWorkoutType(StrEnum):
    BOULDERING = "Bouldering"
    TENSION_BOARD = "Tension Board"
    SPORT_LEAD = "Sport / Lead"
    TOP_ROPE = "Top Rope"
    TECHNIQUE = "Technique"
    LIMIT_BOULDERING = "Limit Bouldering"
    POWER = "Power"
    POWER_ENDURANCE = "Power Endurance"
    EASY_VOLUME = "Easy Volume"
    OUTDOOR = "Outdoor"


class FatigueDomain(StrEnum):
    CARDIOVASCULAR = "CARDIOVASCULAR"
    LOWER_BODY = "LOWER_BODY"
    FINGER_FOREARM = "FINGER_FOREARM"
    PULLING_UPPER_BODY = "PULLING_UPPER_BODY"
    NEURAL = "NEURAL"
    SYSTEMIC = "SYSTEMIC"


class ReadinessLabel(StrEnum):
    GOOD = "GOOD"
    MODERATE = "MODERATE"
    LOW = "LOW"


class Confidence(StrEnum):
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"


class PlanStatus(StrEnum):
    PLANNED = "PLANNED"
    COMPLETED = "COMPLETED"
    MODIFIED = "MODIFIED"
    SKIPPED = "SKIPPED"
    MOVED = "MOVED"
    REPLACED = "REPLACED"
    REST = "REST"


class SessionPriority(StrEnum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"


class AdaptationAction(StrEnum):
    KEEP = "KEEP"
    REDUCE_VOLUME = "REDUCE_VOLUME"
    REDUCE_INTENSITY = "REDUCE_INTENSITY"
    MOVE = "MOVE"
    REPLACE = "REPLACE"
    ADD_RECOVERY = "ADD_RECOVERY"
    PROGRESS = "PROGRESS"


class AdaptationSource(StrEnum):
    RULE_ENGINE = "RULE_ENGINE"
    AI = "AI"
    MANUAL = "MANUAL"


class AdaptationDecision(StrEnum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    EDITED = "EDITED"


class NoteCategory(StrEnum):
    RUNNING = "RUNNING"
    CLIMBING = "CLIMBING"
    STRENGTH_MOBILITY = "STRENGTH_MOBILITY"


class NoteInputType(StrEnum):
    TEXT = "TEXT"
    VOICE = "VOICE"


class EstimateType(StrEnum):
    LT1 = "LT1"
    LT2 = "LT2"


class MediaKind(StrEnum):
    SCREENSHOT = "SCREENSHOT"
    AUDIO = "AUDIO"
    TEXT = "TEXT"


class MediaStatus(StrEnum):
    UPLOADED = "UPLOADED"
    EXTRACTED = "EXTRACTED"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"
    DELETED = "DELETED"

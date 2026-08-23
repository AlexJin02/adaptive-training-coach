from datetime import UTC, date, datetime, timedelta

import pytest

from app.enums import FatigueDomain, ReadinessLabel, SessionPriority, Sport
from app.training_engine.adaptation import (
    AdaptationContext,
    CompletedEvidence,
    PlannedWorkout,
    propose_adaptations,
)
from app.training_engine.fatigue import StressEvent, calculate_fatigue, decay
from app.training_engine.progression import decide_mileage_target, mileage_progression_band
from app.training_engine.readiness import (
    RecoveryInputs,
    calculate_readiness,
    normalized_subjective_values,
    subjective_recovery_delta,
)
from app.training_engine.session_load import calculate_session_load, hard_attempt_multiplier


def blank_fatigue() -> dict[FatigueDomain, float]:
    return {domain: 0.0 for domain in FatigueDomain}


def test_srpe_and_base_stress_formula() -> None:
    result = calculate_session_load(
        sport=Sport.RUNNING,
        workout_type="Easy",
        duration_minutes=52,
        rpe=3,
    )
    assert result.srpe_load == 156
    assert result.base_stress == pytest.approx(156 / 90)
    cardio = next(
        item for item in result.domain_stresses if item.domain == FatigueDomain.CARDIOVASCULAR
    )
    assert cardio.stress == pytest.approx((156 / 90) * 0.70)


def test_missing_rpe_is_not_imputed() -> None:
    result = calculate_session_load(
        sport=Sport.RUNNING, workout_type="Easy", duration_minutes=45, rpe=None
    )
    assert result.srpe_load is None
    assert result.base_stress is None
    assert result.domain_stresses == ()


def test_rpe_must_be_on_the_one_to_ten_scale() -> None:
    with pytest.raises(ValueError, match="between 1 and 10"):
        calculate_session_load(
            sport=Sport.RUNNING,
            workout_type="Easy",
            duration_minutes=45,
            rpe=0,
        )


def test_climbing_long_limit_session_creates_high_finger_and_neural_stress() -> None:
    result = calculate_session_load(
        sport=Sport.CLIMBING,
        workout_type="Limit Bouldering",
        duration_minutes=145,
        rpe=9,
        hard_attempts=22,
    )
    by_domain = {item.domain: item.stress for item in result.domain_stresses}
    assert result.base_stress == 10
    assert hard_attempt_multiplier(22) == pytest.approx(1.18)
    assert by_domain[FatigueDomain.FINGER_FOREARM] == pytest.approx(11.8)
    assert by_domain[FatigueDomain.NEURAL] == pytest.approx(11.8)


def test_hard_attempt_multiplier_is_capped() -> None:
    assert hard_attempt_multiplier(1000) == 1.25


def test_strength_combination_detects_lower_and_pulling_interference() -> None:
    result = calculate_session_load(
        sport=Sport.STRENGTH,
        workout_type="Strength",
        duration_minutes=75,
        rpe=8,
        exercises=["Heavy deadlift", "Weighted pull-up"],
    )
    coefficients = {item.domain: item.coefficient for item in result.domain_stresses}
    assert coefficients[FatigueDomain.LOWER_BODY] >= 0.9
    assert coefficients[FatigueDomain.PULLING_UPPER_BODY] == 1.0


def test_fatigue_exact_half_life_and_no_latent_cap() -> None:
    now = datetime(2026, 8, 23, 12, tzinfo=UTC)
    result = calculate_fatigue(
        [
            StressEvent(
                occurred_at=now - timedelta(hours=36),
                stresses={FatigueDomain.FINGER_FOREARM: 24.0},
            )
        ],
        as_of=now,
    )
    assert decay(24, 36, 36) == 12
    assert result.latent[FatigueDomain.FINGER_FOREARM] == pytest.approx(12)
    assert result.display[FatigueDomain.FINGER_FOREARM] == 10


def test_subjective_normalization_and_available_weight_mean() -> None:
    inputs = RecoveryInputs(
        sleep_duration_hours=5,
        sleep_quality=1,
        energy=1,
        stress=5,
        general_soreness=10,
    )
    assert set(normalized_subjective_values(inputs).values()) == {-1}
    assert subjective_recovery_delta(inputs) == -1
    assert subjective_recovery_delta(RecoveryInputs(energy=5)) == 0.75


def test_readiness_weights_labels_and_finger_soreness_cap() -> None:
    fatigue = blank_fatigue()
    fatigue[FatigueDomain.CARDIOVASCULAR] = 4
    fatigue[FatigueDomain.LOWER_BODY] = 4
    normal = calculate_readiness(fatigue)
    assert normal.running_score == pytest.approx(7.2)
    assert normal.running_label == ReadinessLabel.MODERATE

    sore = calculate_readiness(fatigue, RecoveryInputs(area_soreness={"finger": 7}))
    assert sore.climbing_score < 5
    assert sore.climbing_label == ReadinessLabel.LOW


def test_running_scenario_one_strong_execution_does_not_immediately_progress() -> None:
    trigger = CompletedEvidence(
        id=1,
        session_date=date(2026, 8, 23),
        sport=Sport.RUNNING,
        workout_type="Intervals",
        duration_minutes=64,
        rpe=7,
        planned_duration_minutes=60,
        target_rpe_max=8,
        pre_session_readiness=8,
    )
    upcoming = PlannedWorkout(
        id=2,
        session_date=date(2026, 8, 27),
        sport=Sport.RUNNING,
        workout_type="Intervals",
        title="Quality intervals",
        duration_minutes=60,
        target_rpe_max=8,
    )
    proposals = propose_adaptations(
        AdaptationContext(
            trigger=trigger,
            upcoming=(upcoming,),
            latent_fatigue=blank_fatigue(),
            running_readiness=ReadinessLabel.GOOD,
            climbing_readiness=ReadinessLabel.GOOD,
        )
    )
    assert proposals[0].action.value == "KEEP"
    assert "one result" in proposals[0].reason.lower()


def test_running_scenario_two_two_successes_allow_single_variable_progression() -> None:
    earlier = CompletedEvidence(
        id=1,
        session_date=date(2026, 8, 12),
        sport=Sport.RUNNING,
        workout_type="Threshold",
        duration_minutes=60,
        rpe=7,
        planned_duration_minutes=60,
        target_rpe_max=8,
        pre_session_readiness=7.5,
    )
    trigger = CompletedEvidence(
        id=2,
        session_date=date(2026, 8, 23),
        sport=Sport.RUNNING,
        workout_type="Threshold",
        duration_minutes=60,
        rpe=7,
        planned_duration_minutes=60,
        target_rpe_max=8,
        pre_session_readiness=8,
    )
    upcoming = PlannedWorkout(
        id=3,
        session_date=date(2026, 8, 27),
        sport=Sport.RUNNING,
        workout_type="Threshold",
        title="Threshold",
        duration_minutes=60,
    )
    proposal = propose_adaptations(
        AdaptationContext(
            trigger=trigger,
            upcoming=(upcoming,),
            latent_fatigue=blank_fatigue(),
            running_readiness=ReadinessLabel.GOOD,
            climbing_readiness=ReadinessLabel.GOOD,
            comparable_history=(earlier,),
        )
    )[0]
    assert proposal.action.value == "PROGRESS"
    assert proposal.proposed_changes["progressed_variable"] == "volume"
    assert "target_rpe_max" not in proposal.proposed_changes


def test_medium_finger_soreness_blocks_finger_demand_progression() -> None:
    earlier = CompletedEvidence(
        id=1,
        session_date=date(2026, 8, 12),
        sport=Sport.CLIMBING,
        workout_type="Limit Bouldering",
        duration_minutes=60,
        rpe=7,
        planned_duration_minutes=60,
        target_rpe_max=8,
        pre_session_readiness=7.5,
    )
    trigger = CompletedEvidence(
        id=2,
        session_date=date(2026, 8, 23),
        sport=Sport.CLIMBING,
        workout_type="Limit Bouldering",
        duration_minutes=60,
        rpe=7,
        planned_duration_minutes=60,
        target_rpe_max=8,
        pre_session_readiness=8,
        area_soreness={"finger": 4},
    )
    upcoming = PlannedWorkout(
        id=3,
        session_date=date(2026, 8, 27),
        sport=Sport.CLIMBING,
        workout_type="Limit Bouldering",
        title="Limit bouldering",
        duration_minutes=60,
    )
    proposal = propose_adaptations(
        AdaptationContext(
            trigger=trigger,
            upcoming=(upcoming,),
            latent_fatigue=blank_fatigue(),
            running_readiness=ReadinessLabel.GOOD,
            climbing_readiness=ReadinessLabel.GOOD,
            comparable_history=(earlier,),
        )
    )[0]
    assert proposal.action.value == "KEEP"
    assert "Finger soreness 4/10" in proposal.evidence[0]


@pytest.mark.parametrize("area", ["elbow", "shoulder"])
def test_high_upper_joint_soreness_blocks_overlapping_climbing_progression(area: str) -> None:
    earlier = CompletedEvidence(
        id=1,
        session_date=date(2026, 8, 12),
        sport=Sport.CLIMBING,
        workout_type="Limit Bouldering",
        duration_minutes=60,
        rpe=7,
        target_rpe_max=8,
        pre_session_readiness=7,
    )
    trigger = CompletedEvidence(
        id=2,
        session_date=date(2026, 8, 23),
        sport=Sport.CLIMBING,
        workout_type="Limit Bouldering",
        duration_minutes=60,
        rpe=7,
        target_rpe_max=8,
        pre_session_readiness=8,
        area_soreness={area: 6},
    )
    upcoming = PlannedWorkout(
        id=3,
        session_date=date(2026, 8, 27),
        sport=Sport.CLIMBING,
        workout_type="Limit Bouldering",
        title="Limit bouldering",
        duration_minutes=60,
    )
    proposal = propose_adaptations(
        AdaptationContext(
            trigger=trigger,
            upcoming=(upcoming,),
            latent_fatigue=blank_fatigue(),
            running_readiness=ReadinessLabel.GOOD,
            climbing_readiness=ReadinessLabel.GOOD,
            comparable_history=(earlier,),
        )
    )[0]
    assert proposal.action.value == "KEEP"
    assert area.title() in proposal.evidence[0]


def test_readiness_spread_two_is_stable_and_unrelated_elbow_soreness_does_not_block_run() -> None:
    earlier = CompletedEvidence(
        id=1,
        session_date=date(2026, 8, 12),
        sport=Sport.RUNNING,
        workout_type="Threshold",
        duration_minutes=60,
        rpe=7,
        target_rpe_max=8,
        pre_session_readiness=6,
    )
    trigger = CompletedEvidence(
        id=2,
        session_date=date(2026, 8, 23),
        sport=Sport.RUNNING,
        workout_type="Threshold",
        duration_minutes=60,
        rpe=7,
        target_rpe_max=8,
        pre_session_readiness=8,
        area_soreness={"elbow": 8},
    )
    upcoming = PlannedWorkout(
        id=3,
        session_date=date(2026, 8, 27),
        sport=Sport.RUNNING,
        workout_type="Threshold",
        title="Threshold",
        duration_minutes=60,
    )
    proposal = propose_adaptations(
        AdaptationContext(
            trigger=trigger,
            upcoming=(upcoming,),
            latent_fatigue=blank_fatigue(),
            running_readiness=ReadinessLabel.GOOD,
            climbing_readiness=ReadinessLabel.GOOD,
            comparable_history=(earlier,),
        )
    )[0]
    assert proposal.action.value == "PROGRESS"


def test_readiness_spread_above_two_blocks_progression() -> None:
    earlier = CompletedEvidence(
        id=1,
        session_date=date(2026, 8, 12),
        sport=Sport.RUNNING,
        workout_type="Threshold",
        duration_minutes=60,
        rpe=7,
        target_rpe_max=8,
        pre_session_readiness=5.9,
    )
    trigger = CompletedEvidence(
        id=2,
        session_date=date(2026, 8, 23),
        sport=Sport.RUNNING,
        workout_type="Threshold",
        duration_minutes=60,
        rpe=7,
        target_rpe_max=8,
        pre_session_readiness=8,
    )
    upcoming = PlannedWorkout(
        id=3,
        session_date=date(2026, 8, 27),
        sport=Sport.RUNNING,
        workout_type="Threshold",
        title="Threshold",
        duration_minutes=60,
    )
    proposals = propose_adaptations(
        AdaptationContext(
            trigger=trigger,
            upcoming=(upcoming,),
            latent_fatigue=blank_fatigue(),
            running_readiness=ReadinessLabel.GOOD,
            climbing_readiness=ReadinessLabel.GOOD,
            comparable_history=(earlier,),
        )
    )
    assert not any(proposal.action.value == "PROGRESS" for proposal in proposals)


def test_running_scenario_three_missed_easy_run_is_not_moved() -> None:
    trigger = CompletedEvidence(
        id=1,
        session_date=date(2026, 8, 23),
        sport=Sport.RUNNING,
        workout_type="Easy",
        duration_minutes=0,
        rpe=None,
        missed=True,
    )
    upcoming = PlannedWorkout(
        id=2,
        session_date=date(2026, 8, 24),
        sport=Sport.RUNNING,
        workout_type="Easy",
        title="Easy run",
        distance_km=8,
    )
    proposal = propose_adaptations(
        AdaptationContext(
            trigger=trigger,
            upcoming=(upcoming,),
            latent_fatigue=blank_fatigue(),
            running_readiness=ReadinessLabel.GOOD,
            climbing_readiness=ReadinessLabel.GOOD,
        )
    )[0]
    assert proposal.action.value == "KEEP"
    assert proposal.proposed_changes == {}


def test_running_scenario_four_high_rpe_easy_run_protects_next_quality() -> None:
    trigger = CompletedEvidence(
        id=1,
        session_date=date(2026, 8, 23),
        sport=Sport.RUNNING,
        workout_type="Easy",
        duration_minutes=50,
        rpe=8,
        target_rpe_max=4,
    )
    upcoming = PlannedWorkout(
        id=2,
        session_date=date(2026, 8, 24),
        sport=Sport.RUNNING,
        workout_type="Threshold",
        title="Threshold",
        duration_minutes=60,
        target_rpe_max=8,
    )
    proposal = propose_adaptations(
        AdaptationContext(
            trigger=trigger,
            upcoming=(upcoming,),
            latent_fatigue=blank_fatigue(),
            running_readiness=ReadinessLabel.GOOD,
            climbing_readiness=ReadinessLabel.GOOD,
        )
    )[0]
    assert proposal.action.value == "REDUCE_INTENSITY"


def test_climbing_scenario_max_hangs_next_day_moves_after_limit_session() -> None:
    fatigue = blank_fatigue()
    fatigue[FatigueDomain.FINGER_FOREARM] = 11.8
    fatigue[FatigueDomain.NEURAL] = 11.8
    trigger = CompletedEvidence(
        id=1,
        session_date=date(2026, 8, 23),
        sport=Sport.CLIMBING,
        workout_type="Limit Bouldering",
        duration_minutes=145,
        rpe=9,
    )
    max_hangs = PlannedWorkout(
        id=2,
        session_date=date(2026, 8, 24),
        sport=Sport.STRENGTH,
        workout_type="Max Hangs",
        title="Max hangs",
        duration_minutes=45,
        priority=SessionPriority.HIGH,
        exercises=("max hangs",),
    )
    easy_run = PlannedWorkout(
        id=3,
        session_date=date(2026, 8, 25),
        sport=Sport.RUNNING,
        workout_type="Easy",
        title="Easy run",
    )
    proposal = propose_adaptations(
        AdaptationContext(
            trigger=trigger,
            upcoming=(max_hangs, easy_run),
            latent_fatigue=fatigue,
            running_readiness=ReadinessLabel.GOOD,
            climbing_readiness=ReadinessLabel.LOW,
        )
    )[0]
    assert proposal.action.value in {"MOVE", "REPLACE"}


def test_later_max_hangs_conflict_is_found_even_when_tomorrow_is_easy_run() -> None:
    fatigue = blank_fatigue()
    fatigue[FatigueDomain.FINGER_FOREARM] = 9.5
    fatigue[FatigueDomain.NEURAL] = 9.5
    trigger = CompletedEvidence(
        id=1,
        session_date=date(2026, 8, 23),
        sport=Sport.CLIMBING,
        workout_type="Limit Bouldering",
        duration_minutes=145,
        rpe=9,
    )
    easy_run = PlannedWorkout(
        id=2,
        session_date=date(2026, 8, 24),
        sport=Sport.RUNNING,
        workout_type="Easy",
        title="Easy run",
    )
    max_hangs = PlannedWorkout(
        id=3,
        session_date=date(2026, 8, 25),
        sport=Sport.STRENGTH,
        workout_type="Max Hangs",
        title="Max hangs",
        exercises=("max hangs",),
    )
    proposal = propose_adaptations(
        AdaptationContext(
            trigger=trigger,
            upcoming=(easy_run, max_hangs),
            latent_fatigue=fatigue,
            running_readiness=ReadinessLabel.GOOD,
            climbing_readiness=ReadinessLabel.GOOD,
        )
    )[0]
    assert proposal.affected_session_id == max_hangs.id
    assert proposal.action.value in {"MOVE", "REPLACE"}


def test_missing_rpe_and_readiness_never_count_as_progression_evidence() -> None:
    earlier = CompletedEvidence(
        id=1,
        session_date=date(2026, 8, 12),
        sport=Sport.RUNNING,
        workout_type="Threshold",
        duration_minutes=60,
        rpe=None,
        target_rpe_max=8,
        pre_session_readiness=None,
    )
    trigger = CompletedEvidence(
        id=2,
        session_date=date(2026, 8, 23),
        sport=Sport.RUNNING,
        workout_type="Threshold",
        duration_minutes=60,
        rpe=None,
        target_rpe_max=8,
        pre_session_readiness=None,
    )
    upcoming = PlannedWorkout(
        id=3,
        session_date=date(2026, 8, 27),
        sport=Sport.RUNNING,
        workout_type="Threshold",
        title="Threshold",
        duration_minutes=60,
    )
    proposals = propose_adaptations(
        AdaptationContext(
            trigger=trigger,
            upcoming=(upcoming,),
            latent_fatigue=blank_fatigue(),
            running_readiness=ReadinessLabel.GOOD,
            climbing_readiness=ReadinessLabel.GOOD,
            comparable_history=(earlier,),
        )
    )
    assert not any(item.action.value == "PROGRESS" for item in proposals)


@pytest.mark.parametrize(
    ("weekly", "expected"), [(30, (0.05, 0.08)), (50, (0.03, 0.06)), (80, (0.02, 0.04))]
)
def test_mileage_progression_bands(weekly: float, expected: tuple[float, float]) -> None:
    assert mileage_progression_band(weekly) == expected


def test_mileage_holds_or_deloads_instead_of_blind_ten_percent() -> None:
    hold = decide_mileage_target(
        current_weekly_km=30,
        completion_rate=0.7,
        easy_rpe_stable=True,
        long_run_tolerated=True,
        readiness_acceptable=True,
        persistent_soreness=False,
    )
    assert hold.action == "HOLD"
    deload = decide_mileage_target(
        current_weekly_km=30,
        completion_rate=1,
        easy_rpe_stable=True,
        long_run_tolerated=True,
        readiness_acceptable=False,
        persistent_soreness=True,
    )
    assert deload.action == "DELOAD"


def test_mileage_build_requires_stable_quality_session_performance() -> None:
    missing = decide_mileage_target(
        current_weekly_km=50,
        completion_rate=0.95,
        easy_rpe_stable=True,
        long_run_tolerated=True,
        readiness_acceptable=True,
        persistent_soreness=False,
        quality_session_performance_stable=None,
    )
    assert missing.action == "HOLD"
    stable = decide_mileage_target(
        current_weekly_km=50,
        completion_rate=0.95,
        easy_rpe_stable=True,
        long_run_tolerated=True,
        readiness_acceptable=True,
        persistent_soreness=False,
        quality_session_performance_stable=True,
    )
    assert stable.action == "BUILD"


def test_long_run_progression_is_capped_by_recent_longest_exposure() -> None:
    earlier = CompletedEvidence(
        id=1,
        session_date=date(2026, 8, 12),
        sport=Sport.RUNNING,
        workout_type="Long Run",
        duration_minutes=110,
        rpe=5,
        target_rpe_max=6,
        pre_session_readiness=7,
    )
    trigger = CompletedEvidence(
        id=2,
        session_date=date(2026, 8, 23),
        sport=Sport.RUNNING,
        workout_type="Long Run",
        duration_minutes=115,
        rpe=5,
        target_rpe_max=6,
        pre_session_readiness=8,
    )
    upcoming = PlannedWorkout(
        id=3,
        session_date=date(2026, 8, 27),
        sport=Sport.RUNNING,
        workout_type="Long Run",
        title="Long run",
        duration_minutes=120,
        distance_km=21.8,
    )
    proposal = propose_adaptations(
        AdaptationContext(
            trigger=trigger,
            upcoming=(upcoming,),
            latent_fatigue=blank_fatigue(),
            running_readiness=ReadinessLabel.GOOD,
            climbing_readiness=ReadinessLabel.GOOD,
            comparable_history=(earlier,),
            recent_longest_run_km=20,
        )
    )[0]
    assert proposal.action.value == "PROGRESS"
    assert proposal.proposed_changes == {
        "planned_distance_km": 22.0,
        "progressed_variable": "volume",
    }

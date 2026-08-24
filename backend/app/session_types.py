from __future__ import annotations

import re

from app.enums import ClimbingSessionType, RunningSessionType, Sport


def _key(value: object) -> str:
    return re.sub(r"[\s_/-]+", " ", str(value or "").strip().casefold())


RUNNING_ALIASES: dict[str, RunningSessionType] = {}
for aliases, target in (
    (
        ("easy", "easy run", "recovery", "recovery run", "z2", "zone 2", "aerobic run"),
        RunningSessionType.EASY,
    ),
    (("long", "long run", "lr", "long aerobic run"), RunningSessionType.LONG_RUN),
    (
        (
            "threshold",
            "tempo",
            "interval",
            "intervals",
            "vo2",
            "vo2max",
            "fartlek",
            "hills",
            "hill repeats",
            "speed workout",
            "hm pace workout",
            "hm pace",
            "marathon pace workout",
            "marathon pace",
            "quality",
            "cruise intervals",
            "steady",
            "progression",
            "strides",
            "强度课",
            "強度課",
            "间歇",
            "間歇",
            "阈值",
            "閾值",
            "节奏跑",
            "節奏跑",
        ),
        RunningSessionType.QUALITY,
    ),
    (
        (
            "race",
            "time trial",
            "5k race",
            "10k race",
            "half marathon",
            "marathon",
            "比赛",
            "比賽",
            "测试赛",
            "測試賽",
        ),
        RunningSessionType.RACE,
    ),
):
    for alias in aliases:
        RUNNING_ALIASES[_key(alias)] = target
for item in RunningSessionType:
    RUNNING_ALIASES[_key(item.value)] = item


CLIMBING_ALIASES: dict[str, ClimbingSessionType] = {}
for aliases, target in (
    (
        (
            "bouldering",
            "limit bouldering",
            "technique",
            "volume",
            "easy volume",
            "power",
            "power endurance",
            "outdoor",
            "outdoor bouldering",
        ),
        ClimbingSessionType.BOULDERING,
    ),
    (
        ("sport climbing", "sport lead", "sport / lead", "lead", "top rope"),
        ClimbingSessionType.SPORT_CLIMBING,
    ),
    (
        ("board", "tension board", "tension board 2", "tb2", "kilter board", "moonboard"),
        ClimbingSessionType.BOARD,
    ),
):
    for alias in aliases:
        CLIMBING_ALIASES[_key(alias)] = target
for item in ClimbingSessionType:
    CLIMBING_ALIASES[_key(item.value)] = item


def normalise_session_type(sport: Sport | str, value: object) -> str | None:
    """Return the strict type for primary sports, or preserve auxiliary types."""

    kind = Sport(sport)
    if kind == Sport.RUNNING:
        result = RUNNING_ALIASES.get(_key(value))
        return result.value if result else None
    if kind == Sport.CLIMBING:
        result = CLIMBING_ALIASES.get(_key(value))
        return result.value if result else None
    raw = str(value or "").strip()
    return raw or None

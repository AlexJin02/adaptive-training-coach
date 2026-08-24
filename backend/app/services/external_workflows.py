from __future__ import annotations

import calendar
import re
from collections import Counter, defaultdict
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import models
from app.enums import PlanStatus, SessionPriority, Sport
from app.services import core
from app.session_types import normalise_session_type

DAY_OFFSETS = {
    "MONDAY": 0,
    "TUESDAY": 1,
    "WEDNESDAY": 2,
    "THURSDAY": 3,
    "FRIDAY": 4,
    "SATURDAY": 5,
    "SUNDAY": 6,
}

WEEKLY_PLAN_TEMPLATE = """# TRAINING_WEEKLY_PLAN_V1

## PLAN_INFO

WEEK_START: YYYY-MM-DD
WEEK_END: YYYY-MM-DD

RUNNING_TARGET_KM: 0
CLIMBING_TARGET_SESSIONS: 0

## MONDAY

SESSION_1:
SPORT: REST
TITLE: Rest Day

## TUESDAY

SESSION_1:
SPORT: RUNNING
TYPE: EASY
TITLE: Easy Run
DISTANCE_KM: 8
TARGET_RPE: 2-4

WORKOUT:
- 8 km easy

NOTES:
Keep the run relaxed.

## WEDNESDAY
## THURSDAY
## FRIDAY
## SATURDAY
## SUNDAY

## END_PLAN
"""

MONTHLY_PLAN_TEMPLATE = """# TRAINING_MONTHLY_PLAN_V1

## PLAN_INFO

MONTH: YYYY-MM

## RUNNING

PHASE: N/A
MONTHLY_OBJECTIVE:
N/A

RUNNING_SESSIONS_PER_WEEK: 4

RUNNING_SESSION_STRUCTURE:
- EASY: 2
- LONG_RUN: 1
- QUALITY: 1
- RACE: 0

WEEKLY_DISTANCE_TARGETS:
- Week 1: 0 km
- Week 2: 0 km
- Week 3: 0 km
- Week 4: 0 km

QUALITY_GUIDANCE:
N/A
LONG_RUN_GUIDANCE:
- Week 1: 0 km
- Week 2: 0 km
- Week 3: 0 km
- Week 4: 0 km
KEY_PRINCIPLES:
- Keep most running easy.
OTHER_RUNNING_NOTES:
N/A

## CLIMBING

PHASE: N/A
SESSIONS_PER_WEEK: 0
TARGET_STRUCTURE:
- N/A
BOARD_FOCUS:
N/A
KEY_PRINCIPLES:
- Prioritise attempt quality over session duration.
OTHER_CLIMBING_NOTES:
N/A

## AUXILIARY

STRENGTH:
N/A
MOBILITY:
N/A

## GENERAL_NOTES

N/A

## END_PLAN
"""


def plan_template(cadence: str) -> str:
    return WEEKLY_PLAN_TEMPLATE if cadence == "WEEKLY" else MONTHLY_PLAN_TEMPLATE


def _duration(minutes: float | None) -> str:
    if minutes is None:
        return "N/A"
    seconds = max(0, round(minutes * 60))
    hours, remainder = divmod(seconds, 3600)
    mins, secs = divmod(remainder, 60)
    return f"{hours}:{mins:02d}:{secs:02d}" if hours else f"{mins:02d}:{secs:02d}"


def _pace(seconds: float | None) -> str:
    if seconds is None:
        return "N/A"
    mins, secs = divmod(round(seconds), 60)
    return f"{mins}:{secs:02d}/km"


def _number(value: Any, digits: int = 1) -> str:
    if value is None:
        return "N/A"
    return f"{float(value):.{digits}f}".rstrip("0").rstrip(".")


def _value(text: str, key: str) -> str | None:
    match = re.search(rf"(?m)^{re.escape(key)}:\s*(.*?)\s*$", text)
    return match.group(1).strip() if match and match.group(1).strip() else None


def _multiline(text: str, key: str) -> str:
    match = re.search(rf"(?m)^{re.escape(key)}:\s*(.*)$", text)
    if not match:
        return ""
    lines = [match.group(1).strip()] if match.group(1).strip() else []
    for line in text[match.end() :].splitlines():
        if re.match(r"^[A-Z][A-Z0-9_ ]*:\s*", line) or line.startswith("## "):
            break
        lines.append(line.rstrip())
    return "\n".join(lines).strip()


def _bullet_items(text: str) -> list[str]:
    return [
        match.group(1).strip()
        for line in text.splitlines()
        if (match := re.match(r"^\s*-\s*(.+?)\s*$", line))
    ]


def _week_targets(text: str) -> list[dict[str, Any]]:
    return [
        {"week": int(week), "distance_km": float(value)}
        for week, value in re.findall(
            r"(?mi)^-\s*Week\s*(\d+)\s*:\s*(\d+(?:\.\d+)?)\s*km\s*$", text
        )
    ]


def _session_structure(text: str) -> list[dict[str, Any]]:
    """Accept both `- EASY: 2` and legacy `- 2 Easy sessions` bullets."""

    items: list[dict[str, Any]] = []
    for bullet in _bullet_items(text):
        labelled = re.match(r"^([A-Za-z0-9_ /-]+?)\s*:\s*(\d+(?:\.\d+)?)$", bullet)
        descriptive = re.match(r"^([A-Za-z0-9_ /-]+?)\s*:\s*(.+)$", bullet)
        legacy = re.match(r"^(\d+(?:\.\d+)?)\s+(.+?)(?:\s+sessions?)?$", bullet, re.I)
        if labelled:
            label, count = labelled.group(1), labelled.group(2)
        elif descriptive and (
            frequency := re.search(
                r"(?:每周|每週|weekly)\s*(\d+(?:\.\d+)?)\s*(?:次|sessions?)?",
                descriptive.group(2),
                re.I,
            )
        ):
            label, count = descriptive.group(1), frequency.group(1)
        elif legacy:
            count, label = legacy.group(1), legacy.group(2)
        else:
            continue
        session_type = re.sub(r"[^A-Za-z0-9]+", "_", label.strip()).strip("_").upper()
        items.append({"session_type": session_type, "sessions_per_week": float(count)})
    return items


def _normalise_monthly_content(content: dict[str, Any]) -> dict[str, Any]:
    """Give older stored V1 blocks the same readable shape as newly parsed blocks."""

    running = dict(content.get("running") or {})
    climbing = dict(content.get("climbing") or {})
    auxiliary = dict(content.get("auxiliary") or {})
    if not running and content.get("running_phase") is not None:
        volumes = content.get("weekly_running_volume_targets") or []
        running = {
            "phase": content.get("running_phase"),
            "monthly_objective": "\n".join(content.get("running_objectives") or []),
            "weekly_distance_targets": [
                {"week": index, "distance_km": value}
                for index, value in enumerate(volumes, start=1)
            ],
            "quality_guidance": content.get("quality_session_guidance"),
            "long_run_guidance": content.get("long_run_guidance"),
            "key_principles": [
                *(content.get("progression_criteria") or []),
                *(content.get("hold_criteria") or []),
                *(content.get("deload_criteria") or []),
            ],
        }
        climbing = {
            "phase": content.get("climbing_phase"),
            "board_focus": "\n".join(content.get("climbing_focus") or []),
            "other_notes": "\n".join(content.get("climbing_objectives") or []),
        }
        auxiliary = {"strength": content.get("supporting_strength_guidance")}

    running_structure = running.get("session_structure")
    if isinstance(running_structure, str):
        running_structure = _session_structure(running_structure)
    climbing_structure = climbing.get("target_structure")
    if isinstance(climbing_structure, str):
        climbing_structure = _session_structure(climbing_structure)

    long_run_guidance = str(running.get("long_run_guidance") or "")
    return {
        "month": str(content.get("month") or ""),
        "running": {
            "phase": running.get("phase") or "",
            "monthly_objective": running.get("monthly_objective") or "",
            "sessions_per_week": running.get("sessions_per_week"),
            "session_structure": running_structure or [],
            "weekly_distance_targets": running.get("weekly_distance_targets") or [],
            "quality_guidance": running.get("quality_guidance") or "",
            "long_run_guidance": long_run_guidance,
            "long_run_targets": running.get("long_run_targets") or _week_targets(long_run_guidance),
            "key_principles": running.get("key_principles") or [],
            "other_notes": running.get("other_notes") or "",
        },
        "climbing": {
            "phase": climbing.get("phase") or "",
            "sessions_per_week": climbing.get("sessions_per_week"),
            "target_structure": climbing_structure or [],
            "board_focus": climbing.get("board_focus") or "",
            "key_principles": climbing.get("key_principles") or [],
            "other_notes": climbing.get("other_notes") or "",
        },
        "auxiliary": {
            "strength": auxiliary.get("strength") or "",
            "mobility": auxiliary.get("mobility") or "",
        },
        "general_notes": content.get("general_notes")
        or section_from_raw(
            content.get("raw_plan_text") or content.get("raw_text") or "", "GENERAL_NOTES"
        ),
        "raw_plan_text": content.get("raw_plan_text") or content.get("raw_text") or "",
    }


def section_from_raw(markdown: str, name: str) -> str:
    match = re.search(rf"(?ms)^## {re.escape(name)}\s*$\n(.*?)(?=^## |\Z)", markdown)
    return match.group(1).strip() if match else ""


def _float_field(text: str, key: str, warnings: list[str], label: str) -> float | None:
    raw = _value(text, key)
    if raw is None:
        return None
    try:
        value = float(raw)
    except ValueError:
        warnings.append(f"{label}: {key} must be numeric; preserved in raw text")
        return None
    if value < 0:
        warnings.append(f"{label}: {key} cannot be negative")
        return None
    return value


def _rpe_range(
    raw: str | None, warnings: list[str], label: str
) -> tuple[float | None, float | None]:
    if not raw:
        return None, None
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(?:[-–]\s*(\d+(?:\.\d+)?))?\s*", raw)
    if not match:
        warnings.append(f"{label}: TARGET_RPE must be a value or range from 1 to 10")
        return None, None
    low = float(match.group(1))
    high = float(match.group(2) or low)
    if not 1 <= low <= high <= 10:
        warnings.append(f"{label}: TARGET_RPE must be between 1 and 10")
        return None, None
    return low, high


def _seconds(raw: str) -> float | None:
    match = re.search(
        r"(\d+(?:\.\d+)?)\s*(sec|secs|second|seconds|min|mins|minute|minutes)", raw, re.I
    )
    if not match:
        return None
    value = float(match.group(1))
    return value if match.group(2).lower().startswith("sec") else value * 60


def _parse_workout(workout: str) -> list[dict[str, Any]]:
    """Parse common prescriptions while always retaining each original line."""

    blocks: list[dict[str, Any]] = []
    for order, raw_line in enumerate(workout.splitlines(), start=1):
        line = raw_line.strip().removeprefix("-").strip()
        if not line:
            continue
        label, _, detail = line.partition(":")
        key = label.strip().upper().replace("-", "_").replace(" ", "_")
        segment_kind = {
            "WARMUP": "WARMUP",
            "WARM_UP": "WARMUP",
            "EASY": "EASY",
            "MAIN": "INTERVAL",
            "MAIN_SET": "INTERVAL",
            "REP_RECOVERY": "RECOVERY",
            "SET_RECOVERY": "RECOVERY",
            "RECOVERY": "RECOVERY",
            "STEADY": "STEADY",
            "COOLDOWN": "COOLDOWN",
            "COOL_DOWN": "COOLDOWN",
            "STRIDES": "STRIDES",
        }.get(key, "FREEFORM")
        content = detail.strip() if detail else line
        block: dict[str, Any] = {
            "segment_order": order,
            "segment_kind": segment_kind,
            "label": label.strip() if detail else None,
            "raw_text": line,
            "notes": content,
        }
        nested = re.search(
            r"(?P<sets>\d+)\s*sets?\s*[x×]\s*(?P<reps>\d+)\s*[x×]\s*(?P<distance>\d+(?:\.\d+)?)\s*km\s*@\s*(?P<pace>\d+:\d{2})(?:\s*[-–]\s*(?P<pace_max>\d+:\d{2}))?/km",
            content,
            re.I,
        )
        simple = re.search(
            r"(?P<reps>\d+)\s*[x×]\s*(?P<amount>\d+(?:\.\d+)?)\s*(?P<unit>km|min|sec)\s*@\s*(?P<pace>\d+:\d{2})(?:\s*[-–]\s*(?P<pace_max>\d+:\d{2}))?/km",
            content,
            re.I,
        )
        match = nested or simple
        if match:
            data = match.groupdict()
            block["sets"] = int(data.get("sets") or 1)
            block["repetitions"] = int(data["reps"])
            if data.get("distance"):
                block["distance_km"] = float(data["distance"])
            elif data.get("unit", "").lower() == "km":
                block["distance_km"] = float(data["amount"])
            elif data.get("unit", "").lower() in {"min", "sec"}:
                amount = float(data["amount"])
                block["duration_seconds"] = amount * (60 if data["unit"].lower() == "min" else 1)
            block["target_pace_min"] = data["pace"]
            block["target_pace_max"] = data.get("pace_max") or data["pace"]
        heart_rate_range = re.search(r"\bHR\s*(\d{2,3})\s*[-–]\s*(\d{2,3})\b", content, re.I)
        heart_rate_cap = re.search(r"\bHR\s*(?:<=|≤|max\s*)\s*(\d{2,3})\b", content, re.I)
        if heart_rate_range:
            block["target_hr_min"] = int(heart_rate_range.group(1))
            block["target_hr_max"] = int(heart_rate_range.group(2))
        elif heart_rate_cap:
            block["target_hr_max"] = int(heart_rate_cap.group(1))
        if segment_kind == "RECOVERY":
            recovery = _seconds(content)
            if recovery is not None:
                block["recovery_duration_seconds"] = recovery
                block["recovery_scope"] = "SET" if key == "SET_RECOVERY" else "REP"
        blocks.append(block)
    return blocks


def parse_weekly_plan(markdown: str) -> dict[str, Any]:
    warnings: list[str] = []
    if not re.search(r"(?m)^# TRAINING_WEEKLY_PLAN_V1\s*$", markdown):
        warnings.append("ERROR: Missing # TRAINING_WEEKLY_PLAN_V1 header")
    raw_start = _value(markdown, "WEEK_START")
    raw_end = _value(markdown, "WEEK_END")
    try:
        week_start = date.fromisoformat(raw_start or "")
    except ValueError:
        week_start = date.today() - timedelta(days=date.today().weekday())
        warnings.append("ERROR: WEEK_START must be an ISO date (YYYY-MM-DD)")
    try:
        week_end = date.fromisoformat(raw_end or "")
    except ValueError:
        week_end = week_start + timedelta(days=6)
        warnings.append("WEEK_END was missing or invalid; preview uses WEEK_START + 6 days")
    if week_end != week_start + timedelta(days=6):
        warnings.append("WEEK_END should be six days after WEEK_START")

    sessions: list[dict[str, Any]] = []
    day_pattern = re.compile(
        r"(?ms)^## (MONDAY|TUESDAY|WEDNESDAY|THURSDAY|FRIDAY|SATURDAY|SUNDAY)\s*$\n(.*?)(?=^## |\Z)"
    )
    for day_match in day_pattern.finditer(markdown):
        day_name, body = day_match.groups()
        session_pattern = re.compile(r"(?ms)^SESSION_(\d+):\s*$\n(.*?)(?=^SESSION_\d+:|\Z)")
        for session_match in session_pattern.finditer(body):
            index, block = session_match.groups()
            label = f"{day_name} SESSION_{index}"
            raw_sport = (_value(block, "SPORT") or "").upper()
            title = _value(block, "TITLE")
            if not raw_sport:
                warnings.append(f"ERROR: {label} is missing SPORT")
                continue
            if raw_sport == "REST":
                sport = Sport.MOBILITY_RECOVERY
                session_type = "Rest"
                status = PlanStatus.REST
            else:
                try:
                    sport = Sport(raw_sport)
                except ValueError:
                    warnings.append(f"ERROR: {label} has unsupported SPORT {raw_sport}")
                    continue
                raw_type = _value(block, "TYPE")
                session_type = normalise_session_type(sport, raw_type)
                if sport in {Sport.RUNNING, Sport.CLIMBING} and session_type is None:
                    warnings.append(f"ERROR: {label} has an invalid or missing TYPE")
                    continue
                session_type = session_type or title or raw_sport
                status = PlanStatus.PLANNED
            if not title:
                warnings.append(f"{label} has no TITLE; using the session type")
                title = session_type
            workout = _multiline(block, "WORKOUT")
            notes = _multiline(block, "NOTES")
            low_rpe, high_rpe = _rpe_range(_value(block, "TARGET_RPE"), warnings, label)
            distance = _float_field(block, "DISTANCE_KM", warnings, label)
            duration = _float_field(block, "DURATION_MIN", warnings, label)
            session_date = week_start + timedelta(days=DAY_OFFSETS[day_name])
            if not week_start <= session_date <= week_end:
                warnings.append(f"{label} falls outside the stated week")
            structured_blocks = _parse_workout(workout)
            if (
                "@" in workout
                and "/km" in workout
                and not any(item.get("target_pace_min") for item in structured_blocks)
            ):
                warnings.append(
                    f"{label}: a pace target could not be parsed; raw WORKOUT text is preserved"
                )
            board_name = _value(block, "BOARD")
            angle = _float_field(block, "ANGLE", warnings, label)
            if (
                sport == Sport.CLIMBING
                and session_type == "BOARD"
                and (board_name or angle is not None)
            ):
                structured_blocks.append(
                    {
                        "segment_order": len(structured_blocks) + 1,
                        "segment_kind": "FREEFORM",
                        "label": "Board setup",
                        "raw_text": ", ".join(
                            part
                            for part in (
                                board_name,
                                f"{_number(angle)}°" if angle is not None else None,
                            )
                            if part
                        ),
                        "board_name": board_name,
                        "angle": angle,
                    }
                )
            sessions.append(
                {
                    "date": session_date.isoformat(),
                    "day": day_name,
                    "session_number": int(index),
                    "workout_kind": sport.value,
                    "session_type": session_type,
                    "title": title,
                    "planned_distance_km": distance,
                    "planned_duration_minutes": duration,
                    "target_rpe_min": low_rpe,
                    "target_rpe_max": high_rpe,
                    "target_rpe": high_rpe,
                    "description": workout,
                    "notes": notes,
                    "structured_blocks": structured_blocks,
                    "raw_workout_text": workout,
                    "status": status.value,
                    "board_name": board_name,
                    "angle": angle,
                    "raw_text": block.strip(),
                }
            )
    if not sessions:
        warnings.append("ERROR: No SESSION_n blocks were found")
    return {
        "cadence": "WEEKLY",
        "period_start": week_start.isoformat(),
        "period_end": week_end.isoformat(),
        "running_target_km": _float_field(markdown, "RUNNING_TARGET_KM", warnings, "PLAN_INFO"),
        "climbing_target_sessions": _float_field(
            markdown, "CLIMBING_TARGET_SESSIONS", warnings, "PLAN_INFO"
        ),
        "sessions": sessions,
        "warnings": warnings,
        "can_import": not any(item.startswith("ERROR:") for item in warnings),
    }


def parse_monthly_plan(markdown: str) -> dict[str, Any]:
    warnings: list[str] = []
    if not re.search(r"(?m)^# TRAINING_MONTHLY_PLAN_V1\s*$", markdown):
        warnings.append("ERROR: Missing # TRAINING_MONTHLY_PLAN_V1 header")
    raw_month = _value(markdown, "MONTH")
    try:
        month_start = date.fromisoformat(f"{raw_month}-01")
    except ValueError:
        month_start = date.today().replace(day=1)
        warnings.append("ERROR: MONTH must use YYYY-MM")
    month_end = date(
        month_start.year,
        month_start.month,
        calendar.monthrange(month_start.year, month_start.month)[1],
    )

    def section(name: str, following: str | None = None) -> str:
        end = rf"(?=^## {re.escape(following)}\s*$|\Z)" if following else r"(?=^## |\Z)"
        match = re.search(rf"(?ms)^## {re.escape(name)}\s*$\n(.*?){end}", markdown)
        return match.group(1).strip() if match else ""

    running = section("RUNNING", "CLIMBING")
    climbing = section("CLIMBING", "AUXILIARY")
    auxiliary = section("AUXILIARY", "GENERAL_NOTES")
    general_notes = section("GENERAL_NOTES", "END_PLAN")
    targets = _week_targets(_multiline(running, "WEEKLY_DISTANCE_TARGETS"))
    long_run_guidance = _multiline(running, "LONG_RUN_GUIDANCE")
    if not running:
        warnings.append("ERROR: Missing RUNNING section")
    if not climbing:
        warnings.append("ERROR: Missing CLIMBING section")
    content = {
        "month": month_start.strftime("%Y-%m"),
        "running": {
            "phase": _value(running, "PHASE"),
            "monthly_objective": _multiline(running, "MONTHLY_OBJECTIVE"),
            "sessions_per_week": _float_field(
                running, "RUNNING_SESSIONS_PER_WEEK", warnings, "RUNNING"
            ),
            "session_structure": _session_structure(
                _multiline(running, "RUNNING_SESSION_STRUCTURE")
            ),
            "weekly_distance_targets": targets,
            "quality_guidance": _multiline(running, "QUALITY_GUIDANCE"),
            "long_run_guidance": long_run_guidance,
            "long_run_targets": _week_targets(long_run_guidance),
            "key_principles": _bullet_items(_multiline(running, "KEY_PRINCIPLES")),
            "other_notes": _multiline(running, "OTHER_RUNNING_NOTES"),
        },
        "climbing": {
            "phase": _value(climbing, "PHASE"),
            "sessions_per_week": _float_field(climbing, "SESSIONS_PER_WEEK", warnings, "CLIMBING"),
            "target_structure": _session_structure(_multiline(climbing, "TARGET_STRUCTURE")),
            "board_focus": _multiline(climbing, "BOARD_FOCUS"),
            "key_principles": _bullet_items(_multiline(climbing, "KEY_PRINCIPLES")),
            "other_notes": _multiline(climbing, "OTHER_CLIMBING_NOTES"),
        },
        "auxiliary": {
            "strength": _multiline(auxiliary, "STRENGTH"),
            "mobility": _multiline(auxiliary, "MOBILITY"),
        },
        "general_notes": general_notes,
        "raw_plan_text": markdown.strip(),
    }
    return {
        "cadence": "MONTHLY",
        "period_start": month_start.isoformat(),
        "period_end": month_end.isoformat(),
        "block": content,
        "warnings": warnings,
        "can_import": not any(item.startswith("ERROR:") for item in warnings),
    }


def parse_plan(markdown: str, cadence: str) -> dict[str, Any]:
    return parse_weekly_plan(markdown) if cadence == "WEEKLY" else parse_monthly_plan(markdown)


def import_plan(db: Session, markdown: str, cadence: str) -> dict[str, Any]:
    parsed = parse_plan(markdown, cadence)
    if not parsed["can_import"]:
        raise ValueError("Plan has blocking validation errors; review the preview warnings")
    imported_ids: list[int] = []
    if cadence == "WEEKLY":
        for row in parsed["sessions"]:
            description_parts = [row.get("raw_workout_text") or "", row.get("notes") or ""]
            item = core.create_planned_session(
                db,
                {
                    "date": date.fromisoformat(row["date"]),
                    "workout_kind": row["workout_kind"],
                    "session_type": row["session_type"],
                    "title": row["title"],
                    "description": "\n\n".join(part for part in description_parts if part),
                    "planned_duration_minutes": row.get("planned_duration_minutes"),
                    "planned_distance_km": row.get("planned_distance_km"),
                    "target_rpe": row.get("target_rpe"),
                    "priority": SessionPriority.NORMAL,
                    "status": row["status"],
                    "structured_blocks": row.get("structured_blocks") or [],
                },
            )
            imported_ids.append(item.id)
    else:
        db.query(models.MonthlyTrainingBlock).filter(
            models.MonthlyTrainingBlock.status == "ACTIVE"
        ).update({"status": "ARCHIVED"})
        block = models.MonthlyTrainingBlock(
            month_start=date.fromisoformat(parsed["period_start"]),
            month_end=date.fromisoformat(parsed["period_end"]),
            content=parsed["block"],
            source_proposal_id=None,
            status="ACTIVE",
        )
        db.add(block)
        db.commit()
    history = models.ImportedPlan(
        cadence=cadence,
        period_start=date.fromisoformat(parsed["period_start"]),
        period_end=date.fromisoformat(parsed["period_end"]),
        raw_markdown=markdown,
        parsed_content=parsed,
        imported_session_ids=imported_ids,
    )
    db.add(history)
    db.commit()
    db.refresh(history)
    return {**parsed, "import_id": history.id, "imported_session_ids": imported_ids}


def current_monthly_block(db: Session) -> dict[str, Any] | None:
    item = db.scalar(
        select(models.MonthlyTrainingBlock)
        .where(models.MonthlyTrainingBlock.status == "ACTIVE")
        .order_by(
            models.MonthlyTrainingBlock.month_start.desc(), models.MonthlyTrainingBlock.id.desc()
        )
        .limit(1)
    )
    if item is None:
        return None
    return {
        "id": item.id,
        "month_start": item.month_start.isoformat(),
        "month_end": item.month_end.isoformat(),
        "content": _normalise_monthly_content(
            {"month": item.month_start.strftime("%Y-%m"), **(item.content or {})}
        ),
        "status": item.status,
    }


def update_monthly_block(
    db: Session, block_id: int, changes: dict[str, Any]
) -> dict[str, Any] | None:
    """Save a new active revision while retaining the previous monthly block."""

    item = db.scalar(
        select(models.MonthlyTrainingBlock).where(
            models.MonthlyTrainingBlock.id == block_id,
            models.MonthlyTrainingBlock.status == "ACTIVE",
        )
    )
    if item is None:
        return None
    previous = _normalise_monthly_content(item.content)
    content = _normalise_monthly_content(
        {
            "month": previous["month"] or item.month_start.strftime("%Y-%m"),
            "running": changes["running"],
            "climbing": changes["climbing"],
            "auxiliary": changes["auxiliary"],
            "general_notes": changes.get("general_notes") or "",
            "raw_plan_text": previous["raw_plan_text"],
        }
    )
    item.status = "ARCHIVED"
    revision = models.MonthlyTrainingBlock(
        month_start=item.month_start,
        month_end=item.month_end,
        content=content,
        source_proposal_id=item.source_proposal_id,
        status="ACTIVE",
    )
    db.add(revision)
    db.commit()
    return current_monthly_block(db)


def _sessions(db: Session, start: date, end: date) -> list[models.CompletedSession]:
    return list(
        db.scalars(
            select(models.CompletedSession)
            .options(
                selectinload(models.CompletedSession.running),
                selectinload(models.CompletedSession.climbing).selectinload(
                    models.ClimbingSessionDetail.attempts
                ),
                selectinload(models.CompletedSession.strength).selectinload(
                    models.StrengthSessionDetail.sets
                ),
            )
            .where(models.CompletedSession.session_date.between(start, end))
            .order_by(models.CompletedSession.session_date, models.CompletedSession.id)
        )
    )


def _latest(db: Session, model: type[Any], date_column: Any, on: date) -> Any | None:
    return db.scalar(select(model).where(date_column <= on).order_by(date_column.desc()).limit(1))


def _gym_set_on(db: Session, on: date) -> models.GymSet | None:
    return db.scalar(
        select(models.GymSet)
        .options(selectinload(models.GymSet.colours))
        .where(
            models.GymSet.start_date <= on,
            (models.GymSet.end_date.is_(None) | (models.GymSet.end_date >= on)),
        )
        .order_by(models.GymSet.start_date.desc(), models.GymSet.id.desc())
        .limit(1)
    )


def _gym_progress_lines(gym_set: models.GymSet | None) -> list[str]:
    if gym_set is None or not gym_set.colours:
        return ["- N/A"]
    return [
        f"- {row.colour}: {row.sent_count}"
        + (
            f" / {row.available_problem_count} ({_number(row.completion_rate * 100)}%)"
            if row.available_problem_count and row.completion_rate is not None
            else ""
        )
        for row in sorted(gym_set.colours, key=lambda item: item.ordinal)
    ]


def _goals(db: Session) -> tuple[str, str]:
    rows = list(db.scalars(select(models.Goal).where(models.Goal.current_status == "ACTIVE")))
    running = next(
        (
            row
            for row in rows
            if row.goal_type.value in {"HALF_MARATHON", "MARATHON", "RUNNING_MILEAGE"}
        ),
        None,
    )
    climbing = next(
        (row for row in rows if row.goal_type.value in {"BOULDERING", "LEAD_CLIMBING"}), None
    )

    def label(row: models.Goal | None) -> str:
        if row is None:
            return "N/A"
        return row.description or row.target_value or row.goal_type.value

    return label(running), label(climbing)


def _workout_lines(item: models.CompletedSession) -> list[str]:
    if item.running and item.running.intervals:
        lines = []
        for row in item.running.intervals:
            if not isinstance(row, dict):
                lines.append(f"- {row}")
                continue
            label = row.get("phase") or row.get("segment_kind") or row.get("label") or "Segment"
            detail = row.get("detail") or row.get("raw_text") or row.get("notes") or "N/A"
            lines.append(f"- {label}: {detail}")
        return lines
    if item.running and item.running.distance_km is not None:
        return [f"- {_number(item.running.distance_km)} km {item.workout_type.lower()}"]
    return ["- N/A"]


def weekly_report(db: Session, week_start: date) -> str:
    week_end = week_start + timedelta(days=6)
    profile = core.get_profile(db)
    sessions = _sessions(db, week_start, week_end)
    previous = _sessions(db, week_start - timedelta(days=7), week_start - timedelta(days=1))
    rolling = _sessions(db, week_end - timedelta(days=27), week_end)
    running = [item for item in sessions if item.sport == Sport.RUNNING]
    climbing = [item for item in sessions if item.sport == Sport.CLIMBING]
    auxiliary = [item for item in sessions if item.sport not in {Sport.RUNNING, Sport.CLIMBING}]
    running_goal, climbing_goal = _goals(db)
    latest_10k = _latest(
        db, models.RunningFitnessEstimate, models.RunningFitnessEstimate.source_date, week_end
    )
    lt2 = db.scalar(
        select(models.ThresholdEstimate)
        .where(
            models.ThresholdEstimate.estimate_type == "LT2",
            models.ThresholdEstimate.measured_at <= week_end,
        )
        .order_by(models.ThresholdEstimate.measured_at.desc())
        .limit(1)
    )
    tb2 = _latest(db, models.TB2Benchmark, models.TB2Benchmark.benchmark_date, week_end)
    counts = Counter(item.workout_type for item in running)
    run_distance = sum(item.running.distance_km or 0 for item in running if item.running)
    previous_distance = sum(item.running.distance_km or 0 for item in previous if item.running)
    rolling_distance = sum(item.running.distance_km or 0 for item in rolling if item.running)
    longest = max((item.running.distance_km or 0 for item in running if item.running), default=None)
    lines = [
        "# TRAINING_WEEKLY_REPORT_V1",
        "",
        "## REPORT_INFO",
        "",
        f"WEEK_START: {week_start.isoformat()}",
        f"WEEK_END: {week_end.isoformat()}",
        "",
        "## ATHLETE_GOALS",
        "",
        f"RUNNING_GOAL: {running_goal}",
        f"CLIMBING_GOAL: {climbing_goal}",
        "",
        "## CURRENT_STATE",
        "",
        f"RUNNING_PHASE: {profile.running_phase.value}",
        f"CLIMBING_PHASE: {profile.climbing_phase.value}",
        f"ESTIMATED_10K: {_duration(latest_10k.estimated_10k_seconds / 60) if latest_10k and latest_10k.estimated_10k_seconds else 'N/A'}",
        f"LT2_PACE: {_pace(lt2.pace_low_seconds_per_km) if lt2 else 'N/A'}",
        f"LT2_HR: {lt2.hr_low if lt2 and lt2.hr_low else 'N/A'}",
        f"TB2_VERIFIED: {tb2.verified_grade if tb2 else 'N/A'}",
        f"TB2_ESTIMATED: {tb2.estimated_grade if tb2 and tb2.estimated_grade else 'N/A'}",
        "",
        "## RUNNING_SUMMARY",
        "",
        f"TOTAL_DISTANCE_KM: {_number(run_distance)}",
        f"TOTAL_DURATION: {_duration(sum(item.duration_minutes for item in running))}",
        f"SESSION_COUNT: {len(running)}",
        "",
        f"EASY_COUNT: {counts['EASY']}",
        f"LONG_RUN_COUNT: {counts['LONG_RUN']}",
        f"QUALITY_COUNT: {counts['QUALITY']}",
        f"RACE_COUNT: {counts['RACE']}",
        "",
        f"LONGEST_RUN_KM: {_number(longest)}",
        "",
        f"PREVIOUS_WEEK_DISTANCE_KM: {_number(previous_distance)}",
        f"ROLLING_28D_DISTANCE_KM: {_number(rolling_distance)}",
        f"ROLLING_28D_WEEKLY_AVG_KM: {_number(rolling_distance / 4)}",
        "",
        "## RUNNING_SESSIONS",
        "",
    ]
    for index, item in enumerate(running, 1):
        detail = item.running
        lines.extend(
            [
                f"### RUN_{index}",
                "",
                f"DATE: {item.session_date.isoformat()}",
                f"TYPE: {item.workout_type}",
                f"TITLE: {item.title or item.workout_type}",
                "",
                f"DISTANCE_KM: {_number(detail.distance_km if detail else None)}",
                f"DURATION: {_duration(item.duration_minutes)}",
                f"AVG_PACE: {_pace(detail.average_pace_seconds_per_km if detail else None)}",
                f"AVG_HR: {detail.average_hr if detail and detail.average_hr else 'N/A'}",
                f"MAX_HR: {detail.maximum_hr if detail and detail.maximum_hr else 'N/A'}",
                f"RPE: {_number(item.rpe)}",
                "",
                "WORKOUT:",
                *_workout_lines(item),
                "",
            ]
        )
        if detail and detail.splits:
            lines.extend(["SPLITS:", *[f"- {row}" for row in detail.splits], ""])
        lines.extend(["SUBJECTIVE:", item.subjective_feedback_text or "N/A", ""])
    if not running:
        lines.extend(["N/A", ""])
    climb_counts = Counter(item.workout_type for item in climbing)
    lines.extend(
        [
            "## CLIMBING_SUMMARY",
            "",
            f"SESSION_COUNT: {len(climbing)}",
            f"TOTAL_DURATION: {_duration(sum(item.duration_minutes for item in climbing))}",
            "",
            f"BOULDERING_COUNT: {climb_counts['BOULDERING']}",
            f"SPORT_CLIMBING_COUNT: {climb_counts['SPORT_CLIMBING']}",
            f"BOARD_COUNT: {climb_counts['BOARD']}",
            "",
            "## CLIMBING_SESSIONS",
            "",
        ]
    )
    for index, item in enumerate(climbing, 1):
        detail = item.climbing
        lines.extend(
            [
                f"### CLIMB_{index}",
                "",
                f"DATE: {item.session_date.isoformat()}",
                f"TYPE: {item.workout_type}",
                "",
                f"GYM: {detail.gym_or_crag if detail and detail.gym_or_crag else 'N/A'}",
                f"BOARD: {detail.board_name if detail and detail.board_name else 'N/A'}",
                f"ANGLE: {detail.angle_degrees if detail and detail.angle_degrees is not None else 'N/A'}",
                f"DURATION: {_duration(item.duration_minutes)}",
                f"RPE: {_number(item.rpe)}",
                "",
                "PERFORMANCE:",
            ]
        )
        attempts = detail.attempts if detail else []
        lines.extend(
            [
                f"- {row.grade or row.problem or 'N/A'}: attempts {row.attempts}, sends {row.send_count}"
                for row in attempts
            ]
            or ["- N/A"]
        )
        if item.workout_type == "BOULDERING":
            lines.extend(
                [
                    "",
                    "CURRENT_SET_PROGRESS:",
                    *_gym_progress_lines(_gym_set_on(db, item.session_date)),
                ]
            )
        lines.extend(["", "SUBJECTIVE:", item.notes or "N/A", ""])
    if not climbing:
        lines.extend(["N/A", ""])
    lines.extend(["## AUXILIARY_TRAINING", ""])
    for index, item in enumerate(auxiliary, 1):
        lines.extend(
            [
                f"### SESSION_{index}",
                "",
                f"DATE: {item.session_date.isoformat()}",
                f"TITLE: {item.title or item.workout_type}",
                f"DURATION: {_duration(item.duration_minutes)}",
                f"RPE: {_number(item.rpe)}",
                "",
                "DETAILS:",
                f"- {item.notes or 'N/A'}",
                "",
            ]
        )
    if not auxiliary:
        lines.extend(["N/A", ""])
    note_rows = list(
        db.scalars(
            select(models.TrainingNote).where(
                models.TrainingNote.created_at >= week_start,
                models.TrainingNote.created_at < week_end + timedelta(days=1),
            )
        )
    )
    lines.extend(
        [
            "## WEEK_NOTES",
            "",
            *([f"- {row.summary or row.cleaned_note}" for row in note_rows] or ["N/A"]),
            "",
            "## END_REPORT",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def _subjective_trends(sessions: list[models.CompletedSession], sport: Sport) -> list[str]:
    texts = [
        (item.subjective_feedback_text if sport == Sport.RUNNING else item.notes) or ""
        for item in sessions
        if item.sport == sport
    ]
    populated = [text for text in texts if text.strip()]
    if not populated:
        return ["- No subjective feedback was recorded."]
    combined = " ".join(populated).casefold()
    output = [f"- Subjective feedback was recorded for {len(populated)} session(s)."]
    if any(word in combined for word in ("heavy", "沉", "累", "fatigue", "疲劳", "疲勞")):
        output.append("- Fatigue or heavy-leg/effort language appeared during the month.")
    if any(word in combined for word in ("pain", "疼", "痛", "injury", "受伤", "受傷")):
        output.append(
            "- Pain or injury-related language was recorded; inspect the weekly reports for context."
        )
    if len(output) == 1:
        output.append("- No repeated fatigue or pain keyword pattern was detected.")
    return output


def monthly_report(db: Session, month_start: date) -> str:
    month_start = month_start.replace(day=1)
    month_end = date(
        month_start.year,
        month_start.month,
        calendar.monthrange(month_start.year, month_start.month)[1],
    )
    sessions = _sessions(db, month_start, month_end)
    running = [item for item in sessions if item.sport == Sport.RUNNING]
    climbing = [item for item in sessions if item.sport == Sport.CLIMBING]
    auxiliary = [item for item in sessions if item.sport not in {Sport.RUNNING, Sport.CLIMBING}]
    profile = core.get_profile(db)
    running_goal, climbing_goal = _goals(db)
    run_counts = Counter(item.workout_type for item in running)
    climb_counts = Counter(item.workout_type for item in climbing)
    weeks: dict[int, list[models.CompletedSession]] = defaultdict(list)
    for item in sessions:
        weeks[(item.session_date.day - 1) // 7 + 1].append(item)
    quality = [item for item in running if item.workout_type == "QUALITY"]
    long_runs = [
        item.running.distance_km
        for item in running
        if item.workout_type == "LONG_RUN" and item.running and item.running.distance_km
    ]
    grade_totals: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for item in climbing:
        for attempt in item.climbing.attempts if item.climbing else []:
            grade_totals[attempt.grade or attempt.problem or "N/A"][0] += attempt.attempts
            grade_totals[attempt.grade or attempt.problem or "N/A"][1] += attempt.send_count
    fitness_rows = list(
        db.scalars(
            select(models.RunningFitnessEstimate)
            .where(models.RunningFitnessEstimate.source_date.between(month_start, month_end))
            .order_by(models.RunningFitnessEstimate.source_date, models.RunningFitnessEstimate.id)
        )
    )
    lt2_rows = list(
        db.scalars(
            select(models.ThresholdEstimate)
            .where(
                models.ThresholdEstimate.estimate_type == "LT2",
                models.ThresholdEstimate.measured_at.between(month_start, month_end),
            )
            .order_by(models.ThresholdEstimate.measured_at, models.ThresholdEstimate.id)
        )
    )
    tb2_rows = list(
        db.scalars(
            select(models.TB2Benchmark)
            .where(models.TB2Benchmark.benchmark_date.between(month_start, month_end))
            .order_by(models.TB2Benchmark.benchmark_date, models.TB2Benchmark.id)
        )
    )
    gym_set_start = _gym_set_on(db, month_start)
    gym_set_end = _gym_set_on(db, month_end)

    def fitness_value(row: models.RunningFitnessEstimate | None) -> str:
        return (
            _duration(row.estimated_10k_seconds / 60)
            if row and row.estimated_10k_seconds is not None
            else "N/A"
        )

    def lt2_value(row: models.ThresholdEstimate | None) -> str:
        return _pace(row.pace_low_seconds_per_km) if row else "N/A"

    lines = [
        "# TRAINING_MONTHLY_REPORT_V1",
        "",
        "## REPORT_INFO",
        "",
        f"MONTH: {month_start:%Y-%m}",
        "",
        "## ATHLETE_GOALS",
        "",
        f"RUNNING_GOAL: {running_goal}",
        f"CLIMBING_GOAL: {climbing_goal}",
        "",
        "## CURRENT_STATE",
        "",
        f"RUNNING_PHASE: {profile.running_phase.value}",
        f"CLIMBING_PHASE: {profile.climbing_phase.value}",
        f"ESTIMATED_10K_START: {fitness_value(fitness_rows[0] if fitness_rows else None)}",
        f"ESTIMATED_10K_END: {fitness_value(fitness_rows[-1] if fitness_rows else None)}",
        f"LT2_PACE_START: {lt2_value(lt2_rows[0] if lt2_rows else None)}",
        f"LT2_PACE_END: {lt2_value(lt2_rows[-1] if lt2_rows else None)}",
        f"TB2_VERIFIED_START: {tb2_rows[0].verified_grade if tb2_rows else 'N/A'}",
        f"TB2_VERIFIED_END: {tb2_rows[-1].verified_grade if tb2_rows else 'N/A'}",
        "",
        "## RUNNING_MONTH",
        "",
        f"TOTAL_DISTANCE_KM: {_number(sum(item.running.distance_km or 0 for item in running if item.running))}",
        f"TOTAL_DURATION: {_duration(sum(item.duration_minutes for item in running))}",
        f"SESSION_COUNT: {len(running)}",
        "",
        f"EASY_COUNT: {run_counts['EASY']}",
        f"LONG_RUN_COUNT: {run_counts['LONG_RUN']}",
        f"QUALITY_COUNT: {run_counts['QUALITY']}",
        f"RACE_COUNT: {run_counts['RACE']}",
        "",
        "WEEKLY_DISTANCE:",
    ]
    for week in range(1, 6):
        if week in weeks:
            distance_km = sum(item.running.distance_km or 0 for item in weeks[week] if item.running)
            lines.append(f"- Week {week}: {_number(distance_km)} km")
    if not any(week in weeks for week in range(1, 6)):
        lines.append("- N/A")
    lines.extend(
        [
            "",
            "LONG_RUN_PROGRESSION:",
            *([f"- {_number(value)} km" for value in long_runs] or ["- N/A"]),
            "",
            "QUALITY_SESSIONS:",
        ]
    )
    lines.extend(
        [
            f"- Week {(item.session_date.day - 1) // 7 + 1}: {item.title or item.workout_type}"
            for item in quality
        ]
        or ["- N/A"]
    )
    lines.extend(
        [
            "",
            "RUNNING_SUBJECTIVE_TRENDS:",
            *_subjective_trends(sessions, Sport.RUNNING),
            "",
            "## CLIMBING_MONTH",
            "",
            f"SESSION_COUNT: {len(climbing)}",
            f"TOTAL_DURATION: {_duration(sum(item.duration_minutes for item in climbing))}",
            "",
            f"BOULDERING_COUNT: {climb_counts['BOULDERING']}",
            f"SPORT_CLIMBING_COUNT: {climb_counts['SPORT_CLIMBING']}",
            f"BOARD_COUNT: {climb_counts['BOARD']}",
            "",
            "TB2_BENCHMARK:",
            f"- Start: {tb2_rows[0].verified_grade if tb2_rows else 'N/A'}",
            f"- End: {tb2_rows[-1].verified_grade if tb2_rows else 'N/A'}",
            "",
            "BOARD_GRADE_SUMMARY:",
        ]
    )
    lines.extend(
        [
            f"- {grade}: attempts {values[0]}, sends {values[1]}"
            for grade, values in sorted(grade_totals.items())
        ]
        or ["- N/A"]
    )
    lines.extend(
        [
            "",
            "HOME_GYM_SET_START:",
            *_gym_progress_lines(gym_set_start),
            "",
            "HOME_GYM_SET_END:",
            *_gym_progress_lines(gym_set_end),
            "",
            "CLIMBING_SUBJECTIVE_TRENDS:",
            *_subjective_trends(sessions, Sport.CLIMBING),
            "",
            "## AUXILIARY_TRAINING",
            "",
            f"STRENGTH_SESSION_COUNT: {sum(item.sport == Sport.STRENGTH for item in auxiliary)}",
            f"MOBILITY_SESSION_COUNT: {sum(item.sport == Sport.MOBILITY_RECOVERY for item in auxiliary)}",
            "",
            "KEY_WORK:",
        ]
    )
    exercises = sorted(
        {row.exercise for item in auxiliary if item.strength for row in item.strength.sets}
    )
    lines.extend([f"- {item}" for item in exercises] or ["- N/A"])
    lines.extend(["", "## WEEKLY_SUMMARIES", ""])
    for week in range(1, 6):
        rows = weeks.get(week, [])
        if not rows:
            continue
        lines.extend(
            [
                f"### WEEK_{week}",
                f"RUNNING_DISTANCE: {_number(sum(item.running.distance_km or 0 for item in rows if item.running))} km",
                f"CLIMBING_SESSIONS: {sum(item.sport == Sport.CLIMBING for item in rows)}",
                "KEY_NOTES:",
                f"- {len(rows)} factual training session(s) recorded.",
                "",
            ]
        )
    if not weeks:
        lines.extend(["N/A", ""])
    month_notes = list(
        db.scalars(
            select(models.TrainingNote).where(
                models.TrainingNote.created_at >= month_start,
                models.TrainingNote.created_at < month_end + timedelta(days=1),
            )
        )
    )
    lines.extend(
        [
            "## MONTH_NOTES",
            "",
            *([f"- {row.summary or row.cleaned_note}" for row in month_notes] or ["N/A"]),
            "",
            "## END_REPORT",
        ]
    )
    return "\n".join(lines).strip() + "\n"

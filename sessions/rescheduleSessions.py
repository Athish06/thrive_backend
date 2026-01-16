import logging
from datetime import date, time, timedelta
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel

from db import get_supabase_client, handle_supabase_error, format_supabase_response
from users.settings import get_therapist_settings
from utils.date_utils import (
    parse_date_string,
    parse_time_string,
    format_date_iso,
    utc_now_iso,
)

logger = logging.getLogger(__name__)


class CascadeRescheduleRequest(BaseModel):
    """Request payload for cascading session reschedule operations."""

    include_weekends: bool = False


class SessionSummary(BaseModel):
    """Minimal representation of a session for rescheduling workflows."""

    id: int
    session_date: str
    start_time: str
    end_time: str
    student_name: Optional[str]


def _parse_time_value(value: Optional[str]) -> Optional[time]:
    if not value:
        return None
    parsed = parse_time_string(value)
    if parsed:
        return parsed
    if len(value) >= 5:
        return parse_time_string(value[:5])
    return None


def _format_student_name(session_row: Dict[str, Any]) -> str:
    child_info = session_row.get("children") or {}
    first = child_info.get("first_name") or ""
    last = child_info.get("last_name") or ""
    combined = f"{first} {last}".strip()
    if combined:
        return combined
    return session_row.get("student_name") or "Learner"


def _build_session_summary(session_row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": session_row.get("id"),
        "session_date": session_row.get("session_date"),
        "start_time": session_row.get("start_time"),
        "end_time": session_row.get("end_time"),
        "student_name": _format_student_name(session_row),
    }


def _shift_date_by_one(original: date, include_weekends: bool) -> date:
    new_date = original + timedelta(days=1)
    if include_weekends:
        return new_date

    while new_date.weekday() >= 5:  # 5 = Saturday, 6 = Sunday
        new_date += timedelta(days=1)
    return new_date


def _get_working_hours_map(settings: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    working_hours = (
        settings.get("account_section", {}).get("workingHours")
        if settings
        else None
    )
    mapping: Dict[str, Dict[str, Any]] = {}
    if isinstance(working_hours, list):
        for entry in working_hours:
            day = entry.get("day")
            if day:
                mapping[day] = entry
    return mapping


def _get_free_hours(settings: Dict[str, Any]) -> List[Dict[str, Any]]:
    free_hours = (
        settings.get("account_section", {}).get("freeHours")
        if settings
        else None
    )
    if isinstance(free_hours, list):
        return free_hours
    return []


def _check_working_hours(
    target_date: date,
    session_start: time,
    session_end: time,
    working_hours_map: Dict[str, Dict[str, Any]],
    include_weekends: bool,
) -> Optional[str]:
    day_name = target_date.strftime("%A")

    if target_date.weekday() >= 5 and include_weekends:
        # Therapist explicitly allowed weekend scheduling for this cascade
        return None

    day_schedule = working_hours_map.get(day_name)

    if not day_schedule:
        if target_date.weekday() >= 5:
            return (
                f"{day_name} is not configured as a working day. "
                "Enable weekend hours or include weekends in reschedule settings."
            )
        return None

    if not day_schedule.get("enabled", False):
        return f"{day_name} is not marked as a working day in your schedule."

    start_bound = _parse_time_value(day_schedule.get("startTime"))
    end_bound = _parse_time_value(day_schedule.get("endTime"))

    if start_bound and session_start < start_bound:
        return (
            f"Session starts before working hours on {day_name} "
            f"({session_start.strftime('%H:%M')} vs {start_bound.strftime('%H:%M')})."
        )

    if end_bound and session_end > end_bound:
        return (
            f"Session ends after working hours on {day_name} "
            f"({session_end.strftime('%H:%M')} vs {end_bound.strftime('%H:%M')})."
        )

    return None


def _check_free_time(
    target_date: date,
    session_start: time,
    session_end: time,
    free_hours: List[Dict[str, Any]],
) -> Optional[str]:
    if not free_hours:
        return None

    day_name = target_date.strftime("%A")
    for block in free_hours:
        if block.get("day") != day_name:
            continue

        block_start = _parse_time_value(block.get("startTime"))
        block_end = _parse_time_value(block.get("endTime"))
        if not block_start or not block_end:
            continue

        overlaps = session_start < block_end and session_end > block_start
        if overlaps:
            purpose = block.get("purpose") or "Personal time"
            return (
                f"Session overlaps with your free time block '{purpose}' "
                f"({block_start.strftime('%H:%M')} - {block_end.strftime('%H:%M')})."
            )

    return None


def _sessions_overlap(
    existing_start: time,
    existing_end: time,
    new_start: time,
    new_end: time,
) -> bool:
    return new_start < existing_end and new_end > existing_start


def _fetch_session(therapist_id: int, session_id: int) -> Optional[Dict[str, Any]]:
    supabase = get_supabase_client()
    result = (
        supabase.table("sessions")
        .select(
            "id, therapist_id, child_id, session_date, start_time, end_time, status, "
            "children!child_id (first_name, last_name)"
        )
        .eq("id", session_id)
        .eq("therapist_id", therapist_id)
        .single()
        .execute()
    )
    handle_supabase_error(result)
    return result.data if result.data else None


def _fetch_child_sessions(
    therapist_id: int,
    child_id: int,
    start_date: date,
) -> List[Dict[str, Any]]:
    supabase = get_supabase_client()
    result = (
        supabase.table("sessions")
        .select(
            "id, therapist_id, child_id, session_date, start_time, end_time, status, "
            "children!child_id (first_name, last_name)"
        )
        .eq("therapist_id", therapist_id)
        .eq("child_id", child_id)
        .eq("status", "scheduled")
        .gte("session_date", format_date_iso(start_date))
        .order("session_date", desc=False)
        .order("start_time", desc=False)
        .execute()
    )
    handle_supabase_error(result)
    data = format_supabase_response(result)
    return data or []


def _build_therapist_occupancy(
    therapist_id: int,
    exclude_session_ids: List[int],
    start_date: date,
) -> Dict[date, List[Tuple[time, time]]]:
    supabase = get_supabase_client()
    result = (
        supabase.table("sessions")
        .select("id, session_date, start_time, end_time, status")
        .eq("therapist_id", therapist_id)
        .eq("status", "scheduled")
        .gte("session_date", format_date_iso(start_date))
        .execute()
    )
    handle_supabase_error(result)
    data = format_supabase_response(result) or []

    occupancy: Dict[date, List[Tuple[time, time]]] = {}
    exclude_lookup = set(exclude_session_ids)

    for row in data:
        if row.get("id") in exclude_lookup:
            continue

        session_date_value = parse_date_string(row.get("session_date"))
        start = _parse_time_value(row.get("start_time"))
        end = _parse_time_value(row.get("end_time"))

        if not session_date_value or not start or not end:
            continue

        occupancy.setdefault(session_date_value, []).append((start, end))

    return occupancy


def _add_to_occupancy_map(
    occupancy: Dict[date, List[Tuple[time, time]]],
    target_date: date,
    session_start: time,
    session_end: time,
) -> None:
    slots = occupancy.setdefault(target_date, [])
    slots.append((session_start, session_end))


def _has_time_conflict(
    occupancy: Dict[date, List[Tuple[time, time]]],
    target_date: date,
    session_start: time,
    session_end: time,
) -> bool:
    slots = occupancy.get(target_date, [])
    for existing_start, existing_end in slots:
        if _sessions_overlap(existing_start, existing_end, session_start, session_end):
            return True
    return False


def _find_next_available_date(
    start_from: date,
    include_weekends: bool,
    allow_same_day: bool,
    session_start: time,
    session_end: time,
    working_hours_map: Dict[str, Dict[str, Any]],
    free_hours: List[Dict[str, Any]],
    occupancy: Dict[date, List[Tuple[time, time]]],
    max_iterations: int = 365,
) -> date:
    candidate = start_from
    tried_same_day = False

    for _ in range(max_iterations):
        if allow_same_day and not tried_same_day:
            tried_same_day = True
        else:
            candidate = _shift_date_by_one(candidate, include_weekends)

        working_issue = _check_working_hours(
            candidate, session_start, session_end, working_hours_map, include_weekends
        )
        if working_issue:
            continue

        free_time_issue = _check_free_time(candidate, session_start, session_end, free_hours)
        if free_time_issue:
            continue

        if _has_time_conflict(occupancy, candidate, session_start, session_end):
            continue

        return candidate

    raise ValueError(
        "Unable to find a suitable date for cascade reschedule within a year."
    )


async def check_session_ready_for_start(
    session_id: int, therapist_id: int
) -> Dict[str, Any]:
    """
    Validate whether a session can transition to an ongoing state.

    Returns a payload describing any rescheduling requirements.
    """

    session_row = _fetch_session(therapist_id, session_id)
    if not session_row:
        return {"exists": False, "requires_reschedule": False}

    child_id = session_row.get("child_id")
    session_date_value = parse_date_string(session_row.get("session_date"))
    today = date.today()

    if not session_date_value:
        message = (
            "Session date information is missing or invalid. Please reschedule this session "
            "before starting."
        )
        upcoming = (
            _fetch_child_sessions(therapist_id, child_id, today)
            if child_id
            else []
        )
        return {
            "requires_reschedule": True,
            "reason": message,
            "session": _build_session_summary(session_row),
            "upcoming": {
                "count": len(upcoming),
                "sessions": [_build_session_summary(s) for s in upcoming],
            },
        }

    if session_date_value > today:
        message = (
            "This session is scheduled for a future date. You can only start it on the scheduled "
            "day or after adjusting the session date."
        )
        upcoming = (
            _fetch_child_sessions(therapist_id, child_id, session_date_value)
            if child_id
            else []
        )
        return {
            "requires_reschedule": True,
            "reason": message,
            "session": _build_session_summary(session_row),
            "upcoming": {
                "count": len(upcoming),
                "sessions": [_build_session_summary(s) for s in upcoming],
            },
        }

    if session_date_value < today:
        message = (
            "This session date has already passed. Please reschedule to a current or future date "
            "before starting."
        )
        upcoming = (
            _fetch_child_sessions(therapist_id, child_id, min(session_date_value, today))
            if child_id
            else []
        )
        return {
            "requires_reschedule": True,
            "reason": message,
            "session": _build_session_summary(session_row),
            "upcoming": {
                "count": len(upcoming),
                "sessions": [_build_session_summary(s) for s in upcoming],
            },
        }

    session_start = _parse_time_value(session_row.get("start_time"))
    session_end = _parse_time_value(session_row.get("end_time"))

    if not session_start or not session_end:
        message = (
            "Session timing information is incomplete. Please reschedule this session "
            "before starting."
        )
        upcoming = (
            _fetch_child_sessions(therapist_id, child_id, session_date_value or today)
            if child_id
            else []
        )
        return {
            "requires_reschedule": True,
            "reason": message,
            "session": _build_session_summary(session_row),
            "upcoming": {
                "count": len(upcoming),
                "sessions": [_build_session_summary(s) for s in upcoming],
            },
        }

    if session_start >= session_end:
        message = (
            "Session start time must be earlier than the end time. "
            "Please reschedule before starting."
        )
        upcoming = (
            _fetch_child_sessions(therapist_id, child_id, session_date_value or today)
            if child_id
            else []
        )
        return {
            "requires_reschedule": True,
            "reason": message,
            "session": _build_session_summary(session_row),
            "upcoming": {
                "count": len(upcoming),
                "sessions": [_build_session_summary(s) for s in upcoming],
            },
        }

    return {
        "requires_reschedule": False,
        "session": _build_session_summary(session_row),
    }


async def cascade_reschedule_sessions(
    session_id: int,
    therapist_id: int,
    include_weekends: bool,
) -> Dict[str, Any]:
    """
    Shift the selected session and all upcoming scheduled sessions by one day.

    Performs working hours, personal time, and overlap validation for each session.
    """

    target_session = _fetch_session(therapist_id, session_id)
    if not target_session:
        raise ValueError("Session not found or access denied.")

    target_date = parse_date_string(target_session.get("session_date"))
    if not target_date:
        raise ValueError("Session date is invalid and cannot be parsed.")

    child_id = target_session.get("child_id")
    if not child_id:
        raise ValueError("Session is missing child information for reschedule.")

    fetch_start_date = min(target_date, date.today())
    upcoming = _fetch_child_sessions(therapist_id, child_id, fetch_start_date)
    if not upcoming:
        raise ValueError("No upcoming scheduled sessions found to reschedule.")

    upcoming_sorted = sorted(
        upcoming,
        key=lambda row: (
            row.get("session_date") or "",
            row.get("start_time") or "",
            row.get("id") or 0,
        ),
    )

    sessions_to_reschedule: List[Dict[str, Any]] = []
    for row in upcoming_sorted:
        if row.get("id") == session_id:
            sessions_to_reschedule.insert(0, row)
        else:
            sessions_to_reschedule.append(row)

    settings = get_therapist_settings(therapist_id)
    working_hours_map = _get_working_hours_map(settings or {})
    free_hours = _get_free_hours(settings or {})

    session_ids = [row.get("id") for row in sessions_to_reschedule if row.get("id")]
    occupancy = _build_therapist_occupancy(
        therapist_id,
        exclude_session_ids=session_ids,
        start_date=min(fetch_start_date, date.today()),
    )

    proposed_updates: List[Dict[str, Any]] = []
    last_assigned_date: Optional[date] = None
    today_value = date.today()

    for index, session_row in enumerate(sessions_to_reschedule):
        session_start = _parse_time_value(session_row.get("start_time"))
        session_end = _parse_time_value(session_row.get("end_time"))

        if not session_start or not session_end:
            raise ValueError(
                "One or more sessions have incomplete timing information. "
                "Please reschedule them individually."
            )

        if session_start >= session_end:
            raise ValueError(
                "One or more sessions have invalid time ranges. Please fix those sessions manually "
                "before cascading reschedule."
            )

        original_date = parse_date_string(session_row.get("session_date"))
        if not original_date:
            raise ValueError("Unable to parse session date for an upcoming session.")

        baseline = max(original_date, today_value)
        if last_assigned_date and last_assigned_date > baseline:
            baseline = last_assigned_date

        allow_same_day = index != 0

        new_date = _find_next_available_date(
            start_from=baseline,
            include_weekends=include_weekends,
            allow_same_day=allow_same_day,
            session_start=session_start,
            session_end=session_end,
            working_hours_map=working_hours_map,
            free_hours=free_hours,
            occupancy=occupancy,
        )

        _add_to_occupancy_map(occupancy, new_date, session_start, session_end)
        proposed_updates.append(
            {
                "session": session_row,
                "previous_date": original_date,
                "new_date": new_date,
            }
        )
        last_assigned_date = new_date

    # Apply updates sequentially
    supabase = get_supabase_client()
    updated_sessions: List[Dict[str, Any]] = []

    for item in proposed_updates:
        session_row = item["session"]
        new_date = item["new_date"]

        update_payload = {
            "session_date": format_date_iso(new_date),
            "updated_at": utc_now_iso(),
        }

        result = (
            supabase.table("sessions")
            .update(update_payload)
            .eq("id", session_row.get("id"))
            .eq("therapist_id", therapist_id)
            .execute()
        )
        handle_supabase_error(result)
        if not result.data:
            raise ValueError(
                f"Failed to update session {session_row.get('id')} during reschedule."
            )

        updated_sessions.append(
            {
                "session_id": session_row.get("id"),
                "student_name": _format_student_name(session_row),
                "previous_date": format_date_iso(item["previous_date"]),
                "new_date": format_date_iso(new_date),
                "start_time": session_row.get("start_time"),
                "end_time": session_row.get("end_time"),
            }
        )

    logger.info(
        "Cascade reschedule applied to %s sessions for therapist %s",
        len(updated_sessions),
        therapist_id,
    )

    return {
        "total_updated": len(updated_sessions),
        "sessions": updated_sessions,
        "include_weekends": include_weekends,
    }

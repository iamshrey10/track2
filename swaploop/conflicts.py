"""Time, value and campus conflict checks. Pure functions, no I/O."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum

from swaploop.loop_finder import ValueExchange
from swaploop.models import FreeWindow
from swaploop.timeutil import DAYS

MIN_MEETING_MINUTES = 30
VALUE_GAP_LIMIT_USD = 25
VALUE_GAP_LIMIT_SHARE = 0.5  # of the value given

DEFAULT_CAMPUS = "Tempe"
MEETING_SPOTS = {
    "Tempe": ("Memorial Union", "Hayden Library"),
}


class TimeStatus(str, Enum):
    SHARED = "SHARED"
    CONFLICT = "CONFLICT"
    INFEASIBLE = "INFEASIBLE"


@dataclass(frozen=True)
class TimeResolution:
    status: TimeStatus
    day: str | None = None
    window_start: int | None = None
    window_end: int | None = None
    meeting_min: int | None = None
    dissenter_ids: tuple[int, ...] = ()


@dataclass(frozen=True)
class ValueCheck:
    student_id: int
    given: int
    received: int
    gap: int
    flagged: bool


@dataclass(frozen=True)
class CampusResolution:
    campus: str
    place: str
    conflict: bool
    confirm_ids: tuple[int, ...] = ()


def _coverage_intervals(
    windows_by_student: Mapping[int, Sequence[FreeWindow]],
) -> list[tuple[str, int, int, frozenset[int]]]:
    """Split each day into stretches covered by the same set of students."""
    intervals = []
    for day in DAYS:
        day_windows = [
            (student_id, w.start_min, w.end_min)
            for student_id, windows in windows_by_student.items()
            for w in windows
            if w.day == day
        ]
        boundaries = sorted({edge for _, start, end in day_windows for edge in (start, end)})
        merged: list[list] = []
        for start, end in zip(boundaries, boundaries[1:]):
            covering = frozenset(
                sid for sid, w_start, w_end in day_windows if w_start <= start and end <= w_end
            )
            if not covering:
                continue
            if merged and merged[-1][2] == start and merged[-1][3] == covering:
                merged[-1][2] = end
            else:
                merged.append([day, start, end, covering])
        intervals.extend(tuple(item) for item in merged)
    return intervals


def resolve_time(windows_by_student: Mapping[int, Sequence[FreeWindow]]) -> TimeResolution:
    """Find a meeting time: everyone's shared window, else the one most people share."""
    participants = frozenset(windows_by_student)
    usable = [
        interval
        for interval in _coverage_intervals(windows_by_student)
        if interval[2] - interval[1] >= MIN_MEETING_MINUTES and len(interval[3]) >= 2
    ]
    if not usable:
        return TimeResolution(TimeStatus.INFEASIBLE)

    # most participants first, then longest, then earliest in the week
    day, start, end, covering = min(
        usable, key=lambda i: (-len(i[3]), -(i[2] - i[1]), DAYS.index(i[0]), i[1])
    )
    dissenters = tuple(sorted(participants - covering))
    return TimeResolution(
        status=TimeStatus.CONFLICT if dissenters else TimeStatus.SHARED,
        day=day,
        window_start=start,
        window_end=end,
        meeting_min=start + (end - start) // 2,
        dissenter_ids=dissenters,
    )


def check_values(exchanges: Sequence[ValueExchange]) -> list[ValueCheck]:
    """Flag participants who come out behind by more than the allowed gap.

    Someone who receives more than they give has nothing to accept, so only a
    shortfall can be flagged.
    """
    checks = []
    for exchange in exchanges:
        shortfall = exchange.given - exchange.received
        flagged = shortfall > 0 and (
            shortfall > VALUE_GAP_LIMIT_USD or shortfall > VALUE_GAP_LIMIT_SHARE * exchange.given
        )
        checks.append(
            ValueCheck(exchange.student_id, exchange.given, exchange.received, exchange.gap, flagged)
        )
    return checks


def choose_meeting_spot(campus_by_student: Mapping[int, str | None]) -> CampusResolution:
    """Pick the meeting place from the majority campus; students elsewhere must confirm."""
    counts: dict[str, int] = {}
    for campus in campus_by_student.values():
        if campus:
            key = campus.strip().casefold()
            counts[key] = counts.get(key, 0) + 1

    majority = min(counts, key=lambda key: (-counts[key], key)) if counts else None
    spots_by_campus = {name.casefold(): (name, spots) for name, spots in MEETING_SPOTS.items()}
    campus_name, spots = spots_by_campus.get(
        majority, (DEFAULT_CAMPUS, MEETING_SPOTS[DEFAULT_CAMPUS])
    )

    confirm_ids = tuple(
        sorted(
            student_id
            for student_id, campus in campus_by_student.items()
            if not campus or campus.strip().casefold() != campus_name.casefold()
        )
    )
    return CampusResolution(campus_name, spots[0], bool(confirm_ids), confirm_ids)

"""Weekday and clock-time parsing/formatting. Times are minutes since midnight."""

import re

DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

_DAY_ALIASES = {
    "mon": "Mon", "monday": "Mon",
    "tue": "Tue", "tues": "Tue", "tuesday": "Tue",
    "wed": "Wed", "weds": "Wed", "wednesday": "Wed",
    "thu": "Thu", "thur": "Thu", "thurs": "Thu", "thursday": "Thu",
    "fri": "Fri", "friday": "Fri",
    "sat": "Sat", "saturday": "Sat",
    "sun": "Sun", "sunday": "Sun",
}

_TIME_RE = re.compile(r"^(\d{1,2})(?::(\d{2}))?\s*(am|pm)?$")


def parse_day(text: str) -> str:
    day = _DAY_ALIASES.get(text.strip().lower().rstrip("."))
    if day is None:
        raise ValueError(f"Unknown day '{text}'. Use a weekday such as Thu.")
    return day


def _split_time(text: str) -> tuple[int, int, str | None]:
    match = _TIME_RE.match(text.strip().lower())
    if not match:
        raise ValueError(f"Could not read the time '{text}'. Try something like 4 PM or 4:30 PM.")
    hour, minute, meridiem = int(match.group(1)), int(match.group(2) or 0), match.group(3)
    if minute > 59 or hour > 12 or hour == 0:
        raise ValueError(f"'{text}' is not a valid 12-hour time.")
    return hour, minute, meridiem


def _to_minutes(hour: int, minute: int, meridiem: str) -> int:
    return (hour % 12 + (12 if meridiem == "pm" else 0)) * 60 + minute


def parse_time(text: str) -> int:
    hour, minute, meridiem = _split_time(text)
    if meridiem is None:
        raise ValueError(f"Add AM or PM to '{text}'.")
    return _to_minutes(hour, minute, meridiem)


def parse_time_range(text: str) -> tuple[int, int]:
    """Read '4-6 PM' or '11 AM - 1 PM'. A missing AM/PM on the start borrows the end's."""
    parts = re.split(r"\s*(?:-|–|—|to)\s*", text.strip(), maxsplit=1)
    if len(parts) != 2:
        raise ValueError(f"Could not read the range '{text}'. Try 4-6 PM.")

    start_hour, start_minute, start_meridiem = _split_time(parts[0])
    end_hour, end_minute, end_meridiem = _split_time(parts[1])
    if end_meridiem is None:
        raise ValueError(f"Add AM or PM to the end time in '{text}'.")

    end = _to_minutes(end_hour, end_minute, end_meridiem)
    if start_meridiem is not None:
        return _to_minutes(start_hour, start_minute, start_meridiem), end

    start = _to_minutes(start_hour, start_minute, end_meridiem)
    if start >= end and end_meridiem == "pm":
        # "11-1 PM" reads as 11 AM to 1 PM
        start = _to_minutes(start_hour, start_minute, "am")
    return start, end


def parse_window(text: str) -> tuple[str, int, int]:
    """Read 'Thu 4-6 PM' into (day, start_min, end_min)."""
    day_text, _, range_text = text.strip().partition(" ")
    start, end = parse_time_range(range_text)
    return parse_day(day_text), start, end


def format_time(minutes: int) -> str:
    hour, minute = divmod(minutes, 60)
    suffix = "AM" if hour < 12 else "PM"
    return f"{hour % 12 or 12}:{minute:02d} {suffix}"


def format_range(start_min: int, end_min: int) -> str:
    return f"{format_time(start_min)}-{format_time(end_min)}"


def format_slot(day: str, start_min: int, end_min: int | None = None) -> str:
    if end_min is None:
        return f"{day} {format_time(start_min)}"
    return f"{day} {format_range(start_min, end_min)}"

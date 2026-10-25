import pytest

from swaploop.timeutil import (
    format_range,
    format_slot,
    format_time,
    parse_day,
    parse_time,
    parse_time_range,
    parse_window,
)


@pytest.mark.parametrize("text", ["Thu", "thu", "THURSDAY", "Thurs", " thu. "])
def test_parse_day_accepts_common_spellings(text):
    assert parse_day(text) == "Thu"


def test_parse_day_rejects_unknown():
    with pytest.raises(ValueError):
        parse_day("Someday")


@pytest.mark.parametrize(
    "text, expected",
    [("4 PM", 960), ("4:30 pm", 990), ("12 AM", 0), ("12 PM", 720), ("11:59 PM", 1439)],
)
def test_parse_time(text, expected):
    assert parse_time(text) == expected


@pytest.mark.parametrize("text", ["4", "13 PM", "0 AM", "4:75 PM", "noon"])
def test_parse_time_rejects_bad_input(text):
    with pytest.raises(ValueError):
        parse_time(text)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("4-6 PM", (960, 1080)),
        ("4 PM - 6 PM", (960, 1080)),
        ("11 AM-1 PM", (660, 780)),
        ("11-1 PM", (660, 780)),
        ("3:30-5 PM", (930, 1020)),
        ("2 to 5 PM", (840, 1020)),
    ],
)
def test_parse_time_range(text, expected):
    assert parse_time_range(text) == expected


def test_parse_time_range_needs_end_meridiem():
    with pytest.raises(ValueError):
        parse_time_range("4-6")


def test_parse_window_reads_day_and_range():
    assert parse_window("Thu 4-6 PM") == ("Thu", 960, 1080)


def test_formatting():
    assert format_time(990) == "4:30 PM"
    assert format_time(0) == "12:00 AM"
    assert format_time(720) == "12:00 PM"
    assert format_range(960, 1020) == "4:00 PM-5:00 PM"
    assert format_slot("Thu", 990) == "Thu 4:30 PM"
    assert format_slot("Thu", 960, 1020) == "Thu 4:00 PM-5:00 PM"

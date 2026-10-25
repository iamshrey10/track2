import pytest

from swaploop.conflicts import (
    TimeStatus,
    check_values,
    choose_meeting_spot,
    resolve_time,
)
from swaploop.loop_finder import ValueExchange
from tests.factories import window


def windows(**by_student):
    """windows(s1=["Thu 4-6 PM"], ...) keyed by the number after 's'."""
    return {int(key[1:]): [window(int(key[1:]), text) for text in texts] for key, texts in by_student.items()}


# time

def test_everyone_shares_a_window():
    result = resolve_time(windows(s1=["Thu 3-5 PM"], s2=["Thu 4-6 PM"]))
    assert result.status is TimeStatus.SHARED
    assert (result.day, result.window_start, result.window_end) == ("Thu", 960, 1020)
    assert result.meeting_min == 990  # 4:30 PM
    assert result.dissenter_ids == ()


def test_seed_time_conflict_proposes_thursday_for_rohan():
    result = resolve_time(
        windows(
            s1=["Thu 4-6 PM"],
            s2=["Tue 2-5 PM"],
            s3=["Thu 3-5 PM"],
            s4=["Thu 4-7 PM"],
        )
    )
    assert result.status is TimeStatus.CONFLICT
    assert (result.day, result.window_start, result.window_end) == ("Thu", 960, 1020)
    assert result.meeting_min == 990
    assert result.dissenter_ids == (2,)


def test_no_overlap_anywhere_is_infeasible():
    result = resolve_time(windows(s1=["Mon 9-10 AM"], s2=["Tue 9-10 AM"]))
    assert result.status is TimeStatus.INFEASIBLE


def test_overlap_under_thirty_minutes_does_not_count():
    result = resolve_time(windows(s1=["Thu 4-5 PM"], s2=["Thu 4:50-6 PM"]))
    assert result.status is TimeStatus.INFEASIBLE


def test_exactly_thirty_minutes_is_enough():
    result = resolve_time(windows(s1=["Thu 4-5 PM"], s2=["Thu 4:30-6 PM"]))
    assert result.status is TimeStatus.SHARED
    assert result.meeting_min == 16 * 60 + 45


def test_student_without_windows_is_a_dissenter():
    result = resolve_time({1: [window(1, "Thu 4-6 PM")], 2: [window(2, "Thu 4-6 PM")], 3: []})
    assert result.status is TimeStatus.CONFLICT
    assert result.dissenter_ids == (3,)


def test_nobody_has_windows_is_infeasible():
    assert resolve_time({1: [], 2: []}).status is TimeStatus.INFEASIBLE


def test_longest_then_earliest_window_wins_ties():
    longer = resolve_time(windows(s1=["Mon 9-10 AM", "Wed 9-11 AM"], s2=["Mon 9-10 AM", "Wed 9-11 AM"]))
    assert (longer.day, longer.window_start) == ("Wed", 540)

    earlier = resolve_time(windows(s1=["Mon 9-10 AM", "Wed 9-10 AM"], s2=["Mon 9-10 AM", "Wed 9-10 AM"]))
    assert earlier.day == "Mon"


def test_overlapping_windows_of_one_student_do_not_double_count():
    result = resolve_time(windows(s1=["Thu 3-5 PM", "Thu 4-6 PM"], s2=["Thu 4-5 PM"]))
    assert result.status is TimeStatus.SHARED
    assert (result.window_start, result.window_end) == (960, 1020)


def test_highest_coverage_beats_longer_window_with_fewer_people():
    result = resolve_time(
        windows(
            s1=["Thu 4-5 PM", "Fri 1-5 PM"],
            s2=["Thu 4-5 PM", "Fri 1-5 PM"],
            s3=["Thu 4-5 PM"],
            s4=["Tue 9-10 AM"],
        )
    )
    assert result.day == "Thu"
    assert result.dissenter_ids == (4,)


# value

def flagged(given, received):
    (check,) = check_values([ValueExchange(1, given, received)])
    return check.flagged


def test_rohan_is_flagged_in_the_seed():
    checks = check_values(
        [ValueExchange(1, 40, 60), ValueExchange(4, 20, 40), ValueExchange(3, 15, 20), ValueExchange(2, 60, 15)]
    )
    assert [c.student_id for c in checks if c.flagged] == [2]
    rohan = checks[3]
    assert (rohan.given, rohan.received, rohan.gap) == (60, 15, 45)


def test_receiving_more_than_you_give_is_never_flagged():
    assert not flagged(20, 40)
    assert not flagged(10, 500)


def test_dollar_limit_boundary():
    assert not flagged(100, 75)   # $25 short, under 50% of 100
    assert flagged(100, 74)       # $26 short
    assert flagged(1000, 974)


def test_share_limit_boundary():
    assert not flagged(20, 10)    # exactly 50% of value given
    assert flagged(20, 9)
    assert not flagged(20, 20)


# campus

def test_same_campus_uses_first_spot():
    result = choose_meeting_spot({1: "Tempe", 2: "tempe"})
    assert (result.campus, result.place, result.conflict) == ("Tempe", "Memorial Union", False)
    assert result.confirm_ids == ()


def test_mixed_campuses_use_majority_and_ask_the_others():
    result = choose_meeting_spot({1: "Tempe", 2: "Tempe", 3: "Polytechnic"})
    assert result.place == "Memorial Union"
    assert result.conflict is True
    assert result.confirm_ids == (3,)


def test_tied_campus_without_a_spot_list_falls_back_to_default():
    result = choose_meeting_spot({1: "Tempe", 2: "Downtown"})
    assert result.campus == "Tempe"  # Downtown has no spot list, so the default applies
    assert result.confirm_ids == (2,)


def test_unknown_campus_falls_back_to_tempe_list_and_asks_everyone():
    result = choose_meeting_spot({1: "Mesa", 2: "Mesa"})
    assert result.place == "Memorial Union"
    assert result.conflict is True
    assert result.confirm_ids == (1, 2)


def test_student_without_a_campus_is_asked_to_confirm():
    result = choose_meeting_spot({1: "Tempe", 2: None})
    assert result.confirm_ids == (2,)


@pytest.mark.parametrize("campuses", [{}, {1: None}])
def test_no_campus_data_still_returns_a_default_spot(campuses):
    assert choose_meeting_spot(campuses).place == "Memorial Union"

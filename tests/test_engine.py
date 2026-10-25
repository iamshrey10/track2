import pytest

from swaploop.db import Database
from swaploop.demo import SEED_STUDENTS, seed_demo
from swaploop.engine import AnswerOutcome, SwapEngine
from swaploop.messaging import RecordingMessenger
from swaploop.models import Answer, Channel, LoopStatus, MessageKind
from swaploop.timeutil import parse_window

NAMES = [seed.name for seed in SEED_STUDENTS]


@pytest.fixture
def messenger():
    return RecordingMessenger()


@pytest.fixture
def engine(messenger):
    return SwapEngine(Database(), messenger)


@pytest.fixture
def seeded(engine):
    seed_demo(engine)
    ids = {s.name: s.id for s in engine.db.list_students()}
    (loop,) = engine.db.list_loops(LoopStatus.PENDING)
    return engine, ids, loop


def add_student(engine, name, campus, window, have, need):
    student = engine.add_student(name, campus=campus)
    engine.add_free_window(student.id, *parse_window(window))
    engine.add_need(student.id, need)
    engine.add_have(student.id, *have)
    return student


# registration

def test_listing_is_anonymous_and_shows_item_campus_and_windows(engine, messenger):
    student = engine.add_student("Ann", campus="Tempe")
    engine.add_free_window(student.id, *parse_window("Thu 4-6 PM"))
    engine.add_have(student.id, "desk lamp", "good", 20)

    (listing,) = messenger.of_kind(MessageKind.LISTING)
    assert listing.channel is Channel.SWAP_ROOM
    assert "Agent A" in listing.body and "Ann" not in listing.body
    assert "desk lamp" in listing.body and "good" in listing.body and "$20" in listing.body
    assert "Tempe" in listing.body and "Thu 4:00 PM-6:00 PM" in listing.body


def test_bad_registrations_are_rejected(engine):
    student = engine.add_student("Ann")
    with pytest.raises(ValueError):
        engine.add_have(student.id, "  ", "good", 10)
    with pytest.raises(ValueError):
        engine.add_have(student.id, "lamp", "", 10)
    with pytest.raises(ValueError):
        engine.add_have(student.id, "lamp", "good", -1)
    with pytest.raises(ValueError):
        engine.add_need(student.id, " ")
    with pytest.raises(ValueError, match="enter the window again"):
        engine.add_free_window(student.id, "Thu", 1080, 960)
    with pytest.raises(ValueError):
        engine.set_campus(student.id, " ")


def test_status_lists_everything(engine):
    student = add_student(engine, "Ann", "Tempe", "Thu 4-6 PM", ("desk lamp", "good", 20), "bike lock")
    text = engine.status_text(student.id)
    assert "desk lamp (good, $20)" in text
    assert "bike lock" in text
    assert "Thu 4:00 PM-6:00 PM" in text
    assert "Campus: Tempe" in text


# seed scenario

def test_seed_opens_exactly_one_four_way_loop(seeded):
    engine, ids, loop = seeded
    legs = engine.db.get_legs(loop.id)
    order = [next(n for n, i in ids.items() if i == leg.giver_id) for leg in legs]
    assert order == ["Shreyas", "Shravani", "Bhavisha", "Rohan"]
    assert engine.db.list_haves(unreserved_only=True) == []


def test_seed_loop_meeting_and_stored_conflicts(seeded):
    engine, ids, loop = seeded
    assert (loop.meeting_day, loop.meeting_min, loop.meeting_place) == ("Thu", 990, "Memorial Union")
    assert loop.conflicts["time"]["status"] == "CONFLICT"
    assert loop.conflicts["time"]["dissenter_ids"] == [ids["Rohan"]]
    flagged = [v["student_id"] for v in loop.conflicts["values"] if v["flagged"]]
    assert flagged == [ids["Rohan"]]
    assert loop.conflicts["campus"]["conflict"] is False


def test_rohan_prompt_shows_time_change_and_value_gap_others_do_not(seeded, messenger):
    _, ids, _ = seeded
    prompts = {m.recipient_name: m for m in messenger.of_kind(MessageKind.PROMPT)}
    assert set(prompts) == set(NAMES)

    rohan = prompts["Rohan"].body
    assert "TIME CHANGE" in rohan and "Tue 2:00 PM-5:00 PM" in rohan and "Thu 4:00 PM-5:00 PM" in rohan
    assert "VALUE GAP" in rohan and "$60" in rohan and "$15" in rohan and "$45" in rohan
    assert "Thu 4:30 PM at Memorial Union" in rohan

    for name in NAMES:
        if name != "Rohan":
            assert "TIME CHANGE" not in prompts[name].body
            assert "VALUE GAP" not in prompts[name].body


def test_prompts_go_to_demo_console_with_loop_id_for_buttons(seeded, messenger):
    _, _, loop = seeded
    for prompt in messenger.of_kind(MessageKind.PROMPT):
        assert prompt.channel is Channel.DEMO_CONSOLE
        assert prompt.loop_id == loop.id


def test_agent_notes_cover_time_value_and_meeting_spot(seeded, messenger):
    notes = "\n".join(m.body for m in messenger.of_kind(MessageKind.AGENT_NOTE))
    assert "Agent B: my student is not free then" in notes
    assert "Thu 4:00 PM-5:00 PM" in notes
    assert "$60" in notes and "$15" in notes
    assert "Memorial Union" in notes


def test_no_names_in_swap_room_until_the_loop_locks(seeded, messenger):
    room = [m for m in messenger.messages if m.channel is Channel.SWAP_ROOM]
    assert room
    for message in room:
        assert not any(name in message.body for name in NAMES), message.body


def test_every_student_message_is_mirrored_to_the_swap_room(seeded, messenger):
    to_students = [m for m in messenger.messages if m.recipient_id is not None]
    audits = messenger.of_kind(MessageKind.AUDIT)
    assert len(audits) == len(to_students) == 4
    assert all(m.channel is Channel.SWAP_ROOM for m in audits)


def test_everything_sent_is_logged(seeded, messenger):
    logged = seeded[0].db.list_messages()
    assert [(m.channel, m.kind, m.body) for m in logged] == [
        (m.channel, m.kind, m.body) for m in messenger.messages
    ]


# confirmation

def answer_all(engine, ids, loop, order=NAMES):
    return [engine.answer(loop.id, ids[name], True) for name in order]


def test_loop_locks_only_after_everyone_accepts(seeded):
    engine, ids, loop = seeded
    outcomes = answer_all(engine, ids, loop)
    assert outcomes == [AnswerOutcome.RECORDED] * 3 + [AnswerOutcome.LOCKED]
    assert engine.db.get_loop(loop.id).status is LoopStatus.LOCKED


def test_final_plan_goes_to_room_and_every_participant(seeded, messenger):
    engine, ids, loop = seeded
    answer_all(engine, ids, loop)

    plans = messenger.of_kind(MessageKind.FINAL_PLAN)
    assert len(plans) == 5
    assert {p.recipient_name for p in plans} == {None, *NAMES}
    body = plans[0].body
    assert plans[0].channel is Channel.SWAP_ROOM
    assert "Shreyas gives calculus textbook to Shravani" in body
    assert "Rohan gives mini-fridge to Shreyas" in body
    assert "Thu 4:30 PM at Memorial Union" in body
    assert all(p.body == body for p in plans)


def test_not_locked_while_someone_has_not_answered(seeded, messenger):
    engine, ids, loop = seeded
    answer_all(engine, ids, loop, order=["Shreyas", "Shravani", "Bhavisha"])
    assert engine.db.get_loop(loop.id).status is LoopStatus.PENDING
    assert messenger.of_kind(MessageKind.FINAL_PLAN) == []


def test_decline_releases_items_and_tells_everyone(seeded, messenger):
    engine, ids, loop = seeded
    engine.answer(loop.id, ids["Shreyas"], True)
    outcome = engine.answer(loop.id, ids["Rohan"], False)

    assert outcome is AnswerOutcome.RELEASED
    released = engine.db.get_loop(loop.id)
    assert released.status is LoopStatus.RELEASED and released.released_by == ids["Rohan"]

    infos = {m.recipient_name: m.body for m in messenger.of_kind(MessageKind.INFO)}
    assert set(infos) == set(NAMES)
    assert "You declined" in infos["Rohan"]
    assert "cancelled" in infos["Shreyas"]


def test_declined_loop_is_not_proposed_again(seeded):
    engine, ids, loop = seeded
    engine.answer(loop.id, ids["Rohan"], False)

    assert engine.db.list_loops(LoopStatus.PENDING) == []
    assert len(engine.db.list_loops()) == 1
    assert len(engine.db.list_haves(unreserved_only=True)) == 4


def test_after_a_decline_search_finds_another_loop(engine):
    ann = add_student(engine, "Ann", "Tempe", "Thu 4-6 PM", ("lamp", "good", 20), "book")
    ben = add_student(engine, "Ben", "Tempe", "Thu 4-6 PM", ("book", "good", 20), "lamp")
    cal = add_student(engine, "Cal", "Tempe", "Thu 4-6 PM", ("book", "good", 20), "lamp")
    (first,) = engine.db.list_loops(LoopStatus.PENDING)
    assert {leg.giver_id for leg in engine.db.get_legs(first.id)} == {ann.id, ben.id}

    engine.answer(first.id, ben.id, False)

    (second,) = engine.db.list_loops(LoopStatus.PENDING)
    assert {leg.giver_id for leg in engine.db.get_legs(second.id)} == {ann.id, cal.id}


def test_repeat_and_late_answers_are_ignored(seeded):
    engine, ids, loop = seeded
    assert engine.answer(loop.id, ids["Shreyas"], True) is AnswerOutcome.RECORDED
    assert engine.answer(loop.id, ids["Shreyas"], False) is AnswerOutcome.ALREADY_ANSWERED
    assert engine.db.get_confirmations(loop.id)[ids["Shreyas"]] is Answer.ACCEPTED

    engine.answer(loop.id, ids["Rohan"], False)
    assert engine.answer(loop.id, ids["Shravani"], True) is AnswerOutcome.LOOP_CLOSED
    assert engine.answer(999, ids["Shravani"], True) is AnswerOutcome.LOOP_CLOSED


def test_outsider_cannot_answer(seeded):
    engine, ids, loop = seeded
    stranger = engine.add_student("Zed")
    assert engine.answer(loop.id, stranger.id, True) is AnswerOutcome.NOT_PARTICIPANT


# loops without conflicts, and unworkable loops

def test_two_way_loop_with_no_conflicts_has_plain_prompts(engine, messenger):
    ann = add_student(engine, "Ann", "Tempe", "Thu 4-6 PM", ("lamp", "good", 20), "book")
    ben = add_student(engine, "Ben", "Tempe", "Thu 5-7 PM", ("book", "good", 25), "lamp")

    (loop,) = engine.db.list_loops(LoopStatus.PENDING)
    assert (loop.meeting_day, loop.meeting_min) == ("Thu", 17 * 60 + 30)
    for prompt in messenger.of_kind(MessageKind.PROMPT):
        assert "TIME CHANGE" not in prompt.body and "VALUE GAP" not in prompt.body
        assert "Accepting also means" not in prompt.body

    assert engine.answer(loop.id, ann.id, True) is AnswerOutcome.RECORDED
    assert engine.answer(loop.id, ben.id, True) is AnswerOutcome.LOCKED


def test_mixed_campus_asks_the_other_student_to_confirm(engine, messenger):
    add_student(engine, "Ann", "Tempe", "Thu 4-6 PM", ("lamp", "good", 20), "book")
    add_student(engine, "Ben", "Tempe", "Thu 4-6 PM", ("pen", "good", 20), "lamp")
    cal = add_student(engine, "Cal", "Polytechnic", "Thu 4-6 PM", ("book", "good", 20), "pen")

    prompts = {m.recipient_name: m.body for m in messenger.of_kind(MessageKind.PROMPT)}
    assert "MEETING SPOT" in prompts["Cal"]
    assert "MEETING SPOT" not in prompts["Ann"]
    (loop,) = engine.db.list_loops(LoopStatus.PENDING)
    assert loop.conflicts["campus"]["confirm_ids"] == [cal.id]


def test_loop_without_a_workable_time_is_not_opened(engine, messenger):
    add_student(engine, "Ann", "Tempe", "Mon 9-10 AM", ("lamp", "good", 20), "book")
    add_student(engine, "Ben", "Tempe", "Tue 9-10 AM", ("book", "good", 20), "lamp")

    assert engine.db.list_loops() == []
    assert len(engine.db.list_haves(unreserved_only=True)) == 2
    assert messenger.of_kind(MessageKind.PROMPT) == []


def test_search_is_deferred_while_paused(engine):
    with engine.search_paused():
        add_student(engine, "Ann", "Tempe", "Thu 4-6 PM", ("lamp", "good", 20), "book")
        add_student(engine, "Ben", "Tempe", "Thu 4-6 PM", ("book", "good", 20), "lamp")
        assert engine.db.list_loops() == []
    assert len(engine.db.list_loops(LoopStatus.PENDING)) == 1

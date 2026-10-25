import logging

import pytest

from swaploop.config import Settings
from swaploop.demo import demo_key
from swaploop.discord_app.bot import RedactingFormatter, SwapLoopBot
from swaploop.discord_app.formatting import (
    MAX_MESSAGE_LENGTH,
    button_label,
    outcome_note,
    render_demo_console,
    render_swap_room,
    truncate,
)
from swaploop.discord_app.views import AnswerButton, can_answer_for
from swaploop.engine import AnswerOutcome
from swaploop.messaging import OutgoingMessage
from swaploop.models import Channel, MessageKind, Student


def message(channel, kind, body="line one\nline two", name=None, label=None, **extra):
    return OutgoingMessage(channel, kind, body, recipient_id=1 if name else None,
                           recipient_name=name, recipient_label=label, **extra)


def test_expected_commands_are_registered_on_the_tree():
    bot = SwapLoopBot(Settings("token-value", 1, ":memory:"))
    names = {command.name for command in bot.tree.get_commands()}
    assert names == {"have", "need", "free", "campus", "status", "demo"}
    demo = bot.tree.get_command("demo")
    assert {command.name for command in demo.commands} == {"seed", "reset"}


def test_demo_key_maps_labels_to_students_in_order():
    assert demo_key().splitlines() == [
        "Agent A = Shreyas", "Agent B = Rohan", "Agent C = Bhavisha", "Agent D = Shravani",
    ]


def test_swap_room_rendering_by_kind():
    assert render_swap_room(message(Channel.SWAP_ROOM, MessageKind.LISTING)).startswith("**New listing**")
    assert render_swap_room(message(Channel.SWAP_ROOM, MessageKind.FINAL_PLAN)).startswith("**Final plan**")
    audit = render_swap_room(message(Channel.SWAP_ROOM, MessageKind.AUDIT))
    assert audit == "-# line one\n-# line two"


def test_demo_console_prompt_names_the_student_and_final_plan_is_short():
    prompt = render_demo_console(message(Channel.DEMO_CONSOLE, MessageKind.PROMPT, name="Rohan", label="Agent B"))
    assert prompt.startswith("**Rohan** (Agent B) needs an answer:")
    plan = render_demo_console(
        message(Channel.DEMO_CONSOLE, MessageKind.FINAL_PLAN, "long plan text", "Rohan", "Agent B")
    )
    assert "long plan text" not in plan and "Rohan" in plan


def test_long_text_is_truncated_below_the_discord_limit():
    assert len(truncate("x" * 5000)) <= MAX_MESSAGE_LENGTH
    assert truncate("short") == "short"


def test_button_labels_name_the_student():
    assert button_label(True, "Rohan") == "Rohan: Accept"
    assert button_label(False, "Rohan") == "Rohan: Decline"
    assert button_label(True) == "Accept"


def test_every_outcome_has_a_note():
    assert all(outcome_note(outcome) for outcome in AnswerOutcome)


def test_button_custom_id_round_trips_through_the_template():
    button = AnswerButton(7, 3, accepted=False, student_name="Rohan")
    custom_id = button.item.custom_id
    assert custom_id == "swaploop:7:3:decline"
    match = AnswerButton.__discord_ui_compiled_template__.fullmatch(custom_id)
    assert (match["loop"], match["student"], match["answer"]) == ("7", "3", "decline")


def test_only_the_owner_answers_for_a_real_student_but_anyone_for_a_simulated_one():
    real = Student(1, "Ann", "555", False, None, "Agent A")
    simulated = Student(2, "Rohan", None, True, None, "Agent B")
    assert can_answer_for(real, 555) and not can_answer_for(real, 556)
    assert can_answer_for(simulated, 999)


def test_log_formatter_hides_the_token():
    formatter = RedactingFormatter("super-secret-token")
    record = logging.LogRecord("x", logging.ERROR, __file__, 1, "failed with super-secret-token", None, None)
    assert "super-secret-token" not in formatter.format(record)
    assert "[redacted]" in formatter.format(record)

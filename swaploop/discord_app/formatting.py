"""Turns engine messages into Discord text. Pure functions, no Discord imports."""

from swaploop.engine import AnswerOutcome
from swaploop.messaging import OutgoingMessage
from swaploop.models import MessageKind

MAX_MESSAGE_LENGTH = 1900  # Discord's hard limit is 2000


def truncate(text: str, limit: int = MAX_MESSAGE_LENGTH) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def render_swap_room(message: OutgoingMessage) -> str:
    if message.kind is MessageKind.AUDIT:
        text = "\n".join(f"-# {line}" for line in message.body.splitlines())
    elif message.kind is MessageKind.LISTING:
        text = f"**New listing**\n{message.body}"
    elif message.kind is MessageKind.AGENT_NOTE:
        text = f"**Agent note**\n{message.body}"
    elif message.kind is MessageKind.FINAL_PLAN:
        text = f"**Final plan**\n{message.body}"
    else:
        text = message.body
    return truncate(text)


def render_demo_console(message: OutgoingMessage) -> str:
    who = f"**{message.recipient_name}** ({message.recipient_label})"
    if message.kind is MessageKind.PROMPT:
        text = f"{who} needs an answer:\n{message.body}"
    elif message.kind is MessageKind.FINAL_PLAN:
        text = f"Final plan delivered to {who}. It is also posted in the swap room."
    elif message.recipient_name:
        text = f"To {who}:\n{message.body}"
    else:
        text = message.body
    return truncate(text)


def render_dm(message: OutgoingMessage) -> str:
    return truncate(message.body)


def button_label(accepted: bool, student_name: str | None = None) -> str:
    action = "Accept" if accepted else "Decline"
    return f"{student_name}: {action}" if student_name else action


_OUTCOME_NOTES = {
    AnswerOutcome.RECORDED: "Accepted. Waiting for the others.",
    AnswerOutcome.LOCKED: "Accepted. Everyone agreed, so the loop is locked.",
    AnswerOutcome.RELEASED: "Declined. The loop is cancelled and the items are free again.",
    AnswerOutcome.ALREADY_ANSWERED: "Already answered.",
    AnswerOutcome.LOOP_CLOSED: "This loop is no longer open.",
    AnswerOutcome.NOT_PARTICIPANT: "You are not part of this loop.",
}


def outcome_note(outcome: AnswerOutcome) -> str:
    return _OUTCOME_NOTES[outcome]

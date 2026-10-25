"""Plain data types shared across the core. No behavior beyond small helpers."""

from dataclasses import dataclass, field
from enum import Enum


class LoopStatus(str, Enum):
    PENDING = "PENDING"
    LOCKED = "LOCKED"
    RELEASED = "RELEASED"


class Answer(str, Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    DECLINED = "DECLINED"


class Channel(str, Enum):
    SWAP_ROOM = "SWAP_ROOM"
    DEMO_CONSOLE = "DEMO_CONSOLE"
    DM = "DM"


class MessageKind(str, Enum):
    LISTING = "LISTING"
    AGENT_NOTE = "AGENT_NOTE"
    PROMPT = "PROMPT"
    INFO = "INFO"
    FINAL_PLAN = "FINAL_PLAN"


@dataclass(frozen=True)
class Student:
    id: int
    name: str
    discord_id: str | None
    is_simulated: bool
    campus: str | None
    agent_label: str


@dataclass(frozen=True)
class HaveItem:
    id: int
    student_id: int
    name: str
    canonical: str
    condition: str
    value_usd: int
    loop_id: int | None = None


@dataclass(frozen=True)
class NeedItem:
    id: int
    student_id: int
    name: str
    canonical: str
    loop_id: int | None = None


@dataclass(frozen=True)
class FreeWindow:
    id: int
    student_id: int
    day: str
    start_min: int
    end_min: int


@dataclass(frozen=True)
class LoopLeg:
    """One edge of a loop: giver hands have_item to receiver, who needs it."""

    position: int
    giver_id: int
    receiver_id: int
    have_item_id: int
    need_item_id: int


@dataclass(frozen=True)
class Loop:
    id: int
    status: LoopStatus
    signature: str
    meeting_day: str | None
    meeting_min: int | None
    meeting_place: str | None
    conflicts: dict = field(default_factory=dict)
    released_by: int | None = None
    created_at: str = ""


@dataclass(frozen=True)
class LoggedMessage:
    id: int
    created_at: str
    channel: Channel
    recipient_id: int | None
    kind: MessageKind
    body: str

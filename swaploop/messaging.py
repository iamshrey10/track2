"""How the engine talks to the outside world. Discord and the console both plug in here."""

import sys
import textwrap
from dataclasses import dataclass
from typing import Protocol, TextIO

from swaploop.models import Channel, MessageKind


@dataclass(frozen=True)
class OutgoingMessage:
    channel: Channel
    kind: MessageKind
    body: str
    recipient_id: int | None = None
    recipient_name: str | None = None
    recipient_label: str | None = None
    loop_id: int | None = None  # set on prompts so the transport can attach Accept/Decline


class Messenger(Protocol):
    def send(self, message: OutgoingMessage) -> None: ...


class RecordingMessenger:
    """Keeps every message in memory, for tests."""

    def __init__(self) -> None:
        self.messages: list[OutgoingMessage] = []

    def send(self, message: OutgoingMessage) -> None:
        self.messages.append(message)

    def of_kind(self, kind: MessageKind) -> list[OutgoingMessage]:
        return [m for m in self.messages if m.kind is kind]

    def to_student(self, student_id: int) -> list[OutgoingMessage]:
        return [m for m in self.messages if m.recipient_id == student_id]


_CHANNEL_TITLES = {
    Channel.SWAP_ROOM: "Swap Room",
    Channel.DEMO_CONSOLE: "Demo Console",
    Channel.DM: "DM",
}


class ConsoleMessenger:
    """Prints messages the way the Discord channels would show them."""

    def __init__(self, stream: TextIO | None = None, show_audit: bool = False):
        self._stream = stream or sys.stdout
        # audit lines repeat what is already printed, so they stay in the database log only
        self._show_audit = show_audit

    def send(self, message: OutgoingMessage) -> None:
        if message.kind is MessageKind.AUDIT and not self._show_audit:
            return
        title = _CHANNEL_TITLES[message.channel]
        if message.recipient_name:
            title += f" -> {message.recipient_name} ({message.recipient_label})"
        header = f"[{title}] {message.kind.value.replace('_', ' ').title()}"
        self._write(header)
        for line in message.body.splitlines():
            self._write(textwrap.indent(line, "    "))
        if message.kind is MessageKind.PROMPT:
            self._write("    Buttons: [Accept] [Decline]")
        self._write("")

    def _write(self, line: str) -> None:
        print(line, file=self._stream)

"""Negotiation engine: registration, loop search, conflict handling and confirmation.

Everything an agent says goes through one Messenger. Until a loop locks, text
refers to other people by agent label only; names appear in the final plan.
"""

from contextlib import contextmanager
from dataclasses import asdict
from enum import Enum

from swaploop import matcher
from swaploop.conflicts import (
    VALUE_GAP_LIMIT_SHARE,
    VALUE_GAP_LIMIT_USD,
    CampusResolution,
    TimeResolution,
    TimeStatus,
    ValueCheck,
    check_values,
    choose_meeting_spot,
    resolve_time,
)
from swaploop.db import Database
from swaploop.loop_finder import Candidate, find_cycles, select_loops, value_exchanges
from swaploop.messaging import Messenger, OutgoingMessage
from swaploop.models import (
    Answer,
    Channel,
    FreeWindow,
    HaveItem,
    Loop,
    LoopLeg,
    LoopStatus,
    MessageKind,
    NeedItem,
    Student,
)
from swaploop.timeutil import format_slot


class AnswerOutcome(str, Enum):
    RECORDED = "RECORDED"
    LOCKED = "LOCKED"
    RELEASED = "RELEASED"
    ALREADY_ANSWERED = "ALREADY_ANSWERED"
    LOOP_CLOSED = "LOOP_CLOSED"
    NOT_PARTICIPANT = "NOT_PARTICIPANT"


class SwapEngine:
    def __init__(self, db: Database, messenger: Messenger):
        self.db = db
        self._messenger = messenger
        self._search_pauses = 0

    # registration

    def add_student(
        self, name: str, discord_id: str | None = None,
        is_simulated: bool = False, campus: str | None = None,
    ) -> Student:
        return self.db.add_student(name, discord_id, is_simulated, campus)

    def student_for_discord(self, discord_id: str, display_name: str) -> Student:
        return self.db.find_student_by_discord_id(discord_id) or self.add_student(
            display_name, discord_id=discord_id
        )

    def add_have(self, student_id: int, name: str, condition: str, value_usd: int) -> HaveItem:
        name, condition = name.strip(), condition.strip()
        if not matcher.canonicalize(name):
            raise ValueError("Give the item a name.")
        if not condition:
            raise ValueError("Give the item's condition, such as good or fair.")
        if value_usd < 0:
            raise ValueError("The approximate value cannot be negative.")
        item = self.db.add_have(student_id, name, matcher.canonicalize(name), condition, value_usd)
        self._post_listing(item)
        self.search()
        return item

    def add_need(self, student_id: int, name: str) -> NeedItem:
        name = name.strip()
        if not matcher.canonicalize(name):
            raise ValueError("Give the item a name.")
        item = self.db.add_need(student_id, name, matcher.canonicalize(name))
        self.search()
        return item

    def add_free_window(self, student_id: int, day: str, start_min: int, end_min: int) -> FreeWindow:
        if start_min >= end_min:
            raise ValueError("The start time must be earlier than the end time. Please enter the window again.")
        return self.db.add_free_window(student_id, day, start_min, end_min)

    def set_campus(self, student_id: int, campus: str) -> None:
        campus = campus.strip()
        if not campus:
            raise ValueError("Give a campus name.")
        self.db.set_campus(student_id, campus)

    def status_text(self, student_id: int) -> str:
        student = self.db.get_student(student_id)
        haves = self.db.list_haves(student_id)
        needs = self.db.list_needs(student_id)
        windows = self.db.list_free_windows(student_id)

        def in_loop(item) -> str:
            return f" (in loop #{item.loop_id})" if item.loop_id else ""

        lines = ["Items you have:"]
        lines += [f"  - {h.name} ({h.condition}, ${h.value_usd}){in_loop(h)}" for h in haves] or ["  none yet"]
        lines.append("Items you need:")
        lines += [f"  - {n.name}{in_loop(n)}" for n in needs] or ["  none yet"]
        lines.append("Free windows:")
        lines += [f"  - {format_slot(w.day, w.start_min, w.end_min)}" for w in windows] or ["  none yet"]
        lines.append(f"Campus: {student.campus or 'not set'}")
        return "\n".join(lines)

    # searching

    @contextmanager
    def search_paused(self):
        """Hold off loop searches while loading many records, then search once."""
        self._search_pauses += 1
        try:
            yield
        finally:
            self._search_pauses -= 1
        self.search()

    def search(self) -> list[Loop]:
        if self._search_pauses:
            return []
        ranked = find_cycles(self.db.list_haves(), self.db.list_needs())
        picks = select_loops(
            ranked, self.db.released_signatures(), is_feasible=self._has_workable_time
        )
        return [self._open_loop(pick) for pick in picks]

    def _windows_for(self, candidate: Candidate) -> dict[int, list[FreeWindow]]:
        return {sid: self.db.list_free_windows(sid) for sid in candidate.student_ids}

    def _has_workable_time(self, candidate: Candidate) -> bool:
        return resolve_time(self._windows_for(candidate)).status is not TimeStatus.INFEASIBLE

    def _open_loop(self, candidate: Candidate) -> Loop:
        haves_by_id = {h.id: h for h in self.db.list_haves()}
        time_result = resolve_time(self._windows_for(candidate))
        value_checks = check_values(value_exchanges(candidate.legs, haves_by_id))
        campus_result = choose_meeting_spot(
            {sid: self.db.get_student(sid).campus for sid in candidate.student_ids}
        )

        loop = self.db.create_loop(
            candidate.legs,
            time_result.day,
            time_result.meeting_min,
            campus_result.place,
            {
                "time": asdict(time_result),
                "values": [asdict(check) for check in value_checks],
                "campus": asdict(campus_result),
            },
        )

        self._announce_loop(loop, candidate.legs, haves_by_id)
        self._announce_conflicts(loop, time_result, value_checks, campus_result)
        for leg in candidate.legs:
            self._send_prompt(loop, leg.giver_id, candidate.legs, haves_by_id,
                              time_result, value_checks, campus_result)
        return loop

    # messages to the swap room

    def _label(self, student_id: int) -> str:
        return self.db.get_student(student_id).agent_label

    def _post_listing(self, item: HaveItem) -> None:
        student = self.db.get_student(item.student_id)
        windows = self.db.list_free_windows(student.id)
        free = "; ".join(format_slot(w.day, w.start_min, w.end_min) for w in windows) or "not set yet"
        self._send(
            Channel.SWAP_ROOM, MessageKind.LISTING,
            f"{student.agent_label} is offering {item.name} "
            f"({item.condition}, about ${item.value_usd}).\n"
            f"Campus: {student.campus or 'not set yet'}. Free: {free}.",
        )

    def _announce_loop(self, loop: Loop, legs: tuple[LoopLeg, ...], haves_by_id: dict[int, HaveItem]) -> None:
        ring = " -> ".join(self._label(leg.giver_id) for leg in legs) + f" -> {self._label(legs[0].giver_id)}"
        lines = [f"Loop #{loop.id} found, {len(legs)}-way: {ring}"]
        lines += [
            f"  {self._label(leg.giver_id)} gives {haves_by_id[leg.have_item_id].name} "
            f"to {self._label(leg.receiver_id)}"
            for leg in legs
        ]
        self._send(Channel.SWAP_ROOM, MessageKind.AGENT_NOTE, "\n".join(lines))

    def _announce_conflicts(
        self, loop: Loop, time_result: TimeResolution,
        value_checks: list[ValueCheck], campus_result: CampusResolution,
    ) -> None:
        slot = format_slot(time_result.day, time_result.window_start, time_result.window_end)
        meeting = format_slot(time_result.day, time_result.meeting_min)

        if time_result.status is TimeStatus.SHARED:
            self._note(f"All agents: everyone is free {slot}. Meeting set for {meeting}.")
        else:
            everyone = [leg.giver_id for leg in self.db.get_legs(loop.id)]
            sharing = [self._label(s) for s in everyone if s not in time_result.dissenter_ids]
            for student_id in time_result.dissenter_ids:
                self._note(
                    f"{self._label(student_id)}: my student is not free then. I propose {slot}, "
                    f"which {_join(sharing)} share (meeting {meeting}). Asking my student to accept."
                )

        for check in value_checks:
            if check.flagged:
                self._note(
                    f"{self._label(check.student_id)}: my student gives ${check.given} and gets "
                    f"${check.received} (${check.given - check.received} short). "
                    "Asking my student to accept the gap or add an item."
                )

        if campus_result.conflict:
            for student_id in campus_result.confirm_ids:
                self._note(
                    f"{self._label(student_id)}: meeting spot is {campus_result.place} "
                    f"on {campus_result.campus}. Asking my student to confirm."
                )
        else:
            self._note(f"All agents: meeting spot is {campus_result.place} ({campus_result.campus}).")

    def _note(self, text: str) -> None:
        self._send(Channel.SWAP_ROOM, MessageKind.AGENT_NOTE, text)

    # messages to students

    def _send_prompt(
        self, loop: Loop, student_id: int, legs: tuple[LoopLeg, ...],
        haves_by_id: dict[int, HaveItem], time_result: TimeResolution,
        value_checks: list[ValueCheck], campus_result: CampusResolution,
    ) -> None:
        gives = next(leg for leg in legs if leg.giver_id == student_id)
        gets = next(leg for leg in legs if leg.receiver_id == student_id)
        given, received = haves_by_id[gives.have_item_id], haves_by_id[gets.have_item_id]
        meeting = format_slot(time_result.day, time_result.meeting_min)

        lines = [
            f"Swap loop #{loop.id} needs your answer.",
            f"You give: {given.name} ({given.condition}, ${given.value_usd}) to {self._label(gives.receiver_id)}.",
            f"You get: {received.name} ({received.condition}, ${received.value_usd}) from {self._label(gets.giver_id)}.",
            f"Meet: {meeting} at {campus_result.place}.",
        ]

        asks = []
        if student_id in time_result.dissenter_ids:
            windows = self.db.list_free_windows(student_id)
            listed = ("you listed " + "; ".join(format_slot(w.day, w.start_min, w.end_min) for w in windows)
                      if windows else "you have not listed any free time")
            asks.append(
                f"TIME CHANGE: {listed}, but the rest of the loop is free "
                f"{format_slot(time_result.day, time_result.window_start, time_result.window_end)}. "
                f"The meeting is {meeting}."
            )
        check = next(c for c in value_checks if c.student_id == student_id)
        if check.flagged:
            asks.append(
                f"VALUE GAP: you give ${check.given} and get ${check.received}, so you are "
                f"${check.given - check.received} short (limit is ${VALUE_GAP_LIMIT_USD} or "
                f"{int(VALUE_GAP_LIMIT_SHARE * 100)}% of what you give). "
                "Accept the gap, or decline and add another item."
            )
        if student_id in campus_result.confirm_ids:
            student = self.db.get_student(student_id)
            asks.append(
                f"MEETING SPOT: your campus is {student.campus or 'not set'}, "
                f"the spot is {campus_result.place} on {campus_result.campus}."
            )

        if asks:
            lines.append("")
            lines.append("Accepting also means you agree to:" if len(asks) > 1 else "Accepting also means you agree to this:")
            lines += [f"{n}. {ask}" for n, ask in enumerate(asks, 1)]
        lines.append("")
        lines.append("Accept to confirm, or Decline to cancel the loop.")

        self._send_to_student(student_id, MessageKind.PROMPT, "\n".join(lines), loop.id)

    def _send_to_student(self, student_id: int, kind: MessageKind, body: str, loop_id: int | None = None) -> None:
        student = self.db.get_student(student_id)
        channel = Channel.DEMO_CONSOLE if student.is_simulated else Channel.DM
        self._send(channel, kind, body, student, loop_id)
        if kind is not MessageKind.FINAL_PLAN:
            # the plan is already in the room; every other student message is mirrored label-only
            self._send(Channel.SWAP_ROOM, MessageKind.AUDIT,
                       f"[audit] {kind.value.replace('_', ' ').lower()} to {student.agent_label}:\n{body}")

    def _send(
        self, channel: Channel, kind: MessageKind, body: str,
        student: Student | None = None, loop_id: int | None = None,
    ) -> None:
        self.db.log_message(channel, student.id if student else None, kind, body)
        self._messenger.send(OutgoingMessage(
            channel=channel, kind=kind, body=body,
            recipient_id=student.id if student else None,
            recipient_name=student.name if student else None,
            recipient_label=student.agent_label if student else None,
            loop_id=loop_id if kind is MessageKind.PROMPT else None,
        ))

    # confirmation

    def answer(self, loop_id: int, student_id: int, accepted: bool) -> AnswerOutcome:
        try:
            loop = self.db.get_loop(loop_id)
        except KeyError:
            return AnswerOutcome.LOOP_CLOSED
        if student_id not in self.db.get_confirmations(loop_id):
            return AnswerOutcome.NOT_PARTICIPANT
        if loop.status is not LoopStatus.PENDING:
            return AnswerOutcome.LOOP_CLOSED

        answer = Answer.ACCEPTED if accepted else Answer.DECLINED
        if not self.db.record_answer(loop_id, student_id, answer):
            return AnswerOutcome.ALREADY_ANSWERED

        if not accepted:
            self._release(loop, student_id)
            return AnswerOutcome.RELEASED
        if all(a is Answer.ACCEPTED for a in self.db.get_confirmations(loop_id).values()):
            self._lock(loop)
            return AnswerOutcome.LOCKED
        return AnswerOutcome.RECORDED

    def _lock(self, loop: Loop) -> None:
        self.db.lock_loop(loop.id)
        legs = self.db.get_legs(loop.id)
        haves_by_id = {h.id: h for h in self.db.list_haves()}

        lines = [f"Swap loop #{loop.id} is locked.", "Who gives what to whom:"]
        lines += [
            f"  - {self.db.get_student(leg.giver_id).name} gives {haves_by_id[leg.have_item_id].name} "
            f"to {self.db.get_student(leg.receiver_id).name}"
            for leg in legs
        ]
        lines.append(f"When and where: {format_slot(loop.meeting_day, loop.meeting_min)} at {loop.meeting_place}.")
        plan = "\n".join(lines)

        self._send(Channel.SWAP_ROOM, MessageKind.FINAL_PLAN, plan)
        for leg in legs:
            self._send_to_student(leg.giver_id, MessageKind.FINAL_PLAN, plan)

    def _release(self, loop: Loop, decliner_id: int) -> None:
        self.db.release_loop(loop.id, decliner_id)
        self._send_to_student(
            decliner_id, MessageKind.INFO,
            f"You declined swap loop #{loop.id}. Your items are free again.",
        )
        for leg in self.db.get_legs(loop.id):
            if leg.giver_id != decliner_id:
                self._send_to_student(
                    leg.giver_id, MessageKind.INFO,
                    f"Swap loop #{loop.id} was cancelled because a participant declined. "
                    "Your items are free again and I am searching for another loop.",
                )
        self._note(f"Loop #{loop.id} released: a participant declined. Searching again.")
        self.search()


def _join(labels: list[str]) -> str:
    if len(labels) <= 1:
        return "".join(labels)
    return ", ".join(labels[:-1]) + f" and {labels[-1]}"

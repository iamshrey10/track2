"""Run the demo scenario end to end without Discord: python -m swaploop.simulate"""

import sys
from dataclasses import dataclass
from typing import TextIO

from swaploop.db import Database
from swaploop.demo import ANSWER_ORDER, seed_demo
from swaploop.engine import AnswerOutcome, SwapEngine
from swaploop.messaging import ConsoleMessenger
from swaploop.models import Loop, LoopStatus


@dataclass(frozen=True)
class SimulationResult:
    db: Database
    loop: Loop | None


def run_simulation(out: TextIO | None = None) -> SimulationResult:
    out = out or sys.stdout

    def say(text: str = "") -> None:
        print(text, file=out)

    db = Database()
    engine = SwapEngine(db, ConsoleMessenger(out))

    say("=== SwapLoop demo simulation ===")
    say()
    say("--- Seeding four students; agents post listings and look for loops ---")
    say()
    seed_demo(engine)

    pending = db.list_loops(LoopStatus.PENDING)
    if len(pending) != 1:
        say(f"Expected one pending loop, found {len(pending)}.")
        return SimulationResult(db, None)
    loop = pending[0]
    _describe_loop(db, loop, say)

    say("--- Operator answers each prompt ---")
    say()
    students = {s.name: s for s in db.list_students()}
    outcome = None
    for name in ANSWER_ORDER:
        say(f">>> {name} taps Accept")
        say()
        outcome = engine.answer(loop.id, students[name].id, accepted=True)

    loop = db.get_loop(loop.id)
    say(f"=== Result: loop #{loop.id} {loop.status.value} ===")
    if outcome is not AnswerOutcome.LOCKED:
        say("The loop did not lock.")
    return SimulationResult(db, loop)


def _describe_loop(db: Database, loop: Loop, say) -> None:
    """Operator view: real names behind the anonymous labels."""
    legs = db.get_legs(loop.id)
    students = {s.id: s for s in db.list_students()}
    say("--- Operator view (names behind the agent labels) ---")
    say("Agents: " + ", ".join(f"{s.agent_label} = {s.name}" for s in students.values()))
    chain = " -> ".join(students[leg.giver_id].name for leg in legs) + f" -> {students[legs[0].giver_id].name}"
    say(f"Loop #{loop.id}: {chain}")
    say()


def main() -> None:
    result = run_simulation()
    sys.exit(0 if result.loop and result.loop.status is LoopStatus.LOCKED else 1)


if __name__ == "__main__":
    main()

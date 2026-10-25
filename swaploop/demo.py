"""The demo scenario: four simulated students whose items form one 4-way loop."""

from dataclasses import dataclass

from swaploop.engine import SwapEngine
from swaploop.timeutil import parse_window


@dataclass(frozen=True)
class SeedStudent:
    name: str
    campus: str
    free: str
    have: tuple[str, str, int]  # name, condition, value in USD
    need: str


SEED_STUDENTS = (
    SeedStudent("Shreyas", "Tempe", "Thu 4-6 PM", ("calculus textbook", "good", 40), "mini-fridge"),
    SeedStudent("Rohan", "Tempe", "Tue 2-5 PM", ("mini-fridge", "good", 60), "bike lock"),
    SeedStudent("Bhavisha", "Tempe", "Thu 3-5 PM", ("bike lock", "good", 15), "desk lamp"),
    SeedStudent("Shravani", "Tempe", "Thu 4-7 PM", ("desk lamp", "good", 20), "calculus textbook"),
)

# Shreyas -> Shravani -> Bhavisha -> Rohan, with Rohan last because his prompt carries the conflicts
ANSWER_ORDER = ("Shreyas", "Shravani", "Bhavisha", "Rohan")


def seed_demo(engine: SwapEngine) -> None:
    """Load the four simulated students, replacing any earlier simulated ones."""
    engine.db.delete_simulated_students()
    with engine.search_paused():
        students = [
            engine.add_student(seed.name, is_simulated=True, campus=seed.campus)
            for seed in SEED_STUDENTS
        ]
        # windows and needs first so each listing already shows campus and free time
        for student, seed in zip(students, SEED_STUDENTS):
            engine.add_free_window(student.id, *parse_window(seed.free))
            engine.add_need(student.id, seed.need)
        for student, seed in zip(students, SEED_STUDENTS):
            engine.add_have(student.id, *seed.have)


def reset_demo(engine: SwapEngine) -> None:
    engine.db.reset_all()

import io

from swaploop.demo import reset_demo, seed_demo
from swaploop.db import Database
from swaploop.engine import SwapEngine
from swaploop.messaging import RecordingMessenger
from swaploop.models import LoopStatus
from swaploop.simulate import run_simulation


def simulate():
    out = io.StringIO()
    result = run_simulation(out)
    return result, out.getvalue()


def test_acceptance_seed_ends_in_the_expected_locked_loop():
    result, output = simulate()

    assert result.loop.status is LoopStatus.LOCKED
    assert (result.loop.meeting_day, result.loop.meeting_min) == ("Thu", 990)
    assert result.loop.meeting_place == "Memorial Union"

    assert "Loop #1: Shreyas -> Shravani -> Bhavisha -> Rohan -> Shreyas" in output
    assert "TIME CHANGE" in output and "VALUE GAP" in output
    assert "Thu 4:30 PM at Memorial Union" in output
    assert "Result: loop #1 LOCKED" in output


def test_only_one_loop_exists_after_the_seed():
    result, _ = simulate()
    assert len(result.db.list_loops()) == 1


def test_two_runs_print_identical_output():
    assert simulate()[1] == simulate()[1]


def test_reseeding_replaces_simulated_students_and_reset_clears_all():
    engine = SwapEngine(Database(), RecordingMessenger())
    seed_demo(engine)
    reset_demo(engine)
    assert engine.db.list_students() == [] and engine.db.list_loops() == []

    seed_demo(engine)
    seed_demo(engine)
    assert len(engine.db.list_students()) == 4
    assert len(engine.db.list_loops(LoopStatus.PENDING)) == 1

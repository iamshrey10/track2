import pytest

from swaploop.db import Database, agent_label_for
from swaploop.models import Answer, Channel, LoopLeg, LoopStatus, MessageKind


@pytest.fixture
def db():
    return Database()


def make_pair(db):
    """Two students who can swap one item each."""
    ann = db.add_student("Ann", campus="Tempe")
    ben = db.add_student("Ben", campus="Tempe")
    ann_have = db.add_have(ann.id, "lamp", "desk lamp", "good", 20)
    ben_have = db.add_have(ben.id, "book", "calculus textbook", "good", 40)
    ann_need = db.add_need(ann.id, "book", "calculus textbook")
    ben_need = db.add_need(ben.id, "lamp", "desk lamp")
    legs = [
        LoopLeg(0, ann.id, ben.id, ann_have.id, ben_need.id),
        LoopLeg(1, ben.id, ann.id, ben_have.id, ann_need.id),
    ]
    return ann, ben, legs


def test_agent_labels_follow_id_order():
    assert [agent_label_for(i) for i in (1, 2, 26, 27, 28)] == [
        "Agent A", "Agent B", "Agent Z", "Agent AA", "Agent AB",
    ]


def test_students_get_sequential_labels(db):
    first = db.add_student("Ann")
    second = db.add_student("Ben", discord_id="123", is_simulated=False)
    assert (first.agent_label, second.agent_label) == ("Agent A", "Agent B")
    assert db.find_student_by_discord_id("123").name == "Ben"
    assert db.find_student_by_discord_id("nope") is None


def test_campus_and_windows(db):
    student = db.add_student("Ann")
    db.set_campus(student.id, "Tempe")
    db.add_free_window(student.id, "Thu", 960, 1080)
    assert db.get_student(student.id).campus == "Tempe"
    assert [w.day for w in db.list_free_windows(student.id)] == ["Thu"]


def test_invalid_window_is_rejected(db):
    student = db.add_student("Ann")
    with pytest.raises(ValueError):
        db.add_free_window(student.id, "Thu", 1080, 960)


def test_create_loop_reserves_items_and_confirmations(db):
    ann, ben, legs = make_pair(db)
    loop = db.create_loop(legs, "Thu", 990, "Memorial Union", {"time": "ok"})

    assert loop.status is LoopStatus.PENDING
    assert loop.conflicts == {"time": "ok"}
    assert db.list_haves(unreserved_only=True) == []
    assert db.list_needs(unreserved_only=True) == []
    assert db.get_confirmations(loop.id) == {ann.id: Answer.PENDING, ben.id: Answer.PENDING}
    assert db.get_legs(loop.id) == legs


def test_item_cannot_join_two_loops(db):
    _, _, legs = make_pair(db)
    db.create_loop(legs, "Thu", 990, "Memorial Union", {})
    with pytest.raises(ValueError):
        db.create_loop(legs, "Thu", 990, "Memorial Union", {})
    assert len(db.list_loops()) == 1


def test_release_frees_items_and_remembers_signature(db):
    ann, _, legs = make_pair(db)
    loop = db.create_loop(legs, "Thu", 990, "Memorial Union", {})
    db.release_loop(loop.id, released_by=ann.id)

    released = db.get_loop(loop.id)
    assert released.status is LoopStatus.RELEASED
    assert released.released_by == ann.id
    assert len(db.list_haves(unreserved_only=True)) == 2
    assert db.released_signatures() == {loop.signature}


def test_lock_keeps_items_reserved(db):
    _, _, legs = make_pair(db)
    loop = db.create_loop(legs, "Thu", 990, "Memorial Union", {})
    db.lock_loop(loop.id)
    assert db.get_loop(loop.id).status is LoopStatus.LOCKED
    assert db.list_haves(unreserved_only=True) == []


def test_first_answer_wins(db):
    ann, _, legs = make_pair(db)
    loop = db.create_loop(legs, "Thu", 990, "Memorial Union", {})
    assert db.record_answer(loop.id, ann.id, Answer.ACCEPTED) is True
    assert db.record_answer(loop.id, ann.id, Answer.DECLINED) is False
    assert db.get_confirmations(loop.id)[ann.id] is Answer.ACCEPTED


def test_message_log_round_trip(db):
    student = db.add_student("Ann")
    db.log_message(Channel.DM, student.id, MessageKind.PROMPT, "Accept?")
    db.log_message(Channel.SWAP_ROOM, None, MessageKind.LISTING, "Agent A has a lamp")
    messages = db.list_messages()
    assert [m.kind for m in messages] == [MessageKind.PROMPT, MessageKind.LISTING]
    assert messages[0].recipient_id == student.id


def test_delete_simulated_students_keeps_real_ones_and_frees_their_loops(db):
    real = db.add_student("Real", discord_id="9")
    sim = db.add_student("Sim", is_simulated=True)
    real_have = db.add_have(real.id, "lamp", "desk lamp", "good", 20)
    real_need = db.add_need(real.id, "book", "calculus textbook")
    sim_have = db.add_have(sim.id, "book", "calculus textbook", "good", 40)
    sim_need = db.add_need(sim.id, "lamp", "desk lamp")
    db.create_loop(
        [LoopLeg(0, real.id, sim.id, real_have.id, sim_need.id),
         LoopLeg(1, sim.id, real.id, sim_have.id, real_need.id)],
        "Thu", 990, "Memorial Union", {},
    )

    db.delete_simulated_students()

    assert [s.name for s in db.list_students()] == ["Real"]
    assert db.list_loops() == []
    assert len(db.list_haves(unreserved_only=True)) == 1


def test_reset_all_clears_everything_and_restarts_labels(db):
    _, _, legs = make_pair(db)
    db.create_loop(legs, "Thu", 990, "Memorial Union", {})
    db.log_message(Channel.SWAP_ROOM, None, MessageKind.INFO, "hello")

    db.reset_all()

    assert db.list_students() == []
    assert db.list_haves() == [] and db.list_needs() == []
    assert db.list_free_windows() == [] and db.list_loops() == []
    assert db.list_messages() == []
    assert db.add_student("New").agent_label == "Agent A"

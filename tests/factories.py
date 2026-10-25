"""Small builders so pure-logic tests do not need a database."""

from itertools import count

from swaploop.matcher import canonicalize
from swaploop.models import FreeWindow, HaveItem, NeedItem
from swaploop.timeutil import parse_window

_ids = count(1)


def have(student_id, name, value=10, item_id=None, loop_id=None):
    return HaveItem(
        id=item_id or next(_ids), student_id=student_id, name=name,
        canonical=canonicalize(name), condition="good", value_usd=value, loop_id=loop_id,
    )


def need(student_id, name, item_id=None, loop_id=None):
    return NeedItem(
        id=item_id or next(_ids), student_id=student_id, name=name,
        canonical=canonicalize(name), loop_id=loop_id,
    )


def window(student_id, text):
    day, start, end = parse_window(text)
    return FreeWindow(next(_ids), student_id, day, start, end)


def seed_items():
    """The demo scenario: Shreyas=1, Rohan=2, Bhavisha=3, Shravani=4."""
    haves = [
        have(1, "calculus textbook", 40),
        have(2, "mini-fridge", 60),
        have(3, "bike lock", 15),
        have(4, "desk lamp", 20),
    ]
    needs = [
        need(1, "mini-fridge"),
        need(2, "bike lock"),
        need(3, "desk lamp"),
        need(4, "calculus textbook"),
    ]
    return haves, needs

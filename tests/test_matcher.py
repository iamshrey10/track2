import pytest

from swaploop.matcher import canonicalize, is_match, normalize


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("  Calculus   Textbook ", "calculus textbook"),
        ("Desk Lamps", "desk lamp"),
        ("Bike Locks", "bike lock"),
        ("batteries", "battery"),
        ("boxes", "box"),
        ("glasses", "glass"),
        ("watches", "watch"),
        ("bus", "bus"),
        ("calculus", "calculus"),
        ("mini-fridge", "mini-fridge"),
    ],
)
def test_normalize(raw, expected):
    assert normalize(raw) == expected


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("calc textbook", "calculus textbook"),
        ("Calc Textbooks", "calculus textbook"),
        ("fridge", "mini-fridge"),
        ("Fridges", "mini-fridge"),
        ("mini fridge", "mini-fridge"),
        ("lamp", "lamp"),
    ],
)
def test_canonicalize_applies_aliases(raw, expected):
    assert canonicalize(raw) == expected


def test_alias_and_canonical_name_match():
    assert is_match("fridge", "Mini-Fridge")
    assert is_match("calc textbook", "calculus textbooks")


def test_different_items_do_not_match():
    assert not is_match("desk lamp", "bike lock")


def test_empty_names_never_match():
    assert not is_match("", "  ")

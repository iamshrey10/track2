"""Swap graph construction, cycle enumeration and loop ranking.

Graph rule: an edge X -> Y means X has an item Y needs, so X gives it to Y.
"""

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

from swaploop.models import HaveItem, LoopLeg, NeedItem

MIN_LOOP_SIZE = 2
MAX_LOOP_SIZE = 4


@dataclass(frozen=True)
class Candidate:
    """A cycle that could become a Pending_Loop, listed from its lowest student id."""

    legs: tuple[LoopLeg, ...]
    total_gap: int

    @property
    def size(self) -> int:
        return len(self.legs)

    @property
    def student_ids(self) -> tuple[int, ...]:
        return tuple(leg.giver_id for leg in self.legs)

    @property
    def signature(self) -> str:
        return ",".join(str(i) for i in sorted(leg.have_item_id for leg in self.legs))

    @property
    def sort_key(self) -> tuple:
        return (self.size, self.total_gap, tuple(leg.have_item_id for leg in self.legs))


@dataclass(frozen=True)
class ValueExchange:
    student_id: int
    given: int
    received: int

    @property
    def gap(self) -> int:
        return abs(self.given - self.received)


def build_edges(
    haves: Iterable[HaveItem], needs: Iterable[NeedItem]
) -> dict[int, dict[int, tuple[int, int]]]:
    """Map giver -> receiver -> (have_item_id, need_item_id) over unreserved items.

    When several items match, the lowest id wins so results are repeatable.
    """
    free_needs = sorted((n for n in needs if n.loop_id is None), key=lambda n: n.id)
    free_haves = sorted((h for h in haves if h.loop_id is None), key=lambda h: h.id)

    edges: dict[int, dict[int, tuple[int, int]]] = {}
    for have in free_haves:
        for need in free_needs:
            if need.student_id == have.student_id or need.canonical != have.canonical:
                continue
            receivers = edges.setdefault(have.student_id, {})
            if need.student_id not in receivers:
                receivers[need.student_id] = (have.id, need.id)
    return edges


def value_exchanges(legs: Sequence[LoopLeg], haves_by_id: dict[int, HaveItem]) -> list[ValueExchange]:
    """What each participant gives and receives, in loop order."""
    received_by = {leg.receiver_id: haves_by_id[leg.have_item_id].value_usd for leg in legs}
    return [
        ValueExchange(leg.giver_id, haves_by_id[leg.have_item_id].value_usd, received_by[leg.giver_id])
        for leg in legs
    ]


def find_cycles(haves: Sequence[HaveItem], needs: Sequence[NeedItem]) -> list[Candidate]:
    """All 2-, 3- and 4-way cycles, each once, best first."""
    edges = build_edges(haves, needs)
    haves_by_id = {h.id: h for h in haves}
    found: list[Candidate] = []

    def walk(start: int, path: list[int]) -> None:
        current = path[-1]
        for receiver in sorted(edges.get(current, {})):
            if receiver == start and len(path) >= MIN_LOOP_SIZE:
                found.append(_candidate(path, edges, haves_by_id))
            elif receiver > start and receiver not in path and len(path) < MAX_LOOP_SIZE:
                walk(start, path + [receiver])

    for start in sorted(edges):
        walk(start, [start])

    return sorted(found, key=lambda candidate: candidate.sort_key)


def _candidate(
    path: list[int], edges: dict[int, dict[int, tuple[int, int]]], haves_by_id: dict[int, HaveItem]
) -> Candidate:
    legs = []
    for position, giver in enumerate(path):
        receiver = path[(position + 1) % len(path)]
        have_id, need_id = edges[giver][receiver]
        legs.append(LoopLeg(position, giver, receiver, have_id, need_id))
    total_gap = sum(x.gap for x in value_exchanges(legs, haves_by_id))
    return Candidate(tuple(legs), total_gap)


def select_loops(
    ranked: Iterable[Candidate],
    released_signatures: set[str] = frozenset(),
    is_feasible: Callable[[Candidate], bool] | None = None,
) -> list[Candidate]:
    """Pick non-overlapping loops from a ranked list, skipping released or infeasible ones."""
    chosen: list[Candidate] = []
    claimed_haves: set[int] = set()
    claimed_needs: set[int] = set()

    for candidate in ranked:
        if candidate.signature in released_signatures:
            continue
        have_ids = {leg.have_item_id for leg in candidate.legs}
        need_ids = {leg.need_item_id for leg in candidate.legs}
        if have_ids & claimed_haves or need_ids & claimed_needs:
            continue
        if is_feasible is not None and not is_feasible(candidate):
            continue
        chosen.append(candidate)
        claimed_haves |= have_ids
        claimed_needs |= need_ids
    return chosen

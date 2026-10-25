from swaploop.loop_finder import (
    build_edges,
    find_cycles,
    select_loops,
    value_exchanges,
)
from tests.factories import have, need, seed_items


def ring(size, values=None):
    """Student i has item i and needs item i+1's, forming one cycle."""
    values = values or [10] * size
    haves = [have(i + 1, f"item {i}", values[i]) for i in range(size)]
    needs = [need(i + 1, f"item {(i - 1) % size}") for i in range(size)]
    return haves, needs


def test_edge_means_giver_has_what_receiver_needs():
    haves, needs = seed_items()
    edges = build_edges(haves, needs)
    assert {giver: sorted(receivers) for giver, receivers in edges.items()} == {
        1: [4], 4: [3], 3: [2], 2: [1],
    }


def test_student_never_matches_themselves():
    haves = [have(1, "desk lamp")]
    needs = [need(1, "desk lamp")]
    assert build_edges(haves, needs) == {}


def test_alias_names_still_match():
    edges = build_edges([have(1, "fridge")], [need(2, "Mini-Fridges")])
    assert list(edges[1]) == [2]


def test_lowest_item_id_wins_among_matches():
    first = have(1, "desk lamp", item_id=500)
    second = have(1, "desk lamp", item_id=501)
    wanted = need(2, "desk lamp", item_id=600)
    assert build_edges([second, first], [wanted])[1][2] == (500, 600)


def test_reserved_items_are_ignored():
    reserved = have(1, "desk lamp", loop_id=7)
    assert build_edges([reserved], [need(2, "desk lamp")]) == {}
    assert build_edges([have(1, "desk lamp")], [need(2, "desk lamp", loop_id=7)]) == {}


def test_finds_two_three_and_four_way_cycles():
    for size in (2, 3, 4):
        haves, needs = ring(size)
        cycles = find_cycles(haves, needs)
        assert [c.size for c in cycles] == [size]


def test_five_way_cycle_is_out_of_scope():
    haves, needs = ring(5)
    assert find_cycles(haves, needs) == []


def test_broken_link_means_no_cycle():
    haves, needs = ring(3)
    assert find_cycles(haves, needs[:-1]) == []


def test_cycle_found_once_and_rooted_at_lowest_student():
    haves, needs = ring(4)
    (cycle,) = find_cycles(haves, needs)
    assert cycle.student_ids[0] == 1
    assert [leg.position for leg in cycle.legs] == [0, 1, 2, 3]
    assert all(
        cycle.legs[i].receiver_id == cycle.legs[(i + 1) % 4].giver_id for i in range(4)
    )


def test_seed_has_exactly_one_four_way_loop_in_the_expected_order():
    haves, needs = seed_items()
    cycles = find_cycles(haves, needs)
    assert len(cycles) == 1
    # Shreyas=1, Rohan=2, Bhavisha=3, Shravani=4
    assert cycles[0].student_ids == (1, 4, 3, 2)
    assert [leg.receiver_id for leg in cycles[0].legs] == [4, 3, 2, 1]


def test_value_exchanges_for_seed():
    haves, needs = seed_items()
    (cycle,) = find_cycles(haves, needs)
    exchanges = {x.student_id: (x.given, x.received) for x in value_exchanges(cycle.legs, {h.id: h for h in haves})}
    assert exchanges == {1: (40, 60), 4: (20, 40), 3: (15, 20), 2: (60, 15)}
    assert cycle.total_gap == 20 + 20 + 5 + 45


def test_shorter_loop_beats_a_cheaper_longer_one():
    # 1<->2 is a lopsided 2-way; 1->2->3->1 is an even 3-way
    haves = [have(1, "a", 10), have(2, "b", 100), have(2, "c", 10), have(3, "b", 10)]
    needs = [need(1, "b"), need(2, "a"), need(3, "c")]
    cycles = find_cycles(haves, needs)
    assert [c.size for c in cycles] == [2, 3]
    assert cycles[0].total_gap > cycles[1].total_gap


def test_same_size_loops_rank_by_smallest_total_gap():
    haves = [have(1, "a", 50), have(2, "x", 10), have(3, "x", 50)]
    needs = [need(1, "x"), need(2, "a"), need(3, "a")]
    cycles = find_cycles(haves, needs)
    assert [c.student_ids for c in cycles] == [(1, 3), (1, 2)]


def test_select_loops_skips_overlaps_released_and_infeasible():
    haves = [have(1, "a", 10), have(2, "x", 10), have(3, "x", 10)]
    needs = [need(1, "x"), need(2, "a"), need(3, "a")]
    ranked = find_cycles(haves, needs)
    assert len(ranked) == 2

    assert [c.student_ids for c in select_loops(ranked)] == [(1, 2)]
    assert [c.student_ids for c in select_loops(ranked, {ranked[0].signature})] == [(1, 3)]
    assert select_loops(ranked, is_feasible=lambda c: False) == []
    assert [c.student_ids for c in select_loops(ranked, is_feasible=lambda c: 3 in c.student_ids)] == [(1, 3)]


def test_select_loops_returns_disjoint_loops():
    pair_one = ring(2)
    pair_two = (
        [have(3, "p"), have(4, "q")],
        [need(3, "q"), need(4, "p")],
    )
    haves = pair_one[0] + pair_two[0]
    needs = pair_one[1] + pair_two[1]
    assert [c.student_ids for c in select_loops(find_cycles(haves, needs))] == [(1, 2), (3, 4)]

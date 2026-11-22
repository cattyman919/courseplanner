"""Tests for the pruned DFS combo generator."""

from itertools import combinations

from domain.catalog import CATALOG
from domain.models import Course
from reasoning.combos import MAX_COMBOS, valid_combos
from reasoning.rules import check_schedule

CAT = {c.code: c for c in CATALOG}
# Courses a student with the On-track completed set could see in some term.
POOL = [CAT[c] for c in ("CS301", "CS310", "MATH301", "CS350", "CS360", "CS370",
                         "CS390", "AI320", "GE102", "SYS330")]


def credits(combo: tuple[Course, ...]) -> int:
    return sum(c.credits for c in combo)


def test_no_combo_exceeds_cap():
    for cap in (12, 15, 18):
        combos, _ = valid_combos(POOL, cap)
        assert combos and all(credits(c) <= cap for c in combos)


def test_no_internal_slot_conflict():
    combos, _ = valid_combos(POOL, 21)
    assert all(not check_schedule(c, 21) for c in combos)
    assert all(not set(a.slots) & set(b.slots) for c in combos for a, b in combinations(c, 2))


def test_combos_are_maximal():
    combos, _ = valid_combos(POOL, 15)
    for combo in combos:
        for extra in POOL:
            if extra not in combo:
                assert check_schedule(combo + (extra,), 15), f"{extra.code} fits into {combo}"


def test_deterministic_across_calls():
    first, _ = valid_combos(POOL, 18)
    second, _ = valid_combos(list(reversed(POOL)), 18)
    assert [[c.code for c in x] for x in first] == [[c.code for c in x] for x in second]


def test_below_min_only_when_nothing_reaches_min():
    combos, _ = valid_combos([CAT["AI401"]], 18)
    assert combos == [(CAT["AI401"],)]
    combos, _ = valid_combos(POOL, 18)
    assert all(credits(c) >= 9 for c in combos)


def test_elective_need_limits_electives():
    combos, _ = valid_combos(POOL, 21, elective_credits_needed=3)
    for combo in combos:
        assert sum(1 for c in combo if c.category == "elective") <= 1


def test_empty_input():
    assert valid_combos([], 18) == ([], False)


def test_truncation_flag_flips_on_large_input():
    big = [Course(f"X{i:02d}", f"Filler {i}", 3, slots=(f"S{i}",)) for i in range(20)]
    combos, truncated = valid_combos(big, 18)
    assert truncated and len(combos) == MAX_COMBOS
    _, small_truncated = valid_combos(big[:7], 18)
    assert not small_truncated

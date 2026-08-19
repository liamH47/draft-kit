from draftkit.engine.tiers import gap_tiers


def test_empty():
    assert gap_tiers([]) == []


def test_single_tier_when_no_gaps():
    assert gap_tiers([100, 99, 98, 97]) == [1, 1, 1, 1]


def test_tier_break_at_gap():
    assert gap_tiers([100, 99, 90, 89], min_gap=6) == [1, 1, 2, 2]


def test_multiple_breaks():
    assert gap_tiers([100, 90, 80], min_gap=6) == [1, 2, 3]


def test_gap_exactly_at_threshold_breaks():
    assert gap_tiers([100, 94], min_gap=6) == [1, 2]

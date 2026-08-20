from draftkit.engine.adp import blend_adp


def test_empty_sources():
    assert blend_adp({}, {"sleeper": 0.5}) is None


def test_single_source():
    assert blend_adp({"sleeper": 10.0}, {"sleeper": 0.5, "ffcalc": 0.5}) == 10.0


def test_weighted_mean():
    assert blend_adp({"sleeper": 10.0, "ffcalc": 20.0}, {"sleeper": 0.75, "ffcalc": 0.25}) == 12.5


def test_unknown_source_defaults_to_weight_one():
    assert blend_adp({"mystery": 8.0}, {}) == 8.0


# --- list vs market ---------------------------------------------------------


def test_list_vs_market_needs_both_sides():
    from draftkit.engine.adp import list_vs_market

    assert list_vs_market({}, 20.0) is None
    assert list_vs_market({"espn": 10.0}, None) is None


def test_list_higher_than_the_market_reads_positive():
    """The lists like him more than the room does, so he tends to last."""
    from draftkit.engine.adp import list_vs_market

    assert list_vs_market({"espn": 10.0}, 25.0) == 15.0


def test_market_higher_than_the_list_reads_negative():
    from draftkit.engine.adp import list_vs_market

    assert list_vs_market({"espn": 40.0}, 22.0) == -18.0


def test_multiple_lists_are_averaged():
    from draftkit.engine.adp import list_vs_market

    assert list_vs_market({"espn": 10.0, "expert": 20.0}, 30.0) == 15.0

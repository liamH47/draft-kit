from draftkit.engine.adp import blend_adp, consensus_rank, sentinel_cutoff


def test_empty_sources():
    assert blend_adp({}, {"sleeper": 0.5}) is None


def test_single_source():
    assert blend_adp({"sleeper": 10.0}, {"sleeper": 0.5, "ffcalc": 0.5}) == 10.0


def test_weighted_mean():
    assert blend_adp({"sleeper": 10.0, "ffcalc": 20.0}, {"sleeper": 0.75, "ffcalc": 0.25}) == 12.5


def test_unknown_source_defaults_to_weight_one():
    assert blend_adp({"mystery": 8.0}, {}) == 8.0


# --- consensus rank ---------------------------------------------------------


def test_consensus_rank_weights_espn_over_expert():
    # Default weights: espn 1.0, expert 0.5 -> (10*1 + 40*0.5) / 1.5 = 20
    assert consensus_rank({"espn": 10.0, "expert": 40.0}) == 20.0
    assert consensus_rank({"expert": 40.0}) == 40.0


def test_consensus_rank_is_none_without_lists_or_weights():
    assert consensus_rank({}) is None
    assert consensus_rank({"espn": 10.0}, weights={"espn": 0.0}) is None


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


# --- sentinel detection: a bucket is not a price ----------------------------


def test_a_market_that_prices_everyone_has_no_sentinel():
    """Real prices spread out. FantasyFootballCalculator stops publishing when
    drafting stops, so its tail is genuine."""
    real = [float(i) for i in range(1, 200)]
    assert sentinel_cutoff(real) is None


def test_a_bucket_of_the_undrafted_is_found_and_cut_below():
    """ESPN gives every player it does not really price a number just past the
    end of its draft — a jittered band, not one repeated value."""
    prices = [float(i) for i in range(1, 170)]
    bucket = [169.0 + (i % 5) * 0.01 for i in range(300)]
    cutoff = sentinel_cutoff(prices + bucket)
    assert cutoff is not None and cutoff <= 169.0
    assert max(v for v in prices + bucket if v < cutoff) < 169.0


def test_a_short_list_is_never_called_a_bucket():
    assert sentinel_cutoff([1.0, 2.0, 3.0]) is None
    assert sentinel_cutoff([]) is None


def test_a_crowd_in_the_middle_of_the_board_is_not_a_bucket():
    """Twelve players go every round, so mid-draft ADPs are dense by nature —
    only a crowd at the very tail is a bucket."""
    normal = [round(i * 0.5, 2) for i in range(2, 400)]
    assert sentinel_cutoff(normal) is None


def test_a_source_that_is_all_bucket_is_cut_entirely():
    """Degenerate but possible: a feed that returns the same placeholder for
    everyone has no prices in it at all."""
    assert sentinel_cutoff([170.0] * 30) == 169.0


def test_a_feed_dense_all_the_way_down_leaves_nothing():
    """If the crowd never thins, the walk reaches the start of the draft —
    the honest answer being that none of it is a price."""
    cutoff = sentinel_cutoff([i * 0.02 for i in range(1500)])
    assert cutoff is not None and cutoff <= 0.0

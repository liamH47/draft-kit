from draftkit.engine.scoring import score
from draftkit.models.league import ScoringSettings

WR_LINE = {"rec": 100.0, "rec_yd": 1200.0, "rec_td": 8.0, "fum_lost": 1.0}


def test_standard():
    assert score(WR_LINE, ScoringSettings.preset("standard")) == 1200 * 0.1 + 8 * 6 - 2


def test_half_ppr_adds_half_per_reception():
    std = score(WR_LINE, ScoringSettings.preset("standard"))
    half = score(WR_LINE, ScoringSettings.preset("half_ppr"))
    assert half == std + 50


def test_ppr_adds_one_per_reception():
    std = score(WR_LINE, ScoringSettings.preset("standard"))
    ppr = score(WR_LINE, ScoringSettings.preset("ppr"))
    assert ppr == std + 100


def test_qb_line_identical_across_reception_presets():
    qb = {"pass_yd": 4000.0, "pass_td": 30.0, "pass_int": 10.0, "rush_yd": 300.0}
    assert score(qb, ScoringSettings.preset("standard")) == score(qb, ScoringSettings.preset("ppr"))


def test_unknown_stats_ignored():
    assert score({"made_up_stat": 99.0}, ScoringSettings.preset("ppr")) == 0.0


def test_custom_override():
    scoring = ScoringSettings.preset("ppr")
    scoring.weights["pass_td"] = 6.0
    assert score({"pass_td": 5.0}, scoring) == 30.0

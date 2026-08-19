from draftkit.engine.adp import blend_adp


def test_empty_sources():
    assert blend_adp({}, {"sleeper": 0.5}) is None


def test_single_source():
    assert blend_adp({"sleeper": 10.0}, {"sleeper": 0.5, "ffcalc": 0.5}) == 10.0


def test_weighted_mean():
    assert blend_adp({"sleeper": 10.0, "ffcalc": 20.0}, {"sleeper": 0.75, "ffcalc": 0.25}) == 12.5


def test_unknown_source_defaults_to_weight_one():
    assert blend_adp({"mystery": 8.0}, {}) == 8.0

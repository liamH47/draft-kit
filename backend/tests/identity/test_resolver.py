from pathlib import Path

from draftkit.identity.resolver import Resolver

PLAYERS = [
    {"sleeper_id": "1", "name": "A.J. Brown", "position": "WR", "team": "PHI"},
    {"sleeper_id": "2", "name": "Kenneth Walker", "position": "RB", "team": "SEA"},
    {"sleeper_id": "3", "name": "Josh Allen", "position": "QB", "team": "BUF"},
    # Two different Josh Allens at the same position poison name-only lookup.
    {"sleeper_id": "4", "name": "Josh Allen", "position": "QB", "team": "NO"},
]


def build(overrides_path=None, crosswalk=None):
    return Resolver.build(PLAYERS, crosswalk, overrides_path)


def test_exact_name_pos_team():
    assert build().resolve("AJ Brown", "WR", "PHI").sleeper_id == "1"


def test_suffix_and_name_pos_fallback():
    res = build().resolve("Kenneth Walker III", "RB")
    assert res.sleeper_id == "2"
    assert res.confidence == "name_pos"


def test_ambiguous_name_pos_is_poisoned():
    res = build().resolve("Josh Allen", "QB")
    assert res.sleeper_id is None
    assert build().resolve("Josh Allen", "QB", "BUF").sleeper_id == "3"


def test_unmatched_collected():
    r = build()
    assert r.resolve("Nonexistent Player", "WR").sleeper_id is None
    assert r.unmatched == [{"name": "Nonexistent Player", "position": "WR", "team": None}]


def test_crosswalk_merge_name_indexes(tmp_path):
    crosswalk = [
        {
            "sleeper_id": "9",
            "name": "Hollywood Brown",
            "merge_name": "marquise brown",
            "position": "WR",
            "team": "KC",
        },
    ]
    r = build(crosswalk=crosswalk)
    assert r.resolve("Marquise Brown", "WR").sleeper_id == "9"
    assert r.resolve("Hollywood Brown", "WR").sleeper_id == "9"


def test_overrides_win(tmp_path: Path):
    path = tmp_path / "overrides.yaml"
    path.write_text('"A.J. Brown": "42"\n')
    res = build(overrides_path=path).resolve("A.J. Brown", "WR", "PHI")
    assert res.sleeper_id == "42"
    assert res.confidence == "override"

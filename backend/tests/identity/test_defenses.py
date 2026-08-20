"""Defenses, which no crosswalk covers and every source names differently.

The DynastyProcess crosswalk carries zero DST rows, so there is no id to join
on. What the sources agree on is the team; what they disagree on is how to
spell it. Getting this wrong costs defenses their ADP and bye entirely.
"""

import pytest

from draftkit.identity.resolver import Resolver
from draftkit.identity.teams import TEAMS, canonical_team, team_from_defense_name

PLAYERS = [
    {"sleeper_id": "SF", "name": "San Francisco 49ers", "position": "DEF", "team": "SF"},
    {"sleeper_id": "GB", "name": "Green Bay Packers", "position": "DEF", "team": "GB"},
    {"sleeper_id": "NYG", "name": "New York Giants", "position": "DEF", "team": "NYG"},
    {"sleeper_id": "1", "name": "Real Player", "position": "WR", "team": "SF"},
]


@pytest.mark.parametrize(
    "spelling",
    [
        "San Francisco 49ers",  # Sleeper
        "San Francisco Defense",  # FantasyFootballCalculator
        "49ers D/ST",  # ESPN
        "SF DST",
        "San Francisco D/ST",
        "49ers",
    ],
)
def test_every_spelling_of_a_defense_resolves(spelling):
    assert Resolver.build(PLAYERS).resolve(spelling, "DEF").sleeper_id == "SF"


def test_a_defense_resolves_by_team_code_even_with_an_odd_name():
    r = Resolver.build(PLAYERS)
    assert r.resolve("Whatever They Are Called Now", "DEF", "SFO").sleeper_id == "SF"


@pytest.mark.parametrize(
    ("alias", "canonical"),
    [("SFO", "SF"), ("GBP", "GB"), ("KCC", "KC"), ("JAC", "JAX"), ("NOS", "NO"), ("WSH", "WAS")],
)
def test_crosswalk_team_codes_fold_onto_sleepers(alias, canonical):
    """The crosswalk spells six teams differently from Sleeper, which silently
    killed every team-keyed lookup."""
    assert canonical_team(alias) == canonical


def test_relocated_teams_still_resolve():
    assert canonical_team("OAK") == "LV"
    assert canonical_team("SD") == "LAC"
    assert canonical_team("STL") == "LAR"


def test_unknown_codes_and_names_return_none():
    assert canonical_team("XYZ") is None
    assert canonical_team(None) is None
    assert team_from_defense_name("Not A Team At All") is None


def test_a_defense_we_do_not_have_is_reported_unmatched():
    r = Resolver.build(PLAYERS)
    assert r.resolve("Chicago Bears", "DEF").sleeper_id is None
    assert r.unmatched[-1]["position"] == "DEF"


def test_ambiguous_new_york_needs_the_nickname():
    """Two teams share a city, so the city alone must not pick one."""
    r = Resolver.build(PLAYERS)
    assert r.resolve("New York Giants", "DEF").sleeper_id == "NYG"
    assert r.resolve("Jets", "DEF").sleeper_id is None  # we have no Jets defense


def test_every_team_has_a_city_and_nickname():
    assert len(TEAMS) == 32
    for abbr, (city, nickname) in TEAMS.items():
        assert city and nickname, abbr


def test_non_defense_players_are_unaffected():
    assert Resolver.build(PLAYERS).resolve("Real Player", "WR", "SFO").sleeper_id == "1"


def test_a_name_that_is_only_noise_resolves_to_nothing():
    """ "D/ST" with no team in it identifies nobody."""
    assert team_from_defense_name("D/ST") is None
    assert team_from_defense_name("   ") is None


def test_a_defense_with_no_recognisable_team_is_skipped_when_indexing():
    """A source row we cannot place must not claim a team slot."""
    players = [
        {"sleeper_id": "??", "name": "Mystery Defense", "position": "DEF", "team": None},
        {"sleeper_id": "SF", "name": "San Francisco 49ers", "position": "DEF", "team": "SF"},
    ]
    r = Resolver.build(players)
    assert r.resolve("San Francisco Defense", "DEF").sleeper_id == "SF"
    assert r.resolve("Mystery Defense", "DEF").sleeper_id is None


def test_short_phrases_do_not_match_by_accident():
    """A two-letter code inside a longer word must not claim the name."""
    assert team_from_defense_name("Greenland Bears Of Somewhere") != "GB"

"""Parsing an ESPN league's settings, including the shapes that go wrong."""

import json

import pytest

from draftkit.sources import espn_league
from draftkit.sources.base import RawPayload, SourceError
from tests.conftest import load_fixture


def body(payload) -> RawPayload:
    return RawPayload(body=json.dumps(payload).encode(), content_type="application/json")


def test_unmapped_slots_are_ignored_not_guessed():
    """ESPN's IR slot is not a draftable roster spot; mapping it to something
    approximate would inflate the draft length."""
    row = espn_league.parse(load_fixture("/leagues/")).rows[0]
    assert "ir" not in row["roster"]
    assert sum(row["roster"].values()) == 17


@pytest.mark.parametrize(
    ("reception_points", "expected"),
    [(0.0, "standard"), (0.25, "half_ppr"), (0.5, "half_ppr"), (1.0, "ppr"), (1.5, "ppr")],
)
def test_scoring_preset_follows_the_reception_value(reception_points, expected):
    payload = {
        "id": 1,
        "settings": {
            "name": "L",
            "size": 10,
            "rosterSettings": {"lineupSlotCounts": {"0": 1, "20": 5}},
            "scoringSettings": {"scoringItems": [{"statId": 53, "points": reception_points}]},
        },
    }
    row = espn_league.parse(body(payload)).rows[0]
    assert row["scoring_preset"] == expected
    assert row["reception_points"] == reception_points


def test_a_league_with_no_reception_scoring_is_standard():
    payload = {
        "id": 1,
        "settings": {
            "name": "L",
            "size": 8,
            "rosterSettings": {"lineupSlotCounts": {"0": 1}},
            "scoringSettings": {"scoringItems": [{"statId": 3, "points": 0.04}]},
        },
    }
    assert espn_league.parse(body(payload)).rows[0]["scoring_preset"] == "standard"


def test_superflex_leagues_are_recognised():
    payload = {
        "id": 1,
        "settings": {
            "name": "SF",
            "size": 12,
            "rosterSettings": {"lineupSlotCounts": {"0": 1, "7": 1, "20": 5}},
            "scoringSettings": {},
        },
    }
    assert espn_league.parse(body(payload)).rows[0]["roster"]["superflex"] == 1


def test_missing_sections_do_not_crash():
    payload = {"id": 1, "settings": {}}
    row = espn_league.parse(body(payload)).rows[0]
    assert row["roster"] == {}
    assert row["num_teams"] == 0


def test_private_league_response_is_rejected_with_a_useful_message():
    with pytest.raises(SourceError, match="private"):
        espn_league.validate(body({"messages": ["not authorized"]}))


@pytest.mark.parametrize(
    ("raw_body", "content_type", "match"),
    [
        (b"{}", "text/html", "expected JSON"),
        (b"{ truncated", "application/json", "not valid JSON"),
        (b"[]", "application/json", "no settings"),
    ],
)
def test_unusable_payloads_are_rejected(raw_body, content_type, match):
    with pytest.raises(SourceError, match=match):
        espn_league.validate(RawPayload(body=raw_body, content_type=content_type))


def test_cookies_are_only_sent_when_both_are_present():
    base = {"season": 2026, "league_id": "1"}
    assert "Cookie" not in espn_league.request(base).headers
    assert "Cookie" not in espn_league.request({**base, "espn_s2": "a"}).headers
    assert "Cookie" not in espn_league.request({**base, "swid": "b"}).headers
    spec = espn_league.request({**base, "espn_s2": "a", "swid": "b"})
    assert spec.headers["Cookie"] == "espn_s2=a; SWID=b"

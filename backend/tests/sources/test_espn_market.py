"""ESPN: the one source that carries both a market price and a ranking list.

Their difference is what predicts a specific room — autodrafters walk the list
mechanically and casual drafters anchor to it, while ADP records what actually
happened. Neither is a value estimate, and they must stay separate.
"""

import json

import pytest

from draftkit.sources import espn_market
from draftkit.sources.base import RawPayload, SourceError
from tests.conftest import load_fixture


def parsed():
    raw = load_fixture("lm-api-reads")
    espn_market.validate(raw)
    return {row["name"]: row for row in espn_market.parse(raw).rows}


def test_request_lifts_the_row_cap():
    spec = espn_market.request({"season": 2026})
    assert "seasons/2026/players" in spec.url
    assert json.loads(spec.headers["X-Fantasy-Filter"])["players"]["limit"] > 50


def test_market_and_list_are_captured_separately():
    rows = parsed()
    cook = rows["James Cook"]
    assert cook["adp"] == 22.5  # where he actually goes
    assert cook["list_rank"] == 40  # where ESPN's list puts him
    assert cook["adp"] != cook["list_rank"]


def test_non_fantasy_positions_are_dropped():
    assert "Some Punter" not in parsed()


def test_defenses_are_kept():
    assert parsed()["San Francisco 49ers"]["position"] == "DEF"


def test_missing_ownership_and_ranks_are_none_not_zero():
    """A player with no market yet must not read as ADP 0, which would look
    like the first pick of the draft."""
    deep = parsed()["Deep Sleeper"]
    assert deep["adp"] is None
    assert deep["list_rank"] is None


def test_rank_falls_back_across_rank_types():
    body = json.dumps(
        [
            {
                "id": 1,
                "player": {
                    "fullName": "Standard Only",
                    "defaultPositionId": 2,
                    "ownership": {"averageDraftPosition": 10.0},
                    "draftRanksByRankType": {"PPR": {}, "STANDARD": {"rank": 7}},
                },
            }
        ]
        * 12
    ).encode()
    rows = espn_market.parse(RawPayload(body=body, content_type="application/json"))
    assert rows.rows[0]["list_rank"] == 7


@pytest.mark.parametrize(
    ("body", "content_type", "match"),
    [
        (b"{}", "text/html", "expected JSON"),
        (b"{ truncated", "application/json", "not valid JSON"),
        (b'{"players": []}', "application/json", "non-trivial"),
        (b"[]", "application/json", "non-trivial"),
    ],
)
def test_unusable_payloads_are_rejected(body, content_type, match):
    with pytest.raises(SourceError, match=match):
        espn_market.validate(RawPayload(body=body, content_type=content_type))

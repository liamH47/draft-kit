"""Every way a source can hand us something unusable.

Third-party feeds change shape mid-season without warning. These are the
branches that decide whether that becomes a visible stale banner or a poisoned
snapshot, so they are worth testing individually.
"""

import json

import pytest

from draftkit.sources import (
    borischen_tiers,
    dp_playerids,
    ffcalc_adp,
    sleeper_players,
    sleeper_projections,
)
from draftkit.sources.base import RawPayload, SourceError


def json_body(payload) -> RawPayload:
    return RawPayload(body=json.dumps(payload).encode(), content_type="application/json")


# --- wrong content type -----------------------------------------------------


@pytest.mark.parametrize("adapter", [sleeper_players, sleeper_projections])
def test_non_json_content_type_is_rejected(adapter):
    with pytest.raises(SourceError, match="expected JSON"):
        adapter.validate(RawPayload(body=b"{}", content_type="text/html"))


def test_ffcalc_accepts_json_mislabeled_as_html():
    # FFC's Cloudflare cache serves the JSON payload as text/html; the body
    # is what matters.
    body = json.dumps({"status": "Success", "players": [{"name": "A", "adp": 1.0}]}).encode()
    ffcalc_adp.validate(RawPayload(body=body, content_type="text/html; charset=utf-8"))


def test_ffcalc_rejects_a_body_that_is_not_json():
    with pytest.raises(SourceError, match="expected JSON, got text/html"):
        ffcalc_adp.validate(RawPayload(body=b"<html>error</html>", content_type="text/html"))


def test_ffcalc_rejects_a_non_mapping_json_body():
    with pytest.raises(SourceError, match="status/players"):
        ffcalc_adp.validate(RawPayload(body=b"[]", content_type="application/json"))


# --- malformed bodies -------------------------------------------------------


@pytest.mark.parametrize(
    ("adapter", "match"),
    [(sleeper_players, "not valid JSON"), (sleeper_projections, "not valid JSON")],
)
def test_truncated_json_is_rejected(adapter, match):
    with pytest.raises(SourceError, match=match):
        adapter.validate(RawPayload(body=b'{"a": ', content_type="application/json"))


def test_players_payload_must_be_a_populated_mapping():
    with pytest.raises(SourceError, match="mapping"):
        sleeper_players.validate(json_body({"only": {"one": 1}}))
    with pytest.raises(SourceError, match="mapping"):
        sleeper_players.validate(json_body([{"player_id": "1"}]))


def test_projections_payload_must_be_a_populated_list():
    with pytest.raises(SourceError, match="non-trivial"):
        sleeper_projections.validate(json_body([{"player_id": "1"}]))
    with pytest.raises(SourceError, match="non-trivial"):
        sleeper_projections.validate(json_body({"players": []}))


def test_ffcalc_error_response_is_rejected():
    with pytest.raises(SourceError, match="status/players"):
        ffcalc_adp.validate(json_body({"status": "Success", "players": []}))


def test_borischen_rejects_an_unexpected_header():
    body = b'"Rank","Name","Position"\n1,"Someone","RB"\n'
    with pytest.raises(SourceError, match="tiers CSV header"):
        borischen_tiers.validate(RawPayload(body=body, content_type="text/csv"))


def test_dp_rejects_a_csv_without_the_join_key():
    body = b"mfl_id,name,position\n1,Someone,RB\n"
    with pytest.raises(SourceError, match="playerids CSV header"):
        dp_playerids.validate(RawPayload(body=body, content_type="text/csv"))


# --- rows that must be skipped rather than crash ----------------------------


def test_players_without_a_usable_name_are_skipped():
    payload = {str(i): {"position": "WR", "team": "SF", "full_name": f"P{i}"} for i in range(10)}
    payload["nameless"] = {"position": "WR", "team": "SF"}  # no name fields at all
    payload["blank"] = {"position": "RB", "first_name": "", "last_name": ""}
    ds = sleeper_players.parse(json_body(payload))
    ids = {row["sleeper_id"] for row in ds.rows}
    assert "nameless" not in ids
    assert "blank" not in ids
    assert len(ids) == 10


def test_projection_rows_without_stats_or_an_id_are_skipped():
    rows = [{"player_id": str(i), "stats": {"rec": 1.0}} for i in range(10)]
    rows.append({"player_id": "no_stats", "stats": {}})
    rows.append({"stats": {"rec": 5.0}})  # no player_id
    ds = sleeper_projections.parse(json_body(rows))
    ids = {row["sleeper_id"] for row in ds.rows}
    assert "no_stats" not in ids
    assert len(ids) == 10

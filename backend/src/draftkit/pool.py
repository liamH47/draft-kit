"""Assemble the scored, ranked draft pool for a league configuration.

Joins: sleeper players (identity) + sleeper projections (raw stats + ADP) as
the required spine; FFC ADP and Boris Chen tiers layered on via the resolver
when available. Any optional source failing (even with no snapshot) costs its
columns, never the pool.
"""

import json
import time
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

from draftkit.engine.adp import (
    CUSTOM_PREFIX,
    blend_adp,
    consensus_rank,
    consensus_weights,
    list_vs_market,
    sentinel_cutoff,
)
from draftkit.engine.baselines import baselines
from draftkit.engine.scoring import score
from draftkit.engine.tiers import gap_tiers
from draftkit.identity.resolver import Resolver
from draftkit.models.league import DEFAULT_ADP_WEIGHTS, LeagueConfig
from draftkit.models.player import PoolPlayer
from draftkit.snapshots.store import SnapshotMeta, SnapshotStore
from draftkit.sources import (
    borischen_tiers,
    cbs_rankings,
    dp_playerids,
    espn_market,
    espn_projections,
    fantasypros,
    ffcalc_adp,
    mfl_adp,
    sleeper_players,
    sleeper_projections,
    sleeper_trending,
    yahoo_adp,
)

_PRESET_TO_SLEEPER_ADP = {
    "standard": "adp_std",
    "half_ppr": "adp_half_ppr",
    "ppr": "adp_ppr",
}

# Yahoo ADP fades out around the top ~275; never walk past this.
_YAHOO_MAX_START = 400

# Beyond this there is no draft and therefore no draft price. Sleeper reports
# an ADP for every player it ranks, running smoothly out to a 999 sentinel for
# the undrafted; the real markets (FFC, ESPN, Yahoo) all stop below 200,
# because that is where drafting stops. Treating the tail as a price made
# undrafted kickers look like they were "falling" 300 picks.
_MAX_MEANINGFUL_ADP = 250.0

# How far back to look for market movement. Long enough to span a couple of
# warms, short enough that "he is rising" means this week and not last month.
_MOVEMENT_WINDOW = timedelta(days=4)


@dataclass
class PoolResult:
    players: list[PoolPlayer]
    sources: dict[str, SnapshotMeta]
    unmatched: list[dict[str, Any]]


# Building the pool costs ~800ms of parsing and identity resolution, and the
# board rereads it after every single pick — that lag is what makes entering
# a pick feel slow. The pool only actually changes when a snapshot lands or
# the league config does, so cache per configuration until either happens.
# The time cap keeps the store's TTL semantics: without it, a cache hit would
# skip store.get() forever and a lapsed source would never refetch.
_POOL_CACHE_SECONDS = 300.0
_pool_cache: dict[tuple, tuple[float, tuple, PoolResult]] = {}


def clear_pool_cache() -> None:
    _pool_cache.clear()


def _custom_ranks_fingerprint(custom_ranks: dict | None) -> str:
    """A stable, cheap identity for the user's pasted lists, or their weights.

    Names and sizes alone would miss a re-paste of the same list at the same
    length, which is exactly what correcting a cheat sheet looks like, so the
    contents go in. The lists are a few hundred rows, and this runs once per
    board read.
    """
    if not custom_ranks:
        return ""
    return json.dumps(custom_ranks, sort_keys=True)


def build_pool_cached(
    store: SnapshotStore,
    league: LeagueConfig,
    *,
    season: int,
    scoring_preset: str = "half_ppr",
    overrides_path: Path | None = None,
    min_points: float = 1.0,
    custom_ranks: dict[str, dict[str, float]] | None = None,
    custom_weights: dict[str, float] | None = None,
) -> PoolResult:
    # The user's own pasted lists change the pool (they feed consensus and the
    # list-vs-market nudge), so they have to be part of the cache identity or a
    # freshly imported cheat sheet would not show up until the cache lapsed.
    # Their weights ride along for the same reason: reweighting a list moves
    # the consensus column without adding or removing a single row.
    key = (
        league.model_dump_json(),
        season,
        scoring_preset,
        str(overrides_path),
        min_points,
        _custom_ranks_fingerprint(custom_ranks),
        _custom_ranks_fingerprint(custom_weights),
    )
    token = store.freshness_token()
    hit = _pool_cache.get(key)
    if hit is not None:
        built_at, cached_token, result = hit
        if cached_token == token and time.monotonic() - built_at < _POOL_CACHE_SECONDS:
            return result
    result = build_pool(
        store,
        league,
        season=season,
        scoring_preset=scoring_preset,
        overrides_path=overrides_path,
        min_points=min_points,
        custom_ranks=custom_ranks,
        custom_weights=custom_weights,
    )
    # Re-fingerprint AFTER building: the build itself may have fetched and
    # written snapshots, and the cached token must describe the tree the
    # pool was actually built from.
    _pool_cache[key] = (time.monotonic(), store.freshness_token(), result)
    return result


def build_pool(
    store: SnapshotStore,
    league: LeagueConfig,
    *,
    season: int,
    scoring_preset: str = "half_ppr",
    overrides_path: Path | None = None,
    min_points: float = 1.0,
    custom_ranks: dict[str, dict[str, float]] | None = None,
    custom_weights: dict[str, float] | None = None,
) -> PoolResult:
    sources: dict[str, SnapshotMeta] = {}
    custom_ranks = custom_ranks or {}
    # How far the user trusts each of their own lists, folded in beside the
    # published ones. A list nobody weighted counts level with ESPN and CBS.
    rank_weights = consensus_weights(custom_weights)

    players_ds, sources["sleeper_players"] = store.get(sleeper_players)
    proj_ds, sources["sleeper_projections"] = store.get(sleeper_projections, {"season": season})

    crosswalk_rows: list[dict[str, Any]] = []
    try:
        dp_ds, sources["dp_playerids"] = store.get(dp_playerids)
        crosswalk_rows = dp_ds.rows
    except Exception:
        pass

    # espn_id -> sleeper_id, so a platform source can join by id rather than by
    # name. Ids beat names whenever a source offers them.
    espn_to_sleeper = {
        row["espn_id"]: row["sleeper_id"] for row in crosswalk_rows if row.get("espn_id")
    }

    resolver = Resolver.build(players_ds.rows, crosswalk_rows, overrides_path)
    players_by_id = {p["sleeper_id"]: p for p in players_ds.rows}

    # Every market's full price list, kept so its bucket-of-the-undrafted can
    # be spotted. That is a property of the source, not of the subset that
    # happened to join our player universe.
    raw_adp: dict[str, list[float]] = {}

    ffc_by_id: dict[str, dict[str, Any]] = {}
    try:
        ffc_ds, sources["ffcalc"] = store.get(
            ffcalc_adp, {"format": scoring_preset, "teams": league.num_teams, "year": season}
        )
        raw_adp["ffcalc"] = [float(r["adp"]) for r in ffc_ds.rows if r.get("adp")]
        for row in ffc_ds.rows:
            res = resolver.resolve(row["name"], row["position"], row.get("team"))
            if res.sleeper_id:
                ffc_by_id[res.sleeper_id] = row
    except Exception:
        pass

    # What each market said a few days ago, so a player whose price is moving
    # can be flagged. An injury ahead of somebody shows up here first. Every
    # market is compared only against its OWN past — never across markets,
    # where a blend whose members change would read as movement that never
    # happened.
    adp_before: dict[str, dict[str, float]] = {}

    def _previous(adapter: Any, params: dict[str, Any], to_sleeper_id) -> dict[str, float]:
        try:
            earlier = store.earliest_within(adapter, params, _MOVEMENT_WINDOW)
            if earlier is None:
                return {}
            was: dict[str, float] = {}
            for row in earlier[0].rows:
                sleeper_id = to_sleeper_id(row)
                if sleeper_id and row.get("adp"):
                    was.setdefault(sleeper_id, float(row["adp"]))
            return was
        except Exception:
            return {}

    adp_before["ffcalc"] = _previous(
        ffcalc_adp,
        {"format": scoring_preset, "teams": league.num_teams, "year": season},
        lambda row: resolver.resolve(row["name"], row["position"], row.get("team")).sleeper_id,
    )

    tiers_by_id: dict[str, int] = {}
    expert_by_id: dict[str, dict[str, Any]] = {}
    try:
        bchen_ds, sources["borischen"] = store.get(borischen_tiers, {"format": scoring_preset})
        for row in bchen_ds.rows:
            res = resolver.resolve(row["name"], row["position"])
            if res.sleeper_id:
                tiers_by_id[res.sleeper_id] = row["tier"]
                expert_by_id[res.sleeper_id] = row
    except Exception:
        pass

    # A platform source carries both its own market price and its own list.
    # Their difference predicts a room; neither is a value estimate.
    espn_by_id: dict[str, dict[str, Any]] = {}
    try:
        espn_ds, sources["espn_market"] = store.get(espn_market, {"season": season})
        raw_adp["espn"] = [float(r["adp"]) for r in espn_ds.rows if r.get("adp")]
        for row in espn_ds.rows:
            sleeper_id = espn_to_sleeper.get(row["espn_id"])
            if sleeper_id is None and row.get("name"):
                sleeper_id = resolver.resolve(row["name"], row["position"]).sleeper_id
            if sleeper_id:
                espn_by_id[sleeper_id] = row
    except Exception:
        pass

    # The second projection source. One projection source cannot cross-check
    # itself; averaged points damp any single feed's optimism.
    espn_proj_by_id: dict[str, dict[str, Any]] = {}
    try:
        eproj_ds, sources["espn_projections"] = store.get(espn_projections, {"season": season})
        for row in eproj_ds.rows:
            sleeper_id = espn_to_sleeper.get(row["espn_id"])
            if sleeper_id is None and row.get("name"):
                sleeper_id = resolver.resolve(row["name"], row["position"]).sleeper_id
            if sleeper_id:
                espn_proj_by_id[sleeper_id] = row
    except Exception:
        pass

    adp_before["espn"] = _previous(
        espn_market,
        {"season": season},
        lambda row: (
            espn_to_sleeper.get(row["espn_id"])
            or (
                resolver.resolve(row["name"], row["position"]).sleeper_id
                if row.get("name")
                else None
            )
        ),
    )

    cbs_to_sleeper = {
        row["cbs_id"]: row["sleeper_id"] for row in crosswalk_rows if row.get("cbs_id")
    }
    cbs_by_id: dict[str, dict[str, Any]] = {}
    try:
        cbs_ds, sources["cbs_rankings"] = store.get(cbs_rankings, {"format": scoring_preset})
        for row in cbs_ds.rows:
            sleeper_id = cbs_to_sleeper.get(row["cbs_id"])
            if sleeper_id is None and row.get("name"):
                sleeper_id = resolver.resolve(
                    row["name"], row["position"], row.get("team")
                ).sleeper_id
            if sleeper_id:
                cbs_by_id[sleeper_id] = row
    except Exception:
        pass

    # FantasyPros ECR. The crosswalk carries fantasypros_id, so individual
    # players join by id and only team defenses reach the name resolver —
    # which is the join the defense index was built for.
    fp_to_sleeper = {
        row["fantasypros_id"]: row["sleeper_id"]
        for row in crosswalk_rows
        if row.get("fantasypros_id")
    }
    fp_by_id: dict[str, dict[str, Any]] = {}
    try:
        # Which FantasyPros board applies is decided by the ROSTER, not the
        # scoring preset: a superflex slot is a second QB in all but name, and
        # the consensus prices quarterbacks completely differently for it.
        fp_ds, sources["fantasypros"] = store.get(
            fantasypros,
            {"format": scoring_preset, "superflex": bool(league.roster.superflex)},
        )
        for row in fp_ds.rows:
            sleeper_id = fp_to_sleeper.get(row["fantasypros_id"])
            if sleeper_id is None and row.get("name"):
                sleeper_id = resolver.resolve(
                    row["name"], row["position"], row.get("team")
                ).sleeper_id
            if sleeper_id:
                fp_by_id[sleeper_id] = row
    except Exception:
        pass

    # MyFantasyLeague: hand-run home leagues, which is the population this
    # tool actually gets used in. mfl_id is the crosswalk's own primary key, so
    # this is the one market that needs no name matching at all.
    mfl_to_sleeper = {
        row["mfl_id"]: row["sleeper_id"] for row in crosswalk_rows if row.get("mfl_id")
    }
    mfl_by_id: dict[str, dict[str, Any]] = {}
    try:
        mfl_params = {"format": scoring_preset, "year": season}
        mfl_ds, sources["mfl_adp"] = store.get(mfl_adp, mfl_params)
        raw_adp["mfl"] = [float(r["adp"]) for r in mfl_ds.rows if r.get("adp")]
        for row in mfl_ds.rows:
            sleeper_id = mfl_to_sleeper.get(row["mfl_id"])
            if sleeper_id:
                mfl_by_id[sleeper_id] = row
    except Exception:
        pass

    adp_before["mfl"] = _previous(
        mfl_adp,
        {"format": scoring_preset, "year": season},
        lambda row: mfl_to_sleeper.get(row["mfl_id"]),
    )

    # Waiver churn on Sleeper over the last day. This is the fastest signal the
    # app holds — it moves within hours of news, where ADP takes days — so it
    # is the first place a changed situation shows up. Never scored: adds
    # follow news, and news is as often the man in front tearing an ACL as it
    # is a breakout.
    trend_by_id: dict[str, int] = {}
    for kind, sign in (("add", 1), ("drop", -1)):
        try:
            trend_ds, sources[f"sleeper_trending_{kind}"] = store.get(
                sleeper_trending, {"kind": kind}
            )
        except Exception:
            continue
        for row in trend_ds.rows:
            trend_by_id[row["sleeper_id"]] = (
                trend_by_id.get(row["sleeper_id"], 0) + sign * row["trend_count"]
            )
    # Scale against the hottest add in the window: the raw counts depend on how
    # many people happened to be on Sleeper today, and mean nothing on their own.
    trend_peak = max(trend_by_id.values(), default=0)

    # Yahoo pages are capped at 25 and ADP decays to nothing past the top
    # ~275; walk pages until one carries no ADP at all. A page that fails
    # mid-walk costs the tail, not the source.
    yahoo_to_sleeper = {
        row["yahoo_id"]: row["sleeper_id"] for row in crosswalk_rows if row.get("yahoo_id")
    }
    yahoo_by_id: dict[str, dict[str, Any]] = {}
    for start in range(0, _YAHOO_MAX_START, yahoo_adp.PAGE_SIZE):
        try:
            page_ds, sources["yahoo_adp"] = store.get(yahoo_adp, {"start": start})
        except Exception:
            break
        page_had_adp = False
        raw_adp.setdefault("yahoo", []).extend(
            float(r["adp"]) for r in page_ds.rows if r.get("adp")
        )
        for row in page_ds.rows:
            if row.get("adp") is not None:
                page_had_adp = True
            sleeper_id = yahoo_to_sleeper.get(row["yahoo_id"])
            if sleeper_id is None and row.get("name"):
                sleeper_id = resolver.resolve(
                    row["name"], row["position"], row.get("team")
                ).sleeper_id
            if sleeper_id:
                yahoo_by_id.setdefault(sleeper_id, row)
        if not page_had_adp:
            break

    adp_before["yahoo"] = {}
    for start in range(0, _YAHOO_MAX_START, yahoo_adp.PAGE_SIZE):
        page = _previous(
            yahoo_adp,
            {"start": start},
            lambda row: (
                yahoo_to_sleeper.get(row["yahoo_id"])
                or resolver.resolve(row["name"], row["position"], row.get("team")).sleeper_id
            ),
        )
        if not page:
            break
        adp_before["yahoo"].update(page)

    adp_field = _PRESET_TO_SLEEPER_ADP.get(scoring_preset, "adp_half_ppr")

    # A league saved before a market existed carries no weight for it, and
    # blend_adp gives an unweighted source weight 1.0 — so MFL would have
    # counted double against every other market in every league created before
    # it was added. Defaults fill the gaps; the league's own settings win.
    adp_weights = {**DEFAULT_ADP_WEIGHTS, **league.adp_weights}

    # Find each market's bucket-of-the-undrafted before using any of its
    # numbers, so a hundred players sharing one trailing value never read as a
    # hundred players who are "falling" to it.
    raw_adp["sleeper"] = [
        float(r["adp"][adp_field]) for r in proj_ds.rows if r["adp"].get(adp_field)
    ]
    adp_ceiling = {
        source: min(_MAX_MEANINGFUL_ADP, sentinel_cutoff(values) or _MAX_MEANINGFUL_ADP)
        for source, values in raw_adp.items()
    }
    pool: list[PoolPlayer] = []
    for proj in proj_ds.rows:
        player = players_by_id.get(proj["sleeper_id"])
        if player is None:
            continue
        player_id = proj["sleeper_id"]
        ffc = ffc_by_id.get(player_id)
        espn = espn_by_id.get(player_id)
        expert = expert_by_id.get(player_id)
        eproj = espn_proj_by_id.get(player_id)
        cbs = cbs_by_id.get(player_id)
        fp = fp_by_id.get(player_id)
        yahoo = yahoo_by_id.get(player_id)
        mfl = mfl_by_id.get(player_id)

        extra: dict[str, float | str | None] = {}
        points = score(proj["stats"], league.scoring)
        if eproj is not None:
            # Rescore ESPN's raw stat line under this league's rules; DEF has
            # no mapped categories, so ESPN's own scored total stands in.
            espn_points = (
                score(eproj["stats"], league.scoring)
                if eproj["stats"]
                else float(eproj.get("applied_total") or 0.0)
            )
            if espn_points > 0:
                extra["points.sleeper"] = points
                extra["points.espn"] = espn_points
                points = round((points + espn_points) / 2, 2)
        if points < min_points:
            continue

        adp_by_source = {
            source: float(value)
            for source, value in (
                ("sleeper", proj["adp"].get(adp_field)),
                ("ffcalc", ffc.get("adp") if ffc else None),
                ("espn", espn.get("adp") if espn else None),
                ("yahoo", yahoo.get("adp") if yahoo else None),
                ("mfl", mfl.get("adp") if mfl else None),
            )
            if value and float(value) < adp_ceiling.get(source, _MAX_MEANINGFUL_ADP)
        }

        # Ranking lists, kept apart from market prices.
        rank_by_source: dict[str, float] = {}
        if espn and espn.get("list_rank"):
            rank_by_source["espn"] = float(espn["list_rank"])
        if cbs and cbs.get("rank"):
            rank_by_source["cbs"] = float(cbs["rank"])
        if expert and expert.get("expert_rank"):
            rank_by_source["expert"] = float(expert["expert_rank"])
        if fp and fp.get("rank"):
            rank_by_source["fantasypros"] = float(fp["rank"])
        # The user's own pasted lists sit alongside the published ones. They
        # are namespaced so a list called "espn" cannot quietly overwrite the
        # feed of the same name.
        for list_name, ranks in custom_ranks.items():
            if player_id in ranks:
                rank_by_source[f"{CUSTOM_PREFIX}{list_name}"] = ranks[player_id]

        spread = expert or fp
        if spread:
            extra["expert.stdev"] = spread.get("expert_stdev")
            extra["expert.best"] = spread.get("expert_best")
            extra["expert.worst"] = spread.get("expert_worst")
        if espn:
            extra["espn.percent_owned"] = espn.get("percent_owned")
            extra["espn.auction_value"] = espn.get("auction_value")
        if yahoo:
            extra["yahoo.average_cost"] = yahoo.get("average_cost")
            extra["yahoo.percent_drafted"] = yahoo.get("percent_drafted")
        blended = blend_adp(adp_by_source, adp_weights)
        # Movement, averaged over the markets that can see both readings. One
        # market moving is noise; the same player sliding in several is news,
        # so the count of agreeing markets travels with the number.
        shifts = [
            price - adp_before[source][player_id]
            for source, price in adp_by_source.items()
            if player_id in adp_before.get(source, {})
        ]
        adp_shift = round(sum(shifts) / len(shifts), 1) if shifts else None
        adp_shift_sources = len(shifts) or None
        # Byes chain across sources: FFC covers most, Yahoo and CBS fill the
        # defenses and deep names FFC does not list.
        bye = None
        for src in (ffc, yahoo, cbs, fp):
            if src and src.get("bye"):
                bye = src["bye"]
                break
        pool.append(
            PoolPlayer(
                player_id=player_id,
                name=player["name"],
                position=player["position"],
                team=player.get("team"),
                bye=bye,
                points=points,
                adp=blended,
                adp_by_source=adp_by_source,
                adp_stdev=ffc.get("stdev") if ffc else None,
                rank_by_source=rank_by_source,
                list_vs_market=list_vs_market(rank_by_source, blended),
                consensus_rank=consensus_rank(rank_by_source, rank_weights),
                adp_shift=adp_shift,
                adp_shift_sources=adp_shift_sources,
                injury_status=player.get("injury_status"),
                injury_body_part=player.get("injury_body_part"),
                depth_chart_order=player.get("depth_chart_order"),
                buzz=(
                    round(100 * trend_by_id[player_id] / trend_peak)
                    if trend_peak > 0 and player_id in trend_by_id
                    else None
                ),
                extra={k: v for k, v in extra.items() if v is not None},
                tier_expert=tiers_by_id.get(player_id),
                rank=0,
                pos_rank=0,
            )
        )

    # Raw points are not comparable across positions (every QB projects more
    # points than any RB), so the pool orders by value over the replacement
    # baseline — the same measure the recommendation score is built on. This
    # is what makes the "ALL" view read like a draft board instead of a list
    # of quarterbacks.
    points_by_position: dict[str, list[float]] = {}
    for p in pool:
        points_by_position.setdefault(p.position, []).append(p.points)
    bases = baselines(league, points_by_position)
    for p in pool:
        base = bases.get(p.position, {"vols": 0.0, "vorp": 0.0, "value": 0.0})
        p.vorp = round(p.points - base["vorp"], 1)
        p.vols = round(p.points - base["vols"], 1)
        p.value = round(p.points - base["value"], 1)

    pool.sort(key=lambda p: p.value, reverse=True)
    pos_counts: dict[str, int] = {}
    for i, p in enumerate(pool):
        p.rank = i + 1
        pos_counts[p.position] = pos_counts.get(p.position, 0) + 1
        p.pos_rank = pos_counts[p.position]

    # How far the room lets a player fall past where we rate him. ADP is
    # already a pick number and our rank is the pick we would spend on him, so
    # the two subtract directly: +40 means we have him 40 picks better than
    # the room takes him. That is the shape of a sleeper, and it is the number
    # to scan for once the obvious names are gone.
    for p in pool:
        if p.adp is not None:
            p.market_edge = round(p.adp - p.rank)

    for position in {p.position for p in pool}:
        # Within one position, value order == points order (a per-position
        # baseline is a constant shift), so gap tiers stay valid.
        at_pos = [p for p in pool if p.position == position]
        for p, tier in zip(at_pos, gap_tiers([p.points for p in at_pos]), strict=True):
            p.tier = tier

    return PoolResult(players=pool, sources=sources, unmatched=resolver.unmatched)

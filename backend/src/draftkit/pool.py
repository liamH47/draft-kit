"""Assemble the scored, ranked draft pool for a league configuration.

Joins: sleeper players (identity) + sleeper projections (raw stats + ADP) as
the required spine; FFC ADP and Boris Chen tiers layered on via the resolver
when available. Any optional source failing (even with no snapshot) costs its
columns, never the pool.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from draftkit.engine.adp import blend_adp, list_vs_market
from draftkit.engine.scoring import score
from draftkit.engine.tiers import gap_tiers
from draftkit.identity.resolver import Resolver
from draftkit.models.league import LeagueConfig
from draftkit.models.player import PoolPlayer
from draftkit.snapshots.store import SnapshotMeta, SnapshotStore
from draftkit.sources import (
    borischen_tiers,
    dp_playerids,
    espn_market,
    ffcalc_adp,
    sleeper_players,
    sleeper_projections,
)

_PRESET_TO_SLEEPER_ADP = {
    "standard": "adp_std",
    "half_ppr": "adp_half_ppr",
    "ppr": "adp_ppr",
}


@dataclass
class PoolResult:
    players: list[PoolPlayer]
    sources: dict[str, SnapshotMeta]
    unmatched: list[dict[str, Any]]


def build_pool(
    store: SnapshotStore,
    league: LeagueConfig,
    *,
    season: int,
    scoring_preset: str = "half_ppr",
    overrides_path: Path | None = None,
    min_points: float = 1.0,
) -> PoolResult:
    sources: dict[str, SnapshotMeta] = {}

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

    ffc_by_id: dict[str, dict[str, Any]] = {}
    try:
        ffc_ds, sources["ffcalc"] = store.get(
            ffcalc_adp, {"format": scoring_preset, "teams": league.num_teams, "year": season}
        )
        for row in ffc_ds.rows:
            res = resolver.resolve(row["name"], row["position"], row.get("team"))
            if res.sleeper_id:
                ffc_by_id[res.sleeper_id] = row
    except Exception:
        pass

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
        for row in espn_ds.rows:
            sleeper_id = espn_to_sleeper.get(row["espn_id"])
            if sleeper_id is None and row.get("name"):
                sleeper_id = resolver.resolve(row["name"], row["position"]).sleeper_id
            if sleeper_id:
                espn_by_id[sleeper_id] = row
    except Exception:
        pass

    adp_field = _PRESET_TO_SLEEPER_ADP.get(scoring_preset, "adp_half_ppr")
    pool: list[PoolPlayer] = []
    for proj in proj_ds.rows:
        player = players_by_id.get(proj["sleeper_id"])
        if player is None:
            continue
        points = score(proj["stats"], league.scoring)
        if points < min_points:
            continue
        player_id = proj["sleeper_id"]
        ffc = ffc_by_id.get(player_id)
        espn = espn_by_id.get(player_id)
        expert = expert_by_id.get(player_id)

        adp_by_source = {}
        if proj["adp"].get(adp_field):
            adp_by_source["sleeper"] = float(proj["adp"][adp_field])
        if ffc and ffc.get("adp"):
            adp_by_source["ffcalc"] = float(ffc["adp"])
        if espn and espn.get("adp"):
            adp_by_source["espn"] = float(espn["adp"])

        # Ranking lists, kept apart from market prices.
        rank_by_source: dict[str, float] = {}
        if espn and espn.get("list_rank"):
            rank_by_source["espn"] = float(espn["list_rank"])
        if expert and expert.get("expert_rank"):
            rank_by_source["expert"] = float(expert["expert_rank"])

        extra: dict[str, float | str | None] = {}
        if expert:
            extra["expert.stdev"] = expert.get("expert_stdev")
            extra["expert.best"] = expert.get("expert_best")
            extra["expert.worst"] = expert.get("expert_worst")
        if espn:
            extra["espn.percent_owned"] = espn.get("percent_owned")
            extra["espn.auction_value"] = espn.get("auction_value")
        blended = blend_adp(adp_by_source, league.adp_weights)
        pool.append(
            PoolPlayer(
                player_id=player_id,
                name=player["name"],
                position=player["position"],
                team=player.get("team"),
                bye=ffc.get("bye") if ffc else None,
                points=points,
                adp=blended,
                adp_by_source=adp_by_source,
                adp_stdev=ffc.get("stdev") if ffc else None,
                rank_by_source=rank_by_source,
                list_vs_market=list_vs_market(rank_by_source, blended),
                extra={k: v for k, v in extra.items() if v is not None},
                tier_expert=tiers_by_id.get(player_id),
                rank=0,
                pos_rank=0,
            )
        )

    pool.sort(key=lambda p: p.points, reverse=True)
    pos_counts: dict[str, int] = {}
    for i, p in enumerate(pool):
        p.rank = i + 1
        pos_counts[p.position] = pos_counts.get(p.position, 0) + 1
        p.pos_rank = pos_counts[p.position]

    for position in {p.position for p in pool}:
        at_pos = [p for p in pool if p.position == position]
        for p, tier in zip(at_pos, gap_tiers([p.points for p in at_pos]), strict=True):
            p.tier = tier

    return PoolResult(players=pool, sources=sources, unmatched=resolver.unmatched)

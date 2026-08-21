from pydantic import BaseModel

FANTASY_POSITIONS = {"QB", "RB", "WR", "TE", "K", "DEF"}


class Player(BaseModel):
    """Canonical player identity. player_id is the Sleeper ID everywhere."""

    player_id: str
    name: str
    position: str  # QB/RB/WR/TE/K/DEF
    team: str | None = None


class PoolPlayer(BaseModel):
    """One row of the scored, ranked draft pool served to the frontend."""

    player_id: str
    name: str
    position: str
    team: str | None = None
    bye: int | None = None
    points: float
    adp: float | None = None  # blended market price
    adp_by_source: dict[str, float] = {}
    adp_stdev: float | None = None
    # Where each ranking LIST puts him, as opposed to where he actually goes.
    # Kept separate from ADP on purpose: a list predicts behaviour (autodrafters
    # walk it, casual drafters anchor to it), it does not measure value.
    rank_by_source: dict[str, float] = {}
    # Positive when a list is higher on him than the market is — the market has
    # not caught up, so he tends to last longer than his list rank implies.
    list_vs_market: float | None = None
    # Weighted blend of the ranking lists, shown so a big model-vs-consensus
    # disagreement is visible rather than silent. Never a score input.
    consensus_rank: float | None = None
    # Whatever else a source provided, namespaced by source. Sources change
    # shape; nothing is dropped merely for being unrecognised.
    extra: dict[str, float | str | None] = {}
    # Where the market has moved him since the oldest snapshot we still hold.
    # Negative means his ADP got smaller — the room is taking him earlier than
    # it was, which is what an injury to the man ahead of him looks like.
    adp_shift: float | None = None
    # Places between where the market drafts him and where we rate him.
    # Positive means he lasts past his worth: the shape of a sleeper.
    market_edge: int | None = None
    tier: int | None = None  # gap-based, computed
    tier_expert: int | None = None  # Boris Chen
    # Value over the replacement baselines for this league (see engine/baselines):
    # vols/vorp for display, value (their midpoint) is what scores and orders.
    vorp: float = 0.0
    vols: float = 0.0
    value: float = 0.0
    rank: int  # 1-based by value within the pool — raw points are not
    # comparable across positions, so the pool never orders by them
    pos_rank: int  # 1-based within position

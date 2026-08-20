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
    # Whatever else a source provided, namespaced by source. Sources change
    # shape; nothing is dropped merely for being unrecognised.
    extra: dict[str, float | str | None] = {}
    tier: int | None = None  # gap-based, computed
    tier_expert: int | None = None  # Boris Chen
    rank: int  # 1-based by points within the pool
    pos_rank: int  # 1-based within position

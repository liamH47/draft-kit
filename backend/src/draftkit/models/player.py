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
    adp: float | None = None  # blended
    adp_by_source: dict[str, float] = {}
    adp_stdev: float | None = None
    tier: int | None = None  # gap-based, computed
    tier_expert: int | None = None  # Boris Chen
    rank: int  # 1-based by points within the pool
    pos_rank: int  # 1-based within position

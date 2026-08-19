from typing import Literal, Self

from pydantic import BaseModel, Field

ScoringPreset = Literal["standard", "half_ppr", "ppr"]

# Weights are keyed by Sleeper stat names, which are the raw stat lines we store.
_BASE_WEIGHTS: dict[str, float] = {
    "pass_yd": 0.04,
    "pass_td": 4.0,
    "pass_int": -2.0,
    "pass_2pt": 2.0,
    "rush_yd": 0.1,
    "rush_td": 6.0,
    "rush_2pt": 2.0,
    "rec_yd": 0.1,
    "rec_td": 6.0,
    "rec_2pt": 2.0,
    "fum_lost": -2.0,
    # kickers
    "xpm": 1.0,
    "fgm_0_19": 3.0,
    "fgm_20_29": 3.0,
    "fgm_30_39": 3.0,
    "fgm_40_49": 4.0,
    "fgm_50p": 5.0,
    "fgmiss": -1.0,
    # team defense
    "def_td": 6.0,
    "sack": 1.0,
    "int": 2.0,
    "fum_rec": 2.0,
    "safe": 2.0,
    "blk_kick": 2.0,
}

_REC_POINTS: dict[ScoringPreset, float] = {"standard": 0.0, "half_ppr": 0.5, "ppr": 1.0}


class ScoringSettings(BaseModel):
    """Per-stat point values. Points are always computed from raw stat lines at
    read time, so custom scoring is a config change, never a re-ingest."""

    weights: dict[str, float]

    @classmethod
    def preset(cls, name: ScoringPreset) -> Self:
        return cls(weights=_BASE_WEIGHTS | {"rec": _REC_POINTS[name]})


class RosterSlots(BaseModel):
    qb: int = 1
    rb: int = 2
    wr: int = 2
    te: int = 1
    flex: int = 1  # RB/WR/TE
    superflex: int = 0  # QB/RB/WR/TE
    k: int = 1
    dst: int = 1
    bench: int = 6


Platform = Literal["sleeper", "espn", "yahoo", "other"]


class LeagueConfig(BaseModel):
    name: str = "My league"
    platform: Platform = "other"
    num_teams: int = Field(default=12, ge=4, le=20)
    my_slot: int = Field(default=1, ge=1)
    scoring: ScoringSettings
    roster: RosterSlots = RosterSlots()
    # Weight per ADP source name when blending; missing sources are skipped.
    adp_weights: dict[str, float] = {"sleeper": 0.5, "ffcalc": 0.5}

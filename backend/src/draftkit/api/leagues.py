from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from draftkit.db import repo
from draftkit.models.league import (
    LeagueConfig,
    Platform,
    RosterSlots,
    ScoringPreset,
    ScoringSettings,
)

router = APIRouter(prefix="/api/leagues")


class LeagueCreate(BaseModel):
    name: str = "My league"
    platform: Platform = "other"
    num_teams: int = Field(default=12, ge=4, le=20)
    my_slot: int = Field(default=1, ge=1)
    rounds: int = Field(default=15, ge=1, le=30)
    scoring: ScoringPreset = "half_ppr"
    scoring_overrides: dict[str, float] = {}
    roster: RosterSlots = RosterSlots()
    adp_weights: dict[str, float] = {"sleeper": 0.5, "ffcalc": 0.5}

    def to_config(self) -> LeagueConfig:
        scoring = ScoringSettings.preset(self.scoring)
        scoring.weights.update(self.scoring_overrides)
        return LeagueConfig(
            name=self.name,
            platform=self.platform,
            num_teams=self.num_teams,
            my_slot=self.my_slot,
            scoring=scoring,
            roster=self.roster,
            adp_weights=self.adp_weights,
        )


@router.post("")
def create_league(request: Request, body: LeagueCreate) -> dict:
    if body.my_slot > body.num_teams:
        raise HTTPException(422, f"my_slot {body.my_slot} exceeds num_teams {body.num_teams}")
    conn = request.app.state.db
    league_id = repo.create_league(
        conn, body.to_config(), scoring_preset=body.scoring, rounds=body.rounds
    )
    league = repo.get_league(conn, league_id)
    assert league is not None
    return league


@router.get("")
def list_leagues(request: Request) -> list[dict]:
    return repo.list_leagues(request.app.state.db)


@router.get("/{league_id}")
def get_league(request: Request, league_id: int) -> dict:
    league = repo.get_league(request.app.state.db, league_id)
    if league is None:
        raise HTTPException(404, "league not found")
    return league

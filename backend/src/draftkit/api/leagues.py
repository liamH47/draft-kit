from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from draftkit.auth.routes import CurrentUser
from draftkit.db import repo
from draftkit.models.league import (
    LeagueConfig,
    Platform,
    RosterSlots,
    ScoringPreset,
    ScoringSettings,
)
from draftkit.sources import espn_league

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
    adp_weights: dict[str, float] = {"sleeper": 0.5, "ffcalc": 0.5, "espn": 0.5, "yahoo": 0.5}
    autodraft_count: int = Field(default=0, ge=0)

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
            autodraft_count=self.autodraft_count,
        )


@router.post("")
def create_league(request: Request, body: LeagueCreate, user: CurrentUser) -> dict:
    if body.my_slot > body.num_teams:
        raise HTTPException(422, f"my_slot {body.my_slot} exceeds num_teams {body.num_teams}")
    conn = request.app.state.db
    league_id = repo.create_league(
        conn,
        body.to_config(),
        scoring_preset=body.scoring,
        rounds=body.rounds,
        user_id=user.user_id,
    )
    league = repo.get_league(conn, league_id, user.user_id)
    assert league is not None
    return league


class LeagueImport(BaseModel):
    espn_league_id: str
    my_slot: int = Field(default=1, ge=1)
    name: str | None = None
    autodraft_count: int = Field(default=0, ge=0)


@router.post("/import/espn")
def import_espn_league(request: Request, body: LeagueImport, user: CurrentUser) -> dict:
    """Read a league's real settings from ESPN rather than asking the user to
    retype them. Roster shape drives replacement level, so a transcription slip
    here mis-prices every player at that position."""
    settings = request.app.state.settings
    if settings.auth == "google" and user.email != settings.owner_email:
        # The import signs in to ESPN with the operator's own cookies, so it
        # would read private leagues as the operator, whoever asked.
        raise HTTPException(
            403,
            "ESPN import is limited to the site owner - it signs in to ESPN with "
            "their account. Enter your league's settings by hand instead.",
        )
    store = request.app.state.snapshot_store
    try:
        dataset, _ = store.get(
            espn_league,
            {
                "season": settings.season,
                "league_id": body.espn_league_id,
                # Credentials come from the environment, never from the caller.
                "espn_s2": settings.espn_s2,
                "swid": settings.espn_swid,
            },
        )
    except Exception as exc:
        raise HTTPException(
            502,
            "Could not read that league from ESPN. If it is private, set "
            "DRAFTKIT_ESPN_S2 and DRAFTKIT_ESPN_SWID in your .env.",
        ) from exc

    found = dataset.rows[0]
    if body.my_slot > found["num_teams"]:
        raise HTTPException(
            422, f"my_slot {body.my_slot} exceeds the league's {found['num_teams']} teams"
        )
    draft = LeagueCreate(
        name=body.name or found["league_name"],
        platform="espn",
        num_teams=found["num_teams"],
        my_slot=body.my_slot,
        rounds=found["rounds"],
        scoring=found["scoring_preset"],
        scoring_overrides={"rec": found["reception_points"]},
        roster=RosterSlots(**found["roster"]),
        autodraft_count=body.autodraft_count,
    )
    conn = request.app.state.db
    league_id = repo.create_league(
        conn,
        draft.to_config(),
        scoring_preset=draft.scoring,
        rounds=draft.rounds,
        user_id=user.user_id,
    )
    league = repo.get_league(conn, league_id, user.user_id)
    assert league is not None
    return league


@router.get("")
def list_leagues(request: Request, user: CurrentUser) -> list[dict]:
    return repo.list_leagues(request.app.state.db, user.user_id)


@router.get("/{league_id}")
def get_league(request: Request, league_id: int, user: CurrentUser) -> dict:
    league = repo.get_league(request.app.state.db, league_id, user.user_id)
    if league is None:
        raise HTTPException(404, "league not found")
    return league

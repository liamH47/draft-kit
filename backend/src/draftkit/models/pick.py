from pydantic import BaseModel

PickSource = str  # "manual" | "sleeper" | "extension"


class Pick(BaseModel):
    """One normalized pick. Every producer — the manual UI, the Sleeper poller,
    a future browser extension — creates exactly this shape, which is what
    makes them interchangeable."""

    id: int
    session_id: int
    seq: int
    overall_no: int
    round_no: int
    slot: int
    player_id: str
    is_mine: bool
    source: PickSource
    undone: bool = False

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration. The only place env vars are read.

    Every path the app writes lives under data_dir so hosting later is just
    "mount a volume at DRAFTKIT_DATA_DIR".
    """

    model_config = SettingsConfigDict(env_prefix="DRAFTKIT_", env_file=".env", extra="ignore")

    # Resolved to an absolute path below: a relative default silently means
    # "wherever this process was launched from", which is how a user ends up
    # with two databases and wonders where their tags went.
    data_dir: Path = Path("data")
    static_dir: Path | None = None  # set in prod to the built frontend dist/
    cors_origins: list[str] = []  # dev only; prod is same-origin
    season: int = 2026  # NFL season for projections/ADP
    # Pin every source read to disk. Set this during a live draft so a lapsed
    # TTL can never turn a board refresh into a blocking network fetch.
    offline: bool = False
    # Private ESPN leagues need the two cookies your browser already holds.
    # Put them in .env; they are credentials, so they never appear in a request
    # body, a response, or a log line.
    espn_s2: str | None = None
    espn_swid: str | None = None

    @field_validator("data_dir")
    @classmethod
    def _absolute(cls, value: Path) -> Path:
        return value.expanduser().resolve()

    @property
    def db_path(self) -> Path:
        return self.data_dir / "app.db"

    @property
    def snapshots_dir(self) -> Path:
        return self.data_dir / "snapshots"


def get_settings() -> Settings:
    return Settings()

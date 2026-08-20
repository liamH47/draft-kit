from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration. The only place env vars are read.

    Every path the app writes lives under data_dir so hosting later is just
    "mount a volume at DRAFTKIT_DATA_DIR".
    """

    model_config = SettingsConfigDict(env_prefix="DRAFTKIT_", env_file=".env", extra="ignore")

    data_dir: Path = Path("data")
    static_dir: Path | None = None  # set in prod to the built frontend dist/
    cors_origins: list[str] = []  # dev only; prod is same-origin
    season: int = 2026  # NFL season for projections/ADP
    # Pin every source read to disk. Set this during a live draft so a lapsed
    # TTL can never turn a board refresh into a blocking network fetch.
    offline: bool = False

    @property
    def db_path(self) -> Path:
        return self.data_dir / "app.db"

    @property
    def snapshots_dir(self) -> Path:
        return self.data_dir / "snapshots"


def get_settings() -> Settings:
    return Settings()

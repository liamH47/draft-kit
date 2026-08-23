from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


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
    # Hosting. Off by default: the local install answers every request as the
    # single user "local", with no cookies involved. Set DRAFTKIT_AUTH=google
    # (plus the fields below) to require a Google sign-in instead.
    auth: Literal["off", "google"] = "off"
    google_client_id: str | None = None
    google_client_secret: str | None = None
    secret_key: str | None = None  # signs session cookies; any long random string
    # Who may sign in, comma-separated. An email Google verified but this list
    # does not name is turned away by name — nobody gets in by accident.
    allowed_emails: Annotated[list[str], NoDecode] = []
    # ESPN league import transacts with ESPN as the operator (the cookies
    # above), so in google mode only this email may use it.
    owner_email: str | None = None
    # Where the site lives, e.g. https://draftkit.fly.dev — the OAuth redirect
    # URI derives from it, and its scheme decides the cookies' Secure flag.
    public_url: str | None = None

    @field_validator("data_dir")
    @classmethod
    def _absolute(cls, value: Path) -> Path:
        return value.expanduser().resolve()

    @field_validator("allowed_emails", mode="before")
    @classmethod
    def _split_emails(cls, value: str | list[str]) -> list[str]:
        """Env vars arrive as one comma-separated string; code passes lists."""
        items = value.split(",") if isinstance(value, str) else value
        return [item.strip().lower() for item in items if item.strip()]

    @field_validator("owner_email")
    @classmethod
    def _lower_owner(cls, value: str | None) -> str | None:
        return value.lower() if value else value

    @model_validator(mode="after")
    def _google_needs_its_config(self) -> Self:
        """Refuse to boot half-configured rather than failing at first login,
        naming exactly what is missing."""
        if self.auth != "google":
            return self
        required = {
            "DRAFTKIT_GOOGLE_CLIENT_ID": self.google_client_id,
            "DRAFTKIT_GOOGLE_CLIENT_SECRET": self.google_client_secret,
            "DRAFTKIT_SECRET_KEY": self.secret_key,
            "DRAFTKIT_PUBLIC_URL": self.public_url,
            "DRAFTKIT_ALLOWED_EMAILS": ",".join(self.allowed_emails),
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ValueError(f"DRAFTKIT_AUTH=google requires: {', '.join(missing)}")
        return self

    @property
    def db_path(self) -> Path:
        return self.data_dir / "app.db"

    @property
    def snapshots_dir(self) -> Path:
        return self.data_dir / "snapshots"

    @property
    def redirect_uri(self) -> str:
        """Only meaningful in google mode, where public_url is guaranteed."""
        return f"{(self.public_url or '').rstrip('/')}/auth/google/callback"

    def user_dir(self, user_id: str) -> Path:
        """Where a user's mirror files live. The local install keeps its
        files at the top of data_dir, exactly where they have always been."""
        return self.data_dir if user_id == "local" else self.data_dir / "users" / user_id


def get_settings() -> Settings:
    return Settings()

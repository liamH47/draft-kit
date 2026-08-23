"""The auth settings: half-configured google mode must refuse to boot."""

from typing import Any

import pytest
from pydantic import ValidationError

from draftkit.config import Settings

GOOGLE: dict[str, Any] = {
    "auth": "google",
    "google_client_id": "cid",
    "google_client_secret": "csec",
    "secret_key": "s3cret",
    "allowed_emails": ["a@x.com"],
    "public_url": "https://dk.test",
}


def test_auth_is_off_by_default(tmp_path):
    settings = Settings(data_dir=tmp_path)
    assert settings.auth == "off"
    assert settings.allowed_emails == []


def test_a_fully_configured_google_mode_boots(tmp_path):
    settings = Settings(data_dir=tmp_path, **GOOGLE)
    assert settings.redirect_uri == "https://dk.test/auth/google/callback"


def test_a_trailing_slash_does_not_double_up_in_the_redirect(tmp_path):
    settings = Settings(data_dir=tmp_path, **{**GOOGLE, "public_url": "https://dk.test/"})
    assert settings.redirect_uri == "https://dk.test/auth/google/callback"


@pytest.mark.parametrize(
    ("missing", "env_name"),
    [
        ("google_client_id", "DRAFTKIT_GOOGLE_CLIENT_ID"),
        ("google_client_secret", "DRAFTKIT_GOOGLE_CLIENT_SECRET"),
        ("secret_key", "DRAFTKIT_SECRET_KEY"),
        ("public_url", "DRAFTKIT_PUBLIC_URL"),
        ("allowed_emails", "DRAFTKIT_ALLOWED_EMAILS"),
    ],
)
def test_google_mode_names_what_is_missing_at_boot(tmp_path, missing, env_name):
    """The failure happens at process start, naming the env var — never at the
    first login attempt on draft night."""
    config = {**GOOGLE, missing: [] if missing == "allowed_emails" else None}
    with pytest.raises(ValidationError, match=env_name):
        Settings(data_dir=tmp_path, **config)


def test_emails_arrive_as_one_comma_separated_env_string(tmp_path):
    settings = Settings(data_dir=tmp_path, **{**GOOGLE, "allowed_emails": " A@X.com, b@y.com ,,"})
    assert settings.allowed_emails == ["a@x.com", "b@y.com"]


def test_emails_passed_as_a_list_are_normalized_too(tmp_path):
    settings = Settings(data_dir=tmp_path, **{**GOOGLE, "allowed_emails": ["A@X.com ", ""]})
    assert settings.allowed_emails == ["a@x.com"]


def test_owner_email_is_stored_lowercased_and_may_be_absent(tmp_path):
    settings = Settings(data_dir=tmp_path, **{**GOOGLE, "owner_email": "Liam@Gmail.com"})
    assert settings.owner_email == "liam@gmail.com"
    assert Settings(data_dir=tmp_path).owner_email is None


def test_each_user_gets_a_directory_and_local_keeps_the_old_one(tmp_path):
    settings = Settings(data_dir=tmp_path)
    assert settings.user_dir("local") == settings.data_dir
    assert settings.user_dir("111") == settings.data_dir / "users" / "111"

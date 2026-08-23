"""The Google OAuth code exchange, kept apart from the routes so the HTTP
call has an injectable transport and the parsing is plain functions.

The id_token's signature is deliberately NOT verified against Google's JWKS:
this is a confidential-client exchange, so the token arrives directly from
Google's token endpoint over TLS and the transport authenticates the issuer.
A JWKS fetch would add a network call — a new failure mode — for no gain.
"""

import base64
import json
from urllib.parse import urlencode

import httpx

from draftkit.auth.session import SessionUser

AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"


class ExchangeError(Exception):
    """The sign-in could not be completed against Google."""


def authorize_url(client_id: str, redirect_uri: str, state: str) -> str:
    query = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
        }
    )
    return f"{AUTHORIZE_URL}?{query}"


def _jwt_claims(id_token: str) -> dict:
    parts = id_token.split(".")
    if len(parts) != 3:
        raise ExchangeError("Google's id_token is not a JWT")
    try:
        claims = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4)))
    except ValueError as exc:
        raise ExchangeError("Google's id_token payload would not decode") from exc
    if not isinstance(claims, dict):
        raise ExchangeError("Google's id_token payload is not a claims object")
    return claims


def exchange_code(
    code: str,
    *,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    transport: httpx.BaseTransport | None = None,
) -> SessionUser:
    """Trade the authorization code for an identity, or raise ExchangeError."""
    with httpx.Client(transport=transport, timeout=10.0) as client:
        resp = client.post(
            TOKEN_URL,
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
    if resp.status_code != 200:
        raise ExchangeError(f"Google refused the code exchange (HTTP {resp.status_code})")
    try:
        body = resp.json()
    except ValueError as exc:
        raise ExchangeError("Google's token response was not JSON") from exc
    id_token = body.get("id_token") if isinstance(body, dict) else None
    if not id_token:
        raise ExchangeError("Google's token response held no id_token")
    claims = _jwt_claims(str(id_token))
    sub, email = claims.get("sub"), claims.get("email")
    if not sub or not email:
        raise ExchangeError("Google's id_token named no subject or email")
    return SessionUser(
        user_id=str(sub),
        email=str(email).lower(),
        name=str(claims.get("name") or ""),
        picture=str(claims.get("picture") or ""),
    )

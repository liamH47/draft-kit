"""Sign-in with Google, and the /api/me identity the header shows.

In google mode every data route requires the signed session cookie the
callback sets; without it the API answers 401 and the frontend walks the
user to /login. With auth off (the default, and every local install) the
dependency answers "local" and none of these routes matter.
"""

import secrets
from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from draftkit.auth.google import ExchangeError, authorize_url
from draftkit.auth.session import (
    COOKIE_NAME,
    MAX_AGE_SECONDS,
    SessionUser,
    sign_session,
    verify_session,
)
from draftkit.db import repo

router = APIRouter()

STATE_COOKIE = "dk_oauth_state"


def current_user(request: Request) -> SessionUser:
    """Who is asking. Auth off — the local user, exactly as before hosting
    existed. Auth on — the verified cookie, or the 401 the frontend turns
    into a walk to /login."""
    settings = request.app.state.settings
    if settings.auth != "google":
        return SessionUser(user_id="local", email="")
    token = request.cookies.get(COOKIE_NAME)
    user = verify_session(settings.secret_key, token) if token else None
    if user is None:
        raise HTTPException(401, "not signed in")
    return user


CurrentUser = Annotated[SessionUser, Depends(current_user)]


def _require_google(request: Request):
    settings = request.app.state.settings
    if settings.auth != "google":
        raise HTTPException(404, "sign-in is not enabled on this install")
    return settings


def _secure(settings) -> bool:
    """Secure cookies iff the site is https. Hardcoding True would make the
    browser silently drop the cookie on a plain-http localhost test run —
    a login loop with nothing in the network tab to explain it."""
    return (settings.public_url or "").startswith("https://")


@router.get("/auth/google/login")
def login(request: Request) -> RedirectResponse:
    settings = _require_google(request)
    state = secrets.token_urlsafe(16)
    response = RedirectResponse(
        authorize_url(settings.google_client_id, settings.redirect_uri, state)
    )
    response.set_cookie(
        STATE_COOKIE,
        state,
        max_age=600,
        httponly=True,
        samesite="lax",
        secure=_secure(settings),
        path="/auth",
    )
    return response


@router.get("/auth/google/callback")
def callback(request: Request, code: str | None = None, state: str | None = None):
    settings = _require_google(request)
    expected = request.cookies.get(STATE_COOKIE)
    if not state or not expected or state != expected:
        raise HTTPException(400, "sign-in state mismatch — start again from /login")
    if not code:
        raise HTTPException(400, "Google sent no authorization code — start again from /login")
    try:
        user: SessionUser = request.app.state.token_exchanger(code)
    except ExchangeError as exc:
        raise HTTPException(502, f"Google sign-in failed: {exc}") from exc

    if user.email not in settings.allowed_emails:
        # Verified by Google, but not invited. No cookie; the login page
        # explains rather than a bare 403.
        response = RedirectResponse("/login?error=denied", status_code=302)
        response.delete_cookie(STATE_COOKIE, path="/auth")
        return response

    repo.upsert_user(
        request.app.state.db,
        google_sub=user.user_id,
        email=user.email,
        name=user.name,
        picture=user.picture,
    )
    response = RedirectResponse("/", status_code=302)
    response.set_cookie(
        COOKIE_NAME,
        sign_session(settings.secret_key, user),
        max_age=MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=_secure(settings),
        path="/",
    )
    response.delete_cookie(STATE_COOKIE, path="/auth")
    return response


@router.post("/auth/logout")
def logout() -> JSONResponse:
    response = JSONResponse({"ok": True})
    response.delete_cookie(COOKIE_NAME, path="/")
    return response


@router.get("/api/me")
def me(request: Request) -> dict:
    """Always 200: a 401 here plus the client's 401-goes-to-login rule would
    loop on the login page itself."""
    settings = request.app.state.settings
    if settings.auth != "google":
        return {"auth": "off", "user": asdict(SessionUser(user_id="local", email=""))}
    token = request.cookies.get(COOKIE_NAME)
    user = verify_session(settings.secret_key, token) if token else None
    return {"auth": "google", "user": asdict(user) if user else None}

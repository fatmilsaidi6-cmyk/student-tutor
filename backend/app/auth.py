"""OAuth sign-in (Google / GitHub) with a signed, cookie-based session.

We only need to know *who* is calling; per the privacy design, homework and
history stay in the browser, so there is no database and no server-side user
record. The session cookie stores the public profile returned by the provider.

The access gate (`require_access`) allows a request when any of these holds:
- an `API_KEY` is configured and the request presents it, or
- the caller has a signed-in session (when OAuth is configured), or
- neither API_KEY nor OAuth is configured (open, local use).
"""

from __future__ import annotations

import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import RedirectResponse

from .config import settings

router = APIRouter(prefix="/api/auth", tags=["auth"])

GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO = "https://openidconnect.googleapis.com/v1/userinfo"

GITHUB_AUTH = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN = "https://github.com/login/oauth/access_token"
GITHUB_USER = "https://api.github.com/user"
GITHUB_EMAILS = "https://api.github.com/user/emails"

TIMEOUT = 15.0


# --------------------------------------------------------------------------- #
# Access gate
# --------------------------------------------------------------------------- #
def _valid_api_key(x_api_key: str | None, authorization: str | None) -> bool:
    if not settings.auth_enabled:
        return False
    provided = x_api_key
    if not provided and authorization and authorization.lower().startswith("bearer "):
        provided = authorization[7:].strip()
    return bool(provided) and secrets.compare_digest(provided, settings.api_key)


def require_access(
    request: Request,
    x_api_key: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> None:
    if _valid_api_key(x_api_key, authorization):
        return
    if settings.oauth_enabled and request.session.get("user"):
        return
    if not settings.auth_enabled and not settings.oauth_enabled:
        return  # open mode
    raise HTTPException(401, "Authentication required. Please sign in.")


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
def _base_url(request: Request) -> str:
    if settings.public_base_url:
        return settings.public_base_url.rstrip("/")
    return str(request.base_url).rstrip("/")


def _redirect_uri(request: Request, provider: str) -> str:
    return f"{_base_url(request)}/api/auth/callback/{provider}"


@router.get("/me")
def me(request: Request) -> dict:
    return {
        "user": request.session.get("user"),
        "oauth_providers": settings.oauth_providers,
    }


@router.get("/login/{provider}")
def login(provider: str, request: Request):
    if provider not in settings.oauth_providers:
        raise HTTPException(404, f"Unknown or unconfigured provider: {provider}")

    state = secrets.token_urlsafe(24)
    request.session["oauth_state"] = state
    redirect_uri = _redirect_uri(request, provider)

    if provider == "google":
        params = {
            "client_id": settings.google_client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "prompt": "select_account",
        }
        url = f"{GOOGLE_AUTH}?{urlencode(params)}"
    else:
        params = {
            "client_id": settings.github_client_id,
            "redirect_uri": redirect_uri,
            "scope": "read:user user:email",
            "state": state,
        }
        url = f"{GITHUB_AUTH}?{urlencode(params)}"

    return RedirectResponse(url)


@router.get("/callback/{provider}")
async def callback(
    provider: str,
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    if provider not in settings.oauth_providers:
        raise HTTPException(404, f"Unknown or unconfigured provider: {provider}")
    if error:
        return RedirectResponse(f"/?auth_error={error}")
    expected = request.session.pop("oauth_state", None)
    if not code or not state or not expected or state != expected:
        raise HTTPException(400, "Invalid OAuth state. Please try signing in again.")

    try:
        user = await _exchange_code(provider, code, _redirect_uri(request, provider))
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"Sign-in with {provider} failed: {exc}") from exc

    if not user or not user.get("email"):
        raise HTTPException(400, "Could not read your email from the provider.")

    allowed = settings.allowed_emails_list
    if allowed and user["email"].lower() not in allowed:
        raise HTTPException(403, "This account is not allowed to use this app.")

    request.session["user"] = user
    return RedirectResponse("/")


@router.post("/logout")
def logout(request: Request) -> dict:
    request.session.pop("user", None)
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Provider calls
# --------------------------------------------------------------------------- #
async def _exchange_code(provider: str, code: str, redirect_uri: str) -> dict | None:
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        if provider == "google":
            token_resp = await client.post(
                GOOGLE_TOKEN,
                data={
                    "code": code,
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            token_resp.raise_for_status()
            access_token = token_resp.json().get("access_token")
            if not access_token:
                return None
            info = await client.get(
                GOOGLE_USERINFO,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            info.raise_for_status()
            data = info.json()
            return {
                "provider": "google",
                "id": str(data.get("sub", "")),
                "email": data.get("email"),
                "name": data.get("name") or data.get("email"),
                "picture": data.get("picture"),
            }

        # GitHub
        token_resp = await client.post(
            GITHUB_TOKEN,
            data={
                "code": code,
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "redirect_uri": redirect_uri,
            },
            headers={"Accept": "application/json"},
        )
        token_resp.raise_for_status()
        access_token = token_resp.json().get("access_token")
        if not access_token:
            return None
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github+json",
        }
        info = await client.get(GITHUB_USER, headers=headers)
        info.raise_for_status()
        data = info.json()
        email = data.get("email")
        if not email:
            emails = await client.get(GITHUB_EMAILS, headers=headers)
            if emails.status_code == 200:
                primary = [e for e in emails.json() if e.get("primary") and e.get("verified")]
                pick = primary[0] if primary else next(
                    (e for e in emails.json() if e.get("verified")), None
                )
                if pick:
                    email = pick.get("email")
        return {
            "provider": "github",
            "id": str(data.get("id", "")),
            "email": email,
            "name": data.get("name") or data.get("login"),
            "picture": data.get("avatar_url"),
        }

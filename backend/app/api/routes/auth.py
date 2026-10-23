import hmac
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Literal
from urllib.parse import urlencode, urlsplit

import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.config import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    ALGORITHM,
    COOKIE_SAMESITE,
    COOKIE_SECURE,
    FRONTEND_URL,
    GITHUB_CLIENT_ID,
    GITHUB_CLIENT_SECRET,
    GITHUB_REDIRECT_URI,
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    GOOGLE_REDIRECT_URI,
    REMEMBER_TOKEN_EXPIRE_DAYS,
    SECRET_KEY,
)
from app.core.security import create_access_token, decode_access_token, hash_password, needs_password_rehash, verify_password
from app.database import get_db
from app.models import User
from app.schemas import LoginResponse, UserCreate, UserLogin, UserPublic

router = APIRouter(prefix="/api", tags=["authentication"])
logger = logging.getLogger(__name__)
COOKIE_NAME = "renttrace_session"
OAUTH_STATE_COOKIE = "renttrace_oauth_state"
OAuthProvider = Literal["google", "github"]

OAUTH_CONFIG = {
    "google": {
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "scopes": ["openid", "email", "profile"],
    },
    "github": {
        "client_id": GITHUB_CLIENT_ID,
        "client_secret": GITHUB_CLIENT_SECRET,
        "redirect_uri": GITHUB_REDIRECT_URI,
        "authorize_url": "https://github.com/login/oauth/authorize",
        "token_url": "https://github.com/login/oauth/access_token",
        "scopes": ["read:user", "user:email"],
    },
}


def public_user(user: User) -> dict:
    return UserPublic.model_validate(user).model_dump(mode="json")


def set_session_cookie(response: Response, token: str, remember_me: bool) -> None:
    max_age = REMEMBER_TOKEN_EXPIRE_DAYS * 24 * 60 * 60 if remember_me else ACCESS_TOKEN_EXPIRE_MINUTES * 60
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=max_age,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        path="/",
    )


def oauth_redirect(error: str | None = None) -> RedirectResponse:
    url = f"{FRONTEND_URL}/"
    if error:
        url = f"{url}?oauth_error={error}"
    response = RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(
        key=OAUTH_STATE_COOKIE,
        path="/",
        secure=COOKIE_SECURE,
        httponly=True,
        samesite=COOKIE_SAMESITE,
    )
    return response


@router.get("/auth/oauth/google/config-status")
def oauth_config_status(request: Request) -> dict[str, bool]:
    google_config = OAUTH_CONFIG["google"]
    redirect_uri = urlsplit(google_config["redirect_uri"])
    frontend_url = urlsplit(FRONTEND_URL)
    callback_path = str(request.app.url_path_for("oauth_callback", provider="google"))
    return {
        "google_client_id_present": bool(google_config["client_id"].strip()),
        "google_client_secret_present": bool(google_config["client_secret"].strip()),
        "google_redirect_uri_present": bool(google_config["redirect_uri"].strip()),
        "google_redirect_uri_matches_callback": (
            redirect_uri.scheme in {"http", "https"}
            and bool(redirect_uri.netloc)
            and redirect_uri.path == callback_path
        ),
        "google_redirect_uri_matches_frontend": (
            redirect_uri.scheme == frontend_url.scheme
            and redirect_uri.netloc.lower() == frontend_url.netloc.lower()
        ),
    }


async def fetch_oauth_identity(
    provider: OAuthProvider,
    code: str,
) -> tuple[str, str]:
    config = OAUTH_CONFIG[provider]
    async with httpx.AsyncClient(timeout=10.0) as client:
        token_response = await client.post(
            config["token_url"],
            data={
                "client_id": config["client_id"],
                "client_secret": config["client_secret"],
                "code": code,
                "redirect_uri": config["redirect_uri"],
                "grant_type": "authorization_code",
            },
            headers={"Accept": "application/json"},
        )
        token_response.raise_for_status()
        token_data = token_response.json()
        if not isinstance(token_data, dict) or not isinstance(token_data.get("access_token"), str):
            raise ValueError("OAuth provider did not return an access token.")

        headers = {"Authorization": f"Bearer {token_data['access_token']}"}
        if provider == "google":
            profile_response = await client.get(
                "https://openidconnect.googleapis.com/v1/userinfo",
                headers=headers,
            )
            profile_response.raise_for_status()
            profile = profile_response.json()
            if (
                not isinstance(profile, dict)
                or profile.get("email_verified") is not True
                or not isinstance(profile.get("email"), str)
                or not isinstance(profile.get("name"), str)
                or not profile["email"].strip()
                or not profile["name"].strip()
            ):
                raise ValueError("Google did not return a verified email and account name.")
            return profile["name"].strip(), profile["email"].strip().lower()

        profile_response = await client.get("https://api.github.com/user", headers=headers)
        profile_response.raise_for_status()
        profile = profile_response.json()
        if not isinstance(profile, dict):
            raise ValueError("GitHub returned an invalid user profile.")

        emails_response = await client.get("https://api.github.com/user/emails", headers=headers)
        emails_response.raise_for_status()
        emails = emails_response.json()
        if not isinstance(emails, list):
            raise ValueError("GitHub returned an invalid email list.")
        primary_email = next(
            (
                item["email"].strip().lower()
                for item in emails
                if isinstance(item, dict)
                and item.get("primary") is True
                and item.get("verified") is True
                and isinstance(item.get("email"), str)
            ),
            None,
        )
        if not primary_email:
            raise ValueError("GitHub did not return a verified primary email.")
        name = profile.get("name") or profile.get("login")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("GitHub did not return an account name.")
        return name.strip(), primary_email


@router.get("/auth/oauth/{provider}")
def start_oauth(
    provider: OAuthProvider,
    remember_me: bool = Query(default=False),
) -> Response:
    if provider not in OAUTH_CONFIG:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown sign-in provider.")

    provider_config = OAUTH_CONFIG[provider]
    if not provider_config["client_id"].strip() or not provider_config["client_secret"].strip():
        return oauth_redirect("not_configured")

    state = jwt.encode(
        {
            "provider": provider,
            "remember_me": remember_me,
            "nonce": secrets.token_urlsafe(32),
            "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
        },
        SECRET_KEY,
        algorithm=ALGORITHM,
    )
    authorization_url = f"{provider_config['authorize_url']}?{urlencode({
        'client_id': provider_config['client_id'],
        'redirect_uri': provider_config['redirect_uri'],
        'response_type': 'code',
        'scope': ' '.join(provider_config['scopes']),
        'state': state,
    })}"
    redirect = RedirectResponse(url=authorization_url, status_code=status.HTTP_303_SEE_OTHER)
    redirect.set_cookie(
        key=OAUTH_STATE_COOKIE,
        value=state,
        max_age=600,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        path="/",
    )
    return redirect


@router.get("/auth/oauth/{provider}/callback", name="oauth_callback")
async def oauth_callback(
    provider: OAuthProvider,
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    if provider not in OAUTH_CONFIG:
        return oauth_redirect("failed")
    if error:
        return oauth_redirect("cancelled")

    stored_state = request.cookies.get(OAUTH_STATE_COOKIE, "")
    if not state or not stored_state or not hmac.compare_digest(state, stored_state):
        return oauth_redirect("invalid_state")
    try:
        state_payload = jwt.decode(state, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return oauth_redirect("invalid_state")
    if state_payload.get("provider") != provider or not code:
        return oauth_redirect("invalid_state")

    try:
        name, email = await fetch_oauth_identity(provider, code)
    except (httpx.HTTPError, ValueError, TypeError):
        logger.exception("OAuth identity verification failed for provider %s.", provider)
        return oauth_redirect("failed")

    user = db.scalar(select(User).where(func.lower(User.email) == email))
    if user is None:
        user = User(
            name=name[:150],
            email=email,
            password_hash=hash_password(secrets.token_urlsafe(48)),
        )
        db.add(user)
        try:
            db.commit()
            db.refresh(user)
        except IntegrityError:
            db.rollback()
            user = db.scalar(select(User).where(func.lower(User.email) == email))
            if user is None:
                logger.exception("OAuth user creation failed for provider %s.", provider)
                return oauth_redirect("failed")

    if not user.is_active:
        return oauth_redirect("failed")

    remember_me = state_payload.get("remember_me") is True
    duration = (
        timedelta(days=REMEMBER_TOKEN_EXPIRE_DAYS)
        if remember_me
        else timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    response = oauth_redirect()
    set_session_cookie(response, create_access_token(user.id, duration), remember_me)
    return response


@router.post("/signup", status_code=status.HTTP_201_CREATED)
def signup(payload: UserCreate, db: Session = Depends(get_db)) -> dict:
    email = str(payload.email).strip().lower()
    existing = db.scalar(select(User.id).where(func.lower(User.email) == email))
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists.")

    user = User(name=payload.name.strip(), email=email, password_hash=hash_password(payload.password))
    db.add(user)
    try:
        db.commit()
        db.refresh(user)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists.") from exc
    return {"message": "User created successfully", "user": public_user(user)}


@router.post("/login", status_code=status.HTTP_200_OK, response_model=LoginResponse)
def login(payload: UserLogin, response: Response, db: Session = Depends(get_db)) -> LoginResponse:
    email = str(payload.email).strip().lower()
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")

    if needs_password_rehash(user.password_hash):
        user.password_hash = hash_password(payload.password)
        db.commit()

    duration = timedelta(days=REMEMBER_TOKEN_EXPIRE_DAYS) if payload.remember_me else timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    token = create_access_token(user.id, duration)
    set_session_cookie(response, token, payload.remember_me)
    return LoginResponse(message="Login successful", user=public_user(user))


@router.get("/me")
def current_user(user: User = Depends(get_current_user)) -> dict:
    return {"user": public_user(user)}


@router.get("/session")
def session_status(request: Request, db: Session = Depends(get_db)) -> dict:
    user_id = decode_access_token(request.cookies.get(COOKIE_NAME, ""))
    user = db.get(User, user_id) if user_id is not None else None
    if user is None or not user.is_active:
        return {"authenticated": False, "user": None}
    return {"authenticated": True, "user": public_user(user)}


@router.post("/logout")
def logout(response: Response, request: Request) -> dict:
    response.delete_cookie(
        key=COOKIE_NAME,
        path="/",
        secure=COOKIE_SECURE,
        httponly=True,
        samesite=COOKIE_SAMESITE,
    )
    return {"message": "Logged out successfully"}

"""
GIGA Shorty - Minimal FastAPI-powered URL shortener.

This module defines a small URL shortener service backed by a MySQL database.
It supports:

* Random and custom short codes
* Optional expiration (TTL)
* Visit counting
* Token-based admin protection for link creation
"""

import os
import secrets
import string
import hashlib
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, AsyncGenerator

from fastapi import FastAPI, HTTPException, Depends, Header, Request
from fastapi.responses import RedirectResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from pydantic import BaseModel, AnyHttpUrl
from sqlalchemy import Column, Integer, String, DateTime, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.engine import URL as DBUrl


# ============================================================================
# Configuration
# ============================================================================

MYSQL_USER = os.getenv("MYSQL_USER", "shortener_user")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD")
MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_DB = os.getenv("MYSQL_DB", "shortener")

TOKENS_ENV = os.getenv("ADMIN_TOKENS", "")

ADMIN_TOKENS = { t.strip() for t in TOKENS_ENV.split(",") if t.strip() }
if not ADMIN_TOKENS:
    raise RuntimeError("ADMIN_TOKENS is not configured; set it in the environment.")

DATABASE_URL = DBUrl.create(
    "mysql+aiomysql",
    username=MYSQL_USER,
    password=MYSQL_PASSWORD,
    host=MYSQL_HOST,
    port=MYSQL_PORT,
    database=MYSQL_DB,
)


# ============================================================================
# Database setup
# ============================================================================

engine = create_async_engine(DATABASE_URL, echo=False, future=True)

AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)

Base = declarative_base()


# ============================================================================
# ORM models
# ============================================================================

class URL(Base):
    """URL mapping model.

    Represents a single shortened URL, including optional expiration
    and a basic visit counter.

    Attributes
    ----------
    id : int
        Primary key.
    short_code : str
        Unique short code used in the path (e.g., ``/abc123``).
    target_url : str
        Original URL to redirect to.
    created_by_token : str or None
        SHA-256 hash of the admin token used to create this URL.
    expires_at : datetime or None
        UTC expiration timestamp. ``None`` means the URL never expires.
    visit_count : int
        Number of successful redirects performed for this URL.
    """

    __tablename__ = "urls"

    id = Column(Integer, primary_key=True, index=True)
    short_code = Column(String(10), unique=True, index=True, nullable=False)
    target_url = Column(String(2048), nullable=False)
    created_by_token = Column(String(64), nullable=True, index=True)
    expires_at = Column(DateTime, nullable=True, index=True)
    visit_count = Column(Integer, nullable=False, default=0)


class TTL(str, Enum):
    """Time-to-live choices for shortened URLs."""

    permanent = "permanent"
    hour = "1h"
    day = "1d"
    week = "1w"


# ============================================================================
# Utility functions
# ============================================================================

def hash_token(token: str) -> str:
    """Hash an admin token using SHA-256.

    Parameters
    ----------
    token : str
        Raw admin token as provided by the user or environment.

    Returns
    -------
    str
        Hex-encoded SHA-256 digest of the token.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def compute_expires_at(ttl: TTL) -> Optional[datetime]:
    """Compute expiration timestamp for a given TTL.

    Parameters
    ----------
    ttl : TTL
        Time-to-live value, e.g. ``TTL.hour`` or ``TTL.permanent``.

    Returns
    -------
    datetime or None
        UTC timestamp at which the URL should expire, or ``None`` if
        the URL should never expire.
    """
    now = datetime.utcnow()
    if ttl == TTL.hour:
        return now + timedelta(hours=1)
    if ttl == TTL.day:
        return now + timedelta(days=1)
    if ttl == TTL.week:
        return now + timedelta(weeks=1)
    return None  # permanent


def generate_code(length: int = 6) -> str:
    """Generate a random short code.

    Parameters
    ----------
    length : int, optional
        Length of the generated code, by default 6.

    Returns
    -------
    str
        Random alphanumeric code.
    """
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


# ============================================================================
# Pydantic schemas
# ============================================================================

class URLCreate(BaseModel):
    """Schema for creating a random short URL."""

    target_url: AnyHttpUrl
    ttl: TTL = TTL.permanent


class CustomURLCreate(BaseModel):
    """Schema for creating a short URL with a custom code."""

    target_url: AnyHttpUrl
    custom_code: str
    ttl: TTL = TTL.permanent


# ============================================================================
# Dependency injection
# ============================================================================

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session.

    Returns
    -------
    AsyncGenerator[AsyncSession, None]
        Async SQLAlchemy session generator for use with FastAPI dependencies.
    """
    async with AsyncSessionLocal() as session:
        yield session


async def require_admin(x_admin_token: str = Header(None)) -> str:
    """Validate the admin token from the request headers.

    Parameters
    ----------
    x_admin_token : str, optional
        Value of the ``X-Admin-Token`` header.

    Returns
    -------
    str
        The validated token.

    Raises
    ------
    HTTPException
        If the token is missing or not in the allowed set.
    """
    if not x_admin_token or x_admin_token not in ADMIN_TOKENS:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing admin token",
        )
    return x_admin_token


# ============================================================================
# FastAPI app and routes
# ============================================================================

app = FastAPI(title="GIGA Shorty")

# Static files (for favicon, etc.)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.on_event("startup")
async def on_startup() -> None:
    """Create database tables on startup if they do not exist."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@app.get("/", response_class=HTMLResponse)
async def ui() -> FileResponse:
    """Serve the minimal HTML UI.

    Returns
    -------
    FileResponse
        HTML page containing the Tailwind-based user interface for
        creating short URLs.
    """
    return FileResponse("static/index.html")


@app.post("/shorten")
async def create_short_url(
    data: URLCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_token: str = Depends(require_admin),
):
    """Create a short URL with a random code.

    Parameters
    ----------
    data : URLCreate
        Payload containing the target URL and TTL.
    request : Request
        Incoming FastAPI request instance.
    db : AsyncSession
        Database session dependency.
    admin_token : str
        Validated admin token from the headers.

    Returns
    -------
    dict
        JSON response with the short URL and its expiration timestamp.
    """
    # generate a unique code
    while True:
        code = generate_code()
        result = await db.execute(select(URL).where(URL.short_code == code))
        if not result.scalars().first():
            break

    expires_at = compute_expires_at(data.ttl)

    new_url = URL(
        short_code=code,
        target_url=str(data.target_url),
        created_by_token=hash_token(admin_token),
        expires_at=expires_at,
    )
    db.add(new_url)
    await db.commit()
    await db.refresh(new_url)

    base_url = str(request.base_url).rstrip("/")
    short_url = f"{base_url}/{new_url.short_code}"

    return {
        "short_url": short_url,
        "expires_at": new_url.expires_at.isoformat() if new_url.expires_at else None,
    }


@app.post("/custom_shorten")
async def create_custom_short_url(
    data: CustomURLCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_token: str = Depends(require_admin),
):
    """Create a short URL with a custom code.

    Parameters
    ----------
    data : CustomURLCreate
        Payload containing the target URL, desired custom code, and TTL.
    request : Request
        Incoming FastAPI request instance.
    db : AsyncSession
        Database session dependency.
    admin_token : str
        Validated admin token from the headers.

    Returns
    -------
    dict
        JSON response with the short URL and its expiration timestamp.

    Raises
    ------
    HTTPException
        If the custom code is invalid or already in use.
    """
    code = data.custom_code.strip()

    if not code or len(code) > 10:
        raise HTTPException(
            status_code=400,
            detail="Custom code must be between 1 and 10 characters.",
        )

    allowed_chars = string.ascii_letters + string.digits + "-_"
    if any(c not in allowed_chars for c in code):
        raise HTTPException(
            status_code=400,
            detail="Custom code can only contain letters, numbers, '-' and '_'.",
        )

    existing = await db.execute(select(URL).where(URL.short_code == code))
    if existing.scalars().first():
        raise HTTPException(
            status_code=409,
            detail="This short code is already in use.",
        )

    expires_at = compute_expires_at(data.ttl)

    new_url = URL(
        short_code=code,
        target_url=str(data.target_url),
        created_by_token=hash_token(admin_token),
        expires_at=expires_at,
    )
    db.add(new_url)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="This short code is already in use.",
        )

    await db.refresh(new_url)

    base_url = str(request.base_url).rstrip("/")
    short_url = f"{base_url}/{new_url.short_code}"

    return {
        "short_url": short_url,
        "expires_at": new_url.expires_at.isoformat() if new_url.expires_at else None,
    }


@app.get("/{code}")
async def redirect_to_target(
    code: str,
    db: AsyncSession = Depends(get_db),
):
    """Redirect from a short code to the target URL.

    Parameters
    ----------
    code : str
        Short code segment from the path.
    db : AsyncSession
        Database session dependency.

    Returns
    -------
    RedirectResponse
        HTTP redirect to the target URL.

    Raises
    ------
    HTTPException
        If the short code does not exist or has expired.
    """
    result = await db.execute(select(URL).where(URL.short_code == code))
    url_obj = result.scalars().first()

    if not url_obj:
        raise HTTPException(status_code=404, detail="Short URL not found")

    now = datetime.utcnow()
    if url_obj.expires_at and url_obj.expires_at <= now:
        raise HTTPException(status_code=410, detail="Short URL has expired")

    # increment visit count
    url_obj.visit_count = (url_obj.visit_count or 0) + 1
    await db.commit()

    return RedirectResponse(url_obj.target_url)

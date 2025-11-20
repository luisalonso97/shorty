"""
Shorty - Minimal FastAPI-powered URL shortener.

This module defines a small URL shortener service backed by a MySQL database.
It supports:

* Random and custom short codes
* Optional expiration (TTL)
* Visit counting
* Token-based admin protection for link creation
"""

import string
from datetime import datetime

from fastapi import FastAPI, HTTPException, Depends, Header, Request
from fastapi.responses import RedirectResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import engine, Base, get_db
from models import URL
from schemas import URLCreate, CustomURLCreate
from utils import hash_token, compute_expires_at, generate_code


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
    if not x_admin_token or x_admin_token not in settings.admin_tokens:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing admin token",
        )
    return x_admin_token


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

import os
import secrets
import string
import hashlib
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, Header, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from pydantic import BaseModel, AnyHttpUrl
from sqlalchemy import Column, Integer, String, DateTime, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.engine import URL as DBUrl

MYSQL_USER = os.getenv("MYSQL_USER", "shortener_user")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD")
MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_DB = os.getenv("MYSQL_DB", "shortener")
TOKENS_ENV = os.getenv("ADMIN_TOKENS", "")

ADMIN_TOKENS = {t.strip() for t in TOKENS_ENV.split(",") if t.strip()}

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

engine = create_async_engine(DATABASE_URL, echo=False, future=True)

AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)

Base = declarative_base()

class URL(Base):
    __tablename__ = "urls"

    id = Column(Integer, primary_key=True, index=True)
    short_code = Column(String(10), unique=True, index=True, nullable=False)
    target_url = Column(String(2048), nullable=False)
    created_by_token = Column(String(64), nullable=True, index=True)
    expires_at = Column(DateTime, nullable=True, index=True)
    visit_count = Column(Integer, nullable=False, default=0)

class TTL(str, Enum):
    permanent = "permanent"
    hour = "1h"
    day = "1d"
    week = "1w"


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def compute_expires_at(ttl: TTL) -> Optional[datetime]:
    now = datetime.utcnow()
    if ttl == TTL.hour:
        return now + timedelta(hours=1)
    elif ttl == TTL.day:
        return now + timedelta(days=1)
    elif ttl == TTL.week:
        return now + timedelta(weeks=1)
    else:
        return None  # permanent

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

class URLCreate(BaseModel):
    target_url: AnyHttpUrl
    ttl: TTL = TTL.permanent

class CustomURLCreate(BaseModel):
    target_url: AnyHttpUrl
    custom_code: str
    ttl: TTL = TTL.permanent

def generate_code(length: int = 6) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))

app = FastAPI(title="GIGA Shorty")

app.mount("/static", StaticFiles(directory="static"), name="static")

async def require_admin(x_admin_token: str = Header(None)):
    if not x_admin_token or x_admin_token not in ADMIN_TOKENS:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing admin token",
        )
    return x_admin_token

@app.on_event("startup")
async def on_startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

@app.get("/", response_class=HTMLResponse)
async def ui():
    return """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>Shorty · URL Shortener</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <link rel="icon" type="image/x-icon" href="/static/favicon.ico" />
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="min-h-screen bg-slate-950 text-slate-100">
  <div class="min-h-screen flex items-center justify-center px-4">
    <div class="w-full max-w-lg">
      <div class="text-center mb-6">
        <h1 class="text-3xl font-semibold tracking-tight">🤯 Shorty</h1>
        <p class="text-slate-400 mt-1 text-sm">
          Create short links powered by ME!
        </p>
      </div>

      <div class="bg-slate-900/70 border border-slate-800 rounded-2xl shadow-xl p-6 space-y-5">
        <div class="space-y-1.5">
          <label for="targetUrl" class="block text-sm font-medium text-slate-200">
            Destination URL
          </label>
          <input
            id="targetUrl"
            type="url"
            placeholder="https://example.com/some/long/path"
            class="w-full rounded-xl border border-slate-700 bg-slate-950/70 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500 focus:border-sky-500"
          />
        </div>

        <div class="space-y-1.5">
          <label for="customCode" class="block text-sm font-medium text-slate-200">
            Custom short code <span class="text-slate-500 text-xs">(optional)</span>
          </label>
          <input
            id="customCode"
            type="text"
            placeholder="my-alias (letters, numbers, - and _)"
            class="w-full rounded-xl border border-slate-700 bg-slate-950/70 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500 focus:border-sky-500"
          />
        </div>

        <div class="space-y-1.5">
          <label for="ttl" class="block text-sm font-medium text-slate-200">
            Expiration
          </label>
          <select
            id="ttl"
            class="w-full rounded-xl border border-slate-700 bg-slate-950/70 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500 focus:border-sky-500"
          >
            <option value="1d">1 day</option>
            <option value="1w">1 week</option>
            <option value="permanent">Perpetual</option>
          </select>
        </div>

        <div class="space-y-1.5">
          <label for="adminToken" class="block text-sm font-medium text-slate-200">
            Token
          </label>
          <input
            id="adminToken"
            type="password"
            placeholder="Your secret admin token"
            class="w-full rounded-xl border border-slate-700 bg-slate-950/70 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500 focus:border-sky-500"
          />
        </div>

        <div class="flex gap-3 pt-1">
          <button
            id="btnRandom"
            class="flex-1 rounded-xl bg-sky-500 hover:bg-sky-600 px-3 py-2 text-sm font-medium text-white transition-colors"
          >
            Shorten (random code)
          </button>

          <button
            id="btnCustom"
            class="flex-1 rounded-xl bg-slate-800 hover:bg-slate-700 px-3 py-2 text-sm font-medium text-slate-100 transition-colors"
          >
            Shorten with custom code
          </button>
        </div>

        <div id="message" class="hidden text-sm mt-2"></div>

        <div id="resultBox" class="hidden mt-3 rounded-xl border border-emerald-700 bg-emerald-900/40 px-4 py-3">
          <div class="text-xs uppercase tracking-wide text-emerald-300 mb-1">Short URL</div>
          <div class="flex items-center justify-between gap-2">
            <a id="resultLink" href="#" class="break-all text-sm text-emerald-100 underline underline-offset-2"></a>
            <button
              id="copyBtn"
              class="shrink-0 text-xs px-2 py-1 rounded-lg border border-emerald-500/70 text-emerald-100 hover:bg-emerald-500/10"
            >
              Copy
            </button>
          </div>
          <div id="expiryInfo" class="mt-1 text-xs text-emerald-200"></div>
        </div>
      </div>

      <p class="mt-4 text-center text-xs text-slate-600">
        Served from <span class="font-mono">s.lalonso.com</span>
      </p>
    </div>
  </div>
  <script>
    document.addEventListener("DOMContentLoaded", () => {
      const btnRandom = document.getElementById("btnRandom");
      const btnCustom = document.getElementById("btnCustom");
      const targetUrlInput = document.getElementById("targetUrl");
      const customCodeInput = document.getElementById("customCode");
      const adminTokenInput = document.getElementById("adminToken");
      const ttlSelect = document.getElementById("ttl");
      const messageEl = document.getElementById("message");
      const resultBox = document.getElementById("resultBox");
      const resultLink = document.getElementById("resultLink");
      const copyBtn = document.getElementById("copyBtn");
      const expiryInfo = document.getElementById("expiryInfo");

      function showMessage(text, type = "info") {
        messageEl.textContent = text;
        messageEl.classList.remove("hidden", "text-emerald-300", "text-red-400");
        messageEl.classList.add(type === "error" ? "text-red-400" : "text-emerald-300");
      }

      function clearMessage() {
        messageEl.classList.add("hidden");
        messageEl.textContent = "";
      }

      function showResult(shortUrl, expiresAt) {
        resultLink.href = shortUrl;
        resultLink.textContent = shortUrl;

        if (expiresAt) {
          const d = new Date(expiresAt);
          expiryInfo.textContent = "Expires at: " + d.toLocaleString();
        } else {
          expiryInfo.textContent = "Expires: never";
        }

        resultBox.classList.remove("hidden");
      }

      async function copyShortUrl(text) {
        const value = (text || "").trim();
        if (!value) {
          showMessage("There is no short URL to copy yet.", "error");
          return;
        }

        try {
          if (navigator.clipboard && navigator.clipboard.writeText) {
            await navigator.clipboard.writeText(value);
          } else {
            const textarea = document.createElement("textarea");
            textarea.value = value;
            textarea.style.position = "fixed";
            textarea.style.left = "-9999px";
            document.body.appendChild(textarea);
            textarea.focus();
            textarea.select();
            document.execCommand("copy");
            document.body.removeChild(textarea);
          }
          showMessage("Short URL created and copied to clipboard.");
        } catch (e) {
          console.error("Clipboard error:", e);
          showMessage("Short URL created, but could not copy to clipboard.", "error");
        }
      }

      async function callApi({ useCustom }) {
        clearMessage();
        resultBox.classList.add("hidden");

        const targetUrl = targetUrlInput.value.trim();
        const customCode = customCodeInput.value.trim();
        const adminToken = adminTokenInput.value.trim();
        const ttl = ttlSelect.value;

        if (!targetUrl) {
          showMessage("Please enter a destination URL.", "error");
          return;
        }
        if (!adminToken) {
          showMessage("Admin token is required.", "error");
          return;
        }

        let endpoint = "/shorten";
        let body = { target_url: targetUrl, ttl };

        if (useCustom) {
          if (!customCode) {
            showMessage("Please enter a custom code or use the random button.", "error");
            return;
          }
          endpoint = "/custom_shorten";
          body = { target_url: targetUrl, custom_code: customCode, ttl };
        }

        try {
          const res = await fetch(endpoint, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "X-Admin-Token": adminToken,
            },
            body: JSON.stringify(body),
          });

          const data = await res.json().catch(() => ({}));

          if (!res.ok) {
            const errMsg = data.detail || `Error ${res.status}`;
            showMessage(errMsg, "error");
            return;
          }

          let shortUrl = data.short_url;
          if (!shortUrl && body.custom_code) {
            shortUrl = window.location.origin + "/" + body.custom_code;
          }

          const expiresAt = data.expires_at || null;

          if (!shortUrl) {
            showMessage("Short URL created but response was unexpected.", "error");
            console.log("Response:", data);
            return;
          }

          showResult(shortUrl, expiresAt);
          await copyShortUrl(shortUrl);
        } catch (err) {
          console.error("API error:", err);
          showMessage("Network error while contacting the API.", "error");
        }
      }

      btnRandom.addEventListener("click", () => callApi({ useCustom: false }));
      btnCustom.addEventListener("click", () => callApi({ useCustom: true }));

      copyBtn.addEventListener("click", async () => {
        const text = resultLink.textContent;
        await copyShortUrl(text);
      });
    });
  </script>

</body>
</html>
    """


@app.post("/shorten")
async def create_short_url(
    data: URLCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_token: str = Depends(require_admin),
):
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
async def redirect_to_target(code: str, db: AsyncSession = Depends(get_db)):
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

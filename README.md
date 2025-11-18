# Shorty · Personal URL Shortener

Shorty is a tiny FastAPI-based URL shortener you can host on your own server.

It gives you:

- Random and **custom** short codes
- **Expiring links** (1 day, 1 week, or permanent)
- A **simple web UI** with Tailwind
- **Admin-token–protected** link creation
- MySQL storage with a **visit counter** per link

Designed to run nicely on a small VPS.

---

## Features

- 🔐 **Protected API** – Only requests with a valid `X-Admin-Token` can create links.
- 🎯 **Random or custom codes**
  - `/shorten` generates a random code.
  - `/custom_shorten` lets you specify your own code (e.g. `/home-wifi`).
- ⏱ **Time-to-live (TTL)**
  - `permanent`
  - `1d` – 1 day
  - `1w` – 1 week
  - (API also supports `1h`, even if the UI doesn’t show it.)
- 📈 **Visit counting**
  - Each successful redirect increments `visit_count` in the database.
- 🧱 **MySQL backend**
  - Async SQLAlchemy + `aiomysql`.
- 🖥 **Single-file app**
  - One `main.py` with everything: models, API, and HTML UI.

---

## Tech Stack

- **Python** 3.10+ (tested with 3.12)
- **FastAPI** + Uvicorn
- **SQLAlchemy** (async)
- **MySQL** 8.x (or compatible)
- **Tailwind CSS** via CDN (for the UI)

---

## Database Schema

Table: `urls`

- `id` (INT, PK)
- `short_code` (VARCHAR(10), unique, indexed)
- `target_url` (VARCHAR(2048))
- `created_by_token` (VARCHAR(64), nullable, indexed) – SHA-256 of admin token used
- `expires_at` (DATETIME, nullable, indexed, UTC)
- `visit_count` (INT, default 0)

Tables are created automatically on app startup.

---

## Setup

### 1. Clone and install dependencies

```bash
python -m venv venv
source venv/bin/activate

pip install requirements.txt
```

### 2. Create the MySQL database and user

From your server:

```bash
sudo mysql
```

Then in the MySQL shell:

```sql
CREATE DATABASE shortener CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE USER 'shortener_user'@'localhost' IDENTIFIED BY 'your_password_here';
GRANT ALL PRIVILEGES ON shortener.* TO 'shortener_user'@'localhost';
FLUSH PRIVILEGES;
EXIT;
```

Adjust username/password/host as needed.

### 3. Configure environment variables

The app reads configuration from environment variables:

* `MYSQL_USER` – DB username (default: `shortener_user`)
* `MYSQL_PASSWORD` – DB password **(required)**
* `MYSQL_HOST` – DB host (default: `127.0.0.1`)
* `MYSQL_PORT` – DB port (default: `3306`)
* `MYSQL_DB` – DB name (default: `shortener`)
* `ADMIN_TOKENS` – comma-separated list of admin tokens (at least one required)

Example (bash):

```bash
export MYSQL_USER="shortener_user"
export MYSQL_PASSWORD="your_password_here"
export MYSQL_HOST="127.0.0.1"
export MYSQL_PORT="3306"
export MYSQL_DB="shortener"
export ADMIN_TOKENS="my-super-secret-token,another-token"
```

If `ADMIN_TOKENS` is not set, the app will fail to start with a clear error.

---

## Running Locally

```bash
uvicorn main:app --reload
```

Then open:

* UI: [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
* Docs (auto-generated): [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

On first run, the app will automatically create the `urls` table in the configured database.

---

## API Usage

All write endpoints require the header:

```http
X-Admin-Token: <one-of-your-ADMIN_TOKENS>
```

### 1. Create a random short URL

`POST /shorten`

**Request body:**

```json
{
  "target_url": "https://example.com/some/long/path",
  "ttl": "1d"
}
```

`ttl` options:

* `"permanent"`
* `"1h"`
* `"1d"`
* `"1w"`

**Example `curl`:**

```bash
curl -X POST http://127.0.0.1:8000/shorten \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: my-super-secret-token" \
  -d '{"target_url": "https://example.com", "ttl": "1d"}'
```

**Response:**

```json
{
  "short_url": "http://127.0.0.1:8000/Ab3xYz",
  "expires_at": "2025-11-18T01:23:45.000000"
}
```

`expires_at` is in UTC; `null` means permanent.

---

### 2. Create a custom short URL

`POST /custom_shorten`

**Request body:**

```json
{
  "target_url": "https://example.com",
  "custom_code": "home-wifi",
  "ttl": "1w"
}
```

Rules for `custom_code`:

* Length: 1–10 characters
* Allowed characters: letters, digits, `-`, `_`

**Example `curl`:**

```bash
curl -X POST http://127.0.0.1:8000/custom_shorten \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: my-super-secret-token" \
  -d '{"target_url": "https://example.com", "custom_code": "home-wifi", "ttl": "1w"}'
```

**Response:**

```json
{
  "short_url": "http://127.0.0.1:8000/home-wifi",
  "expires_at": "2025-11-25T01:23:45.000000"
}
```

Possible errors:

* `400` – invalid code (wrong length or characters)
* `409` – custom code already in use

---

### 3. Redirect from a short code

`GET /{code}`

Examples:

* `GET /Ab3xYz`
* `GET /home-wifi`

Behavior:

* If the code exists and is **not expired**:

  * Returns an HTTP redirect (`RedirectResponse`, status 307 by default) to `target_url`.
  * Increments `visit_count` for that record.
* If not found:

  * `404 {"detail": "Short URL not found"}`
* If expired:

  * `410 {"detail": "Short URL has expired"}`

---

## Web UI

When you open `/` in a browser (e.g. `http://127.0.0.1:8000/`), you get a small Tailwind-based interface:

* Enter:

  * Destination URL
  * Optional custom code
  * TTL (1 day, 1 week, or permanent)
  * Your admin token
* Click:

  * **Shorten (random code)** or
  * **Shorten with custom code**
* On success:

  * The short URL is displayed
  * The expiration is shown
  * The short URL is automatically copied to your clipboard (if allowed by the browser)
  * There’s also a **Copy** button as a backup

The UI is generated inline in `ui()` and uses Tailwind via CDN.

---

## Optional: Cleanup of Expired Links

Expired URLs are simply not usable anymore (HTTP 410), but they stay in the DB until you clean them up.

You can periodically delete expired rows with a script like this:

**`/usr/local/bin/cleanup_shortener_urls.sh`**

```bash
#!/usr/bin/env bash
# Cleanup expired URLs in the shortener DB (timestamps stored in UTC)

mysql shortener << 'EOF'
DELETE FROM urls
WHERE expires_at IS NOT NULL
  AND expires_at < UTC_TIMESTAMP();
EOF
```

Make it executable:

```bash
sudo chmod +x /usr/local/bin/cleanup_shortener_urls.sh
```

Add a cron job (as root) to run it daily at 03:30:

```bash
sudo crontab -e
```

Add:

```cron
30 3 * * * /usr/local/bin/cleanup_shortener_urls.sh >/var/log/shortener_cleanup.log 2>&1
```

---

## Production Deployment (High Level)

A typical production setup:

1. **Systemd service** to run Uvicorn:

   ```ini
   [Unit]
   Description=FastAPI URL Shortener
   After=network.target

   [Service]
   WorkingDirectory=/var/www/py-shortener
   Environment="PATH=/var/www/py-shortener/venv/bin"
   Environment="MYSQL_USER=shortener_user"
   Environment="MYSQL_PASSWORD=your_password_here"
   Environment="MYSQL_HOST=127.0.0.1"
   Environment="MYSQL_PORT=3306"
   Environment="MYSQL_DB=shortener"
   Environment="ADMIN_TOKENS=my-super-secret-token"
   ExecStart=/var/www/py-shortener/venv/bin/uvicorn main:app --host 127.0.0.1 --port 8001
   Restart=always
   User=www-data
   Group=www-data

   [Install]
   WantedBy=multi-user.target
   ```

2. **Nginx** as a reverse proxy for your domain (e.g. `s.lalonso.com`) → forwards to `127.0.0.1:8001`.

3. **Let’s Encrypt** (via `certbot`) for HTTPS.

---

## License

```text
MIT License

Copyright (c) 2025 Luis Alonso
```

---

## Notes / Ideas for Future

* Simple admin dashboard showing:

  * List of URLs
  * `visit_count`
  * Expiration status
* Rate limiting or IP allowlist on write endpoints
* Optional password-protected links
* Export of stats as CSV

import hashlib
import secrets
import string
from datetime import datetime, timedelta
from typing import Optional
from models import TTL

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
    return None # permanent


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

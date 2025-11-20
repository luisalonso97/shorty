from sqlalchemy import Column, Integer, String, DateTime
from enum import Enum
from database import Base

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

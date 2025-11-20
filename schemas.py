from pydantic import BaseModel, AnyHttpUrl
from models import TTL

class URLCreate(BaseModel):
    """Schema for creating a random short URL."""

    target_url: AnyHttpUrl
    ttl: TTL = TTL.permanent


class CustomURLCreate(BaseModel):
    """Schema for creating a short URL with a custom code."""

    target_url: AnyHttpUrl
    custom_code: str
    ttl: TTL = TTL.permanent

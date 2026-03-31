"""API key authentication for protected endpoints."""

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from database.config import get_settings

_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: str | None = Security(_API_KEY_HEADER)) -> str:
    """Validate the X-API-Key header against the configured API_KEY.

    Raises HTTP 403 if the key is missing or does not match.
    """
    settings = get_settings()
    if not api_key or api_key != settings.api_key:
        raise HTTPException(status_code=403, detail="Invalid or missing API key.")
    return api_key

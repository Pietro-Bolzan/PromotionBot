import re
import secrets

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from app.core.config import settings

# Declared as a security scheme rather than a plain Header so the requirement
# shows up in the OpenAPI document: /docs renders an Authorize button and sends
# the header on every "Try it out". auto_error=False keeps the 401 responses
# below as the single source of the error messages.
api_key_header = APIKeyHeader(name="X-API-KEY", auto_error=False)

# Telegram puts the bot token in the URL path, so any HTTP error message about
# a Telegram call carries it. Matched by shape too, in case the token in the
# message is not the one currently configured.
_TELEGRAM_TOKEN_IN_URL = re.compile(r"/bot[^/\s]+/")


def validate_api_key(api_key: str | None = Security(api_key_header)) -> None:
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key",
        )

    # Compared as bytes: secrets.compare_digest() raises TypeError for str
    # arguments holding non-ASCII characters, which would turn a bad header into
    # a 500 on an authentication route. Encoding keeps it constant-time.
    if not secrets.compare_digest(
        api_key.encode("utf-8"),
        settings.app_api_key.encode("utf-8"),
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )


def mask_secrets(text: str) -> str:
    """Remove configured secrets from text bound for storage or logs."""
    for secret in (
        settings.telegram_bot_token,
        settings.openai_api_key,
        settings.app_api_key,
    ):
        if secret:
            text = text.replace(secret, "***")

    return _TELEGRAM_TOKEN_IN_URL.sub("/bot***/", text)

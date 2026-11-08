from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """The body of every error the API returns."""

    error_code: str
    message: str
    request_id: str | None
    details: list | None = None

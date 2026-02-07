"""API response schemas and error handling per contracts/api.md."""

from typing import Any

from pydantic import BaseModel


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any]


class ErrorResponse(BaseModel):
    error: ErrorDetail


# Error codes per contracts/api.md
SESSION_NOT_FOUND = "SESSION_NOT_FOUND"
PHOTO_NOT_FOUND = "PHOTO_NOT_FOUND"
INVALID_FILE_TYPE = "INVALID_FILE_TYPE"
FILE_TOO_LARGE = "FILE_TOO_LARGE"
INSUFFICIENT_PHOTOS = "INSUFFICIENT_PHOTOS"
MARKERS_NOT_DETECTED = "MARKERS_NOT_DETECTED"
SCAN_PARSE_ERROR = "SCAN_PARSE_ERROR"
INSUFFICIENT_MARKERS = "INSUFFICIENT_MARKERS"
UNAUTHORIZED = "UNAUTHORIZED"
RATE_LIMITED = "RATE_LIMITED"
INVALID_LANDMARK = "INVALID_LANDMARK"
ANALYSIS_IN_PROGRESS = "ANALYSIS_IN_PROGRESS"
ANALYSIS_NOT_COMPLETE = "ANALYSIS_NOT_COMPLETE"
ALIGNMENT_NOT_READY = "ALIGNMENT_NOT_READY"
ALIGNMENT_IN_PROGRESS = "ALIGNMENT_IN_PROGRESS"
EXPORT_NOT_READY = "EXPORT_NOT_READY"


def make_error(code: str, message: str, **details: Any) -> dict[str, Any]:
    """Build a standard error response dict."""
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details,
        }
    }

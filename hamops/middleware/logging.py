"""Structured logging utilities and middleware for FastAPI."""

import json
import logging
import time
import uuid
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


LOG = logging.getLogger("hamops")
if not LOG.hasHandlers():
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    handler.setFormatter(formatter)
    LOG.addHandler(handler)
LOG.setLevel(logging.INFO)


def log_info(event: str, **kwargs: object) -> None:
    """Log an informational event as structured JSON."""
    log = {"level": "info", "event": event, **kwargs}
    LOG.info(json.dumps(log, default=str))


def log_warning(event: str, **kwargs: object) -> None:
    """Log a warning event as structured JSON."""
    log = {"level": "warning", "event": event, **kwargs}
    LOG.warning(json.dumps(log, default=str))


def log_error(event: str, **kwargs: object) -> None:
    """Log an error event as structured JSON."""
    log = {"level": "error", "event": event, **kwargs}
    LOG.error(json.dumps(log, default=str))


def _redact_headers(headers: dict) -> dict:
    """Redact sensitive headers such as authorization tokens."""
    redacted = {}
    for k, v in headers.items():
        if k.lower() in ("authorization", "x-api-key"):
            redacted[k] = "<redacted>"
        else:
            redacted[k] = v
    return redacted


class RequestLogMiddleware(BaseHTTPMiddleware):
    """Structured HTTP request logging middleware."""

    def __init__(self, app, max_body: int = 2048) -> None:
        """Initialize the middleware."""
        super().__init__(app)
        self.max_body = max_body

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Log the request and response in structured JSON format."""
        rid = request.headers.get("x-request-id", str(uuid.uuid4()))
        start = time.time()

        # Read body safely for POST/PUT/PATCH and restore stream for downstream
        body_preview = ""
        if request.method in {"POST", "PUT", "PATCH"}:
            raw = await request.body()
            if raw:
                try:
                    body_preview = raw[: self.max_body].decode(
                        "utf-8", errors="replace"
                    )
                except Exception:
                    body_preview = "<non-text-body>"

            async def receive() -> dict:
                return {"type": "http.request", "body": raw, "more_body": False}

            request._receive = receive  # Starlette internal, OK in middleware

        response = await call_next(request)

        dur_ms = int((time.time() - start) * 1000)
        log_info(
            "http_request",
            request_id=rid,
            method=request.method,
            path=request.url.path,
            query=dict(request.query_params),
            headers=_redact_headers(dict(request.headers)),
            body_preview=body_preview,
            status=response.status_code,
            duration_ms=dur_ms,
        )
        response.headers["x-request-id"] = rid
        return response

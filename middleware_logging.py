import json, time, uuid, logging
from typing import Callable
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

LOG = logging.getLogger("hamops")

def _redact_headers(headers: dict) -> dict:
    redacted = {}
    for k, v in headers.items():
        if k.lower() in ("authorization", "x-api-key"):
            redacted[k] = "<redacted>"
        else:
            redacted[k] = v
    return redacted

class RequestLogMiddleware(BaseHTTPMiddleware):
    """Logs method, path, query, limited body, status, and duration (ms)."""

    def __init__(self, app, max_body=2048):
        super().__init__(app)
        self.max_body = max_body

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        rid = request.headers.get("x-request-id", str(uuid.uuid4()))
        start = time.time()

        # Read body safely for POST/PUT/PATCH and restore stream for downstream
        body_preview = ""
        if request.method in {"POST", "PUT", "PATCH"}:
            raw = await request.body()
            if raw:
                try:
                    body_preview = raw[: self.max_body].decode("utf-8", errors="replace")
                except Exception:
                    body_preview = "<non-text-body>"
            # restore stream so FastAPI can read again
            async def receive():
                return {"type": "http.request", "body": raw, "more_body": False}
            request._receive = receive  # Starlette internal, OK in middleware

        # Call downstream
        response = await call_next(request)

        dur_ms = int((time.time() - start) * 1000)
        log = {
            "event": "http_request",
            "request_id": rid,
            "method": request.method,
            "path": request.url.path,
            "query": dict(request.query_params),
            "headers": _redact_headers(dict(request.headers)),
            "body_preview": body_preview,
            "status": response.status_code,
            "duration_ms": dur_ms,
        }
        LOG.info(json.dumps(log, default=str))
        response.headers["x-request-id"] = rid
        return response

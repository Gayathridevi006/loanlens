import json
import logging
import os
import time
import uuid

from fastapi import Request
from prometheus_client import Counter, Histogram

REQUESTS = Counter("loanlens_http_requests_total", "HTTP requests", ["method", "path", "status"])
LATENCY = Histogram("loanlens_http_request_seconds", "HTTP request latency", ["method", "path"])


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps({
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%SZ"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        })


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), handlers=[handler], force=True)


async def request_metrics(request: Request, call_next):
    started = time.perf_counter()
    request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
    response = await call_next(request)
    route = request.scope.get("route")
    path = getattr(route, "path", request.url.path)
    elapsed = time.perf_counter() - started
    REQUESTS.labels(request.method, path, response.status_code).inc()
    LATENCY.labels(request.method, path).observe(elapsed)
    response.headers["x-request-id"] = request_id
    logging.getLogger("loanlens.http").info(
        "%s %s status=%s duration_ms=%.1f request_id=%s",
        request.method, path, response.status_code, elapsed * 1000, request_id,
    )
    return response

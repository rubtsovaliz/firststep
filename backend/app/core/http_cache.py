"""HTTP cache policy for read-only API responses."""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

API_CACHE_CONTROL = "no-store, no-cache, must-revalidate"


class ApiNoStoreMiddleware(BaseHTTPMiddleware):
    """Apply Cache-Control: no-store to all /api/* responses."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = API_CACHE_CONTROL
            response.headers["Pragma"] = "no-cache"
        return response

import base64
import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.config import settings


class BasicAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not _has_valid_credentials(request.headers.get("Authorization")):
            return Response(
                status_code=401,
                headers={"WWW-Authenticate": 'Basic realm="Dashboard"'},
            )
        return await call_next(request)


def _has_valid_credentials(authorization_header: str | None) -> bool:
    if not authorization_header or not authorization_header.startswith("Basic "):
        return False
    encoded = authorization_header[len("Basic "):]
    try:
        decoded = base64.b64decode(encoded).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return False
    username, _, password = decoded.partition(":")
    return secrets.compare_digest(username, settings.dashboard_user) and secrets.compare_digest(
        password, settings.dashboard_password
    )

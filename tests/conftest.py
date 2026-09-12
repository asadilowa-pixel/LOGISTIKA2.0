import base64

import pytest

from app.config import settings


@pytest.fixture()
def basic_auth_headers() -> dict[str, str]:
    """Installed starlette's TestClient has no `auth=` constructor kwarg, so
    build the Basic Authorization header directly instead."""
    credentials = base64.b64encode(
        f"{settings.dashboard_user}:{settings.dashboard_password}".encode()
    ).decode()
    return {"Authorization": f"Basic {credentials}"}

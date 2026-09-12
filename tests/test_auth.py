from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.config as config_module


def _make_app():
    from app.auth import BasicAuthMiddleware

    test_app = FastAPI()
    test_app.add_middleware(BasicAuthMiddleware)

    @test_app.get("/ping")
    def ping():
        return {"ok": True}

    return test_app


def test_no_credentials_returns_401(monkeypatch):
    monkeypatch.setattr(config_module.settings, "dashboard_user", "admin")
    monkeypatch.setattr(config_module.settings, "dashboard_password", "secret")
    client = TestClient(_make_app())

    resp = client.get("/ping")

    assert resp.status_code == 401
    assert resp.headers["WWW-Authenticate"].startswith("Basic")


def test_wrong_password_returns_401(monkeypatch):
    monkeypatch.setattr(config_module.settings, "dashboard_user", "admin")
    monkeypatch.setattr(config_module.settings, "dashboard_password", "secret")
    client = TestClient(_make_app())

    resp = client.get("/ping", auth=("admin", "wrong"))

    assert resp.status_code == 401


def test_wrong_username_returns_401(monkeypatch):
    monkeypatch.setattr(config_module.settings, "dashboard_user", "admin")
    monkeypatch.setattr(config_module.settings, "dashboard_password", "secret")
    client = TestClient(_make_app())

    resp = client.get("/ping", auth=("someone-else", "secret"))

    assert resp.status_code == 401


def test_correct_credentials_returns_200(monkeypatch):
    monkeypatch.setattr(config_module.settings, "dashboard_user", "admin")
    monkeypatch.setattr(config_module.settings, "dashboard_password", "secret")
    client = TestClient(_make_app())

    resp = client.get("/ping", auth=("admin", "secret"))

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_malformed_authorization_header_returns_401(monkeypatch):
    monkeypatch.setattr(config_module.settings, "dashboard_user", "admin")
    monkeypatch.setattr(config_module.settings, "dashboard_password", "secret")
    client = TestClient(_make_app())

    resp = client.get("/ping", headers={"Authorization": "Bearer not-basic-auth"})

    assert resp.status_code == 401


def test_dashboard_page_requires_auth():
    from app.main import app as real_app

    client = TestClient(real_app)

    resp = client.get("/")

    assert resp.status_code == 401


def test_dashboard_page_served_with_auth(basic_auth_headers):
    from app.main import app as real_app

    client = TestClient(real_app, headers=basic_auth_headers)

    resp = client.get("/")

    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]

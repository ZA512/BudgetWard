import pytest
from fastapi.testclient import TestClient

from budgetward.api import app_factory
from budgetward.config import read_secret
from budgetward.woob_connector import BankConfiguration


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    for name in (
        "BUDGETWARD_ADMIN_TOKEN",
        "BUDGETWARD_BANK_LOGIN",
        "BUDGETWARD_BANK_PASSWORD",
    ):
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv(name + "_FILE", raising=False)
    monkeypatch.setenv("BUDGETWARD_DEMO", "false")


def test_environment_authenticates_and_configures_bank(tmp_path, monkeypatch):
    token = "test-admin-token-with-at-least-24-characters"
    monkeypatch.setenv("BUDGETWARD_DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.setenv("BUDGETWARD_ADMIN_TOKEN", token)
    monkeypatch.setenv("BUDGETWARD_BANK_WEBSITE", "www.ca-paris.fr")
    monkeypatch.setenv("BUDGETWARD_BANK_LOGIN", "00123456789")
    monkeypatch.setenv("BUDGETWARD_BANK_PASSWORD", " 00123$# ")
    configuration = BankConfiguration.from_environment()
    assert configuration.credentials_configured
    assert configuration.login == "00123456789"
    assert configuration.password == " 00123$# "
    with TestClient(app_factory()) as client:
        assert client.get("/api/export").status_code == 401
        assert client.post("/api/session", json={"token": "wrong"}).status_code == 401
        assert client.post("/api/session", json={"token": token}).status_code == 200
        response = client.get("/api/bank/status")
        assert response.json()["credentials_configured"] is True
        assert configuration.login not in response.text
        assert configuration.password not in response.text
        assert token not in response.text


@pytest.mark.parametrize("token", [None, "", "short"])
def test_missing_or_short_environment_token_refuses_startup(tmp_path, monkeypatch, token):
    monkeypatch.setenv("BUDGETWARD_DB_PATH", str(tmp_path / "app.db"))
    if token is not None:
        monkeypatch.setenv("BUDGETWARD_ADMIN_TOKEN", token)
    with pytest.raises(RuntimeError, match="BUDGETWARD_ADMIN_TOKEN"):
        app_factory()


@pytest.mark.parametrize(
    "name", ["BUDGETWARD_ADMIN_TOKEN", "BUDGETWARD_BANK_LOGIN", "BUDGETWARD_BANK_PASSWORD"]
)
def test_legacy_file_fallback_and_environment_precedence(tmp_path, monkeypatch, name):
    path = tmp_path / "secret"
    path.write_text("legacy-value\n", encoding="utf-8")
    monkeypatch.setenv(name + "_FILE", str(path))
    assert read_secret(name) == "legacy-value"
    monkeypatch.setenv(name, "environment-value")
    path.unlink()
    assert read_secret(name) == "environment-value"
    monkeypatch.setenv(name, "")
    assert read_secret(name) == ""
    monkeypatch.delenv(name)
    assert read_secret(name) == ""


def test_demo_ignores_admin_secret_files(tmp_path, monkeypatch):
    monkeypatch.setenv("BUDGETWARD_DEMO", "true")
    monkeypatch.setenv("BUDGETWARD_DEMO_DB_PATH", str(tmp_path / "demo.db"))
    monkeypatch.setattr("budgetward.api.read_secret", lambda _: pytest.fail("secret read"))
    with TestClient(app_factory()) as client:
        assert client.get("/api/session").json()["authenticated"] is True

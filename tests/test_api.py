import sqlite3
from contextlib import closing

import pytest
from fastapi.testclient import TestClient

from budgetward.api import create_app


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(str(tmp_path / "demo.db"), demo=True)) as client:
        client.headers["x-csrf-token"] = "demo"
        yield client


def state(client, month="2026-10"):
    response = client.get("/api/forecast", params={"month": month})
    assert response.status_code == 200, response.text
    return response.json()


def tx(client, account=1, amount=-10000, reference=None, day="2026-10-05", operation_date=None):
    response = client.post(
        "/api/transactions",
        json={
            "account_id": account,
            "booking_date": day,
            "operation_date": operation_date,
            "amount_cents": amount,
            "raw_label": "Opération test",
            "provider_id": reference,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["id"]


def classify(client, id, kind, target=None, other=None):
    response = client.put(
        f"/api/transactions/{id}/classification",
        json={
            "kind": kind,
            "target_id": target,
            "other_account_id": other,
        },
    )
    assert response.status_code == 200, response.text


def test_demo_matches_prd_example(client):
    data = state(client)
    assert data["charges_cents"] == 232000
    assert data["budgets_cents"] == 186500
    assert data["protected_cents"] == 443500
    assert data["transferable_cents"] == 53500


def test_paid_charge_not_counted_twice_and_anomaly_keeps_rule(client):
    charge = next(c for c in state(client)["charges"] if "EDF" in c["name"])
    id = tx(client, amount=-17200)
    classify(client, id, "CHARGE", charge["id"])
    data = state(client)
    updated = next(c for c in data["charges"] if c["id"] == charge["id"])
    assert updated["remaining_cents"] == 0
    assert updated["amount_cents"] == 16150
    assert data["charges_cents"] == 232000 - 16150
    assert data["balance_cents"] == 497000
    assert len(data["anomalies"]) == 1
    assert data["anomalies"][0]["actual_cents"] == 17200


def test_funding_spending_and_internal_counterpart(client):
    groceries = next(b for b in state(client)["budgets"] if b["name"] == "Courses alimentaires")
    funded_id = tx(client, amount=-27000)
    classify(client, funded_id, "FUNDED", groceries["id"], 2)
    incoming_id = tx(client, account=2, amount=27000)
    classify(client, incoming_id, "INTERNAL", other=1)
    spent_id = tx(client, account=2, amount=-25800)
    classify(client, spent_id, "SPENT", groceries["id"])
    data = state(client)
    budget = next(b for b in data["budgets"] if b["id"] == groceries["id"])
    assert budget["remaining_cents"] == 108000
    assert budget["spent_cents"] == 25800
    assert data["budgets_cents"] == 186500 - 27000
    assert data["balance_cents"] == 497000


def test_reclassification_reverses_previous_effect_without_mutating_transaction(client):
    budget = state(client)["budgets"][0]
    id = tx(client, amount=-5000)
    classify(client, id, "FUNDED", budget["id"], 2)
    assert state(client)["budgets_cents"] == 181500
    classify(client, id, "OTHER")
    data = state(client)
    assert data["budgets_cents"] == 186500
    assert data["transactions"][0]["amount_cents"] == -5000
    assert client.patch(f"/api/transactions/{id}", json={"amount_cents": 1}).status_code == 404


def test_monthly_override_does_not_change_other_months(client):
    budget = next(b for b in state(client)["budgets"] if b["name"] == "Courses alimentaires")
    url = f"/api/plans/2026-10/budgets/{budget['id']}"
    assert client.put(url, json={"count": 3}).status_code == 200
    assert next(b for b in state(client)["budgets"] if b["id"] == budget["id"])["count"] == 3
    assert (
        next(b for b in state(client, "2026-11")["budgets"] if b["id"] == budget["id"])["count"]
        == 4
    )
    assert client.put(url, json={"count": None}).status_code == 200
    assert next(b for b in state(client)["budgets"] if b["id"] == budget["id"])["count"] == 5


def test_revision_retains_historical_month_and_installment_lifecycle(client):
    response = client.post(
        "/api/charges",
        json={
            "name": "Oney",
            "amount_cents": 6450,
            "frequency": "MONTHLY",
            "anchor_date": "2026-10-01",
            "installment_count": 4,
        },
    )
    id = response.json()["id"]
    assert (
        client.post(
            f"/api/charges/{id}/revisions",
            json={"amount_cents": 7000, "effective_from": "2026-11-01"},
        ).status_code
        == 200
    )

    def charge(month):
        return next(c for c in state(client, month)["charges"] if c["id"] == id)

    assert charge("2026-10")["expected_cents"] == 6450
    assert charge("2026-11")["expected_cents"] == 7000
    assert charge("2027-01")["expected_cents"] == 7000
    assert charge("2027-02")["expected_cents"] == 0


def test_duplicates_only_on_provider_id_not_similar_operations(client):
    tx(client, reference="bank-1")
    duplicate = client.post(
        "/api/transactions",
        json={
            "account_id": 1,
            "booking_date": "2026-10-05",
            "amount_cents": -10000,
            "raw_label": "Opération test",
            "provider_id": "bank-1",
        },
    )
    assert duplicate.status_code == 409
    tx(client)
    tx(client)
    assert len(state(client)["transactions"]) == 3


def test_logical_date_moves_spending_to_purchase_month(client):
    budget = state(client)["budgets"][0]
    id = tx(client, account=2, day="2026-10-01", operation_date="2026-09-30", amount=-1000)
    classify(client, id, "SPENT", budget["id"])
    assert next(b for b in state(client)["budgets"] if b["id"] == budget["id"])["spent_cents"] == 0
    assert (
        next(b for b in state(client, "2026-09")["budgets"] if b["id"] == budget["id"])[
            "spent_cents"
        ]
        == 1000
    )


@pytest.mark.parametrize("amount", [1.5, 100.0, "100", True, -1])
def test_money_rejects_float_string_bool_and_negative_budget(client, amount):
    assert (
        client.post(
            "/api/budgets",
            json={
                "name": "Test",
                "amount_cents": amount,
                "frequency": "MONTHLY",
                "anchor_date": "2026-10-01",
            },
        ).status_code
        == 422
    )


def test_incoming_cannot_fund_and_funding_must_leave_charges(client):
    budget = state(client)["budgets"][0]
    for account, amount in [(1, 1000), (2, -1000)]:
        id = tx(client, account=account, amount=amount)
        response = client.put(
            f"/api/transactions/{id}/classification",
            json={
                "kind": "FUNDED",
                "target_id": budget["id"],
                "other_account_id": 3 - account,
            },
        )
        assert response.status_code == 422


def test_backup_is_restorable_and_persistence_survives_restart(client, tmp_path):
    tx(client, amount=-12345)
    path = tmp_path / "restored.db"
    response = client.get("/api/backup")
    assert response.status_code == 200
    path.write_bytes(response.content)
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    with TestClient(create_app(str(path), demo=True)) as restored:
        assert state(restored)["transactions"][0]["amount_cents"] == -12345
        assert len(state(restored)["accounts"]) == 2


def test_real_startup_auth_csrf_empty_state_and_setup(tmp_path):
    token = "a-test-admin-secret-of-more-than-24-characters"
    with TestClient(create_app(str(tmp_path / "real.db"), token)) as client:
        assert client.get("/api/forecast?month=2026-10").status_code == 401
        assert client.get("/api/backup").status_code == 401
        assert client.post("/api/session", json={"token": "wrong"}).status_code == 401
        response = client.post("/api/session", json={"token": token})
        assert response.status_code == 200
        assert "HttpOnly" in response.headers["set-cookie"]
        assert not state(client)["configured"]
        assert client.post("/api/setup", json={}).status_code == 403
        client.headers["x-csrf-token"] = response.json()["csrf"]
        payload = {
            "name": "Charges",
            "balance_cents": 497000,
            "balance_date": "2026-10-01",
            "expenses_name": "Dépenses",
            "expenses_balance_cents": 12345,
        }
        assert client.post("/api/setup", json=payload).status_code == 200
        assert client.post("/api/setup", json=payload).status_code == 409
        assert state(client)["accounts"][1]["balance_cents"] == 12345
        assert state(client)["charges"] == []
        assert client.delete("/api/session").status_code == 200
        assert client.get("/api/export").status_code == 401


def test_unsafe_configuration_refuses_start(tmp_path):
    with pytest.raises(RuntimeError):
        create_app(str(tmp_path / "app.db"), "short")


def test_bad_month_rejected(client):
    assert client.get("/api/forecast?month=2026-13").status_code == 422

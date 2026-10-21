import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing

import pytest
from fastapi.testclient import TestClient

from budgetward.api import create_app
from budgetward.csv_import import money_cents


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(str(tmp_path / "demo.db"), demo=True)) as test_client:
        test_client.headers["x-csrf-token"] = "demo"
        yield test_client


def payload(content, **changes):
    return {
        "account_id": 1,
        "content": content,
        "delimiter": ";",
        "date_format": "%d/%m/%Y",
        "decimal_separator": ",",
        "mapping": {
            "booking_date": "Date",
            "raw_label": "Libellé",
            "amount": "Montant",
            "provider_id": "Référence",
        },
        **changes,
    }


HEADER = "Date;Libellé;Montant;Référence\n"


def preview(client, data):
    response = client.post("/api/import/csv/preview", json=data)
    assert response.status_code == 200, response.text
    return response.json()


def commit(client, data, view=None, decisions=None):
    view = view or preview(client, data)
    return client.post(
        "/api/import/csv/commit",
        json={**data, "preview_token": view["preview_token"], "decisions": decisions or {}},
    )


def test_csv_preview_writes_nothing_then_import_is_atomic_and_idempotent(client):
    data = payload(HEADER + "05/09/2026;EDF;-161,50;bank1\n06/09/2026;Salaire;2000,00;bank2\n")
    view = preview(client, data)
    assert view["counts"] == {"NEW": 2}
    assert client.get("/api/export").json()["transactions"] == []
    result = commit(client, data, view)
    assert result.status_code == 200, result.text
    assert result.json()["imported_count"] == 2
    assert commit(client, data, view).json()["imported_count"] == 0
    exported = client.get("/api/export").json()
    assert len(exported["transactions"]) == 2
    assert exported["accounts"][0]["balance_cents"] == 497000
    assert all(tx["source"] == "CSV" for tx in exported["transactions"])


def test_no_reference_preserves_two_real_identical_payments_and_replays_once(client):
    data = payload(HEADER + "05/09/2026;CHEQUE;-100,00;\n05/09/2026;CHEQUE;-100,00;\n")
    assert commit(client, data).json()["imported_count"] == 2
    assert commit(client, data).json()["already_imported"]
    assert len(client.get("/api/export").json()["transactions"]) == 2
    overlapping = payload(HEADER + "05/09/2026;CHEQUE;-100,00;\n")
    view = preview(client, overlapping)
    assert view["counts"] == {"AMBIGUOUS": 1}
    assert commit(client, overlapping, view).status_code == 422
    assert commit(client, overlapping, view, {"2": "IMPORT"}).json()["imported_count"] == 1
    assert len(client.get("/api/export").json()["transactions"]) == 3


def test_ambiguous_skip_requires_explicit_decision_and_is_receipted(client):
    first = payload(HEADER + "05/09/2026;EDF;-100,00;\n")
    commit(client, first)
    second = payload(HEADER + "05/09/2026;EDF;-100,00;\n\n")
    view = preview(client, second)
    assert view["counts"] == {"AMBIGUOUS": 1}
    response = commit(client, second, view, {"2": "SKIP"})
    assert response.json()["skipped_count"] == 1
    assert commit(client, second).json()["already_imported"]
    assert len(client.get("/api/export").json()["transactions"]) == 1


def test_different_bank_ids_are_distinct_even_with_same_date_amount_and_label(client):
    commit(client, payload(HEADER + "05/09/2026;CHEQUE;-100,00;cheque1\n"))
    new = payload(HEADER + "05/09/2026;CHEQUE;-100,00;cheque2\n")
    assert preview(client, new)["counts"] == {"NEW": 1}
    assert commit(client, new).json()["imported_count"] == 1


@pytest.mark.parametrize(
    ("original_date", "later_date", "expected"),
    [
        ("", "04/09/2026", "AMBIGUOUS"),
        ("04/09/2026", "", "AMBIGUOUS"),
        ("03/09/2026", "04/09/2026", "NEW"),
    ],
)
def test_optional_operation_date_between_sources_requires_decision(
    client, original_date, later_date, expected
):
    mapping = {**payload(HEADER)["mapping"], "operation_date": "Achat"}
    first = payload(
        HEADER.rstrip() + ";Achat\n05/09/2026;EDF;-100,00;;" + original_date + "\n",
        mapping=mapping,
    )
    assert commit(client, first).json()["imported_count"] == 1
    second = payload(
        HEADER.rstrip() + ";Achat\n05/09/2026;EDF;-100,00;provider-bank;" + later_date + "\n",
        mapping=mapping,
    )
    view = preview(client, second)
    assert view["counts"] == {expected: 1}
    if expected == "AMBIGUOUS":
        assert commit(client, second, view).status_code == 422
        assert commit(client, second, view, {"2": "SKIP"}).json()["imported_count"] == 0
        assert len(client.get("/api/export").json()["transactions"]) == 1


def test_conflicting_reference_blocks_entire_import_and_original_is_immutable(client):
    commit(client, payload(HEADER + "05/09/2026;EDF;-100,00;edf1\n"))
    conflict = payload(HEADER + "05/09/2026;EDF;-110,00;edf1\n06/09/2026;Internet;-30,00;new1\n")
    view = preview(client, conflict)
    assert view["counts"] == {"CONFLICT": 1, "NEW": 1}
    assert commit(client, conflict, view).status_code == 422
    txs = client.get("/api/export").json()["transactions"]
    assert len(txs) == 1
    assert txs[0]["amount_cents"] == -10000


def test_duplicate_reference_inside_file_and_conflict_inside_file(client):
    same = payload(HEADER + "05/09/2026;EDF;-100,00;edf1\n05/09/2026;EDF;-100,00;edf1\n")
    assert preview(client, same)["counts"] == {"NEW": 1, "DUPLICATE": 1}
    assert commit(client, same).json()["imported_count"] == 1
    conflict = payload(HEADER + "05/09/2026;Test;-10,00;x\n06/09/2026;Test;-20,00;x\n")
    view = preview(client, conflict)
    assert view["counts"]["CONFLICT"] == 1
    assert commit(client, conflict, view).status_code == 422


def test_stale_preview_rejected_including_another_import_without_bank_reference(client):
    original = payload(HEADER + "05/09/2026;EDF;-100,00;\n")
    view = preview(client, original)
    other_file = payload(HEADER + "05/09/2026;EDF;-100,00;\n\n")
    assert commit(client, other_file).status_code == 200
    assert commit(client, original, view).status_code == 409
    assert preview(client, original)["counts"] == {"AMBIGUOUS": 1}


def test_split_debit_credit_bom_quoted_newline_and_operation_date(client):
    data = payload(
        '\ufeffDate;Texte;Débit;Crédit;Achat\n01/10/2026;"Courses;\nFamille";258,25;;30/09/2026\n',
        mapping={
            "booking_date": "Date",
            "raw_label": "Texte",
            "debit": "Débit",
            "credit": "Crédit",
            "operation_date": "Achat",
        },
    )
    view = preview(client, data)
    assert view["rows"][0]["amount_cents"] == -25825
    assert view["rows"][0]["operation_date"] == "2026-09-30"
    assert commit(client, data, view).status_code == 200


@pytest.mark.parametrize(
    "line",
    [
        "31/02/2026;Test;-100,00;x",
        "05/09/2099;Test;-100,00;x",
        "05/09/2026;Test;1,234;x",
        "05/09/2026;Test;1.50;x",
        "05/09/2026;Test;0;x",
        "05/09/2026;;100;x",
        "05/09/2026;Test;100;x;extra",
    ],
)
def test_invalid_row_prevents_partial_import(client, line):
    data = payload(HEADER + "05/09/2026;Valid;-1,00;valid\n" + line + "\n")
    view = preview(client, data)
    assert view["counts"]["ERROR"] == 1
    assert commit(client, data, view).status_code == 422
    assert client.get("/api/export").json()["transactions"] == []


@pytest.mark.parametrize(
    "value,separator,result",
    [
        ("1 350,27", ",", 135027),
        ("-0.29", ".", -29),
        ("+100,50 €", ",", 10050),
    ],
)
def test_exact_money(value, separator, result):
    assert money_cents(value, separator) == result


def test_mapping_columns_and_limits(client):
    assert client.post(
        "/api/import/csv/columns",
        json={"content": 'Date;"Libellé;banque";Montant\n01/01/2026;Test;100\n'},
    ).json()["headers"] == ["Date", "Libellé;banque", "Montant"]
    data = payload(HEADER + "05/09/2026;Test;100;x\n")
    data["mapping"]["amount"] = "Absent"
    assert client.post("/api/import/csv/preview", json=data).status_code == 422
    too_many = payload(HEADER + "05/09/2026;Test;100;\n" * 5001)
    assert client.post("/api/import/csv/preview", json=too_many).status_code == 422


def historical_import(client):
    data = payload(
        HEADER + "05/07/2026;prlv Énergie;-98,50;energy7\n"
        "05/08/2026;PRLV Energie;-98,50;energy8\n"
        "05/09/2026;PRLV ENERGIE;-105,00;energy9\n"
        "06/08/2026;CHEQUE;-100,00;cheque8\n"
        "06/09/2026;CHEQUE;-100,00;cheque9\n"
    )
    assert commit(client, data).status_code == 200
    return client.get("/api/history?account_id=1").json()


def test_history_monthly_stats_conservative_labels_and_no_automatic_writes(client):
    groups = historical_import(client)["groups"]
    energy = next(g for g in groups if g["normalized_label"] == "PRLV ENERGIE")
    assert energy["frequency"] == "MONTHLY"
    assert energy["last_cents"] == 10500
    assert energy["median_cents"] == 9850
    assert energy["mean_cents"] == 10067
    cheque = next(g for g in groups if g["label"] == "CHEQUE")
    assert cheque["ambiguous"]
    assert cheque["frequency"] is None
    assert not client.get("/api/export").json()["classifications"]


def test_history_validation_links_only_selection_and_older_history_has_no_false_anomaly(client):
    group = next(g for g in historical_import(client)["groups"] if g["frequency"])
    selected = [t["id"] for t in group["transactions"]]
    data = {
        "account_id": 1,
        "key": group["key"],
        "transaction_ids": selected,
        "name": "Énergie",
        "amount_cents": 10500,
        "frequency": "MONTHLY",
        "anchor_date": "2026-10-05",
    }
    result = client.post("/api/history/validate", json=data)
    assert result.status_code == 200, result.text
    id = result.json()["charge_id"]
    october = client.get("/api/forecast?month=2026-10").json()
    assert next(c for c in october["charges"] if c["id"] == id)["remaining_cents"] == 10500
    september = client.get("/api/forecast?month=2026-09").json()
    charge = next(c for c in september["charges"] if c["id"] == id)
    assert charge["status"] == "HISTORICAL"
    assert charge["paid_cents"] == 10500
    assert not september["anomalies"]
    assert client.post("/api/history/validate", json=data).status_code == 409
    assert all(
        g["key"] != group["key"] for g in client.get("/api/history?account_id=1").json()["groups"]
    )


def test_history_dismissal_retains_transactions_and_is_reversible(client):
    group = historical_import(client)["groups"][0]
    url = f"/api/history/{group['key']}/dismissal?account_id=1"
    assert client.put(url).status_code == 200
    assert all(
        g["key"] != group["key"] for g in client.get("/api/history?account_id=1").json()["groups"]
    )
    assert len(client.get("/api/export").json()["transactions"]) == 5
    ignored = client.get("/api/history?account_id=1&include_dismissed=true").json()["groups"]
    assert next(g for g in ignored if g["key"] == group["key"])["dismissed"]
    assert client.delete(url).status_code == 200


def test_history_does_not_merge_cheque_numbers_or_different_accounts(client):
    data = payload(HEADER + "05/07/2026;CHEQUE 123;-100,00;c1\n05/08/2026;CHEQUE 456;-100,00;c2\n")
    commit(client, data)
    other = {**data, "account_id": 2}
    commit(client, other)
    groups = client.get("/api/history?account_id=1").json()["groups"]
    assert len(groups) == 2
    assert all(g["count"] == 1 and g["frequency"] is None for g in groups)


def test_migration_v1_backup_preserves_transactions(tmp_path):
    path = tmp_path / "existing.db"
    with TestClient(create_app(str(path), demo=True)) as original:
        original.headers["x-csrf-token"] = "demo"
        commit(original, payload(HEADER + "05/09/2026;EDF;-100,00;reference1\n"))
    with closing(sqlite3.connect(path)) as db:
        db.executescript(
            "DROP TABLE bank_bindings; DROP TABLE import_batches; "
            "DROP TABLE history_dismissals; PRAGMA user_version=1;"
        )
        db.commit()
    with TestClient(create_app(str(path), demo=True)) as migrated:
        assert len(migrated.get("/api/export").json()["transactions"]) == 1
        assert len(migrated.get("/api/export").json()["accounts"]) == 2
    backups = list((tmp_path / "backups" / "existing.db" / "before-migration").glob("v1-*.db"))
    assert len(backups) == 1
    with closing(sqlite3.connect(backups[0])) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM transactions").fetchone()[0] == 1
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 3


def test_import_and_history_require_authentication_and_csrf(tmp_path):
    with TestClient(
        create_app(str(tmp_path / "real.db"), "test-token-long-enough-for-access")
    ) as c:
        assert c.post("/api/import/csv/preview", json={}).status_code == 401
        assert c.get("/api/history?account_id=1").status_code == 401
        assert c.post("/api/history/validate", json={}).status_code == 401


def test_wrong_month_or_account_cannot_reuse_preview_token(client):
    data = payload(HEADER + "05/09/2026;EDF;-100,00;bank1\n")
    view = preview(client, data)
    assert commit(client, {**data, "account_id": 2}, view).status_code == 409
    changed = payload(HEADER + "06/09/2026;EDF;-100,00;bank1\n")
    assert commit(client, changed, view).status_code == 409


def test_concurrent_same_file_without_references_is_imported_once(client):
    data = payload(HEADER + "05/09/2026;CHEQUE CONCURRENT;-100,00;\n")
    view = preview(client, data)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: commit(client, data, view), range(2)))
    assert all(result.status_code == 200 for result in results)
    assert sum(result.json()["imported_count"] for result in results) == 1
    assert len(client.get("/api/export").json()["transactions"]) == 1


def test_payment_before_rule_start_in_same_month_does_not_consume_new_occurrence(client):
    data = payload(HEADER + "05/10/2026;NOUVELLE CHARGE;-100,00;new-charge1\n")
    assert commit(client, data).status_code == 200
    group = client.get("/api/history?account_id=1").json()["groups"][0]
    result = client.post(
        "/api/history/validate",
        json={
            "account_id": 1,
            "key": group["key"],
            "transaction_ids": [t["id"] for t in group["transactions"]],
            "name": "Nouvelle charge",
            "amount_cents": 10000,
            "frequency": "MONTHLY",
            "anchor_date": "2026-10-20",
        },
    )
    id = result.json()["charge_id"]
    charge = next(
        c for c in client.get("/api/forecast?month=2026-10").json()["charges"] if c["id"] == id
    )
    assert charge["remaining_cents"] == 10000


def test_separate_databases_never_overwrite_each_others_startup_backups(tmp_path):
    with TestClient(create_app(str(tmp_path / "app.db"), demo=True)) as first:
        first.headers["x-csrf-token"] = "demo"
        assert (
            first.put(
                "/api/accounts/1",
                json={"name": "Charges", "balance_cents": 123456, "balance_date": "2026-10-01"},
            ).status_code
            == 200
        )
    with TestClient(create_app(str(tmp_path / "app.db"), demo=True)):
        pass
    with TestClient(create_app(str(tmp_path / "demo.db"), demo=True)):
        pass
    with closing(
        sqlite3.connect(next((tmp_path / "backups" / "app.db").glob("startup-*.db")))
    ) as db:
        assert (
            db.execute("SELECT balance_cents FROM accounts WHERE role='CHARGES'").fetchone()[0]
            == 123456
        )
    with closing(
        sqlite3.connect(next((tmp_path / "backups" / "demo.db").glob("startup-*.db")))
    ) as db:
        assert (
            db.execute("SELECT balance_cents FROM accounts WHERE role='CHARGES'").fetchone()[0]
            == 497000
        )

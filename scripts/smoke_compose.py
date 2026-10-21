"""Vérifie une image avec Compose et des données fictives dans un dossier temporaire."""

import argparse
import http.cookiejar
import json
import os
import secrets
import sqlite3
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from contextlib import closing
from datetime import date
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", help="Image locale déjà construite ; aucun build ni pull.")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    image = args.image or "budgetward:smoke"
    if not args.image:
        subprocess.run(["docker", "build", "-t", image, "."], cwd=root, check=True)
    with tempfile.TemporaryDirectory(prefix="budgetward-smoke-") as directory:
        folder = Path(directory)
        (folder / "data").mkdir()
        token = secrets.token_urlsafe(48)
        token_file = folder / "token"
        token_file.write_text(token, encoding="utf-8")
        token_file.chmod(0o644)
        uid = os.getuid() if hasattr(os, "getuid") else 1000
        gid = os.getgid() if hasattr(os, "getgid") else 1000
        env = {
            **os.environ,
            "BUDGETWARD_IMAGE": image,
            "APPDATA_PATH": (folder / "data").as_posix(),
            "ADMIN_TOKEN_FILE": token_file.as_posix(),
            "PUID": str(uid),
            "PGID": str(gid),
            "BIND_ADDRESS": "127.0.0.1",
            "PORT": "0",
            "BUDGETWARD_SECURE_COOKIE": "false",
            "BUDGETWARD_BANK_WEBSITE": "",
        }
        project = "budgetward-smoke-" + secrets.token_hex(4)

        def compose(*arguments, capture=False):
            return subprocess.run(
                [
                    "docker",
                    "compose",
                    "--env-file",
                    os.devnull,
                    "-f",
                    str(root / "compose.yaml"),
                    "-p",
                    project,
                    *arguments,
                ],
                cwd=root,
                env=env,
                text=True,
                capture_output=capture,
                check=True,
            ).stdout

        base, csrf = "", ""
        opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
        )

        def request(path, body=None):
            req = urllib.request.Request(
                base + path,
                data=json.dumps(body).encode() if body is not None else None,
                headers={"Content-Type": "application/json", "X-CSRF-Token": csrf},
            )
            with opener.open(req, timeout=10) as response:
                if path in {"/", "/api/backup"}:
                    return response.read()
                return json.load(response)

        def wait_ready():
            nonlocal base
            port = compose("port", "budgetward", "8000", capture=True).strip().rsplit(":", 1)[1]
            base = "http://127.0.0.1:" + port
            for _ in range(60):
                try:
                    if request("/health")["status"] == "ok":
                        return
                except (OSError, urllib.error.URLError):
                    time.sleep(0.5)
            raise RuntimeError("Le conteneur ne devient pas disponible.")

        try:
            compose("up", "-d", "--pull", "never")
            wait_ready()
            assert b"BudgetWard" in request("/")
            try:
                request("/api/export")
                raise AssertionError("L'export doit nécessiter une session.")
            except urllib.error.HTTPError as error:
                assert error.code == 401
            csrf = request("/api/session", {"token": token})["csrf"]
            bank_status = request("/api/bank/status")
            assert bank_status["module_installed"] is True
            assert bank_status["credentials_configured"] is False
            assert bank_status["bindings"] == []
            compose(
                "exec",
                "-T",
                "budgetward",
                "python",
                "-c",
                "from woob.core import WoobBase; "
                "w=WoobBase(modules_path='/app/bank_modules'); "
                "assert w.modules_loader.get_or_load_module('cragr'); w.deinit()",
            )
            request(
                "/api/setup",
                {
                    "name": "Charges test",
                    "balance_cents": 100000,
                    "balance_date": date.today().isoformat(),
                    "expenses_name": "Dépenses test",
                    "expenses_balance_cents": 0,
                },
            )
            request(
                "/api/charges",
                {
                    "name": "Facture test",
                    "amount_cents": 10000,
                    "frequency": "MONTHLY",
                    "anchor_date": date.today().replace(day=1).isoformat(),
                },
            )
            month = date.today().strftime("%Y-%m")
            assert request("/api/forecast?month=" + month)["protected_cents"] == 10000

            def prior_month(offset):
                absolute = date.today().year * 12 + date.today().month - 1 - offset
                return date(absolute // 12, absolute % 12 + 1, 1).isoformat()

            csv_data = {
                "account_id": 1,
                "content": "Date;Libelle;Montant;Reference\n"
                + f"{prior_month(2)};ABONNEMENT CSV SMOKE;-35,00;csv-test-1\n"
                + f"{prior_month(1)};ABONNEMENT CSV SMOKE;-35,00;csv-test-2\n",
                "delimiter": ";",
                "date_format": "%Y-%m-%d",
                "decimal_separator": ",",
                "mapping": {
                    "booking_date": "Date",
                    "raw_label": "Libelle",
                    "amount": "Montant",
                    "provider_id": "Reference",
                },
            }
            preview = request("/api/import/csv/preview", csv_data)
            import_data = {**csv_data, "preview_token": preview["preview_token"], "decisions": {}}
            assert request("/api/import/csv/commit", import_data)["imported_count"] == 2
            assert request("/api/import/csv/commit", import_data)["imported_count"] == 0
            group = request("/api/history?account_id=1")["groups"][0]
            assert group["frequency"] == "MONTHLY"
            request(
                "/api/history/validate",
                {
                    "account_id": 1,
                    "key": group["key"],
                    "transaction_ids": [t["id"] for t in group["transactions"]],
                    "name": "Abonnement CSV test",
                    "amount_cents": 3500,
                    "frequency": "MONTHLY",
                    "anchor_date": date.today().replace(day=1).isoformat(),
                },
            )
            assert request("/api/forecast?month=" + month)["protected_cents"] == 13500
            backup = folder / "backup.db"
            backup.write_bytes(request("/api/backup"))
            with closing(sqlite3.connect(backup)) as db:
                assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
                assert db.execute("SELECT count(*) FROM charges").fetchone()[0] == 2
                assert db.execute("SELECT count(*) FROM transactions").fetchone()[0] == 2
                assert db.execute("PRAGMA user_version").fetchone()[0] == 3
            compose("up", "-d", "--force-recreate", "--pull", "never")
            wait_ready()
            csrf = request("/api/session", {"token": token})["csrf"]
            forecast = request("/api/forecast?month=" + month)
            assert forecast["protected_cents"] == 13500
            assert forecast["balance_cents"] == 100000
            assert request("/api/import/csv/commit", import_data)["imported_count"] == 0
            print("Compose OK : module Woob, session, CSV, historique, sauvegarde et persistance.")
        finally:
            compose("down", "--remove-orphans")


if __name__ == "__main__":
    main()

"""Banking secrets stay server-side; each bank access runs in a short-lived worker."""

import importlib.util
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from pydantic import ValidationError

from .config import read_secret
from .connectors import ConnectorAccount, ConnectorTransaction

MESSAGES = {
    "configuration": "Configurer la caisse régionale et les identifiants bancaires sur le serveur.",
    "module": "Le module bancaire n'est pas installé. Recréez le conteneur avec l'image complète.",
    "credentials": "La banque a refusé les identifiants. Vérifiez les secrets du serveur.",
    "action_required": "La banque demande une validation. Ouvrez son site ou son application, "
    "effectuez la validation demandée, puis réessayez ici.",
    "unavailable": "La banque ou son connecteur est indisponible. "
    "Réessayez plus tard ou utilisez le CSV.",
    "timeout": "Le délai de lecture bancaire est dépassé. Aucune opération n'a été importée.",
    "account": "Un compte associé n'est plus disponible. Vérifiez l'accès auprès de la banque.",
    "data": "La lecture contient des données incomplètes ou incompatibles. Rien n'a été importé.",
}


class ConnectorError(Exception):
    def __init__(self, code: str):
        self.code = code if code in MESSAGES else "unavailable"
        super().__init__(MESSAGES[self.code])


@dataclass(frozen=True)
class BankConfiguration:
    website: str = ""
    login: str = field(default="", repr=False)
    password: str = field(default="", repr=False)
    modules_path: Path = Path("bank_modules")

    @classmethod
    def from_environment(cls):
        return cls(
            website=os.getenv("BUDGETWARD_BANK_WEBSITE", "").strip(),
            login=read_secret("BUDGETWARD_BANK_LOGIN"),
            password=read_secret("BUDGETWARD_BANK_PASSWORD"),
            modules_path=Path(os.getenv("BUDGETWARD_BANK_MODULES_PATH", "bank_modules")),
        )

    @property
    def credentials_configured(self):
        return bool(self.website and self.login and self.password)

    @property
    def module_installed(self):
        return (self.modules_path / "cragr" / "module.py").is_file() and bool(
            importlib.util.find_spec("woob")
        )


class WoobConnector:
    def __init__(self, configuration: BankConfiguration):
        self.configuration = configuration
        self.snapshot = None
        self.bounds = None

    def _call(self, operation: str, **arguments):
        config = self.configuration
        if not config.credentials_configured:
            raise ConnectorError("configuration")
        if not config.module_installed:
            raise ConnectorError("module")
        payload = {
            "operation": operation,
            "website": config.website,
            "login": config.login,
            "password": config.password,
            "modules_path": str(config.modules_path.resolve()),
            **arguments,
        }
        try:
            result = subprocess.run(
                [sys.executable, "-m", "budgetward.woob_worker"],
                input=json.dumps(payload),
                text=True,
                capture_output=True,
                timeout=180,
                encoding="utf-8",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                env={
                    key: value
                    for key, value in os.environ.items()
                    if key
                    not in {
                        "BUDGETWARD_ADMIN_TOKEN",
                        "BUDGETWARD_ADMIN_TOKEN_FILE",
                        "BUDGETWARD_BANK_LOGIN",
                        "BUDGETWARD_BANK_LOGIN_FILE",
                        "BUDGETWARD_BANK_PASSWORD",
                        "BUDGETWARD_BANK_PASSWORD_FILE",
                    }
                },
            )
            response = json.loads(result.stdout)
            if result.returncode != 0 or not response.get("ok"):
                raise ConnectorError(response.get("error", "unavailable"))
            return response["data"]
        except subprocess.TimeoutExpired:
            raise ConnectorError("timeout") from None
        except (OSError, ValueError, KeyError, TypeError):
            raise ConnectorError("unavailable") from None

    def get_accounts(self) -> list[ConnectorAccount]:
        try:
            return [ConnectorAccount.model_validate(row) for row in self._call("accounts")]
        except (ValidationError, TypeError):
            raise ConnectorError("data") from None

    def read_snapshot(self, account_ids: list[str], since: date, until: date):
        self.snapshot = self._call(
            "snapshot", account_ids=account_ids, since=since.isoformat(), until=until.isoformat()
        )
        self.bounds = (since, until)

    def get_balance(self, account_id: str) -> int:
        if not self.snapshot or account_id not in self.snapshot:
            raise ConnectorError("data")
        value = self.snapshot[account_id]["balance_cents"]
        if type(value) is not int or not -1_000_000_000 <= value <= 1_000_000_000:
            raise ConnectorError("data")
        return value

    def get_transactions(self, account_id: str, since: date, until: date):
        if not self.snapshot or account_id not in self.snapshot or self.bounds != (since, until):
            raise ConnectorError("data")
        try:
            return [
                ConnectorTransaction.model_validate(row)
                for row in self.snapshot[account_id]["transactions"]
            ]
        except (ValidationError, KeyError, TypeError):
            raise ConnectorError("data") from None

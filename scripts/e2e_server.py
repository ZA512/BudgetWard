"""Serveur de test avec une base temporaire, jamais la base utilisateur."""

import argparse
import tempfile
from pathlib import Path

import uvicorn

from budgetward.api import create_app
from budgetward.banking import DemoConnector
from budgetward.woob_connector import BankConfiguration

parser = argparse.ArgumentParser()
parser.add_argument("--real", action="store_true")
parser.add_argument("--bank", action="store_true")
args = parser.parse_args()
with tempfile.TemporaryDirectory(prefix="budgetward-e2e-") as folder:
    modules = Path(folder) / "modules"
    if args.bank:
        (modules / "cragr").mkdir(parents=True)
        (modules / "cragr" / "module.py").touch()
    configuration = (
        BankConfiguration("bank.invalid", "fake-login", "fake-password", modules)
        if args.bank
        else BankConfiguration()
    )
    app = create_app(
        str(Path(folder) / "test.db"),
        admin_token="e2e-fake-token-more-than-24-characters",
        demo=not (args.real or args.bank),
        bank_configuration=configuration,
        bank_factory=DemoConnector if args.bank else None,
    )
    port = 8767 if args.bank else (8766 if args.real else 8765)
    uvicorn.run(app, host="127.0.0.1", port=port, access_log=False)

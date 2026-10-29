import hmac
import os
import secrets
import sqlite3
import time
from contextlib import asynccontextmanager, closing
from datetime import date, timedelta
from pathlib import Path
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, StrictInt
from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from .banking import Banking
from .config import read_secret
from .csv_import import CsvColumnsInput, CsvCommit, CsvInput, columns
from .csv_import import commit as commit_csv
from .csv_import import preview as preview_csv
from .database import initialize
from .engine import month_bounds
from .history import HistoryValidation, analyze
from .history import validate as validate_history
from .models import (
    Account,
    Adjustment,
    BankTransaction,
    Budget,
    Charge,
    ChargeRule,
    Classification,
    HistoryDismissal,
    ImportBatch,
    Plan,
)
from .service import forecast
from .woob_connector import ConnectorError

Money = Annotated[StrictInt, Field(ge=0, le=1_000_000_000)]
Frequency = Literal["MONTHLY", "WEEKLY", "EVERY_2_WEEKS", "QUARTERLY", "YEARLY", "MANUAL"]
Name = Annotated[str, Field(min_length=1, max_length=120, pattern=r"\S")]


def today():
    from datetime import datetime

    return datetime.now(ZoneInfo("Europe/Paris")).date()


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class AccountInput(Input):
    name: Name
    balance_cents: Annotated[StrictInt, Field(ge=-1_000_000_000, le=1_000_000_000)]
    balance_date: date


class SetupInput(AccountInput):
    expenses_balance_cents: Annotated[StrictInt, Field(ge=-1_000_000_000, le=1_000_000_000)]
    expenses_name: Name = "Compte DÉPENSES"
    charges_choice_id: str | None = None
    expenses_choice_id: str | None = None
    bank_confirmed: bool = False


class BankSelection(Input):
    charges_choice_id: str
    expenses_choice_id: str | None = None
    confirmed: Literal[True]


class BankRead(Input):
    since: date


class BankImport(Input):
    snapshot_id: str
    confirmed: Literal[True]
    decisions: dict[str, dict[str, Literal["IMPORT", "SKIP"]]] = Field(default_factory=dict)


class ChargeInput(Input):
    name: Name
    amount_cents: Money
    frequency: Frequency = "MONTHLY"
    anchor_date: date
    end_date: date | None = None
    installment_count: Annotated[StrictInt, Field(ge=1, le=600)] | None = None
    tolerance_cents: Money = 0


class RevisionInput(Input):
    amount_cents: Money
    effective_from: date


class BudgetInput(Input):
    name: Name
    amount_cents: Money
    frequency: Frequency = "WEEKLY"
    anchor_date: date


class PlanInput(Input):
    safety_cents: Money
    treasury_cents: Money


class CountInput(Input):
    count: Annotated[StrictInt, Field(ge=0, le=100)] | None


class AdjustmentInput(Input):
    name: Name
    amount_cents: Money


class TransactionInput(Input):
    account_id: StrictInt
    booking_date: date
    operation_date: date | None = None
    amount_cents: Annotated[StrictInt, Field(ge=-1_000_000_000, le=1_000_000_000)]
    raw_label: Annotated[str, Field(min_length=1, max_length=250, pattern=r"\S")]
    provider_id: Annotated[str, Field(min_length=1, max_length=120)] | None = None


class ClassificationInput(Input):
    kind: Literal["CHARGE", "FUNDED", "SPENT", "INTERNAL", "OTHER"]
    target_id: StrictInt | None = None
    other_account_id: StrictInt | None = None


class LoginInput(Input):
    token: Annotated[str, Field(max_length=1000)]


def seed_demo(db: Session):
    month = "2026-10"
    day = date(2026, 10, 21)
    db.add_all(
        [
            Account(
                name="Compte joint CHARGES", role="CHARGES", balance_cents=497000, balance_date=day
            ),
            Account(
                name="Compte joint DÉPENSES", role="DEPENSES", balance_cents=53500, balance_date=day
            ),
        ]
    )
    for name, amount, due in [
        ("Prêts du foyer", 95000, 5),
        ("Assurances", 23000, 8),
        ("Électricité · EDF", 16150, 5),
        ("Internet et abonnements", 18500, 12),
        ("École et cantines", 28300, 25),
        ("Autres charges", 51050, 28),
    ]:
        charge = Charge(name=name)
        db.add(charge)
        db.flush()
        db.add(
            ChargeRule(
                charge_id=charge.id,
                effective_from=date(2026, 10, 1),
                amount_cents=amount,
                frequency="MONTHLY",
                anchor_date=date(2026, 10, due),
                tolerance_cents=0,
            )
        )
    for name, amount, frequency, anchor in [
        ("Courses alimentaires", 27000, "WEEKLY", date(2026, 10, 3)),
        ("Fast-food familial", 4000, "EVERY_2_WEEKS", date(2026, 10, 13)),
        ("Carburant · utilisateur", 7500, "MONTHLY", date(2026, 10, 1)),
        ("Carburant · conjointe", 5500, "WEEKLY", date(2026, 10, 5)),
        ("Covoiturage FAC", 3500, "MANUAL", date(2026, 10, 1)),
    ]:
        db.add(Budget(name=name, amount_cents=amount, frequency=frequency, anchor_date=anchor))
    db.flush()
    carpool = db.scalar(select(Budget).where(Budget.name == "Covoiturage FAC"))
    db.add(
        Plan(
            month=month,
            safety_cents=10000,
            treasury_cents=15000,
            budget_counts={str(carpool.id): 4},
        )
    )
    db.commit()


def create_app(
    db_path: str | None = None,
    admin_token: str | None = None,
    demo: bool = False,
    *,
    bank_configuration=None,
    bank_factory=None,
):
    db_file = Path(db_path or "data/app.db").resolve()
    db_file.parent.mkdir(parents=True, exist_ok=True)
    if not demo and (not admin_token or len(admin_token) < 24):
        raise RuntimeError(
            "Configurer BUDGETWARD_ADMIN_TOKEN avec une clé de 24 caractères minimum."
        )
    engine = create_engine(
        f"sqlite:///{db_file.as_posix()}", connect_args={"check_same_thread": False, "timeout": 20}
    )

    @event.listens_for(engine, "connect")
    def pragmas(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")

    sessions = sessionmaker(engine, expire_on_commit=False)
    auth_sessions: dict[str, tuple[float, str]] = {}
    failed_logins: dict[str, list[float]] = {}
    import_signing_key = secrets.token_bytes(32)
    banking = Banking(
        engine,
        import_signing_key,
        demo=demo,
        configuration=bank_configuration,
        factory=bank_factory,
    )

    @asynccontextmanager
    async def lifespan(app):
        initialize(engine, db_file)
        with sessions() as db:
            if demo and not db.scalar(select(Account.id).limit(1)):
                seed_demo(db)
        backup_dir = db_file.parent / "backups" / db_file.name
        backup_dir.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(db_file)) as source:
            with closing(
                sqlite3.connect(backup_dir / f"startup-{today().isoformat()}.db")
            ) as target:
                source.backup(target)
        yield
        engine.dispose()

    app = FastAPI(
        title="BudgetWard",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.sessions = sessions
    app.state.engine = engine
    app.state.banking = banking

    @app.exception_handler(ConnectorError)
    async def bank_failure(request, error):
        content = {"detail": str(error), "code": error.code}
        if error.diagnostic:
            content["diagnostic"] = error.diagnostic
        return JSONResponse(status_code=502, content=content)

    def get_db():
        with sessions() as db:
            yield db

    def authenticated(request: Request):
        if demo:
            csrf = "demo"
        else:
            key = request.cookies.get("budgetward_session", "")
            session = auth_sessions.get(key)
            if session is None or session[0] <= time.monotonic():
                auth_sessions.pop(key, None)
                raise HTTPException(401, "Veuillez vous connecter.")
            csrf = session[1]
        if request.method not in {"GET", "HEAD"}:
            if not hmac.compare_digest(request.headers.get("x-csrf-token", ""), csrf):
                raise HTTPException(403, "Session invalide. Rechargez la page.")
        return csrf

    def require_month(month: str):
        try:
            if len(month) != 7:
                raise ValueError
            month_bounds(month)
        except ValueError:
            raise HTTPException(422, "Mois invalide, format attendu AAAA-MM.") from None

    def get_or_404(db: Session, model, id):
        obj = db.get(model, id)
        if obj is None:
            raise HTTPException(404, "Élément introuvable.")
        return obj

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'"
        )
        if request.url.path.startswith("/api"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/health")
    def health():
        with engine.connect() as connection:
            connection.exec_driver_sql("SELECT 1")
        return {"status": "ok"}

    @app.get("/api/session")
    def session_info(request: Request):
        try:
            csrf = authenticated(request)
            return {"authenticated": True, "csrf": csrf, "demo": demo}
        except HTTPException:
            return {"authenticated": False, "demo": demo}

    @app.post("/api/session")
    def login(data: LoginInput, request: Request, response: Response):
        client = request.client.host if request.client else "local"
        now = time.monotonic()
        failures = [t for t in failed_logins.get(client, []) if now - t < 60]
        if len(failures) >= 10:
            raise HTTPException(429, "Trop d'essais. Réessayez dans une minute.")
        if not demo and not hmac.compare_digest(data.token.encode(), admin_token.encode()):
            failed_logins[client] = [*failures, now]
            raise HTTPException(401, "Clé incorrecte.")
        failed_logins.pop(client, None)
        expired = [k for k, (deadline, _) in auth_sessions.items() if deadline <= now]
        for key in expired:
            auth_sessions.pop(key, None)
        key, csrf = secrets.token_urlsafe(40), secrets.token_urlsafe(32)
        auth_sessions[key] = (now + 8 * 3600, csrf)
        response.set_cookie(
            "budgetward_session",
            key,
            httponly=True,
            samesite="strict",
            secure=os.getenv("BUDGETWARD_SECURE_COOKIE") == "true",
            max_age=28800,
        )
        return {"authenticated": True, "csrf": "demo" if demo else csrf, "demo": demo}

    @app.delete("/api/session", dependencies=[Depends(authenticated)])
    def logout(request: Request, response: Response):
        auth_sessions.pop(request.cookies.get("budgetward_session", ""), None)
        response.delete_cookie("budgetward_session")
        return {"ok": True}

    @app.get("/api/forecast", dependencies=[Depends(authenticated)])
    def get_forecast(month: str, db: Session = Depends(get_db)):
        require_month(month)
        result = forecast(db, month, today())
        bank_status = banking.status()
        return {
            **result,
            "bank_pending": bank_status["pending"],
            "bank_problem_count": sum(bool(b["error_code"]) for b in bank_status["bindings"]),
        }

    @app.post("/api/setup", dependencies=[Depends(authenticated)])
    def setup(data: SetupInput, db: Session = Depends(get_db)):
        if db.scalar(select(Account.id).limit(1)):
            raise HTTPException(409, "Le suivi existe déjà.")
        if data.balance_date > today():
            raise HTTPException(422, "Le solde doit avoir été constaté aujourd'hui ou avant.")
        if data.expenses_choice_id and not data.charges_choice_id:
            raise HTTPException(422, "Sélectionnez le compte CHARGES avant d'associer la banque.")
        if data.charges_choice_id and not data.bank_confirmed:
            raise HTTPException(422, "Confirmez les comptes bancaires choisis.")
        db.add(
            Account(
                name=data.name,
                role="CHARGES",
                balance_cents=data.balance_cents,
                balance_date=data.balance_date,
            )
        )
        db.add(
            Account(
                name=data.expenses_name,
                role="DEPENSES",
                balance_cents=data.expenses_balance_cents,
                balance_date=data.balance_date,
            )
        )
        if data.charges_choice_id:
            with banking.exclusive():
                db.flush()
                banking.bind_in_session(db, data.charges_choice_id, data.expenses_choice_id)
                db.commit()
        else:
            db.commit()
        return {"ok": True}

    @app.get("/api/bank/status", dependencies=[Depends(authenticated)])
    def bank_status():
        return banking.status()

    @app.get("/api/bank/pending", dependencies=[Depends(authenticated)])
    def bank_pending():
        return banking.pending()

    @app.post("/api/bank/discover", dependencies=[Depends(authenticated)])
    def bank_discover():
        return banking.discover()

    @app.post("/api/bank/bind", dependencies=[Depends(authenticated)])
    def bank_bind(data: BankSelection):
        return banking.bind(data.charges_choice_id, data.expenses_choice_id)

    @app.post("/api/bank/preview", dependencies=[Depends(authenticated)])
    def bank_preview(data: BankRead):
        return banking.prepare(data.since, today(), today())

    @app.post("/api/bank/commit", dependencies=[Depends(authenticated)])
    def bank_commit(data: BankImport):
        return banking.commit(data.snapshot_id, data.decisions, data.confirmed, today())

    @app.put("/api/accounts/{id}", dependencies=[Depends(authenticated)])
    def account_balance(id: int, data: AccountInput, db: Session = Depends(get_db)):
        if data.balance_date > today():
            raise HTTPException(422, "La date du solde ne peut pas être future.")
        account = get_or_404(db, Account, id)
        for key, value in data.model_dump().items():
            setattr(account, key, value)
        db.commit()
        return {"ok": True}

    @app.post("/api/charges", dependencies=[Depends(authenticated)])
    def add_charge(data: ChargeInput, db: Session = Depends(get_db)):
        if data.frequency == "MANUAL":
            raise HTTPException(422, "Utilisez un ajustement mensuel pour une charge ponctuelle.")
        if data.end_date and data.end_date < data.anchor_date:
            raise HTTPException(422, "La fin précède la première échéance.")
        if data.installment_count and data.frequency not in {"MONTHLY", "QUARTERLY", "YEARLY"}:
            raise HTTPException(422, "Les échéanciers de ce premier lot sont mensuels ou annuels.")
        charge = Charge(name=data.name)
        db.add(charge)
        db.flush()
        values = data.model_dump(exclude={"name"})
        db.add(ChargeRule(charge_id=charge.id, effective_from=data.anchor_date, **values))
        db.commit()
        return {"id": charge.id}

    @app.post("/api/charges/{id}/revisions", dependencies=[Depends(authenticated)])
    def revise_charge(id: int, data: RevisionInput, db: Session = Depends(get_db)):
        get_or_404(db, Charge, id)
        latest = db.scalar(
            select(ChargeRule)
            .where(ChargeRule.charge_id == id)
            .order_by(ChargeRule.effective_from.desc())
            .limit(1)
        )
        if data.effective_from <= latest.effective_from:
            raise HTTPException(422, "La nouvelle période doit commencer après la précédente.")
        latest.effective_until = data.effective_from - timedelta(days=1)
        db.add(
            ChargeRule(
                charge_id=id,
                effective_from=data.effective_from,
                amount_cents=data.amount_cents,
                frequency=latest.frequency,
                anchor_date=latest.anchor_date,
                end_date=latest.end_date,
                installment_count=latest.installment_count,
                tolerance_cents=latest.tolerance_cents,
            )
        )
        db.commit()
        return {"ok": True}

    @app.post("/api/budgets", dependencies=[Depends(authenticated)])
    def add_budget(data: BudgetInput, db: Session = Depends(get_db)):
        budget = Budget(**data.model_dump())
        db.add(budget)
        db.commit()
        return {"id": budget.id}

    @app.put("/api/plans/{month}", dependencies=[Depends(authenticated)])
    def update_plan(month: str, data: PlanInput, db: Session = Depends(get_db)):
        require_month(month)
        plan = db.get(Plan, month)
        if not plan:
            plan = Plan(month=month)
            db.add(plan)
        plan.safety_cents, plan.treasury_cents = data.safety_cents, data.treasury_cents
        db.commit()
        return {"ok": True}

    @app.put("/api/plans/{month}/budgets/{id}", dependencies=[Depends(authenticated)])
    def budget_count(month: str, id: int, data: CountInput, db: Session = Depends(get_db)):
        require_month(month)
        get_or_404(db, Budget, id)
        plan = db.get(Plan, month)
        if not plan:
            plan = Plan(month=month, safety_cents=0, treasury_cents=0, budget_counts={})
            db.add(plan)
        counts = dict(plan.budget_counts or {})
        if data.count is None:
            counts.pop(str(id), None)
        else:
            counts[str(id)] = data.count
        plan.budget_counts = counts
        db.commit()
        return {"ok": True}

    @app.post("/api/plans/{month}/adjustments", dependencies=[Depends(authenticated)])
    def add_adjustment(month: str, data: AdjustmentInput, db: Session = Depends(get_db)):
        require_month(month)
        db.add(Adjustment(month=month, **data.model_dump()))
        db.commit()
        return {"ok": True}

    @app.delete("/api/adjustments/{id}", dependencies=[Depends(authenticated)])
    def remove_adjustment(id: int, db: Session = Depends(get_db)):
        db.delete(get_or_404(db, Adjustment, id))
        db.commit()
        return {"ok": True}

    @app.post("/api/transactions", dependencies=[Depends(authenticated)])
    def add_transaction(data: TransactionInput, db: Session = Depends(get_db)):
        get_or_404(db, Account, data.account_id)
        if data.booking_date > today() or (data.operation_date and data.operation_date > today()):
            raise HTTPException(422, "Une opération réelle ne peut pas être future.")
        if data.operation_date and data.operation_date > data.booking_date:
            raise HTTPException(422, "La date d'achat doit précéder ou égaler la date comptable.")
        if data.amount_cents == 0:
            raise HTTPException(422, "Le montant ne peut pas être nul.")
        transaction = BankTransaction(**data.model_dump())
        db.add(transaction)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(
                409, "Cette référence bancaire existe déjà sur ce compte."
            ) from None
        return {"id": transaction.id}

    @app.put("/api/transactions/{id}/classification", dependencies=[Depends(authenticated)])
    def classify(id: int, data: ClassificationInput, db: Session = Depends(get_db)):
        tx = get_or_404(db, BankTransaction, id)
        account = get_or_404(db, Account, tx.account_id)
        charge_id = budget_id = other_account_id = None
        if data.kind in {"CHARGE", "FUNDED", "SPENT"} and tx.amount_cents >= 0:
            raise HTTPException(422, "Cette affectation nécessite une sortie d'argent.")
        if data.kind == "CHARGE":
            get_or_404(db, Charge, data.target_id)
            charge_id = data.target_id
        if data.kind in {"FUNDED", "SPENT"}:
            get_or_404(db, Budget, data.target_id)
            budget_id = data.target_id
        if data.kind in {"INTERNAL", "FUNDED"}:
            other = get_or_404(db, Account, data.other_account_id)
            if other.id == account.id:
                raise HTTPException(422, "Choisir l'autre compte du transfert.")
            other_account_id = other.id
        if data.kind == "FUNDED" and (account.role != "CHARGES" or other.role != "DEPENSES"):
            raise HTTPException(422, "Le financement doit sortir de CHARGES vers DÉPENSES.")
        classification = db.get(Classification, id)
        if not classification:
            classification = Classification(transaction_id=id)
            db.add(classification)
        classification.kind, classification.charge_id = data.kind, charge_id
        classification.budget_id = budget_id
        classification.other_account_id = other_account_id
        db.commit()
        return {"ok": True}

    @app.get("/api/export", dependencies=[Depends(authenticated)])
    def export(db: Session = Depends(get_db)):
        result = {}
        for model in [
            Account,
            Charge,
            ChargeRule,
            Budget,
            Plan,
            Adjustment,
            BankTransaction,
            Classification,
            ImportBatch,
            HistoryDismissal,
        ]:
            result[model.__tablename__] = [
                {column.name: getattr(row, column.name) for column in model.__table__.columns}
                for row in db.scalars(select(model))
            ]
        return result

    @app.post("/api/import/csv/preview", dependencies=[Depends(authenticated)])
    def csv_preview(data: CsvInput, db: Session = Depends(get_db)):
        return preview_csv(db, data, today(), import_signing_key)

    @app.post("/api/import/csv/columns", dependencies=[Depends(authenticated)])
    def csv_columns(data: CsvColumnsInput):
        return columns(data)

    @app.post("/api/import/csv/commit", dependencies=[Depends(authenticated)])
    def csv_commit(data: CsvCommit, db: Session = Depends(get_db)):
        return commit_csv(db, data, today(), import_signing_key)

    @app.get("/api/history", dependencies=[Depends(authenticated)])
    def get_history(
        account_id: int, include_dismissed: bool = False, db: Session = Depends(get_db)
    ):
        return analyze(db, account_id, include_dismissed)

    @app.post("/api/history/validate", dependencies=[Depends(authenticated)])
    def history_validate(data: HistoryValidation, db: Session = Depends(get_db)):
        return validate_history(db, data)

    @app.put("/api/history/{key}/dismissal", dependencies=[Depends(authenticated)])
    def dismiss_history(key: str, account_id: int, db: Session = Depends(get_db)):
        if not any(g["key"] == key for g in analyze(db, account_id, True)["groups"]):
            raise HTTPException(404, "Groupe introuvable.")
        if not db.get(HistoryDismissal, key):
            db.add(HistoryDismissal(key=key))
            db.commit()
        return {"ok": True}

    @app.delete("/api/history/{key}/dismissal", dependencies=[Depends(authenticated)])
    def restore_history(key: str, db: Session = Depends(get_db)):
        dismissal = db.get(HistoryDismissal, key)
        if dismissal:
            db.delete(dismissal)
            db.commit()
        return {"ok": True}

    @app.get("/api/backup", dependencies=[Depends(authenticated)])
    def backup():
        from starlette.background import BackgroundTask

        path = db_file.parent / "backups" / db_file.name / f"export-{secrets.token_hex(12)}.db"
        with closing(sqlite3.connect(db_file)) as source:
            with closing(sqlite3.connect(path)) as target:
                source.backup(target)
        return FileResponse(
            path,
            filename=f"budgetward-{today()}.db",
            background=BackgroundTask(path.unlink, missing_ok=True),
        )

    static = Path(os.getenv("BUDGETWARD_FRONTEND_PATH", "frontend/dist")).resolve()
    if (static / "assets").exists():
        app.mount("/assets", StaticFiles(directory=static / "assets"), name="assets")

    @app.get("/")
    def index():
        if not (static / "index.html").exists():
            raise HTTPException(503, "Compiler le frontend avec npm run build.")
        return FileResponse(static / "index.html")

    return app


def app_factory():
    demo = os.getenv("BUDGETWARD_DEMO") == "true"
    token = None if demo else read_secret("BUDGETWARD_ADMIN_TOKEN")
    path = (
        os.getenv("BUDGETWARD_DEMO_DB_PATH", "data/demo.db")
        if demo
        else os.getenv("BUDGETWARD_DB_PATH", "data/app.db")
    )
    return create_app(path, token, demo)

from datetime import UTC, date, datetime

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Account(Base):
    __tablename__ = "accounts"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(20), unique=True)
    balance_cents: Mapped[int] = mapped_column(Integer)
    balance_date: Mapped[date] = mapped_column(Date)


class Charge(Base):
    __tablename__ = "charges"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(default="ACTIVE")


class ChargeRule(Base):
    __tablename__ = "charge_rules"
    id: Mapped[int] = mapped_column(primary_key=True)
    charge_id: Mapped[int] = mapped_column(ForeignKey("charges.id"))
    effective_from: Mapped[date] = mapped_column(Date)
    effective_until: Mapped[date | None] = mapped_column(Date)
    amount_cents: Mapped[int] = mapped_column(Integer)
    frequency: Mapped[str] = mapped_column(String(30))
    anchor_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    installment_count: Mapped[int | None] = mapped_column(Integer)
    tolerance_cents: Mapped[int] = mapped_column(Integer, default=0)


class Budget(Base):
    __tablename__ = "budgets"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    amount_cents: Mapped[int] = mapped_column(Integer)
    frequency: Mapped[str] = mapped_column(String(30))
    anchor_date: Mapped[date] = mapped_column(Date)


class Plan(Base):
    __tablename__ = "plans"
    month: Mapped[str] = mapped_column(String(7), primary_key=True)
    safety_cents: Mapped[int] = mapped_column(Integer, default=0)
    treasury_cents: Mapped[int] = mapped_column(Integer, default=0)
    # Monthly overrides are deliberately separate from global budget references.
    budget_counts: Mapped[dict] = mapped_column(JSON, default=dict)


class Adjustment(Base):
    __tablename__ = "adjustments"
    id: Mapped[int] = mapped_column(primary_key=True)
    month: Mapped[str] = mapped_column(String(7))
    name: Mapped[str] = mapped_column(String(120))
    amount_cents: Mapped[int] = mapped_column(Integer)


class BankTransaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (UniqueConstraint("account_id", "provider_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    provider_id: Mapped[str | None] = mapped_column(String(120))
    booking_date: Mapped[date] = mapped_column(Date)
    operation_date: Mapped[date | None] = mapped_column(Date)
    amount_cents: Mapped[int] = mapped_column(Integer)
    raw_label: Mapped[str] = mapped_column(String(250))
    source: Mapped[str] = mapped_column(default="MANUAL")
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class Classification(Base):
    __tablename__ = "classifications"
    transaction_id: Mapped[int] = mapped_column(ForeignKey("transactions.id"), primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))
    charge_id: Mapped[int | None] = mapped_column(ForeignKey("charges.id"))
    budget_id: Mapped[int | None] = mapped_column(ForeignKey("budgets.id"))
    other_account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"))


class ImportBatch(Base):
    __tablename__ = "import_batches"
    __table_args__ = (UniqueConstraint("account_id", "digest"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    digest: Mapped[str] = mapped_column(String(64))
    imported_count: Mapped[int] = mapped_column(Integer)
    skipped_count: Mapped[int] = mapped_column(Integer)
    transaction_ids: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class HistoryDismissal(Base):
    __tablename__ = "history_dismissals"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)


class BankBinding(Base):
    __tablename__ = "bank_bindings"
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), primary_key=True)
    provider_account_id: Mapped[str] = mapped_column(String(200), unique=True)
    masked_iban: Mapped[str] = mapped_column(String(40))
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime)
    error_code: Mapped[str | None] = mapped_column(String(30))

"""Read-only bank contract; no dependency on a particular banking provider."""

from datetime import date
from typing import Annotated, Protocol

from pydantic import BaseModel, ConfigDict, Field, StrictInt


class ConnectorAccount(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: Annotated[str, Field(min_length=1, max_length=200)]
    name: Annotated[str, Field(min_length=1, max_length=120)]
    balance_cents: Annotated[StrictInt, Field(ge=-1_000_000_000, le=1_000_000_000)]
    masked_iban: Annotated[str, Field(min_length=1, max_length=40)]


class ConnectorTransaction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    booking_date: date
    operation_date: date | None = None
    amount_cents: Annotated[StrictInt, Field(ge=-1_000_000_000, le=1_000_000_000)]
    raw_label: Annotated[str, Field(min_length=1, max_length=250)]
    provider_id: Annotated[str, Field(min_length=1, max_length=120)] | None = None


class BankConnector(Protocol):
    def get_accounts(self) -> list[ConnectorAccount]: ...
    def get_balance(self, account_id: str) -> int: ...
    def get_transactions(
        self, account_id: str, since: date, until: date
    ) -> list[ConnectorTransaction]: ...

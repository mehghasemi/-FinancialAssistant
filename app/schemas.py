from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from .calendar import parse_jalali_date
from .utils import normalize_text


class TransactionInput(BaseModel):
    transaction_type: Literal["income", "expense"]
    amount: int = Field(gt=0)
    occurred_on: date
    category_id: int | None = None
    account_id: int | None = None
    note: str = Field(default="", max_length=300)

    @field_validator("note")
    @classmethod
    def normalize_note(cls, value: str) -> str:
        return normalize_text(value)

    @field_validator("occurred_on", mode="before")
    @classmethod
    def parse_occurrence_date(cls, value):
        return parse_jalali_date(value)


class CommitmentInput(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    kind: str = Field(min_length=2, max_length=50)
    total_amount: int | None = Field(default=None, gt=0)
    installment_amount: int = Field(gt=0)
    first_due_date: date
    installment_count: int = Field(ge=1, le=600)
    interval_months: int = Field(default=1, ge=1, le=12)

    @field_validator("title", "kind")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        cleaned = normalize_text(value)
        if len(cleaned) < 2:
            raise ValueError("این فیلد باید حداقل دو حرف داشته باشد.")
        return cleaned

    @field_validator("first_due_date", mode="before")
    @classmethod
    def parse_first_due_date(cls, value):
        return parse_jalali_date(value)


class PaymentInput(BaseModel):
    installment_id: int
    amount: int = Field(gt=0)
    paid_on: date
    account_id: int | None = None
    note: str = Field(default="", max_length=300)

    @field_validator("note")
    @classmethod
    def normalize_note(cls, value: str) -> str:
        return normalize_text(value)

    @field_validator("paid_on", mode="before")
    @classmethod
    def parse_payment_date(cls, value):
        return parse_jalali_date(value)


class PaymentUpdate(BaseModel):
    amount: int = Field(gt=0)
    paid_on: date
    account_id: int | None = None
    note: str = Field(default="", max_length=300)

    @field_validator("paid_on", mode="before")
    @classmethod
    def parse_paid_on(cls, value):
        return parse_jalali_date(value)


class CommitmentUpdate(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    kind: str = Field(min_length=2, max_length=50)
    total_amount: int | None = Field(default=None, gt=0)

    @field_validator("title", "kind")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        return normalize_text(value)


class CommitmentGroupUpdate(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    kind: str = Field(min_length=2, max_length=50)

    @field_validator("title", "kind")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        return normalize_text(value)


class InstallmentUpdate(BaseModel):
    due_date: date
    amount: int = Field(gt=0)
    note: str = Field(default="", max_length=300)

    @field_validator("due_date", mode="before")
    @classmethod
    def parse_due_date(cls, value):
        return parse_jalali_date(value)

    @field_validator("note")
    @classmethod
    def normalize_note(cls, value: str) -> str:
        return normalize_text(value)


class SettingsInput(BaseModel):
    backup_enabled: bool = True
    backup_directory: str = Field(min_length=1, max_length=500)

    @field_validator("backup_directory")
    @classmethod
    def normalize_backup_directory(cls, value: str) -> str:
        return str(Path(value).expanduser())

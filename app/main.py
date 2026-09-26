from __future__ import annotations

import logging
import json
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Literal

import jdatetime
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, Field, field_validator

from .calendar import format_jalali_date, format_jalali_datetime, jalali_month_bounds, jalali_month_label, parse_jalali_date
from .config import APP_NAME, APP_VERSION, LOCAL_HOSTS, MAX_PAGE_SIZE
from .database import (
    RESOURCE_DIR, connection, create_database_backup, get_setting,
    initialize_database, set_setting, write_audit_log,
)


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title=APP_NAME, version=APP_VERSION)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=[*LOCAL_HOSTS])
STATIC_DIR = RESOURCE_DIR / "static"


def normalize_text(value: str) -> str:
    return " ".join(value.strip().split())


def commitment_title_key(value: str) -> str:
    return normalize_text(value).replace("ي", "ی").replace("ك", "ک")


def month_bounds_or_error(month: str) -> tuple[str, str]:
    try:
        start, end = jalali_month_bounds(month)
        return start.isoformat(), end.isoformat()
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


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


def serialize(row):
    return dict(row)


def add_months(value: date, months: int) -> date:
    jalali_value = jdatetime.date.fromgregorian(date=value)
    month_index = jalali_value.month - 1 + months
    year = jalali_value.year + month_index // 12
    month = month_index % 12 + 1
    maximum_day = 31 if month <= 6 else 30 if month <= 11 else 30 if jdatetime.date(year, 12, 1).isleap() else 29
    return jdatetime.date(year, month, min(jalali_value.day, maximum_day)).togregorian()


def planned_installments(payload: CommitmentInput) -> list[date]:
    return [
        add_months(payload.first_due_date, index * payload.interval_months)
        for index in range(payload.installment_count)
    ]


def installment_rows(where: str = "", params: tuple = ()) -> list[dict]:
    query = f"""
        SELECT
            i.id, i.due_date, i.amount, i.note, c.id AS commitment_id,
            c.title, c.kind, c.total_amount,
            COALESCE(SUM(p.amount), 0) AS paid_amount,
            i.amount - COALESCE(SUM(p.amount), 0) AS remaining_amount
        FROM installments i
        JOIN commitments c ON c.id = i.commitment_id
        LEFT JOIN payments p ON p.installment_id = i.id
        {where}
        GROUP BY i.id
        ORDER BY i.due_date, i.id
    """
    with connection() as db:
        result = [serialize(row) for row in db.execute(query, params).fetchall()]

    today = date.today().isoformat()
    for item in result:
        if item["remaining_amount"] <= 0:
            item["status"] = "paid"
        elif item["paid_amount"] > 0:
            item["status"] = "partial"
        elif item["due_date"] < today:
            item["status"] = "overdue"
        else:
            item["status"] = "unpaid"
        item["due_date"] = format_jalali_date(item["due_date"])
    return result


@app.on_event("startup")
def startup() -> None:
    initialize_database()


@app.on_event("shutdown")
def shutdown() -> None:
    if get_setting("backup_enabled", "true") != "true":
        return
    try:
        create_database_backup(get_setting("backup_directory", ""))
    except Exception:
        logger.exception("Automatic database backup failed during shutdown")


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, error: Exception):
    error_id = uuid.uuid4().hex[:10]
    logger.exception("Unhandled error %s at %s", error_id, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "خطای غیرمنتظره رخ داد. دوباره تلاش کنید؛ اگر ادامه داشت، شناسهٔ پیگیری را نگه دارید.", "error_id": error_id},
        headers={"X-Error-Id": error_id},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, error: RequestValidationError):
    fields = [".".join(str(part) for part in item["loc"] if part != "body") for item in error.errors()]
    return JSONResponse(
        status_code=422,
        content={"detail": "اطلاعات واردشده معتبر نیست. فیلدهای ضروری را بررسی کنید.", "fields": fields},
    )


@app.get("/api/health")
def health():
    return {"status": "ok", "database": "sqlite", "version": APP_VERSION}


@app.get("/api/settings")
def settings():
    return {
        "backup_enabled": get_setting("backup_enabled", "true") == "true",
        "backup_directory": get_setting("backup_directory", ""),
    }


@app.put("/api/settings")
def update_settings(payload: SettingsInput):
    set_setting("backup_enabled", "true" if payload.backup_enabled else "false")
    set_setting("backup_directory", payload.backup_directory)
    return settings()


@app.post("/api/backups", status_code=201)
def create_backup():
    backup_path = create_database_backup(get_setting("backup_directory", ""))
    return {"path": str(backup_path)}


@app.get("/api/releases")
def releases(limit: int = Query(default=20, ge=1, le=MAX_PAGE_SIZE)):
    with connection() as db:
        result = [serialize(row) for row in db.execute(
            """SELECT version, released_at, title, description, affected_areas
               FROM release_history ORDER BY released_at DESC LIMIT ?""", (limit,)
        ).fetchall()]
    for item in result:
        item["released_at"] = format_jalali_datetime(item["released_at"])
    return result


@app.get("/api/accounts")
def accounts():
    with connection() as db:
        return [serialize(row) for row in db.execute("SELECT id, name, kind FROM accounts ORDER BY id").fetchall()]


@app.get("/api/categories")
def categories(transaction_type: Literal["income", "expense"] | None = None):
    sql = "SELECT id, name, transaction_type FROM categories"
    params: tuple = ()
    if transaction_type:
        sql += " WHERE transaction_type = ?"
        params = (transaction_type,)
    sql += " ORDER BY transaction_type, name"
    with connection() as db:
        return [serialize(row) for row in db.execute(sql, params).fetchall()]


@app.post("/api/transactions", status_code=201)
def create_transaction(payload: TransactionInput):
    with connection() as db:
        if payload.category_id:
            category = db.execute("SELECT transaction_type FROM categories WHERE id = ?", (payload.category_id,)).fetchone()
            if not category:
                raise HTTPException(404, "دسته‌بندی پیدا نشد.")
            if category["transaction_type"] != payload.transaction_type:
                raise HTTPException(422, "نوع دسته‌بندی با نوع تراکنش هم‌خوان نیست.")
        cursor = db.execute(
            """INSERT INTO transactions(transaction_type, amount, occurred_on, category_id, account_id, note)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (payload.transaction_type, payload.amount, payload.occurred_on.isoformat(), payload.category_id, payload.account_id, payload.note.strip()),
        )
        write_audit_log(db, "create", "transaction", cursor.lastrowid, payload.transaction_type)
        return {"id": cursor.lastrowid}


@app.get("/api/transactions")
def transactions(month: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$")):
    params: list[str] = []
    where = ""
    if month:
        start, end = month_bounds_or_error(month)
        where = "WHERE t.occurred_on >= ? AND t.occurred_on < ?"
        params.extend((start, end))
    query = f"""
        SELECT t.id, t.transaction_type, t.amount, t.occurred_on, t.note,
               c.name AS category_name, a.name AS account_name
        FROM transactions t
        LEFT JOIN categories c ON c.id = t.category_id
        LEFT JOIN accounts a ON a.id = t.account_id
        {where}
        ORDER BY t.occurred_on DESC, t.id DESC
    """
    with connection() as db:
        result = [serialize(row) for row in db.execute(query, params).fetchall()]
    for item in result:
        item["occurred_on"] = format_jalali_date(item["occurred_on"])
    return result


@app.post("/api/commitments", status_code=201)
def create_commitment(payload: CommitmentInput):
    due_dates = planned_installments(payload)
    planned_total = payload.installment_amount * payload.installment_count
    if payload.total_amount and planned_total > payload.total_amount:
        raise HTTPException(422, "جمع اقساط نمی‌تواند بیشتر از مبلغ کل باشد.")
    with connection() as db:
        cursor = db.execute(
            "INSERT INTO commitments(title, kind, total_amount) VALUES (?, ?, ?)",
            (payload.title.strip(), payload.kind.strip(), payload.total_amount),
        )
        commitment_id = cursor.lastrowid
        db.executemany(
            "INSERT INTO installments(commitment_id, due_date, amount) VALUES (?, ?, ?)",
            ((commitment_id, due.isoformat(), payload.installment_amount) for due in due_dates),
        )
        write_audit_log(db, "create", "commitment", commitment_id, payload.title)
    return {"id": commitment_id, "installment_count": payload.installment_count}


@app.post("/api/commitments/preview")
def preview_commitment(payload: CommitmentInput):
    due_dates = planned_installments(payload)
    planned_total = payload.installment_amount * payload.installment_count
    if payload.total_amount and planned_total > payload.total_amount:
        raise HTTPException(422, "جمع اقساط نمی‌تواند بیشتر از مبلغ کل باشد.")
    return {
        "planned_total": planned_total,
        "first_due_date": format_jalali_date(due_dates[0]),
        "last_due_date": format_jalali_date(due_dates[-1]),
        "installments": [
            {"number": index + 1, "due_date": format_jalali_date(due), "amount": payload.installment_amount}
            for index, due in enumerate(due_dates)
        ],
    }


@app.get("/api/commitments")
def commitment_list():
    with connection() as db:
        return [
            serialize(row)
            for row in db.execute(
                """SELECT c.id, c.title, c.kind, c.total_amount, COUNT(i.id) AS installment_count,
                          COALESCE(SUM(i.amount), 0) AS planned_amount,
                          COALESCE(SUM(p.payment_amount), 0) AS paid_amount,
                          MIN(CASE WHEN i.amount > COALESCE(p.payment_amount, 0) THEN i.due_date END) AS next_unpaid_due_date,
                          MAX(i.due_date) AS last_due_date,
                          GROUP_CONCAT(i.due_date) AS due_dates
                   FROM commitments c
                   LEFT JOIN installments i ON i.commitment_id = c.id
                   LEFT JOIN (
                       SELECT installment_id, SUM(amount) AS payment_amount
                       FROM payments GROUP BY installment_id
                   ) p ON p.installment_id = i.id
                   GROUP BY c.id
                   ORDER BY c.id DESC"""
            ).fetchall()
        ]


@app.patch("/api/commitments/{commitment_id}")
def update_commitment(commitment_id: int, payload: CommitmentUpdate):
    with connection() as db:
        existing = db.execute("SELECT id, title, kind, total_amount FROM commitments WHERE id = ?", (commitment_id,)).fetchone()
        if not existing:
            raise HTTPException(404, "تعهد پیدا نشد.")
        planned_amount = db.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total FROM installments WHERE commitment_id = ?", (commitment_id,)
        ).fetchone()["total"]
        if payload.total_amount and payload.total_amount < planned_amount:
            raise HTTPException(422, "مبلغ کل نمی‌تواند کمتر از جمع اقساط باشد.")
        db.execute(
            "UPDATE commitments SET title = ?, kind = ?, total_amount = ? WHERE id = ?",
            (payload.title, payload.kind, payload.total_amount, commitment_id),
        )
        write_audit_log(db, "update", "commitment", commitment_id, json.dumps({
            "before": dict(existing), "after": {"title": payload.title, "kind": payload.kind, "total_amount": payload.total_amount}
        }, ensure_ascii=False))
    return {"id": commitment_id}


@app.patch("/api/commitments/{commitment_id}/group")
def update_commitment_group(commitment_id: int, payload: CommitmentGroupUpdate):
    with connection() as db:
        records = db.execute("SELECT id, title, kind, total_amount FROM commitments").fetchall()
        anchor = next((row for row in records if row["id"] == commitment_id), None)
        if anchor is None:
            raise HTTPException(404, "تعهد پیدا نشد.")
        key = commitment_title_key(anchor["title"])
        related = [row for row in records if commitment_title_key(row["title"]) == key]
        for row in related:
            db.execute("UPDATE commitments SET title = ?, kind = ? WHERE id = ?", (payload.title, payload.kind, row["id"]))
            write_audit_log(db, "update", "commitment", row["id"], json.dumps({
                "before": dict(row),
                "after": {"title": payload.title, "kind": payload.kind, "total_amount": row["total_amount"]},
                "scope": "group",
            }, ensure_ascii=False))
    return {"id": commitment_id, "updated_count": len(related)}


@app.get("/api/commitment-filters")
def commitment_filters():
    with connection() as db:
        return [
            serialize(row)
            for row in db.execute(
                """SELECT c.title, c.total_amount, COUNT(DISTINCT c.id) AS commitment_count,
                          COUNT(i.id) AS installment_count
                   FROM commitments c
                   LEFT JOIN installments i ON i.commitment_id = c.id
                   GROUP BY c.title, c.total_amount
                   ORDER BY c.title, c.total_amount"""
            ).fetchall()
        ]


@app.get("/api/installments")
def installments(
    month: str | None = None,
    status: Literal["paid", "partial", "overdue", "unpaid"] | None = None,
    commitment_id: int | None = None,
    commitment_title: str | None = None,
    commitment_total: int | None = None,
    commitment_total_missing: bool = False,
    search: str | None = None,
):
    clauses, params = [], []
    if month:
        start, end = month_bounds_or_error(month)
        clauses.append("i.due_date >= ? AND i.due_date < ?")
        params.extend((start, end))
    if commitment_id:
        clauses.append("i.commitment_id = ?")
        params.append(commitment_id)
    if commitment_title and normalize_text(commitment_title):
        clauses.append("c.title = ?")
        params.append(normalize_text(commitment_title))
        if commitment_total_missing:
            clauses.append("c.total_amount IS NULL")
        elif commitment_total is not None:
            clauses.append("c.total_amount = ?")
            params.append(commitment_total)
    if search and normalize_text(search):
        clauses.append("c.title LIKE ?")
        params.append(f"%{normalize_text(search)}%")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    result = installment_rows(where, tuple(params))
    if status:
        result = [item for item in result if item["status"] == status]
    return result


@app.patch("/api/installments/{installment_id}")
def update_installment(installment_id: int, payload: InstallmentUpdate):
    with connection() as db:
        existing = db.execute("SELECT id, commitment_id, due_date, amount, note FROM installments WHERE id = ?", (installment_id,)).fetchone()
        if not existing:
            raise HTTPException(404, "قسط پیدا نشد.")
        paid_amount = db.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total FROM payments WHERE installment_id = ?", (installment_id,)
        ).fetchone()["total"]
        if payload.amount < paid_amount:
            raise HTTPException(422, "مبلغ قسط نمی‌تواند کمتر از پرداخت‌های ثبت‌شده باشد.")
        planned_amount = db.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM installments WHERE commitment_id = ?", (existing["commitment_id"],)
        ).fetchone()[0]
        total_amount = db.execute("SELECT total_amount FROM commitments WHERE id = ?", (existing["commitment_id"],)).fetchone()[0]
        if total_amount is not None and planned_amount - existing["amount"] + payload.amount > total_amount:
            raise HTTPException(422, "جمع اقساط نمی‌تواند از مبلغ کل تعهد بیشتر باشد.")
        db.execute(
            "UPDATE installments SET due_date = ?, amount = ?, note = ? WHERE id = ?",
            (payload.due_date.isoformat(), payload.amount, payload.note, installment_id),
        )
        write_audit_log(db, "update", "installment", installment_id, json.dumps({
            "before": {"due_date": existing["due_date"], "amount": existing["amount"], "note": existing["note"]},
            "after": {"due_date": payload.due_date.isoformat(), "amount": payload.amount, "note": payload.note}
        }, ensure_ascii=False))
    return {"id": installment_id}


@app.post("/api/payments", status_code=201)
def create_payment(payload: PaymentInput):
    with connection() as db:
        installment = db.execute("SELECT amount FROM installments WHERE id = ?", (payload.installment_id,)).fetchone()
        if not installment:
            raise HTTPException(404, "سررسید پیدا نشد.")
        paid = db.execute("SELECT COALESCE(SUM(amount), 0) AS total FROM payments WHERE installment_id = ?", (payload.installment_id,)).fetchone()["total"]
        if paid + payload.amount > installment["amount"]:
            raise HTTPException(422, "مبلغ پرداخت از ماندهٔ سررسید بیشتر است.")
        cursor = db.execute(
            "INSERT INTO payments(installment_id, amount, paid_on, account_id, note) VALUES (?, ?, ?, ?, ?)",
            (payload.installment_id, payload.amount, payload.paid_on.isoformat(), payload.account_id, payload.note.strip()),
        )
        write_audit_log(db, "create", "payment", cursor.lastrowid, json.dumps({
            "installment_id": payload.installment_id, "amount": payload.amount, "paid_on": payload.paid_on.isoformat()
        }, ensure_ascii=False))
        return {"id": cursor.lastrowid}


@app.get("/api/installments/{installment_id}/details")
def installment_details(installment_id: int):
    with connection() as db:
        row = db.execute("SELECT commitment_id FROM installments WHERE id = ?", (installment_id,)).fetchone()
        if not row:
            raise HTTPException(404, "قسط پیدا نشد.")
        payments = [serialize(item) for item in db.execute(
            "SELECT p.id, p.amount, p.paid_on, p.account_id, p.note, a.name AS account_name "
            "FROM payments p LEFT JOIN accounts a ON a.id = p.account_id WHERE p.installment_id = ? ORDER BY p.id", (installment_id,)
        ).fetchall()]
        logs = [serialize(item) for item in db.execute(
            "SELECT id, action, resource_type, details, created_at FROM audit_logs "
            "WHERE (resource_type = 'installment' AND resource_id = ?) "
            "OR (resource_type = 'commitment' AND resource_id = ?) "
            "OR (resource_type = 'payment' AND (resource_id IN (SELECT id FROM payments WHERE installment_id = ?) "
            "OR (json_valid(details) AND json_extract(details, '$.installment_id') = ?) "
            "OR details = ?)) ORDER BY id DESC",
            (installment_id, row["commitment_id"], installment_id, installment_id, f"installment:{installment_id}")
        ).fetchall()]
        for log in logs:
            try:
                log["details"] = json.loads(log["details"])
            except (ValueError, TypeError):
                pass
        for payment in payments:
            payment["paid_on"] = format_jalali_date(payment["paid_on"])
        for log in logs:
            log["created_at"] = format_jalali_datetime(log["created_at"])
    return {"payments": payments, "history": logs}


@app.patch("/api/payments/{payment_id}")
def update_payment(payment_id: int, payload: PaymentUpdate):
    with connection() as db:
        existing = db.execute("SELECT * FROM payments WHERE id = ?", (payment_id,)).fetchone()
        if not existing:
            raise HTTPException(404, "پرداخت پیدا نشد.")
        installment = db.execute("SELECT amount FROM installments WHERE id = ?", (existing["installment_id"],)).fetchone()
        paid_other = db.execute("SELECT COALESCE(SUM(amount), 0) FROM payments WHERE installment_id = ? AND id != ?", (existing["installment_id"], payment_id)).fetchone()[0]
        if paid_other + payload.amount > installment["amount"]:
            raise HTTPException(422, "مجموع پرداخت‌ها از مبلغ قسط بیشتر می‌شود.")
        if payload.account_id is not None and not db.execute("SELECT 1 FROM accounts WHERE id = ?", (payload.account_id,)).fetchone():
            raise HTTPException(422, "حساب انتخاب‌شده پیدا نشد.")
        db.execute("UPDATE payments SET amount = ?, paid_on = ?, account_id = ?, note = ? WHERE id = ?",
                   (payload.amount, payload.paid_on.isoformat(), payload.account_id, payload.note.strip(), payment_id))
        write_audit_log(db, "update", "payment", payment_id, json.dumps({
            "installment_id": existing["installment_id"],
            "before": {key: existing[key] for key in ("amount", "paid_on", "account_id", "note")},
            "after": {"amount": payload.amount, "paid_on": payload.paid_on.isoformat(), "account_id": payload.account_id, "note": payload.note.strip()}
        }, ensure_ascii=False))
    return {"id": payment_id}


@app.delete("/api/payments/{payment_id}")
def delete_payment(payment_id: int):
    with connection() as db:
        existing = db.execute("SELECT * FROM payments WHERE id = ?", (payment_id,)).fetchone()
        if not existing:
            raise HTTPException(404, "پرداخت پیدا نشد.")
        write_audit_log(db, "delete", "payment", payment_id, json.dumps({
            "installment_id": existing["installment_id"],
            "before": {key: existing[key] for key in ("amount", "paid_on", "account_id", "note")}
        }, ensure_ascii=False))
        db.execute("DELETE FROM payments WHERE id = ?", (payment_id,))
    return {"id": payment_id}


@app.get("/api/dashboard")
def dashboard(month: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$")):
    today_jalali = jdatetime.date.fromgregorian(date=date.today())
    selected_month = month or f"{today_jalali.year:04d}-{today_jalali.month:02d}"
    start, end = month_bounds_or_error(selected_month)
    installment_data = installment_rows("WHERE i.due_date >= ? AND i.due_date < ?", (start, end))
    with connection() as db:
        transaction_data = db.execute(
            """SELECT transaction_type, COALESCE(SUM(amount), 0) AS total
               FROM transactions WHERE occurred_on >= ? AND occurred_on < ? GROUP BY transaction_type""",
            (start, end),
        ).fetchall()
        paid_commitments = db.execute(
            """SELECT COALESCE(SUM(p.amount), 0) AS total FROM payments p
               WHERE p.paid_on >= ? AND p.paid_on < ?""",
            (start, end),
        ).fetchone()["total"]

    totals = {row["transaction_type"]: row["total"] for row in transaction_data}
    planned = sum(item["amount"] for item in installment_data)
    remaining = sum(item["remaining_amount"] for item in installment_data)
    overdue = installment_rows("WHERE i.due_date < ?", (date.today().isoformat(),))
    return {
        "month": selected_month,
        "month_label": jalali_month_label(selected_month),
        "income": totals.get("income", 0),
        "expense": totals.get("expense", 0),
        "planned_commitments": planned,
        "paid_commitments": paid_commitments,
        "remaining_commitments": remaining,
        "overdue_commitments": sum(item["remaining_amount"] for item in overdue),
        "upcoming": [item for item in installment_data if item["status"] != "paid"][:6],
    }


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(STATIC_DIR / "index.html")

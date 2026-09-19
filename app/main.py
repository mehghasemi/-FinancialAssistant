from __future__ import annotations

import calendar
import logging
import uuid
from datetime import date, datetime
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
from .database import RESOURCE_DIR, connection, initialize_database, write_audit_log


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title=APP_NAME, version=APP_VERSION)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=[*LOCAL_HOSTS])
STATIC_DIR = RESOURCE_DIR / "static"


def normalize_text(value: str) -> str:
    return " ".join(value.strip().split())


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


def serialize(row):
    return dict(row)


def add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def installment_rows(where: str = "", params: tuple = ()) -> list[dict]:
    query = f"""
        SELECT
            i.id, i.due_date, i.amount, i.note, c.id AS commitment_id,
            c.title, c.kind,
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
    due_dates = [add_months(payload.first_due_date, index * payload.interval_months) for index in range(payload.installment_count)]
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


@app.get("/api/installments")
def installments(month: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"), status: str | None = None):
    where, params = "", []
    if month:
        start, end = month_bounds_or_error(month)
        where = "WHERE i.due_date >= ? AND i.due_date < ?"
        params.extend((start, end))
    result = installment_rows(where, tuple(params))
    if status:
        result = [item for item in result if item["status"] == status]
    return result


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
        write_audit_log(db, "create", "payment", cursor.lastrowid, f"installment:{payload.installment_id}")
        return {"id": cursor.lastrowid}


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

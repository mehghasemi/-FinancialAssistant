from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from ..calendar import format_jalali_date
from ..database import connection, write_audit_log
from ..schemas import TransactionInput
from ..utils import month_bounds_or_error, serialize

router = APIRouter(prefix="/api", tags=["transactions"])


@router.get("/accounts")
def accounts():
    with connection() as db:
        return [serialize(row) for row in db.execute("SELECT id, name, kind FROM accounts ORDER BY id").fetchall()]


@router.get("/categories")
def categories(transaction_type: Literal["income", "expense"] | None = None):
    sql = "SELECT id, name, transaction_type FROM categories"
    params: tuple = ()
    if transaction_type:
        sql += " WHERE transaction_type = ?"
        params = (transaction_type,)
    sql += " ORDER BY transaction_type, name"
    with connection() as db:
        return [serialize(row) for row in db.execute(sql, params).fetchall()]


@router.post("/transactions", status_code=201)
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


@router.get("/transactions")
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

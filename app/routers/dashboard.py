from __future__ import annotations

from datetime import date

import jdatetime
from fastapi import APIRouter, Query

from ..calendar import jalali_month_label
from ..database import connection
from ..utils import installment_rows, month_bounds_or_error

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard")
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

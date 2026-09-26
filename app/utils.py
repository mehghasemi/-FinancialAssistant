from __future__ import annotations

from datetime import date

import jdatetime
from fastapi import HTTPException

from .calendar import format_jalali_date, jalali_month_bounds
from .database import connection


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


def serialize(row):
    return dict(row)


def add_months(value: date, months: int) -> date:
    jalali_value = jdatetime.date.fromgregorian(date=value)
    month_index = jalali_value.month - 1 + months
    year = jalali_value.year + month_index // 12
    month = month_index % 12 + 1
    maximum_day = 31 if month <= 6 else 30 if month <= 11 else 30 if jdatetime.date(year, 12, 1).isleap() else 29
    return jdatetime.date(year, month, min(jalali_value.day, maximum_day)).togregorian()


def planned_installments(payload) -> list[date]:
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

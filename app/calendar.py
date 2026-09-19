from __future__ import annotations

from datetime import date, datetime

import jdatetime


PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
MONTH_NAMES = (
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
)


def latin_digits(value: str) -> str:
    return str(value).translate(PERSIAN_DIGITS).strip()


def persian_digits(value: object) -> str:
    return str(value).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def parse_jalali_date(value: str | date) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    parts = latin_digits(value).replace("-", "/").split("/")
    if len(parts) != 3:
        raise ValueError("تاریخ را به‌شکل ۱۴۰۵/۰۶/۲۸ وارد کنید.")
    try:
        jalali = jdatetime.date(*(int(part) for part in parts))
        return jalali.togregorian()
    except (TypeError, ValueError) as error:
        raise ValueError("تاریخ شمسی معتبر نیست.") from error


def format_jalali_date(value: str | date | datetime) -> str:
    if isinstance(value, str):
        value = date.fromisoformat(value[:10])
    if isinstance(value, datetime):
        value = value.date()
    jalali = jdatetime.date.fromgregorian(date=value)
    return persian_digits(f"{jalali.year:04d}/{jalali.month:02d}/{jalali.day:02d}")


def jalali_month_bounds(value: str) -> tuple[date, date]:
    parts = latin_digits(value).replace("/", "-").split("-")
    if len(parts) != 2:
        raise ValueError("ماه را به‌شکل ۱۴۰۵-۰۶ انتخاب کنید.")
    try:
        year, month = (int(part) for part in parts)
        start = jdatetime.date(year, month, 1)
    except (TypeError, ValueError) as error:
        raise ValueError("ماه شمسی معتبر نیست.") from error
    next_month = jdatetime.date(year + 1, 1, 1) if month == 12 else jdatetime.date(year, month + 1, 1)
    return start.togregorian(), next_month.togregorian()


def jalali_month_label(value: str) -> str:
    year, month = (int(part) for part in latin_digits(value).replace("/", "-").split("-"))
    if not 1 <= month <= 12:
        raise ValueError("ماه شمسی معتبر نیست.")
    return f"{MONTH_NAMES[month - 1]} {persian_digits(year)}"


def format_jalali_datetime(value: str) -> str:
    instant = datetime.fromisoformat(value)
    return f"{format_jalali_date(instant.date())}، {persian_digits(instant.strftime('%H:%M'))}"

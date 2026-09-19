from __future__ import annotations

import sqlite3
from contextlib import contextmanager
import os
from pathlib import Path
import sys


ROOT_DIR = Path(__file__).resolve().parents[1]
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", ROOT_DIR))
if getattr(sys, "frozen", False):
    default_data_dir = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "FinancialAssistant"
else:
    default_data_dir = ROOT_DIR / "data"
DATA_DIR = Path(os.getenv("FINANCIAL_ASSISTANT_DATA_DIR", default_data_dir))
DATABASE_PATH = DATA_DIR / "financial_assistant.db"


def write_audit_log(db: sqlite3.Connection, action: str, resource_type: str, resource_id: int, details: str = "") -> None:
    db.execute(
        """INSERT INTO audit_logs(action, resource_type, resource_id, details)
           VALUES (?, ?, ?, ?)""",
        (action, resource_type, resource_id, details),
    )


@contextmanager
def connection():
    DATA_DIR.mkdir(exist_ok=True)
    db = sqlite3.connect(DATABASE_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def initialize_database() -> None:
    with connection() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                kind TEXT NOT NULL DEFAULT 'bank',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                transaction_type TEXT NOT NULL CHECK (transaction_type IN ('income', 'expense')),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY,
                transaction_type TEXT NOT NULL CHECK (transaction_type IN ('income', 'expense')),
                amount INTEGER NOT NULL CHECK (amount > 0),
                occurred_on TEXT NOT NULL,
                category_id INTEGER REFERENCES categories(id),
                account_id INTEGER REFERENCES accounts(id),
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS commitments (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                kind TEXT NOT NULL,
                total_amount INTEGER CHECK (total_amount IS NULL OR total_amount > 0),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS installments (
                id INTEGER PRIMARY KEY,
                commitment_id INTEGER NOT NULL REFERENCES commitments(id) ON DELETE CASCADE,
                due_date TEXT NOT NULL,
                amount INTEGER NOT NULL CHECK (amount > 0),
                note TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY,
                installment_id INTEGER NOT NULL REFERENCES installments(id) ON DELETE CASCADE,
                amount INTEGER NOT NULL CHECK (amount > 0),
                paid_on TEXT NOT NULL,
                account_id INTEGER REFERENCES accounts(id),
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY,
                action TEXT NOT NULL,
                resource_type TEXT NOT NULL,
                resource_id INTEGER NOT NULL,
                details TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS release_history (
                version TEXT PRIMARY KEY,
                released_at TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                affected_areas TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_transactions_occurred_on ON transactions(occurred_on);
            CREATE INDEX IF NOT EXISTS idx_installments_due_date ON installments(due_date);
            CREATE INDEX IF NOT EXISTS idx_payments_paid_on ON payments(paid_on);
            CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at DESC);
            """
        )

        accounts = ("حساب اصلی", "کارت بانکی", "نقدی")
        db.executemany("INSERT OR IGNORE INTO accounts(name) VALUES (?)", ((name,) for name in accounts))

        categories = (
            ("درآمد شغلی", "income"),
            ("درآمد دیگر", "income"),
            ("خانه", "expense"),
            ("خوراک", "expense"),
            ("حمل‌ونقل", "expense"),
            ("درمان", "expense"),
            ("آموزش", "expense"),
            ("سایر", "expense"),
        )
        db.executemany(
            "INSERT OR IGNORE INTO categories(name, transaction_type) VALUES (?, ?)", categories
        )
        db.execute(
            """INSERT OR IGNORE INTO release_history(version, released_at, title, description, affected_areas)
               VALUES ('0.2.0', '2026-09-19T00:00:00+03:30', 'پایهٔ قابل استفاده',
                       'ثبت تراکنش، تعهد، سررسید و پرداخت جزئی با دیتابیس محلی.',
                       'رابط کاربری، API، منطق مالی، SQLite و مستندات')"""
        )
        db.execute(
            """INSERT OR IGNORE INTO release_history(version, released_at, title, description, affected_areas)
               VALUES ('0.3.0', '2026-09-19T00:00:00+03:30', 'تقویم شمسی',
                       'ورود، نمایش و فیلتر تاریخ‌ها با تقویم جلالی و نام ماه‌های فارسی.',
                       'رابط کاربری، API، گزارش‌ها و مستندات')"""
        )

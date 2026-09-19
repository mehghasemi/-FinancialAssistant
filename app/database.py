from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
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


def create_database_backup(destination: str | Path) -> Path:
    backup_dir = Path(destination).expanduser().resolve()
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = backup_dir / f"financial_assistant_backup_{timestamp}.db"
    source = sqlite3.connect(DATABASE_PATH)
    target = sqlite3.connect(backup_path)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    return backup_path


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

            CREATE TABLE IF NOT EXISTS data_migrations (
                migration_key TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS app_settings (
                setting_key TEXT PRIMARY KEY,
                setting_value TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS import_runs (
                id INTEGER PRIMARY KEY,
                source_name TEXT NOT NULL,
                source_path TEXT NOT NULL,
                workbook_hash TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
                total_rows INTEGER NOT NULL DEFAULT 0,
                mapped_commitments INTEGER NOT NULL DEFAULT 0,
                mapped_installments INTEGER NOT NULL DEFAULT 0,
                mapped_payments INTEGER NOT NULL DEFAULT 0,
                mapped_budget_items INTEGER NOT NULL DEFAULT 0,
                imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                completed_at TEXT,
                error_message TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS imported_rows (
                id INTEGER PRIMARY KEY,
                import_id INTEGER NOT NULL REFERENCES import_runs(id) ON DELETE CASCADE,
                sheet_name TEXT NOT NULL,
                source_row INTEGER NOT NULL,
                record_type TEXT NOT NULL DEFAULT 'raw',
                data_json TEXT NOT NULL,
                UNIQUE(import_id, sheet_name, source_row)
            );

            CREATE TABLE IF NOT EXISTS budget_items (
                id INTEGER PRIMARY KEY,
                fiscal_year INTEGER NOT NULL,
                category_name TEXT NOT NULL,
                jalali_month INTEGER NOT NULL CHECK (jalali_month BETWEEN 1 AND 12),
                amount INTEGER NOT NULL CHECK (amount >= 0),
                import_id INTEGER REFERENCES import_runs(id) ON DELETE SET NULL,
                source_key TEXT UNIQUE,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_transactions_occurred_on ON transactions(occurred_on);
            CREATE INDEX IF NOT EXISTS idx_installments_due_date ON installments(due_date);
            CREATE INDEX IF NOT EXISTS idx_payments_paid_on ON payments(paid_on);
            CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_imported_rows_import_sheet ON imported_rows(import_id, sheet_name);
            CREATE INDEX IF NOT EXISTS idx_budget_items_year_month ON budget_items(fiscal_year, jalali_month);
            """
        )

        _ensure_column(db, "commitments", "source_key TEXT")
        _ensure_column(db, "installments", "source_key TEXT")
        _ensure_column(db, "payments", "source_key TEXT")
        _ensure_column(db, "transactions", "source_key TEXT")
        db.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_commitments_source_key "
            "ON commitments(source_key) WHERE source_key IS NOT NULL"
        )
        db.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_installments_source_key "
            "ON installments(source_key) WHERE source_key IS NOT NULL"
        )
        db.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_payments_source_key "
            "ON payments(source_key) WHERE source_key IS NOT NULL"
        )
        db.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_transactions_source_key "
            "ON transactions(source_key) WHERE source_key IS NOT NULL"
        )
        _apply_rial_to_toman_migration(db)
        db.execute(
            "INSERT OR IGNORE INTO app_settings(setting_key, setting_value) VALUES ('backup_enabled', 'true')"
        )
        db.execute(
            "INSERT OR IGNORE INTO app_settings(setting_key, setting_value) VALUES ('backup_directory', ?)",
            (str(DATA_DIR / "backups"),),
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
               VALUES ('0.4.0', '2026-09-19T00:00:00+03:30', 'واردسازی اکسل',
                       'بایگانی کامل ردیف‌های اکسل و تبدیل امن تعهدات مالی و بودجه‌ها به داده‌های عملیاتی.',
                       'دیتابیس محلی، واردسازی، تعهدات، اقساط و بودجه')"""
        )
        db.execute(
            """INSERT OR IGNORE INTO release_history(version, released_at, title, description, affected_areas)
               VALUES ('0.4.1', '2026-09-19T00:00:00+03:30', 'راهنمای سیستم',
                       'انتقال توضیح محل نگهداری داده‌ها از نوار کناری به صفحهٔ راهنمای سیستم.',
                       'رابط کاربری و راهنما')"""
        )
        db.execute(
            """INSERT OR IGNORE INTO release_history(version, released_at, title, description, affected_areas)
               VALUES ('0.5.0', '2026-09-19T00:00:00+03:30', 'مدیریت تعهدات و اقساط',
                       'تعریف یکجای تعهد، پیش‌نمایش اقساط، فیلتر گرید و ثبت پرداخت از همان ردیف.',
                       'تعهدات مالی، اقساط و پرداخت‌ها')"""
        )
        db.execute(
            """INSERT OR IGNORE INTO release_history(version, released_at, title, description, affected_areas)
               VALUES ('0.5.1', '2026-09-19T00:00:00+03:30', 'فیلتر یکتای تعهدات',
                       'نمایش هر ترکیب عنوان و مبلغ کل فقط یک‌بار در فیلتر تعهدات.',
                       'فیلتر اقساط')"""
        )
        db.execute(
            """INSERT OR IGNORE INTO release_history(version, released_at, title, description, affected_areas)
               VALUES ('0.5.2', '2026-09-19T00:00:00+03:30', 'تبدیل ریال به تومان',
                       'تبدیل یک‌بارهٔ مبالغ عملیاتی و نمایش جداکنندهٔ هزارگان.',
                       'مبالغ، فیلتر تعهدات و رابط کاربری')"""
        )
        db.execute(
            """INSERT OR IGNORE INTO release_history(version, released_at, title, description, affected_areas)
               VALUES ('0.6.0', '2026-09-19T00:00:00+03:30', 'پشتیبان‌گیری و ویرایش تعهدات',
                       'تنظیمات پشتیبان‌گیری، فیلتر وضعیت هوشمند و ویرایش کلی و جزئی تعهدات.',
                       'تنظیمات، پشتیبان‌گیری، تعهدات و اقساط')"""
        )
        db.execute(
            """INSERT OR IGNORE INTO release_history(version, released_at, title, description, affected_areas)
               VALUES ('0.6.1', '2026-09-19T00:00:00+03:30', 'گرید تعهدات',
                       'افزودن فهرست مستقل تعهدات و ویرایش کلی هر تعهد در همان گرید.',
                       'مدیریت تعهدات')"""
        )
        db.execute(
            """INSERT OR IGNORE INTO release_history(version, released_at, title, description, affected_areas)
               VALUES ('0.3.0', '2026-09-19T00:00:00+03:30', 'تقویم شمسی',
                       'ورود، نمایش و فیلتر تاریخ‌ها با تقویم جلالی و نام ماه‌های فارسی.',
                       'رابط کاربری، API، گزارش‌ها و مستندات')"""
        )


def _ensure_column(db: sqlite3.Connection, table: str, definition: str) -> None:
    column_name = definition.split()[0]
    columns = {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}
    if column_name not in columns:
        db.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")


def _apply_rial_to_toman_migration(db: sqlite3.Connection) -> None:
    migration_key = "rial_amounts_to_toman_20260919"
    if db.execute("SELECT 1 FROM data_migrations WHERE migration_key = ?", (migration_key,)).fetchone():
        return
    for table, column in (
        ("transactions", "amount"),
        ("commitments", "total_amount"),
        ("installments", "amount"),
        ("payments", "amount"),
        ("budget_items", "amount"),
    ):
        db.execute(f"UPDATE {table} SET {column} = CAST({column} / 10 AS INTEGER) WHERE {column} IS NOT NULL")
    db.execute("INSERT INTO data_migrations(migration_key) VALUES (?)", (migration_key,))


def get_setting(key: str, default: str = "") -> str:
    with connection() as db:
        row = db.execute("SELECT setting_value FROM app_settings WHERE setting_key = ?", (key,)).fetchone()
    return row["setting_value"] if row else default


def set_setting(key: str, value: str) -> None:
    with connection() as db:
        db.execute(
            """INSERT INTO app_settings(setting_key, setting_value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(setting_key) DO UPDATE SET setting_value = excluded.setting_value, updated_at = CURRENT_TIMESTAMP""",
            (key, value),
        )

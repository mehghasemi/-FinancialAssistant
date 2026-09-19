import tempfile
import unittest
from datetime import date
from pathlib import Path

import app.database as database
from app import main


class FinancialFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_data_dir, self.old_database_path = database.DATA_DIR, database.DATABASE_PATH
        database.DATA_DIR = Path(self.temp_dir.name)
        database.DATABASE_PATH = Path(self.temp_dir.name) / "financial-assistant-test.db"
        database.initialize_database()

    def tearDown(self):
        database.DATA_DIR, database.DATABASE_PATH = self.old_data_dir, self.old_database_path
        self.temp_dir.cleanup()

    def test_partial_payment_reduces_installment_balance(self):
        main.create_commitment(main.CommitmentInput(
            title="وام آزمایشی", kind="وام", total_amount=3_000_000,
            installment_amount=1_000_000, first_due_date=date(2026, 10, 1), installment_count=3,
        ))
        installment = main.installments(month="1405-07")[0]
        main.create_payment(main.PaymentInput(
            installment_id=installment["id"], amount=400_000,
            paid_on=date(2026, 10, 1), account_id=1,
        ))
        updated = main.installments(month="1405-07")[0]
        self.assertEqual(updated["status"], "partial")
        self.assertEqual(updated["paid_amount"], 400_000)
        self.assertEqual(updated["remaining_amount"], 600_000)

    def test_payment_cannot_exceed_remaining_balance(self):
        main.create_commitment(main.CommitmentInput(
            title="وام آزمایشی", kind="وام", installment_amount=1_000_000,
            first_due_date=date(2026, 10, 1), installment_count=1,
        ))
        installment = main.installments(month="1405-07")[0]
        with self.assertRaises(Exception):
            main.create_payment(main.PaymentInput(
                installment_id=installment["id"], amount=1_000_001,
                paid_on=date(2026, 10, 1), account_id=1,
            ))

    def test_commitment_preview_creates_all_installments_before_save(self):
        preview = main.preview_commitment(main.CommitmentInput(
            title="وام ده قسطه", kind="وام", total_amount=10_000_000,
            installment_amount=1_000_000, first_due_date=date(2026, 10, 1),
            installment_count=10, interval_months=1,
        ))
        self.assertEqual(len(preview["installments"]), 10)
        self.assertEqual(preview["planned_total"], 10_000_000)
        self.assertEqual(preview["first_due_date"], "۱۴۰۵/۰۷/۰۹")
        self.assertEqual(preview["last_due_date"], "۱۴۰۶/۰۴/۰۹")

    def test_installment_filter_by_commitment_and_status(self):
        first = main.create_commitment(main.CommitmentInput(
            title="وام اول", kind="وام", installment_amount=1_000_000,
            first_due_date=date(2026, 10, 1), installment_count=1,
        ))
        main.create_commitment(main.CommitmentInput(
            title="وام دوم", kind="وام", installment_amount=2_000_000,
            first_due_date=date(2026, 10, 1), installment_count=1,
        ))
        filtered = main.installments(commitment_id=first["id"], status="unpaid")
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["title"], "وام اول")

    def test_installment_filter_by_unique_title_and_total(self):
        main.create_commitment(main.CommitmentInput(
            title="وام مشابه", kind="وام", total_amount=10_000_000,
            installment_amount=1_000_000, first_due_date=date(2026, 10, 1), installment_count=1,
        ))
        main.create_commitment(main.CommitmentInput(
            title="وام مشابه", kind="وام", total_amount=20_000_000,
            installment_amount=2_000_000, first_due_date=date(2026, 10, 1), installment_count=1,
        ))
        filtered = main.installments(commitment_title="وام مشابه", commitment_total=10_000_000)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["amount"], 1_000_000)

    def test_rial_to_toman_migration_runs_only_once(self):
        with database.connection() as db:
            db.execute("INSERT INTO commitments(title, kind, total_amount) VALUES ('تبدیل', 'وام', 1000)")
            commitment_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
            db.execute("INSERT INTO installments(commitment_id, due_date, amount) VALUES (?, '2026-10-01', 500)", (commitment_id,))
            installment_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
            db.execute("INSERT INTO payments(installment_id, amount, paid_on) VALUES (?, 200, '2026-10-01')", (installment_id,))
            db.execute("DELETE FROM data_migrations WHERE migration_key = 'rial_amounts_to_toman_20260919'")
        database.initialize_database()
        with database.connection() as db:
            self.assertEqual(db.execute("SELECT total_amount FROM commitments WHERE id = ?", (commitment_id,)).fetchone()[0], 100)
            self.assertEqual(db.execute("SELECT amount FROM installments WHERE id = ?", (installment_id,)).fetchone()[0], 50)
            self.assertEqual(db.execute("SELECT amount FROM payments WHERE installment_id = ?", (installment_id,)).fetchone()[0], 20)
        database.initialize_database()
        with database.connection() as db:
            self.assertEqual(db.execute("SELECT total_amount FROM commitments WHERE id = ?", (commitment_id,)).fetchone()[0], 100)

    def test_backup_and_commitment_edits(self):
        created = main.create_commitment(main.CommitmentInput(
            title="تعهد قابل ویرایش", kind="وام", total_amount=2_000_000,
            installment_amount=1_000_000, first_due_date=date(2026, 10, 1), installment_count=2,
        ))
        main.update_commitment(created["id"], main.CommitmentUpdate(
            title="تعهد ویرایش‌شده", kind="بدهی", total_amount=2_500_000,
        ))
        installment = main.installments(commitment_id=created["id"])[0]
        main.update_installment(installment["id"], main.InstallmentUpdate(
            due_date=date(2026, 10, 2), amount=1_100_000, note="تغییر دستی",
        ))
        updated = main.installments(commitment_id=created["id"])[0]
        self.assertEqual(updated["title"], "تعهد ویرایش‌شده")
        self.assertEqual(updated["kind"], "بدهی")
        self.assertEqual(updated["amount"], 1_100_000)
        self.assertEqual(updated["note"], "تغییر دستی")
        backup = database.create_database_backup(Path(self.temp_dir.name) / "backups")
        self.assertTrue(backup.is_file())

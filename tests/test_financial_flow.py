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

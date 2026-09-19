import unittest
from datetime import date

from app.calendar import format_jalali_date, jalali_month_bounds, jalali_month_label, parse_jalali_date


class JalaliCalendarTests(unittest.TestCase):
    def test_known_jalali_date_converts_to_gregorian(self):
        self.assertEqual(parse_jalali_date("۱۴۰۵/۰۶/۲۸"), date(2026, 9, 19))

    def test_gregorian_date_displays_as_jalali(self):
        self.assertEqual(format_jalali_date(date(2026, 9, 19)), "۱۴۰۵/۰۶/۲۸")

    def test_month_has_persian_name_and_correct_bounds(self):
        start, end = jalali_month_bounds("1405-06")
        self.assertEqual((start, end), (date(2026, 8, 23), date(2026, 9, 23)))
        self.assertEqual(jalali_month_label("1405-06"), "شهریور ۱۴۰۵")

# همراه مالی

وب‌اپ شخصیِ محلی برای مدیریت درآمد، هزینه، بودجه و تعهدات مالی.

## مشاهدهٔ نمونه

در PowerShell اجرا کنید:

```powershell
.\run.ps1
```

سپس `http://127.0.0.1:8000` را در مرورگر باز کنید. در اجرای اول، فایل دیتابیس در `data/financial_assistant.db` ساخته می‌شود.

## اجرای یک‌کلیکی در ویندوز

پس از ساخت بستهٔ نهایی، روی `dist/FinancialAssistant.exe` دوبار کلیک کنید. برنامه مرورگر پیش‌فرض را باز می‌کند و دیتابیس شخصی را در `%LOCALAPPDATA%/FinancialAssistant/financial_assistant.db` نگه می‌دارد.

## تصمیم معماری پیشنهادی

- رابط کاربری: HTML/CSS/JavaScript (در فاز بعد قابل انتقال به React + TypeScript)
- API محلی: FastAPI
- دیتابیس محلی: SQLite
- لایهٔ داده: SQLAlchemy و migration نسخه‌دار
- اجرا: یک سرویس محلی که فقط روی `localhost` در دسترس است

جداسازی «تعهد»، «سررسید» و «پرداخت» اصل محوری مدل داده است. با این کار پرداختِ جزئی، پرداخت با تأخیر و گزارش‌های برنامه‌ای در برابر واقعی، قابل اتکا می‌شوند.

جزئیات فازها در [docs/project-phases.md](docs/project-phases.md) آمده است.

## مستندات

- [معماری](docs/architecture.md)
- [قرارداد API](docs/api.md)
- [تاریخچهٔ تغییرات](CHANGELOG.md)
- [تنظیمات نمونه](.env.example)

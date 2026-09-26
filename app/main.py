from __future__ import annotations

import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .config import APP_NAME, APP_VERSION, LOCAL_HOSTS
from .database import RESOURCE_DIR, create_database_backup, get_setting, initialize_database
from .routers import commitments, dashboard, settings, transactions

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title=APP_NAME, version=APP_VERSION)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=[*LOCAL_HOSTS])
STATIC_DIR = RESOURCE_DIR / "static"

app.include_router(transactions.router)
app.include_router(commitments.router)
app.include_router(dashboard.router)
app.include_router(settings.router)


@app.on_event("startup")
def startup() -> None:
    initialize_database()


@app.on_event("shutdown")
def shutdown() -> None:
    if get_setting("backup_enabled", "true") != "true":
        return
    try:
        create_database_backup(get_setting("backup_directory", ""))
    except Exception:
        logger.exception("Automatic database backup failed during shutdown")


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, error: Exception):
    error_id = uuid.uuid4().hex[:10]
    logger.exception("Unhandled error %s at %s", error_id, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "خطای غیرمنتظره رخ داد. دوباره تلاش کنید؛ اگر ادامه داشت، شناسهٔ پیگیری را نگه دارید.", "error_id": error_id},
        headers={"X-Error-Id": error_id},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, error: RequestValidationError):
    fields = [".".join(str(part) for part in item["loc"] if part != "body") for item in error.errors()]
    return JSONResponse(
        status_code=422,
        content={"detail": "اطلاعات واردشده معتبر نیست. فیلدهای ضروری را بررسی کنید.", "fields": fields},
    )


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(STATIC_DIR / "index.html")

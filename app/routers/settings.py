from __future__ import annotations

from fastapi import APIRouter, Query

from ..calendar import format_jalali_datetime
from ..config import APP_VERSION, MAX_PAGE_SIZE
from ..database import connection, create_database_backup, get_setting, set_setting
from ..schemas import SettingsInput
from ..utils import serialize

router = APIRouter(prefix="/api", tags=["settings"])


@router.get("/health")
def health():
    return {"status": "ok", "database": "sqlite", "version": APP_VERSION}


@router.get("/settings")
def settings():
    return {
        "backup_enabled": get_setting("backup_enabled", "true") == "true",
        "backup_directory": get_setting("backup_directory", ""),
    }


@router.put("/settings")
def update_settings(payload: SettingsInput):
    set_setting("backup_enabled", "true" if payload.backup_enabled else "false")
    set_setting("backup_directory", payload.backup_directory)
    return settings()


@router.post("/backups", status_code=201)
def create_backup():
    backup_path = create_database_backup(get_setting("backup_directory", ""))
    return {"path": str(backup_path)}


@router.get("/releases")
def releases(limit: int = Query(default=20, ge=1, le=MAX_PAGE_SIZE)):
    with connection() as db:
        result = [serialize(row) for row in db.execute(
            """SELECT version, released_at, title, description, affected_areas
               FROM release_history ORDER BY released_at DESC LIMIT ?""", (limit,)
        ).fetchall()]
    for item in result:
        item["released_at"] = format_jalali_datetime(item["released_at"])
    return result

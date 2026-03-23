from __future__ import annotations

import shutil
from pathlib import Path

from nonebot import logger, require

require("nonebot_plugin_localstore")
import nonebot_plugin_localstore as localstore

PLUGIN_DATA_DIR_NAME = "nonebot_plugin_cs2radar"
LEGACY_DATA_DIRS = [
    Path("data/cs_pro"),
    Path("data/csstats"),
    Path("data/astrbot_plugin_csstats"),
]


def get_data_dir() -> Path:
    return localstore.get_plugin_data_dir()


def get_bind_db_path(configured_path: str | None = None) -> Path:
    raw = str(configured_path or "").strip()
    if raw:
        return Path(raw)
    return get_data_dir() / "user_bindings.db"


def get_pw_session_path() -> Path:
    return get_data_dir() / "pw_session.json"


def migrate_legacy_file(filename: str, target_path: Path) -> Path:
    if target_path.exists():
        return target_path

    for legacy_dir in LEGACY_DATA_DIRS:
        legacy_path = legacy_dir / filename
        if not legacy_path.exists() or legacy_path.resolve() == target_path.resolve():
            continue
        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(legacy_path, target_path)
            logger.info(f"[nonebot_plugin_cs2radar] migrated legacy file from {legacy_path} to {target_path}")
            return target_path
        except Exception as exc:
            logger.warning(f"[nonebot_plugin_cs2radar] failed to migrate legacy file {legacy_path}: {exc}")
    return target_path

from __future__ import annotations

import asyncio
import json
import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

TRUSTED_IMAGE_HOST_SUFFIXES = (
    "5eplay.com",
    "5eplaycdn.com",
    "wmpvp.com",
    "pwesports.cn",
    "csgo.com.cn",
    "viki.moe",
    "hltv.org",
    "steamstatic.com",
    "akamaihd.net",
)
DEFAULT_IMAGE_URL = "https://static.5eplay.com/images/common/player_default.png"

CSP_META = (
    '<meta http-equiv="Content-Security-Policy" content="'
    "default-src 'none'; "
    "script-src 'none'; connect-src 'none'; object-src 'none'; frame-src 'none'; "
    "base-uri 'none'; form-action 'none'; "
    "style-src 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src data: https://fonts.gstatic.com; "
    "img-src data: https://*.5eplay.com https://5eplay.com "
    "https://*.5eplaycdn.com https://5eplaycdn.com "
    "https://*.wmpvp.com https://wmpvp.com "
    "https://*.pwesports.cn https://pwesports.cn "
    "https://*.csgo.com.cn https://csgo.com.cn "
    "https://*.viki.moe https://viki.moe "
    "https://*.hltv.org https://hltv.org "
    "https://*.steamstatic.com https://steamstatic.com "
    "https://*.akamaihd.net https://akamaihd.net;"
    '">'
)


def _host_is_trusted(host: str) -> bool:
    normalized = host.rstrip(".").lower()
    return any(
        normalized == suffix or normalized.endswith(f".{suffix}")
        for suffix in TRUSTED_IMAGE_HOST_SUFFIXES
    )


def safe_image_url(value: Any, fallback: str = DEFAULT_IMAGE_URL) -> str:
    """Return a trusted HTTPS image URL or a trusted fallback."""
    raw = str(value or "").strip()
    try:
        parsed = urlsplit(raw)
        port = parsed.port
    except ValueError:
        parsed = None
        port = None

    if (
        parsed
        and parsed.scheme.lower() == "https"
        and parsed.hostname
        and parsed.username is None
        and parsed.password is None
        and port in (None, 443)
        and _host_is_trusted(parsed.hostname)
    ):
        return raw

    if fallback and fallback != raw:
        return safe_image_url(fallback)
    return ""


def inject_csp(html: str) -> str:
    if "<head>" in html:
        return html.replace("<head>", f"<head>{CSP_META}", 1)
    return f"{CSP_META}{html}"


def ensure_private_file(path: Path) -> None:
    if not path.exists():
        return
    try:
        path.chmod(0o600)
    except OSError:
        # Windows ACLs are not represented by POSIX mode bits.
        pass


def secure_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Atomically write JSON and restrict POSIX permissions to the owner."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(temp_path, flags, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
        ensure_private_file(path)
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass


class GuardRejected(RuntimeError):
    pass


class CommandGuard:
    _MAX_TRACKED_USERS = 4096

    def __init__(self, max_concurrency: int, cooldown_seconds: int) -> None:
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._cooldown_seconds = max(0, cooldown_seconds)
        self._state_lock = asyncio.Lock()
        self._last_used: dict[tuple[str, str], float] = {}
        self._last_cleanup = 0.0

    def _prune_expired(self, now: float) -> None:
        if self._cooldown_seconds <= 0:
            self._last_used.clear()
            return
        cleanup_interval = max(10.0, float(self._cooldown_seconds))
        if len(self._last_used) < 1024 and now - self._last_cleanup < cleanup_interval:
            return
        cutoff = now - self._cooldown_seconds
        self._last_used = {
            key: last_used
            for key, last_used in self._last_used.items()
            if last_used > cutoff
        }
        self._last_cleanup = now

    @asynccontextmanager
    async def acquire(self, user_id: str, command: str) -> AsyncIterator[None]:
        try:
            await asyncio.wait_for(self._semaphore.acquire(), timeout=0.1)
        except asyncio.TimeoutError as exc:
            raise GuardRejected("当前查询人数较多，请稍后再试。") from exc

        try:
            now = time.monotonic()
            key = (str(user_id), command)
            async with self._state_lock:
                self._prune_expired(now)
                last_used = self._last_used.get(key, 0.0)
                remaining = self._cooldown_seconds - (now - last_used)
                if remaining > 0:
                    raise GuardRejected(f"操作过于频繁，请等待 {max(1, int(remaining) + 1)} 秒。")
                if self._cooldown_seconds > 0:
                    self._last_used[key] = now
                    if len(self._last_used) > self._MAX_TRACKED_USERS:
                        oldest_key = min(self._last_used, key=self._last_used.get)
                        self._last_used.pop(oldest_key, None)
            yield
        finally:
            self._semaphore.release()

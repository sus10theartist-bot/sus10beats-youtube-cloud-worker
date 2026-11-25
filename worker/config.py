"""Environment configuration with safe defaults and strict validation."""
from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse


def _positive_int(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)).strip())
    except ValueError as exc:
        raise ValueError(f"{name} must be a whole number.") from exc
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero.")
    return value


def _bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    return default if raw is None else raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    api_base_url: str
    shared_secret: str
    publish_enabled: bool
    allowed_asset_hosts: frozenset[str]
    max_audio_bytes: int
    max_cover_bytes: int
    max_video_seconds: int

    @classmethod
    def from_env(cls) -> "Settings":
        base = os.getenv("SITE_API_BASE_URL", "").strip().rstrip("/")
        secret = os.getenv("SITE_WORKER_SHARED_SECRET", "").strip()
        hosts: set[str] = set()
        if base:
            parsed = urlparse(base)
            if parsed.scheme != "https" or not parsed.hostname:
                raise ValueError("SITE_API_BASE_URL must be an HTTPS URL.")
            if parsed.username or parsed.password:
                raise ValueError("SITE_API_BASE_URL must not contain credentials.")
            hosts.add(parsed.hostname.lower())
        extras = os.getenv("SITE_ALLOWED_ASSET_HOSTS", "")
        hosts.update(v.strip().lower() for v in extras.split(",") if v.strip())
        return cls(
            api_base_url=base,
            shared_secret=secret,
            publish_enabled=_bool("WORKER_PUBLISH_ENABLED", False),
            allowed_asset_hosts=frozenset(hosts),
            max_audio_bytes=_positive_int("MAX_AUDIO_MB", 200) * 1024 * 1024,
            max_cover_bytes=_positive_int("MAX_COVER_MB", 15) * 1024 * 1024,
            max_video_seconds=_positive_int("MAX_VIDEO_SECONDS", 900),
        )

    def ready_for_marketplace(self) -> bool:
        return bool(self.api_base_url and len(self.shared_secret.encode("utf-8")) >= 32)

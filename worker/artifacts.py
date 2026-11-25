"""Upload rendered MP4s to short-lived private object-storage URLs."""
from __future__ import annotations

import os
from pathlib import Path

import requests

from worker.assets import validate_asset_url


def upload_rendered_artifact(
    video_path: str,
    upload_url: str,
    allowed_hosts: frozenset[str],
) -> None:
    validate_asset_url(upload_url, allowed_hosts)
    size = Path(video_path).stat().st_size
    if size <= 0:
        raise ValueError("Rendered video file is empty.")
    with open(video_path, "rb") as source:
        response = requests.put(
            upload_url,
            data=source,
            headers={"Content-Type": "video/mp4", "Content-Length": str(size)},
            timeout=(20, 900),
            allow_redirects=False,
        )
    try:
        response.raise_for_status()
    finally:
        response.close()

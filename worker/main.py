"""One-shot worker entry point used by GitHub Actions."""
from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
import uuid
from pathlib import Path

from worker.artifacts import upload_rendered_artifact
from worker.assets import download_asset
from worker.client import MarketplaceClient
from worker.config import Settings
from worker.renderer import render_video


def _required_string(value: object, field: str, limit: int = 2048) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Missing required job field: {field}.")
    return value.strip()[:limit]


def _job_id(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", value):
        raise ValueError("Marketplace returned an invalid job ID.")
    return value


def health_check() -> int:
    settings = Settings.from_env()
    print("Sus10 Beats cloud worker configuration")
    print(f"Marketplace URL configured: {'yes' if settings.api_base_url else 'no'}")
    print(f"Worker signing secret configured: {'yes' if len(settings.shared_secret.encode()) >= 32 else 'no'}")
    print(f"Trusted media/storage hosts configured: {len(settings.allowed_asset_hosts)}")
    print(f"YouTube publishing enabled: {'yes' if settings.publish_enabled else 'no'}")
    print("YouTube upload capability: not implemented; publishing remains blocked")
    return 0


def run_once() -> int:
    settings = Settings.from_env()
    if settings.publish_enabled:
        print("Unsafe configuration: this foundation release cannot publish. Set WORKER_PUBLISH_ENABLED=false.")
        return 1
    if not settings.ready_for_marketplace():
        print("Worker is installed. Marketplace URL and a 32+ byte shared secret are still required; no job was claimed.")
        return 0
    if not settings.allowed_asset_hosts:
        print("No trusted media or storage hosts are configured; no job was claimed.")
        return 1

    client = MarketplaceClient(settings.api_base_url, settings.shared_secret)
    worker_id = os.getenv("GITHUB_RUN_ID", f"manual-{uuid.uuid4().hex[:12]}")
    worker_id += "-" + os.getenv("GITHUB_RUN_ATTEMPT", "1")
    job = client.claim_job(worker_id)
    if job is None:
        print("Queue check complete: no approved video jobs are waiting.")
        return 0

    job_id = _job_id(job.get("job_id"))
    lease_token = _required_string(job.get("lease_token"), "lease_token", 512)
    audio_path = cover_path = video_path = None
    try:
        title = _required_string(job.get("title"), "title", 90)
        producer = _required_string(job.get("producer_name"), "producer_name", 60)
        audio_url = _required_string(job.get("audio_url"), "audio_url")
        cover_url = _required_string(job.get("cover_url"), "cover_url")
        upload_url = _required_string(job.get("artifact_upload_url"), "artifact_upload_url")
        artifact_key = _required_string(job.get("artifact_key"), "artifact_key", 512)

        audio_path = download_asset(audio_url, settings.allowed_asset_hosts, settings.max_audio_bytes, ".audio")
        cover_path = download_asset(cover_url, settings.allowed_asset_hosts, settings.max_cover_bytes, ".cover")
        video_path, duration = render_video(
            audio_path, cover_path, title, producer, settings.max_video_seconds
        )
        size_bytes = Path(video_path).stat().st_size

        # A job is only reported as rendered after the MP4 is safely stored.
        upload_rendered_artifact(video_path, upload_url, settings.allowed_asset_hosts)
        result = {
            "render_version": "promo-video-v1",
            "duration_seconds": round(duration, 2),
            "size_bytes": size_bytes,
            "filename": "sus10-beats-promo.mp4",
            "artifact_key": artifact_key,
            "publishing_state": "disabled",
        }
        client.report_rendered(job_id, lease_token, result)
        print(f"Job {job_id} rendered, privately stored, and reported for review.")
        return 0
    except Exception as exc:
        # Deliberately generic: do not leak signed URLs, server paths, or tracebacks.
        print(f"Job {job_id} could not be completed ({type(exc).__name__}).")
        try:
            client.report_failed(job_id, lease_token, "worker_job_failed", "The cloud worker could not finish this job. Check the worker run logs.")
        except Exception:
            print(f"Job {job_id}: failure callback could not be delivered.")
        return 1
    finally:
        for path in (audio_path, cover_path, video_path):
            if path:
                try:
                    os.unlink(path)
                except OSError:
                    pass
        if video_path:
            shutil.rmtree(str(Path(video_path).parent), ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Sus10 Beats cloud video worker")
    parser.add_argument("--health-check", action="store_true", help="check configuration without contacting the marketplace")
    args = parser.parse_args()
    try:
        return health_check() if args.health_check else run_once()
    except Exception as exc:
        print(f"Worker stopped safely ({type(exc).__name__}): {str(exc)[:180]}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

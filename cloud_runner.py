#!/usr/bin/env python3
"""One-shot, GitHub-hosted cloud runner for Sus10 Beats YouTube jobs.

No desktop process, local worker configuration file, MySQL connection, Google
Client Secret, or YouTube refresh token is stored in this repository.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from typing import Any
from urllib.parse import urlparse

import requests

import worker

VERSION = "1.1.0-cloud"
EXPECTED_HOST = "sus10beats.great-site.net"
WORKER_NAME = "sus10-github-actions-cloud"


def build_config(site_url: str | None = None, worker_secret: str | None = None) -> dict[str, Any]:
    site = (site_url if site_url is not None else os.getenv("SUS10_SITE_URL", "https://sus10beats.great-site.net")).strip().rstrip("/")
    secret = (worker_secret if worker_secret is not None else os.getenv("SUS10_WORKER_SECRET", "")).strip()
    parsed = urlparse(site)
    if parsed.scheme != "https" or parsed.netloc.lower() != EXPECTED_HOST or parsed.path or parsed.query or parsed.fragment:
        raise worker.WorkerError(f"SUS10_SITE_URL must be exactly https://{EXPECTED_HOST} with no path or query.")
    if len(secret) < 40:
        raise worker.WorkerError("SUS10_WORKER_SECRET is missing or too short. Add it as a GitHub Actions repository secret.")
    if any(ord(ch) < 33 or ord(ch) > 126 for ch in secret):
        raise worker.WorkerError("SUS10_WORKER_SECRET must contain printable, non-space ASCII characters.")
    return {
        "site_url": site,
        "worker_secret": secret,
        "worker_name": WORKER_NAME,
    }


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": f"Sus10BeatsGitHubCloudWorker/{VERSION}"})
    return session


def probe(config: dict[str, Any]) -> int:
    """Verify signed HTTPS bridge access without claiming or consuming a job."""
    session = make_session()
    payload = {"worker_name": WORKER_NAME, "version": VERSION, "mode": "probe"}
    result = worker.signed_json_request(
        session, config, "POST", "/bridge/youtube/v1/heartbeat", payload, timeout=45
    )
    if not result.get("ok"):
        raise worker.WorkerError("The website did not confirm the cloud-worker heartbeat.")
    if not result.get("heartbeat_saved"):
        raise worker.WorkerError("The bridge was reached, but the website could not save its heartbeat. Check that storage/cache is writable on the website host.")
    expected = "UCER9nZgssKit3V6B_JSgv3A"
    actual = str(result.get("expected_channel_id") or "")
    if actual != expected:
        raise worker.WorkerError(f"Website channel lock mismatch. Expected {expected}; received {actual or 'empty'}.")
    print("Cloud bridge probe succeeded.")
    print(f"Worker: {WORKER_NAME}")
    print(f"Channel lock: {actual}")
    print("No queue job was claimed during this probe.")
    return 0


def process_one(config: dict[str, Any]) -> int:
    """Claim and process at most one render or approved publish job."""
    session = make_session()
    payload = {
        "worker_name": WORKER_NAME,
        "version": VERSION,
        "capabilities": ["youtube.render", "youtube.publish", "ffmpeg", "cloud-runner"],
    }
    result = worker.signed_json_request(
        session, config, "POST", "/bridge/youtube/v1/claim", payload, timeout=45
    )
    job = result.get("job")
    if not job:
        reason = result.get("reason")
        print("Cloud worker checked the queue. No eligible job is waiting." if not reason else str(reason))
        return 0
    job_id = int(job.get("id") or 0)
    job_type = str(job.get("type") or "unknown")
    print(f"Claimed job #{job_id}: {job_type}")
    try:
        worker.process_job(job, session, config)
    except Exception as exc:
        print(f"Job #{job_id} failed: {exc}", file=sys.stderr, flush=True)
        return 1
    print(f"Job #{job_id} completed its worker step.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Sus10 Beats scheduled cloud YouTube worker")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="Validate cloud secrets and FFmpeg; no network request")
    mode.add_argument("--probe", action="store_true", help="Check the signed website bridge without claiming a job")
    mode.add_argument("--once", action="store_true", help="Claim and process at most one eligible queue job")
    args = parser.parse_args()
    try:
        config = build_config()
        if args.check:
            if shutil.which("ffmpeg") is None:
                raise worker.WorkerError("FFmpeg is missing from the GitHub runner PATH.")
            print("Cloud configuration is valid. FFmpeg is available. No website request was made.")
            return 0
        if args.probe:
            return probe(config)
        return process_one(config)
    except (worker.WorkerError, requests.RequestException, OSError, ValueError) as exc:
        print(f"Cloud worker setup/connection error: {exc}", file=sys.stderr, flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

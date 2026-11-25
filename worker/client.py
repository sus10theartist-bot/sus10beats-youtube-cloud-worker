"""Authenticated client for the Sus10 Beats marketplace worker API."""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any
from urllib.parse import quote

import requests


class MarketplaceClient:
    def __init__(self, base_url: str, shared_secret: str, timeout: int = 30) -> None:
        if not base_url.startswith("https://"):
            raise ValueError("Marketplace API must use HTTPS.")
        if len(shared_secret.encode("utf-8")) < 32:
            raise ValueError("Worker shared secret must contain at least 32 bytes.")
        self.base_url = base_url.rstrip("/")
        self.secret = shared_secret.encode("utf-8")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Sus10BeatsCloudWorker/0.1"})

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        timestamp = str(int(time.time()))
        body_hash = hashlib.sha256(body).hexdigest()
        message = f"{timestamp}\nPOST\n{path}\n{body_hash}".encode("utf-8")
        signature = hmac.new(self.secret, message, hashlib.sha256).hexdigest()
        response = self.session.post(
            self.base_url + path,
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-Sus10-Worker-Timestamp": timestamp,
                "X-Sus10-Worker-Signature": signature,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("Marketplace API returned an invalid response.")
        return data

    def claim_job(self, worker_id: str) -> dict[str, Any] | None:
        data = self._post(
            "/api/worker/v1/jobs/claim",
            {"worker_id": worker_id, "capabilities": ["ffmpeg", "promo-video-v1"], "max_job_seconds": 1200},
        )
        job = data.get("job")
        if job is None:
            return None
        if not isinstance(job, dict):
            raise ValueError("Marketplace API returned an invalid job object.")
        return job

    def report_rendered(self, job_id: str, lease_token: str, result: dict[str, Any]) -> dict[str, Any]:
        return self._post(
            f"/api/worker/v1/jobs/{quote(job_id, safe='')}/rendered",
            {"lease_token": lease_token, "result": result},
        )

    def report_failed(self, job_id: str, lease_token: str, error_code: str, message: str) -> dict[str, Any]:
        return self._post(
            f"/api/worker/v1/jobs/{quote(job_id, safe='')}/failed",
            {"lease_token": lease_token, "error_code": error_code[:60], "message": message[:240]},
        )

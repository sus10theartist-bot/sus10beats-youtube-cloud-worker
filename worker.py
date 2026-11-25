#!/usr/bin/env python3
"""Cloud worker library used by cloud_runner.py.

GitHub-hosted runner only. It never connects to MySQL and never stores Google
refresh credentials or the Google OAuth client secret.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

YOUTUBE_CHANNELS_URL = "https://youtube.googleapis.com/youtube/v3/channels?part=id&mine=true"
YOUTUBE_UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status"
MAX_RETURN_VIDEO_BYTES = 7 * 1024 * 1024


class WorkerError(RuntimeError):
    pass


def canonical_signature(secret: str, method: str, path: str, body_hash: str, timestamp: str | None = None) -> dict[str, str]:
    ts = timestamp or str(int(time.time()))
    canonical = f"{ts}\n{method.upper()}\n{path}\n{body_hash.lower()}"
    signature = hmac.new(secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()
    return {"X-Sus10-Worker-Timestamp": ts, "X-Sus10-Worker-Signature": signature}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def signed_json_request(session: requests.Session, config: dict[str, Any], method: str, path: str, payload: dict[str, Any] | None = None, timeout: int = 45) -> dict[str, Any]:
    body = json.dumps(payload or {}, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    headers = canonical_signature(config["worker_secret"], method, path, sha256_bytes(body))
    headers["Content-Type"] = "application/json"
    headers["Accept"] = "application/json"
    response = session.request(method, config["site_url"] + path, data=body, headers=headers, timeout=timeout)
    if response.status_code >= 400:
        short = response.text[:700].replace("\n", " ")
        raise WorkerError(f"Website bridge returned HTTP {response.status_code}: {short}")
    try:
        result = response.json()
    except ValueError as exc:
        raise WorkerError(f"Website bridge returned a non-JSON response (HTTP {response.status_code}). InfinityFree may be blocking external worker/API traffic. Response begins: {response.text[:180]!r}") from exc
    if not isinstance(result, dict):
        raise WorkerError("Website bridge returned an unexpected response.")
    return result


def signed_download(session: requests.Session, config: dict[str, Any], asset_url: str, target: Path) -> None:
    parsed = urlparse(asset_url)
    base_host = urlparse(config["site_url"]).netloc.lower()
    if parsed.scheme != "https" or parsed.netloc.lower() != base_host:
        raise WorkerError("The website returned an asset URL outside the configured Sus10 Beats domain.")
    path = parsed.path
    headers = canonical_signature(config["worker_secret"], "GET", path, sha256_bytes(b""))
    headers["Accept"] = "application/octet-stream"
    with session.get(asset_url, headers=headers, stream=True, timeout=(30, 180), allow_redirects=False) as response:
        if response.status_code >= 400:
            raise WorkerError(f"Could not download worker media (HTTP {response.status_code}): {response.text[:500]}")
        if 300 <= response.status_code < 400:
            raise WorkerError("The website returned a redirect for a signed private media URL.")
        total = 0
        with target.open("wb") as out:
            for chunk in response.iter_content(chunk_size=1024 * 256):
                if not chunk:
                    continue
                total += len(chunk)
                if total > 100 * 1024 * 1024:
                    raise WorkerError("Downloaded media exceeded the 100 MB safety limit.")
                out.write(chunk)
    if not target.is_file() or target.stat().st_size < 100:
        raise WorkerError("Downloaded media file is empty or incomplete.")


def render_promo(job: dict[str, Any], session: requests.Session, config: dict[str, Any], temp_dir: Path) -> Path:
    preview = temp_dir / "preview.mp3"
    cover = temp_dir / "cover.jpg"
    output = temp_dir / "sus10-promo.mp4"
    assets = job.get("assets") or {}
    signed_download(session, config, str(assets["preview"]), preview)
    signed_download(session, config, str(assets["cover"]), cover)

    if shutil.which("ffmpeg") is None:
        raise WorkerError("FFmpeg is not available in the cloud runner environment.")

    filter_complex = (
        "[0:v]scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,"
        "zoompan=z='min(zoom+0.0002,1.04)':d=1500:s=1280x720:fps=25,format=yuv420p[bg];"
        "[1:a]showwaves=s=1120x130:mode=line:rate=25:colors=white,format=rgba[w];"
        "[bg][w]overlay=(W-w)/2:H-h-68[v]"
    )

    def run_render(video_bitrate: str, audio_bitrate: str) -> None:
        cmd = [
            "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
            "-loop", "1", "-framerate", "25", "-i", str(cover), "-i", str(preview),
            "-filter_complex", filter_complex, "-map", "[v]", "-map", "1:a",
            "-t", "60", "-shortest", "-c:v", "libx264", "-preset", "veryfast",
            "-b:v", video_bitrate, "-maxrate", video_bitrate, "-bufsize", "900k",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", audio_bitrate,
            "-movflags", "+faststart", str(output)
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        if proc.returncode != 0:
            raise WorkerError("FFmpeg render failed: " + (proc.stderr or proc.stdout)[-900:])

    run_render("420k", "96k")
    if not output.is_file() or output.stat().st_size < 10_000:
        raise WorkerError("FFmpeg did not produce a valid promotional MP4.")
    if output.stat().st_size > MAX_RETURN_VIDEO_BYTES:
        output.unlink(missing_ok=True)
        run_render("300k", "80k")
    if output.stat().st_size > MAX_RETURN_VIDEO_BYTES:
        raise WorkerError("The generated video is still over 7 MB. Try a shorter preview or lower bitrate.")
    return output


def upload_rendered_video(job_id: int, video_path: Path, session: requests.Session, config: dict[str, Any]) -> None:
    path = f"/bridge/youtube/v1/jobs/{job_id}/rendered-video"
    file_hash = hashlib.sha256(video_path.read_bytes()).hexdigest()
    headers = canonical_signature(config["worker_secret"], "POST", path, file_hash)
    headers["X-Sus10-Worker-File-SHA256"] = file_hash
    headers["Accept"] = "application/json"
    with video_path.open("rb") as file_handle:
        response = session.post(config["site_url"] + path, files={"video": ("sus10-promo.mp4", file_handle, "video/mp4")}, headers=headers, timeout=(30, 240))
    if response.status_code >= 400:
        raise WorkerError(f"Website rejected the generated video (HTTP {response.status_code}): {response.text[:700]}")
    data = response.json()
    if not data.get("ok"):
        raise WorkerError(str(data.get("error") or "Website did not accept the video."))


def verify_youtube_channel(access_token: str, expected_channel_id: str, session: requests.Session) -> None:
    response = session.get(YOUTUBE_CHANNELS_URL, headers={"Authorization": f"Bearer {access_token}"}, timeout=45)
    if response.status_code >= 400:
        raise WorkerError(f"YouTube channel verification failed (HTTP {response.status_code}): {response.text[:600]}")
    items = response.json().get("items") or []
    actual = str(items[0].get("id", "")) if items else ""
    if not actual or actual != expected_channel_id:
        raise WorkerError(f"Wrong YouTube channel. Expected {expected_channel_id}; Google authorized {actual or 'no channel'}.")


def upload_to_youtube(job: dict[str, Any], video_path: Path, session: requests.Session) -> str:
    token = str(job.get("access_token") or "")
    expected = str(job.get("expected_channel_id") or "")
    if not token or not expected:
        raise WorkerError("The website did not supply a verified YouTube access token and expected channel ID.")
    verify_youtube_channel(token, expected, session)
    size = video_path.stat().st_size
    title = str(job.get("title") or "Sus10 Beats promotional video")[:100]
    description = str(job.get("description") or "Discover and license beats on Sus10 Beats.")[:5000]
    visibility = str(job.get("visibility") or "unlisted")
    if visibility not in {"public", "unlisted", "private"}:
        raise WorkerError("The marketplace supplied an unsupported YouTube visibility setting.")
    payload = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": ["Sus10 Beats", "Afrobeats", "Instrumental Beats", "Music Production"],
            "categoryId": "10",
        },
        "status": {"privacyStatus": visibility},
    }
    start = session.post(
        YOUTUBE_UPLOAD_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": "video/mp4",
            "X-Upload-Content-Length": str(size),
        },
        json=payload,
        timeout=60,
    )
    if start.status_code not in (200, 201):
        raise WorkerError(f"YouTube did not create an upload session (HTTP {start.status_code}): {start.text[:700]}")
    upload_url = start.headers.get("Location")
    if not upload_url or not upload_url.startswith("https://"):
        raise WorkerError("YouTube did not return a secure resumable upload URL.")
    with video_path.open("rb") as media:
        uploaded = session.put(upload_url, data=media, headers={"Content-Type": "video/mp4", "Content-Length": str(size)}, timeout=(60, 900))
    if uploaded.status_code not in (200, 201):
        raise WorkerError(f"YouTube upload response was not confirmed (HTTP {uploaded.status_code}): {uploaded.text[:700]}")
    video_id = str(uploaded.json().get("id") or "")
    if len(video_id) != 11:
        raise WorkerError("YouTube returned an unexpected video ID. Check the channel before retrying.")
    return video_id


def report_failure(job_id: int, message: str, retryable: bool, session: requests.Session, config: dict[str, Any]) -> None:
    payload = {"error": message[:900], "retryable": bool(retryable)}
    signed_json_request(session, config, "POST", f"/bridge/youtube/v1/jobs/{job_id}/fail", payload)


def process_job(job: dict[str, Any], session: requests.Session, config: dict[str, Any]) -> None:
    job_id = int(job["id"])
    job_type = str(job.get("type") or "")
    print(f"Processing YouTube job #{job_id}: {job_type}", flush=True)
    with tempfile.TemporaryDirectory(prefix="sus10-youtube-") as temp:
        temp_dir = Path(temp)
        if job_type == "youtube.render":
            try:
                video = render_promo(job, session, config, temp_dir)
                upload_rendered_video(job_id, video, session, config)
                print(f"Promotional video for #{job.get('promotion_id')} is ready for producer review.", flush=True)
            except Exception as exc:
                try:
                    report_failure(job_id, str(exc), retryable=True, session=session, config=config)
                except Exception as report_exc:
                    print(f"Could not report render failure to website: {report_exc}", file=sys.stderr, flush=True)
                raise
            return

        if job_type == "youtube.publish":
            # An uncertain YouTube upload is never blindly retried.
            upload_started = False
            try:
                video_path = temp_dir / "approved-promo.mp4"
                signed_download(session, config, str((job.get("assets") or {})["video"]), video_path)
                upload_started = True
                video_id = upload_to_youtube(job, video_path, session)
                signed_json_request(session, config, "POST", f"/bridge/youtube/v1/jobs/{job_id}/complete", {"youtube_video_id": video_id})
                print(f"Published https://www.youtube.com/watch?v={video_id}", flush=True)
            except Exception as exc:
                try:
                    report_failure(job_id, str(exc), retryable=not upload_started, session=session, config=config)
                except Exception as report_exc:
                    print(f"Could not report publish failure to website: {report_exc}", file=sys.stderr, flush=True)
                raise
            return

        raise WorkerError(f"Unsupported worker job type: {job_type}")

# Marketplace worker API contract (v1)

This document defines the integration boundary between the PHP/MySQL marketplace and the cloud runner. The website remains the authority for producer approval, final administrator approval, and the connected Sus10 Beats YouTube channel.

**Do not connect this worker to the live site until these endpoints and private artifact storage are implemented and tested.** This repository does not change the marketplace database or PHP application.

## Authentication

All requests use HTTPS POST and carry:

- `X-Sus10-Worker-Timestamp`: Unix time in seconds
- `X-Sus10-Worker-Signature`: lowercase hexadecimal HMAC-SHA256

The signed message is exactly:

```text
{timestamp}\nPOST\n{request_path}\n{sha256_hex_of_exact_request_body}
```

The key is a random secret of at least 32 bytes, stored privately in marketplace server configuration and GitHub Actions secret `SITE_WORKER_SHARED_SECRET`. The PHP endpoint must reject timestamps outside a five minutes window, compare signatures in constant time, cap body size, and rate-limit failed requests. Do not place this key in the repository or browser code.

## Claim

`POST /api/worker/v1/jobs/claim`

Request:

```json
{"worker_id":"github-run-id-attempt","capabilities":["ffmpeg","promo-video-v1"],"max_job_seconds":1200}
```

No work: `{"job":null}`

Claimed job:

```json
{
  "job": {
    "job_id": "opaque-id",
    "lease_token": "expiring-lease-token",
    "title": "Beat title",
    "producer_name": "Producer display name",
    "audio_url": "https://sus10beats.great-site.net/short-lived-signed-audio-url",
    "cover_url": "https://sus10beats.great-site.net/short-lived-signed-cover-url",
    "artifact_upload_url": "https://private-object-storage.example/short-lived-presigned-put-url",
    "artifact_key": "private/promos/job-id.mp4"
  }
}
```

Audio, cover, and storage hosts must be in the worker's explicit allow-list. The upload URL must be short-lived, write-only for one object, restricted to the expected content type and size, and must keep the storage object private.

The server must atomically lease exactly one eligible job. Only jobs with producer approval and any required final admin approval may be claimed. Suggested lease duration: 30 minutes. Audio and cover URLs must be short-lived, read-only, HTTPS URLs.

## Store and report the rendered video

The worker uploads the MP4 with an HTTPS `PUT` to `artifact_upload_url`, then calls:

`POST /api/worker/v1/jobs/{job_id}/rendered`

Request:

```json
{
  "lease_token": "the-lease-token-from-claim",
  "result": {
    "render_version": "promo-video-v1",
    "duration_seconds": 91.25,
    "size_bytes": 12345678,
    "filename": "sus10-beats-promo.mp4",
    "artifact_key": "private/promos/job-id.mp4",
    "publishing_state": "disabled"
  }
}
```

The marketplace must verify the lease token and artifact key, store the metadata, and set the job to a reviewable state. Provide a separately authorized, short-lived download URL to admins/producers when they preview the rendered file. Do not make generated promo files public by default.

## Failed callback

`POST /api/worker/v1/jobs/{job_id}/failed`

```json
{"lease_token":"the-lease-token-from-claim","error_code":"worker_job_failed","message":"The cloud worker could not finish this job."}
```

Do not persist tracebacks, OAuth tokens, HMAC signatures, signed URLs, or server paths in marketplace logs.

## Future YouTube upload stage — not implemented

1. Re-check producer approval, final admin approval, and the global publishing switch immediately before upload.
2. Use only channel `UCER9nZgssKit3V6B_JSgv3A`. Never accept producer-owned channels.
3. Obtain a short-lived access token from a server-side endpoint backed by the marketplace's existing OAuth refresh token. Do not copy refresh tokens into GitHub.
4. Verify the OAuth connection still belongs to the expected channel.
5. Use YouTube resumable upload and begin with `private` visibility during end-to-end tests.
6. Store the YouTube video ID and upload state durably. Ambiguous timeouts must enter a reconciliation state; blind retries risk duplicate videos.
7. Require both the site admin switch and GitHub variable `WORKER_PUBLISH_ENABLED=true`. Either switch being false must block publication.

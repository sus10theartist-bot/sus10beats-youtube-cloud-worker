# Sus10 Beats — Cloud YouTube Worker

Cloud-side processing for approved Sus10 Beats promotional videos. Jobs run on temporary GitHub-hosted runners; no producer or owner computer needs to stay online.

## Current stage

This repository contains the initial cloud-worker foundation: scheduled/manual execution, signed HTTPS marketplace requests, one-job claiming, restricted asset downloads, FFmpeg promo rendering, and automated tests.

**YouTube uploads are not enabled in this foundation release.** The marketplace API endpoints and approval/token hand-off must be integrated and tested before upload capability is added. The designated channel is `UCER9nZgssKit3V6B_JSgv3A`; producer-owned channels are not accepted.

## Architecture

```text
Sus10 Beats marketplace (PHP + MySQL)
        | signed HTTPS claim/report calls
        v
GitHub Actions (temporary cloud runner)
        +-- downloads approved promo assets
        +-- renders a 1280x720 video using FFmpeg
        +-- reports the rendered job for review
        v
Marketplace admin review / publishing stage
```

GitHub Actions is a lightweight scheduled queue poller, not an always-on server. The workflow polls every ten minutes and can also be started manually. Scheduled runs can be delayed under load.

## Setup after marketplace integration

Configure only in **Settings → Secrets and variables → Actions**:

| Name | Type | Purpose |
|---|---|---|
| `SITE_API_BASE_URL` | Variable | `https://sus10beats.great-site.net` |
| `SITE_WORKER_SHARED_SECRET` | Secret | Random HMAC key shared with the private marketplace server config |
| `WORKER_PUBLISH_ENABLED` | Variable | Keep `false` until upload approval flow is tested |

No credentials belong in this public repository. Without these values the workflow safely performs a no-op configuration check.

## Local checks

Requires Python 3.12 and FFmpeg.

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m worker.main --health-check
```

## Security rules

- The marketplace is the source of truth for producer and final admin approval.
- The worker processes only jobs returned by the authenticated claim endpoint.
- HMAC signatures and HTTPS protect worker API requests.
- Asset URLs must use HTTPS and an explicit host allow-list.
- Download size and render duration are bounded.
- Publishing remains disabled unless the marketplace job and a separate worker-side switch both authorize it. This release has no upload implementation.
- Never commit Google OAuth tokens, GitHub tokens, shared secrets, or signed asset URLs.
- The marketplace must lease jobs atomically to prevent duplicate runners.

See [the marketplace API contract](docs/site-api-contract.md) before connecting the live site.

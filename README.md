# Sus10 Beats — YouTube cloud worker

<badge>RC7 reverse-bridge package required before queue processing</badge>

The previous direct GitHub Actions → InfinityFree bridge was tested and failed because InfinityFree returned its JavaScript browser challenge instead of the API JSON response. The old scheduled queue worker has therefore been paused. Do not rerun the old website probe, and do not enable YouTube publishing.

## Next release

Use **Sus10 Beats RC7 — Cloudflare reverse bridge**. It reverses the network direction:

```text
Sus10 Beats PHP on InfinityFree
   | signed outbound HTTPS
   v
Cloudflare Worker + Workers KV
   ^ signed queue polling
   |
GitHub-hosted Ubuntu runner (FFmpeg)
```

The design keeps the owner’s PC off, avoids a direct inbound API call to InfinityFree, and keeps the Google OAuth refresh token on the website. The cloud worker is hard-locked to the official channel `UCER9nZgssKit3V6B_JSgv3A`.

## Installation

Download the RC7 Cloudflare Reverse Bridge Patch from the current ChatGPT conversation. In its `github_repository/` folder are the files that must be uploaded to this repository root, preserving subfolders. Its `website_patch/` folder contains the three website files that replace matching paths in `htdocs`. Follow `docs/RC7_CLOUDFLARE_SETUP.md`.

Until the RC7 files have been uploaded and Cloudflare is configured, this repository intentionally runs source validation only. It does not poll a queue, access InfinityFree, or publish videos.

Keep both website YouTube publishing switches OFF. Do not add secrets to repository files. The existing GitHub Actions secret is `SUS10_WORKER_SECRET`; the Cloudflare Worker secret is `WORKER_SHARED_SECRET`; the website protected `.env` uses `WORKER_SHARED_SECRET`. All three must contain the same existing value.

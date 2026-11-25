# Sus10 Beats — GitHub-hosted YouTube cloud worker

This repository contains only the cloud processing worker and its GitHub Actions workflow. It does not contain the Sus10 Beats website, database dump, Google Client Secret, YouTube refresh token, or customer data.

The worker runs only as GitHub-hosted Ubuntu cloud jobs. It does **not** run on the owner's computer; there is no desktop/local-worker mode in this release. A scheduled workflow checks the Sus10 Beats queue every five minutes and processes at most one job per run.

## Architecture and safety

- GitHub Actions provides the temporary cloud compute and FFmpeg environment.
- The worker talks to the existing PHP application through its signed HTTPS bridge.
- It never connects directly to MySQL.
- It never stores the Google OAuth Client Secret or refresh token.
- For a publish job, the website supplies a short-lived access token after checking its saved OAuth connection. The worker verifies that the authorised channel is exactly `UCER9nZgssKit3V6B_JSgv3A` before uploading.
- Render jobs return a compressed MP4 to the website (maximum 7 MB for the current shared-host build) for producer review.
- Publishing jobs are claimable only when both website publishing switches are enabled and the channel connection exists.
- Uncertain YouTube upload outcomes are not blindly retried, to avoid duplicate public videos.
- Any missing or invalid visibility setting fails safe to Unlisted; do not use this worker for public releases until tested.

## One-time setup

### 1. Create a public GitHub repository

Create a **Public** repository named `sus10beats-youtube-cloud-worker`. The repository contains worker code only; do not put secrets, website source, media, `.env` files, SQL dumps, or customer information in it. Keep the default branch `main`.

### 2. Create one strong shared secret

Generate a random 64-character hexadecimal secret using your password manager's secure password generator (allow only `0-9` and `a-f`). Use the exact same value in both locations:

**Sus10 Beats protected `.env` file** — add one line, with no quotation marks:

```ini
WORKER_SHARED_SECRET=PASTE_THE_64_CHARACTER_SECRET_HERE
```

Keep all existing Google OAuth and application settings unchanged. Do not upload `.env` to GitHub.

**GitHub repository Actions secret** — open repository Settings → Secrets and variables → Actions → New repository secret:

- Name: `SUS10_WORKER_SECRET`
- Secret: the exact same 64-character value

Do not create a normal repository variable for this value. It must be an Actions secret.

### 3. Test the cloud connection before processing jobs

Open the repository's Actions tab. Choose **Sus10 Beats YouTube Cloud Worker** → **Run workflow** → select `probe` → **Run workflow**.

A successful run reports `Cloud bridge probe succeeded.`, the channel lock `UCER9nZgssKit3V6B_JSgv3A`, and confirms no queue job was claimed.

Then open marketplace Admin → YouTube. It should show the cloud runner as recently active.

If GitHub Actions receives HTTP 403 or an HTML bot/security page instead of JSON, InfinityFree may be blocking external bridge traffic. Do not enable publishing; resolve reachability first.

### 4. Test a promotional render

Keep `YOUTUBE_PUBLISH_ENABLED=false` and the website publishing switch OFF. Upload a test beat with a prepared MP3 preview and valid cover artwork. Manually run workflow mode `process-one` or wait for its schedule. Confirm the video reaches **Producer Review**.

Only after rendering and review are correct should you perform one controlled **Unlisted** YouTube upload, keeping final administrator approval enabled.

## Runtime and limits

- The schedule is every five minutes; this is cloud execution, not a permanent 24/7 process. Scheduled events are best-effort and can be delayed during heavy load.
- GitHub may disable scheduled workflows in public repositories after 60 days with no repository activity.
- The workflow serialises processing and handles one queue job per run, so a backlog drains gradually.
- GitHub Actions is a temporary no-card cloud option. For strict real-time, always-on, higher-volume processing, move this worker to a persistent cloud service when budget permits.
- Google OAuth apps in External Testing can have refresh-token expiry restrictions for YouTube scopes. Complete Google's appropriate publishing/verification steps before relying on unattended long-term publishing.

## Troubleshooting

- **Missing `SUS10_WORKER_SECRET`:** add the Actions secret with exactly that name.
- **HTTP 401:** the website `.env` and GitHub Actions secret do not match, or the request timestamp is outside the five-minute signature window.
- **HTTP 403 / HTML:** the website host may be blocking automated external API traffic.
- **HTTP 413:** the generated MP4 or PHP post-size limit exceeds the current host configuration. The worker targets a 7 MB maximum.
- **No eligible job:** the connection is working; there was no render/publish job ready for this run.
- **Producer Review:** video rendering succeeded. Producer approval is required.
- **Admin Review:** producer approval succeeded; final administrator approval is still required.
- **Upload unclear or failed after starting:** inspect the YouTube channel before retrying. The worker deliberately avoids blind duplicate uploads.

Never enable public publishing until a real controlled Unlisted test video is visible on the official channel and the resulting URL is recorded in the marketplace.

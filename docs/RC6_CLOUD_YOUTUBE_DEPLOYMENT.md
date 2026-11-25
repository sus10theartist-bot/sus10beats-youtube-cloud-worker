# RC6 — Cloud YouTube worker deployment

**Cloud-only:** this worker runs on GitHub-hosted Ubuntu runners. Do not install anything on the owner's Windows computer. The computer can be off.

## 1. Apply the two-file website bridge patch

Upload the two files from the RC6 Cloud YouTube Setup Kit, replacing only these destinations:

| Package file | Website destination |
|---|---|
| `website_patch/public/index.php` | `htdocs/public/index.php` |
| `website_patch/app/Views/admin/youtube.php` | `htdocs/app/Views/admin/youtube.php` |

Merge folders and replace only those two files. Do not replace `.env`, `.htaccess`, database files, profile uploads, user files, or run the installer. Do not reset or import the database.

The patch adds signed bridge routes under `/bridge/youtube/v1/` for heartbeat, queue claim, private asset access, rendered-video receipt, completion and failure reporting. The website remains responsible for moderation, approval, OAuth token custody and the queue.

## 2. Add the shared worker secret

Generate a random 64-character hexadecimal secret with a password manager. Do not send it in chat and do not commit it to GitHub.

Add this line to the existing protected `htdocs/.env` file (same key name, no quotation marks):

```ini
WORKER_SHARED_SECRET=YOUR_64_CHARACTER_RANDOM_VALUE
```

In this repository, open **Settings → Secrets and variables → Actions → New repository secret**:

- Name: `SUS10_WORKER_SECRET`
- Value: the same 64-character secret

Keep the value in an Actions **secret**, not a variable. Keep all existing Google OAuth and database settings unchanged.

## 3. Run a harmless bridge probe

Open **Actions → Sus10 Beats YouTube Cloud Worker → Run workflow**. Choose `probe` and start it.

A passing run must report `Cloud bridge probe succeeded`, confirm channel ID `UCER9nZgssKit3V6B_JSgv3A`, and state that no queue job was claimed. Then check Admin → YouTube for a recent cloud-worker heartbeat.

If the runner receives HTTP 403 or HTML instead of JSON, the host may be blocking the external bridge. Stop here and keep publishing disabled.

## 4. Render before publishing

Keep `YOUTUBE_PUBLISH_ENABLED=false` in `.env`, keep the site publishing switch OFF, leave final administrator approval ON, and set visibility to Unlisted.

Submit one test promotion with a valid MP3 preview and cover. Run workflow mode `process-one`. Confirm the rendered MP4 is received by the site and appears in Producer Review.

Only after rendering and review pass should you test one manually approved Unlisted upload to the official `@sus10beats` channel. Verify the video appears on that channel and that its video ID/URL is saved in the website.

## Safety and operating limits

- The worker never connects to MySQL and never stores the Google refresh token or OAuth client secret in GitHub.
- Only the central channel `UCER9nZgssKit3V6B_JSgv3A` is allowed. The worker verifies the channel before uploading.
- Publishing requires the website's own feature/configuration gates. Keep both switches OFF until the controlled Unlisted test is ready.
- An uncertain YouTube upload is not automatically retried; check the channel first to avoid duplicate videos.
- GitHub scheduled runs are best-effort, can be delayed, and are not an always-on queue service. GitHub's minimum schedule interval is five minutes. Public-repository scheduled workflows are disabled after 60 days without repository activity. See [GitHub's schedule event documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows) and [workflow disable guidance](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/disable-and-enable-workflows).

- GitHub-hosted Actions is a no-card starter option, not a guarantee of instant or continuous processing. For higher volume or guaranteed latency, move to an always-on cloud service when a suitable budget is available.


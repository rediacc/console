# R2 Media Distribution Setup (tutorial/solution videos)

Mirrors `.ci/docs/r2-setup.md` (release binaries), but a **separate bucket and
domain** — video assets are overwritten in place when a tutorial/solution is
re-recorded, unlike release binaries which are write-once/immutable. Sharing
the releases bucket's sentinel/write-once guards with mutable-in-place media
would either trip those guards or require weakening them for an unrelated
use case.

## 1. R2 Bucket

- **Bucket name:** `rediacc-www-media`
- **Region:** EEUR
- **Created:** 2026-07-01

## 2. Custom Domain

Domain: `media.rediacc.com` (not `videos.rediacc.com` — poster images/subtitles
live here too, `media` is the more durable name as scope grows).

Dashboard steps (or via API, see below):
1. Go to R2 → `rediacc-www-media` → Settings
2. Under **Custom Domains**, click **Add**
3. Enter `media.rediacc.com`, click **Continue**
4. Confirm the CNAME record, click **Connect Domain**
5. Wait for status to change from "Initializing"/"pending" to "Active"

API equivalent (Global API Key or a token with R2 + Zone edit permissions):
```bash
curl -sS -X POST "https://api.cloudflare.com/client/v4/accounts/$CLOUDFLARE_ACCOUNT_ID/r2/buckets/rediacc-www-media/domains/custom" \
  -H "X-Auth-Email: $CF_EMAIL" -H "X-Auth-Key: $CF_GLOBAL_API_KEY" -H "Content-Type: application/json" \
  -d '{"domain": "media.rediacc.com", "zoneId": "9e802649c143c9cefd811d8fd671d31c", "enabled": true, "minTLS": "1.0"}'
```

## 3. R2 API Token (S3-compatible)

Dashboard steps:
1. Go to R2 → **Manage R2 API Tokens** → **Create API Token**
2. Token name: `ci-www-media-rw`
3. Permissions: **Object Read & Write**
4. Specify bucket: `rediacc-www-media` only (not account-wide — least privilege,
   a compromised www-media credential can't touch release binaries)
5. TTL: No expiration
6. Click **Create API Token**

Record the following values (also stored in the team password vault):

```
R2_MEDIA_ACCESS_KEY_ID=
R2_MEDIA_SECRET_ACCESS_KEY=
R2_MEDIA_ENDPOINT=https://fa51e4a18d553c30e1633288e9733d04.r2.cloudflarestorage.com
```

Note: if creating the token via the Cloudflare API (`/user/tokens`) instead of
the dashboard, the S3-compatible credentials are **derived**, not returned
directly: `Access Key ID = token.id`, `Secret Access Key =
sha256_hex(token.value)`. Permission groups needed: "Workers R2 Storage Bucket
Item Read" + "Workers R2 Storage Bucket Item Write", scoped via resource key
`com.cloudflare.edge.r2.bucket.<account_id>_default_rediacc-www-media`.

## 4. GitHub Org Secrets

```bash
gh secret set R2_MEDIA_ACCESS_KEY_ID --org rediacc --body "<access-key-id>"
gh secret set R2_MEDIA_SECRET_ACCESS_KEY --org rediacc --body "<secret-access-key>"
gh secret set R2_MEDIA_ENDPOINT --org rediacc --body "https://fa51e4a18d553c30e1633288e9733d04.r2.cloudflarestorage.com"
```

(Not yet wired into any workflow — CI/pipeline integration is a later phase of
the video-migration plan. For now these are used locally/manually via
`.ci/scripts/deploy/sync-media-to-r2.sh`.)

## 5. Cloudflare Cache Rule

Unlike `releases.rediacc.com` (which **bypasses** cache to avoid stale
package-manager signature checks), `media.rediacc.com` **wants** aggressive
CDN caching — large video files, byte-range scrubbing, and cost control all
benefit from edge caching. The rule respects origin `Cache-Control` rather
than overriding it (avoiding the same zone-wide 4h-TTL-override bug documented
in `r2-setup.md`), so the per-object header set at upload time
(`public, max-age=31536000`, no `immutable` — paths *can* legitimately change
content on re-record) governs caching.

| | |
|---|---|
| **Zone** | `rediacc.com` (ID `9e802649c143c9cefd811d8fd671d31c`) |
| **Phase** | `http_request_cache_settings` |
| **Expression** | `(http.host eq "media.rediacc.com")` |
| **Action** | `set_cache_settings` with `cache: true`, `edge_ttl.mode: respect_origin`, `browser_ttl.mode: respect_origin` |

Recreate via API if ever needed (appends to the existing ruleset without
disturbing the `releases.rediacc.com` rule):
```bash
curl -sS -X POST \
  "https://api.cloudflare.com/client/v4/zones/9e802649c143c9cefd811d8fd671d31c/rulesets/phases/http_request_cache_settings/entrypoint/rules" \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" -H "Content-Type: application/json" \
  --data '{
    "description": "Cache media.rediacc.com, respect origin TTL",
    "expression": "(http.host eq \"media.rediacc.com\")",
    "action": "set_cache_settings",
    "action_parameters": { "cache": true, "edge_ttl": {"mode": "respect_origin"}, "browser_ttl": {"mode": "respect_origin"} },
    "enabled": true
  }'
```

Verify caching + range-request support (needed for video seeking):
```bash
curl -sI https://media.rediacc.com/<some-path>.mp4 | grep -iE "cf-cache-status|accept-ranges|cache-control"
curl -sI -r 0-99 https://media.rediacc.com/<some-path>.mp4   # expect HTTP 206
```

## 5b. CORS policy

`media.rediacc.com` is a different origin than `www.rediacc.com`/
`edge.rediacc.com`, so the tutorial player's `<video crossOrigin="anonymous">`
element (needed for cross-origin `<track>` subtitle/chapter loading) and its
plain `fetch()` for `words.json` both require the bucket to send
`Access-Control-Allow-Origin`. R2's CORS config is set via the Cloudflare API
(not the S3-compatible API — the scoped `ci-www-media-rw` token's Object
Read & Write permission doesn't cover it; use a Global API Key / account-admin
token instead):

```bash
curl -X PUT "https://api.cloudflare.com/client/v4/accounts/$CLOUDFLARE_ACCOUNT_ID/r2/buckets/rediacc-www-media/cors" \
  -H "X-Auth-Key: $CF_GLOBAL_API_KEY" -H "X-Auth-Email: $CF_EMAIL" -H "Content-Type: application/json" \
  --data '{
    "rules": [{
      "id": "public-media-read",
      "allowed": { "origins": ["*"], "methods": ["GET", "HEAD"] },
      "exposeHeaders": ["Content-Length", "Content-Range", "ETag"],
      "maxAgeSeconds": 3600
    }]
  }'
```

`origins: ["*"]` is intentional — every file in this bucket is already
individually fetchable by anyone at `media.rediacc.com/<path>` with no
credentials, so scoping CORS to specific origins would add no real
restriction, just friction for local dev / PR previews on other hostnames.

Verify: `curl -sI -H "Origin: https://edge.rediacc.com" https://media.rediacc.com/<path> | grep -i access-control-allow-origin` should show `*`.

Also see `packages/www/public/_headers`: the CSP's `media-src` and
`connect-src` directives must include `https://media.rediacc.com`, or the
browser blocks the loads before CORS is even evaluated.

## 6. Syncing media

Use `.ci/scripts/deploy/sync-media-to-r2.sh` — wraps `aws s3 sync`, which is
incremental by default (only uploads files whose size/mtime differ from what's
already in the bucket). Safe to re-run any time a tutorial or solution video
is re-recorded; it will only push what changed.

```bash
export R2_MEDIA_ACCESS_KEY_ID=... R2_MEDIA_SECRET_ACCESS_KEY=... R2_MEDIA_ENDPOINT=...
.ci/scripts/deploy/sync-media-to-r2.sh                  # sync everything
.ci/scripts/deploy/sync-media-to-r2.sh --dry-run        # preview only
.ci/scripts/deploy/sync-media-to-r2.sh --tutorials-only # just tutorials/video/
.ci/scripts/deploy/sync-media-to-r2.sh --solutions-only # just videos/solutions/
```

The URL builders (`src/utils/solution-video.ts`,
`src/plugins/remark-tutorial-embed.ts`) read from `video-manifest.json` and
emit `https://media.rediacc.com/...` URLs when `PUBLIC_VIDEO_CDN_BASE_URL` is
set at build time, falling back to the local `/assets/...` path when it's
unset (e.g. local dev without the env var). That env var is wired into the
"Build pages" step of `.github/workflows/cd-deploy-worker.yml`. Once an
edge/stable deploy with that path has been verified serving real traffic,
the local `public/assets/{tutorials/video,videos/solutions,tutorials/audio}`
copies are removed from git entirely (gitignored) — see root `CLAUDE.md`'s
"Media Assets" section for current status.

## 7. Restoring media after a fresh clone

`.ci/scripts/deploy/sync-media-from-r2.sh` is the download counterpart —
restores `packages/www/public/assets/tutorials/video/` and
`packages/www/public/assets/videos/` from R2 into a local checkout. Same
incremental behavior as the upload script (only pulls what's missing or
changed locally), and needs the same `R2_MEDIA_*` credentials (the S3 API is
used to list/diff the bucket; the public `media.rediacc.com` domain doesn't
expose a listing endpoint, only individual file GETs).

```bash
export R2_MEDIA_ACCESS_KEY_ID=... R2_MEDIA_SECRET_ACCESS_KEY=... R2_MEDIA_ENDPOINT=...
.ci/scripts/deploy/sync-media-from-r2.sh                  # restore everything
.ci/scripts/deploy/sync-media-from-r2.sh --dry-run        # preview only
.ci/scripts/deploy/sync-media-from-r2.sh --tutorials-only
.ci/scripts/deploy/sync-media-from-r2.sh --solutions-only
```

Once the media directories are removed from git (see §6), this is the way to
populate a local working copy — needed for pipeline development / offline
work / local ffmpeg operations (`--tutorials-only` / `--solutions-only`), and
for the tutorial-audio cache specifically (`--audio-only`, always needed —
see §9). **Not** needed for normal `npm run dev` browsing of tutorial/solution
pages, since the site fetches videos straight from `media.rediacc.com` over
the network once the URL builders point at the CDN, the same way a real
visitor's browser does.

## 8. Verification

```bash
aws s3 ls s3://rediacc-www-media/ --endpoint-url https://fa51e4a18d553c30e1633288e9733d04.r2.cloudflarestorage.com
aws s3 sync --dryrun packages/www/public/assets/tutorials/video/ s3://rediacc-www-media/tutorials/video/ \
  --endpoint-url https://fa51e4a18d553c30e1633288e9733d04.r2.cloudflarestorage.com
```
A clean dry-run (no pending uploads) confirms R2 has every current local byte.

## 9. Tutorial-audio cache (`tutorials/audio/`) — not CDN-served

`packages/www/public/assets/tutorials/audio/` holds per-narration-step `.mp3`
files synthesized by `private/generative/src/tutorial_tts/cli.py`
(Qwen3-TTS). Unlike `tutorials/video/` and `videos/solutions/`, this is
**not** a runtime-served asset — nothing in the browser player ever fetches
a `.mp3`. `generate-tutorial-video.ts` / `scripts/lib/ffmpeg-video.ts` mux
these files into the final tutorial `.mp4` at build time, then they're done;
the mp4 already has audio embedded.

It's synced to the same `rediacc-www-media` bucket under `tutorials/audio/`
purely as a **build-time cache** — regenerating narration costs real TTS
GPU/electricity, so losing the local copy on a fresh checkout shouldn't mean
paying that cost again. It is not covered by the Cache Rule in §5 (no reason
to CDN-cache something nothing fetches over HTTP) and is only reachable via
the S3 API (`sync-media-to-r2.sh` / `sync-media-from-r2.sh --audio-only`),
never via `media.rediacc.com`.

Restore/upload for this cache is wired into `run.sh`'s tutorial pipeline
directly (`www_tutorial_audio_restore` / `www_tutorial_audio_upload` in
`run.sh`, called from `www_tutorials_generate` and `www_tutorials_video`) —
best-effort, so local iteration without `R2_MEDIA_*` set still works, just
without the cache (narration gets re-synthesized instead of restored).
`private/generative/src/tutorial_tts/cli.py`'s own cache-hit check
(`absolute_audio.exists()`) is unchanged; it just benefits from the file
already being present locally by the time it runs.

```bash
export R2_MEDIA_ACCESS_KEY_ID=... R2_MEDIA_SECRET_ACCESS_KEY=... R2_MEDIA_ENDPOINT=...
.ci/scripts/deploy/sync-media-to-r2.sh --audio-only     # backup
.ci/scripts/deploy/sync-media-from-r2.sh --audio-only   # restore
```

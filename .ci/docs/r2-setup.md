# R2 Release Distribution Setup

## 1. R2 Bucket

- **Bucket name:** `rediacc-releases`
- **Region:** ENAM
- **Created:** 2026-02-24

## 2. Custom Domain

Domain: `releases.rediacc.com`

Dashboard steps:
1. Go to R2 → `rediacc-releases` → Settings
2. Under **Custom Domains**, click **Add**
3. Enter `releases.rediacc.com`, click **Continue**
4. Confirm the CNAME record, click **Connect Domain**
5. Wait for status to change from "Initializing" to "Active"

## 3. R2 API Token (S3-compatible)

Dashboard steps:
1. Go to R2 → **Manage R2 API Tokens** → **Create API Token**
2. Token name: `ci-releases-rw`
3. Permissions: **Object Read & Write**
4. Specify bucket: `rediacc-releases`
5. TTL: No expiration (or set a long TTL)
6. Click **Create API Token**

Record the following values:

```
R2_ACCESS_KEY_ID=
R2_SECRET_ACCESS_KEY=
R2_ENDPOINT=https://fa51e4a18d553c30e1633288e9733d04.r2.cloudflarestorage.com
```

## 4. GitHub Org Secrets

After creating the R2 API token, set these secrets:

```bash
gh secret set R2_ACCESS_KEY_ID --org rediacc --body "<access-key-id>"
gh secret set R2_SECRET_ACCESS_KEY --org rediacc --body "<secret-access-key>"
gh secret set R2_ENDPOINT --org rediacc --body "https://fa51e4a18d553c30e1633288e9733d04.r2.cloudflarestorage.com"
```

## 5. Cloudflare Cache Rule (critical)

The `rediacc.com` zone has `cache_level: aggressive` and `browser_cache_ttl: 14400` (4 h), which causes CF to OVERRIDE origin `Cache-Control: no-cache` with `max-age=14400` on GET responses for binary content served from this R2 custom domain. That is fine for `www.rediacc.com` (HTML served by Workers), but on `releases.rediacc.com` it broke package-manager signature checks: apt / apk / pacman fetched a fresh APKINDEX / InRelease referencing one sha256, then got the previous release's cached body with a different sha256, and aborted with `BAD signature` / `File has unexpected size`.

A zone-level Cache Rule forces BYPASS for every request to `releases.rediacc.com`, so origin `Cache-Control` passes through unmodified and CF never caches the body. R2 is colocated with CF POPs, so bypassing the edge cache has negligible latency impact.

| | |
|---|---|
| **Zone** | `rediacc.com` (ID `9e802649c143c9cefd811d8fd671d31c`) |
| **Phase** | `http_request_cache_settings` |
| **Expression** | `(http.host eq "releases.rediacc.com")` |
| **Action** | `set_cache_settings` with `cache: false` |

Recreate via API (use `CLOUDFLARE_API_TOKEN` with Zone:Cache Purge + Zone:Cache Rules, or the legacy `CF_API_KEY`+`CF_EMAIL` global key):

```bash
ZONE=9e802649c143c9cefd811d8fd671d31c
curl -sS -X PUT \
  "https://api.cloudflare.com/client/v4/zones/$ZONE/rulesets/phases/http_request_cache_settings/entrypoint" \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  -H "Content-Type: application/json" \
  --data '{
    "rules": [{
      "description": "Bypass cache for releases.rediacc.com",
      "expression": "(http.host eq \"releases.rediacc.com\")",
      "action": "set_cache_settings",
      "action_parameters": { "cache": false },
      "enabled": true
    }]
  }'
```

Verify both HEAD and GET return `cf-cache-status: DYNAMIC` + the origin's `Cache-Control: no-cache`, and that `content-length` matches between HEAD and GET (pre-rule, they differed by a few bytes on `.pkg.tar.zst`):

```bash
for m in HEAD GET; do
  echo "== $m =="
  curl -sI -X $m "https://releases.rediacc.com/apk/edge/x86_64/APKINDEX.tar.gz" \
    | grep -iE "content-length|cache-control|cf-cache-status"
done
```

If the rule is ever removed or disabled, `Validate Install Methods` on CI will fail with `BAD signature` on apk and `Maximum file size exceeded` on pacman within ~1 release cycle.

## 6. GitHub Org Variable for the Zone ID

```bash
gh variable set CLOUDFLARE_ZONE_ID \
  --org rediacc \
  --body "9e802649c143c9cefd811d8fd671d31c" \
  --visibility selected --repos console
```

Used by `.ci/scripts/deploy/cf-purge-urls.sh` (belt-and-suspenders cache purge after every upload in cd-dryrun / cd-v2 / promote-stable / ci.yml Validate Promotion). With the Cache Rule active the purge is a no-op, but kept so that if someone disables the Cache Rule we still evict stale entries.

## 7. Verification

After setup, verify with:

```bash
AWS_ACCESS_KEY_ID=<key> \
AWS_SECRET_ACCESS_KEY=<secret> \
aws s3 ls s3://rediacc-releases/ \
  --endpoint-url https://fa51e4a18d553c30e1633288e9733d04.r2.cloudflarestorage.com
```

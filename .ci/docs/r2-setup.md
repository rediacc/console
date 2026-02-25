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

## 5. Verification

After setup, verify with:

```bash
AWS_ACCESS_KEY_ID=<key> \
AWS_SECRET_ACCESS_KEY=<secret> \
aws s3 ls s3://rediacc-releases/ \
  --endpoint-url https://fa51e4a18d553c30e1633288e9733d04.r2.cloudflarestorage.com
```

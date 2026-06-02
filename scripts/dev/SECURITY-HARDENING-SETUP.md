# Security Hardening: External Setup Checklist

The workflow code changes from the Phase 1-3 hardening are committed, but
three things must be done outside the repo before the changes become active:

1. Create a new GitHub App (`rediacc-cd-app`) and store its credentials
2. Mint a scoped Cloudflare token (`CLOUDFLARE_API_TOKEN_PREVIEW`)
3. Push 19 (secret, env) pairs via `migrate-secrets-to-envs.sh`

Order matters: do steps 1 + 2 BEFORE merging the workflow changes, otherwise
the next CI/CD run will fail with missing-secret errors. Step 3 should follow
a successful test run of `promote-stable.yml` so you can verify env-scope
resolution before deleting the org-level copies.

---

## Step 1: Create `rediacc-cd-app` GitHub App

The existing `rediacc-ci-cd` App stays — it gets narrowed to CI-only perms.
A new App handles deploys.

**1a. Create the App** at <https://github.com/organizations/rediacc/settings/apps/new>:
- Name: `rediacc-cd-app`
- Homepage: `https://www.rediacc.com`
- Webhook: disable (uncheck "Active")
- **Repository permissions** (these are the only ones to enable):
  - Actions: Read and write
  - Contents: Read and write
  - Deployments: Read and write
  - Environments: Read and write
  - Metadata: Read-only (auto-required)
  - Packages: Read and write
  - Pull requests: Read and write
- **DO NOT** enable `Administration` — the `check:ci-no-app-admin-perm` CI
  gate will fail builds if any workflow ever requests it.

**1b. Generate a private key** in the App's General settings → "Private keys"
→ "Generate a private key". Download the PEM file.

**1c. Install the App on the org**, scoped to repos: `console`, `renet`,
`middleware`, `elite`, `account`.

**1d. Store credentials**:
```bash
# Org-level variable (App ID, not a secret)
gh variable set CD_APP_ID --org rediacc --visibility selected \
  --repos console --body "<numeric APP ID from settings>"

# Org-level secret (private key contents)
gh secret set CD_APP_PRIVATE_KEY --org rediacc --visibility selected \
  --repos console < path/to/downloaded.pem
```

**1e. After verification, narrow the existing `rediacc-ci-cd` App** at
<https://github.com/organizations/rediacc/settings/apps/rediacc-ci-cd/permissions>:
- Reduce to: Contents (Read), Pull requests (Read), Metadata (Read), Actions (Write).
- Remove: Deployments, Environments, Packages.
- Save and accept the org-installation permission update prompt.

After narrowing, only the new `rediacc-cd-app` can mint deploy-scoped tokens.
A leaked `APP_PRIVATE_KEY` (CI-only) cannot deploy.

---

## Step 2: Mint preview-only Cloudflare token

The existing `CLOUDFLARE_API_TOKEN` stays as the production token. A new
narrower token handles PR preview deploys, so a leak from any PR run cannot
touch production.

**2a. Create the token** at <https://dash.cloudflare.com/profile/api-tokens>:
- Click "Create Token" → "Get started" with custom token
- Name: `rediacc-preview-deploys`
- **Permissions** (only these):
  - Account → Cloudflare Pages: Edit
  - Account → Workers Scripts: Edit (for preview workers)
  - Account → Workers Routes: Edit
  - Zone → Workers Routes: Edit (only on preview zones if you have a
    separate one; otherwise omit)
- **Account Resources**: include only the rediacc account
- **Zone Resources**: if you have a dedicated preview zone (e.g.
  `*.preview.rediacc.com`), restrict to that. Otherwise leave blank — the
  token will still be narrower than the prod one because it only has
  Pages/Workers edit, not the full account access of the prod token.

**2b. Store as org secret**:
```bash
gh secret set CLOUDFLARE_API_TOKEN_PREVIEW --org rediacc \
  --visibility selected --repos console
# (paste the token when prompted)
```

**2c. Verify the token cannot touch production**:
```bash
# Should 403 (insufficient permissions on prod zone):
curl -i -H "Authorization: Bearer $TOKEN" \
  https://api.cloudflare.com/client/v4/zones/<prod-zone-id>/dns_records
```

The 9 PR-preview sites in `ci.yml` and 4 in `cleanup-preview.yml` will use
this token. The cd-stage call (1 site in `ci.yml:669`) keeps using the prod
token because cd-stage purges prod-zone cache on PR runs.

---

## Step 3: Migrate the env-scoped secrets

Three sub-flows depending on who owns each credential:

### 3a. Stripe (NOT in rotation tool — manual)

Stripe credentials are rotated manually via the Stripe dashboard, so the
one-shot push is needed once. After this, future rotations are also manual
(`gh secret set --env ...`).

```bash
# Export the 6 Stripe values from your Stripe dashboard, then:
./scripts/dev/migrate-stripe-to-envs.sh
# Verify, then:
./scripts/dev/migrate-stripe-to-envs.sh --remove-from-org
```

### 3b. SES (US/Asia) — rotation tool handles env-scope automatically

The rotation tool now reads `ROTATION_CONFIG.awsSes[<region>].githubSecretEnvScope`
(see `private/account/scripts/rotation/lib/config.ts`) and pushes the IAM
access key pair to the configured GitHub env (`stable-us` for `ses-us`,
`stable-asia` for `ses-asia`) instead of org-level. ses-eu stays org-level
(used by `ci.yml` preview deploy + `standalone-run.yml` operator email).

Trigger one rotation per region to push the existing keys to env scope:

```bash
./run.sh rotation rotate ses-us
./run.sh rotation rotate ses-asia
```

Then delete the now-orphaned org-level secrets:

```bash
gh secret delete AWS_SES_ACCESS_KEY_ID_US --org rediacc
gh secret delete AWS_SES_SECRET_ACCESS_KEY_US --org rediacc
gh secret delete AWS_SES_ACCESS_KEY_ID_ASIA --org rediacc
gh secret delete AWS_SES_SECRET_ACCESS_KEY_ASIA --org rediacc
```

### 3c. OTLP — rotation tool handles env-scope automatically

The OTLP consumer refs in `lib/config.ts` are now `github-secret-env:<env>:NAME`
for all three regions (each pushed to BOTH `edge-<region>` and `stable-<region>`
since both target=edge and target=stable matrix runs consume the secret).

```bash
./run.sh rotation rotate otlp-eu
./run.sh rotation rotate otlp-us
./run.sh rotation rotate otlp-asia
```

Then delete org-level:

```bash
gh secret delete OTLP_CLIENT_CREDENTIALS_EU --org rediacc
gh secret delete OTLP_CLIENT_CREDENTIALS_US --org rediacc
gh secret delete OTLP_CLIENT_CREDENTIALS_ASIA --org rediacc
```

### Verify after all three sub-flows:

```bash
# Trigger a dry-run promote-stable:
gh workflow run promote-stable.yml --ref main
gh run watch --exit-status

# Inspect the deploy job logs — every "Configure Worker secrets" step should
# show non-empty values per region.
```

---

## Verification (everything together)

After all three steps:

```bash
# CI gate passes (no admin perm requested anywhere)
npm run check:ci-no-app-admin-perm

# All envs present, no orphans
gh api repos/rediacc/console/environments --jq '.environments[].name'
# Expected: edge, edge-asia, edge-eu, edge-us, stable, stable-asia, stable-eu, stable-us

# Org secrets reduced
gh secret list --org rediacc | wc -l
# Expected: previously ~36, now ~24 (removed 12 regional + EU Stripe pair, added CD_APP_PRIVATE_KEY + CLOUDFLARE_API_TOKEN_PREVIEW)

# Env-scoped secrets present
for env in edge stable edge-eu edge-us edge-asia stable-eu stable-us stable-asia; do
  echo "=== $env ==="
  gh secret list --env $env --repo rediacc/console
done

# Trigger a no-op release dispatch to confirm CD pipeline still works end-to-end
gh workflow run "Release" -f release_mode=retry
```

---

## Roll-back

If anything breaks post-merge:
- **Workflow swap (CD_APP_ID, CLOUDFLARE_API_TOKEN_PREVIEW) breaks**: revert
  the relevant workflow file changes and the App/token can sit unused.
- **Env-scoped secrets break a deploy**: re-add to org level via
  `gh secret set --org rediacc <NAME>`. Env-scoped + org-level can coexist;
  workflow-resolution prefers env-scoped, so org-level acts as fallback.
- **Ephemeral GPG breaks PR builds**: revert the `Resolve GPG signing key`
  step in `cd-stage.yml` and the GPG ternary in `ci.yml:660`.

---
name: deploy
description: Deploy the account Worker (per region) and the www Worker to the EDGE or STABLE side from an agent session, for one or several regions, with the Bitwarden (bws) credentials the deploy needs. Covers the preferred CI dispatch, the local path, the keys, verification and rollback. Use whenever a task says deploy, publish, ship to edge/stable/production, or redeploy eu/us/asia.
user-invocable: true
---

# deploy: account and www Workers to edge or stable

A fresh session knows none of this. Read it top to bottom once; every trap listed here was paid for.

## 0. Authorization comes first

A deploy to either side reaches real users. Edge and stable are BOTH production-quality channels (CLAUDE.md, "Release Channels"). Run a deploy only when the operator asked for it **in this task**, naming the side and the regions. Approving a plan is not authorization (docs/agent-reference/ci-gates.md, "Never push to `main` or cut a release"). When the request is ambiguous about side or regions, ask with AskUserQuestion before anything else:

- **Side:** `edge` (edge-rediacc-account-&lt;region&gt;, edge.rediacc.com) or `stable` (rediacc-account-&lt;region&gt;, www.rediacc.com). Stable is what customers use.
- **Regions** (multi-select): `eu`, `us`, `asia`. The www Worker is global, not per region.
- **Components:** account Worker, www Worker, or both.

## 1. What exists (from the tracked code)

| Component | Side | Worker | Wrangler config | D1 |
|---|---|---|---|---|
| account | stable | `rediacc-account-<region>` | `workers/account/wrangler.<region>.toml` | `account-db-<region>` |
| account | edge | `edge-rediacc-account-<region>` | `workers/account/wrangler.edge-<region>.toml` | `edge-account-db-<region>` |
| www | stable | `rediacc-www` (www.rediacc.com) | `workers/www/wrangler.toml` | none |
| www | edge | `edge-rediacc-www` (edge.rediacc.com) | `workers/www/wrangler.edge.toml` | none |

Regions, domains and bucket names live in `regions.json`. The proxy Worker (`rediacc-proxy-eu`) is a separate, manual-only path (`.ci/scripts/deploy/deploy-proxy.sh`) and is out of scope here. The CLI release channels (R2 `edge/` and `stable/`) are promoted by `promote-stable.yml` and `cd-v2.yml`, not by this skill.

## 2. Preferred path: let CI deploy

CI builds from a known commit and pushes the Worker secrets too. Prefer it whenever the code to ship is on `main`:

```bash
# Edge, Workers only (all regions in regions.json), from the latest green CI run on main:
gh workflow run "Release to Edge" -f release_mode=retry -f deploy_workers_only=true
# Stable after the 7-day soak, or forced:
gh workflow run "Release to Production" -f force=true
```

`release_mode` accepts only `retry` or `patch`. `publish_stable=true` on "Release to Edge" is the hotfix path that skips the soak. Watch the run with the ci-watch skill (`.ci/scripts/ci/ci-trace.py --wait --run <id>`), never a hand-rolled poll. CI deploys every region in `regions.json`; a single-region deploy needs the local path below.

## 3. Local path: the credentials (bws)

Every deploy credential comes from Bitwarden Secrets Manager. **Without it nothing can publish.**

1. **The token.** It lives at `~/.config/rediacc/bws-access-token` (mode 0600). Only the operator creates it, with `scripts/dev/bws-rotate.py` in their own terminal; the script refuses non-interactive input, so an agent cannot write it. Check it exists, never print it:
   ```bash
   test -s ~/.config/rediacc/bws-access-token && echo "bws token present" || echo "MISSING: ask the operator to run scripts/dev/bws-rotate.py"
   ```
2. **The binary.** `bws` is installed in the devbox image only, not on the host. Run every credentialed step through `./run.sh devbox exec -- ...` (the devbox reads the token file at login). `./run.sh devbox status` shows whether the devbox is up; `./run.sh setup` creates it.
3. **The profile.** `deploy-workers` in `.ci/config/secret-supply.json` binds exactly what a code deploy needs: `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `TURNSTILE_SITE_KEY`. Confirm the names resolve (values are never printed):
   ```bash
   ./run.sh devbox exec -- env PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env names CLOUDFLARE_API_TOKEN CLOUDFLARE_ACCOUNT_ID TURNSTILE_SITE_KEY
   ```
   All three names printed means ready. A missing name is an operator task (the store entry is absent), not something to work around.

The profile does NOT carry the Worker runtime secrets (`ACCOUNT_*` keys, `AWS_SES_*`, `STRIPE_*`, `OBS_OTLP_*`, `SELLER_*`). A code deploy keeps the secrets already on the Worker; only CI's `set_account_worker_secrets` / `set_www_worker_secrets` steps change them. If a task changes a secret, deploy through CI (section 2).

## 4. Local path: the steps

**Deploy only committed code.** The build reads the working tree. A tree that holds another writer's half-finished change (a migration included) ships that change to production. Check first:

```bash
git status --porcelain -- private/account packages workers   # must print nothing
git -C private/account status --porcelain                      # must print nothing
```

**The account Worker, per region.** Build once, then deploy each chosen region. `SIDE` is `edge` or `production`; any value other than the literal `edge` deploys **production** (`deploy_account.py` does not validate it), so spell it exactly.

```bash
SIDE=edge                 # or: production
REGIONS="eu us"           # any of: eu us asia
./run.sh devbox exec -- env PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env exec --profile deploy-workers -- bash -c '
  set -euo pipefail
  npm run build:packages
  ( cd private/account/web && VITE_TURNSTILE_SITE_KEY="$TURNSTILE_SITE_KEY" VITE_CI_MODE=false \
      npx vite build --outDir ../../../workers/account/dist/account --emptyOutDir )
  grep -rqF -- "$TURNSTILE_SITE_KEY" workers/account/dist/account/assets \
    || { echo "portal build has no Turnstile key: refusing to deploy"; exit 1; }
  for r in '"$REGIONS"'; do
    PYTHONPATH=.ci python3 -m rediacc_ci.deploy.deploy_account --region "$r" --target '"$SIDE"'
  done'
```

`deploy_account` applies the region's D1 migrations (`wrangler d1 migrations apply --remote`), then `wrangler deploy`. Record the `Current Version ID` it prints for each region: that id is the rollback handle.

**The www Worker (global).** Stable uses `.ci/scripts/deploy/deploy-www.sh` (no arguments), edge uses `.ci/scripts/deploy/deploy-edge.sh`:

```bash
WWW_SCRIPT=deploy-edge.sh # or: deploy-www.sh  (stable)
./run.sh devbox exec -- env PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env exec --profile deploy-workers -- bash -c '
  set -euo pipefail
  npm run build:packages
  APP_VERSION="$(.ci/scripts/version/resolve-version.sh --current)" PUBLIC_VIDEO_CDN_BASE_URL=https://media.rediacc.com \
    npm run build -w @rediacc/www
  rm -rf workers/www/dist && mkdir -p workers/www/dist && cp -r packages/www/dist/* workers/www/dist/
  ( cd private/account/web && VITE_TURNSTILE_SITE_KEY="$TURNSTILE_SITE_KEY" VITE_CI_MODE=false \
      npx vite build --outDir ../../../workers/www/dist/account )
  grep -rqF -- "$TURNSTILE_SITE_KEY" workers/www/dist/account/assets \
    || { echo "portal build has no Turnstile key: refusing to deploy"; exit 1; }
  ( cd workers/www && npm install )
  .ci/scripts/deploy/'"$WWW_SCRIPT"''
```

`APP_VERSION` puts the release version in the footer; without it the site shows `0.0.0-dev` and `verify_edge_endpoints` fails. The Turnstile check is not optional. On 2026-09-24 a portal built without the key reached production and nobody could log in.

## 5. Verify

```bash
# account, per region (domains are in regions.json; edge uses the edge domain):
curl -s -o /dev/null -w "%{http_code}\n" https://eu.rediacc.com/account/api/v1/.well-known/server-info
# the read-only smoke tests CI runs (no credentials needed):
PYTHONPATH=.ci python3 -m rediacc_ci.deploy.verify_stable_endpoints
VERSION=<version> PYTHONPATH=.ci python3 -m rediacc_ci.deploy.verify_edge_endpoints
```

Then probe the route or page the change touched: a new route answering its expected refusal (401/403 for a missing credential, not 404) proves the new code is live.

## 6. Rollback

The repo's model is fix-forward (re-dispatch "Release to Edge" with `release_mode=retry`, or deploy the corrected commit). For an immediate revert, wrangler's own rollback works with the version id recorded in step 4:

```bash
./run.sh devbox exec -- env PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env exec --profile deploy-workers -- \
  npx wrangler rollback <previous-version-id> --config workers/account/wrangler.<region>.toml -y
```

A D1 migration is not undone by a Worker rollback. Migrations here only add; a destructive one needs an operator decision before it ships, and `scripts/ops/backup-d1.sh` exports the database first.

## 7. Report

State, per region: side, Worker name, the `Current Version ID`, whether migrations applied (and which), and the verification result. Name anything that was skipped.

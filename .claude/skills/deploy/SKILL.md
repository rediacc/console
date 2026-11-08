---
name: deploy
description: Deploy the shared account and proxy Workers (per region) and the www Worker from an agent session, for one or several regions, with the Bitwarden (bws) credentials the deploy needs. Covers the `release:local --channel edge --workers-only` path, the keys, verification and rollback, and where the CLI's stable channel is promoted instead. Use whenever a task says deploy, publish, ship to production, or redeploy eu/us/asia.
user-invocable: true
---

# deploy: the shared account, proxy and www Workers

A fresh session knows none of this. Read it top to bottom once; every trap listed here was paid for.

## 0. Authorization comes first

agent/plans/PLAN-product-domain-rename.md collapsed the stable and edge Worker pairs into ONE shared set per region on `rediacc.cloud`, so there is no stable Worker any more. A Worker deploy needs no ask: operator ruling 4 of 2026-11-05 lets the session deploy the shared regions without asking, bench first always. `block_unasked_release` admits every Worker deploy module whatever target it names, and a raw `wrangler deploy|rollback` on a shared region Worker's `wrangler.<region>.toml`. Still asked, with `RELEASE_ASKED=ASKED:<YYYY-MM-DDTHH:MM>Z` naming the minute of the operator's answer, which the guard proves from the transcript: the CLI's stable channel (the promote verbs) and a raw wrangler deploy of a config outside the shared region set (`workers/mta-sts`, `workers/ops-health`, `wrangler.dev.toml`).
When the request is ambiguous about regions or components, settle it from the task first; ask with AskUserQuestion only when it cannot be:

- **Regions** (multi-select): `eu`, `us`, `asia`, and `bench` first. The www Worker is global, not per region.
- **Components:** account Worker, proxy Worker, www Worker, or several.

## 1. What exists (from the tracked code)

| Component | Worker | Host | Wrangler config | D1 |
|---|---|---|---|---|
| account | `account-<region>` | `<region>.rediacc.cloud` | `workers/account/wrangler.<region>.toml` | `account-<region>` |
| account (bench) | `account-bench` | `bench.rediacc.cloud` | `workers/account/wrangler.bench.toml` | `account-bench` |
| proxy | `proxy-<region>` | `proxy.<region>.rediacc.cloud` | `workers/proxy/wrangler.<region>.toml` | none |
| proxy (bench) | `proxy-bench` | `proxy.bench.rediacc.cloud` | `workers/proxy/wrangler.bench.toml` | none |
| www | `www` | `www.rediacc.com`, built from edge | `workers/www/wrangler.toml` | none |

Regions, hosts and bucket names (`configs-<region>`, `backups-<region>`) live in `regions.json`. The proxy Workers deploy through `release:local` (`deploy_proxy` with `workers/proxy/wrangler.<target>.toml`); section 4a covers the per-region steps. The bench proxy stays manual. The CLI release channels (R2 `edge/` and `stable/`) are published by CD and `release:local`, and promoted to stable by `cd-release-stable.yml`, not by this skill.

## 2. Paths: locally or by CD

**Shared regions.** `release:local` with `--workers-only` skips the version, builds, Docker and Release steps and redeploys the Workers for the listed regions. The entry builds in a clean release clone of `main` HEAD, runs the gates, applies the order check before any account deploy, and writes a deploy record per Worker to R2 (docs/agent-reference/release-process.md). CD also deploys on every merge.

```bash
npm run release:local -- --channel edge --workers-only --regions eu,us --dry-run
npm run release:local -- --channel edge --workers-only --regions eu,us
```

`--dry-run` prints every step with profile and key names, reads no secret value and writes nothing. The entry sets `APP_VERSION`, builds the portal with the Turnstile key and refuses a build without it, checks the `wrangler_pin`, applies the region's D1 migrations, and pushes the account Worker secrets through `account_secrets_local`. The `--channel edge` name stays: it picks the CLI update channel the Workers announce (`ENVIRONMENT=edge`), not a separate Worker set. The `rediacc_ci.deploy.*` modules run directly too, with no ask, when a step needs them on its own (a stub bootstrap, a single proxy redeploy).

**The CLI's stable channel (asked).** `release:local --channel stable` is refused outright; stable is promoted through CI/CD after the 7-day soak, and the dispatch needs `RELEASE_ASKED` naming the operator's answer:

```bash
RELEASE_ASKED=ASKED:<YYYY-MM-DDTHH:MM>Z gh workflow run "CD - Release to Stable"
```

Watch a run with the ci-watch skill (`.ci/scripts/ci/ci-trace.py --wait --run <id>`), never a hand-rolled poll.

**eu.** Every eu deploy records the rollback handle and the D1 bookmark in its deploy record.

**Bench.** `PYTHONPATH=.ci python3 -m rediacc_ci.ops.deploy_bench` stays as it is, and so does the bench proxy (section 4a, `deploy_proxy --target bench`). A raw `wrangler deploy` on a bench or preview config is refused: its module is the path.

## 3. Local path: the credentials (bws)

Every deploy credential comes from Bitwarden Secrets Manager. **Without it nothing can publish.**

1. **The token.** It lives at `~/.config/rediacc/bws-access-token` (mode 0600). Only the operator creates it, with `scripts/dev/bws-rotate.py` in their own terminal; the script refuses non-interactive input, so an agent cannot write it. Check it exists, never print it:
   ```bash
   test -s ~/.config/rediacc/bws-access-token && echo "bws token present" || echo "MISSING: ask the operator to run scripts/dev/bws-rotate.py"
   ```
2. **The binary.** `bws` is installed on the host (`~/.local/bin/bws`) and in the devbox image. Run credentialed steps directly with `PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env exec --profile <p> -- ...`; `./run.sh devbox exec -- ...` wraps the same command when the host has no `bws`. `which bws` tells which case applies.
3. **The profile.** `deploy-workers` in `.ci/config/secret-supply.json` binds exactly what a code deploy needs: `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `TURNSTILE_SITE_KEY`. Confirm the names resolve (values are never printed):
   ```bash
   PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env names CLOUDFLARE_API_TOKEN CLOUDFLARE_ACCOUNT_ID TURNSTILE_SITE_KEY
   ```
   On a host without `bws`, prefix it with `./run.sh devbox exec --` as step 2 says. All three names printed means ready. A missing name is an operator task (the store entry is absent), not something to work around.

The `deploy-workers` profile does NOT carry the Worker runtime secrets (`ACCOUNT_*` keys, `AWS_SES_*`, `STRIPE_*`, `OBS_OTLP_*`, `SELLER_*`). A code deploy keeps the secrets already on the Worker; only a secrets push changes them.

**The secrets step.** `release:local` pushes the 29 runtime secrets to each account Worker through `rediacc_ci.deploy.account_secrets_local`, with the profile `account-secrets-<region>` (one per shared Worker, in `.ci/config/secret-supply.json`). `--dry-run` on the entry prints the profile and key names only, reads no credential and contacts no service.

The step derives the Worker name, suffix, buckets, R2 jurisdiction and SES region from `regions.json`, refuses unless the wrangler pin agrees (`wrangler_pin`, section 4), then hydrates the profile, runs the Turnstile drift preflight and refuses on drift or on no verdict, and only then runs `set_account_worker_secrets` (one `wrangler secret bulk`, so the assets binding survives). CI's own `set_account_worker_secrets` step is the other path (section 2). Exit codes: 0 pushed (or dry run complete), 1 a refusal, 2 a usage error.

**Stale secrets on a Worker.** `wrangler secret bulk` only adds, so a renamed key stays on the Worker. List what the live Workers hold beyond the push, names only:

```bash
PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env exec --profile deploy-workers -- \
  python3 -m rediacc_ci.ops.prune_worker_secrets --region eu
```

The default is a listing. `--archive --region <r>` is the way to remove extras: Worker secrets are write-only, so each extra's value is read from bws (`LEGACY_BWS` maps a legacy name to its successor key), PUT as `__ARCHIVE_<NAME>`, confirmed listed, and only then deleted; a name with no bws value is reported and left in place. Add `--dry-run` to see which names have a recoverable value without writing anything. `--delete` alone keeps no copy. Both remove through Cloudflare's `DELETE /accounts/{id}/workers/scripts/{name}/secrets/{secret}`, which keeps the ASSETS binding (measured 2026-10-15); `wrangler secret delete` mints a new Worker version and does not. The archive PUT is not measured for the ASSETS binding yet, so check the Worker's static assets after the first run. `check:ci-worker-secret-names` prints the same extras when a token is in its environment.

## 4. What the entry does per deploy

The entry deploys only committed code, from the release clone. A dirty shared checkout never ships, and the clean-clone gate refuses a `HEAD` that differs from `origin/main`.

- **Account Worker, per region.** The portal is built with `VITE_TURNSTILE_SITE_KEY` and the build is refused when the key is absent from `assets` (on 2026-09-24 a portal built without it reached production and nobody could log in). `wrangler_pin` refuses unless `WRANGLER_VERSION` in `.ci/config/constants.sh`, the `wrangler` entry of `workers/account/package.json` and the installed `workers/account/node_modules/wrangler` agree; the fix is `npm ci --prefix workers/account`. `deploy_account` then applies the region's D1 migrations and runs `wrangler deploy`.
- **www Worker (global).** Built with `APP_VERSION` set to the release version, because without it the site shows `0.0.0-dev` and `verify_edge_endpoints` fails.
- **Records.** The `Current Version ID` of each Worker is the rollback handle, and it lands in the deploy record under `release-records/v<V>/<channel>/` in R2.

### 4a. Proxy steps inside the per-region account deploy

Per PLAN-proxy-cd-six-targets (box D2), the per-region deploy job (run by `release:local` and CD) deploys the region's proxy Worker beside the account Worker. The proxy reaches the account Worker over the `ACCOUNT` and `ISSUER` (`ExecutorIssuer`, an RPC entrypoint with `route(bearer)`, `issue(orgId)` and `probe()`) service bindings, and the account config binds `EXECUTOR` back to the proxy. Order:

1. Record before: account and proxy version ids and the D1 time-travel bookmark taken before migrations.
2. Bootstrap proxy deploy, only when the proxy Worker does not exist yet, so the account's `EXECUTOR` binding resolves.
3. Deploy the account Worker, then set the Worker secrets.
4. Deploy the proxy Worker: `deploy_proxy --target <target> --region <r> --version <V>`. The image comes from the durable executor artifacts at `executor/v<V>/` (`rediacc_ci.deploy.executor_artifacts fetch`, sha256 verified), never built from source.
5. Proxy smoke: health 200, unauthenticated server-info 401, and `/v1/ready` 200 with `workerVersion` equal to the deployed id, polled for up to 5 minutes.
6. Enable the console executor (`console_executor`, which sets the `EXECUTOR_MODE=proxy` Worker secret), only when step 5 passed. A region stays closed, answering the coded 503, until then.

Per PLAN-console-executor-multi-org, one region serves every entitled org. The proxy keys one executor container per org (25 per target at most, a further org gets the coded 503 `EXECUTOR_CAPACITY`), and each org's token is issued with the issuer key `executor:<ENVIRONMENT>:<REGION>:<orgId>`. Migration 0066 (the per-org block column) lands with the account deploy, so the D1 bookmark of step 1 covers it. `executor_orgs list` and `verify` read each org's entitlement from the target's D1, and `block` and `unblock` close and reopen one org without touching the others.

Per PLAN-executor-durable-object-policy, the executor runs on the `durable_object` scheduling policy (Design A: `OrgExecutor` per org, `AccountEgress` for egress, an `ExecutorCapacity` coordinator for the cap of 25, with at most 5 heavy `standard-1` instances). Box C1 retired the `Container` class: migration `v3` deletes `ExecutorContainer`, and the `EXECUTOR` binding, the `EXECUTOR_BACKEND` var and `@cloudflare/containers` are gone. Migration `v3` is a Durable Object class lifecycle change, so `wrangler rollback` is refused across it: the deploy record reads `forward-only` and the fix is a forward deploy. A durable-object-policy entry carries no `max_instances`, and no phase has a D1 migration.

The deploy record `deploy-record-<target>-<region>.json` (worker names, version ids before and after, D1 bookmark, smoke rc, artifact manifest sha256s, rollback command) is written once to R2 under `release-records/`. Report it per section 7.

On failure the entry rolls back in reverse order: disable the console executor (`wrangler secret delete EXECUTOR_MODE`), redeploy the previous proxy version from the record (nothing for a first deploy, and nothing for a `forward-only` record: a Phase 1 or Phase 3 deploy adds or removes a Durable Object class, so the fix is a forward deploy), then the account rollback and D1 restore commands are printed and stay human-run. Cloudflare documents no container rollback, so the previous proxy version is redeployed from its own config and fetched artifacts. A redeploy ends every executor session; the web client re-grants.

Bench stays manual: `PYTHONPATH=.ci python3 -m rediacc_ci.deploy.deploy_proxy --target bench` builds renet locally with the dev licence key, because the release renet cannot run under a bench executor.

Bench drills use two verbs of the same module rather than a raw wrangler call or a toml edit. `deploy_proxy --target bench --var KEY=VALUE` (repeatable, bench only) overrides one existing `[vars]` value for that deploy through wrangler's own `--var KEY:VALUE`, and the record names it under `var_overrides`. `deploy_proxy --target <t> [--region <r>] --rollback <full version uuid> [--record PATH]` runs `wrangler rollback` against the target's config, cross-checks the deployments list, smokes that version and writes the record with `rolled_back: true`. It reaches only a version on the same `[[migrations]]` tag: wrangler refuses a rollback across a Durable Object class change, so a `forward-only` record still has no rollback and is fixed forward. No target needs an ask, and `--dry-run`, `--smoke-only`, `--version` and `--var` are refused beside it.

## 5. Verify

```bash
# account, per region (hosts are in regions.json):
curl -s -o /dev/null -w "%{http_code}\n" https://eu.rediacc.cloud/account/api/v1/.well-known/server-info
# the read-only smoke tests CI runs (no credentials needed):
PYTHONPATH=.ci python3 -m rediacc_ci.deploy.verify_stable_endpoints
VERSION=<version> PYTHONPATH=.ci python3 -m rediacc_ci.deploy.verify_edge_endpoints
```

Then probe the route or page the change touched: a new route answering its expected refusal (401/403 for a missing credential, not 404) proves the new code is live.

## 6. Rollback

The repo's model is fix-forward (run `release:local` again, or merge the corrected commit and let CD deploy it). For an immediate revert, wrangler's own rollback works with the version id in the deploy record, and the guard admits it on a shared region Worker's config:

```bash
./run.sh devbox exec -- env PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env exec --profile deploy-workers -- \
  npx wrangler rollback <previous-version-id> --config workers/account/wrangler.<region>.toml -y
```

A D1 migration is not undone by a Worker rollback. Migrations here only add; a destructive one needs an operator decision before it ships, and `PYTHONPATH=.ci python3 -m rediacc_ci.ops.backup_d1` exports the database first.

## 7. Report

State, per region: Worker name, the `Current Version ID`, whether migrations applied (and which), and the verification result. Name anything that was skipped.

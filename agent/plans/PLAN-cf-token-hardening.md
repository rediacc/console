# PLAN: Cloudflare token hardening (scoped tokens, global key as break-glass)

Status: Draft
Depends-On: no-dep -- builds on landed rotation tooling only; the five profile narrowings of #cf7b9860 run beside it
Priority: P1
Concurrency: parallel
Owns: private/account/scripts/rotation/**, .ci/rediacc_ci/ops/cf_auth.py, .ci/config/secret-supply.json
Owner: d778be9d
Updated: 2026-11-26
Live-Proof: none -- operator-attended mints and Bitwarden writes, "global key kept for a while as break-glass" in agent/worklist/d778be9d.jsonl
Item: #f7128272

## Context

The operator asked (2026-11-26) for Cloudflare hardening on the pattern of the AWS split, keeping the Global API Key for a while as break-glass in the read-only `rotation-admin` Bitwarden project, and asked that the official docs be checked. A design agent read developers.cloudflare.com; the quotes below came through WebFetch summaries and are rechecked before any box cites them.

## Doc facts

- An account-owned token can create account-owned tokens with Account API Tokens Write ("To create account-owned API tokens, create a token with Account > Account API Tokens > Edit", fundamentals/api/how-to/create-via-api). The docs name no cap on what it can grant ("it can create tokens with access to any of a user's resources"), so a token-creating token is treated as strong as the account.
- Tokens take a client IP condition (`condition.request_ip.in`, CIDR) and `expires_on` / `not_before` (same page; fundamentals/api/get-started/create-token).
- Account-owned tokens do not support Turnstile per the compatibility matrix (fundamentals/api/get-started/account-owned-tokens), yet rotation rotates Turnstile secrets.
- R2 S3 credentials are a token id plus the SHA-256 of its value, scoped per bucket (r2/api/tokens); the repo already mints these (`rotate.ts:633`, `rotate.ts:748`).
- The Global API Key "has the exact same permissions as the user"; "When possible, use API tokens instead of Global API key" (fundamentals/api/get-started/keys).

## Design

A. `rotation-cf`: an account-owned token bound as `CF_ROTATION_TOKEN` from `rotation-admin` (not `CLOUDFLARE_API_TOKEN`, which is `cf-cd`'s name, `config.ts:150`). Groups: Account API Tokens Read and Write, Workers Scripts Write, Workers Observability Write, Turnstile Sites Write (if B1 proves it), Zone Read on all zones (`listZoneIds` builds `cf-cd`'s zone policy; a narrower view silently narrows `cf-cd`), DNS Write on `rediacc.cloud` only. Dropped from today's management set: D1 Write, Workers R2 Storage Write, Workers Routes Write, DNS Write on all zones, the user-scope token pair. IP condition: this host's IPv4 /32 and IPv6 prefix. Expiry 90 days, rolled at 60 through a `rotation-cf` slug (create successor, write to `rotation-admin`, verify, delete predecessor); `check` warns under 21 days.

B. Every other global-key reader gets a `cf-job-<purpose>` slug and binds `CF_JOB_TOKEN` (which `cf_auth` already prefers, df62ac3c9f): mirror-config-store, cf-usage-report (also stop feeding it `cf-cd`), ops-health, cf_notifications, r2_lifecycle and backup_d1 (move to `resolve_scoped`), observability_volume, and the five profiles of #cf7b9860. The deploy-bench token also needs Account API Tokens Read (`deploy_bench.py:560-582` runs `rotation check`). enterprise-mint stays user-owned with expiry and IP added. cf_retire stays break-glass or a per-run short-TTL token.

C. Global key: both fallbacks (`credentials.ts:89`, `cf_auth.py:345`, `:370`) require `CF_BREAK_GLASS=1`; delete the pair from `ci-shared` once no profile binds it; after 30 days with no break-glass use the operator changes the key in the dashboard and stores it only in `rotation-admin`.

## Boxes

- [ ] B1 Live capability probe with a throwaway 1-hour account token holding the `rotation-cf` set: create and delete a child token carrying a group the parent lacks, list Turnstile widgets, list a bench Worker's secrets, compare the zone count with the global key's; record each result. A refused Turnstile read moves Turnstile to a user-owned `rotation-cf-turnstile` token.
- [ ] B2 Code in private/account: `resolveCloudflare` order `CF_ROTATION_TOKEN`, then `CLOUDFLARE_API_TOKEN` with a warning, then the global key only under `CF_BREAK_GLASS=1`; readiness probe on `/accounts/{id}/tokens/verify`; the `rotation-cf` slug with self-rotation and expiry; `expires_on` and `condition` in `buildCfTokenPolicies`; a guard refusing a `cf-cd` mint whose zone count drops; tests. Accept: `cd private/account && npx vitest run tests/integration/rotation` rc 0 and `npx tsc --noEmit` rc 0.
- [ ] B3 Bootstrap `rotation-cf` (operator grants `rotation-admin` write for the run): `CF_BREAK_GLASS=1 ./run.sh rotation rotate rotation-cf`, then read only again. Accept: `./run.sh rotation check` rc 0 with only `CF_ROTATION_TOKEN` bound.
- [ ] B4 Re-mint `cf-r2-media` as account-owned and drop the `/user/tokens` listing. Accept: `./run.sh rotation rotate cf-r2-media` rc 0 and `check` rc 0.
- [ ] B5 Mint the `cf-job-*` slugs and rebind the profiles. Accept per job: its run rc 0 with `CF_GLOBAL_API_KEY` unset; `npm run check:ci-secret-supply` rc 0.
- [ ] B6 Move `r2_lifecycle` and `backup_d1` to `resolve_scoped`, gate both `cf_auth` fallbacks on `CF_BREAK_GLASS`, rebind `ops-cf-usage-report.yml`. Accept: `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest -q .ci/rediacc_ci/tests -k cf_auth` rc 0.
- [ ] B7 Delete `CF_GLOBAL_API_KEY` and `CF_EMAIL` from `ci-shared` (operator). Accept: only the `rotation` profile in `.ci/config/secret-supply.json` names them.
- [ ] B8 (time: 30 days after B7) The operator changes the global key and stores the new value in `rotation-admin` only. Accept: a break-glass `./run.sh rotation list` rc 0.

## Operator-only

B1's global-key mint, B3, each `rotation-admin` write toggle, B7, B8, the IPv6 prefix length and whether the IPv4 address is static, and any `rotation-cf-turnstile` creation.

## Risks

A token that creates tokens is as strong as the account; the IP condition, the expiry and the read-only store are the real controls. A changed home IP locks `rotation-cf` out until break-glass. GitHub-hosted runners cannot be IP-filtered, so CI tokens get least privilege and expiry only. Holding both credentials doubles exposure until B7 and B8, so both get dates.

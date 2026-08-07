---
name: account-dev
description: Running and driving the account server development environment: ./run.sh account dev (gateway + portal + www + RustFS), the TEST_MODE seams, dev credentials and seeding, port mechanics and orphan cleanup, the tsx no-hot-reload rule, and how the CLI connects to it (./rdc.sh --dev, config init --server, headless auth chains). Use when a task needs a live account server: license/subscription flows, config-storage work, portal testing, drills, or diagnosing gateway weirdness.
tools: Bash, Read, Edit, Write, Grep, Glob
model: opus
---

You run the dev account environment. It is one command with many moving parts; the
notes below are what the command's own output does not tell you.

## What ./run.sh account dev starts

One dev gateway (tsx src/entry/dev-gateway.ts, API on the gateway port) fronting the
account portal (vite) and www (astro dev), plus a Docker RustFS for config-blob storage
(without it configService is null and the portal says config storage is not
configured). State lands in an .account-state file (gateway_port, pids, worktree); a
new `account dev` auto-kills the previous one via that file.

Port mechanics: it scans for consecutive FREE ports starting at 4808. ORPHANED
gateways (from killed shells, crashed drills) keep 4808 bound and push the next start
to 4811+. Consequences: never hardcode 4808; read the port from the startup output or
.account-state; a config that recorded the old port strands its writes. Kill orphans
by pattern (`pkill -f dev-gateway.ts`) only when you know no other session owns one;
the drills instead re-read the port per connection through a TCP shim.

THE tsx RULE: tsx does NOT hot-reload. A long-running gateway serves the code from
when it started; after any src change under private/account, RESTART the gateway or
you will debug phantom old behavior. Drills restart it unconditionally for this
reason, and re-read the printed credentials each time (dev passwords are random per
start).

## Credentials and seeding (all TEST_MODE, printed at startup)

account_dev_credentials provisions three logins with fresh random passwords: the root
user (ROOT_EMAIL, default root@rediacc.dev), dev-user@rediacc.io (given a
PROFESSIONAL subscription so paid surfaces like the web console are reachable), and
dev-partner@rediacc.io (seeded partner demo data). The dev user's config store is
seeded with the CONSTANT password DevConsole123! (never rotated: an idempotent
re-seed cannot re-wrap the CEK without the prior password).

The /test/* surface (mounted ONLY when TEST_MODE=true; hard-off on Cloudflare):
- POST /test/ensure-login {email,password}: create-or-reset a user.
- POST /test/ensure-subscription {email,planCode,maxActivations?}: DELETES the
  customer's subscriptions and creates one; maxActivations int 1..10000 (default 5)
  makes slot walls reachable (cap 1 + two machines). Never call it mid-scenario to
  lower a cap: that orphans issued licenses; use PUT /admin/subscriptions/:id.
- GET /test/totp-code?email=...: the CURRENT computed TOTP for a seeded store (real
  secret, no hardcoded bypass): this is the headless 2FA path.
- POST /test/seed-config-store, /test/seed-demo-partner, /test/emails (captured
  outbound mail), plus exam/study seeding.
Headless auth chain precedent: .ci/scripts/test/run-account-e2e.sh (node entry +
TEST_MODE, register/login/device-code mint); the drills' lib
(scripts/drills/lib.sh drill_account_*) is the curl-based equivalent.

## Connecting the CLI

- `./rdc.sh --dev ...` (or RDC_DEV=1): reads REDIACC_ACCOUNT_SERVER + X25519 key from
  private/account/.env, seeds/patches ~/.config/rediacc/dev.json, runs with
  REDIACC_CONFIG=dev, and FAILS FAST if no dev gateway is running. Bare ./rdc.sh
  targets PRODUCTION config.
- Explicit config against a chosen gateway: `rdc config init <name> --server
  http://127.0.0.1:<port>` now also syncs that server's E2E public key at init (an
  unreachable server only warns; the first successful request heals). Then
  `rdc subscription login --token <api-token> --server <url>`.
- ORDERING TRAP: any CLI invocation auto-creates the config named by an exported
  REDIACC_CONFIG. Run the explicit `config init` BEFORE exporting, or init dies with
  "already exists" (and the auto-created config gets the PRODUCTION server's key,
  since a bare config has no accountServer).
- API tokens bind to the client IP on FIRST use: mixing curl (direct) and CLI
  (tunnelled) against one token poisons it with a 403 that renders as an IP-binding
  message. Let the intended consumer be the token's first user.

## Tests and environments

- Unit/integration (vitest, in-memory sqlite, no gateway needed): cd private/account
  && npm test. E2E (Playwright, gateway REQUIRED): ./run.sh account test e2e
  [--grep @tag].
- The on-premise entry (src/entry/on-premise.ts with DELEGATION_CERT_PATH) is the
  only server that attaches delegationCert to issued licenses; the dev gateway is the
  cloud entry. Delegated-flow work needs that entry or the license-mint fixtures.
- bench (bench.rediacc.com) is a real deploy target via scripts/dev/deploy-bench.sh,
  not a local mode; edge/production deploy from CI only. Deploy order for licensing
  changes: account servers BEFORE renet BEFORE CLI.
- `./run.sh account reset` regenerates .env; the gateway must be restarted to pick
  env changes up (same tsx rule).

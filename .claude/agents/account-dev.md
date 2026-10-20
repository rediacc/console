---
name: account-dev
description: Running and driving the account server development environment: ./run.sh account dev (gateway + portal + www + RustFS), the TEST_MODE seams, dev credentials and seeding, port mechanics and orphan cleanup, the tsx no-hot-reload rule, and how the CLI connects to it (./rdc.sh --dev, config init --server, headless auth chains). Also the bench environment (bench.rediacc.com): deploying the account worker with rediacc_ci.ops.deploy_bench, wrangler deploys, Cloudflare D1 databases and R2 buckets, worker secrets, and rediacc_ci.ops.reset_bench wipes. Use when a task needs a live account server or a bench deploy: license/subscription flows, config-storage work, portal testing, drills, D1 or wrangler trouble, or diagnosing gateway weirdness.
tools: Bash, Read, Edit, Write, Grep, Glob
model: opus
---

You run the dev account environment. It is one command with many moving parts; the notes below are what the command's own output does not tell you.

## What ./run.sh account dev starts

One dev gateway (tsx src/entry/dev-gateway.ts, API on the gateway port) fronting the account portal (vite) and www (astro dev), plus a Docker RustFS for config-blob storage (without it configService is null and the portal says config storage is not configured). State lands in an .account-state file (gateway_port, pids, worktree); a new `account dev` auto-kills the previous one via
that file.

Port mechanics: it scans for consecutive FREE ports starting at 4800. ORPHANED gateways (from killed shells, crashed drills) keep 4800 bound and push the next start to 4803+. Consequences: never hardcode 4800; read the port from the startup output or .account-state; a config that recorded the old port strands its writes. Kill orphans by pattern (`pkill -f dev-gateway.ts`) only when
you know no other session owns one; the drills instead re-read the port per connection through a TCP shim.

THE tsx RULE: tsx does NOT hot-reload. A long-running gateway serves the code from when it started; after any src change under private/account, RESTART the gateway or you will debug phantom old behavior. Drills restart it unconditionally for this reason, and re-read the printed credentials each time (dev passwords are random per start).

`npm run vm:check` runs its account phase against this gateway and follows the same rule: it reuses a gateway only when the record `.ci/cache/vm-check/gateway.json` matches the account worktree, and otherwise restarts it and leaves it running for the next run (a restart rotates the dev passwords and may move the port, so re-read both from the startup output).

## Credentials and seeding (all TEST_MODE, printed at startup)

account_dev_credentials provisions three logins with fresh random passwords: the root user (ROOT_EMAIL, default root@rediacc.dev), dev-user@rediacc.io (given a PROFESSIONAL subscription so paid surfaces like the web console are reachable), and dev-partner@rediacc.io (seeded partner demo data). The dev user's config store is seeded with the CONSTANT password DevConsole123! (never
rotated: an idempotent re-seed cannot re-wrap the CEK without the prior password).

The /test/* surface (mounted ONLY when TEST_MODE=true; hard-off on Cloudflare):
- POST /test/ensure-login {email,password}: create-or-reset a user.
- POST /test/ensure-subscription {email,planCode,maxActivations?}: DELETES the
customer's subscriptions and creates one; maxActivations int 1..10000 (default 5) makes slot walls reachable (cap 1 + two machines). Never call it mid-scenario to lower a cap: that orphans issued licenses; use PUT /admin/subscriptions/:id.
- GET /test/totp-code?email=...: the CURRENT computed TOTP for a seeded store (real
secret, no hardcoded bypass): this is the headless 2FA path.
- POST /test/seed-config-store, /test/seed-demo-partner, /test/emails (captured
outbound mail), plus exam/study seeding. Headless auth chain precedent: .ci/rediacc_ci/testrun/account_e2e.py (node entry + TEST_MODE, register/login/device-code mint); the drills' lib (rediacc_ci.drills.lib, `Drill.account_*`) is the urllib-based equivalent.

## Connecting the CLI

- `./rdc.sh --dev ...` (or RDC_DEV=1): reads the gateway port from .account-state and the
X25519 public key from the running gateway's /.well-known/server-info, seeds/patches ~/.config/rediacc/dev.json, runs with REDIACC_CONFIG=dev, and FAILS FAST if no dev gateway is running. Bare ./rdc.sh targets PRODUCTION config.
- Explicit config against a chosen gateway: `rdc config init <name> --server
http://127.0.0.1:<port>` now also syncs that server's E2E public key at init (an unreachable server only warns; the first successful request heals). Then `rdc subscription login --token <api-token> --server <url>`.
- ORDERING TRAP: any CLI invocation auto-creates the config named by an exported
REDIACC_CONFIG. Run the explicit `config init` BEFORE exporting, or init dies with "already exists" (and the auto-created config gets the PRODUCTION server's key, since a bare config has no accountServer).
- API tokens bind to the client IP on FIRST use: mixing curl (direct) and CLI
(tunnelled) against one token poisons it with a 403 that renders as an IP-binding message. Let the intended consumer be the token's first user.

## Tests and environments

- Unit/integration (vitest, in-memory sqlite, no gateway needed): cd private/account
&& npm test. E2E (Playwright, gateway REQUIRED): ./run.sh account test e2e [--grep @tag].
- The on-premise entry (src/entry/on-premise.ts with DELEGATION_CERT_PATH) is the
only server that attaches delegationCert to issued licenses; the dev gateway is the cloud entry. Delegated-flow work needs that entry or the license-mint fixtures.
- bench (bench.rediacc.com) is a real deploy target via `PYTHONPATH=.ci python3 -m rediacc_ci.ops.deploy_bench`,
not a local mode; edge/production deploy from CI only. Deploy order for licensing changes: account servers BEFORE renet BEFORE CLI.
- Bench email is readable from D1 (operator ruling 2026-10-13). `/test/*` stays off on bench, and reauth links, magic links and invitation tokens are stored hashed, so `EMAIL_CAPTURE_D1 = "true"` in `workers/account/wrangler.bench.toml` makes the worker also copy each outgoing email into the `captured_emails` table (`id`, `created_at`, `recipient`, `subject`, `kind`, `text_body`). No route exposes the table, and the account server refuses to start with the switch unless `ENVIRONMENT` is `bench`. Each write deletes rows older than 7 days.
The newest link for a recipient, run from the console root: `PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env exec --profile deploy-bench -- bash -c "cd workers/account && CLOUDFLARE_API_KEY=\$CF_GLOBAL_API_KEY CLOUDFLARE_EMAIL=\$CF_EMAIL npx wrangler d1 execute account-db-bench --remote --config wrangler.bench.toml --json --command \"SELECT created_at, kind, subject, text_body FROM captured_emails WHERE recipient = '<address>' ORDER BY created_at DESC LIMIT 1\""`.
WARNING: `text_body` holds LIVE links (session elevation, sign-in, invitation). Never paste a row into a commit, a PR, a worklist item or a report; extract the link in-process and use it.
- There is no private/account/.env: secrets come from Bitwarden through `bws_env exec --profile account-dev` (.ci/config/secret-supply.json `consumers`), constants from the committed private/account/dev.defaults.env. `./run.sh account reset` pushes a fresh shared DEV keypair to the ACCOUNT_*_DEV store entries; the gateway must be restarted to pick it up (same tsx rule), and other machines re-run `./run.sh setup`.

Database: the dev data lives in `private/account/account.db` (better-sqlite3, opened
by `src/entry/dev-gateway.ts` with cwd `private/account`), NOT in wrangler/D1 -- `wrangler.toml` declares a D1 binding that the dev path never touches. Browse it with `./run.sh account db`, which runs Drizzle Studio against that file; `drizzle.config.ts` already points at it. **`./run.sh account reset` DELETES account.db** (plus -wal/-shm), so anything you were reading in Studio is
gone after a reset.

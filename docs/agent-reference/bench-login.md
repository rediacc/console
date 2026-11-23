# Headless bench login (`npm run login:bench`)

`npm run login:bench` logs the `eu-bench` rdc config into https://bench-eu.rediacc.cloud with the operator's own bench account, with no prompt and no browser (operator order 2026-10-27). It is bench only. Edge and stable keep human login, and no profile binds an account for them. The WebAuthn relying party is the host, so a passkey registered on `bench.rediacc.cloud` does not work on `bench-eu.rediacc.cloud`; the login uses the password and the TOTP seed, never a passkey.

## Whose step it is

Running `npm run login:bench` is an agent's own step, never the operator's (operator order 2026-10-30). It is the remedy whenever an `eu-bench` command answers that the login is "tied to another network address", that the IP address changed, or "Not logged in": run it, then rerun the command. The CLI's own text for that error tells a human to type an authenticator code in an interactive terminal; for `eu-bench` that code is derived from the vault, so nobody is asked for it.

Three places carry this so a session does not have to remember it:

- `rediacc_ci.ops.live_proof record` runs `npm run login:bench` once when an `eu-bench` step fails that way, retries the step, and names the remedy if the login itself fails.
- The trapguard rule `bench-login-is-the-agents-step` (`.claude/hooks/trapguard/dispatch.py`) adds the remedy to the context after any `./rdc.sh --config eu-bench` call that printed the error.
- `block_settled_questions` refuses an AskUserQuestion asking the operator for an `eu-bench` authenticator code or login.

The same holds for a production config (`eu-remote`, `eu-edge`) whose token answers TOKEN_IP_MISMATCH: `PYTHONPATH=.ci python3 -m rediacc_ci.ops.rebind_login -- <rdc argv...>` derives the root account's code from `ROOT_TOTP_SEED` (the `root-login` profile) and runs `./rdc.sh <argv>` with it in `REDIACC_IP_REBIND_CODE`, which the CLI POSTs once when no terminal is attached. The code never reaches argv or output, and a refused code is a named CLI failure with no retry.

The operator's door is narrower: a value still holding `PLACEHOLDER-operator-fills`, or a dead `bws` machine token (see `.ci/config/bws-rotation-notice.txt`).

## What it does

`rediacc_ci.ops.login_bench` runs these steps in order and stops at the first one that fails, naming it (exit 1):

1. Refuses any server other than `https://bench-eu.rediacc.cloud` and any config other than `eu-bench` (a named error, exit 2), before any credential is read.
2. Re-executes under the `bench-login-eu` Bitwarden profile through `rediacc_ci.core.bws_env exec`.
3. Refuses a value that is unset or still the placeholder `PLACEHOLDER-operator-fills`, naming the Bitwarden entry and its id (exit 2).
4. Refreshes the bench IP allowlist with `rediacc_ci.ops.bench_access add-current`, which binds its own `bench-access` profile.
5. Derives the six-digit TOTP code in memory (`rediacc_ci.ops.totp`, RFC 6238, HMAC-SHA1, 30 s, 6 digits) and runs `./rdc.sh --config eu-bench subscription login --server https://bench-eu.rediacc.cloud`.
6. Runs `./rdc.sh --config eu-bench config remote enable --config-id 1880812c-2086-4daa-a620-8f84aa3b6e7c --api-url https://bench-eu.rediacc.cloud`, unless `config remote status` already reports `eu-bench` connected to that config id on bench. `enable` refuses a linked config with "nothing to enable" (exit 2), so a repeat run skips the step instead of failing on it. The tool still passes the password-slot flag that the removal of password key slots deleted, so this step waits on the operator-created recovery code and a machine secret (`--machine-secret <id>`, PLAN-rmcp-policy-record.md).
7. Prints `./rdc.sh --config eu-bench config remote status`.

## The secrets

The `bench-login-eu` consumer in `.ci/config/secret-supply.json` binds four Bitwarden entries, mapped by id in `.ci/config/bws-secret-map.json`. The three bench entries carry the region in their store name (`BENCH_ROOT_PASSWORD_EU`, `BENCH_ROOT_TOTP_SEED_EU`, `BENCH_STORE_MASTER_PASSWORD_EU`) and the profile maps each onto the unsuffixed name the tool reads:

| Name | Holds | Reaches the CLI as |
|---|---|---|
| `ROOT_EMAIL` | the root address, the same on every environment | `REDIACC_LOGIN_EMAIL` |
| `BENCH_ROOT_PASSWORD_EU` | the eu bench root password (its own, not the production one) | `REDIACC_LOGIN_PASSWORD` |
| `BENCH_ROOT_TOTP_SEED_EU` | the base32 TOTP seed of the eu bench root, server-generated and written back by the re-enrol path | `REDIACC_LOGIN_TOTP`, the derived code only |
| `BENCH_STORE_MASTER_PASSWORD_EU` | the master password of the eu-bench remote config store | `REDIACC_STORE_MASTER_PASSWORD` |

Every value travels by name in a child's environment. None is put on argv, printed or logged, and each `rdc` child receives only the values its own step needs. `RDC_DEV`, `REDIACC_CONFIG`, `REDIACC_TOKEN` and `REDIACC_ACCOUNT_SERVER` are dropped from every child, so an inherited dev selection cannot point the login at another server or config. The allowlist child receives none of the four.

## One bench per region

The us and asia benches (`us-bench`, `asia-bench`, hosts from `regions.json` `bench`) log in with `npm run login:bench -- --region us|asia`. Each bench, the eu one included, keeps its own root password, TOTP seed and store master password, named with the region suffix and bound by a region profile under the names `login_bench` reads:

| Profile | Entries |
|---|---|
| `bench-login-eu` | `ROOT_EMAIL`, `BENCH_ROOT_PASSWORD_EU`, `BENCH_ROOT_TOTP_SEED_EU`, `BENCH_STORE_MASTER_PASSWORD_EU` |
| `bench-login-us` | `ROOT_EMAIL`, `BENCH_ROOT_PASSWORD_US`, `BENCH_ROOT_TOTP_SEED_US`, `BENCH_STORE_MASTER_PASSWORD_US` |
| `bench-login-asia` | `ROOT_EMAIL`, `BENCH_ROOT_PASSWORD_ASIA`, `BENCH_ROOT_TOTP_SEED_ASIA`, `BENCH_STORE_MASTER_PASSWORD_ASIA` |

`deploy-bench-eu|us|asia` and `backup-push-bench-eu|us|asia` bind the region's `ACCOUNT_CONFIG_SERVER_KEY_BENCH_<R>`, `ACCOUNT_BACKUP_STORE_KEK_BENCH_<R>`, `ACCOUNT_BACKUP_S3_*_BENCH_<R>` and `BENCH_ROOT_PASSWORD_<R>`; the rest of each set is shared by every bench. The region entries are `optional` in those profiles until box L1 of `agent/plans/PLAN-multi-region-bench.md` writes them to the store. `WK_BENCH_ORIGIN` in `.ci/config/well-known.env` is the eu bench's origin; the other benches' hosts come from `regions.json`.

`PYTHONPATH=.ci python3 -m rediacc_ci.ops.totp` runs the RFC 6238 Appendix B self-check and, with `BENCH_ROOT_TOTP_SEED` set, confirms the seed decodes. It prints only `ok` lines, never the seed or a code.

## Bench carries hostinger production data: reset guard, pins, escrow

Hostinger, a production machine, backs up through the eu bench, so the bench holds the only off-site copy of its repositories once the first bench snapshot commits (`agent/plans/PLAN-hostinger-to-bench.md`). Four controls keep a bench wipe, an allowlist expiry or a lost config from costing that copy.

- **Reset guard.** `.ci/config/bench-production.json` lists each protected `{subscription_id, region, machine, reason, plan}`. While an entry names a region, `rediacc_ci.ops.reset_bench` refuses every mode for it (`--yes`, `--d1-only`, `--r2-only`) with exit 2 before any credential is read, the drills' cleanup refuses to delete a listed subscription's rows, and a bench signer of that region is not stopped. There is no override flag: un-protecting is a reviewed commit that removes the entry (`.ci/rediacc_ci/ops/bench_production.py`).
- **Pins.** `.ci/config/bench-access-pinned.json` lists hostinger's IPv4 and IPv6 /64 as entries that never expire, are never evicted and sit outside the five-address cap of the bench WAF rule. Every mutating `bench_access` run writes a missing pin back, `remove` and `clear` refuse them, and `PYTHONPATH=.ci python3 -m rediacc_ci.ops.bench_access verify-pinned` (read-only) exits 1 when one is absent from the live rule.
- **Escrow.** The `hostinger-escrow` profile binds `HOSTINGER_REPO_CREDENTIALS_ESCROW` (repository name to its GUID and credential, per tag), a copy held outside bench. The value travels only through the environment of the step that writes it.
- **Config import.** `rdc config import-machine <machine> --from <config> [--dry-run] [-o json]` copies a machine, its repositories and their bound strategies from another config into the active one, naming entries only; a second run reports no change.

The data-loss rule behind them: the old eu buckets and the old config's token stay until the first scheduled bench run is verified after a store verify and a restore test of every repository.

## Bench signs licences with the production key

Bench signs licences with the PRODUCTION ED25519 pair (operator ruling 2026-10-27, "Bench signs with production key"). The `deploy-bench-eu` profile binds `ACCOUNT_ED25519_PRIVATE_KEY` and `ACCOUNT_ED25519_PUBLIC_KEY` from the same unsuffixed entries the edge and stable `account-secrets-*` profiles bind, fingerprint `fb37f1ae16f8b7c0` through `rediacc_ci.release.renet_key_gate.key_fingerprint`. A released renet bakes the production public key, so it verifies a bench licence.

The X25519 pair stays DEV. It is the E2E envelope key, not the licence signer, and every bench config already carries the DEV X25519 public key as its account `e2ePublicKey`; moving the pair would fail every bench response with "Decryption failed". The JWT secret and the server API key stay DEV as well.

The `deploy-proxy-bench-eu` profile binds the production ED25519 public key too, so the renet the bench proxy image builds verifies a production-signed bench licence; the bench proxy was redeployed with it on 2026-10-27 (version 5622d50c).

A TOTP step is accepted once per user (account 8c656b6). Two runs that log in within the same 30 s step collide: the second is refused "Invalid verification code". Nothing waits automatically: a caller that runs a second TOTP-using command right after `npm run login:bench` (for example `rdc config remote refresh`) must itself wait for the next 30 s step before computing the codes, or it is refused before anything is written.

## Stable and edge root

Stable and edge share one production root, and `/auth/login` there answers 400 "Captcha verification required", so the agent path is the root API token kind (`private/account/CLAUDE.md` *Root API token*). The operator mints `ROOT_API_TOKEN_EU` once in the portal at `/account/admin/root-tokens`, and the `root-login` profile binds it with `ROOT_TOTP_SEED`. `ROOT_EMAIL` and `ROOT_PASSWORD` are optional there, read only by `--password`. The bench root keeps its own password and seed.

`PYTHONPATH=.ci python3 -m rediacc_ci.ops.root_login --target stable|edge --region eu` runs token mode: it refuses an unset, placeholder or non-`rdr_` value (rc 2, naming the entry), opens a token session with a code derived from the seed in memory, and prints `root session opened (<target> <region>, token, session until HH:MMZ, token expires in N days)`. A session lasts 10 minutes.

- **Refresh path.** The token binds to one IPv4 address and one IPv6 /64. When the address changes (the nightly change), `session` answers 403 `ROOT_TOKEN_IP_MISMATCH`; the tool then calls `bind` with a code, waits for the next 30 s step (the account spends a code once), opens the session again and prints `ip rebound (<family>)`. A bind from the address already bound spends no code. At most 6 binds per 24 h per token.
- **Flags.** `--check` makes no request and validates the vault values. `--probe stats|audit` makes one read-only GET. `--control` proves two refusals live: a session-less call answers 403 `ROOT_TOKEN_SESSION_REQUIRED`, and `/auth/login` without a captcha token still answers 400. `--rotate` (or `ROOT_LOGIN_AUTOROTATE=1` with fewer than 14 days left) mints the successor and stores it in the same `ROOT_API_TOKEN_EU` entry; a failed vault write leaves the old token valid for about an hour, so a rerun recovers. `--password` is the older sign-in.
- **Region rule.** Tokens live in one regional database, so the eu token is `ROOT_API_TOKEN_EU`. `--region us|asia` is refused with the entry name its token would take (`ROOT_API_TOKEN_US`, `ROOT_API_TOKEN_ASIA`).
- **The one operator step.** Minting needs the root cookie session, a fresh step-up and TOTP enabled on the root user, so the operator mints the first token in the portal and stores the value as `ROOT_API_TOKEN_EU`. After that the tool rotates it on its own for up to 365 days from the first mint; past that, the operator mints again. Disabling 2FA on the root user revokes every root token.
- **Honest limit.** Whoever holds both `ROOT_API_TOKEN_EU` and `ROOT_TOTP_SEED` can rebind, so the binding protects against the token value leaking alone, and every bind is audited (`root_token.ip_bound`).

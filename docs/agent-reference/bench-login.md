# Headless bench login (`npm run login:bench`)

`npm run login:bench` logs the `eu-bench` rdc config into https://bench.rediacc.com with the operator's own bench account, with no prompt and no browser (operator order 2026-10-27). It is bench only. Edge and stable keep human login, and no profile binds an account for them.

## What it does

`rediacc_ci.ops.login_bench` runs these steps in order and stops at the first one that fails, naming it (exit 1):

1. Refuses any server other than `https://bench.rediacc.com` and any config other than `eu-bench` (a named error, exit 2), before any credential is read.
2. Re-executes under the `bench-login` Bitwarden profile through `rediacc_ci.core.bws_env exec`.
3. Refuses a value that is unset or still the placeholder `PLACEHOLDER-operator-fills`, naming the Bitwarden entry and its id (exit 2).
4. Refreshes the bench IP allowlist with `rediacc_ci.ops.bench_access add-current`, which binds its own `bench-access` profile.
5. Derives the six-digit TOTP code in memory (`rediacc_ci.ops.totp`, RFC 6238, HMAC-SHA1, 30 s, 6 digits) and runs `./rdc.sh --config eu-bench subscription login --server https://bench.rediacc.com`.
6. Runs `./rdc.sh --config eu-bench config remote enable --master-password --config-id 1880812c-2086-4daa-a620-8f84aa3b6e7c --api-url https://bench.rediacc.com`, unless `config remote status` already reports `eu-bench` connected to that config id on bench. `enable` refuses a linked config with "nothing to enable" (exit 2), so a repeat run skips the step instead of failing on it.
7. Prints `./rdc.sh --config eu-bench config remote status`.

## The secrets

The `bench-login` consumer in `.ci/config/secret-supply.json` binds four Bitwarden entries, mapped by id in `.ci/config/bws-secret-map.json`:

| Name | Holds | Reaches the CLI as |
|---|---|---|
| `REDIACC_BENCH_EMAIL` | the operator's bench login address | `REDIACC_LOGIN_EMAIL` |
| `REDIACC_BENCH_PASSWORD` | the operator's bench login password | `REDIACC_LOGIN_PASSWORD` |
| `REDIACC_BENCH_TOTP_SEED` | the base32 TOTP seed of that account | `REDIACC_LOGIN_TOTP`, the derived code only |
| `REDIACC_BENCH_MASTER_PASSWORD` | the master password of the eu-bench remote config store | `REDIACC_STORE_MASTER_PASSWORD` |

Every value travels by name in a child's environment. None is put on argv, printed or logged, and each `rdc` child receives only the values its own step needs. `RDC_DEV`, `REDIACC_CONFIG`, `REDIACC_TOKEN` and `REDIACC_ACCOUNT_SERVER` are dropped from every child, so an inherited dev selection cannot point the login at another server or config. The allowlist child receives none of the four.

`PYTHONPATH=.ci python3 -m rediacc_ci.ops.totp` runs the RFC 6238 Appendix B self-check and, with `REDIACC_BENCH_TOTP_SEED` set, confirms the seed decodes. It prints only `ok` lines, never the seed or a code.

## Bench signs licences with the production key

Bench signs licences with the PRODUCTION ED25519 pair (operator ruling 2026-10-27, "Bench signs with production key"). The `deploy-bench` profile binds `ACCOUNT_ED25519_PRIVATE_KEY` and `ACCOUNT_ED25519_PUBLIC_KEY` from the same unsuffixed entries the edge and stable `account-secrets-*` profiles bind, fingerprint `fb37f1ae16f8b7c0` through `rediacc_ci.release.renet_key_gate.key_fingerprint`. A released renet bakes the production public key, so it verifies a bench licence.

The X25519 pair stays DEV. It is the E2E envelope key, not the licence signer, and every bench config already carries the DEV X25519 public key as its account `e2ePublicKey`; moving the pair would fail every bench response with "Decryption failed". The JWT secret and the server API key stay DEV as well.

The `deploy-proxy-bench` profile binds the production ED25519 public key too, so the renet the bench proxy image builds verifies a production-signed bench licence; the bench proxy was redeployed with it on 2026-10-27 (version 5622d50c).

A TOTP step is accepted once per user (account 8c656b6). Two runs that log in within the same 30 s step collide: the second is refused "Invalid verification code". A run that follows `npm run login:bench`, such as `rdc config remote master-password change`, waits for the next step first.

# PLAN: private/account/.env to Bitwarden -- the store is the only source of truth
Status: draft
Owner: d778be9d
First-Seen: 2026-09-24
Date: 2026-09-24
Parent: agent/plans/PLAN-env-to-bitwarden-v2.md (subsumes its open boxes "Seed the 4 admin credentials" and "Everything in v1's task list from 'Write .ci/lib/bws-env.sh' onward", except v1's `__ROTATED_` clone-protocol boxes v1:20-25, which are orthogonal and stay with v2)
Scope: design. Measured read-only 2026-09-24 against `private/account/.env` (47 assigned names) and live BWS `ci-shared` (78 secrets, one project). No value was printed; comparisons ran in-process and emitted MATCH/MISMATCH/ABSENT/EMPTY only.


## Tasks

- [ ] T1 Bootstrap token file. Add `token_path()` and `read_token()` to `.ci/rediacc_ci/core/bws_env.py`: `BWS_ACCESS_TOKEN` in the environment wins, then `BWS_ACCESS_TOKEN_FILE`, then `${XDG_CONFIG_HOME:-$HOME/.config}/rediacc-console/bws-access-token`. Refuse a file whose mode is wider than 0600 or whose directory is wider than 0700. Update the `NO_TOKEN` refusal text and its differential golden in `.ci/rediacc_ci/tests/test_core_bws_env.py`.
- [ ] T2 Devbox: bind `$HOME/.config/rediacc-console` read-only to `/home/vscode/.config/rediacc-console` in `.ci/lib/devbox.sh` (next to the `~/.config/gh` bind; `devbox_missing_binds` recreates old containers). Change `.devcontainer/devbox-bws.sh` to read the token file first and fall back to `private/account/.env` only until T16. Coordinate with the agent wiring the devbox token now: this is the path it should target.
- [ ] T3 Retarget `scripts/dev/bws-rotate.py` (`ENV_FILE`, :41) to write the token file atomically at mode 0600, and update `.ci/config/bws-rotation-notice.txt` section 5 and 6 to name the file. Update `test_gate_bws_rotate.py` seams.
- [ ] T4 Operator: create the token file on the host from the current `.env` line (one `umask 077` command, no echo). Verify it with `python3 -m rediacc_ci.core.bws_env fingerprint` on host and in devbox: the two fingerprints must be equal.
- [ ] T5 Add a `compare` verb to `bws_env.py`: `compare FILE [SPEC...]` prints `NAME MATCH|MISMATCH|ABSENT|LOCAL-EMPTY` per name, never a value or a length. It unquotes the local value the way `rediacc_ci.core.env` parses it. This is the read-back instrument every deletion below depends on. Add gate cases covering a planted mismatch, a planted absence and a quoted value.
- [ ] T6 Add an `exec` verb to `bws_env.py`: `exec --profile P [--profile Q] -- CMD ARGS`. It loads the profile's specs in-process, merges them into the child's environment (the shell wins, as with `env_file_load`), sets `REDIACC_BWS_PROFILES`, and `os.execvpe`s. It never writes to stdout or disk. A profile already listed in `REDIACC_BWS_PROFILES` is skipped, so nested `./run.sh` calls inherit instead of re-fetching. Absent, empty or offline means exit 1 with the existing refusals, and there is no fallback to a file. Gate cases: no value on stdout or stderr, child env has exactly the requested names, alias binds LOCAL only, an unknown profile is refused.
- [ ] T7 Declare profiles in `.ci/config/secret-supply.json` under a new `consumers` key (one list of specs per consumer: `account-dev`, `account-e2e`, `deploy-bench`, `rotation`, `backup-plane`, `publish-media`). `check_secret_supply.py` asserts every spec resolves in `bws-secret-map.json` (or in the ops-admin map from T9), and that no profile uses a wildcard (`start-local-plane.sh` relies on `ACCOUNT_BACKUP_S3_*` being absent).
- [ ] T8 Committed `private/account/dev.defaults.env` holding the (c) constants: `PORT`, `DATABASE_PATH`, `WEBAUTHN_RP_ID`, `WEBAUTHN_RP_NAME`, `CI_MODE`, `STRIPE_E2E_WEBHOOK_SECRET` (a committed fixture already, `.ci/lib/account.sh` writer). `WEBAUTHN_ORIGIN` and `REDIACC_ACCOUNT_SERVER` are derived from `GATEWAY_PORT` in `account_dev` rather than stored. `check_secret_supply.py` already refuses a `secret`-shard name routed to `dev.defaults.env`; keep that.
- [ ] T9 Operator, web vault only: create project `ops-admin` and a machine account `mc-ops-admin` with read on `ops-admin` only. Do NOT create it with `bws project create` using the current token: that token is also CI's (bws-rotate.py installs one value in `.env` and every repo secret), and a machine account that creates a project is granted access to it. Put the new token in `~/.config/rediacc-console/bws-admin-access-token` (0600). Record the project id in a new `.ci/config/bws-admin-map.json` (names and ids only) so `check_bws_map.py` stays single-project.
- [ ] T10 Operator: seed `AWS_IAM_ADMIN_ACCESS_KEY_ID`, `AWS_IAM_ADMIN_SECRET_ACCESS_KEY`, `CF_GLOBAL_API_KEY`, `CF_EMAIL` into `ops-admin`. Confirm with `bws_env compare` (admin token) that all 4 report MATCH.
- [ ] T11 Operator: seed the local dev keypair as `ACCOUNT_ED25519_PRIVATE_KEY_DEV`, `ACCOUNT_ED25519_PUBLIC_KEY_DEV`, `ACCOUNT_X25519_PRIVATE_KEY_DEV`, `ACCOUNT_X25519_PUBLIC_KEY_DEV`, `ACCOUNT_SERVER_API_KEY_DEV`, `ACCOUNT_JWT_SECRET_DEV` into `ci-shared` (per the operator's choice in Q1). The `_DEV` suffix follows the store's `PREFIX_<SUFFIX>` convention. `compare` with aliases `X_DEV > X` must report MATCH for all 6. Refresh `bws-secret-map.json`.
- [ ] T12 Resolve OBS before any OBS cutover: local `OBS_OTLP_CREDENTIALS` is JSON `{user,pass}` (the rotation format, `rotate.ts:1037`). All four store entries are base64 `user:pass`, match no local value, and the server `JSON.parse`s the value (`private/account/src/routes/telemetry.ts:41`). Probe both credentials against the collector with status codes only, then have the operator run `rotation rotate otlp-eu` so the Worker, the store and dev all receive one JSON value. Open a separate worklist item for the production shape defect (`cd-deploy-account.yml:197-199` pushes the store value to Workers).
- [ ] T13 `.env.bench` into the store: seed `AWS_SES_ACCESS_KEY_ID_BENCH`, `AWS_SES_SECRET_ACCESS_KEY_BENCH`, `OBS_OTLP_CREDENTIALS_BENCH`, `CLOUDFLARE_TURNSTILE_SECRET_KEY_BENCH` (plus `AWS_SES_FROM`/`AWS_SES_REGION` only if `compare` shows they differ from the unsuffixed store entries). Add `bitwarden-sm:` consumers and `bitwarden_secret_names` to slugs `ses-bench`, `otlp-bench`, `turnstile-bench` in `private/account/scripts/rotation/lib/config.ts` and `rotation-manifest.json`.
- [ ] T14 Switch readers one at a time, each proven by running the real command (the switch commit reverts cleanly):
  - `.ci/lib/account.sh` `account_dev` (:473) and `account_test_e2e` (:832), via re-exec under `bws_env exec --profile account-dev`
  - `scripts/ops/deploy-bench.sh` (:149-153), via `--profile deploy-bench`
  - `programs/backup-storage/start-local-plane.sh:72`
  - `account_rotation` (`.ci/lib/account.sh:1018`), via `--profile rotation` with the admin token (a second exec over `BWS_ACCESS_TOKEN_FILE`)
  - the build public-key readers (`private/renet/build.sh:411-416`, `.ci/lib/local-common.sh:791-792`, `.ci/rediacc_ci/ops/build_server.py:42,83`) and `rdc.sh:113`
  - `scripts/gates/check-env-credential-drift.ts`, `scripts/drills/{lib,license}.sh`, `scripts/ops/r2-oneshot-scrub.sh`
  - the guard text in `.claude/rediacc_hooks/guards/block_host_toolchain_run.py:388-421`
  - `.ci/rediacc_ci/setup/phases.py:83,187-199` and `machine.py:378-385`
  - Separately, file a `private/growth` item for `publish-solutions.sh:51`
- [ ] T15 Public-key cache for offline builds: extend `cache-to` to accept `X_DEV > X` for the three `CACHEABLE` local names only (the allowlist stays on the LOCAL name, the store name comes from a hardcoded pair table). `./run.sh setup` writes `private/account/.cache/public-keys.env`, and the four build readers read that file. Without the alias, the cache would bake the PRODUCTION public key into dev renet and break every dev-signed licence.
- [ ] T16 Retarget writers:
  - `account_generate_fresh_env`, `account_ensure_env_keys` and `account_reset` (bash `.ci/lib/account.sh:222-330,890+` and `.ci/rediacc_ci/core/account.py:463-557`): reset generates a keypair and pushes the six `_DEV` names through `bws secret edit`, with a `compare` read-back, and warns that other machines' dev databases hold licences signed by the old key
  - `dev-gateway.ts:150-170` `updateEnvServerUrl`: delete it
  - the rotation `local:` consumers: remove every `local:.env`/`local:.env.bench` ref from `config.ts` and `rotation-manifest.json`, then delete `consumers/local-env-file.ts` and the four branches in `rotate.ts` (:659, :870, :1055, :1881)
  - `scripts/ops/secret-rename.py` `EXTRA`
- [ ] T17 Delete keys from `.env` in batches, each only after (i) its consumers are switched (T14) and (ii) `compare` reports MATCH for it. Before the first deletion, write `private/account/.env.pre-bws.bak` (0600). Order: the 24 (a) names first, then the 3 (e) names, then the (c) names once T8 lands, then the 11 (b) names after T10-T12. Remove `.env.bench` after T13.
- [ ] T18 Terminal state: remove `private/account/.env` and `.env.bench` entirely (the token now lives in the T1 file), remove `devbox-bws.sh`'s `.env` fallback, and shrink `secret-supply.json` `dotenv` to an empty `names` with `bootstrap_names: ["BWS_ACCESS_TOKEN"]` pointing at the token file. The operator deletes `.env.pre-bws.bak` after 14 days.
- [ ] T19 Gate `check:ci-account-env-retired` (three-point wiring as `check:ci-actions-vars`). It passes only when no code reads the account `.env` files, rotation has no `local:` consumer, and `secret-supply.json` names no dotenv key. Its checks are listed under Part 5.
- [ ] T20 Local blocking check in `./run.sh setup` (NOT beside the warn-only drift check at `machine.py:382-388`): the token file exists with mode 0600, and `private/account/.env`/`.env.bench` are absent, or contain nothing but `BWS_ACCESS_TOKEN` during the T17 window.

## Part 1. Classification of the 47 names

Method: key names from `grep -oE '^[A-Z0-9_]+='`, store keys from `bws secret list` (78 keys, project `2b5e33f9-...`), and in-process equality. The name set equals `.ci/config/secret-supply.json` `dotenv.names` exactly (47/47).

(a) In BWS with an identical value, deletable once the consumer is switched: 24. Exact MATCH (22): `ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN`, `AWS_SES_FROM`, `AWS_SES_REGION`, `CLOUDFLARE_BREAKPOINT_TUNNEL_TOKEN`, `CLOUDFLARE_R2_ACCESS_KEY_ID`, `CLOUDFLARE_R2_SECRET_ACCESS_KEY`, `CLOUDFLARE_R2_ENDPOINT`, `CLOUDFLARE_R2_MEDIA_ACCESS_KEY_ID`, `CLOUDFLARE_R2_MEDIA_SECRET_ACCESS_KEY`, `CLOUDFLARE_R2_MEDIA_ENDPOINT`, `CLOUDFLARE_TURNSTILE_SECRET_KEY`, `OTEL_ENDPOINT`, `ROOT_EMAIL`, and the nine `SELLER_*`. Alias MATCH (2): `AWS_SES_ACCESS_KEY_ID` and `AWS_SES_SECRET_ACCESS_KEY` equal `_EU`. `secret-supply.json` routes these two to `dev-shared`; this plan re-routes them to a `ci-shared` alias (Q4).

(b) Must be seeded or reconciled before deletion: 11. Absent from the store (4): `AWS_IAM_ADMIN_ACCESS_KEY_ID`, `AWS_IAM_ADMIN_SECRET_ACCESS_KEY`, `CF_GLOBAL_API_KEY`, `CF_EMAIL`, destined for `ops-admin`. MISMATCH (7): the six `ACCOUNT_*` names hold a locally generated DEV keypair (identical to `.env.pre-rename.bak`, different from the store's production set; the API key and JWT even differ in length). They are seeded as `_DEV` names, never replaced by the production values. `OBS_OTLP_CREDENTIALS` differs from every store entry in value and in shape (see T12).

(c) Local, non-secret constants or derived values: 8. `PORT`, `DATABASE_PATH`, `WEBAUTHN_RP_ID`, `WEBAUTHN_RP_NAME`, `CI_MODE`, and `STRIPE_E2E_WEBHOOK_SECRET` (a committed fixture) go to a committed `dev.defaults.env`. `WEBAUTHN_ORIGIN` and `REDIACC_ACCOUNT_SERVER` are derived from `GATEWAY_PORT` at runtime. None enters BWS: a store is for values that are the same on every machine and secret or shared, and these are neither.

(d) Bootstrap: 1. `BWS_ACCESS_TOKEN`.

(e) Dead: 3. `UPSTREAM_URL`, `UPSTREAM_PUBLIC_KEY` and `UPSTREAM_API_KEY` are EMPTY in `.env`. Their readers (`src/entry/on-premise.ts`) treat empty as unset, so deleting them changes nothing, and v2's Q1 no longer matters for this file.

## Part 2. Where the bootstrap token lives

A token-only file `${XDG_CONFIG_HOME:-~/.config}/rediacc-console/bws-access-token` (dir 0700, file 0600), plus `bws-admin-access-token` beside it for T9. Why not `~/.config/rediacc`, which is already bound into the devbox: that directory is the rdc CLI's own state (api-token files, audit log), bound read-write, and a product CLI or its E2E suite managing that directory must not be able to delete the console's root credential. Why not the host keyring: there is no `secret-tool` on this WSL host and no D-Bus session in the devbox, so it cannot work the same in both. The directory is bound read-only into the devbox, so the devbox can read the token but never rewrite it. The only writer is `bws-rotate.py` on the host. Resolution order (env, then `BWS_ACCESS_TOKEN_FILE`, then the default path) lives in `bws_env.py` only. `devbox-bws.sh` stays POSIX sh and reads the same default path, because profile.d cannot import Python.

## Part 3. Runtime hydration

`bws_env.py` refuses to be an eval-able emitter (its docstring, route 1). So hydration is the process-level form of route 2: `bws_env exec --profile P -- CMD`. It makes one `bws secret list` call in-process, binds only the profile's explicit specs (same `NAME > LOCAL` grammar as `parse_spec`), and replaces itself with CMD. Values live only in the process environment, never on disk or stdout, which is what `env_file_load` exposes today. Bash entry points re-exec themselves once under it, guarded by `REDIACC_BWS_PROFILES`. Nested calls inherit, so caching means in-memory by inheritance only. Offline or expired means exit 1 with the existing refusal and rotation notice, and there is no stale fallback (v1 Part 3). The only disk artefact is the three-name PUBLIC key cache (T15), which keeps builds offline.

## Part 4. Rotation

Every slug that now writes `local:.env` also has a `bitwarden-sm:` consumer (`cf-r2`, `otlp-eu`, `ses-eu`). The three bench slugs gain one in T13. Then every `local:` ref is deleted, and so is `local-env-file.ts`. Dev picks up a rotated value on its next `exec`, because the store is the only copy. Rotation's own credentials (admin set) come through the `rotation` profile over the admin token.

## Part 5. The gate

`check:ci-account-env-retired`, modelled on `check_actions_vars.py`:
- No tracked file in console, `private/account` or `private/renet` names `private/account/.env`, `account/.env`, `.env.bench` or a `local:.env*` ref, outside an allowlist of docs, plans, goldens and the gate itself. Each allowlist entry is re-derived.
- `secret-supply.json` `dotenv.names` is empty and `bootstrap_names == ["BWS_ACCESS_TOKEN"]`.
- `bws_env.token_path()` does not resolve under the repo.
- Selftest plants: a `sed` of `.env` in a script, a `local:.env` manifest ref, a re-added dotenv name, and a token path moved under `private/`. Each must turn the gate red.
- Before T18 it runs as a ratchet: the count of dotenv names and file readers may only fall, against a baseline.

## Part 6. Migration order and rollback

The rule is: consumer switched, then `compare` MATCH, then delete. Order: T1-T4 token file (nothing loses a value, and `.env` keeps its token line as a fallback), then T5-T8 instruments, then T9-T13 seeding (additive to the store only), then T14-T16 switches (each one commit, each reverted cleanly by `git revert` while `.env` still holds the value), then T17 deletions, then T18-T20 terminal state. Rollback after T17 is copying `.env.pre-bws.bak` back and reverting the switch commit. The operator's personal vault keeps a copy of the (b) values before T18.

## Remaining (operator)

- `[?]` Q1 Dev keypair home. DEFAULT: `_DEV` names in `ci-shared`, shared across host, devbox and all dev machines. A separate `dev-shared` project buys nothing while the local and CI tokens are one credential. Rejected alternative: using the production keys in dev.
- `[?]` Q2 Admin tier. DEFAULT: `ops-admin` plus `mc-ops-admin`, created in the web vault (T9). Also decide whether the admin token file is bound into the devbox (default yes, read-only: the same exposure `.env` has via the repo bind today), and v2 Q2's `CLOUDFLARE_API_TOKEN` replacing `CF_GLOBAL_API_KEY` for `publish-solutions.sh`.
- `[?]` Q3 OBS: which credential is live, and confirm the production Worker value shape (T12).
- `[?]` Q4 Dev SES: keep aliasing the production EU key (the status quo, and the default) or mint a dev IAM user.
- Operator-only: T4, T9, T10, T11, T13 seeding, the T12 rotation, and deleting the backup file.

## Operator rulings, 2026-09-24

- Q1: `_DEV` names in `ci-shared` (the default).
- Q2: the four admin credentials go into `ci-shared`, NOT a separate `ops-admin` project. This supersedes the older `admin-bootstrap` rationale at `.ci/config/secret-supply.json:236`. Seeded the same day with read-back MATCH for all four; `.ci/config/secret-supply.json` now routes them to `ci-shared` and `.ci/config/bws-unrequested.json` records why no workflow requests them. T9 and T10 are done in that form.
- Q3: investigate directly on the observability machine through `./rdc.sh` with the operator's migrated config (worklist item added the same day).
- Q4: keep aliasing the EU SES key (the default).

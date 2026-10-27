# PLAN: layer 3 of the config store is encrypted under a key public in the source

Status: approved -- operator answers ASKED:2026-10-27T11:05Z ("None, refuse at boot"; "Mirror first, then the fix"); promoted in the commit that adds this file
Depends-On: no-dep -- the eu stable-to-edge store mirror (worklist #046d4339) runs first by ruling, but it is an ops step, not a plan
Priority: P1 -- security finding #caef1cc3: anyone with D1 read access recovers every org passphrase
Concurrency: parallel -- boxes K1, K2, K4 and K5 own disjoint files; K3 and K6 follow
Owns: private/account/src/services/config-server-key.ts, private/account/src/services/legacy-server-key.ts, private/account/src/services/config.service.ts, private/account/src/types/env.ts, private/account/src/app.ts, private/account/src/entry/node.ts, private/account/src/errors.ts, private/account/scripts/rewrap-config-server-key.ts, private/account/tests/unit/config-server-key.test.ts, private/account/tests/integration/config-server-key-migration.test.ts, .ci/rediacc_ci/deploy/set_account_worker_secrets.py, .ci/rediacc_ci/ops/deploy_bench.py, .ci/config/secret-supply.json (the account-secrets and deploy-bench profiles), .ci/config/bws-secret-map.json, .ci/config/python-env-registry.json, .github/workflows/cd-deploy-account.yml, .ci/rediacc_ci/tests/test_deploy_set_account_worker_secrets.py, .ci/rediacc_ci/tests/test_deploy_account_secrets_local.py, .ci/rediacc_ci/ops/rewrap_config_server_key.py, .ci/rediacc_ci/tests/test_ops_rewrap_config_server_key.py, .ci/rediacc_ci/ops/mirror_config_store.py, .ci/rediacc_ci/tests/test_ops_mirror_config_store.py, .ci/scripts/quality/check_config_server_key_constant.py, docs/DESIGN-CONFIG-STORAGE.md
Owner: d778be9d
First-Seen: 2026-10-27
Worklist: #caef1cc3

**Finding.** `private/account/src/services/config.service.ts:2929-2945` (`getServerEncryptionKey`) reads `process.env.CONFIG_SERVER_KEY ?? 'rediacc-config-server-dev-key'` and derives the AES-GCM key that encrypts `config_stores.server_recoverable_org_passphrase`.
- Nothing sets the variable: it is not in `env.ts`, not in `KEYS` of `set_account_worker_secrets.py:184-214`, and not in any account-secrets profile or wrangler toml.
- So all seven account Workers (eu, us and asia, stable and edge, plus bench) encrypt layer 3 under the constant. The ciphertext carries no AAD and no key tag (`packages/shared/src/config-crypto/aes.ts:99-109`).
- Severity is defense in depth, not an incident. The CEK layer still needs a slot secret, so a D1 dump does not expose config plaintext. It does expose every org passphrase, which contradicts `docs/DESIGN-CONFIG-STORAGE.md:989`.

Design memo: Plan agent aecb122b, 2026-10-27, summarized in the boxes below.

## Tasks

- [ ] K1 [writer] Key module and fail-closed (landing A).
  - New `private/account/src/services/config-server-key.ts`:
    - `resolveConfigServerKey(env)` returns `ACCOUNT_CONFIG_SERVER_KEY`. The dev constant is returned only under TEST_MODE, resolved after `pinDeployedEnv` (`entry/cloudflare.ts:47-49`). Otherwise it throws `ConfigServerKeyMissingError`.
    - `sealServerSecret`/`openServerSecret`: HKDF with today's salt and info, a non-extractable key, AAD `csk1|<storeId>`, and output `csk1.<kid>.<base64(iv||ct)>`, where kid is 8 hex characters of HMAC-SHA256(key, "kid").
  - `legacy-server-key.ts` is the only file allowed to hold the constant. It opens an untagged row with it, and the row is rewritten on read with a compare-and-swap UPDATE.
  - Add `ACCOUNT_CONFIG_SERVER_KEY` to `envFields`.
  - `app.ts:457-460` passes the key to ConfigService. On a deployed Worker without the key, only the config routes fail closed, with a mapped 5xx.
  - `entry/node.ts` refuses to boot when `CONFIG_R2_*` is set without the key (operator: no on-premise config storage exists).
  - Delete `getServerEncryptionKey`, `serverEncrypt` and `serverDecrypt`; the five call sites use seal and open with storeId.
  - Accept: `cd private/account && npx vitest run tests/unit/config-server-key.test.ts tests/integration/config-server-key-migration.test.ts tests/integration/config-cek-rotation.test.ts tests/integration/console-session.test.ts && npm run typecheck` rc=0.
- [ ] K2 [writer] Provisioning.
  - The Worker secret is named `ACCOUNT_CONFIG_SERVER_KEY`. It is never `CONFIG_SERVER_KEY`, because the running code would read that name at once and fail every layer-3 read.
  - Bitwarden names: `ACCOUNT_CONFIG_SERVER_KEY_<EU|US|ASIA>_<STABLE|EDGE>` and `ACCOUNT_CONFIG_SERVER_KEY_BENCH`. Each channel and region gets its own key; none is shared.
  - `set_account_worker_secrets` gains a computed `KEYS` row using the `backup_pair` channel logic, refuses a value from the other channel, and lists the key in `REQUIRED_NONEMPTY`.
  - Each account-secrets profile binds its one name. `deploy-bench` binds the bench name, and `deploy_bench.py` pushes it. `cd-deploy-account.yml` fetches the matrix's name.
  - Accept: the two deploy test files rc=0; `check_bws_map.py` and `check_secret_supply.py` rc=0; `account_secrets_local --region eu --target edge --dry-run` lists `ACCOUNT_CONFIG_SERVER_KEY`.
- [ ] K3 [lead] Mint the seven secrets in Bitwarden, in process (`secrets.token_bytes(32)`), through `bws_env store-from-env`. No value appears on argv or in a log.
  - Accept: the map gate resolves all seven names, and after deploy, `prune_worker_secrets --json` shows the key under `live` and no `CONFIG_SERVER_KEY`.
- [ ] K4 [writer] Rewrap tool `.ci/rediacc_ci/ops/rewrap_config_server_key.py --region --target [--apply] [--verify]`.
  - It hydrates the Worker's own key, selects the untagged rows through `wrangler d1 execute`, and seals them through the K1 helper in `private/account/scripts/rewrap-config-server-key.ts`, so the output is byte-compatible by construction.
  - It takes a D1 bookmark first, then writes compare-and-swap UPDATEs from a temp file. `--verify` exits 0 only when no untagged row is left.
  - Accept: its pytest rc=0. Then, per Worker after deploy, `--apply` followed by `--verify` rc=0, seven times, bench included.
- [ ] K5 [writer] Mirror alignment. The mirror runs before this plan (operator, 11:05Z). After K1, `mirror_config_store.py` refuses an untagged row or a kid that does not match the stable key, because its old CONFIG_SERVER_KEY pre-check goes blind once the key is in `KEYS`.
  - Accept: its pytest rc=0, with cases for an untagged row and a mismatched kid.
- [ ] K6 [writer] Landing B, gated on K4's `--verify` rc=0 on all seven databases.
  - Delete `legacy-server-key.ts` and the legacy branch.
  - Add `check_config_server_key_constant.py`, which confines the dev constant to `config-server-key.ts` under TEST_MODE.
  - Correct `DESIGN-CONFIG-STORAGE.md:989` and the layer-3 section.
  - Accept: the gate rc=0, the account vitest rc=0, and `grep -rn rediacc-config-server-dev-key private/account/src` returns only `config-server-key.ts`.

## Order

1. The mirror (#046d4339) applies first, while both sides still use the constant.
2. K1, K2, K4 and K5 run in parallel, then K3.
3. Deploy each Worker, then K4 on that Worker: edge through CD or `release:local`; stable through CI/CD with an ASK (stable is CI/CD-only by ruling); bench by hand.
4. K6 after all seven verify.

## Risks

- **Rollback after a rewrap breaks layer 3**, because old code cannot read `csk1.` rows. The rollback is the D1 bookmark K4 records, restored together with the code rollback.
- **The secret must reach the Worker before the new code serves**, or the config routes answer 5xx. Check the order in `cd-deploy-account.yml`.
- **The bash twin of `set_account_worker_secrets` `KEYS`** (`tests/twin_names.py`) changes with it, or that differential is retired.

## Results

(K3, K4 and K6 record here.)

# PLAN: production key only: one account keypair (the unsuffixed production entries) for every build, gateway, bench and drill; the six ACCOUNT_*_DEV entries parked as __<NAME>; renet builds fail closed without a key

Status: approved -- operator 2026-10-29: "we can make the production key primary and get rid of the development key. we already have bws/bitwarden and we almost always need it. So, keeping separate development keys make things difficult to manage. This is also valid for private/account not just for private/renet. ... [the development keys may be renamed on the Bitwarden side with a __ (double underscore) prefix]" In ## Generated until the operator promotes it.
Priority: P1 -- `./rdc.sh` baked the cached DEV key into renet (private/renet/build.sh:414-436), `machine setup` put that binary on hostinger, and a backup snapshot failed with "no installed repository license" (private/renet/cmd/renet/backup_snapshot.go:437-440), because hostinger's licences are signed by the production key and renet looks a licence up only under the fingerprint of the key it baked (private/renet/pkg/license/preferred.go:21-28, :38-43).
Depends-On: no-dep -- the code boxes need nothing outside this plan. PLAN-per-flavor-renet-binary-paths.md (owns build.sh and local_common.py) has 0 open boxes. PLAN-local-release.md (owns renet_key_gate.py and release/local.py) has 2 open boxes, and K4 waits for its writer lease on those two files. PLAN-config-server-key.md (owns the deploy-bench profile and deploy_bench.py) has 1 open box, and K2 waits for its lease on those lines.
Concurrency: parallel -- K1, K2, K3, K4 and K5 have disjoint Owns and run at the same time. L1 (the bws park) runs after K1-K3 land on the branch and right before the merge. K6 (map refresh plus the no-DEV gate) follows L1 in the same PR. L2-L4 follow the merge. One line of .ci/rediacc_ci/tests/test_deploy_deploy_proxy.py (owned by PLAN-executor-durable-object-policy, exclusive) changes in K6, and only under that plan's lease.
Owns: agent/plans/PLAN-production-key-only.md, .ci/rediacc_ci/core/bws_env.py, scripts/ops/bws-map-refresh.py, .ci/scripts/quality/check_bws_map.py, .ci/rediacc_ci/tests/test_core_bws_env.py, .ci/rediacc_ci/tests/gates/test_gate_bws_env.py, .ci/rediacc_ci/tests/gates/test_gate_bws_map.py, .ci/config/secret-supply.json, .ci/rediacc_ci/ops/prune_worker_secrets.py, .ci/rediacc_ci/ops/deploy_bench.py, .ci/rediacc_ci/drills/backup_onprem.py, .ci/rediacc_ci/quality/region_consistency_offline.py, .ci/rediacc_ci/quality/region_consistency_controls.py, .ci/rediacc_ci/tests/test_ops_deploy_bench.py, .ci/rediacc_ci/tests/test_ops_prune_worker_secrets.py, .ci/rediacc_ci/core/account_lifecycle.py, .ci/rediacc_ci/core/account_lifecycle_shadow_driver.py, .ci/rediacc_ci/tests/goldens/twins/lib.account.jsonl, .ci/rediacc_ci/setup/machine.py, .ci/rediacc_ci/core/local_common.py, .ci/rediacc_ci/core/local_common_actions_shadow_driver.py, .ci/rediacc_ci/ops/build_server.py, .ci/rediacc_ci/tests/test_setup_account_bws.py, .ci/rediacc_ci/tests/test_core_local_common_renet_key.py, private/renet/build.sh, private/renet (gitlink bump only), .github/workflows/ci-vm-bake.yml, .github/workflows/ct-backup-perf.yml, .github/workflows/ct-e2e-probe.yml, .github/workflows/ci-ops-test.yml, .github/workflows/ct-tests.yml, .ci/rediacc_ci/release/renet_key_gate.py, .ci/rediacc_ci/release/local.py, .ci/rediacc_ci/tests/test_release_renet_key_gate.py, .ci/rediacc_ci/tests/test_release_local.py, private/account/CLAUDE.md, private/account (gitlink bump only), docs/agent-reference/local-env.md, .ci/config/bws-secret-map.json, .ci/config/bws-unrequested.json, .ci/config/env-manifest.json, scripts/data/doc-registry.md, .ci/scripts/quality/check_no_dev_keys.py, .ci/rediacc_ci/quality/no_dev_keys.py, .ci/rediacc_ci/tests/gates/test_gate_no_dev_keys.py, package.json, .ci/config/gate-costs.json, .ci/config/lane-durations.json, `check:ci-bws-map`
Live-Proof: bench, hostinger -- bench is the account/account-worker surface's live target, and it is redeployed with the production six in L2. hostinger is the renet surface's target: L3 proves a production-keyed renet takes a snapshot there.
First-Seen: 2026-10-29

## Why

There are two account keypairs today. Production is one keypair, the same for all three regions and both channels. The DEV keypair is used by the local gateway, the backup plane and, for X25519/JWT/API key, bench. renet bakes whichever public key happens to be in the environment or in the cache. When the two keypairs disagree, the result is exactly this incident: the binary builds and uploads fine, and then cannot find any licence on the machine. The operator's ruling removes the second keypair rather than adding more guards around the choice between them.

## Inventory: every place a DEV keypair exists or is chosen (verified 2026-10-29)

### The six bws entries (store)
- `ACCOUNT_ED25519_PRIVATE_KEY_DEV`, `ACCOUNT_ED25519_PUBLIC_KEY_DEV`, `ACCOUNT_JWT_SECRET_DEV`, `ACCOUNT_SERVER_API_KEY_DEV`, `ACCOUNT_X25519_PRIVATE_KEY_DEV`, `ACCOUNT_X25519_PUBLIC_KEY_DEV`. Mapped at .ci/config/bws-secret-map.json:61-93, listed at .ci/config/bws-unrequested.json:51-74 ("no workflow requests it, because CI's drills leg mints throwaway keys instead"), classified at .ci/config/env-manifest.json:107-117, and generated into scripts/data/doc-registry.md:1309-1320 (scripts/gen/gen-docs.ts).

### Profiles that bind them (.ci/config/secret-supply.json consumers)
- `account-dev`: all six (:276-284). This is `./run.sh account dev`.
- `backup-plane`: all six (:312-320). This is rediacc_ci.drills.backup_local_plane.
- `deploy-bench`: X25519 pair, server API key and JWT secret as DEV (:329-332). ED25519 is already production (:327-328), by operator ruling 2026-10-27, documented at .ci/rediacc_ci/ops/deploy_bench.py:25.
- No CI test profile binds a DEV name. `account-e2e` binds only ROOT_EMAIL (:305-311). CI legs mint throwaway keys: .ci/rediacc_ci/testrun/start_account.py:13, :35-36, :102; .ci/rediacc_ci/infra/ci_env.py:105, :350-351; .ci/rediacc_ci/testrun/start_backup_plane.py:10, :132; .ci/rediacc_ci/drills/backup_onprem.py:254.

### `./run.sh account reset`
- Mints a fresh keypair and session secrets and pushes them through `store-from-env` to `RESET_STORE_SPECS`, the six `X_DEV > X` specs (.ci/rediacc_ci/core/account_lifecycle.py:78-85, :1115-1139).
- Then caches `RESET_CACHE_SPECS` (:86-89, :1141-1145).
- DANGER after the change: re-pointed to the unsuffixed names, this verb would overwrite the production keys of every region. K3 deletes the key mint. It does not re-point it.
- Twin evidence: .ci/rediacc_ci/core/account_lifecycle_shadow_driver.py:621, :910; .ci/rediacc_ci/tests/goldens/twins/lib.account.jsonl:8.

### The public-key cache and `./run.sh setup`
- `PUBLIC_KEY_SPECS` = the two `_DEV > X` public specs (.ci/rediacc_ci/setup/machine.py:416-421). `cache-to` writes them on setup and only warns on failure (:465-490).
- `cache-to` accepts the `_DEV` aliases through `CACHE_STORE_NAMES` (.ci/rediacc_ci/core/bws_env.py:218-227). The comment there explains why: "a dev renet must bake the DEV public key".
- Cache readers:
  - private/renet/build.sh:414-436
  - .ci/rediacc_ci/core/local_common.py:1369-1379 (the `./rdc.sh` stamp path)
  - .ci/rediacc_ci/ops/build_server.py:10, :42, :87
  - .ci/rediacc_ci/release/renet_key_gate.py:8, :40-41, :130-165, :276-315 (it reads the cache as "the DEV key" to refuse it)
  - .ci/rediacc_ci/release/local.py:1181 (`dev_cache=`)

### private/renet/build.sh fallback
- `_account_key_ldflags` (:409-446) takes env first, then the cache. It warns "baking the cached DEV key" (:429-434) and returns 0 with no key at all (:437-445).
- Every flavor goes through it: stage_linux :521, build :557, dev :840.
- A keyless binary is not harmless even under `-tags nolicense`. preferred.go is untagged (:12-15), and `LoadPreferredRepoLicense` returns errNoPublicKey when the key is empty (:21-23, :38-42). backup_snapshot.go:437-440 then rejects. The nolicense stubs cover only the validate calls (pkg/license/runtime_nolicense.go:1-27).

### private/account
- The dev gateway gets its keys only through the `account-dev` profile (private/account/CLAUDE.md:62).
- private/account/CLAUDE.md:66 documents the DEV reset. :75 says bench runs "the DEV keypair", which is already stale for ED25519.
- Vitest uses a fixed, committed test keypair: private/account/tests/integration/helpers/test-keys.ts:12-30, fingerprint `fc6a12b178711e65`. It is not in bws and has no relation to either real keypair. Keep it (see Design item 4).
- private/account/scripts/generate-keys.ts:17-18 prints a fresh pair to stdout. This is a manual tool, untouched.
- The rotation tool (private/account/scripts/rotation) has no `_DEV` reference.

### Bench
- `deploy-bench` profile as above.
- prune_worker_secrets `BENCH_LEGACY_BWS` maps API_KEY, JWT_SECRET and the X25519 pair to `_DEV` (.ci/rediacc_ci/ops/prune_worker_secrets.py:17, :73-82, :301-304; test at .ci/rediacc_ci/tests/test_ops_prune_worker_secrets.py:121).
- Pinned by .ci/rediacc_ci/tests/test_ops_deploy_bench.py:491-498.
- The eu-bench config pins the DEV X25519 public key as `account.e2ePublicKey` (deploy_bench.py:25). The CLI uses a pinned key before discovery (packages/cli/src/services/account/account-client.ts:99-119).

### Region-consistency gate
- `_check_bench_profile` checks bench's `_BENCH` families and foreign suffixes (.ci/rediacc_ci/quality/region_consistency_offline.py:502-518).
- The bench payload is compared against `pusher.KEYS` (:476-500).
- Nothing asserts that bench binds the same six store names as the regions. Today it cannot, because bench binds four `_DEV` names.

### CI workflows
- Production-keyed renet builds already take `ACCOUNT_ED25519_PUBLIC_KEY` from bws: .github/workflows/ci-build-renet.yml:69-73, :151, :284-288, :320; ci-build-docker.yml:243, :313, :346, :416; cd-deploy-account.yml:280-285, :522-713.
- Keyless `--nolicense` test builds:
  - ci-vm-bake.yml:127
  - ct-backup-perf.yml:141 (rebuilt with the plane's throwaway key at :210-223)
  - ct-e2e-probe.yml:133, :232
  - ci-ops-test.yml:81, :272
  - ct-tests.yml:315, :491, :729 and the later matrix legs
- No workflow binds a `_DEV` name.

### Docs and gate fixtures
- docs/agent-reference/local-env.md:140-170 (`RDC_RENET_LICENSE=1` with "paste the production key").
- private/account/CLAUDE.md:62, :66, :75.
- .ci/rediacc_ci/drills/backup_onprem.py:16-17 ("signed by the gateway's DEV key").
- Gate fixtures that use a DEV spec as sample data:
  - .ci/scripts/quality/check_bws_map.py:1392
  - .ci/rediacc_ci/tests/gates/test_gate_bws_map.py:76
  - .ci/rediacc_ci/tests/test_core_bws_env.py:399-414
  - .ci/rediacc_ci/tests/test_setup_account_bws.py:25-30
  - .ci/rediacc_ci/tests/test_deploy_deploy_proxy.py:1158 (asserts absence, but carries the literal)
- Historical, exempt from the new gate: agent/plans/_done/**, agent/archive/**, agent/<session>/**, .ci/shadow/*.jsonl, .ci/cache/**.

## Design

### 1. Which key everything uses (the production key)
- There is one production keypair for all regions and channels. Every `account-secrets-<region>-<channel>` profile binds the same unsuffixed store names `ACCOUNT_ED25519_PRIVATE_KEY`, `ACCOUNT_ED25519_PUBLIC_KEY`, `ACCOUNT_X25519_PRIVATE_KEY`, `ACCOUNT_X25519_PUBLIC_KEY`, `ACCOUNT_SERVER_API_KEY` and `ACCOUNT_JWT_SECRET` (secret-supply.json:648-653, :685-690, :720-725, :757-762, :792-797, :831-836).
- The pusher reads them under the same names (.ci/rediacc_ci/deploy/set_account_worker_secrets.py:196-202).
- regions.json has a `secretSuffix` per region (regions.json, `"secretSuffix": "EU" | "US" | "ASIA"`), but it selects only the SES/OTLP/Stripe/config-server-key fan-ins, never the signing keys.
- "The production key" is therefore the bws entry `ACCOUNT_ED25519_PUBLIC_KEY`, fingerprint `fb37f1ae16f8b7c0` (deploy_bench.py:25, via renet_key_gate.key_fingerprint).
- After this plan, every renet build, the dev gateway, the backup plane and bench use these six entries. The only exceptions are CI legs and unit tests that mint their own throwaway keys (item 4).
- **renet build.sh** reads `ACCOUNT_ED25519_PUBLIC_KEY` from the environment only. It never reads the cache file. An empty key is refused with exit 1 and a message naming the variable and `./run.sh setup`. The one exception is `RENET_KEYLESS=1`, which is honoured only when `GITHUB_ACTIONS=true` (Decision D2). This exception is for the CI test builds listed in the inventory.
- **`./rdc.sh` / `./run.sh`** reach build.sh through `local_common.ensure_renet_built`, which resolves the key in this order and passes it into the build's environment:
  1. the shell environment;
  2. the public-key cache, now holding the production key;
  3. `bws_env.load(["ACCOUNT_ED25519_PUBLIC_KEY"])`, which also rewrites the cache through `cache-to`;
  4. otherwise a `LocalCommonError` that names `./run.sh setup`.
  The cache stays because the key is public. It keeps offline builds working, which PLAN-env-to-bitwarden-v2 0.4 rules a requirement (bws_env.py:211-213). Its only source becomes the production entry: `CACHE_STORE_NAMES` maps each name to itself only.

### 2. The dev gateway and bench sign with the production key (operator ruling; the risk, stated)
- `account-dev` and `backup-plane` bind the six unsuffixed names. `deploy-bench` binds the same six with no alias.
- **Risk, stated plainly.** Whoever controls a dev box or the bench Worker holds the production signing, envelope and session secrets:
  - **ED25519.** Any licence or delegation cert the dev gateway signs verifies on every released renet and on hostinger. That includes the dev-only `/test/*` seeding routes, which are mounted whenever `NODE_ENV !== 'production'` (private/account/CLAUDE.md "Demo data"), and the delegation-cert route the on-prem drill uses (backup_onprem.py:16-17). A dev gateway bound to 0.0.0.0 (backup_local_plane.py:11) hands out production-valid licences to anyone who can reach that port.
  - **JWT secret.** Access tokens are HS256 over `{sub, email, role, iat, exp}` with no issuer or audience claim (private/account/src/services/session.service.ts:31-41). The production secret on a dev box can therefore mint access tokens that production verifies.
  - **Server API key.** It gates the subscriptions API (private/account/src/middleware/api-key.ts:13-14, routes/subscriptions.ts:16).
  - **X25519.** It is the E2E transport key (private/account/src/app.ts:254). A dev box holding it can open production request envelopes it captures.
  - **Recovery cost.** If a dev box leaks, recovery is a production rotation of all six. Every issued licence on every region must be re-issued, and every pinned `e2ePublicKey` refreshed.
- **Containment.**
  - The values live only in bws. They reach a process only through `bws_env exec --profile ...`, which execs the consumer with them in its environment (bws_env.py:1205-1210).
  - No file holds them. `private/account/.env` is retired, and setup refuses to continue while it exists (.ci/rediacc_ci/setup/machine.py:409-436).
  - `cache-to` can write only the three PUBLIC names (bws_env.py:205-215), and gate B10 proves it (.ci/rediacc_ci/tests/gates/test_gate_bws_env.py:421-455).
  - After K3, nothing local writes any of the six to the store. The reset mint is deleted, so only the rotation tool rotates them.
  - Agent sessions never print values. Only names and fingerprints appear.
  - The dev gateway's 0.0.0.0 bind for the VM plane stays as it is (backup_local_plane needs it). The residual risk is recorded here and not engineered away, per the ruling.

### 3. Fallout and its resolution
- **Dev configs.** `./rdc.sh --dev` re-reads the X25519 public key from the running gateway's server-info and patches dev.json (docs/agent-reference/local-env.md:58), so this heals itself.
- **Local dev database.** Its subscriptions and licences were issued by the DEV signer. The choice is to wipe or re-issue: `./run.sh account reset`, now DB-only, or `rdc --dev subscription refresh -m <vm>` (packages/cli/src/commands/subscription.ts:412-435).
- **ops VMs and the vm:check drill.** The drill talks to the dev gateway with `RDC_DEV=1` (.ci/rediacc_ci/drills/vm_check.py:1111), and that gateway now signs with the production key. The renet that `./rdc.sh` builds bakes the same key, so new licences verify. Old DEV-fingerprint licence files on a VM are ignored, because renet looks up only the baked fingerprint. Re-issue with `subscription refresh -m <vm>`, or tear down and recreate with `ops down/up`.
- **e2e fleet in CI.** Unaffected. Each leg mints its own pair and bakes that public key (start_account.py:13, start_backup_plane.py:10).
- **The license-mint tool.** .ci/scripts/private/license-mint signs with a master key the license_e2e battery mints per run (main.go:1-15; license_e2e.py:2, :12). It uses no DEV key and stays as it is. It cannot stand in for the server anyway, because its payload has no grandGuid (.ci/rediacc_ci/drills/backup_roundtrip.py:17).
- **Bench.**
  - ED25519 has been production since 2026-10-27. Licences minted before that are DEV-signed: re-issue with `--config eu-bench subscription refresh -m <machine>`.
  - X25519, JWT and API key change in L2. Every bench session dies (re-login with rediacc_ci.ops.login_bench), and eu-bench's pinned `e2ePublicKey` must become the production X25519 public key. That key is also the CLI's baked production key, `CURRENT_SERVER_E2E_KEY` (account-client.ts:128-134).
- **hostinger.** Its licences come from the stable EU server and are production-signed. The renet now on it is reported as production-keyed already. L3 verifies that by fingerprint and reruns the snapshot.
- **Release key gate.** renet_key_gate reads the cache as "the DEV key" and refuses an expected key equal to it (:276-290, :300-315). Once the cache holds the production key, that check would refuse every release. K4 replaces it with a constant tuple of retired fingerprints, which holds only the DEV key's 16-hex fingerprint, so a stale DEV-baked binary is still named as such.

### 4. What stays separate on purpose
- A **DEV keypair in bws**, meaning a second long-lived real keypair, is removed: the six entries are parked.
- **Test keys** stay:
  - the throwaway pairs CI legs mint per run (start_account.generate_keys, ci_env, start_backup_plane, backup_onprem, license_e2e);
  - the fixed committed vitest fixture (test-keys.ts:12-30).
  The vitest keys are committed constants, not generated per run as the brief assumed. They are test-only, live in no store, and match no deployed key, so they need no change. The new gate's patterns do not match them because they carry no `_DEV` store name.

### 5. The bws park (rename, not delete)
- Each `X_DEV` becomes `__X_DEV`, same id and same value:
  - `ACCOUNT_ED25519_PRIVATE_KEY_DEV` -> `__ACCOUNT_ED25519_PRIVATE_KEY_DEV`
  - `ACCOUNT_ED25519_PUBLIC_KEY_DEV` -> `__ACCOUNT_ED25519_PUBLIC_KEY_DEV`
  - `ACCOUNT_JWT_SECRET_DEV` -> `__ACCOUNT_JWT_SECRET_DEV`
  - `ACCOUNT_SERVER_API_KEY_DEV` -> `__ACCOUNT_SERVER_API_KEY_DEV`
  - `ACCOUNT_X25519_PRIVATE_KEY_DEV` -> `__ACCOUNT_X25519_PRIVATE_KEY_DEV`
  - `ACCOUNT_X25519_PUBLIC_KEY_DEV` -> `__ACCOUNT_X25519_PUBLIC_KEY_DEV`
- **Write path.** The existing writer private/account/scripts/rotation/bws-write.ts does an `edit` that "overwrites key, value, note and project together" (its header, lines 11-16). A rename is therefore an edit with the new key, the same id, and the value bws_env already holds in memory from `listing()`. K1 adds `bws_env park NAME...`, built on `write_secret` (bws_env.py:1226-1273).
  - The value goes over stdin only, never argv or stdout.
  - The read-back asserts that the same id now carries `__NAME` with an unchanged value (a MATCH verdict, no value printed) and that `NAME` is gone.
- Changed in the same PR:
  - the three profiles;
  - `RESET_*_SPECS`, `PUBLIC_KEY_SPECS`, `CACHE_STORE_NAMES`, `BENCH_LEGACY_BWS`;
  - the map, bws-unrequested.json, env-manifest.json and doc-registry.md;
  - the fixtures listed in the inventory.
- **Parked names are never mapped and never bound.** `PARKED_RE = ^__(?!.*__ROTATED_)` is excluded by bws-map-refresh, the way archive clones are (scripts/ops/bws-map-refresh.py:52-53, :159-162), and refused by check_bws_map and by `bws_env load`.

## Decisions (defaults taken without asking; operator may veto)

- **D1.** All six names move to production, including JWT and API key, because the ruling says "get rid of the development key" and the brief lists six. The risk is stated in Design 2.
- **D2.** CI test builds that bake no key declare it with `RENET_KEYLESS=1` in each named workflow step, honoured only with `GITHUB_ACTIONS=true`, instead of binding the production public key into public-PR test jobs. The no-DEV gate (G1) refuses `RENET_KEYLESS` outside .github/workflows and tests.
- **D3.** The public-key cache stays, sourced from the production entry (Design 1).
- **D4.** A new `bws_env park` verb, not a one-off script, so the read-back and the never-print rule are tested.
- **D5.** The retired DEV fingerprint is pinned in renet_key_gate as a constant. It is computed in K4 from the current cache before K3 rewrites it, and it is a fingerprint, not a key.

## Tasks

- [x] K1 [writer] bws plumbing. Changes:
  - `CACHE_STORE_NAMES` maps each name to itself only (bws_env.py:218-227), and the comment is rewritten.
  - Add `PARKED_RE` and the `park` verb (Design 5).
  - `load`, `exec` and `cache-to` refuse any `__`-prefixed spec.
  - bws-map-refresh drops parked names.
  - check_bws_map gets assertion 16: no mapped or bound name is parked. Its :1392 fixture becomes `AWS_SES_ACCESS_KEY_ID_EU > AWS_SES_ACCESS_KEY_ID`.
    (ticked) 2026-10-29T09:01:19Z by d778be9d: commit:d3b47b367

  Tests:
  - `cache-to` refuses `ACCOUNT_ED25519_PUBLIC_KEY_DEV > ACCOUNT_ED25519_PUBLIC_KEY` and writes nothing. Control: the unaliased name is written 0644.
  - `park` against a fake writer edits with key `__X`, the same id and an unchanged value, never puts the value on argv or stdout, and refuses an already-parked or absent name.
  - Assertion 16 goes red on a planted mapped `__X`. Control: a clean map is green.

  Owns: .ci/rediacc_ci/core/bws_env.py, scripts/ops/bws-map-refresh.py, .ci/scripts/quality/check_bws_map.py, .ci/rediacc_ci/tests/test_core_bws_env.py, .ci/rediacc_ci/tests/gates/test_gate_bws_env.py, .ci/rediacc_ci/tests/gates/test_gate_bws_map.py, .ci/rediacc_ci/tests/test_core_bws_env_park.py (new). Accept: `PYTHONPATH=.ci python3 -m pytest .ci/rediacc_ci/tests/test_core_bws_env.py .ci/rediacc_ci/tests/test_core_bws_env_park.py .ci/rediacc_ci/tests/gates/test_gate_bws_env.py .ci/rediacc_ci/tests/gates/test_gate_bws_map.py` rc 0, and `npm run check:ci-bws-map` rc 0.

- [x] K2 [writer] Profiles, bench and prune. Changes:
  - secret-supply.json: `account-dev` (:279-284) and `backup-plane` (:315-320) bind the six unsuffixed names. `deploy-bench` (:327-332) binds the six unaliased. Each `why` is rewritten (production key, operator 2026-10-29).
  - `BENCH_LEGACY_BWS` maps API_KEY, JWT_SECRET and X25519_* to the unsuffixed names (prune_worker_secrets.py:73-82, docstring :17).
  - deploy_bench.py docstring :25.
  - backup_onprem.py:16-17 wording.
  - region_consistency_offline.py `_check_bench_profile` asserts that bench binds exactly the six signing/session store names every regional profile binds, unaliased.
    (ticked) 2026-10-29T08:07:23Z by d778be9d: commit:bfc0eeee3 profiles bind the production six; 63 pytest, check:ci-region-consistency and check:ci-secret-supply rc 0

  Tests:
  - test_ops_deploy_bench.py:491-498 pins the unaliased six.
  - test_ops_prune_worker_secrets.py:121 expects `ACCOUNT_JWT_SECRET`.
  - The region gate goes red on a planted `ACCOUNT_JWT_SECRET_DEV > ACCOUNT_JWT_SECRET` in deploy-bench. Control: the real profile is green.

  Owns: .ci/config/secret-supply.json (account-dev, backup-plane, deploy-bench only), .ci/rediacc_ci/ops/prune_worker_secrets.py, .ci/rediacc_ci/ops/deploy_bench.py (docstring only), .ci/rediacc_ci/drills/backup_onprem.py (docstring only), .ci/rediacc_ci/quality/region_consistency_offline.py, .ci/rediacc_ci/quality/region_consistency_controls.py, .ci/rediacc_ci/tests/test_ops_deploy_bench.py, .ci/rediacc_ci/tests/test_ops_prune_worker_secrets.py, .ci/rediacc_ci/tests/gates/test_gate_region_consistency.py. Accept: those pytest files rc 0, `npm run check:ci-secret-supply` and `npm run check:ci-region-consistency` rc 0.

- [x] K3 [writer] Reset, setup and the `./rdc.sh` key path. Changes:
  - `reset()` loses the mint, the push and the cache refresh (account_lifecycle.py:78-89, :1115-1145). It only deletes the dev DB files and says the keys are production and untouched.
  - The twin rows are updated (shadow driver :621, :910; goldens/twins/lib.account.jsonl:8, regenerated by its documented path).
  - `PUBLIC_KEY_SPECS` becomes the two unsuffixed public names (machine.py:416-421).
  - `ensure_renet_built` resolves env, then cache, then `bws_env.load`, then refuses (local_common.py:1369-1379; Design 1). The shadow rows are adjusted.
  - build_server.py docstring :10.
    (ticked) 2026-10-29T09:01:22Z by d778be9d: commit:824f3bd7b

  Tests:
  - reset never runs `store-from-env` (a recording runner) and still removes the four DB files.
  - With empty env, no cache and a stubbed empty load, `ensure_renet_built` raises a message naming `./run.sh setup`. With the stub returning a key, the build env carries it and the cache is written. Control: with an env key, no load is called.
  - test_setup_account_bws.py:25-30 uses unsuffixed names.

  Owns: .ci/rediacc_ci/core/account_lifecycle.py, .ci/rediacc_ci/core/account_lifecycle_shadow_driver.py, .ci/rediacc_ci/tests/goldens/twins/lib.account.jsonl, .ci/rediacc_ci/setup/machine.py, .ci/rediacc_ci/core/local_common.py (ensure_renet_built key resolution only), .ci/rediacc_ci/core/local_common_actions_shadow_driver.py, .ci/rediacc_ci/ops/build_server.py (docstring only), .ci/rediacc_ci/tests/test_setup_account_bws.py, .ci/rediacc_ci/tests/test_core_local_common_renet_key.py (new), .ci/rediacc_ci/tests/test_core_account_lifecycle_reset.py (new). Accept: those tests and the account-lifecycle twin test rc 0.

- [x] K4 [writer] renet fails closed (gate G2) and the release gate. Changes:
  - build.sh `_account_key_ldflags` (:409-446) reads env only. Empty means exit 1 unless `RENET_KEYLESS=1` with `GITHUB_ACTIONS=true`. The cache read and the DEV warnings go away.
  - Add `./build.sh key-ldflags`, which prints the flag or fails, as the test seam.
  - Add `RENET_KEYLESS: "1"` to each keyless step: ci-vm-bake.yml:127, ct-backup-perf.yml:141, ct-e2e-probe.yml:133 and :232, ci-ops-test.yml:81 and :272, ct-tests.yml:315, :491, :729 and every later `infra.build_renet --nolicense` that runs before a plane key exists. The writer audits each one. ct-backup-perf.yml:223 keeps the plane key.
  - renet_key_gate drops `DEV_KEY_CACHE`, `--dev-cache` and `dev_fingerprint*` and gains `RETIRED_FINGERPRINTS` (D5).
  - release/local.py:1181 drops `dev_cache`.
    (ticked) 2026-10-29T09:01:24Z by d778be9d: commit:824f3bd7b

  Tests (new test_renet_build_key_required.py driving `bash private/renet/build.sh key-ldflags`):
  - Env unset plus a cache file holding a key gives rc 1 with no output on stdout. This proves no cache fallback.
  - `RENET_KEYLESS=1` without `GITHUB_ACTIONS` gives rc 1.
  - `RENET_KEYLESS=1 GITHUB_ACTIONS=true` gives rc 0 with empty output.
  - Control: an env key gives rc 0 and output containing `keys.ProductionPublicKey=<key>`.
  - renet_key_gate refuses a binary whose baked fingerprint is retired. Control: the expected key passes.
  - test_release_renet_key_gate.py:247 and test_release_local.py:1235 are updated.

  Owns: private/renet/build.sh, private/renet (gitlink bump only), .github/workflows/ci-vm-bake.yml, .github/workflows/ct-backup-perf.yml, .github/workflows/ct-e2e-probe.yml, .github/workflows/ci-ops-test.yml, .github/workflows/ct-tests.yml (the RENET_KEYLESS env lines only), .ci/rediacc_ci/release/renet_key_gate.py, .ci/rediacc_ci/release/local.py (dev_cache only), .ci/rediacc_ci/tests/test_release_renet_key_gate.py, .ci/rediacc_ci/tests/test_release_local.py, .ci/rediacc_ci/tests/test_renet_build_key_required.py (new). Accept: those pytest files rc 0. A CI run of ct-tests on the branch shows the keyless legs green and a local `env -u ACCOUNT_ED25519_PUBLIC_KEY ./private/renet/build.sh dev` exiting 1.

- [x] K5 [writer] Docs.
  - private/account/CLAUDE.md:62, :66, :75: the production six, reset is DB-only, bench binds the production six, plus a paragraph stating the Design 2 risk and containment.
  - docs/agent-reference/local-env.md:140-170: the key comes from bws through `./rdc.sh`. No paste and no `ACCOUNT_ED25519_PUBLIC_KEY=` prefix are needed. A build without it fails.
  - private/renet/CLAUDE.md build table: `dev` needs `ACCOUNT_ED25519_PUBLIC_KEY`, and rdc.sh supplies it.
    (ticked) 2026-10-29T09:01:26Z by d778be9d: commit:efdb3cd51

  Owns: private/account/CLAUDE.md, private/account (gitlink bump only), docs/agent-reference/local-env.md, private/renet/CLAUDE.md. Accept: `npm run check:ci-docs` (or the doc lint lane that covers these files) rc 0.

- [ ] L1 [live] Park the six entries, after K1-K3 are on the branch and right before the merge. The window is short because main's `account dev` still needs `_DEV` until the merge.
  1. `PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env park ACCOUNT_ED25519_PRIVATE_KEY_DEV ACCOUNT_ED25519_PUBLIC_KEY_DEV ACCOUNT_JWT_SECRET_DEV ACCOUNT_SERVER_API_KEY_DEV ACCOUNT_X25519_PRIVATE_KEY_DEV ACCOUNT_X25519_PUBLIC_KEY_DEV`. It must print six MATCH lines with names only.
  2. Record the ids (unchanged, from bws-secret-map.json:61-93) and the verdicts. No value is ever printed.

- [ ] K6 [writer] After L1: map refresh and the no-DEV gate (G1). Changes:
  - Run `scripts/ops/bws-map-refresh.py` so bws-secret-map.json loses the six `_DEV` entries and gains no `__` entries.
  - Remove bws-unrequested.json:51-74 and env-manifest.json:107-117 rows. Regenerate doc-registry.md with `npx tsx scripts/gen/gen-docs.ts --write`.
  - Add `check:ci-no-dev-keys` (.ci/scripts/quality/check_no_dev_keys.py plus .ci/rediacc_ci/quality/no_dev_keys.py). It refuses:
    - (a) any store name ending `_DEV` in the map, bws-unrequested, env-manifest, or the store side of any secret-supply spec;
    - (b) the regex `(?<![A-Z0-9_])ACCOUNT_[A-Z0-9_]+_DEV(?![A-Z0-9_])` in tracked files under .ci/ (except .ci/shadow and .ci/cache), scripts/, .github/, private/renet/build.sh, private/account/{src,scripts,CLAUDE.md}, docs/;
    - (c) any `__`-prefixed store name bound by a profile;
    - (d) `RENET_KEYLESS` outside .github/workflows and tests;
    - (e) a `CACHE_STORE_NAMES` value that is not exactly its own name.
  - Register it in package.json, gate-costs.json and lane-durations.json.
  - Change test_deploy_deploy_proxy.py:1158 to assemble the literal at run time (under PLAN-executor-durable-object-policy's lease).

  Tests (gate test, controls):
  - Each rule goes red on its planted fixture in a temp tree: a `_DEV` map row, an `ACCOUNT_JWT_SECRET_DEV` line in a .py, a `__X` profile binding, `RENET_KEYLESS=1` in rdc.sh, and a `_DEV` cache alias.
  - `__ACCOUNT_X_DEV` text alone does not trip rule (b).
  - The real tree is green.

  Owns: .ci/config/bws-secret-map.json, .ci/config/bws-unrequested.json, .ci/config/env-manifest.json, scripts/data/doc-registry.md, .ci/scripts/quality/check_no_dev_keys.py (new), .ci/rediacc_ci/quality/no_dev_keys.py (new), .ci/rediacc_ci/tests/gates/test_gate_no_dev_keys.py (new), package.json (one script line), .ci/config/gate-costs.json, .ci/config/lane-durations.json, .ci/rediacc_ci/tests/test_deploy_deploy_proxy.py (line 1158 only). Accept: `npm run check:ci-no-dev-keys`, `check:ci-bws-map`, `check:ci-bws-map-live` and `check:ci-secret-supply` rc 0, and the gate test rc 0.

- [ ] L2 [live] Bench redeploy with the production six, after the merge.
  1. Run `bws_env exec --profile deploy-bench -- PYTHONPATH=.ci python3 -m rediacc_ci.ops.deploy_bench`. Record the version id, smoke rc and rollback command.
  2. Run `prune_worker_secrets --region bench` to check for extras.
  3. Point eu-bench's `account.e2ePublicKey` at bench's new server-info key (`buildInitAccountUpdate`, packages/cli/src/commands/config.ts:127-146; the writer confirms the exact verb).
  4. Re-login with rediacc_ci.ops.login_bench.
  5. Run `--config eu-bench subscription refresh -m <each bench machine>`.
  6. Run a bench backup drill. It must pass with licences under fingerprint `fb37f1ae16f8b7c0`.

- [ ] L3 [live] hostinger, read-only first.
  1. Run `renet_key_gate` against the local `private/renet/bin/renet` built by `./rdc.sh`. It must pass and name `fb37f1ae16f8b7c0`.
  2. Run `./rdc.sh machine status hostinger --config eu-remote --licenses -o json`. Every repo licence must be present under that fingerprint.
  3. Then, with the operator's go (a mutating verb uploads renet), rerun the snapshot that failed on one repo and record its rc and record id.

- [ ] L4 [live] Local machines and VMs.
  1. Run `./run.sh setup` on each dev box. The cache must now hold the production public key, which `renet_key_gate.key_fingerprint` checks.
  2. Run `./run.sh account reset` (DB only) or `rdc --dev subscription refresh -m <vm>` for each ops VM.
  3. Run `npm run vm:check -- --changed` green on the merged tree.

- [ ] LP-bench [live] Fresh bench receipt through worklist.py --live-proof after L2.
- [ ] LP-hostinger [live] Fresh hostinger receipt through --config eu-bench after L3 and a verified vm:check on the same tree. Ask the operator first, because provisioning restarts the router.

## Alternatives rejected

- **Keep a DEV keypair and add an upload guard that refuses a DEV-baked renet on non-dev machines.** It keeps the two-key choice the operator ruled out.
- **Delete the `_DEV` entries.** The ruling says rename, and parking keeps the values recoverable.
- **Drop the public-key cache and fetch from bws on every `./rdc.sh` run.** That adds a network call per invocation for a public value and breaks offline builds.
- **Re-point `account reset` to rotate the production keys.** That turns a local DB wipe into a production rotation of every region.

## Risks

- The dev box and bench now hold production secrets (Design 2). The operator ruled this, and it is accepted.
- The L1-to-merge window: other sessions on main lose `./run.sh account dev` until the merge. Keep the window to minutes.
- A missed keyless CI step goes red after K4 with the build.sh refusal message. That failure is loud and named, which is intended.
- Bench sessions and any eu-bench pin break in L2 until the re-login and re-pin. Only bench is affected.

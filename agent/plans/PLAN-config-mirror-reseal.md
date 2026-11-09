# PLAN: the config-store mirror reseals config layer 3 under the target channel's key

Status: proposed -- no operator ruling promotes it yet (CB5 of PLAN-plan-compaction-bindings.md): worklist #fc0490ad, left open when PLAN-config-server-key closed, had no live home
Depends-On: no-dep -- PLAN-config-server-key.md finished (every box ticked, merged in PR 602 at ae2fa4570), so the per-channel keys and the csk1.<kid> row format this box reseals already exist
Owner: d778be9d
Worklist: #90e05ca6
First-Seen: 2026-10-27
Updated: 2026-11-09
Priority: P2 -- every mirror of a store that holds a server-recoverable passphrase refuses, so the bench copy of a real store cannot be refreshed
Concurrency: parallel -- one box owning the mirror, its test and one account script
Live-Proof: bench -- the reseal script under private/account/scripts is the account surface, whose only live target is bench, and the mirror it serves writes the bench account database
Owns: agent/plans/PLAN-config-mirror-reseal.md, .ci/rediacc_ci/ops/mirror_config_store.py, .ci/rediacc_ci/tests/test_ops_mirror_config_store.py, private/account/scripts/**

## Context

After PLAN-config-server-key K1 and K2 each channel holds its own `ACCOUNT_CONFIG_SERVER_KEY`, and a `csk1.<kid>.` row opens only under the key that sealed it. `check_server_key` in `.ci/rediacc_ci/ops/mirror_config_store.py` therefore refuses a row sealed under the stable key when the target is another channel, and says so: "no step reseals it under the target's key yet (worklist #fc0490ad)". The sealing code is `private/account/src/services/config-server-key.ts`; the rewrap script the item named (rewrap-config-server-key, under the account scripts folder) is not in the tree, and `private/account/scripts/tsconfig.json` did not type-check it (it needs the DOM lib for `CryptoKey`). The helper existed as `scripts/rewrap-config-server-key.ts` in private/account ae9d3be and was removed in 35f8262 (K6).

## Tasks

- [ ] R1 Reseal before the mirror writes: open each layer-3 row with the source channel's key and seal it under the target's (`ACCOUNT_CONFIG_SERVER_KEY_<SUFFIX>_STABLE` or `ACCOUNT_CONFIG_SERVER_KEY_BENCH`, the names `key_env_name` gives both ends), through one script under `private/account/scripts/` that reuses `private/account/src/services/config-server-key.ts` and type-checks under `private/account/scripts/tsconfig.json`; `check_server_key` then accepts a resealed row and still refuses a row it could not reseal. Accept: `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests/test_ops_mirror_config_store.py` rc 0 with a reseal case and a control that a wrong source key refuses, and one `--dry-run` of a real store from eu to bench that reports every row resealable.
- [ ] LP-bench [live] Fresh bench receipt (PLAN-tested-on-bench ruling 3): deploy this branch to bench with deploy_bench, then record and tick through worklist.py --live-proof.
  - Accept: `live-proof bench account-smoke`

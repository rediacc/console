# PLAN: settings set verb: one registry of tunables and one verb that writes every copy of a value, validates it and runs the tests that pin it

Status: approved -- operator /ask 2026-10-30T06:40Z: "Yes, plan it" (a settings verb so any session can change tunables safely); PR-TASK 9f92c43e.
Depends-On: no-dep -- S1 and S2 need nothing outside this plan. S3 edits .ci/rediacc_ci/ops/cf_usage_report.py and its test, which PLAN-cloudflare-spend-guard.md owns (open box T6), so S3 runs only under that plan's writer lease or after T6 closes.
Owns: agent/plans/PLAN-settings-set-verb.md, scripts/settings/**, scripts/lib/settings/**, .ci/config/settings.json, .ci/config/cf-spend-guard.json, .ci/rediacc_ci/ops/cf_usage_report.py, .ci/rediacc_ci/tests/test_ops_cf_usage_report.py, .ci/scripts/quality/check_settings_registry.py, .ci/rediacc_ci/tests/gates/test_gate_settings_registry.py, package.json, .ci/config/gate-costs.json, .ci/config/lane-durations.json, docs/agent-reference/ci-gates.md
Owner: d778be9d
Updated: 2026-10-30
First-Seen: 2026-10-30
Priority: P2 -- one operator ruling (R2 storage to 5 TB) had to be written into three places by hand on 2026-10-30, and only a test caught a missed copy; every other tunable under .ci/config is hand-edited JSON with no validation at write time
Concurrency: parallel -- S1 and S2 own new files except one script line each in package.json (S1) and the shared package.json, gate-costs.json and lane-durations.json rows (S4), which PLAN-production-key-only.md also lists in Owns: the two plans edit different lines there and `block_plan_concurrency` serializes the writers on the same file; S3 touches the spend-guard files under that plan's lease (Depends-On); S4 follows S3.

## Finding

- The R2 storage ceiling lives in three places, kept equal by hand:
  - `.ci/config/cf-spend-guard.json:21-25`, `notifications.products.r2_storage.limit` (the Cloudflare alert policy that `rediacc_ci.ops.cf_notifications` upserts);
  - `.ci/config/cf-spend-guard.json:81`, `report.r2_storage_bytes` (the weekly report's ceiling);
  - `.ci/rediacc_ci/ops/cf_usage_report.py:43`, `DEFAULT_CEILINGS["r2_storage_bytes"]`, used whenever the JSON lacks the key (`load_ceilings`, :105-124).
- Only `.ci/rediacc_ci/tests/test_ops_cf_usage_report.py:192-200` (`test_default_ceilings_agree_with_the_ruled_report_object`) keeps the code default equal to the JSON, and it compares only the keys the `report` object carries. Five of the ten `DEFAULT_CEILINGS` keys (:40-53) have no JSON copy at all (the workers, R2 class A/B and D1 ceilings), so their only source is code.
- The same shape repeats inside the JSON: `worker_requests` and `worker_standard_request` both carry 20000000 (:6-14), and the report's `workers_requests_month` default is that number again in code.
- Search first: two verbs already change committed settings safely, and this plan reuses their patterns instead of inventing a third.
  - `npm run pins -- bump` (scripts/pins/pins.ts) plans the whole rewrite first, refuses a file holding another session's changes, journals before-bytes, runs the named gates and restores by comparison on failure (scripts/lib/pins/txn.ts:1-30). It never commits and prints the `git add`/`git commit -F` lines.
  - `worklist.py --queue-set` (.claude/hooks/stop/worklist.py:2538-2545) validates every pair before touching the file and refuses the whole call on one bad pair.
  - Nothing covers .ci/config tunables: no `settings` script in package.json and no registry of tunables anywhere in the tree.

## Design

1. **The verb.** `npm run settings -- <verb>` (scripts/settings/settings.ts):
   - `list [--json]`: every registered id, its value at each copy, unit, and whether the copies agree.
   - `get <id> [--json]`: one id, with every copy and its source line.
   - `set <id> <value> --reason '<why>' [--task <id>]`: parse, validate, plan every copy, write through the pins transaction, run the id's tests, print the commit lines. Never commits or pushes.
   - `--selftest`: fixture controls and mutants, the pins pattern.
2. **The registry**, `.ci/config/settings.json`, one entry per id:
   - `id` (for example `cf.r2_storage_bytes`), `unit` (`bytes`, `count`, `usd`, `ms`), `min`/`max`, `why`;
   - `copies`: `[{file, json_path}]`, the first one the source; every copy is written by `set`;
   - `reason_path`: where the ruling text lands (for example `report_reason` or the product's `why`);
   - `tests`: gate ids and pytest node ids `set` runs after the write.
3. **Parsing.** One parser per unit: `5TB`, `500GB`, `5e12` and `5000000000000` all give bytes (decimal SI, binary only with `TiB`/`GiB`); `20M` gives a count; `$350` gives usd. A value outside `min`/`max` or unparseable is refused before any write.
4. **One source.** `DEFAULT_CEILINGS` leaves cf_usage_report.py. Every ceiling moves into the `report` object, and `load_ceilings` reads only the JSON and raises on a missing key. A copy that exists only to feed a second consumer (`notifications...limit` beside `report...`) stays a registered copy, which `set` writes and the gate compares.
5. **The gate**, the new settings-registry gate (created and named in S4): every copy resolves, every copy of an id holds the same value, each value is in range, and every registered file exists. Controls: a planted disagreement, a dangling path and an out-of-range value each go red; the real tree is green.

## Tasks

- [x] S1 [writer] The registry and the read verbs. Changes: `.ci/config/settings.json` with the spend-guard ids (the six report ceilings, the four container ceilings, the six notification limits, each with its copies); scripts/settings/settings.ts with `list`, `get` and the unit parsers in scripts/lib/settings/units.ts; the `settings` script in package.json.
  Owns: .ci/config/settings.json, scripts/settings/**, scripts/lib/settings/**, package.json (one script line). Accept: `npm run settings -- --selftest` rc 0, and `npm run settings -- list` rc 0 showing every spend-guard id with agreeing copies.
    (ticked) 2026-10-30T22:41:01Z by d778be9d: commit:99ef80d8 package.json:410; npm run settings -- --selftest rc 0 (44 controls); settings -- list rc 0. DEPS-WAIVED: the box's code and its acceptance commands do not depend on the open prerequisite plans

- [x] S2 [writer] `set` through the pins transaction. Changes: `set` plans every copy and the reason path, refuses a peer-dirty file and an out-of-range or unparseable value before writing, writes through scripts/lib/pins/txn.ts (journal under .ci/cache/settings/<stamp>/), runs the id's tests, restores by comparison on a red, and prints the commit lines.
  Owns: scripts/settings/**, scripts/lib/settings/**. Accept: `npm run settings -- --selftest` rc 0 with controls for an out-of-range value, a peer-dirty file, a failing test that restores the bytes, and `5TB` written as 5000000000000 to both spend-guard copies.
    (ticked) 2026-10-30T22:41:05Z by d778be9d: commit:99ef80d8 scripts/settings/settings.ts:22; set no longer passes -p no:cacheprovider; planted flag turns 4 controls red; a real set on a clone rc 0. DEPS-WAIVED: the box's code and its acceptance commands do not depend on the open prerequisite plans

- [ ] S3 [writer] One source for the ceilings. Changes: every `DEFAULT_CEILINGS` key moves into `report` of .ci/config/cf-spend-guard.json; `DEFAULT_CEILINGS` is deleted from .ci/rediacc_ci/ops/cf_usage_report.py and `load_ceilings` raises on a missing key; `test_default_ceilings_agree_with_the_ruled_report_object` is replaced by a test that a missing key raises.
  Owns: .ci/config/cf-spend-guard.json, .ci/rediacc_ci/ops/cf_usage_report.py, .ci/rediacc_ci/tests/test_ops_cf_usage_report.py. Accept: `PYTHONPATH=.ci python3 -m pytest .ci/rediacc_ci/tests/test_ops_cf_usage_report.py .ci/rediacc_ci/tests/test_ops_cf_notifications.py` rc 0, and `grep -n DEFAULT_CEILINGS .ci/rediacc_ci/ops/cf_usage_report.py` prints nothing.

- [x] S4 [writer] The registry gate. Changes: .ci/scripts/quality/check_settings_registry.py with the Design 5 rules and their controls, registered as the `check:ci-settings-registry` script in package.json, gate-costs.json and lane-durations.json; one paragraph in docs/agent-reference/ci-gates.md naming `npm run settings -- set` as the way to change a registered tunable.
  Owns: .ci/scripts/quality/check_settings_registry.py, .ci/rediacc_ci/tests/gates/test_gate_settings_registry.py, package.json (one script line), .ci/config/gate-costs.json, .ci/config/lane-durations.json, docs/agent-reference/ci-gates.md (one paragraph). Accept: the new settings-registry gate's npm script (added by this plan) at rc 0, the gate test rc 0, and `npm run check:ci-parity` rc 0.
    (ticked) 2026-10-30T22:41:08Z by d778be9d: commit:99ef80d8 .ci/scripts/quality/check_settings_registry.py:1; check:ci-settings-registry rc 0, rc 1 on three plants; pytest 10 passed; parity, reachability and gate-bind rc 0. DEPS-WAIVED: the box's code and its acceptance commands do not depend on the open prerequisite plans

## Alternatives rejected

- **A Python verb beside cf_usage_report.** The transaction, the peer-dirty refusal and the restore already exist and are tested in scripts/lib/pins/txn.ts; a second implementation would drift.
- **Fold tunables into pins.json.** A pin is a version with a release-age window and drivers; a ceiling is a number with a unit and a ruling. One registry per shape keeps both verbs simple.
- **Keep code defaults as a fallback.** A fallback is a second source; Design 4 removes it.

## Verification notes

- 2026-10-30, S2 on the real tree: `set` built its pytest step with `-p no:cacheprovider`. Disabling that plugin unregisters the `cache_dir` ini key, and pyproject's `--strict-config` then exits 4 with `Unknown config option: cache_dir` and collects nothing, so every real `set` went red and restored. The selftest stayed green because its fixture carried no pyproject. Fixed in scripts/settings/settings.ts: the flag is gone (the cache lands in the ignored `.ci/cache/pytest`), and the fixture now copies the console's own `[tool.pytest.ini_options]` table. Planting the flag back turned 4 controls red; a `set cf.d1_storage_bytes 5GB` against a `git clone --shared` of HEAD ran the two cf tests at rc 0 and printed the commit line.
- S2 journal path: the journal sits under `.ci/cache/pins/settings-<stamp>/`, not `.ci/cache/settings/<stamp>/` as the S2 text says, because scripts/lib/pins/txn.ts fixes its journal root; sharing it also shares the one-run lock and lets `npm run pins -- verify` see a settings run killed mid-write.
- S3 hand-off: when `DEFAULT_CEILINGS` leaves cf_usage_report.py, every `py_dict` copy leaves .ci/config/settings.json in the same change, `report/<key>` copies are added for the five keys `report` lacks today (workers_requests_month, workers_cpu_ms_month, r2_class_a_month, r2_class_b_month, d1_storage_bytes), and three settings selftest controls that name the code copy (three R2 copies, the `5_000_000_000_000` line, the `1\t1` numstat of cf_usage_report.py) move to the JSON-only shape.

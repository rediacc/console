# PLAN: sys.path hop debt -- canonicalize the 5 gate-flagged sites
Status: done
First-Seen: 2026-09-22
Owner: d778be9d
Updated: 2026-09-22

## Why this plan exists

`test_canonical_sys_path_hop.py::test_no_hand_written_hop_outside_the_exemptions_and_the_baseline` is red because 5 hand-written `sys.path.insert(...)` call sites exist in the tree that are in neither its `EXEMPT` dict nor its `BASELINE` dict.
Per the test's own docstring, the fix is never "add every finding to `EXEMPT`" -- `EXEMPT` is reserved for hops that are structurally permanent (the resolver itself, the two `.ci` shims, one ruff-E402-forced ordering, and two genuinely circular guard imports).
Everything else either gets fixed to the canonical form or, if it is real still-standing debt of the same shape as hops already in the tree, gets added to `BASELINE` (and to `FRESH`, since all 4 non-wlfix sites were introduced on 2026-09-21/22, after PRE-A1 established the canonical form).

Only 1 of the 5 sites (`wlfix.py`) can actually be rewritten to the canonical form without creating a new file.
The other 4 sit inside dual-use package modules or standalone hook scripts where the canonical resolver (`rediacc_ci.paths`) is not yet reachable without the exact hop being eliminated -- the same chicken-and-egg the test's docstring already documents for `check_pytest.py` and `setup/shadow_driver.py`.

## Findings (verified against the tree, not assumed)

The Fingerprint column is not a git object: it is `fingerprint()`'s own sha1-of-`ast.unparse` output (`.ci/rediacc_ci/tests/test_canonical_sys_path_hop.py:185`), the stable id the test's `BASELINE`/`FRESH` tables key on.
It is written below behind a `fingerprint:` marker, which is what tells check:ci-plan-citations it is not a git object; the value itself is exactly what appears in that file's tables.

| Site | Fingerprint | Class | Fix |
|---|---|---|---|
| `.ci/rediacc_ci/dev/shadow_driver.py:69` | `fingerprint:c1e552fa19e9` | Dual-use package module (imported by `.ci/rediacc_ci/tests/test_dev_www.py:43` and run as a script), same shape as already-baselined `setup/shadow_driver.py` | BASELINE + FRESH |
| `.ci/rediacc_ci/docker/shadow_driver.py:81` | `fingerprint:c1e552fa19e9` | Same dual-use class (imported by `test_docker_run_in_image.py`, also run as a script) | BASELINE + FRESH |
| `.claude/hooks/post-bash/cancel_old_ci.py:24` | `fingerprint:c1e552fa19e9` | Standalone script invoked by `lifecycle.run_pattern`; needs `.claude` on `sys.path`, not `.ci`; no shim exists yet | BASELINE + FRESH |
| `.claude/hooks/post-bash/refresh_pr_body.py:24` | `fingerprint:c1e552fa19e9` | Same as above | BASELINE + FRESH |
| `.claude/rediacc_hooks/tests/wlfix.py:111` | `fingerprint:33a55988e0f6` | Pytest-only fixture module; `.ci` already on `sys.path` via `pyproject.toml`'s `pythonpath = [".ci"]` | CODE FIX to `paths.on_sys_path(STOP_DIR)` |

Branch reality check, re-verified independently: `gh pr view 589` returns `state: MERGED`, `mergedAt: 2026-09-22T08:22:16Z`; `gh pr list --state open` returns zero. Local `0914-1` is 69 commits ahead of `origin/0914-1`. Ride the current branch; no new PR needed for this bookkeeping-sized fix.

## Task checklist

- [x] 1. `.claude/rediacc_hooks/tests/wlfix.py`: canonical-form fix.
    (ticked) 2026-09-23T11:19:19Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
  - Add `from rediacc_ci import paths` near the existing imports.
  - Replace the `if str(STOP_DIR) not in sys.path: sys.path.insert(0, str(STOP_DIR))` two-liner in `import_wl` with `paths.on_sys_path(STOP_DIR)`.
  - `sys` stays imported, since it is still used for `sys.executable` elsewhere.
  - Re-run `git diff -- wlfix.py` immediately before editing: another session has one unrelated uncommitted hunk in this file (RESET_KNOBS), nowhere near this region.
- [x] 2. `.ci/rediacc_ci/tests/test_canonical_sys_path_hop.py`: table additions.
    (ticked) 2026-09-23T11:19:19Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
  - Add `.ci/rediacc_ci/dev/shadow_driver.py` and `.ci/rediacc_ci/docker/shadow_driver.py` to `BASELINE` (`fingerprint:c1e552fa19e9`; see the note above the Findings table), alphabetically between `check_pytest.py` and `setup/port_parity.py`.
  - Add `.claude/hooks/post-bash/cancel_old_ci.py` and `.claude/hooks/post-bash/refresh_pr_body.py` to `BASELINE` (same fingerprint), alphabetically between `.claude/hooks/context/test-context-bands.py` and `.claude/hooks/stop/calibrate-judge-rules.py`.
  - Add all 4 paths to `FRESH`.
- [x] 3. Verify: `pytest .ci/rediacc_ci/tests/test_canonical_sys_path_hop.py -v` all pass.
    (ticked) 2026-09-23T11:19:19Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
  - `test_no_hand_written_hop_outside_the_exemptions_and_the_baseline` (was red, 5 findings) turns green.
  - `test_the_floor_holds_every_known_hop_is_still_found`, `test_the_baseline_names_only_files_that_exist`, `test_every_fresh_entry_is_really_baselined` and `test_the_exemptions_are_all_live` all stay green.
- [x] 4. Fires-on-a-planted-defect control: temporarily add an unbudgeted `sys.path.insert(0, "/tmp/plant")` to wlfix.py, confirm the target test reds naming it, then revert before committing. Confirm silence (zero findings) after the real fix with the plant reverted.
    (ticked) 2026-09-23T11:19:19Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] 5. Smoke-test wlfix.py's edited `import_wl` still works: `pytest .claude/rediacc_hooks/tests -k "wl_" -q` clean.
    (ticked) 2026-09-23T11:19:19Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] 6. Do not touch anything outside the 5 named files plus this plan file. No new shim file, no edit to `paths.py` or already-baselined siblings.
    (ticked) 2026-09-23T11:19:19Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites

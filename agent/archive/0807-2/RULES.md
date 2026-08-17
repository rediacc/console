# RULES: branch 0807-2 (version-hole wave)

**SHARPEN THIS FILE. Do not append to it.** Settled facts and standing
constraints for this branch. Wrong rule -> edit it here, not below it.
Sharpened from `.agent/0807-1/RULES.md` on 2026-08-07 by session d136ac61.
0807-1's own content did NOT carry forward — its js-yaml, i18n and
amend-hook items belong to that branch, which is a SEPARATE PR.

## What this branch is

The big-bang closing every remaining "a version check that cannot fail" hole,
approved by the operator on 2026-08-07 with an explicit rule:

> **WE SHOULD ALWAYS HAVE A VERSION! SKIP OR FAIL!**

Every path must end VERIFIED, or in an explicit VISIBLE skip, or in a FAILURE.
A path that cannot determine a version and returns success IS the defect. That
is the yardstick for every change here; if a fix leaves a fourth outcome, it is
not done.

Cut from local `main`, so it CARRIES `e3407af36` (the verify_version fix) as an
ancestor. That commit is on main locally and is deliberately unpushed — see
STATE.md.

## Do not re-litigate

- The three fixes already on main or in the base are DONE and must not be
  redone: `assert-artifact-version.sh` (looked for a `cli-manifest` artifact
  nothing produced, so it warned and exited 0 on every release of its life),
  the Windows install validation (ran `--version` and discarded the output),
  and `verify_version()` (passed on empty expectation, empty output, and
  substring — 1.2.1 "verified" against 1.2.16).
- `compareVersions` does NOT return 0 for an empty string. `Number('')` is 0,
  so `('1.2.16','')` returns 1. The silent-equal case is NON-NUMERIC segments:
  `('1.2.16','1.2.x')` and `('x.y.z','1.2.16')` both return 0. Verified by
  running it. Any fix must target NaN segments, not emptiness.
- Landing shape: NEW BRANCH + PR, operator's explicit choice. Not main.

## Standing constraints

- Never push `main` from this branch, never merge, never force-push, never
  suppress a gate.
- Never `git checkout/restore/stash/clean`. Repair forward. Shared tree.
- TWO WRITER AGENTS share this branch with DISJOINT file ownership. The lead
  does ALL committing; writers never run git. Ownership:
  `fix-installtests` -> `.ci/scripts/test/test-install-methods.sh`,
  `test-linux-packages.sh`, new `gates/test-installmethods-*.sh`.
  `fix-releaseguards` -> `cd-v2.yml`, `ci-build-cli.yml`, `ci-build-docker.yml`,
  `build-cli-executables.sh`, `build-cli-musl.sh`, `initialize.sh`,
  `generate-tag.sh`, `inject-env.sh`, `verify-artifact-attestation.sh`,
  `version.ts`, new `gates/test-releaseversion-*.sh`.
- NEVER stage `.claude/settings.local.json`, `private/generative`,
  `private/growth`, or a submodule pointer that merely drifted.
- Gate-test protocol: source `../lib/test-helpers.sh`; the helper is
  **`assert_eq`**, there is no `assert_equals`. Start `log_test`, end
  `log_pass`. `run-all.sh` auto-discovers `gates/test-*.sh` and REJECTS a test
  that exits 0 registering no assertions. Baseline to preserve: 71 passed,
  0 failed, 820 assertions.
- A new `check:ci-*` gate needs BOTH an npm script AND a manifest GateSpec, or
  `check-ci-parity.ts` fails; its declared `leaves` must match what
  package.json resolves to.
- `mapfile` is BANNED (minimal CI shell) — use a read loop. shfmt is `-i 4 -ci`.
- No attribution trailers in commits; no backticks in `git commit -m`;
  amending is hook-blocked, make a NEW commit.
- Round-tripping JSON in python: pass `ensure_ascii=False`, and re-verify the
  WHOLE file after any scripted edit — the diffstat is the cheapest place to
  catch a rewrite scoped wider than intended.

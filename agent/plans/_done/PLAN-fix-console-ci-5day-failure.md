# PLAN: fix main's 5-day Console CI red streak

Status: superseded by operator ruling 2026-09-24: "Drop 0923-2 ... broken main is not our priority right now". The branch this plan drove was ported into 0923-1 commit by commit and deleted; its boxes stay [?] as abandoned by decision, not ticked. The one live remainder, dependency freshness, is tracked as worklist #e3db9ce2.
Ruling: #d9785655
First-Seen: 2026-09-24
Owner: d778be9d
Updated: 2026-09-23

## Finding

Main's "Console CI" workflow has failed 5 consecutive days (2026-09-19 through 2026-09-23), all on head `5f4c7608beff4c766de99891b7e0d4804622a004` (main has not been pushed to in that window; the last push-triggered green run was 2026-09-07).
A dispatched Plan agent read the actual failed-job logs of the latest run (`35822714317`) and found this is one CI run failing five independent ways, not one root cause -- several of Console CI's gates are calendar/registry-driven rather than diff-driven, so a frozen main goes red on its own over time.

## Root causes, one per failing job

| Job | Failing step | Nature | Evidence |
|---|---|---|---|
| Quality / Security | `Audit` | Environmental drift -- newly-published CVE advisories | `Production vulnerabilities: 1 critical, 4 high, 12 total` -- `GHSA-82fw-gwwq-j7x9` (vitest/@vitest/mocker path traversal), `GHSA-2883-xcg3-v3hh` (js-yaml DoS via merge keys), `GHSA-w27v-7q3p-w38r` / `GHSA-4vpr-x523-8j87` (svgo `removeScripts` bypasses). Nothing in the repo changed; the advisory DB did. |
| Quality / Content | `External dependency freshness` | Environmental drift -- a freshness-window gate firing after 2+ weeks with no dependency bump | 13 packages listed as "must upgrade" (jszip, eslint-plugin-playwright, @biomejs/biome, react/react-dom, typescript-eslint, etc.). The separate "Blocked packages" list (astro, eslint v10, playwright, glob majors) is deliberately held with documented reasons and is not part of this failure. |
| Quality / i18n | `Plan file housekeeping` | Environmental drift by design -- a wall-clock gate | 32 plan files unchanged for more than 33 days (main's pre-reorg flat `agent/PLAN-*.md` layout; this branch already moved to `agent/plans/`, so the fix targets main's actual paths), plus 15 more crossing the threshold soon. |
| Quality / Go | `rotation-bitwarden-names.test.ts` | Real, already-fixed regression -- stale submodule pointer | Main pins `private/account@65820fd7` (2026-09-05); account commit `dd232718` (2026-09-06, `fix(rotation): stop pushing secrets to GitHub, except the one that still needs it`) already fixed this exact test 17 days ago. Main's submodule pointer was never advanced past it. |
| Tests + Infra / Account E2E | 5 Stripe billing tests | Unresolved, needs verification after the submodule bump | `expiresAt did not change from "null"`, `Admin get subscription failed: 404`, plan never reaches `BUSINESS`. Confirmed not the `sk_test_dummy` fixture (that's a unit-test-only value); the E2E job uses the real sandbox key and webhooks return 200. Whether the submodule bump (which carries 9 account commits) also fixes this is unverified. |
| CI Complete | `Check all jobs passed` | Downstream aggregate of the five above | No independent cause. |

## Routing: a fresh branch against main, not PR #590

PR #590 (`0923-1` -> `main`) is a 527k+/194k- diff across 100 files for an unrelated tooling-transformation epic, still draft. Bundling a red-CI hotfix into it would hold the fix hostage to that review timeline, bloat an unrelated diff, and mix two very different risk profiles.
This plan cuts a fresh branch from `origin/main` (e.g. `fix/console-ci-main-red-streak`), PRs it against `main`, and goes through normal review + operator-authorized merge -- no direct push to main.

**This is a second, genuinely independent open PR against a different base than #590 (main vs main, but a different source branch), and CLAUDE.md's ONE OPEN PR rule makes that the operator's call.** Parked as a worklist `[?]` with a DEFAULT of proceeding, per the "ask decides packaging, never whether" rule -- the fix itself is not optional, only whether it rides its own branch is being confirmed.

## Steps

- [?] Cut a fresh branch from `origin/main`.
- [?] Bump `private/account` from `65820fd7` to its current green tip (at least `3e796472`, covering commit `dd232718`). Run the account submodule's own vitest suite first and confirm `rotation-bitwarden-names.test.ts` passes before pinning.
- [?] Dependency freshness: run the upgrade for the 13 "must upgrade" packages only (patch/minor); leave the documented "Blocked packages" list untouched. Files: `package.json`, `package-lock.json`. Verify `check:deps` green, then run the quality-branch lane to catch lint/type fallout from the react/react-dom/typescript-eslint bumps.
- [?] Security audit: for each of the 3 advisories, check whether a patched version is available via a non-major fix or a root `overrides` entry; if genuinely unfixed upstream, record a scoped, dated waiver following this repo's existing allowlist/BLOCKER pattern rather than force a breaking bump or leave it silently red.
- [?] Plan housekeeping: work main's own flat `agent/PLAN-*.md` layout (not this branch's `agent/plans/` reorg) -- for each of the 32 stale (and soon 15 more) plans, either continue the work, `git rm` if genuinely done/abandoned (checking for dangling citations first), or add a dated, reasoned entry to `.ci/policy/.plan-housekeeping-allowlist`.
- [?] Re-run the Account E2E job after the submodule bump; if the 5 Stripe tests still fail, treat that as a separate, still-undiagnosed issue and investigate with fresh logs rather than guessing.
- [?] Full `npm run ci` locally, then push and confirm CI green before requesting merge authorization.

## Verification

- [?] `rotation-bitwarden-names.test.ts` passes after the submodule bump.
- [?] `check:deps` green.
- [?] `.ci/rediacc_ci/security/audit.py` clean.
- [?] Plan housekeeping gate green on main's own layout.
- [?] Account E2E's 5 Stripe tests pass, or a fresh, separate investigation is opened if not.
- [?] Full `npm run ci` green before push.

## Critical files

- `.gitmodules` / `private/account` (submodule pointer)
- `package.json`, `package-lock.json`
- `.ci/rediacc_ci/security/audit.py`
- `scripts/gates/check-deps.ts`
- `agent/PLAN-*.md` on `main`, `.ci/policy/.plan-housekeeping-allowlist`

Design produced by a dispatched Plan agent (2026-09-23) reading the actual failed-job logs of run `35822714317`; this session verified the branch-routing decision and the submodule-pointer claim before writing this file.

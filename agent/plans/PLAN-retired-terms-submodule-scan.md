# PLAN: Retired-terms gate reads every checked-out submodule's tracked files
Status: executing -- triaged PLAN+SUBAGENT for worklist #2f9533de on 2026-10-24; design by a Plan agent, implemented this session on 1023-1.
Depends-On: no-dep -- extends an existing gate; the H-phase removals it baselines keep running on their own schedule
Priority: P2 -- stale retired-term text in submodules reaches no gate today
Owner: d778be9d
Updated: 2026-10-24
Owns: .ci/rediacc_ci/quality/retired_terms.py, .ci/scripts/quality/check_retired_terms.py, .ci/config/retired-terms.json, .ci/rediacc_ci/tests/gates/test_gate_retired_terms.py, .github/workflows/ci-quality.yml, scripts/ci-runner/manifest.ts, scripts/ci-runner/gates.lock.json, scripts/data/doc-registry.md, private/renet/CLAUDE.md, private/renet/docs/datastore/README.md, private/renet/pkg/kube/registry/zot.go, private/renet/cmd/renet/backup_stderr_test.go, private/renet/build.sh, private/renet/cmd/renet/backup_snapshot.go, private/renet/cmd/renet/backup_snapshot_cold.go, private/renet/cmd/renet/coldlock_invariant_test.go, private/renet/pkg/infra/aptretry/aptretry.go, private/account/web/src/lib/resource-pages.ts, private/account/web/src/hooks/__tests__/usePickerOptions.test.tsx, private/account/web/src/lib/__tests__/resource-options.test.ts, private/elite/docker-compose.yml
Live-Proof: bench, hostinger -- the zot registry, build.sh, backup snapshot and aptretry edits under private/renet are the renet surface, live on hostinger only, and private/account/web/src/lib/resource-pages.ts is the account surface, live on bench only.
Concurrency: parallel
Worklist: #2f9533de. Retirement context: agent/plans/PLAN-backup-program.md phase H.

## Why

`check:ci-retired-terms` (`.ci/scripts/quality/check_retired_terms.py`, logic in `.ci/rediacc_ci/quality/retired_terms.py`) judges two subject kinds: open worklist items (`item_subjects`, .ci/rediacc_ci/quality/retired_terms.py:529-535) and live plans (`plan_subjects`, :537-556). It never reads a file under `private/*`, nor any console source file. A sweep on 2026-10-24 with the shipped patterns over the submodules' tracked files found:

- Stale text no gate reports: `private/renet/CLAUDE.md:19,24,26,33,61` (renet no longer embeds rclone: no rclone in `private/renet/Dockerfile` or `pkg/embed/*.go`); `private/renet/docs/datastore/README.md:184-186` documents `--target storage --rclone-backend`, which `private/renet/cmd/renet/backup_push_test.go:61-69` asserts are gone; `private/renet/pkg/kube/registry/zot.go:7`; `private/account/web/src/lib/resource-pages.ts:99`. `private/account/CLAUDE.md:237` and the `BACKUP_S3_*` test comment were fixed in account 645a233.
- False positives the shipped patterns would raise on day one: `rclone` is case-insensitive with no boundary (.ci/config/retired-terms.json:38-39) and matches `discoverCloneState` at `private/renet/pkg/rbd/cowclone.go:220,281,283`; the `edge-rediacc-configs` lookahead (.ci/config/retired-terms.json:105) fires on `edge-rediacc-configs-<region>`.
- Deliberate history: `private/elite/docker-compose.yml:43-44` (the `BACKUP_S3_*` rename chain kept as a warning) and renet comments recording the rclone removal (X8).
- Removal in progress: about 50 renet files and 3 account files still name rclone, removed by PLAN-backup-program boxes H7, H8, H9, H11 and H13.

## Design

1. Enumeration: a third subject kind, `file`, built in `gather()` (.ci/rediacc_ci/quality/retired_terms.py:700). Submodules come from `rediacc_ci.gitx.submodules(root)` (.ci/rediacc_ci/gitx.py:457); each goes through `rediacc_ci.core.common.require_submodule` (.ci/rediacc_ci/core/common.py:495), which raises under CI (mapped to CannotRunError, rc 2) and returns False locally, printing `NOT CHECKED <path>`. Files come from `git -C <sm> ls-files -z`, keyed `<sm.path>/<rel>`; symlinks, gitlinks and binary files (a NUL in the first 4096 bytes, as .ci/rediacc_ci/quality/account_env_retired.py:107) are skipped. Anti-vacuity: a `.gitmodules` with zero entries, or a checked-out submodule with zero files, is CANNOT RUN; the shape line `N submodule(s) declared, M checked out, F file(s) read; NOT CHECKED: ...` prints every run. The file half runs only in the default mode, never under `--owner` (the Stop hook call). For files, a `retired_by` citation does not excuse a hit.
2. Findings and baseline: extend the existing shrink-only `plan_baseline` mechanism (.ci/config/retired-terms.json:148, `baseline_pairs` .ci/rediacc_ci/quality/retired_terms.py:258-280, `plan_verdict` :281-293, `write_baseline` :747-826) with a sibling `file_baseline: [{path, term, count, blocker}]`, count-keyed (the account_env_retired multiset precedent). A count above the ceiling or an unlisted file is NEW; below it is STALE until drained; an entry under a NOT CHECKED submodule is skipped and printed. `write_baseline` only lowers and removes, and refuses while any submodule is NOT CHECKED. `file_exclusions: [{prefix, blocker}]`, with a liveness rule (a prefix matching no tracked file is CANNOT RUN); one entry at landing, `private/account/drizzle/` (append-only applied migrations; H13 supersedes them with a new migration).
3. Marker: `retired-term-ok(<term-id>): <reason>` on the line, under any comment leader (a trailing `-->` or `*/` stripped), suppressing only its named term. Refused (rc 1): a missing or empty reason, a reason `allowlist.validate_reason` rejects, an unknown term id, a dead marker. Files only; JSON hits are baselined. Precedent: `style-ok` and `slop-ok` (.ci/rediacc_ci/quality/prose_style.py:89), which carry no reason; this one must.
4. Pattern corrections, narrowing only (`plan_baseline` is `[]`): `rclone` becomes case-sensitive `rclone|R(?i:clone)` with `discoverCloneState` in `must_not_match`; the `edge-rediacc-configs` lookahead becomes `(?![A-Za-z0-9_]|-[A-Za-z0-9<{$])` with `edge-rediacc-configs-<region>` and `edge-rediacc-configs-${region}` in `must_not_match`.
5. Landing disposition: the rclone fix list (CLAUDE.md, datastore README, zot.go, backup_stderr_test.go fixtures, resource-pages.ts) per the design report; markers on the deliberate history lines; a hand-seeded `file_baseline` (43 entries) whose BLOCKERs name the draining H box; the drizzle exclusion.
6. Lane: the header moves from `lane: quality-static`, `needs: none` (.ci/scripts/quality/check_retired_terms.py:7-9; quality-static checks out no submodules, .github/workflows/ci-quality.yml:197-212) to `lane: quality-security`, `needs: submodules`, beside `check_account_env_retired.py`; then `npm run gate:bind`, the manifest job (scripts/ci-runner/manifest.ts:1703-1714) and `npm run gen:gates-lock`.

## Boxes

- [x] X1: Pattern corrections in `.ci/config/retired-terms.json` (rclone and edge-rediacc-configs, plus the new must_not_match texts) and a `_comment` covering `file_baseline`, `file_exclusions` and the marker. Accept: `.ci/scripts/quality/check_retired_terms.py --selftest` rc=0
    (ticked) 2026-10-24T13:52:25Z by d778be9d: X1 landed in aa78e9680; check_retired_terms.py --selftest rc=0 (60 controls) on this tree
- [x] X2: File enumeration in `retired_terms.py`: gitx.submodules, require_submodule, `git -C <sm> ls-files -z`, the NOT CHECKED line, CI fail-closed, the zero-declared and zero-files floors, the file half skipped under `--owner`, with selftest controls. Accept: `.ci/scripts/quality/check_retired_terms.py --selftest` rc=0
    (ticked) 2026-10-24T13:52:46Z by d778be9d: landed in 64c99d907; check_retired_terms.py --selftest rc=0 (60 controls)
- [x] X3: The marker parser and its four refusals, with selftest PLANT and CONTROL entries both ways. Accept: `.ci/scripts/quality/check_retired_terms.py --selftest` rc=0
    (ticked) 2026-10-24T13:52:47Z by d778be9d: landed in 64c99d907; check_retired_terms.py --selftest rc=0 (60 controls)
- [x] X4: `baseline_pairs` and `plan_verdict` generalised to `file_baseline` (count-keyed) and `file_exclusions` (BLOCKER plus liveness); `write_baseline` lowers and removes only, refusing while a submodule is NOT CHECKED. Accept: `.ci/scripts/quality/check_retired_terms.py --selftest` rc=0
    (ticked) 2026-10-24T13:52:49Z by d778be9d: landed in 64c99d907; check_retired_terms.py --selftest rc=0 (60 controls)
- [x] X5: pytest controls in `test_gate_retired_terms.py` over a fixture submodule: a planted term FIRES as NEW; a clean submodule is silent; a marked line with a reason is silent; a marker with no reason, a low-effort reason, a dead marker and an unknown-term marker are refused; a baselined path is held, a count rise is NEW and a fall is STALE; an excluded prefix is silent and a dead exclusion is rc 2; a baseline entry without BLOCKER is rc 2; a declared but absent submodule is NOT CHECKED rc 0 locally and rc 2 under CI=true; zero `.gitmodules` entries is rc 2; the drain never raises a count. Accept: `PYTHONPATH=.ci python3 -m pytest .ci/rediacc_ci/tests/gates/test_gate_retired_terms.py -q` rc=0
    (ticked) 2026-10-24T13:53:19Z by d778be9d: landed in 64c99d907; pytest test_gate_retired_terms.py rc=0 (32 passed)
- [x] X6: renet fixes (CLAUDE.md, docs/datastore/README.md, zot.go, backup_stderr_test.go), committed in renet first. Accept: `! git -C private/renet grep -nI -E '(^|[^a-z])rclone|Rclone|RCLONE' -- CLAUDE.md docs/datastore/README.md pkg/kube/registry/zot.go cmd/renet/backup_stderr_test.go` rc=0 and `npm run check:ci-renet` rc=0
    (ticked) 2026-10-24T13:54:39Z by d778be9d: renet 6e85b02 under d2953620b; git grep for rclone in the four files rc=0 (no hits), npm run check:ci-renet rc=0
- [x] X7: account: fix private/account/web/src/lib/resource-pages.ts:99 and mark private/account/web/src/hooks/__tests__/usePickerOptions.test.tsx:159 and private/account/web/src/lib/__tests__/resource-options.test.ts:198. Accept: the account web vitest lane for those files rc=0
    (ticked) 2026-10-24T13:53:20Z by d778be9d: account 2cf3374 under 69e799037; vitest usePickerOptions.test.tsx and resource-options.test.ts rc=0 (31 passed)
- [x] X8: renet markers on the history lines private/renet/build.sh:215, private/renet/cmd/renet/backup_snapshot.go:231, private/renet/cmd/renet/backup_snapshot_cold.go:41, private/renet/cmd/renet/coldlock_invariant_test.go:100, private/renet/pkg/infra/aptretry/aptretry.go:4, each under the golangci `lll` limit. Accept: `npm run check:ci-renet` rc=0
    (ticked) 2026-10-24T13:54:40Z by d778be9d: renet 6e85b02 under d2953620b; markers replaced by term-free wording this session; npm run check:ci-renet rc=0
- [x] X9: elite markers `retired-term-ok(BACKUP_S3_pre-rename): <reason>` on private/elite/docker-compose.yml:43 and :44. Accept: `docker compose -f private/elite/docker-compose.yml config -q` rc=0
    (ticked) 2026-10-24T13:52:52Z by d778be9d: elite b2430f1 under aa78e9680; docker compose config -q rc=0
- [x] X10: Bump the submodule pointers, then hand-seed `file_baseline` (counts against the bumped pointers, one BLOCKER per entry naming its H box) and the drizzle `file_exclusions` entry. Accept: `.ci/scripts/quality/check_retired_terms.py` rc=0 showing `4 submodule(s) declared, 4 checked out` and no NEW or STALE line
    (ticked) 2026-10-24T13:52:53Z by d778be9d: d2953620b; check_retired_terms.py rc=0, 4 submodule(s) declared, 4 checked out, 0 new, 0 stale
- [x] X11: Wiring: header `lane: quality-security`, `needs: submodules`; `npm run gate:bind`; the manifest job; `npm run gen:gates-lock`; `npx tsx scripts/gen/gen-docs.ts --write`. Accept: `npm run check:ci-gate-bind && npm run check:ci-gates-lock && npm run check:ci-gen-manifest && npm run check:ci-lane-budget && npm run check:ci-retired-terms` rc=0
    (ticked) 2026-10-24T13:53:20Z by d778be9d: landed in 64c99d907; check:ci-gate-bind, gates-lock, gen-manifest, lane-budget, retired-terms all rc=0
- [x] X12: The module docstring (.ci/rediacc_ci/quality/retired_terms.py:1-54) and the header `why:` describe the file subject, the marker, file_baseline and exclusions. Accept: `npm run check:ci-retired-terms && PYTHONPATH=.ci python3 -m pytest .ci/rediacc_ci/tests/gates/test_gate_retired_terms.py -q` rc=0
    (ticked) 2026-10-24T13:53:21Z by d778be9d: landed in 64c99d907; check:ci-retired-terms rc=0 and test_gate_retired_terms.py rc=0 (32 passed)
- [x] LP-bench [live] Fresh bench receipt (PLAN-tested-on-bench ruling 3): deploy this branch to bench with deploy_bench, then record and tick through worklist.py --live-proof.
  - Accept: `live-proof bench account-smoke`
    (ticked) 2026-10-30T06:19:12Z by d778be9d: live-proof lp-fc4aa471d9a4 bench account-smoke rc=0 v=b0ffdd76-1edb-40a0-9517-ed940f8b3981
- [ ] LP-hostinger [live] Fresh hostinger receipt through --config eu-bench (PLAN-tested-on-bench ruling 3), after a VERIFIED npm run vm:check -- --changed on the same tree; ASK the operator first, because provisioning a branch renet restarts the router and daemons.
  - Accept: `live-proof hostinger renet-live`

Order: X1, then X2-X5 on the checker; X6-X9 in parallel, submodule commits first; X10 after X1, X4 and X6-X9; X11 and X12 last.

## Risks

- Count-keyed STALE makes each partial H-phase edit red until `--write-baseline` runs; the STALE line names the command.
- The inline marker could be read as one of the lint pragmas docs/agent-reference/suppressions.md:17-21 bans. Fallback if refused: a `file_allow: [{path, term, line_text_sha, blocker}]` list in the same config.
- Console's own files stay unscanned (235 still name rclone); a follow-up item adds console as a further root with an H1-H14 baseline.
- A NOT CHECKED submodule passes locally, loudly; CI fails closed only when `CI=true` exactly (.ci/rediacc_ci/core/common.py:495-527).
- `write_baseline` never adds, so the first seed is written by hand in X10 and each BLOCKER must name the right H box.
- This plan names retired terms, so it carries the token PLAN-backup-program (header) or it becomes a NEW plan finding against itself.

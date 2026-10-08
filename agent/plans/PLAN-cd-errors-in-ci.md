# PLAN: catch CD failures at the CI level

Status: approved -- operator 2026-10-08: "Catch CD errors at CI level as much as possible."
Depends-On: no-dep -- builds on release_state, check_soak_period, decide_release_mode and the housekeeping root fix landing on the same branch (#a5a1f981)
Owner: d778be9d
First-Seen: 2026-10-08
Priority: P0 -- main went red after the PR #599 merge on a CD invariant (release-state bijection) that no pre-merge check could see, and the edge release was blocked
Concurrency: parallel -- four writers with disjoint files (section 5); W2 starts after W1 publishes tag_retention_plan()
Owns: .ci/rediacc_ci/housekeeping/cleanup_versions.py, .ci/rediacc_ci/tests/test_housekeeping_cleanup_versions.py, .ci/rediacc_ci/release/retention_contract.py, .ci/rediacc_ci/tests/test_release_retention_contract.py, .ci/rediacc_ci/deploy/upload_to_r2.py, .ci/rediacc_ci/release/cd_preflight.py, .ci/rediacc_ci/tests/test_release_cd_preflight.py, .github/workflows/ci.yml, .github/workflows/housekeeping.yml, .github/workflows/cd-v2.yml, .ci/rediacc_ci/quality/ci_workflow_invariants.py, docs/agent-reference/release-process.md, .claude/commands/pr-merge.md
Worklist: #dd4cb2e3

## Why (2026-10-08)

Housekeeping Phase 2 (`.ci/rediacc_ci/housekeeping/cleanup_versions.py:1460-1500`) keeps the newest 20 tags. That count includes the non-semver `production` tag (`.ci/rediacc_ci/release/mark_production.py:120`), so only 19 semver tags survive. The R2 tracker prune (`.ci/rediacc_ci/deploy/upload_to_r2.py:131,492-540`) keeps 20 semver versions plus promotion candidates.

The 10-07 scheduled run 37604651929 deleted tag v1.3.1 while `cli/v1.3.1/.released` stayed. Console CI's `check-release-state` (`.github/workflows/ci.yml:989-1027`) runs on pushes to main only, so the drift surfaced first on main, in run 37736104945. That run cancelled itself, and CD did not release edge v2.2.0.

## Failure catalogue (design: opus Plan agent, file:line in its report)

| Class | Evidence | Catchable pre-merge |
|---|---|---|
| C1 two pruners whose retention windows disagree, one of them scheduled | today, #a5a1f981 | yes: property test, and a projection against live state |
| C2 the tag/Release keep rule ignores `in_walk` promotion candidates (.ci/rediacc_ci/release/check_soak_period.py:88) | not hit yet | yes: the same property test |
| C3 the retention window starves stable | d99774c83, bfaf3db8c | yes (tests exist) |
| C4 bump-none still moved the channel pointer | 11e0262cd | yes: logic plus projection |
| C5 sparse checkout missing a config file | ca2dabca9 | yes: check:ci-checkout-cone (782fda27e) |
| C6 app token lacking `workflows` | 567dcb4c | partly: a pin on the cd preset |
| C7 missing secret or config value | ce687556 | yes: guard steps exist |
| C8 a GitHub 5xx shipped a wrong decision | 6f47166dc, 5fc116f7f | mitigated: retry-then-refuse |
| C9 ordering / duplicate main run | de0d355c | fixed with tests |
| C10 Validate Promotion growing toward the watchdog | 59c93891 | yes: a projection |

## Boxes

- [ ] W1 housekeeping (opus; this is the #a5a1f981 root-fix writer):
  - Phase 2 counts strict-semver tags only and never deletes a tag whose sentinel exists. It also never deletes an `in_walk` version, and Phase 1 follows the same rule.
  - It fails closed when the sentinel listing is unreadable.
  - The dry-run counter tells the truth.
  - It extracts `tag_retention_plan()` as a pure function.
  - Control: the pre-fix rule replayed on today's state (19 semver tags plus `production`) goes red.
- [ ] W2 retention contract (opus): `.ci/rediacc_ci/release/retention_contract.py` and its test.
  - `tracker_retention_plan()` is extracted from upload_to_r2.py.
  - A property test over generated states asserts two things:
    - surviving tags equal surviving sentinels at or above the contract floor;
    - every `in_walk` version keeps its tag, Release, sentinel and snapshot.
  - The oracle is `release_state.assert_bijection` (.ci/rediacc_ci/quality/release_state.py:238).
  - Controls: a planted non-semver tag, and an in_walk version outside the top 20, each go red under the pre-W1 rule.
- [ ] W3 cd_preflight (opus): `.ci/rediacc_ci/release/cd_preflight.py` and its test. It is read-only and runs four checks:
  - (a) the bijection against live R2 and `git ls-remote --tags`;
  - (b) the bijection after the next housekeeping run, from the PR head's keep rules applied to live state;
  - (c) floor and pointer consistency;
  - (d) the PR's predicted next_version is neither tagged nor released.

  It also runs `update_homebrew_tap --dry-run` against the PR's checksums, and projects Validate Promotion's object count times copy rate against its 20-minute cap.

  Control: today's live snapshot (v1.3.1 sentinel, no tag) goes red.
- [ ] W4 wiring (opus):
  - A `cd-preflight` job on same-repo PRs and on main, aggregated into ci-complete.
  - housekeeping.yml gets a refusal pre-step.
  - cd-v2.yml init runs preflight before any write.
  - Pins in ci_workflow_invariants.py: the cd preset requests `workflows`, every cd-v2 `git push` uses the app token, and tag-and-release has no `contents: write`.
  - Docs: release-process.md, and the main-only list in pr-merge.md.
  - Controls: a push-only preflight `if:` reds the reachability check, and dropping `permission-workflows` reds the pin.
- [ ] A live run on a PR: cd-preflight green on the head, and red on a replay of the 10-07 state.

## What stays post-merge, and how it fails loudly

- **Scheduled jobs:** housekeeping runs the projection first and refuses any deletion that would break the bijection. It refuses, never auto-heals, matching Phase 8d (.ci/rediacc_ci/housekeeping/cleanup_versions.py:2611).
- **Drift between merge and release:** preflight (a), (c) and (d) run as cd-v2's first step.
- **Credentials, outages and mid-run merges:** these stay with retry-then-refuse and the all-or-nothing app token.

## Tunables

| Name | Value | Reason |
|---|---|---|
| Projection horizon | 2 housekeeping runs | covers the next 03:00 UTC run plus one more, so a PR merged after 03:00 is still judged |
| PR severity | current drift: blocking; projected drift: warning plus annotation | current drift would red main anyway; the hard refusal for projected drift lives in housekeeping |
| Validate Promotion | warn at 80% of 20 min, fail at 100%; rate 80 objects/min | the measured lower bound in 59c93891 |
| Keep counts | 20, from one shared constant | the contract test proves the two pruners agree by construction, not by coincidence |

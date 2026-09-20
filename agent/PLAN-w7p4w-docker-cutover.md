# PLAN: W7P4-W docker sub-slice — cut the 3 already-ported docker scripts over from bash to Python
Status: compacted
Owner: f4da5c2e
Full-Text-Blob: 34d1153bbcf19cb076af1957dcb17306000a4c53
Record-Sig: 47e04057

## Why
W7P4-W's docker sub-slice: three bash scripts (cleanup_staging, create_manifest, retag_image) fully ported to Python (W7P6 closed, 99/99 differential, K=5 ledgers), ready for workflow cutover. Cutover required staged rollout proving registry parity, fixing a scanner pattern-widening bug that would make staging_tag_guard vacuous-red, and sequencing across three release workflows to
avoid mutation races.

## Outcome
Landed: Stages 0-5 executed 2026-09-15. Entry points added, differential 99/99 passing. All 9 call sites flipped across ci-build-docker.yml (3x create-manifest), cd-v2.yml (3x retag-image), cd-stage.yml (3x retag-image). Gate scanner widened to match cleanup_staging.py without false positives. Sibling fix forced: cleanup_channel_docker_tags.py's hardcoded target updated (4
failing tests -> 17 passing). Remaining: disposable staging image in GHCR (version 1253038485) needs deletion, blocked on delete:packages scope.

## Lessons
- Staging_tag_guard widening exposed extension-shaped matcher false positives in .ci/rediacc_ci/ self-references. Scoping .py scanning to .ci/scripts only eliminated 17 false positives. Proved by independent plant/revert on bash and Python.
- A non-ported sibling (cleanup_channel_docker_tags.py, W7P5-a owned) had to be fixed in this pass when its hardcoded caller target moved. Prevents silent divergence from its own twin when commit lands.
- Plan's section 1.1 was wrong: cleanup_staging.py --dry-run returns before gh api LIST, not after. Real canary required nonexistent-tag fallback to prove error-path parity.
- Staging image deletion blocked on credential scope (delete:packages) separate from write:packages, a surprise in GitHub's package REST authorization model. Left as explicit cleanup.
- Scoping W7P4-W-docker as separate small box was correct: fully ready, disjoint workflows, acceptance criterion (K=5 + differential + real-run) doesn't map to gate-registration framework.

## Boxes
- [x] Run the real, read-only dry-run canary (§1.1) for all 3 scripts against
    (record) sig=9a712c29 done=77fdd9102
- [x] Add `.ci/scripts/docker/_cipath.py` (copied convention from
    (record) sig=ad18a60c done=77fdd9102
- [x] Re-run the existing differential suite (`test_docker_cleanup_staging.py`,
    (record) sig=9574cdc2 done=77fdd9102
- [x] Flip `ci-build-docker.yml`'s 3 `create-manifest.sh` call sites (§4b). —
    (record) sig=ee684f8e done=696a45bf9
- [x] Flip `cd-stage.yml`'s 3 `retag-image.sh` call sites (§4d). — **DONE.**
    (record) sig=6423f70c done=696a45bf9
- [x] Flip `cd-v2.yml`'s 3 `retag-image.sh` call sites (§4c). — **DONE.**
    (record) sig=04981742 done=696a45bf9
- [x] Widen `check-staging-tag-guard.sh`'s and `staging_tag_guard.py`'s scan
    (record) sig=2c7c6761 done=696a45bf9
- [x] Flip `.ci/scripts/release/cleanup-channel-docker-tags.sh:66` (§4e), in the
    (record) sig=677c752d done=696a45bf9
- [x] Confirm `check:ci-staging-tag-guard` still reports the same 1 call site
    (record) sig=079a9042 done=696a45bf9
- [x] Run `check:ci-python-lint`, `check:ci-dead-python`,
    (record) sig=223d6966 done=696a45bf9
- [x] Get one real (non-dry-run) invocation of `cleanup_staging.py` against a
    (record) sig=86e49bb5 done=696a45bf9
- [x] Record the K=5 ledgers, differential counts, and real-run results in the
    (record) sig=c1a60359 done=696a45bf9

## Record
Record-Kind: compacted
Prior-Status: stages
Compacted-By: d778be9d
Compacted-At: 2026-09-20T18:06:24Z
Boxes: 12 attested, 0 open, 0 abandoned
Epics: e87fa3ce
Touched: agent/PLAN-tooling-transformation.md, .ci/rediacc_ci/docker/retag_image.py, .ci/rediacc_ci/docker/create_manifest.py, .ci/rediacc_ci/docker/cleanup_staging.py, package.json, scripts/ci-runner/manifest.ts, .ci/scripts/release/cleanup-channel-docker-tags.sh, .ci/rediacc_ci/quality/script_exec_bit.py, .github/workflows/ci-build-docker.yml, .github/workflows/cd-stage.yml, .github/workflows/cd-v2.yml, .ci/scripts/docker/create-manifest.sh, .ci/scripts/docker/cleanup-staging.sh, .ci/config/constants.sh, .ci/scripts/docker/cleanup_staging.py
Gates: check:ci-dead-bash, check:ci-dead-python, check:ci-em-dash-surfaces, check:ci-python-lint, check:ci-shell-size, check:ci-staging-tag-guard
Why-Source: model
Read-History: `git show 34d1153bbcf19cb076af1957dcb17306000a4c53` recovers the text; `git log --find-object=34d1153bbcf19cb076af1957dcb17306000a4c53 --all` names the commit

## History
- 2026-09-20T18:06:24Z compacted by d778be9d from `stages` (record-sig 47e04057)

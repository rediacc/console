# PLAN: remove Autopilot completely
Status: compacted
Full-Text-Blob: d2f66802c91b406d26dcbf5a82eca82444b45c4b
Record-Sig: 53e10957

## Why
<FILL: why>

## Outcome
<FILL: outcome>

## Lessons
<FILL: lessons>

## Boxes
- [x] `grep -ril autopilot .` (excluding .git, node_modules) returns ONLY: the confirmed-unrelated packages/www tutorial hits, the frozen agent/ archives, the two flavor-text test fixtures (wlfix.py, test_wl_stuck_and_blockers.py), the historical docs/ci-overhaul/{06-progress,10-ci-port-baseline}.md snapshots, and the deliberately-kept historical-lesson comments in block_raw_pr_body_edit.py / its oracle twin, worklist.py/worklist_messages.py/wl_store.py/wl_checks.py, gitx.py, deploy_account.py, deploy_www.py, calibrate-judge-rules.py, and pr-epics/body.md -- nothing else.
    (record) sig=560f1317 done=abandoned
- [x] `npx tsx scripts/gen/gen-gates-lock.ts` (verify mode) exits 0.
    (record) sig=e3709674 done=abandoned
- [x] `npx tsx scripts/gen/gen-docs.ts` (verify mode) exits 0.
    (record) sig=ab28f47a done=abandoned
- [x] `python3 .ci/scripts/quality/check_language_policy.py` exits 0.
    (record) sig=42945172 done=abandoned
- [x] `python3 .ci/scripts/quality/check_python_env_registry.py` exits 0.
    (record) sig=b0c3c466 done=abandoned
- [x] `python3 .ci/scripts/quality/check_env_manifest.py` exits 0.
    (record) sig=d49ba2b9 done=abandoned
- [x] `npm run check:ci-parity` exits 0.
    (record) sig=86c755dd done=abandoned
- [x] `npm run check:ci-dead-bash` exits 0.
    (record) sig=14fc2afe done=abandoned
- [x] `npm run check:ci-label-inventory` and `check:ci-label-refs` exit 0 (only after the live labels are already deleted per section 5).
    (record) sig=bf45959c done=abandoned
- [x] `npm run check:ci-pytest` exits 0 with no collection errors (proves no leftover import of a deleted `.ci/rediacc_ci/autopilot/*` module anywhere).
    (record) sig=827f20c5 done=abandoned
- [x] Full CI green on the PR.
    (record) sig=d4a24120 done=abandoned
- [x] Delete the live GitHub labels `autopilot` and `autopilot-blocked` (`gh label delete`), and remove the Actions variables, the AUTOPILOT_PRIVATE_KEY secret, and the rediacc-autopilot App's ruleset bypass actor, on the live repo -- BEFORE the labels.yml edit below merges.
    (record) sig=12bb0cfa done=abandoned
- [x] Delete `.github/workflows/autopilot.yml`.
    (record) sig=ccc43e6c done=abandoned
- [x] Delete `.ci/rediacc_ci/autopilot/` (17 files).
    (record) sig=dd17aeba done=abandoned
- [x] Delete `.ci/rediacc_ci/quality/autopilot_no_bypass.py`, `.ci/rediacc_ci/quality/autopilot_breakpoint_alignment.py`, `.ci/rediacc_ci/security/autopilot_workflow_invariants.py`.
    (record) sig=1bc3916f done=abandoned
- [x] Delete `.ci/scripts/quality/check_autopilot_breakpoint_alignment.py`, `.ci/scripts/quality/check-autopilot-no-bypass.sh`, `.ci/scripts/ci/autopilot-guide-comment.cjs`, `.ci/scripts/autopilot/` (5 files).
    (record) sig=dacbdfc9 done=abandoned
- [x] Delete the 18 test_autopilot_*.py / test_quality_autopilot_no_bypass.py / test_security_autopilot_workflow_invariants.py files and the 5 test_gate_autopilot_*.py files.
    (record) sig=8b614bbc done=abandoned
- [x] Delete the 17 `.ci/rediacc_ci/tests/goldens/{autopilot-*,compose-prompt,fetch-review-threads,finish,linked-sub-prs,post-escalation,resolve-model-args,restore-trusted-config,review-payload,review-reply,state-comment,submodule-prs,sweep-campaigns,sweep-collect,update-state}` directories (667 files) -- leave `goldens/allowlist` alone (shared).
    (record) sig=2f6b2fc6 done=abandoned
- [x] Delete the 18 `.ci/shadow/{w7p2-autopilot-no-bypass,w7p6-autopilot-gate,w7p6-autopilot-push,w7p6-check-autopilot-workflow-invariants,w7p6-<each-remaining-module>}.observations.jsonl` files.
    (record) sig=80e4d54c done=abandoned
- [x] Remove check:ci-autopilot-workflow / check:ci-autopilot-bp-align from package.json (lines 35, 296) and scripts/ci-runner/manifest.ts (~4231-4241, ~4282-4292).
    (record) sig=0ab601ac done=abandoned
- [x] Regenerate scripts/ci-runner/gates.lock.json (gen-gates-lock.ts --write).
    (record) sig=3bb35bb2 done=abandoned
- [x] Remove the "Post the autopilot guide" step from the label-guide job in .github/workflows/ci.yml.
    (record) sig=ce45ab14 done=abandoned
- [x] Remove the autopilot / autopilot-blocked blocks from .github/labels.yml.
    (record) sig=abbba5dd done=abandoned
- [x] Remove the 4 autopilot.yml:* lines from .ci/policy/.profiler-coverage-allowlist.
    (record) sig=b5a5df62 done=abandoned
- [x] Drain .ci/config/language-policy-baseline.json (check_language_policy.py --write-baseline) and .ci/config/python-env-registry.json (check_python_env_registry.py --write-baseline).
    (record) sig=1e6a61d5 done=abandoned
- [x] Move the ~17 AUTOPILOT_*/GITHUB_AUTOPILOT_* names to the tombstone shard in .ci/config/env-manifest.json; remove the matching entries from .ci/config/secret-supply.json, .ci/config/bws-secret-map.json, .ci/config/bws-unrequested.json per their own gates' rules.
    (record) sig=aba13d1f done=abandoned
- [x] Regenerate scripts/data/doc-registry.md, docs/agent-reference/ci-gates.md's generated regions, and .ci/policy/README.md (gen-docs.ts --write); hand-edit ci-gates.md's prose at lines 128 and 290.
    (record) sig=774f60fd done=abandoned
- [x] Delete docs/ci-overhaul/03-v2-autonomy.md; edit the Autopilot-specific paragraphs/rows in README.md, 04-decisions.md, 05-execution-guide.md, PROMPT.md, 09-env-residue.md.
    (record) sig=082e0867 done=abandoned
- [x] Run every check in section 7 and the full CI suite; fix anything still red.
    (record) sig=8a50c639 done=abandoned
- [x] (Separate PR, private/account submodule) retire the AUTOPILOT_PRIVATE_KEY rotation entry and its Bitwarden Secrets Manager item.
    (record) sig=a8e7d284 done=abandoned

## Record
Record-Kind: compacted
Prior-Status: done
Compacted-By: d778be9d
Compacted-At: 2026-09-22T13:44:19Z
Boxes: 0 attested, 0 open, 30 abandoned
Epics: e87fa3ce
Touched: docs/agent-reference/ci-gates.md, .claude/hooks/stop/worklist.py, package.json, scripts/ci-runner/manifest.ts, scripts/ci-runner/gates.lock.json
Gates: check:ci-dead-bash, check:ci-label-inventory, check:ci-label-refs, check:ci-parity, check:ci-pytest, check:ci-shape-duplication
Why-Source: author
Read-History: `git show d2f66802c91b406d26dcbf5a82eca82444b45c4b` recovers the text; `git log --find-object=d2f66802c91b406d26dcbf5a82eca82444b45c4b --all` names the commit

## History
- 2026-09-22T13:44:19Z compacted by d778be9d from `done` (record-sig 53e10957)

# PLAN: the scope gate's false-line assertion is locale-dependent, not key-dependent
Status: compacted
First-Seen: 2026-09-20
Owner: 854ac1c6
Full-Text-Blob: 47c6717ec4575da4a682e5ed7b69a98a8b664cb3
Record-Sig: 66a09fb1

## Why
A test comparing scope-gate output lines used a bare `sort` command, which respects the ambient locale's collation rules. Under en_US.UTF-8, the characters `=` and `_` are weighted differently than in node's UTF-16 code unit sort, causing two job keys to transpose (`run_e2e_k8s_ceph=false` vs `run_e2e_k8s=false`). The test was green in CI (ubuntu-latest, codepoint locale) but red
on every developer machine with a UTF-8 collating locale, undetected for 26 days.

## Outcome
Fixed in `.ci/scripts/test/gates/test-scope-gate-outputs.sh`: added `LC_ALL=C` to line 254's sort command to match node's byte-order sorting, and moved the JS `.sort()` to occur after `.map()` (lines 187–196 reordered). Three controls verified the fix: C1 confirmed the locale was the cause, C2 and C3 planted defects (missing key, emission order) and confirmed the test still detects
real problems while staying green under all locale settings. TRAPS.md was updated with a rule for future authors. The change lands on PR #577 (release-gating work; no production code touched, only test comparison infrastructure).

## Lessons
- Shell `sort` without `LC_ALL=C` can diverge from node/jq/python sorts; any comparison between shell and another language's sorted output must pin the locale explicitly.
- CI's ubuntu-latest runs under a codepoint locale, masking bugs that appear immediately under UTF-8 collating locales common on developer machines — CI-green ≠ developer-green without locale parity.
- The test was checking set equality (same keys present) through order comparison — a category mistake that made it fragile to collation rules it did not intend to depend on.
- Byte-order sorts (UTF-16 code units) and glibc collation differ on punctuation and combining characters; documenting which sort a test depends on prevents accidental transposition when new keys are added.

## Boxes
(this plan carried no checkbox tasks)

## Record
Record-Kind: compacted
Prior-Status: draft
Compacted-By: d778be9d
Compacted-At: 2026-09-20T18:00:09Z
Boxes: 0 attested, 0 open, 0 abandoned
Epics: e87fa3ce
Touched: .ci/scripts/test/gates/test-scope-gate-outputs.sh, .ci/scripts/ci/scope-shadow.sh, .ci/scripts/quality/check-profiler-coverage.sh, scripts/ci-runner/manifest.ts
Gates: check:ci-parity
Why-Source: model
Read-History: `git show 47c6717ec4575da4a682e5ed7b69a98a8b664cb3` recovers the text; `git log --find-object=47c6717ec4575da4a682e5ed7b69a98a8b664cb3 --all` names the commit

## History
- 2026-09-20T18:00:09Z compacted by d778be9d from `draft` (record-sig 66a09fb1)

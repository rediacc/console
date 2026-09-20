# PLAN: W7P5-a deploy/release port — close the real-run-note gap, not re-port anything
Status: compacted
Owner: f4da5c2e
Full-Text-Blob: 64b41e3de247b051b0cfc19438f94e9c3a29bbc3
Record-Sig: 2d4f91d3

## Why
W7P5-a's gate checked that 16 deploy/release paths had dry-run parity (K=5 ledger) or were blocked by BLOCKER, but made no assertion about whether ledgered paths also executed their real-run half. Thirteen of the 16 ledgered rows never recorded a real run, creating a silent 'third state' — the same failure mode the box itself forbade for blocked paths, just in a different bucket.

## Outcome
Closed 2026-09-15. Group A (6 safe-to-run paths): verified bash twin and Python port outputs byte-identical, updated status notes with confirmation phrase. Group B (7 production-facing paths): extended gate to enforce that ledgered paths carry either a real-run confirmation or a real-run-specific BLOCKER; added 7 entries to `.ci/policy/.w7p5a-real-run-leg-blocklist` naming each
external system (CDN, Worker, GitHub) they reach. Gate now correctly reports '32 blocked, 16 ledgered, 9 confirmed, 7 leg-blocked'. The remaining 39 production-facing paths require explicit operator authorization before real runs are safe.

## Lessons
- Status-file prose claims in unchecked fields are identical third-state risks, regardless of which bucket (blocked vs ledgered) they sit in — validation must cover the content of the status field, not just its existence.
- Split multi-leg acceptance criteria (dry-run parity + one real run each) into separately-checkable, separately-enforceable pieces; leaving the second leg as implicit prose invites gaps.
- When concurrent writers share a file scope, confirm no one else holds it before starting — W7P5-b's writer was active nearby; the specific files mattered more than the wider tree state.
- A gate's selftest must PLANT each new check before deploying it live — the two new PLANT cases here caught the exact violations the gate was meant to catch.
- Reuse existing validation machinery (rediacc_ci.core.allowlist, BLOCKER text format) rather than inventing new status formats — byte-identical phrasing across all 16 ledger rows let a future audit grep for the marker and know it means the same thing everywhere.

## Boxes
- [x] Confirm no concurrent writer holds `.ci/shadow/w7p5a-status.json`,
    (record) sig=d9f1066e done=c126fbe0f
- [x] Group A, six real runs (Section 3): `resolve-www-deploy-target`,
    (record) sig=e8822a18 done=c126fbe0f
- [x] Update each of the six paths' `note` field in `.ci/shadow/w7p5a-status.json` to append the
    (record) sig=d00c5ddf done=c126fbe0f
- [x] Re-run `npm run check:ci-w7p5a-real-run-blockers` after the status-file edit; confirm rc=0
    (record) sig=bceef160 done=c126fbe0f
- [x] Extend `.ci/rediacc_ci/quality/w7p5a_real_run_blockers.py`'s `run()` with the fifth check
    (record) sig=9f3394a2 done=c126fbe0f
- [x] Add real-run BLOCKER entries for the 7 Group-B paths (`wait-for-preview-worker`,
    (record) sig=02848e2f done=c126fbe0f
- [x] Re-run `check:ci-w7p5a-real-run-blockers --selftest` and the gate itself; confirm the new
    (record) sig=e42e4162 done=c126fbe0f
- [x] Leave all 32 fully-`blocked` paths untouched — no real run, no status change, matching the
    (record) sig=3167ed51 done=c126fbe0f

## Record
Record-Kind: compacted
Prior-Status: draft
Compacted-By: d778be9d
Compacted-At: 2026-09-20T18:06:46Z
Boxes: 8 attested, 0 open, 0 abandoned
Epics: e87fa3ce
Touched: agent/PLAN-tooling-transformation.md
Gates: check:ci-policy-inventory, check:ci-w7p5a-real-run-blockers
Why-Source: model
Read-History: `git show 64b41e3de247b051b0cfc19438f94e9c3a29bbc3` recovers the text; `git log --find-object=64b41e3de247b051b0cfc19438f94e9c3a29bbc3 --all` names the commit

## History
- 2026-09-20T18:06:46Z compacted by d778be9d from `draft` (record-sig 2d4f91d3)

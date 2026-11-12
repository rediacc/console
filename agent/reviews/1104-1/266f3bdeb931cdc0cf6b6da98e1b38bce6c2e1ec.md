# Review 266f3bde: fix(www): hover the tutorial player before each playback click in its release gate

Commit: 266f3bdeb931cdc0cf6b6da98e1b38bce6c2e1ec
Repo: console
Branch: 1104-1
Parent: e59de2311fb4f0420091d518fc04f74413067ade
Patch-Id: 62511230913d6eb307be5c7777859b85b8b99c0b
Reviewed-At: 2026-11-11T20:12:47Z
Model: claude-haiku-5-5
Cost: $0.0057 USD, 1 call(s), 35.1s
Diff: 2808 bytes, 1 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=bug,ci why=Gate-script fix only in packages/www/scripts; no user-facing change.
Dropped: 0
Body-Sig: a5ac5162b644fb4f

## Findings

### 266f3bde.1 [medium] packages/www/scripts/test-tutorial-player-release-gate.js:210
Anchor: in-diff
Claim: The commit changes the retry classification (adds 'covered by') and adds a pointer-hover step before every playback click, but the diff contains no test for either; the only evidence is a manual investigator run, so a regex or hover regression would not be caught by any repo check.
Class: missing-control-test
Resolution: fixed 837cce00acc04b5fa92d94f2ca8a808a2dd7dca1 | d778be9d 2026-11-12T08:42:32Z

### 266f3bde.2 [medium] packages/www/scripts/test-tutorial-player-release-gate.js:222
Anchor: in-diff
Claim: clickWithRetry now retries a 'covered by' refusal (lines 221-222) without calling revealControls again, so if the 2 s idle timer hides the bar during the retry gaps (e.g. a slow first attempt on a loaded host), every retry hits the same hidden bar and the click is logged FAILED.
Class: other
Resolution: fixed 837cce00acc04b5fa92d94f2ca8a808a2dd7dca1 | d778be9d 2026-11-12T08:42:33Z

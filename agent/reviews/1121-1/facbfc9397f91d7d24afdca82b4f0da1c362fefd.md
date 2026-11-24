# Review facbfc93: fix(ci): tracked-credentials green: baseline the deactivated SES key id (operator ruling), unspell the example key

Commit: facbfc9397f91d7d24afdca82b4f0da1c362fefd
Repo: console
Branch: 1121-1
Parent: 75b7ec02a58174fe6807d48dfbe724ff46eb42d2
Patch-Id: 0dc16406bf8a24c043d74ce71788d749a7a8f65b
Reviewed-At: 2026-11-24T17:32:20Z
Model: claude-haiku-5-5
Cost: $0.0039 USD, 1 call(s), 17.4s
Diff: 3570 bytes, 2 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=ci why=CI baseline entry and a test docstring only; no user-facing change.
Dropped: 0
Body-Sig: d3f23a5a4ea40036

## Findings

### facbfc93.1 [high] .ci/config/tracked-credentials-baseline.json:5
Anchor: in-diff
Claim: The new entry "agent/worklist/ace763dd.jsonl:AWS_KEY_ID" exempts every AWS_KEY_ID finding in that whole file, not just the deactivated SES key, so any further AWS access key id appended to that store (for example by compaction or the markdown sync) passes check:ci-tracked-credentials instead of going red.
Class: security
Resolution: open

### facbfc93.2 [low] .ci/config/tracked-credentials-baseline.json:2
Anchor: in-diff
Claim: The note's provenance stamp "ASKED:2026-11-24T17:3xZ" is not a valid timestamp, so the operator-ruling record it is meant to document cannot be checked against the ruling time.
Class: other
Resolution: open

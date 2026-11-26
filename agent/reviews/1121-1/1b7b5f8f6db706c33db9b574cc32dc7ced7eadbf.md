# Review 1b7b5f8f: chore(forensics-detect): rebuild detect.wasm from the current renet detector inputs

Commit: 1b7b5f8f6db706c33db9b574cc32dc7ced7eadbf
Repo: private/account
Branch: 1121-1
Parent: b09578091286767b58711875a4d0d4a3dd1a8d12
Patch-Id: 11e1a43b13e16d4d2035ecf7b2012d12047c8cda
Reviewed-At: 2026-11-26T17:18:53Z
Model: claude-haiku-5-5
Cost: $0.0012 USD, 1 call(s), 7.1s
Diff: 1119 bytes, 2 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=patch kind=bug,ci why=Repairs a failing detect-wasm CI gate by rebuilding the detector artifact and its recorded hashes; the wasm binary itself is not inspectable from the diff.
Dropped: 0
Body-Sig: 9691a3397651a840

## Findings

### 1b7b5f8f.1 [medium] src/services/forensics-detect/wasm/detect-wasm.json:3
Anchor: in-diff
Claim: The diff changes model_public_key from "" to "svx7r1RfnJOcJjRxdrJu5eDfX6jZE5PnaasSHjZUuBw=", but the commit message describes only a rebuild for renet input hashes, so the change to the pinned verification key is undisclosed and no added test is shown that checks it.
Class: other
Resolution: not-a-bug | .ci/rediacc_ci/quality/detect_wasm.py:290 the gate rebuilds with the manifest model_public_key and compares; control at :390 fails on a differing key | d778be9d 2026-11-26T18:57:06Z

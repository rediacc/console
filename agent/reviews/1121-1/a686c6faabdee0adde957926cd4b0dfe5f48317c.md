# Review a686c6fa: feat(cli): incident export downloads and verifies raw evidence in one step

Commit: a686c6faabdee0adde957926cd4b0dfe5f48317c
Repo: console
Branch: 1121-1
Parent: 33e2287535dee8c8c26002453482aa76337bd34b
Patch-Id: 35ac1dfb7d4c4a7d75314ebbab6f852b5b8d30c3
Reviewed-At: 2026-11-25T21:57:03Z
Model: claude-haiku-5-5
Cost: $0.0092 USD, 1 call(s), 37.5s
Diff: 55353 bytes, 13 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=minor kind=bug,feature why=New export download and verification capability, plus a forensics verify key-source change.
Dropped: 0
Body-Sig: 0a8588d43c8ee040

## Findings

### a686c6fa.1 [high] packages/cli/src/commands/forensics.ts:34
Anchor: in-diff
Claim: `rdc forensics verify --dir` now takes public keys from the directory's own raw-manifest.json (`...manifestMachineKeys(options.dir)`), so a batch re-signed with an attacker key and a rewritten manifest verifies clean with exit 0 and no operator-supplied key, where before the operator's --machine-key was required.
Class: security
Resolution: fixed e92638b7dfa98e6887f5a9a673c6e99445a8f21a | d778be9d 2026-11-26T03:04:24Z

### a686c6fa.2 [medium] packages/cli/src/services/forensics/evidence.ts:239
Anchor: in-diff
Claim: If raw-manifest.json contains the JSON value `null`, JSON.parse succeeds and `manifest.machineKeys` throws a raw TypeError outside the try, so the intended forensics.badManifest refusal never fires.
Class: other
Resolution: open

### a686c6fa.3 [low] packages/cli/src/i18n/locales/en/cli.json:3494
Anchor: in-diff
Claim: The incident export description says the report is written to verification.json, but verification.json is only written when the manifest lists an audit or headers chain file; otherwise no report is written.
Class: doc-contradicts-code
Resolution: open

### a686c6fa.4 [low] packages/cli/src/services/forensics/client.ts:191
Anchor: in-diff
Claim: The byte-length mismatch refusal (forensics.rawFileTruncated) has no test in incident-read.test.ts or elsewhere in this diff, so a regression that drops the check would not fail any test.
Class: missing-control-test
Resolution: open

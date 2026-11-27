# Review 4e5fa359: fix(infra): renetMissing reads the exit code of either ssh transport

Commit: 4e5fa35973efdd9af3bbde3b5acab41a1b7d66fb
Repo: private/renet
Branch: 1121-1
Parent: c6bea0a7a494635440d21aed9a002332b24ed22f
Patch-Id: 69a8f2564bf410b32a9ef5c15814104ef7134d9a
Reviewed-At: 2026-11-27T00:34:17Z
Model: claude-haiku-5-5
Cost: $0.0027 USD, 1 call(s), 15.9s
Diff: 4016 bytes, 3 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=patch kind=bug why=Fixes ops up misreading an in-process Windows ssh exit 1 as a fatal error; no new capability.
Dropped: 0
Body-Sig: f89439b4872b019a

## Findings

### 4e5fa359.1 [medium] pkg/infra/worker/service.go:52
Anchor: in-diff
Claim: The fixed call site `if code, ok := sshexec.ExitCode(err); ok && code > 0 && code != 255` has no test: TestExitCodeReadsBothTransports only exercises the helper, so reverting renetMissing to the old *exec.ExitError assertion would still pass every added test.
Class: missing-control-test
Resolution: fixed d68f599b943ff145cfdcdcc355e2b3d228f0e09a | d778be9d 2026-11-27T00:45:11Z

### 4e5fa359.2 [low] pkg/infra/sshexec/exitcode.go:9
Anchor: in-diff
Claim: The doc says ok is false for an error with no exit status, but an *exec.ExitError from a process killed by a signal is reported as (-1, true), since e.ExitCode() returns -1 and ok is set unconditionally.
Class: doc-contradicts-code
Resolution: fixed d68f599b943ff145cfdcdcc355e2b3d228f0e09a | d778be9d 2026-11-27T00:45:11Z

### 4e5fa359.3 [low] pkg/infra/sshexec/exitcode_test.go:14
Anchor: in-diff
Claim: The test runs `sh -c 'exit 3'` with no build tag or skip, so on Windows (the platform this in-process transport targets) sh is not found, execErr is not an ExitError, and the 'exec exit error' case fails.
Class: missing-control-test
Resolution: fixed d68f599b943ff145cfdcdcc355e2b3d228f0e09a | d778be9d 2026-11-27T00:45:12Z

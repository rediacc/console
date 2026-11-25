# Review e8cecd5e: fix(vm-check): P4 accepts a stored token only on the dev gateway

Commit: e8cecd5e8dba524fcfa6eceb9bbeacd149c91aa9
Repo: console
Branch: 1121-1
Parent: f8657aa02320db8a9448e0e018ec5552633ed227
Patch-Id: c82171a8f7bccf0dac266d66220eec7fe6fc0024
Reviewed-At: 2026-11-25T12:59:41Z
Model: claude-haiku-5-5
Cost: $0.0045 USD, 1 call(s), 26.6s
Diff: 9576 bytes, 2 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=bug why=Fixes internal vm:check CI drill logic; no user-facing CLI change.
Dropped: 0
Body-Sig: 70c474c0265e9d23

## Findings

### e8cecd5e.1 [medium] .ci/rediacc_ci/drills/vm_check.py:2985
Anchor: in-diff
Claim: When the stored token is valid (rc 0) but the account server is not the dev gateway and the gateway is unhealthy, the NotVerifiedError says 'the stored token is refused', which is false: the token was accepted and only its server was wrong.
Class: doc-contradicts-code
Resolution: fixed 8b6b4ac1ec2b90e0d9e31771b4a27606afee3bde | d778be9d 2026-11-25T15:00:08Z

### e8cecd5e.2 [medium] .ci/rediacc_ci/drills/vm_check.py:3011
Anchor: in-diff
Claim: The port comparison and the VM-network-address acceptance in _stored_server_is_dev_gateway are new behaviour with no test: the only new test uses a production https host, so a loopback server on the wrong port or a config pointing at the VM-network address would be misclassified and nothing would fail.
Class: missing-control-test
Resolution: fixed 8b6b4ac1ec2b90e0d9e31771b4a27606afee3bde | d778be9d 2026-11-25T15:00:09Z

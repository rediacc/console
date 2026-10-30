# Review 82adcc34: fix(backup,tofu): a dangling removed-strategy timer is stopped best-effort with its enable link dropped; the IPv4 fallback also skips loopback, link-local and C

Commit: 82adcc34f293c8c62e9bbdef0e4d2df7da210cc4
Repo: console
Branch: 1023-1
Parent: 44451990cda035fd03a2dea416a29872266b99fc
Patch-Id: f9a7228c18d6e4ce1a52eaa97e5b43c19e382e3a
Reviewed-At: 2026-10-30T01:37:44Z
Model: claude-haiku-5-5
Cost: $0.0041 USD, 1 call(s), 39.7s
Diff: 9220 bytes, 4 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=patch kind=bug why=Fixes a dangling-timer cleanup path and widens the cherryservers IPv4 fallback exclusions; no new capability.
Dropped: 0
Body-Sig: aa12f05c607de06e

## Findings

### 82adcc34.1 [high] packages/cli/src/services/backup/backup-schedule-execute.ts:130
Anchor: in-diff
Claim: The combined command `systemctl stop ${unit}; rm -f ...; systemctl daemon-reload` returns only the exit code of its last command, so a failed stop is masked whenever daemon-reload succeeds. `exitCode !== 0` (line 133) then stays false and no warning is printed, which contradicts the commit's 'only warns on failure' contract for the exact case it targets.
Resolution: open

### 82adcc34.2 [medium] packages/cli/src/services/backup/__tests__/backup-schedule-execute.test.ts:70
Anchor: in-diff
Claim: The test titled 'a failure there only warns' never asserts that outputService.warn is called. Its mock returns 5 for the whole combined string, so it cannot detect the masked-exit-code bug in backup-schedule-execute.ts:130, and it would still pass if the warning were removed.
Resolution: open

### 82adcc34.3 [low] packages/cli/src/services/tofu/provider-registry.json:114
Anchor: in-diff
Claim: The new CGNAT alternation `100\\.(6[4-9]|[7-9][0-9]|1[01][0-9]|12[0-7])\\.` is correct for 100.64/10, but the test only checks 100.64.3.3, so boundary regressions at 100.63.x (public) and 100.128.x (public) would go unnoticed.
Resolution: open

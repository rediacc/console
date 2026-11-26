# Review 9dcf94c3: fix(cli): rdc tools install rsync writes etc/fstab so /c/... paths resolve (B4)

Commit: 9dcf94c378cb1fd20a75a5be2b1df2b8a3fae65d
Repo: console
Branch: 1121-1
Parent: 8d87920a181a3254c354bf3f2d931ecfe11bea9b
Patch-Id: 50def627def578d72b2be9258d2390f6739f29dc
Reviewed-At: 2026-11-26T20:44:34Z
Model: claude-haiku-5-5
Cost: $0.0027 USD, 1 call(s), 14.8s
Diff: 6699 bytes, 2 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=patch kind=bug why=Fixes rdc /c/... path resolution on Windows by writing MSYS2 fstab and nsswitch config; no new capability.
Dropped: 0
Body-Sig: 28b5728cd209d121

## Findings

### 9dcf94c3.1 [low] packages/cli/src/services/tools/rsync.ts:72
Anchor: in-diff
Claim: The doc comment on ensureMsys2RootDirs says it only creates the etc, tmp and dev directories, but the function now also writes etc/fstab and etc/nsswitch.conf, so the comment no longer describes what the function does.
Class: doc-contradicts-code
Resolution: open

### 9dcf94c3.2 [low] packages/cli/src/services/tools/__tests__/rsync-install.test.ts:242
Anchor: in-diff
Claim: The repair test checks that an existing etc/fstab is kept and a missing one is re-created, but no test covers the same keep-or-create behaviour for etc/nsswitch.conf, so a regression in that loop entry would pass.
Class: missing-control-test
Resolution: open

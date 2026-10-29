# Review d460d0f0: test(chunkstore): key rotation on a real LUKS2 image keeps payload cells, and a reencrypt reseeds fully (PLAN-backup-program K9)

Commit: d460d0f07fde94eaabbcfddab6805a9f5c5b15de
Repo: private/renet
Branch: 1023-1
Parent: 3c2ff5c3571b57bf36f8e5e1d295d8d48574bf61
Patch-Id: 4f3f163833ad6d1775374bcc18153fb793611aa6
Reviewed-At: 2026-10-28T15:12:45Z
Model: claude-haiku-5-5
Cost: $0.0060 USD, 1 call(s), 34.5s
Diff: 6457 bytes, 1 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=ci why=Test-only file added under btrfs/linux build tags; no runtime or user-facing change.
Dropped: 0
Body-Sig: eb8e135124e64d77

## Findings

### d460d0f0.1 [low] pkg/chunkstore/key_rotation_luks_test.go:85
Anchor: in-diff
Claim: The write loop keeps only the last WriteAt error in werr, overwriting earlier ones, so a failure on an early cell can be hidden if a later write succeeds; the test then fails with a less specific error or none at all.
Resolution: fixed 2f196307a808e5b76179719732d68e292bbc37cc | d778be9d 2026-10-29T22:30:34Z

### d460d0f0.2 [low] pkg/chunkstore/key_rotation_luks_test.go:91
Anchor: in-diff
Claim: The error from dev.Close() is discarded with `_ =`, so a flush failure on the device-mapper handle would go unreported before the mapping is closed and the snapshot is taken from a possibly incomplete write.
Resolution: fixed 2f196307a808e5b76179719732d68e292bbc37cc | d778be9d 2026-10-29T22:30:34Z

### d460d0f0.3 [low] pkg/chunkstore/key_rotation_luks_test.go:82
Anchor: in-diff
Claim: The opened mapping is closed by explicit calls only, not via t.Cleanup; a panic or runtime.Goexit between open and close leaks the fixed name k9-keyrot-probe, and the next run then fails at the cryptsetup open on line 78.
Resolution: fixed 2f196307a808e5b76179719732d68e292bbc37cc | d778be9d 2026-10-29T22:30:34Z

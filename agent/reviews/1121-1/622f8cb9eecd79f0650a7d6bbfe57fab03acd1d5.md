# Review 622f8cb9: feat(renet): add the fentry file-open hook for Full-level forensics capture

Commit: 622f8cb9eecd79f0650a7d6bbfe57fab03acd1d5
Repo: private/renet
Branch: 1121-1
Parent: 91972d08dfa6c4b737eec77c05912298de893fe4
Patch-Id: 81aa680139ac06a9c02439ea935575375cd3d589
Reviewed-At: 2026-11-23T18:15:54Z
Model: claude-haiku-5-5
Cost: $0.0101 USD, 1 call(s), 50.8s
Diff: 31319 bytes, 11 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=minor kind=feature why=Adds a new Full-level file-open capture hook and its loader; new capability, no user-facing fix.
Dropped: 0
Body-Sig: 7635678d0114b47f

## Findings

### 622f8cb9.1 [medium] pkg/ebpf/fileopen.c:180
Anchor: in-diff
Claim: The dedupe key is (cgroup, inode, pid) with no device or superblock id, so two different regular files on different filesystems that share an inode number, opened by the same pid in the same cgroup within 60 s, produce one event and the second file's open is silently lost.
Class: other
Resolution: open

### 622f8cb9.2 [low] pkg/ebpf/fileopen_root_test.go:160
Anchor: in-diff
Claim: TestFileOpen_StandardLevelRecordsNothing asserts zero events with no positive control in the same run, so it still passes if the hook never fires at all (for example if the open never reaches the program), and its 300 ms sleep is the only wait before the check.
Class: missing-control-test
Resolution: open

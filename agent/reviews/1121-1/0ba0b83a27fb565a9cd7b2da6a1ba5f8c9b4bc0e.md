# Review 0ba0b83a: fix(cli): orphan executor join matches a GUID-less event on the orphan's archived name

Commit: 0ba0b83a27fb565a9cd7b2da6a1ba5f8c9b4bc0e
Repo: console
Branch: 1121-1
Parent: c7d516e565bbb826d520592ec62af1e5fddf6e42
Patch-Id: 8ea82224f2c1fff6a256a8c2dfd6660748ea679c
Reviewed-At: 2026-11-24T09:38:44Z
Model: claude-haiku-5-5
Cost: $0.0035 USD, 1 call(s), 19.9s
Diff: 10143 bytes, 2 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=patch kind=bug why=Fixes orphan executor join: name fallback and machine filtering for executor events.
Dropped: 0
Body-Sig: a5d8b7efc424efa0

## Findings

### 0ba0b83a.1 [medium] packages/cli/src/services/repo/orphan-repos.ts:207
Anchor: in-diff
Claim: The GUID-less fallback compares the event's repo name with row.name, but row.name is composeRef(record.name, record.tag), which the interface doc says is `name:tag` when a tag exists; so a GUID-less event for an orphan whose archived record has a tag never matches, and the orphan keeps its old reason. The tests only use an untagged name ('alpha'), so this path is not covered.
Class: other
Resolution: open

### 0ba0b83a.2 [medium] packages/cli/src/services/repo/orphan-repos.ts:92
Anchor: in-diff
Claim: classifyMachineRepos now fills `name` from the new archivedNames() lookup (listArchivedRepositories, lowercase GUID keying, composeRef), but no test in this diff exercises that population; every test builds the rows by hand with a literal name, so a broken archivedNames() or name assignment would not fail any test in this commit.
Class: missing-control-test
Resolution: open

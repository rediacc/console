# Review 9025fddf: fix(guards): the last hand-rolled git readers in .claude move onto shellscan, closing nine more bypasses

Commit: 9025fddffb07cd6cfa2ce9edc07456b4e1705bae
Repo: console
Branch: 1007-1
Parent: ea3f50ccd09dbee3cc90b219ef6af7732b2058e5
Patch-Id: 4c2b9c77a7a8ee1dcb6659a714fabbb2ece61a62
Reviewed-At: 2026-10-07T11:38:29Z
Model: claude-haiku-4-5-20251001
Cost: $0.2162 USD, 1 call(s), 219.9s
Diff: 106981 bytes, 18 files, truncated: yes
Unreviewed: .claude/rediacc_hooks/tests/goldens/block_unlinked_commit_author.jsonl
Verdict: findings
Attempt: 1
Labels: bump=patch kind=bug why=Guard bypass when walk cannot parse pushes; allows refspec-less tags-only pushes to pass even when walk is incomplete, though impact is limited since true --tags-only pushes are safe.
Dropped: 0
Body-Sig: 2dfbc83dcfbc8b98

## Findings

### 9025fddf.1 [medium] .claude/rediacc_hooks/guards/block_push_to_protected_branch.py:421
Anchor: in-diff
Claim: The TAGS_ONLY check uses `all(_tags_only(r) for r in pushes)` which returns True vacuously when pushes is empty, allowing any command matching the `--tags` regex text even if the walk found no pushes. This fails open: if the walk cannot parse a push, the guard still allows it based on the regex alone, bypassing the intended fallback-to-regex-only safety check.
Resolution: fixed 8ba89fd58721a5739d9e4a572cf83b477c293593 | d778be9d 2026-10-07T12:06:09Z

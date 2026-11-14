# Review ba6e8fc4: chore(hooks): tidy the tombstone control

Commit: ba6e8fc417abfbdfb5202a166fc21714feed37bf
Repo: console
Branch: 1104-1
Parent: 92e9779361326c26aa42d8e909bdab7c82194988
Patch-Id: a55e179533ce6d5e7ab212facea83610240fd08e
Reviewed-At: 2026-11-04T08:20:31Z
Model: claude-haiku-5-5
Cost: $0.0010 USD, 1 call(s), 10.2s
Diff: 1372 bytes, 1 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=ci why=Test-hook helper and comment tidy only; no user-facing change.
Dropped: 0
Body-Sig: 43b2afbf30cd2023

## Findings

### ba6e8fc4.1 [low] .claude/hooks/stop/test-planindex.py:443
Anchor: in-diff
Claim: The stub's signature changes from `tracked_only=False` to `**_kwargs`, so a positional second argument (`_records(root, True)`) now raises TypeError, and any misspelled keyword passed by refresh_index is silently swallowed; neither case is covered by the diff's checks, though the 71-check run reportedly passed.
Resolution: not-a-bug | .claude/hooks/stop/test-planindex.py:443 refresh_index passes only the keyword, and this stub is the test's own | d778be9d 2026-11-04T08:22:14Z

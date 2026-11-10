# Review de1096fc: test(hooks): warn_writer_brief budget checks run on a fake clock

Commit: de1096fcfb6c9ee26dfee2dbbca0393d34b6ed9d
Repo: console
Branch: 1104-1
Parent: 7b476e17711b6620856858105baf17b076e585e7
Patch-Id: 1983ea99fae66acd6e0ae1103225d02aecebb5e0
Reviewed-At: 2026-11-10T15:52:34Z
Model: claude-haiku-5-5
Cost: $0.0034 USD, 1 call(s), 23.7s
Diff: 5477 bytes, 1 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=bug why=Test-only flake fix moving budget cases to a fake clock; no user-facing change.
Dropped: 0
Body-Sig: a2d75214f0f60e13

## Findings

### de1096fc.1 [medium] .claude/rediacc_hooks/guards/test-warn_writer_brief.py:289
Anchor: in-diff
Claim: The _Fake class docstring says it 'sleeps `delay_git` on the listing', but the code now calls self.clock.advance(self.delay_git) and never sleeps, so the comment states the wrong behaviour for anyone reading the fake.
Class: doc-contradicts-code
Resolution: open

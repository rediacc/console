# Review bebb89ad: fix(ci-trace): GitHub's own 404 for main's workflow file proves a branch-only workflow

Commit: bebb89adc23f263cde9aad82bcc64c3e4c09cea3
Repo: console
Branch: 1023-1
Parent: 83dfdb272f31aa90d4fedd429475b0603b4838b2
Patch-Id: 05293fe5e00ee4748838464bf51d462dcfb0263f
Reviewed-At: 2026-10-24T10:44:05Z
Model: claude-haiku-5-5
Cost: $0.0054 USD, 1 call(s), 40.4s
Diff: 6626 bytes, 2 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=bug,ci why=Fixes developer CI-trace hook tooling only; no product-facing change.
Dropped: 0
Body-Sig: 8cb8063437e8be20

## Findings

### bebb89ad.1 [medium] .claude/hooks/stop/wl_schedred.py:264
Anchor: in-diff
Claim: The new check treats any HTTP 404 from the contents API as proof the file is absent on main, but GitHub also returns 404 to a token that can read Actions yet lacks Contents read on a private repo. For a workflow that main does carry, the nightly then becomes a silent not_on_main row with red=False, hiding a RED run, and no test pins this case.
Resolution: fixed ce8c3fe1ce1ce1ac013db90dcc21c52e6a2847af | d778be9d 2026-10-24T10:48:59Z

### bebb89ad.2 [low] .claude/hooks/stop/wl_schedred.py:260
Anchor: in-diff
Claim: Each branch-only workflow now costs one extra uncached gh API call on every refresh of the scheduled read, so the fallback path adds API rate-limit pressure in proportion to the number of such workflows.
Resolution: fixed ce8c3fe1ce1ce1ac013db90dcc21c52e6a2847af | d778be9d 2026-10-24T10:48:59Z

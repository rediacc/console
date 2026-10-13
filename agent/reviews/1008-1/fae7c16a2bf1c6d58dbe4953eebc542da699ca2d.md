# Review fae7c16a: fix(hooks): guards take the project root from the event, scratch prune prints undecodable names, the basetemp exemption needs pytest's shape, and a foreign cwd

Commit: fae7c16a2bf1c6d58dbe4953eebc542da699ca2d
Repo: console
Branch: 1008-1
Parent: 0c06c48c4e65764c980f448f483d9eff737ce469
Patch-Id: 6024607bc1b5bdd21687a0eb0123aa726da217f7
Reviewed-At: 2026-10-11T12:21:04Z
Model: claude-haiku-5-5
Cost: $0.0140 USD, 1 call(s), 79.5s
Diff: 39508 bytes, 9 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=patch kind=bug why=Hook guard fix: tightens and corrects scope judgement for foreign-cwd commands and makes the prune listing print undecodable names safely.
Dropped: 0
Body-Sig: 4d1d151eb6efcd62

## Findings

### fae7c16a.1 [medium] .claude/rediacc_hooks/guards/block_destructive_git_restore.py:925
Anchor: in-diff
Claim: The new early `return None` sits before the function's final `return walked`, so a non-wide walked refusal already computed above is discarded whenever `_all_foreign` is true; e.g. from a cwd inside another repo, `git submodule foreach 'git -C <absolute checkout path> reset --hard'` has its top-level invocation resolve outside and is allowed, and no test pins a nested payload from a foreign cwd.
Resolution: fixed 88ab93d6a95838c0eda30eea334f2b029e4089de | d778be9d 2026-10-11T12:39:46Z

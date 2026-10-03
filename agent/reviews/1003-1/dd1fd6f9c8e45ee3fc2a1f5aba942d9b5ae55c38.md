# Review dd1fd6f9: fix(hooks): a judge sample that ends its turn without the object is retried, not reported as a broken gate

Commit: dd1fd6f9c8e45ee3fc2a1f5aba942d9b5ae55c38
Repo: console
Branch: 1003-1
Parent: 068dbb7b668079f494711b50a7528788cc937474
Patch-Id: bdd7ea292e33f310e7f2027f8ef02b174bed5b10
Reviewed-At: 2026-10-03T16:47:58Z
Model: claude-haiku-4-5-20251001
Cost: $0.0487 USD, 1 call(s), 74.4s
Diff: 5547 bytes, 2 files, truncated: no
Unreviewed: (none)
Verdict: clean
Attempt: 1
Labels: bump=patch kind=bug why=Fixes incorrect handling of samples that end their turn without producing a structured object -- now correctly retried instead of reported as gate failures
Dropped: 0
Body-Sig: e3b0c44298fc1c14

## Findings

(none)

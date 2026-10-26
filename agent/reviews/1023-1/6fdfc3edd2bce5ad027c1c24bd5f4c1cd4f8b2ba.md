# Review 6fdfc3ed: fix(drills): the U1 namespace guard fails closed and G1.7 reads MainPID before touching the stamp

Commit: 6fdfc3edd2bce5ad027c1c24bd5f4c1cd4f8b2ba
Repo: console
Branch: 1023-1
Parent: d7cb08f176a4637557f0a296b1e374159650a4ff
Patch-Id: cb5a9e3e983b65d248fc58bdaf361f4e418c0804
Reviewed-At: 2026-10-26T21:38:33Z
Model: claude-haiku-5-5
Cost: $0.0050 USD, 1 call(s), 38.4s
Diff: 6473 bytes, 4 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=bug why=Changes only the .ci drill harness (test tooling), not shipped product behaviour; fixes a fail-open namespace guard and a stamp-before-check ordering.
Dropped: 0
Body-Sig: c6531ecd508fcd54

## Findings

### 6fdfc3ed.1 [low] .ci/rediacc_ci/tests/test_drills_upgrade_converge.py:227
Anchor: in-diff
Claim: The new fail-closed test only checks that the guard's text appears in the generated script; it never runs the shell with an unreadable namespace, so a wrong guard that still contains these substrings would pass.
Resolution: fixed 002e129a042567b94e05643540401f480f6961fa | d778be9d 2026-10-26T21:43:48Z

### 6fdfc3ed.2 [low] .ci/rediacc_ci/drills/upgrade_converge.py:82
Anchor: in-diff
Claim: The docstring still describes only the host-namespace refusal and does not mention that an unreadable /proc namespace link is now also refused as HOSTNS; the behaviour is documented only in the inline comment at line 90.
Resolution: fixed 002e129a042567b94e05643540401f480f6961fa | d778be9d 2026-10-26T21:43:48Z

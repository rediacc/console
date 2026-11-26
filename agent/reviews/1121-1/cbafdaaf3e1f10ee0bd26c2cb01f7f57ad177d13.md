# Review cbafdaaf: fix(stop-hook): name the failure where nine modules read a broken read as no data

Commit: cbafdaaf3e1f10ee0bd26c2cb01f7f57ad177d13
Repo: console
Branch: 1121-1
Parent: ee55dfaec6d4e61a86578d3cf71b6dd6abdc79f1
Patch-Id: 8537b6156e3f379b731826e4489d4c366b2cc66a
Reviewed-At: 2026-11-23T06:48:59Z
Model: claude-haiku-5-5
Cost: $0.0095 USD, 1 call(s), 56.1s
Diff: 36756 bytes, 12 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=patch kind=bug why=Stop-hook failures are now named in advisory text instead of read as empty data; no new block.
Dropped: 0
Body-Sig: ae5e6bfaccf04e40

## Findings

### cbafdaaf.1 [medium] .claude/hooks/stop/wl_planenforce.py:251
Anchor: in-diff
Claim: The evaluate docstring still says every read failure 'degrades to silence', but when all of a PR's plans fail to parse this commit now returns ADVISORY with the unparsed text, not SILENT, so the stated behaviour is wrong.
Class: doc-contradicts-code
Resolution: open

### cbafdaaf.2 [low] .claude/rediacc_hooks/tests/test_wl_silent_a.py:170
Anchor: in-diff
Claim: test_handover_names_an_unreadable_lease leaves handover.UNREADABLE['lease-1'] set (the module-level dict written by lease_landed) and nothing resets it, so a later test in the same process that injects a None state for 'lease-1' would receive a stale 'could not be read' reason.
Class: seam-not-restored
Resolution: fixed 5fb22d3cdf4c2a96a8735a632ce1f1c0f05958e2 | d778be9d 2026-11-26T17:58:05Z

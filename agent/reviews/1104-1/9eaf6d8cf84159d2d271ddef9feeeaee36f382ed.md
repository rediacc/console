# Review 9eaf6d8c: fix(ops): ops-health repair ledger, source names and status read hold to what their docs say

Commit: 9eaf6d8cf84159d2d271ddef9feeeaee36f382ed
Repo: console
Branch: 1104-1
Parent: 891cacd39b6486bd72aeea347c7fe41a10d1f507
Patch-Id: 838256dab5d9dd83c17e110385fc1dd4bfbf8ecf
Reviewed-At: 2026-11-07T11:57:09Z
Model: claude-haiku-5-5
Cost: $0.0084 USD, 1 call(s), 53.8s
Diff: 20350 bytes, 5 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=bug why=Internal ops CI tooling fixes (ledger source names, status read errors); no user-facing product change.
Dropped: 0
Body-Sig: fc490bd649cdb41b

## Findings

### 9eaf6d8c.1 [medium] .ci/rediacc_ci/ops/deploy_ops_health.py:360
Anchor: in-diff
Claim: fetch_deployed still returns None (first deploy) for any TimeoutError or OSError raised inside https.urlopen, which includes a stall after TCP/TLS connect while the Worker is waiting to send headers; the docstring says a stall is never a first deploy, so a hung live Worker gets every secret re-put and a create deploy run over it.
Resolution: open

### 9eaf6d8c.2 [low] .ci/rediacc_ci/ops/deploy_ops_health.py:355
Anchor: in-diff
Claim: An http.client.HTTPException such as BadStatusLine raised by https.urlopen on a live but malformed reply is not caught (it is not an OSError or URLError), so it escapes as a raw traceback instead of StatusUnreadableError, contrary to the 'any other answer ... stops the run' contract the docstring states.
Resolution: open

### 9eaf6d8c.3 [medium] .ci/rediacc_ci/tests/test_ops_health.py:819
Anchor: in-diff
Claim: test_two_pairs_that_spell_one_source_name_keep_both_verdicts uses machines b-c and c that are each held by only one config, so machine_sources never joins or hashes them; the names are local-machine-b-c and local-machine-c, so the test passes with the collision handling removed and does not pin the behaviour its name claims.
Resolution: open

### 9eaf6d8c.4 [low] .ci/rediacc_ci/tests/test_ops_health_deploy.py:343
Anchor: in-diff
Claim: test_a_body_of_invalid_utf8 sends b'\xff\xfe{', which json.loads reads as a UTF-16 BOM and fails on odd length, not as invalid UTF-8, so the test name overstates what it covers (a body such as b'{\xff' would be the real UTF-8 case).
Resolution: open

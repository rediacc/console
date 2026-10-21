# Review a476bc84: feat(hooks): the Stop hook orders /wisdom past 92% of auto-compact, and /wisdom hands in-flight work to sub-agents with full briefs

Commit: a476bc84084b7fcebeb73abb3d8faad6cf9823c3
Repo: console
Branch: 1020-1
Parent: d47c66ccb36122dd4f666d34bb53c3f63b956835
Patch-Id: 49860ebfa92e1810ccdf03ca08372c629b104776
Reviewed-At: 2026-10-21T09:30:24Z
Model: claude-haiku-5-5
Cost: $0.0108 USD, 1 call(s), 68.2s
Diff: 28193 bytes, 10 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=minor kind=feature why=Adds a new always-tier Stop-hook check, a model-invocable /wisdom command and a new effort row, which are new capabilities.
Dropped: 0
Body-Sig: 8c9da3846d811e1e

## Findings

### a476bc84.1 [medium] .claude/hooks/stop/wl_checks.py:2653
Anchor: in-diff
Claim: wisdom_due clears on any rewrite after the crossing as long as STATE.md contains a '## Delegated' heading, so a rewrite past 92% that carries an earlier context's section over clears wisdom-due with no new delegation, contrary to the docstring and commit message.
Resolution: fixed e20b3ceccd0f12ebc9cd28a3a18b98a019d30526 | d778be9d 2026-10-21T09:39:13Z

### a476bc84.2 [medium] .claude/commands/wisdom.md:4
Anchor: in-diff
Claim: allowed-tools omits the git add/commit, worklist.py --lease/--update/--add/--state and wl_wake.py calls that steps 2, 4, 5 and 6 require, so if those Bash calls are denied the always-tier wisdom-due block cannot be cleared.
Resolution: fixed e20b3ceccd0f12ebc9cd28a3a18b98a019d30526 | d778be9d 2026-10-21T09:39:13Z

### a476bc84.3 [low] .claude/rediacc_hooks/tests/test_wl_wisdom.py:98
Anchor: in-diff
Claim: test_w3_twin reuses the DELEGATED fixture from an earlier context and asserts it clears the block, so the suite encodes the stale-section clearance and cannot catch the case above.
Resolution: fixed e20b3ceccd0f12ebc9cd28a3a18b98a019d30526 | d778be9d 2026-10-21T09:39:13Z

### a476bc84.4 [low] .claude/hooks/context/ctx_budget.py:73
Anchor: in-diff
Claim: The comment says 92% leaves about 77,000 'on a 1M window', but 8% of the 967,000 threshold is 77,360 and 8% of the 1M window is 80,000; the figure is for the threshold, not the window.
Resolution: fixed e20b3ceccd0f12ebc9cd28a3a18b98a019d30526 | d778be9d 2026-10-21T09:39:14Z

### a476bc84.5 [low] .claude/hooks/stop/wl_checks.py:2668
Anchor: in-diff
Claim: wisdom_due returns an empty string on any exception, so an always-tier check fails silently open whenever the band state or STATE.md read raises.
Resolution: not-a-bug | .claude/hooks/stop/wl_checks.py:2625 _ctx_late_band returns False on any exception too; the Stop hook fails open by design so a broken read never wedges every stop | d778be9d 2026-10-21T09:39:14Z

### a476bc84.6 [low] .claude/hooks/stop/worklist_messages.py:2856
Anchor: in-diff
Claim: V_WISDOM_DUE asks each STATE.md line to hold 'agent id, item id, what it owns', while wisdom.md step 5 (line 32) asks for 'agent id, item id, files owned, acceptance check', so the two instructions disagree on the required fields.
Resolution: fixed e20b3ceccd0f12ebc9cd28a3a18b98a019d30526 | d778be9d 2026-10-21T09:39:14Z

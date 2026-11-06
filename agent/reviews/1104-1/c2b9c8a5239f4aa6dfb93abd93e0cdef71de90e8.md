# Review c2b9c8a5: fix(wl-report): lead names match in any case, agent ids refuse a trailing newline, section headings in a payload are escaped

Commit: c2b9c8a5239f4aa6dfb93abd93e0cdef71de90e8
Repo: console
Branch: 1104-1
Parent: d7a5dc6854fd4ab034a398daa42417cebcb5d3bc
Patch-Id: 08999bfccf0d06185e02b187d3b0bc778729e400
Reviewed-At: 2026-11-06T22:21:20Z
Model: claude-haiku-5-5
Cost: $0.0050 USD, 1 call(s), 30.6s
Diff: 13590 bytes, 3 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=bug why=Fixes a worklist report hook under .claude/ (internal tooling, not a shipped product feature); no user-facing release change.
Dropped: 0
Body-Sig: 4b509529a2f44ca6

## Findings

### c2b9c8a5.1 [medium] .claude/hooks/stop/wl_report.py:1206
Anchor: in-diff
Claim: assemble_body escapes only the payload message and the final text, but writes s["summary"] unescaped into the section head (`head += "\n_%s_" % s["summary"]`), so a summary containing a newline followed by a `## Outgoing N -> x` or `## Final message` line still splits the section on read-back.
Resolution: open

### c2b9c8a5.2 [low] .claude/hooks/stop/wl_report.py:1194
Anchor: in-diff
Claim: _defang prepends a backslash to each heading-like line, and nothing in the diff reverses it on read; the new test only checks that "not final" survives, so a payload line `## Outgoing 1 -> x` is returned as `\## Outgoing 1 -> x` with no test pinning the round-trip text (unless body_parts, which is not in this diff, strips it).
Resolution: open

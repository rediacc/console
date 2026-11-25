# Review 4ab1dce5: feat(shared): regulatory field map for the incident report

Commit: 4ab1dce546dd9b7840c90def2ce73bdf47a55afd
Repo: console
Branch: 1121-1
Parent: 4474dcde99a38280b00b894255c3864bd7537018
Patch-Id: ab4329d6fafb329f6d42e39c5c9f6d61614f9fd7
Reviewed-At: 2026-11-25T17:47:00Z
Model: claude-haiku-5-5
Cost: $0.0050 USD, 1 call(s), 29.5s
Diff: 12901 bytes, 3 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=feature why=New internal shared incident module with a loader; no user-facing change.
Dropped: 0
Body-Sig: 4f13daa2c72540bc

## Findings

### 4ab1dce5.1 [low] packages/shared/src/incident/__tests__/report-field-map.test.ts:41
Anchor: in-diff
Claim: The assertion expect(regimeMapping(path, regime.id)).toBeDefined() cannot fail independently: REPORT_FIELD_MAP is parsed at module load, so any missing row already throws at import, and the test adds no check the loader does not already make.
Class: missing-control-test
Resolution: open

### 4ab1dce5.2 [low] packages/shared/src/incident/report-field-map.json:5
Anchor: in-diff
Claim: The regime name cites 'the NIS Cooperation Group reporting templates of 26 May 2026', but the url and retrievedAt for that regime point at the Directive's OJ page, so the stated retrieval date does not cover the templates the name refers to.
Class: other
Resolution: open

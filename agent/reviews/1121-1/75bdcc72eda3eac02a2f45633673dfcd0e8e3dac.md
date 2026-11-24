# Review 75bdcc72: feat(legal): version 2026-11-24 for the privacy policy and the DPA

Commit: 75bdcc72eda3eac02a2f45633673dfcd0e8e3dac
Repo: console
Branch: 1121-1
Parent: 6453becc7da59fd9e979d171f76afb7ea9cc6c9b
Patch-Id: 64926c7ad0596c9141695de9933b1603910bd26f
Reviewed-At: 2026-11-24T03:43:53Z
Model: claude-haiku-5-5
Cost: $0.0038 USD, 1 call(s), 14.7s
Diff: 23298 bytes, 4 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=patch kind=docs why=Legal text and version metadata update only; no code behaviour change.
Dropped: 0
Body-Sig: 9b63eb3cf217d5d3

## Findings

### 75bdcc72.1 [low] packages/www/public/legal/archive/privacy-policy-2026-11-24.txt:2
Anchor: in-diff
Claim: The archived 2026-11-24 text states 'Effective Date: November 11, 2026', but the version record in legal-documents.json and documents.generated.ts gives effective 2026-12-24, so the published text and its metadata disagree on when it takes effect.
Class: doc-contradicts-code
Resolution: open

### 75bdcc72.2 [low] packages/www/public/legal/archive/data-processing-agreement-2026-11-24.txt:2
Anchor: in-diff
Claim: The archived 2026-11-24 DPA states 'Effective Date: November 11, 2026', but the version record gives effective 2026-12-24, so the document text and the metadata disagree on the effective date.
Class: doc-contradicts-code
Resolution: open

### 75bdcc72.3 [low] packages/www/public/legal/archive/privacy-policy-2026-11-24.txt:68
Anchor: in-diff
Claim: The telemetry bullet says telemetry goes to 'our own telemetry endpoint' and that 'No telemetry data is shared with third parties', while the DPA in the same commit lists Hostinger as a subprocessor hosting otlp.rediacc.io, which receives Telemetry Data.
Class: other
Resolution: open

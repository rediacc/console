# Review cd64926e: fix(cli): print subscription status and the backup strategy estimate on stdout

Commit: cd64926ebe8f6e2d8a9b3eaedeea4b672e17c53e
Repo: console
Branch: 1104-1
Parent: 2c6d60240fd4d8b41d342b8a096a7bf46c722ae0
Patch-Id: bc5503210b8b7b0e6400f807f46a4427a4326f92
Reviewed-At: 2026-11-10T19:16:32Z
Model: claude-haiku-5-5
Cost: $0.0057 USD, 1 call(s), 22.5s
Diff: 34004 bytes, 10 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=patch kind=bug why=Routes CLI result prose to stdout so pipes capture it; a bug fix with no new capability.
Dropped: 0
Body-Sig: c3521edcdfc81597

## Findings

### cd64926e.1 [high] packages/cli/src/commands/subscription-repo-table.ts:12
Anchor: in-diff
Claim: renderRepoLicenseTable now calls outputService.report unconditionally, so under -o json (job-plan-misc.test.ts mocks getOutputFormat to 'json' and expects outReport to receive the repo.status.entry line) the prose table goes to stdout and corrupts the JSON result that previously stayed clean on stdout via info (stderr).
Class: other
Resolution: not-a-bug | packages/cli/src/services/core/output.ts:366 fixed at the callee in 6d47b5720e: renderRepoLicenseTable keeps calling outputService.report, and report() now writes to stderr under json, yaml or csv (output-report.test.ts covers -o json/yaml/csv and the dispatch buffer); the table file needed no change | d778be9d 2026-11-10T19:26:30Z

### cd64926e.2 [low] packages/cli/src/commands/subscription-output.ts:54
Anchor: in-diff
Claim: The activation 'active' line changed from outputService.success to outputService.report, dropping the success styling with no comment or doc note; the test only asserts the call moved, not that the output format is preserved.
Class: other
Resolution: not-a-bug | packages/cli/src/commands/subscription-output.ts:46 the active line is part of the status result, which report() prints as plain text on stdout so a pipe or redirect captures it; success() styling targets stderr progress, and a coloured result on stdout would put escape codes into captured output | d778be9d 2026-11-10T19:30:21Z

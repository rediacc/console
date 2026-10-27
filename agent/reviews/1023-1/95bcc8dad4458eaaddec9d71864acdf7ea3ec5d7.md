# Review 95bcc8da: fix(serve): the executor's config pull sends x-config-envelope

Commit: 95bcc8dad4458eaaddec9d71864acdf7ea3ec5d7
Repo: console
Branch: 1023-1
Parent: 4cd6f4c4434655208fc748d8251a71f15d909129
Patch-Id: 7fb5ecd629a1068a48d902402a11f9aeb2284702
Reviewed-At: 2026-10-27T06:31:22Z
Model: claude-haiku-5-5
Cost: $0.0016 USD, 1 call(s), 11.5s
Diff: 4271 bytes, 3 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=patch kind=bug why=Fixes the executor's config pull so it is no longer refused with 426 under the v3 envelope requirement; no new capability.
Dropped: 0
Body-Sig: cb4c7d436e93147e

## Findings

### 95bcc8da.1 [low] packages/cli/src/services/serve/container-config.ts:164
Anchor: in-diff
Claim: The new header is written as 'x-config-envelope' while the adjacent header in the same object is 'X-Config-Token'. Header names are case-insensitive on the wire, so behaviour is unaffected, but the two names in one literal now use different casing.
Resolution: not-a-bug | packages/cli/src/services/config/config-server-client.ts:97 the CLI already spells the header lowercase, so container-config matches the one other sender; header names are case-insensitive on the wire | d778be9d 2026-10-27T07:05:03Z

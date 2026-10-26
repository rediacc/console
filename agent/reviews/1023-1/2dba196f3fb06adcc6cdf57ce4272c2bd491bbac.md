# Review 2dba196f: fix(ci): the live-console profile binds the scoped CD token, not the Global API Key, and the plan records name the round-4 result

Commit: 2dba196f3fb06adcc6cdf57ce4272c2bd491bbac
Repo: console
Branch: 1023-1
Parent: eb02c1a87b5c7830b95ea3087c9e2400eaf8a903
Patch-Id: 05de9720509f65b7ed19b5aa7d540ece774b9e78
Reviewed-At: 2026-10-26T23:03:40Z
Model: claude-haiku-5-5
Cost: $0.0099 USD, 1 call(s), 51.9s
Diff: 39061 bytes, 7 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=docs,ci why=Changes CI secret-supply profile and plan records only; no user-facing behaviour changes.
Dropped: 0
Body-Sig: 483e959086b8b48c

## Findings

### 2dba196f.1 [medium] .ci/config/secret-supply.json:417
Anchor: in-diff
Claim: The live-console why says the D1 audit read runs through wrangler with the scoped CD token, measured 2026-10-27, but the commit message says that measurement ran under --profile deploy-workers; nothing in the diff shows the live-console path reading D1 with CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID.
Resolution: fixed 47f00c30eb60594e432c30c8c1a05075a440eaa0 | d778be9d 2026-10-26T23:08:17Z

### 2dba196f.2 [low] agent/plans/PLAN-console-executor-multi-org.md:291
Anchor: in-diff
Claim: The E1 spec bullet still says 'The profile gains the four names only', while the tick directly below says the profile gained more than four (six login and TOTP names plus store password, machine and D1 database), so the box text contradicts its own tick.
Resolution: not-a-bug | box text is never edited by a tick (plan-tick flips only the bracket; worklist.py --plan-tick refuses a text change), so the deviation is recorded in the tick evidence at agent/plans/PLAN-console-executor-multi-org.md:292, which names the extra names and why (2FA) | d778be9d 2026-10-26T23:08:18Z

### 2dba196f.3 [low] agent/plans/PLAN-console-executor-multi-org.md:342
Anchor: in-diff
Claim: The ML0 'Live-console member logins' note still says the live-console profile binds only ROOT_EMAIL and no login secret is stored; after this commit the profile lists the org login and TOTP names, so the note states the old behaviour as current.
Resolution: fixed 47f00c30eb60594e432c30c8c1a05075a440eaa0 | d778be9d 2026-10-26T23:08:17Z

### 2dba196f.4 [low] agent/plans/PLAN-proxy-cd-six-targets.md:395
Anchor: in-diff
Claim: The revoke command recorded for the E1 probe key sets REDIACC_ALLOW_GRAND_REPO='*' to a wildcard before running sed on the remote authorized_keys; a reader copying this runbook line runs with that guard variable widened to every repo.
Resolution: not-a-bug | machine-level term connect (no repo) requires REDIACC_ALLOW_GRAND_REPO=* by design; a repo-name list does not unlock it (private/renet/CLAUDE.md:126, the "Run a command directly on the machine" row), and the variable is scoped to that one command | d778be9d 2026-10-26T23:08:18Z

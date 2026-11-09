# Review 1dfcd7f3: fix(proxy): the account Worker applies the allowlist too, and a malformed range matches nothing

Commit: 1dfcd7f371eea52f8e27d1b8de5eeaba02be9017
Repo: console
Branch: 1104-1
Parent: 16f57d6db92d38aa5bec33d7b7f01f440efbe87a
Patch-Id: f4fd21656b710b67352125e648de6d6d982e7b8a
Reviewed-At: 2026-11-09T02:32:58Z
Model: claude-haiku-5-5
Cost: $0.0039 USD, 1 call(s), 26.8s
Diff: 6882 bytes, 3 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=patch kind=bug why=Security fix: malformed allowlist ranges no longer match every address, and the account Worker now enforces the opt-in IP allowlist. No new capability; off unless ALLOW_IPS is set.
Dropped: 0
Body-Sig: 71d8b70569c5253f

## Findings

### 1dfcd7f3.1 [medium] workers/account/src/index.ts:128
Anchor: in-diff
Claim: The account Worker's fetch now returns 403 for any caller outside ALLOW_IPS, but no test in this diff exercises that path. The added tests cover only allowlistRefusal in the proxy, so a regression in the account gate or its header wrapping would not be caught.
Resolution: fixed b0a6e261a749d3e9633c466c88831dc883ec646e | d778be9d 2026-11-09T02:40:36Z

### 1dfcd7f3.2 [low] workers/proxy/src/ip-allowlist.ts:31
Anchor: in-diff
Claim: A well-formed prefix of 0 (e.g. `203.0.113.0/0` or `/00`) passes the new regex and bits check and matches every address, so a mistyped prefix still opens the allowlist; no test covers this case.
Resolution: fixed b0a6e261a749d3e9633c466c88831dc883ec646e | d778be9d 2026-11-09T02:40:36Z

### 1dfcd7f3.3 [low] workers/proxy/src/ip-allowlist.ts:51
Anchor: in-diff
Claim: The refusal log line changed from 'proxy: caller refused' to 'worker: caller refused'; any log query or alert keyed on the old prefix will silently stop matching after deploy.
Resolution: fixed b0a6e261a749d3e9633c466c88831dc883ec646e | d778be9d 2026-11-09T02:40:36Z

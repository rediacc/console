# Review 31d2c28c: docs(plans): PLAN-account-env-to-bws and PLAN-env-to-bitwarden-v2 close into _done

Commit: 31d2c28c3e277d5f4c8bcba40125e0bef1aaffea
Repo: console
Branch: 1008-1
Parent: 26466b9b22a64b25af8f3c2d80a685714ac1ce6c
Patch-Id: 429943cf49a372f846ba70e7814709ff6fba888a
Reviewed-At: 2026-10-08T07:33:54Z
Model: claude-haiku-5-5
Cost: $0.0093 USD, 1 call(s), 15.2s
Diff: 185116 bytes, 8 files, truncated: yes
Unreviewed: agent/plans/PLAN-env-to-bitwarden-v2.md, agent/plans/_done/PLAN-env-to-bitwarden-v2.md
Verdict: findings
Attempt: 1
Labels: bump=none kind=docs why=Plan moves, queue renumbering and regenerated ledgers only; no code or user-facing behaviour changes.
Dropped: 0
Body-Sig: 383a821a3a248ec3

## Findings

### 31d2c28c.1 [low] agent/plans/_done/PLAN-account-env-to-bws.md:9
Anchor: in-diff
Claim: The moved plan, now marked `Status: done`, still carries the seed header `Priority: P2 -- seed: Status draft, 1 open box(es)`, which contradicts the new status and the zero open boxes in plan-boxes.json.
Resolution: fixed 026b5c06601dec13a5fb5cd68225e5e22dc42bf2 | d778be9d 2026-10-08T07:37:50Z

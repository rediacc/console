## SESSION 74de73ca 2026-09-02T21:12:14Z

## OPERATOR IS AWAY AND HAS AUTHORIZED LANDING (2026-09-02)

Verbatim: *"Remove github secrets from github! I authorize! use gh cli tool. Then go for
/pr-babysit I'll not be around. So, you're alone. You can also set bitwarden secrets there.
don't worry about expire date... Also use cron for every 45 mins."*

### THE ORDER IS NOT OPTIONAL — read before deleting anything

`agent/PLAN-github-secrets-removal.md`: **the Bitwarden layer HAS NEVER RUN.** The composite
action is not in HEAD; not one of the 63 comparisons has executed. `gh secret` has no `get`,
so deletion is irreversible for the ~10% not recoverable (Stripe, Dockerhub, App key are
dashboard-or-reissue only). Deleting first would also break CI on the very PR being babysat.

**commit -> PR -> shadow runs for the FIRST time -> every compare step green -> THEN delete.**
The compare step fails on mismatch OR on either side empty, so a green run IS the proof.

## Next action, in order

1. **`#fce6882b`** — commit (account/renet/elite FIRST, then console with pointers bumped),
   push a branch, open ONE draft PR. `.claude/hooks/pre-bash/block-second-open-pr.sh` enforces
   one PR; `block-nondraft-pr-create` enforces draft.
2. **`#fd865ed1`** — 45-minute cron to catch CI errors that do not reproduce locally.
3. Babysit to green. Expect the shadow's first-ever execution to surface real mismatches;
   a mismatch is the gate working, not a flake.
4. **`#fbd35dba` — ONLY after green**: delete the 43 deletable org secrets with `gh`.
   `scripts/dev/rename-org-secrets.sh` is CANCELLED (Part 22) — do not run it.
5. **`#06f9fa63`** — setting Bitwarden secrets is authorized; token expiry is explicitly not a
   blocker, the operator will rotate later.
6. **`[>] #12b56f61`** — live calibration; do NOT record a `SHAPE_PROMPT` hash off a run that
   is not fully green.

## State of the tree (all uncommitted until step 1)

One gate red on purpose: `check:ci-secret-reachability` (record names OLD org secrets; moot
once they are deleted). All others green: `ci-bws-map` (assertions 1,5-9), `ci-workflow-gates`
(CHECK 1-4), `ci-greenlight-closures`, `ci-builder-env-contract`, `ci-worker-secret-names`,
`ci-actionlint`, `ci-workflows`, `ci-parity`, `ci-gate-manifest`, `ci-trap-registry`,
`ci-breakpoint-drift`, `ci-autopilot-bp-align`, shellcheck, python-lint, test-judge-schema,
and gate-tests bws-env / bws-map / workflow-contracts.

Built today: the secret rename APPLIED; assertions 5-9; CHECK 4 + `.github/external-callers.yml`;
`check:ci-greenlight-closures`; `.ci/lib/bws-env.sh` + its gate-test; `test-bws-map.sh`;
four guards on `secret-rename.py`. Recovered from my own dedupe that destroyed 26 workflow
files. Audit fixed a fail-OPEN production defect (edge deploy would have used the LIVE Stripe
key) and a total account-deploy failure (matrix missing three fields).

Five plans, none built: `PLAN-github-secrets-removal.md` (the sequencer),
`PLAN-env-to-bitwarden-v2.md`, `PLAN-secret-names-one-to-one.md`,
`PLAN-branch-aware-workflows.md`, `PLAN-secret-namespace-migration.md` Parts 17-22.

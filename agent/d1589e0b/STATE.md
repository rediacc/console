## SESSION d1589e0b 2026-09-05T11:05:28Z

# MERGED and on main. Chasing the edge release; 3 secrets need the OPERATOR

## Next action
Read worker **blumwhdqo** (`ci-trace.py --wait --until-final --ref main`) on
Console CI **33962302989**, head `d7b313a73`.

Green ⇒ it dispatches **Release to Edge**. Watch that BY RUN ID
(`ci-trace.py --run <id> --wait`), never by branch: a `workflow_dispatch` run's
check-runs are absent from the branch rollup, so `--ref main` reports GREEN while
the release is still mid-flight. Edge green ⇒ re-sync main (CD pushes two
`[skip ci]` commits back), then order #624e1863:
`gh workflow run "Release to Production" -f force=true`.

**Operator cap in force: at most 3 background workers.** Currently 2.

## Done and irreversible
PR #585 **MERGED 07:32:41Z**; all four stacked PRs landed. `main` went
`079edc5d4` → `35933a303` → **`d7b313a73`** (4 commits pushed directly to main,
which order #dfe46a93 authorises).

  c55d906f7  stale-comment class, 3 sites
  bdde69f1f  shadow drift record — THE RELEASE BLOCKER
  51b2f1064  killed-reset regression test (first test file for either ops module)
  d7b313a73  5 blank lines in ci-quality.yml

## THREE SECRETS NEED THE OPERATOR — nothing else can resolve them
Release to Edge `33955200168` failed in FOUR jobs (all 3 account regions +
marketing worker) on "Compare shadow secrets against GitHub". GitHub and
Bitwarden disagree, verdict `[content differs]`, on:
`ACCOUNT_BACKUP_S3_ACCESS_KEY_ID`, `ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY`,
`CLOUDFLARE_TURNSTILE_SECRET_KEY`.

The drift PRE-DATES the shadow: the last good edge deploy ran ZERO comparisons
(no `shadow <NAME> match|MISMATCH` line in its log at all) because those names
were first shadowed in `35933a303`. Nothing regressed.

GitHub secrets are write-only, so no session can read the other side to pick a
winner — `door: operator-only`. Recorded in
`.ci/config/shadow-expected-mismatches.json`; CD is unblocked but the values are
still wrong on one side.

**Trap that nearly cost a fake fix:** that JSON is DOCUMENTATION. The compare
reads `SHADOW_EXPECTED_MISMATCH`, a literal env var per workflow, and
`cd-deploy-account.yml` set it not at all. Editing the ledger alone changes
nothing. Both halves are wired now; `check_bws_map.py` assertion 12 binds them
bidirectionally.

## Local state
On `main`, clean of mine. Dirty and NOT mine, never stage: `package-lock.json`
(npm11 cosmetic flip), `agent/74de73ca/*`.

## Queue
**#dfe46a93** follow main (active) · **#624e1863** production release ·
**#10719055** cap steps 2-6 of `agent/PLAN-reggate-effort-cap.md` ·
**#76761e31** `wl_wait` wakes on every branch sub-agent report, no filter flag.

Ticked this phase: #0638d947, #a5d9f490, #5d223f33.

## Peers
`74de73ca` stopped and verified. `8f55d4f0` live on a large read-only audit
(~100 sub-agent reports); never ran `--brief` so it cannot be addressed
directly. Tree verified untouched at every check.

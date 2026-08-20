## SESSION e6500e92 2026-08-20T11:40:05Z

## What is true right now

Branch `0818-1`, PR **#569 OPEN, READY**. **Pushed: local HEAD == `origin/0818-1` ==
`37f6433a6`.** Working tree holds only OTHER sessions' live work (`.claude/hooks/**`,
`.claude/agents/**`) plus the cosmetic `package-lock.json` npm11 flip. **None of it is mine.**

Three PRs open, all linked in #569's body because the submodule gate REQUIRES the link:
console **#569**, account **#80** (`3cd870b`), renet **#104** (`c452df8`). `private/growth`
(NOT a submodule, gitignored) at `d231757`.

**Still owed:** `gh label delete no-media-quality` AND removing its entry from
`.github/labels.yml` -- `check-label-inventory.sh` compares both directions.

## CI `32364765277` on `37f6433a6`, in flight. Watch `byi8tz15e`.

**Every QUALITY gate has been green for several runs.** Only E2E infra has been red.

**Read the CONSOLE CI run by workflow name**, never the newest run on the branch (usually a
`Watchdog:` run). Distinguish the two cancelled shapes: **cancelled + ZERO failures + a newer
commit = SUPERSEDED** (my own push auto-cancels), while cancelled alongside a failure = the
watchdog killing the run.

**Self-inflicted pattern to avoid repeating:** `Concurrent Fork Isolation` has not reported
since `ef40cd2aa`, because each fix I pushed cancelled the run that would have judged the
previous one. If you need that job's verdict, WAIT for the run rather than pushing.

## Both `--debug` withhold paths are now closed

There were TWO, and the first fix alone could not work. `repo up` routes through the DAEMON,
not `local-executor` -- proven from the test log, where the spinner and `Checkpoint created`
are `renderJobEvent` output, which only exists on the daemon path.

    output-lines.ts    shouldEchoRelayLive(options)   fixed 7525913da / ef40cd2aa
    daemon/client.ts   routeLogEvent(..., echoAll)    fixed 37f6433a6

Class swept independently by BOTH sessions, counts agree: the only `debugEnabled()` left in
`packages/cli/src` outside tests and `utils/debug.ts` is inside `shouldEchoRelayLive`.
Verified by my own mutation (1 FAILED/10 passed, restored 11) and `check:ci-guard-mutations`
6 of 6.

**NOT proven end to end.** The controls pin both decisions and both pumps, not renet's line
surviving the daemon relay over SSH into the grepped log. **Two sessions have now reasoned
from code to a WRONG conclusion about which pump `repo up` uses. If it fails again, do NOT do
a third code read -- pull the runner's captured `--debug` stderr from the job artifact.**

## Ceph: root-caused and FIXED, do not re-investigate

`cephadm bootstrap` ran with no `--image`, so it pulled a floating tag, and quay.io rebuilt
EVERY Ceph tag in place on 2026-08-19. The next run bootstrapped Ceph 20 against noble's
ceph-common 19.2.3 (unchanged since 2026-02-24); a 32-byte type-2 admin key is unreadable to a
19.x client. Pinned to a dated tag in renet `c452df8`, gated by `check:ci-ceph-image-pin`
(review date, floating-tag detection, file/code agreement). **Two earlier hypotheses were WRONG
and are recorded so nobody retries them: it is NOT the 1800s resetVMs cap, and NOT apt drift.**

## Next action

1. Read `byi8tz15e` (or re-check `32364765277`). Count `cancelled` AND `neutral` as DID NOT
   REPORT (#4179d239).
2. Then a FRESH Claude review: the head has moved eighteen times, the marker no longer
   matches, `Review Complete` would go `neutral`. Resolve every thread.
3. Then delete the label in BOTH places, then `CronDelete 7cb9b31f`.
4. Never merge, never push `main`.

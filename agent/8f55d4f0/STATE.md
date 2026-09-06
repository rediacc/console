# Session 8f55d4f0 -- driver state

Branch `0906-1`. Last commit `96355d3b5`. Updated 2026-09-06.

## ACT ON THIS FIRST

Nothing is blocking. Six writer agents are live (see the wave below). When one
reports, SPOT-CHECK ITS ARTIFACT, not its summary: re-run the assert or the
count yourself. Two agent reports this session were confidently wrong about
their own headline number.

## Position, measured today not remembered

| Body | Done | Total |
|---|---|---|
| Quality gates ported (W7 P2) | 39 | 77 |
| Shadow pairs asserting green | 38 | 39 |
| Gate tests with a header (W2.3) | 0 | 148 |
| Aged plans compacted (W12 P1.8) | 32 | 32 |
| Plan boxes | 67 | 130 |

The single red pair is `w7p2-stagingtag`, permanently so: three tree ids are
disqualified by rows recorded through a hole since closed. It carries 12
qualifying trees over 9 finding sets, so the claim IS evidenced and only the
assert cannot express it. DO NOT delete rows to make it green.

PORT-D's five ledgers were verified independently after PORT-E disclosed that
its fixture-refresh script amended sibling agents' fixture commits: all five
assert green over 5 distinct trees. That risk is closed.

## Wave 2, launched 2026-09-06, six writers with disjoint ownership

| Agent | Owns | Doing |
|---|---|---|
| PORT-F | .ci/rediacc_ci/quality + tests + .ci/shadow, 12 named gates | W7 P2 |
| PORT-G | same dirs, 11 named gates | W7 P2 |
| PORT-H | same dirs, 11 named gates | W7 P2 |
| HDR-A | .ci/scripts/test/gates/test-*.sh entries 1-74 | W2.3 |
| HDR-B | .ci/scripts/test/gates/test-*.sh entries 75-148 | W2.3 |
| MOVE | 14 root policy dotfiles into .ci/policy + readers | W4 P2 |

Four gates are EXCLUDED from the port slices until MOVE lands, because they read
root dotfiles whose paths MOVE changes: check-e2e-coverage, check-go-deps,
check-profiler-coverage, check-plan-housekeeping.

## Driver-only, no agent may write these

package.json, scripts/ci-runner/manifest.ts, gates.lock.json, .github/workflows/**,
CLAUDE.md, docs/agent-reference/TRAPS.md, scripts/data/doc-registry.md,
scripts/lib/doc-providers.ts, .ci/breakpoint/**, agent/worklist/**.
An agent authors its registration as literal patch lines; the driver pastes them.
Only the driver runs `gate:bind --write`, once per wave, asserting `dropped` is empty.

## What is next after this wave

`docs/ci-overhaul/12-remaining-work.md` carries every remaining task WITH its
ready-to-run prompt. Wave 2 still holds T3 (PROXY, holds the machine mutex) and
T5 (SETUP, W6 P2). Wave 3 is T6 HOOKS, T7 SWEEP-CI, T8 RECORDS, T9 ENVMAN.
Wave 4 is driver-serial with no writer agents at all.

## Standing hazards paid for in this session

- `git add` with a wildcard crossed an ownership boundary and swept another
  agent's in-flight files without their dependency. HEAD imported a symbol that
  did not exist; gates stayed green on success and threw on the refusal path.
  Stage by explicit path.
- `git log --diff-filter=A` names the RENAME, not the landing, and `--follow`
  only sometimes repairs it. Search content history: `git log -S '<string>'`.
- Exit codes from a pipeline were misread twice. `grep -c` exiting 1 is the
  compound's exit.
- Never `git checkout`, `restore`, `stash`, `clean` or `reset`. Repair forward.

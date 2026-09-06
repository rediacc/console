# Session 8f55d4f0 -- driver state

Branch `0906-1`. Head `f9ade65db`. Updated 2026-09-06.

## ACT ON THIS FIRST

Nothing blocks. Five writer agents are live. When one reports, SPOT-CHECK ITS
ARTIFACT, not its summary: re-run the assert or the count yourself. Several
agent reports this session were confidently wrong about their own headline
number, and two of my own instruments were wrong before the claim they were
about to support (a grep for `PASS` when the vocabulary is `ok`, and `-m` on
six modules whose entry point is a shim).

## Position, measured today

| Body | Done | Total |
|---|---|---|
| Quality gates with a Python module on disk | 73 | 77 |
| Shadow ledgers | 71 | 77 |
| Gate tests declaring a header (W2.3) | 148 | 148 |
| Aged plans compacted (W12 P1.8) | 32 | 32 |
| Plan boxes | 67 | 130 |

The 73 and 71 include five agents' IN-FLIGHT work. Only 39 were asserted green
at the last full sweep; the rest assert when their agent reports.

`w7p2-stagingtag` is the one permanently red pair: three tree ids disqualified
by rows recorded through a hole since closed. It carries 12 qualifying trees
over 9 finding sets, so the claim IS evidenced and only the assert cannot
express it. DO NOT delete rows to make it green.

## Wave 2, five writers still live

| Agent | Owns | Doing |
|---|---|---|
| PORT-F | 12 named gates, .ci/rediacc_ci + .ci/shadow | W7 P2 |
| PORT-G | 11 named gates, same dirs | W7 P2 |
| PORT-H | 11 named gates, same dirs | W7 P2 |
| PORT-I | the 4 released from behind T4 | W7 P2 |
| PROXY | new files under .ci/scripts/test/proxies/ only | W3 P2 |

DONE this wave: HDR-A and HDR-B (148 headers), MOVE (fifteen policy lists).

## Landed by the driver while they ran

- Four quality gates died at the line that reads their input (`set -e` plus a
  bare `grep` substitution), so the empty-input handler each had was unreachable
- The 148 headers were UNREAD: `gate-bind.ts` excluded `/test/gates/`, and
  separately a malformed header refused nothing in `--write` or `--dry-run`
- `--park` was a silent no-op for a box-less plan, granting an unearned
  housekeeping exemption; the live case was revived and re-recorded
- Epics were still dying with /tmp; 18 commits already had an unresolvable
  `PR-TASK`, and the epic was restored from an older branch's tracked snapshot
- `check-enumeration-vacuity` was reading comments as code, and its claim to be
  inside its own scope was false

## Driver-only, no agent may write these

package.json, scripts/ci-runner/manifest.ts, gates.lock.json, .github/workflows/**,
CLAUDE.md, docs/agent-reference/TRAPS.md, scripts/data/doc-registry.md,
scripts/lib/doc-providers.ts, .ci/breakpoint/**, agent/worklist/**.
An agent authors its registration as literal patch lines; the driver pastes them.

## What is next

`docs/ci-overhaul/12-remaining-work.md` carries every remaining task WITH its
prompt. T5 (SETUP, W6 P2) is HELD while the port agents run, because they copy
`.ci/scripts/lib` into fixtures and a concurrent edit there makes a record
unstable. Wave 3 is T6 HOOKS, T7 SWEEP-CI, T8 RECORDS, T9 ENVMAN.

## Standing hazards paid for in this session

- `git commit` commits the INDEX, not the paths you just added. A peer's staged
  renames rode one of my commits and half-landed the policy move. Use
  `git commit -F <file> -- <pathspec>`, options BEFORE the `--`.
- `git add` with a wildcard crossed an ownership boundary and swept an agent's
  in-flight files without their dependency.
- `git log --diff-filter=A` names the RENAME. Search content history: `git log -S`.
- Never `git checkout`, `restore`, `stash`, `clean` or `reset`. Repair forward.

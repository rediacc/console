## SESSION legacy 2026-09-06T19:02:15Z (adopted from a pre-section document)

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

## SESSION 8f55d4f0 2026-09-07T00:48:38Z

Branch `0906-1`, head `5d6f07955` plus a worklist commit. TREE IS CLEAN: no agents, no
uncommitted files except an untracked `.err` that belongs to the OTHER live session.
Leave that alone.

## Next action

1. **#4a9b14ce, the push, and nothing is in its way now.** `ci:quick` is in flight as
   `bwnjt71vb` on a genuinely clean tree. On green:
   `git push origin 880b1b3ee:main`. One commit, fast-forward from `9295fb63c`, one
   file, +25 lines, operator-authorised. Until it lands, rediacc/account PR #86 and
   every renet and elite review run stay red at `discover-epics.sh: No such file or
   directory, exit 127`. `check:ci-secret-reachability` is carried in
   `.ci/config/carried-reds.json` with its operator-only door; carry NOTHING else.
2. Launch the rest of wave 3 from `docs/ci-overhaul/12-remaining-work.md`, all now
   unblocked and file-disjoint: **T7 SWEEP-CI** (W1 P4, re-measure first, the 93
   `sys.path` count predates the guard move), **T8 RECORDS** (W12 P3.1b/P3.2/P3.3/P3.4b,
   its prerequisite of a merged compaction wave is met), **T9 ENVMAN** (W8 P2/P3/P4).
3. **W7 P3 is the largest body left and is ONE box: 148 gate tests to pytest.**
   Untouched. It is also where the local run's floor lives: `gate-test:claude-hooks`
   780.4s and `check:ci-hook-worklist-suite` 686.4s are 24 minutes between them.

## What landed, measured this cycle

W2.6 at `5d6f07955`: the gate-bind regions now emit and OWN their steps. 112
hand-written duplicates removed, 10 jobs and 264 unique step names both before and
after, actionlint green. The deleter guard written for one job-boundary failure found a
SECOND at the other end of every span.

W5 P5-P7 at `7acaeca98`: dispatcher live, settings.json 73 command entries to 30, 456
process executions per Bash call to 35. The bash twins were MOVED to `.claude/oracles/`
and MUST NOT be deleted by a later sweep: they are what `test_guards_differential.py`
compares each port against, 5,844 cases.

W6 P2 at `2f0c3515d`: the one install table, 22 rows, 9 pinned, WITH the pytest row,
plus four macOS guards proved on a bash 3.2.0 built from source.

All eight plan and registry gates rc=0 this cycle on a clean tree. 78 shadow pairs, 77
green; `w7p2-stagingtag` is permanently red (three tree ids disqualified by rows
recorded through a closed hole, 12 qualifying trees over 9 finding sets, so the claim IS
evidenced). DO NOT delete rows to make it green.

Plan boxes 75 of 130, which FLATTERS: the 148 gate tests are ONE box.

## Volatile facts a fresh session would get wrong

A SECOND Claude session is live here: pid 2222763, session `a20630a0-dac7-...`. The
untracked `.err` at the repo root is its litter.

`check-gate-manifest` judges the FLOOR of the last five samples. I dropped
`check:ci-editorconfig`'s `slow` on a 4.6s floor and had to restore it a day later at
25.9s: one lucky run is not the cost.

SEVEN times this session an instrument of mine was wrong before the claim it supported.
The worst HID a real change: I verified a workflow's step-name set was unchanged while
two whole jobs had vanished, because a job header is not a `- name:` line. Choose the
check that could see the damage, and prefer a guard that REFUSES over care.

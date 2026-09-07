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

## SESSION 8f55d4f0 2026-09-07T00:27:05Z

Branch `0906-1`, head is the worklist commit after `7acaeca98`. BOTH WAVE-3 AGENTS
HAVE LANDED and the tree is clean apart from an untracked `.err` that belongs to the
other session. No agents are running.

## Next action

1. **#4a9b14ce, the push, and it is finally unblocked.** `ci:quick` is in flight as
   `b5c47v7vs` on the first genuinely still tree of the session. On green:
   `git push origin 880b1b3ee:main`. One commit, fast-forward from `9295fb63c`, one
   file, +25 lines, operator-authorised. Until it lands, rediacc/account PR #86 and
   every renet and elite review run stay red at `discover-epics.sh: No such file or
   directory, exit 127`. `check:ci-secret-reachability` is carried in
   `.ci/config/carried-reds.json` with its operator-only door; carry NOTHING else.
2. **#a6635a5b** Re-record `w7p2-hosttoolchain`. It asserts green over 5 trees, but I
   edited BOTH `check-host-toolchain-coverage.sh` and its port
   `.ci/rediacc_ci/quality/host_toolchain_coverage.py` for the W5 path re-key, so the
   rows attest to superseded bytes. Follow the recording recipe in
   `docs/ci-overhaul/12-remaining-work.md`.
3. **#0a1b79c4 W2.6 is DEFERRED, DEFAULT is a dedicated pass.** I attempted it and BROKE
   THE WORKFLOW: deleting the 112 duplicates `gate:bind --write` takes ownership of
   removed TWO ENTIRE JOBS, quality-branch and quality-content, because my deleter
   walked back over each step's comment block and for a step FIRST in its job that walk
   ate the job header. Repaired from a byte copy. If you retry: never cross a line
   matching `^  [a-z0-9-]+:$`, check the JOB set not only the step set, actionlint
   before believing anything.
4. Then T7 SWEEP-CI, T8 RECORDS, T9 ENVMAN from `docs/ci-overhaul/12-remaining-work.md`,
   all three now UNBLOCKED since their collisions with HOOKS and SETUP are gone. Then
   W7 P3: 148 gate tests to pytest, the largest body left and ONE box.

## What landed, and what it is worth

W5 CUTOVER at `7acaeca98`: the dispatcher is live, settings.json went from 73 command
entries to 30, and a Bash tool call from 456 process executions to 35, measured with
6,394 counting shims. The bash twins were MOVED to `.claude/oracles/`, not deleted,
because deleting them retires `test_guards_differential.py`, 5,844 cases and the only
proof a port answers what its twin answered. I verified 46 of 47 byte-identical myself;
the 47th is a disclosed forwarder. I also drove the live chain: `git add -A`,
`git commit --amend --no-edit` and `git worktree add x` all exit 2, `echo hello` exits 0.

W6 P2 at `2f0c3515d`: the one install table, 22 rows, 9 pinned, WITH the pytest row,
plus four macOS guards proved against a bash 3.2.0 built from source.

W7 P2 77/77, W3 P2 10/10, W4 P2 15/15, W12 P1.8 32/32. 78 shadow pairs, 77 green;
`w7p2-stagingtag` is permanently red (three tree ids disqualified by rows recorded
through a closed hole, 12 qualifying trees over 9 finding sets, so the claim IS
evidenced). DO NOT delete rows to make it green.

## Volatile facts a fresh session would get wrong

A SECOND Claude session is live here: pid 2222763, session `a20630a0-dac7-...`. The
untracked `.err` at the repo root is its litter, not yours; leave it.

`check-gate-manifest` judges the FLOOR of the last five samples, not the average. 52
gates are over budget and all 52 are tiered.

SIX times today an instrument of mine was wrong before the claim it supported. Five
invented findings; the sixth HID a real change: I verified the workflow's step-name set
was unchanged, 274/264 both sides, while two whole jobs had vanished, because a job
header is not a `- name:` line. Choose the check that could see the damage.

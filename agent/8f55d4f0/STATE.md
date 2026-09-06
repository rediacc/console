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

## SESSION 8f55d4f0 2026-09-06T19:38:18Z

Branch `0906-1`, head `01f7b312e` plus one worklist commit. Nothing of mine is
uncommitted. No writer agents are live.

## Next action

1. **#c5870a54** Widen `enumerates()` in `scripts/check-enumeration-vacuity.ts`
   to see the argv-array form of `git ls-files`, plus six corpus-derived floors
   in check-dead-service-methods, check-jq-boolean-default,
   check-merge-method-prose, check-retired-commands-in-docs,
   check-shape-duplication and check-shell-declared-commands. Measured
   2026-09-06: 19 tracked scripts are invisible to that predicate INCLUDING THE
   GATE ITSELF, whose comment claims it is inside its own scope, and 6 carry no
   guard. That adds 6 entries to a shrink-only baseline, so the regex and the
   six floors land as ONE change. Floors corpus-derived, never typed.
2. Correct the attribution in `.claude/hooks/pre-bash/block-pathspecless-git-commit.sh`
   and its TRAPS entry `git-commit-takes-the-whole-index`. The staged renames
   were MY OWN sub-agent's, not a peer session's, and the mechanism is that
   `git mv` stages by definition: `git mv a.txt b.txt` alone leaves
   `R100 a.txt b.txt` in the index, no `git add` anywhere. Both texts name a
   plausible cause rather than the measured one.
3. **#f79eb721** Re-measure `check:ci-gate-manifest`'s three `[tier]` findings
   (gate-test:doc-region-parity, gate-test:docs-gen, check:ci-editorconfig) on a
   still tree and set `slow:` from THAT run. The current numbers were taken with
   up to seven writer agents live: inadmissible under invariant 13.
4. **#4a9b14ce** `git push origin 880b1b3ee:main`. One commit, fast-forward from
   `9295fb63c`, one file, +25 lines, operator-authorised. Until it lands,
   rediacc/account PR #86 and every renet and elite review run stay red at
   `discover-epics.sh: No such file or directory, exit 127`.

CONDITION on 4 only: `block-unverified-push` refuses a push whose tree no gate
run has judged. `bng44gxl5` (`npm run ci:quick`) is in flight for that, and any
edit from 1 to 3 invalidates it, so one more run follows. A cost, not a blocker.

## What is true right now

W7 P2 COMPLETE: 77 of 77 quality gates have a Python twin, 76 of 77 shadow
ledgers assert `equivalence holds`. The one red is `w7p2-stagingtag`, and it is
permanent: three tree ids disqualified by rows recorded through a hole since
closed, 12 qualifying trees over 9 finding sets, so the claim IS evidenced and
only the assert cannot express it. DO NOT delete rows to make it green.

Also complete this wave: W2.3's headers (148 of 148 gate tests, and the binder
now READS them, which it did not when they landed), W3 P2 (10 heavy-job proxies
returning 77 rather than 0), W4 P2 (15 policy lists into `.ci/policy`, fifteen
not fourteen), W12 P1.8 (32 of 32 aged plans). No bash twin was deleted: that is
invariant 5, and deletion is W7 P5.

`docs/ci-overhaul/12-remaining-work.md` carries every remaining task with its
ready-to-run prompt and the command that re-derives each status number. Wave 2
still holds T5 (SETUP, W6 P2). Wave 3 is T6 HOOKS, T7 SWEEP-CI, T8 RECORDS,
T9 ENVMAN. Wave 4 is driver-serial, no writer agents.

## Volatile facts a fresh session would get wrong

A SECOND Claude session is live in this checkout: pid 2222763, session
`a20630a0-dac7-4561-94ce-4ff5f09fc6be`, started 17:43:15 today. It has never
written to the worklist store, so nothing tracked points at it.
`private/homebrew-tap` shows modified and is not mine.

In an interactive shell `grep` is a FUNCTION wrapping ugrep 7.8.4; a script gets
GNU grep 3.12. They disagree on `\x27` and on which files are searched: 231
references under the wrapper, 226 under the real grep. Use `/usr/bin/grep`.

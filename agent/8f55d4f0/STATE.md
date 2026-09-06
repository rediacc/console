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

## SESSION 8f55d4f0 2026-09-06T21:34:58Z

Branch `0906-1`, head `cb013fb51`. SETUP is writing: `.ci/scripts/lib/*.sh` are
modified and `.ci/rediacc_ci/setup/` is new and untracked. Those are ITS files,
not mine. HOOKS has no footprint under `.claude/` yet.

## Next action

1. **Land HOOKS (#609983e6) and SETUP (#95f675d1) when they report.** Re-run
   their acceptance yourself, do not trust the report. NOTE, because this
   document carried the opposite for half an hour: SETUP has NOT deviated.
   `core/platform.py` and `core/toolchain.py` already existed from W1 P3, and
   the new `.ci/rediacc_ci/setup/` package is the fourth deliverable its brief
   named, THE ONE INSTALL TABLE, at 1260 lines citing the six disagreeing
   sources it replaces. I flagged drift from a directory listing without
   checking whether the named files were already there.
2. **#4a9b14ce, one command once the tree is still.** `npm run ci:quick`, then
   `git push origin 880b1b3ee:main`. One commit, fast-forward from `9295fb63c`,
   one file, +25 lines, operator-authorised. Until it lands, rediacc/account
   PR #86 and every renet and elite review run stay red at `discover-epics.sh:
   No such file or directory, exit 127`. `block-unverified-push` requires the
   tree a run judged to equal the current tree, which is why this has waited.
   `check:ci-secret-reachability` is already carried in
   `.ci/config/carried-reds.json` with its operator-only door. Carry NOTHING
   else: every other red today was fixed.
3. Then the rest of wave 3 from `docs/ci-overhaul/12-remaining-work.md`: T7
   SWEEP-CI, T8 RECORDS, T9 ENVMAN, each held because it collides with a live
   agent (T7 with SETUP in `.ci/rediacc_ci`, T8 with HOOKS in
   `.claude/hooks/stop/wl_planrec.py`, T9 with SETUP in `.ci/scripts/lib`).
4. W7 P3, the largest remaining body and ONE box: 148 gate tests to pytest.

## What is true right now, measured this cycle

77 of 77 quality gates ported. 77 shadow pairs, 76 green. 374 files declare a
gate header, 0 malformed, of 847 subjects; 455 lock entries. 32 of 83 plans are
records (31 compacted, 1 parked). Plan boxes 71 of 130, which FLATTERS: the 148
gate tests are one box.

Every plan and registry gate green THIS cycle, measured on a contended tree
(SETUP writing): check:ci-plan-record, -plan-boxes, -plan-citations,
check-plan-housekeeping.sh, check:ci-gate-bind, -parity, -gate-manifest,
-python-lint.

`w7p2-stagingtag` is the one permanent red: three tree ids disqualified by rows
recorded through a hole since closed, 12 qualifying trees over 9 finding sets, so
the claim IS evidenced and only the assert cannot express it. DO NOT delete rows.

No bash twin has been deleted anywhere. That is invariant 5; deletion is W7 P5.

## Volatile facts a fresh session would get wrong

A SECOND Claude session is live in this checkout: pid 2222763, session
`a20630a0-dac7-4561-94ce-4ff5f09fc6be`. It never writes the worklist store;
`private/homebrew-tap` is its trace.

A task `.output` file reads 133 bytes for a LIVE agent; that is the placeholder,
not a dead worker. The stop hook reports the real size.

`check-gate-manifest` judges the FLOOR of the last five samples in
`.ci/cache/gate-durations.json`, not the average, so a contention excuse for its
findings is wrong. `ORDER` in `.claude/rediacc_hooks/guards/*.py` counts COMMANDS
in a chain, so inserting any hook re-keys every ORDER after it. In an interactive
shell `grep` is a FUNCTION wrapping ugrep 7.8.4 while a script gets GNU grep
3.12: use `/usr/bin/grep` or the number describes the wrapper.

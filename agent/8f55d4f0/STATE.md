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

## SESSION 8f55d4f0 2026-09-06T22:08:52Z

Branch `0906-1`, head `a6a351b84`. THE TREE IS MID-CUTOVER AND MOSTLY NOT MINE:
46 `.claude/hooks/**` files DELETED, 7 modified, 50 untracked. That is HOOKS and
SETUP working, not damage. Do not commit it blind, and NEVER `git checkout` or
`restore` to tidy it: that destroys two agents' in-flight work.

`block-unverified-push.sh`, `block-blanket-git-add.sh` and
`block-destructive-git-restore.sh` are among the deleted, so those guards are
OFF on disk right now. Behave as if they still fire.

## Next action

1. **HOOKS (#609983e6) is deleting the bash guards: W5 P6, the riskiest moment
   of the programme.** When it reports, verify YOURSELF before committing:
   `.claude/hooks/test-hooks.sh` exits 0 with every assertion green;
   `check:ci-pytest`, `check:ci-hook-integrity`, `check:ci-hooks-resolvable`
   exit 0; `check:ci-shape-duplication` exits 0 AND its baseline SHRANK, because
   deleting 43 `block-*.sh` shrinks a corpus that gate counts and
   `scripts/data/shape-duplication-seed.json` must be re-keyed in the same
   change (invariant 2). A guard that stops refusing is invisible everywhere
   except a test that plants what it should refuse.
2. **SETUP (#95f675d1) is at its assert.** `.ci/shadow/w6p2-toolchain.observations.jsonl`
   exists now, so run `npx tsx scripts/lib/shadow-gate.ts --pair w6p2-toolchain
   --assert --k 5` yourself. It has NOT deviated: `core/{platform,toolchain}.py`
   predate this wave (W1 P3) and `.ci/rediacc_ci/setup/tools.py` is the install
   table its brief named. An earlier STATE.md said otherwise; that was wrong.
3. **#4a9b14ce, the push.** Run `npm run ci:quick` once BOTH agents have landed
   and their work is committed, then `git push origin 880b1b3ee:main`. One
   commit, fast-forward from `9295fb63c`, one file, +25 lines,
   operator-authorised. Until it lands, rediacc/account PR #86 and every renet
   and elite review run stay red at `discover-epics.sh: No such file or
   directory, exit 127`. `check:ci-secret-reachability` is carried in
   `.ci/config/carried-reds.json` with its operator-only door; carry nothing
   else, everything else today was fixed.
4. Then T7 SWEEP-CI, T8 RECORDS, T9 ENVMAN from
   `docs/ci-overhaul/12-remaining-work.md`, each held only by a collision with
   HOOKS or SETUP. Then W7 P3: 148 gate tests to pytest, the largest body left
   and ONE box.

## What is true right now

W7 P2 COMPLETE, verified PAIRWISE rather than by count: all 77 bash quality
gates have a Python twin AND are named by a shadow ledger, mapped by the bash
path recorded inside each ledger row rather than by filename. 76 of 77 assert
green. `w7p2-stagingtag` is permanently red: three tree ids disqualified by rows
recorded through a hole since closed, 12 qualifying trees over 9 finding sets,
so the claim IS evidenced and only the assert cannot express it. DO NOT delete
rows to make it green.

Also complete: W2.3 headers (148 gate tests plus the 2 remaining run targets
under `.ci/scripts/test`; gate-bind reads 376 declared), W3 P2 (10 proxies
returning 77 not 0), W4 P2 (15 policy lists), W12 P1.8 (32 of 32 aged plans).
No bash twin deleted: invariant 5, W7 P5 owns that. Plan boxes 71 of 130, which
flatters, since 148 gate tests are one box.

## Volatile facts a fresh session would get wrong

A SECOND Claude session is live here: pid 2222763, session `a20630a0-dac7-...`;
`private/homebrew-tap` is its trace.

FIVE times today an instrument of mine produced a finding that did not exist:
grepping PASS when the vocabulary is `ok`; `python3 -m` on modules whose entry
point is a shim; `return problems` against `return exempt, problems`; ledger-to-
gate matching by filename when ids are abbreviated; and inferring SETUP drift
from a directory listing. Check the instrument before the claim.

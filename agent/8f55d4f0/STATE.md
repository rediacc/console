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

## SESSION 8f55d4f0 2026-09-06T22:37:35Z

Branch `0906-1`, head `0d60816d6`. HOOKS is still live and mid-cutover: 50
`.claude/hooks/**` files show DELETED, `.claude/rediacc_hooks/**` modified. That is
its work, not damage. NEVER `git checkout` or `restore` to tidy this tree.

The settings.json collapse is DONE (Bash chain 40 command entries to 4, pre-edit 11 to
4, pre-ask to 3) and I drove the replacement myself rather than trusting it:
`git add -A` exit 2, `git push --force origin main` exit 2, `git checkout -- x.ts`
exit 2, `echo hello` exit 0. The guards still refuse through the dispatcher.

## Next action

1. **Land HOOKS (#609983e6) when it reports.** Verify YOURSELF first:
   `.claude/hooks/test-hooks.sh` exits 0 with every assertion green;
   `check:ci-pytest`, `check:ci-hook-integrity`, `check:ci-hooks-resolvable` exit 0;
   `check:ci-shape-duplication` exits 0 AND its baseline SHRANK, because deleting 43
   `block-*.sh` shrinks a corpus that gate counts and
   `scripts/data/shape-duplication-seed.json` must be re-keyed in the same change.
   `check:ci-python-lint` is currently rc=1 on ITS files only
   (`.claude/rediacc_hooks/dispatch.py` and a guards test, both formatting, mid-edit).
2. **#4a9b14ce, the push.** After HOOKS lands and is committed: `npm run ci:quick` on a
   still tree, then `git push origin 880b1b3ee:main`. One commit, fast-forward from
   `9295fb63c`, one file, +25 lines, operator-authorised. Until it lands,
   rediacc/account PR #86 and every renet and elite review run stay red at
   `discover-epics.sh: No such file or directory, exit 127`.
   `check:ci-secret-reachability` is carried in `.ci/config/carried-reds.json` with its
   operator-only door; carry nothing else.
3. **#0a1b79c4 W2.6 is DEFERRED, DEFAULT is to leave it to a dedicated pass.** I tried
   it and BROKE THE WORKFLOW: deleting the 112 duplicates `gate:bind --write` takes
   ownership of removed TWO ENTIRE JOBS, quality-branch and quality-content, because my
   deleter walked back over each step's comment block and for a step FIRST in its job
   that walk ate the job header. Repaired from a byte copy. If you retry: never cross a
   line matching `^  [a-z0-9-]+:$`, check the JOB set not only the step set, actionlint
   before believing anything.
4. Then T7 SWEEP-CI, T8 RECORDS, T9 ENVMAN from `docs/ci-overhaul/12-remaining-work.md`,
   then W7 P3: 148 gate tests to pytest, the largest body left and ONE box.

## Measured this cycle

78 shadow pairs, 77 green. `w7p2-stagingtag` is the permanent red: three tree ids
disqualified by rows recorded through a closed hole, 12 qualifying trees over 9 finding
sets, so the claim IS evidenced and only the assert cannot express it. DO NOT delete rows.

W6 P2 LANDED (2f0c3515d), W7 P2 77/77, W3 P2 10/10, W4 P2 15/15, W12 P1.8 32/32,
headers 377 declared of 850 subjects, 0 malformed. Plan boxes 72 of 130, which FLATTERS:
148 gate tests to pytest are ONE box and are untouched.

Green this cycle: plan-record, plan-boxes, plan-citations, plan-housekeeping, gate-bind,
parity, gate-manifest (after retiering three gates over budget at their FLOOR),
gates-lock.

## Volatile facts a fresh session would get wrong

A SECOND Claude session is live here: pid 2222763, session `a20630a0-dac7-...`;
`private/homebrew-tap` is its trace.

`check-gate-manifest` judges the FLOOR of the last five samples, not the average, so a
contention excuse for its findings is wrong. I made that mistake once today.

SIX times today an instrument of mine was wrong before the claim it supported. Five
invented findings; the sixth HID a real change: I verified the workflow's step-name set
was unchanged, 274/264 both sides, while two whole jobs had vanished, because a job
header is not a `- name:` line. Choose the check that could see the damage.

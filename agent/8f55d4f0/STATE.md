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

## SESSION 8f55d4f0 2026-09-07T01:00:35Z

Branch `0906-1`. Tree clean but for an untracked `.err` belonging to the OTHER live
session. No agents running.

## Next action

1. **W2.6 IS REVERTED AND MUST NOT BE RE-LANDED AS-IS.** `gate:bind --write` DROPS
   PER-STEP `env:` BLOCKS. Measured: six emitted steps lost theirs (PR epic block,
   Every commit names its epic, Action freshness, Docker image freshness, External
   links, DKIM notify DNS), and three gates caught it:
   `check:ci-pr-head-ref-completeness`, `check:ci-bws-map`, `check:ci-python-gate-deps`.
   I reverted `.github/workflows/ci-quality.yml` from my own byte copy and all three
   went green again. THE EMITTER MUST CARRY `env:` (a header field, or emit it from
   the manifest) before the regions can own those steps. My earlier verification
   checked the job set and step NAMES and passed, because neither can see a missing
   `env:` block: that is the third time this session a check agreed while the damage
   was elsewhere.
2. **#4a9b14ce, the push.** `npm run ci:quick` then `git push origin 880b1b3ee:main`.
   One commit, fast-forward from `9295fb63c`, one file, +25 lines,
   operator-authorised. Until it lands, rediacc/account PR #86 and every renet and
   elite review run stay red at `discover-epics.sh: No such file or directory, exit
   127`. `check:ci-secret-reachability` is carried in `.ci/config/carried-reds.json`
   with its operator-only door; carry NOTHING else. Every other red named today was
   fixed.
3. Then T7 SWEEP-CI, T8 RECORDS, T9 ENVMAN from
   `docs/ci-overhaul/12-remaining-work.md`, all unblocked and file-disjoint. Then
   W7 P3: 148 gate tests to pytest, the largest body left and ONE box.

## What is true right now

W5 P5-P7 landed (`7acaeca98`): dispatcher live, settings.json 73 command entries to
30, 456 execs per Bash call to 35. The bash twins were MOVED to `.claude/oracles/`
and MUST NOT be deleted: they are what `test_guards_differential.py` compares each
port against. W6 P2 landed (`2f0c3515d`): the install table with its pytest row plus
four macOS guards proved on a bash 3.2.0 built from source.

W7 P2 77/77. 78 shadow pairs, 77 green; `w7p2-stagingtag` is permanently red and its
claim IS evidenced, so DO NOT delete rows to make it green. Plan boxes 75 of 130,
which flatters: 148 gate tests are ONE box.

## Volatile facts a fresh session would get wrong

A SECOND Claude session is live here: pid 2222763. The untracked `.err` is its litter.

`check-gate-manifest` judges the FLOOR of the last five samples, not the average.

EIGHT times this session an instrument of mine was wrong before the claim it
supported. The pattern is always the same: the check could not have seen the damage.
A step-name set cannot see a missing job or a missing `env:`; an `is_file()` guard
turns a moved subject into a silent skip; `[^)]*` cannot cross a nested paren. Prefer
a guard that REFUSES over a check that agrees.

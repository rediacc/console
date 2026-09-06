# Remaining work, with ready-to-run prompts

Written 2026-09-06 for a session that may be a compaction of this one and knows
NOTHING. Every task below carries the prompt to launch it, so nothing has to be
re-derived. Status figures are measured, not remembered.

## Where the program actually is

| Body | Done | Total | % |
|---|---|---|---|
| Quality gates ported (W7 P2) | 39 | 77 | 51 |
| Gate tests ported (W7 P3) | 0 | 148 | 0 |
| Gate tests DECLARING a header (W2.3) | 0 | 148 | 0 |
| Plans compacted (W12 P1.8) | 32 | 32 aged | 100 |
| Shadow pairs proven | 38 | 39 | 97 |
| Plan boxes | 67 | 130 | 51 |

Re-measured 2026-09-06 after the PORT-D landing, not carried forward. The
commands, so the next reader re-derives rather than trusts:

    ls .ci/rediacc_ci/quality/*.py | grep -v __init__ | wc -l          # 39 ported
    for l in .ci/shadow/*.observations.jsonl; do ... --assert --k 5; done  # 38 of 39
    grep -l '^Status: compacted' agent/PLAN-*.md | wc -l               # 32
    grep -cE '^\s*- \[x\]' <the plan>                                 # 67 of 130

The one red pair is `w7p2-stagingtag` and it is expected: see Known open defects.
The header row was wrong in the previous revision, which counted 226 of 445
headers across the WHOLE tree and read it as W2.3 progress. W2.3's actual
subject is the 148 gate tests, and every one of them has no header today.

**The 51 percent is by BOX COUNT and it flatters us.** The single largest body,
148 gate tests, is one box and is untouched. Bash is still present ON PURPOSE:
invariant 5 forbids deleting a twin in the change that ports it, so deletion is
W7 P5, the last phase.

## Constraints every prompt below must carry

Copy these into any agent brief. They are not ceremony; each was paid for.

- Never `git checkout`, `restore`, `stash`, `clean` or `reset`. Repair forward.
- Never `git commit` in the console checkout. Inside a throwaway fixture repo it
  is required.
- DRIVER-ONLY, no writer agent may edit: `package.json`,
  `scripts/ci-runner/manifest.ts`, `gates.lock.json`, `.github/workflows/**`,
  `CLAUDE.md`, `docs/agent-reference/TRAPS.md`, `scripts/data/doc-registry.md`,
  `scripts/lib/doc-providers.ts`, `.ci/breakpoint/**`, `agent/worklist/**`.
  An agent authors its registration as LITERAL LINES in its report; the driver
  pastes and commits them together. That is contract section 5e.
- A W7 P2 port needs NO registration at all. Verified: zero references to
  `rediacc_ci.quality` in package.json or manifest.ts.
- Only the driver runs `gate:bind --write`, once per wave, asserting `dropped`
  is empty. A stray `--write` deleted four hand-added steps on 2026-09-05.
- Namespace scratchpad helpers per agent. A sibling overwrote another agent's
  helper mid-wave.
- No em dashes. Read stdout and stderr separately. Run the real thing.
- To find where something LANDED, search content history first:
  `git log -S '<distinctive string>' -- <file>`. `git log --diff-filter=A` names the
  RENAME for any file ever moved, and `--follow` only sometimes repairs it: both were
  measured returning an unrelated commit as a landing. See TRAPS.md.

## The recording recipe, for any port task

`--record` refuses a dirty tree and this checkout is never clean, so recording
against it yields `clean:false` rows that `--assert` ignores entirely. Build each
specimen as its OWN committed git repo holding `.ci/scripts/lib`, the one gate,
its shim and `.ci/rediacc_ci`; seal with a commit; record with `--repo`. Run the
new side under `PYTHONDONTWRITEBYTECODE=1`. BOTH implementations must live inside
the recorded tree; the comparator now refuses a command reading outside it.
Acceptance is `--assert --k 5` exiting 0 with at least two distinct fingerprints.

## WAVE 2, up to 9 parallel

### T1. PORT-F/G/H, the last 39 quality gates. THREE AGENTS, fully parallel.
Owns per gate only: `.ci/rediacc_ci/quality/<mod>.py`,
`.ci/rediacc_ci/tests/test_quality_<mod>.py`,
`.ci/shadow/w7p2-<name>.observations.jsonl`.
PROMPT: "Port THIRTEEN bash quality gates to Python twins behind a shadow
differential. Your subjects are <list>. Follow the recording recipe in
docs/ci-overhaul/12-remaining-work.md exactly. No registration is needed. Never
edit or delete a bash twin. Transliterate comments: below a 0.90 comment-byte
ratio is REFUSED IN CODE by the comparator. Report each assert output verbatim."
EXCLUDE until T4 merges: check-e2e-coverage, check-go-deps,
check-profiler-coverage, check-plan-housekeeping. They read root dotfiles whose
paths T4 moves.

### T2. Gate-test headers. TWO AGENTS, split alphabetically, parallel.
The 148 `.ci/scripts/test/gates/test-*.sh` with no header. They declare
`kind: test` with a `blocker:`, which is non-emitting.
PROMPT: "Add a `---- gate ----` header to each of <list>. Read
scripts/lib/gate-header.ts for the parser v2 grammar. Derive id, run, step and
lane from the EXISTING entry in gates.lock.json so the header restates the
registry rather than inventing. Invariant 11: a header may only claim a step in
a lane that has an `- id: setup` step; quality-branch has none, so a gate there
declares `emit: false` plus `blocker:`. Verify with `gate-bind.ts --dry-run` and
`--only check:ci-gate-bind`, both exit 0, and the declared count must rise by
exactly the number you added. Never run `--write`."

### T3. PROXY, W3 P2 heavy-job proxies. ONE AGENT.
Owns new files under `.ci/scripts/test/` only. Each proxy returns 77 when its
toolchain is absent. HOLDS A MACHINE MUTEX (docker, port 4800, account.db), so
it cannot share a wave with any other docker-touching set. The elite compose
proxy and the Stripe offline test are CUT: both depend on a gitignored surface
or a live third party and would become flaky gates.

### T4. MOVE, W4 P2 policy folder. ONE AGENT, SERIAL, cannot be split.
Measured: ZERO of the 91 allow/block list pairs have disjoint reader sets, so
twelve agents would produce twelve conflicting branches. Moves the 14 root
dotfiles into `.ci/policy/` with every reader, and each list's own liveness
probe line, in one atomic change per list.

### T5. SETUP, W6 P2. ONE AGENT.
`.ci/rediacc_ci/core/{platform,toolchain}.py`, the toolchain port behind a
differential shadow gate, the four macOS bash fixes, and the one install table
INCLUDING the pytest row. Must not touch `NODE_VERSION_MIN`.

## WAVE 3, up to 6 parallel

### T6. HOOKS, W5 P5+P6+P7. ONE AGENT, long.
Owns `.claude/settings.json`, `.claude/hooks/**`, `.claude/rediacc_hooks/**`.
47 guards are ported but nothing routes to the dispatcher yet; settings.json
still has 144 command entries. MUST re-key `scripts/data/shape-duplication-seed.json`
in the same change: deleting 43 `block-*.sh` shrinks a corpus that gate counts,
which is invariant 2.

### T7. SWEEP-CI, W1 P4, `.ci` half only. ONE AGENT.
Measured 93 `sys.path` occurrences across 47 files, NOT the plan's 24. The
`.claude` half is deferred: 14 of its files are `wl_*.py`, which T6 is live in.

### T8. RECORDS, W12 P3.1b/P3.2/P3.3/P3.4b. ONE AGENT.
Hard prerequisite: ALL compaction batches merged. P3.3 and P3.4b change what
`check_plan_record.py` accepts while a compaction wave runs `--update`.

### T9. ENVMAN, W8 P2/P3/P4. ONE AGENT.
Do not delete `.ci/lib/local-common.sh` until W6's quality lane and W8's
retarget both land.

## WAVE 4, DRIVER-SERIAL, no writer agents

W2.3's generated manifest region plus the lock; W3 P3's shard matrix; W1 P4's
`.claude` half; W11 P5 (CLAUDE.md to 440 lines) and P6; W6 P5 deleting
`run-legacy.sh`; W7 P5 deleting the bash twins once their ledgers retire them.

## Known open defects, each needing its own change

- `--park` is a SILENT NO-OP for a plan with no checkbox boxes, so an unfinished
  plan is recorded `compacted` and gains an unearned housekeeping exemption.
  `renet-fetch-hardening` is the live case at 7 of 8 sites open.
- `check-shape-duplication.ts` reports coordinates off by up to 243 lines and
  silently drops code from its own corpus: its string-literal replacement uses
  `[^'\\]`, which matches newlines, so an apostrophe inside a double-quoted
  message eats every line to the next quote. Fixing it re-keys all 342
  fingerprints at once, so it is its own piece of work.
- `w7p2-stagingtag` can never assert green. Three tree ids are permanently
  disqualified by rows recorded through a hole since closed. It carries 12
  qualifying trees over 9 finding sets, so the claim is evidenced; only the
  assert cannot express it. Do not delete rows to make it pass.

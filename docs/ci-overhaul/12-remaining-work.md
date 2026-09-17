# Remaining work, with ready-to-run prompts

Written 2026-09-06 for a session that may be a compaction of this one and knows NOTHING. Every task below carries the prompt to launch it, so nothing has to be re-derived. Status figures are measured, not remembered.

## Where the program actually is

| Body | Done | Total | % |
|---|---|---|---|
| Quality gates ported (W7 P2) | 77 | 77 | 100 |
| Shadow pairs asserting green | 77 | 78 | 99 |
| Gate tests declaring a header (W2.3) | 148 | 148 | 100 |
| Heavy-job proxies (W3 P2) | 10 | 10 | 100 |
| Policy lists moved (W4 P2) | 15 | 15 | 100 |
| Install table (W6 P2) | 1 | 1 | 100 |
| Hooks dispatcher cutover (W5 **P5-P6 only**) | 1 | 1 | 100 |
| W5 **P7**, counted separately because the row above hid it | 0 | 4 | 0 |
| Plans compacted (W12 P1.8) | 31 | 31 | 100 |
| Gate tests ported to pytest (W7 P3) | 0 | 148 | 0 |
| Plan boxes | 78 | 130 | 60 |

Re-measured 2026-09-07 at the end of wave 3, not carried forward. The commands, so the next reader re-derives rather than trusts:

    ls .ci/rediacc_ci/quality/*.py | grep -v __init__ | wc -l          # 77 ported
    for l in .ci/shadow/*.observations.jsonl; do ... --assert --k 5; done  # 77 of 78
    grep -l '^Status: compacted' agent/PLAN-*.md | wc -l               # 31
    grep -cE '^\s*- \[x\]' <the plan>                                 # 78 of 130

WHY 55 PERCENT AFTER A WAVE THIS LARGE. Box count is a poor unit and it always flattered us in one direction and cheats us in another. The single largest body left, 148 gate tests to pytest, is ONE box. The eleven boxes wave 2 closed represent 77 ports, 148 headers, 10 proxies and 15 list moves.

The one red pair is `w7p2-stagingtag` and it is expected: see Known open defects. The header row was wrong two revisions ago, which counted 226 of 445 headers across the WHOLE tree and read it as W2.3 progress. W2.3's subject is the 148 gate tests; all 148 now declare, and as of `1490d7b7d` the binder actually reads them, which it did not when they landed.

**The 51 percent is by BOX COUNT and it flatters us.** The single largest body, 148 gate tests, is one box and is untouched. Bash is still present ON PURPOSE: invariant 5 forbids deleting a twin in the change that ports it, so deletion is W7 P5, the last phase.

## Constraints every prompt below must carry

Copy these into any agent brief. They are not ceremony; each was paid for.

- Never `git checkout`, `restore`, `stash`, `clean` or `reset`. Repair forward.
- Never `git commit` in the console checkout. Inside a throwaway fixture repo it
is required.
- DRIVER-ONLY, no writer agent may edit: `package.json`,
`scripts/ci-runner/manifest.ts`, `gates.lock.json`, `.github/workflows/**`, `CLAUDE.md`, `docs/agent-reference/TRAPS.md`, `scripts/data/doc-registry.md`, `scripts/lib/doc-providers.ts`, `.ci/breakpoint/**`, `agent/worklist/**`. An agent authors its registration as LITERAL LINES in its report; the driver pastes and commits them together. That is contract section 5e.
- A W7 P2 port needs NO registration at all. Verified: zero references to
`rediacc_ci.quality` in package.json or manifest.ts.
- Only the driver runs `gate:bind --write`, once per wave, asserting `dropped`
is empty. A stray `--write` deleted four hand-added steps on 2026-09-05.
- Namespace scratchpad helpers per agent. A sibling overwrote another agent's
helper mid-wave.
- No em dashes. Read stdout and stderr separately. Run the real thing.
- To find where something LANDED, search content history first:
`git log -S '<distinctive string>' -- <file>`. `git log --diff-filter=A` names the RENAME for any file ever moved, and `--follow` only sometimes repairs it: both were measured returning an unrelated commit as a landing. See TRAPS.md.

## The recording recipe, for any port task

`--record` refuses a dirty tree and this checkout is never clean, so recording against it yields `clean:false` rows that `--assert` ignores entirely. Build each specimen as its OWN committed git repo holding `.ci/scripts/lib`, the one gate, its shim and `.ci/rediacc_ci`; seal with a commit; record with `--repo`. Run the new side under `PYTHONDONTWRITEBYTECODE=1`. BOTH
implementations must live inside the recorded tree; the comparator now refuses a command reading outside it. Acceptance is `--assert --k 5` exiting 0 with at least two distinct fingerprints.

## WAVE 2, up to 9 parallel

### T1. PORT-F/G/H/I. DONE 2026-09-06. All 77 quality gates have a proven twin.
Owns per gate only: `.ci/rediacc_ci/quality/<mod>.py`, `.ci/rediacc_ci/tests/test_quality_<mod>.py`, `.ci/shadow/w7p2-<name>.observations.jsonl`.
PROMPT: "Port THIRTEEN bash quality gates to Python twins behind a shadow
differential. Your subjects are <list>. Follow the recording recipe in docs/ci-overhaul/12-remaining-work.md exactly. No registration is needed. Never edit or delete a bash twin. Transliterate comments: below a 0.90 comment-byte ratio is REFUSED IN CODE by the comparator. Report each assert output verbatim." The four that were EXCLUDED until T4 merged are released:
check-e2e-coverage, check-go-deps, check-profiler-coverage and check-plan-housekeeping. T4 landed at `b80552370`, so port the CURRENT bytes and do not resurrect a root path from an older document. `POLICY_DIR` is `.ci/policy` now, and two of those four changed in that same commit.

### T2. Gate-test headers. DONE 2026-09-06 (ce8dbac6d, b80552370, 1490d7b7d).
All 148 now declare a header. THE BRIEF'S `kind: test` WAS WRONG and both agents refused it from the parser rather than from each other: `kind: test` forbids `step:` and requires `test:` naming the gate-test that covers the entry, so it describes the 13 manifest entries whose CI coverage IS a gate-test, not the gate-tests themselves. The correct shape is `kind: battery` plus `step:
Quality-gate unit tests`, which the binder's own selftest fixtures.

The headers were NOT load-bearing when they landed, and that took two further fixes at `1490d7b7d`: `gate-bind.ts` excluded the whole `/test/gates/` tree from its subject scan, and separately a malformed header refused nothing in `--write` or `--dry-run` because the scan folded it into `problems`, which only the verify path reaches. Either alone would have made a planted defect
fail to fire.
PROMPT: "Add a `---- gate ----` header to each of <list>. Read
scripts/lib/gate-header.ts for the parser v2 grammar. Derive id, run, step and lane from the EXISTING entry in gates.lock.json so the header restates the registry rather than inventing. Invariant 11: a header may only claim a step in a lane that has an `- id: setup` step; quality-branch has none, so a gate there declares `emit: false` plus `blocker:`. Verify with `gate-bind.ts
--dry-run` and `--only check:ci-gate-bind`, both exit 0, and the declared count must rise by exactly the number you added. Never run `--write`."

### T3. PROXY, W3 P2 heavy-job proxies. DONE 2026-09-06 (`fab50886f`).
Owns new files under `.ci/scripts/test/` only. Each proxy returns 77 when its toolchain is absent. HOLDS A MACHINE MUTEX (docker, port 4800, account.db), so it cannot share a wave with any other docker-touching set. The elite compose proxy and the Stripe offline test are CUT: both depend on a gitignored surface or a live third party and would become flaky gates.

### T4. MOVE, W4 P2 policy folder. DONE 2026-09-06 (b80552370).
FIFTEEN lists moved, not fourteen: the plan's count was doc drift and `POLICY_FILES` is the checkable contract. `.ci-trigger` stays at root per W4 P0. Not one atomic change per list either, but ONE atomic change across the set: `POLICY_DIR` is a single constant and eleven readers reach it only through `policyPath()`, so moving one list while the constant stayed `''` would have
broken that reader for the other fourteen.

### T5. SETUP, W6 P2. DONE 2026-09-07 (`2f0c3515d`).
`.ci/rediacc_ci/core/{platform,toolchain}.py`, the toolchain port behind a differential shadow gate, the four macOS bash fixes, and the one install table INCLUDING the pytest row. Must not touch `NODE_VERSION_MIN`.

## WAVE 3, up to 6 parallel

### T6. HOOKS, W5 P5+P6. DONE 2026-09-07 (`7acaeca98`). **P7 IS NOT DONE.**
**Corrected 2026-09-07.** This heading and the summary row both claimed P5+P6+P7 at 100 percent, and a green row is why nobody staffed P7. All four of its deliverables are measurably open: `gate-test:claude-hooks` is still ONE manifest entry at `manifest.ts:5010` carrying `slow: true`, so it was SCOPED by W3 P0 but never SHARDED and the 785 s local floor stands; the lifecycle is
nowhere near 11 entries; `WORKLIST_*` has 138 distinct names and no registry; and cross-OS reaches exactly one file, `.claude/rediacc_hooks/proc.py`, whose `/proc`-versus-`ps` seam landed back in P1. P7 is startable now and needs a `manifest.ts` fragment for the shard leaves. The dispatcher is live. settings.json went from 73 command entries to 30 (the brief said 144; 73 was the
measured figure at HEAD) and a Bash tool call from 456 process executions to 35, counted with 6,394 shims rather than estimated.

THE BASH TWINS WERE MOVED TO `.claude/oracles/`, NOT DELETED, and a future sweep must not "finish the job" by removing them: they are what `test_guards_differential.py` compares each port against, 5,844 cases and the only proof a port answers what its twin answered. They sit at `.claude/oracles/` and not one level deeper inside the package because a third of these guards derive the
repo root as `dirname/../../..`; at the deeper path the differential reported 30 divergences across five guards.

Two things it found that outlive the phase. A port read the clock as UTC where its twin's `date +%m%d` is LOCAL, and the differential could never have caught it because the harness pins `TZ=UTC` for both sides; `time.tzset()` had to be added before the harness even honoured a per-case TZ. And `check_guard_feature_completeness.py` had NO vacuity floor, reporting "every called
feature resolves" on a corpus that had lost 46 of its 80 files.

### T7. SWEEP-CI, W1 P4. ONE AGENT. NOW UNBLOCKED.
Measured 93 `sys.path` occurrences across 47 files, NOT the plan's 24. The `.claude` half was deferred because T6 was live in `wl_*.py`; T6 has landed, so both halves are available. Re-measure before staffing: the W5 cutover moved 46 guards into `.claude/rediacc_hooks/guards/` and the count will have changed.

### T8. RECORDS, W12 P3.1b/P3.2/P3.3/P3.4b. ONE AGENT.
Hard prerequisite: ALL compaction batches merged. P3.3 and P3.4b change what `check_plan_record.py` accepts while a compaction wave runs `--update`.

### T9. ENVMAN, W8 P2/P3/P4. ONE AGENT. NOW UNBLOCKED.
Do not delete `.ci/lib/local-common.sh` until W6's quality lane and W8's retarget both land. W6 P2 landed at `2f0c3515d`, so the `.ci/scripts/lib` collision that held this is gone; the quality-lane half of W6 (P5) has not.

## WAVE 4, DRIVER-SERIAL, no writer agents

W2.3's generated manifest region plus the lock; W3 P3's shard matrix; W1 P4's `.claude` half; W11 P5 (CLAUDE.md to 440 lines) and P6; W6 P5 deleting `run-legacy.sh`; W7 P5 deleting the bash twins once their ledgers retire them.

## Known open defects, each needing its own change

- **`gate:bind --write` DROPS PER-STEP `env:`, and the repair is uncommitted.**
`grep -n env scripts/gate-bind.ts` returns only shebangs and test fixtures: the binder has no env support at all. The W2.6 emission at `5d6f07955` therefore landed steps with their env stripped. HEAD's `ci-quality.yml` holds 20 `env:` blocks where the correct file holds 26, and the 11 missing lines sit on steps that READ them -- `check:ci-pr-task-trailers` (`PR_HEAD_REF`,
`PR_BASE_REF`) and the Docker image freshness step (`DOCKERHUB_TOKEN`). The repair exists only as uncommitted work in this shared checkout: 711/340, 11 env lines added and ZERO removed, step-name set byte-identical at 274 = 274, `check:ci-gate-bind` green at 377 declared gates. **Teach the binder `env:` BEFORE the next `--write`, or that write re-strips them.** This gates W2.3's
manifest region and W3 P3's shard matrix, both of which run a `--write` as their first act.

- **`hookGuardsProvider` cannot see 117 of the files it claims to inventory, and its
parity gate cannot catch that.** `scripts/lib/doc-providers.ts:382` and `:440` enumerate `lsFiles(root, '.claude/hooks')` and nothing else. After W5 P6 moved the guards, `git ls-files` counts 90 under `.claude/hooks`, **65 under `.claude/rediacc_hooks`** and **52 under `.claude/oracles`** -- the 46 ported guards and the whole oracle corpus `test_guards_differential.py` compares
against are invisible to the generated region. `check:ci-doc-region-parity` compares generated to regenerated, so both sides are equally blind and the document is LYING WHILE GREEN. This is a vacuity hole of exactly the class TRAPS.md exists for.

- **W2.6's region cutover is one command plus a careful deleter.**
`gate:bind --write` emits with an EMPTY dropped set and loses no step (263 to 264 names, `comm` empty), leaving 112 hand-written duplicates the regions now own and the gate names one by one. AN INLINE ATTEMPT ON 2026-09-07 DELETED TWO ENTIRE JOBS, `quality-branch` and `quality-content`: the deleter walked back over each step's comment block to take its prose, and for a step FIRST
in its job that walk crossed the job boundary and ate the header, `runs-on` and `permissions`. Repaired from a byte copy. The recipe: never cross a line matching `^ [a-z0-9-]+:$`; assert the JOB set as well as the step set, because a step-name comparison is STRUCTURALLY BLIND to a missing job and will agree while the damage is there; run actionlint before believing anything.


- ~~`--park` silent no-op~~ FIXED 2026-09-06. `wl_planrec.compact` chose the
status with `park and d["n_open"]`, so a plan with no checkbox boxes took the `compacted` branch however loudly the caller asked for `parked`. It now honours the flag unconditionally, which can only err toward more nagging. Both directions driven on the real module over a four-cell matrix, and the pre-fix line was re-planted to prove the control fires. The live case,
`renet-fetch-hardening` at 7 of 8 sites open, was revived and re-recorded as `parked`; its Full-Text-Blob is unchanged, so nothing was lost.
- `check-shape-duplication.ts` reports coordinates off by up to 243 lines and
silently drops code from its own corpus: its string-literal replacement uses `[^'\\]`, which matches newlines, so an apostrophe inside a double-quoted message eats every line to the next quote. Fixing it re-keys all 342 fingerprints at once, so it is its own piece of work.
- `w7p2-stagingtag` can never assert green. Three tree ids are permanently
disqualified by rows recorded through a hole since closed. It carries 12 qualifying trees over 9 finding sets, so the claim is evidenced; only the assert cannot express it. Do not delete rows to make it pass.

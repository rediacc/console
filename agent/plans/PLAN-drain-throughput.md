# PLAN: Drain throughput -- fewer stalled writer turns, cheaper verification, reviews and landing inside the loop
Status: approved -- operator 2026-11-25 ordered a speedup plan after the drain consult of the same morning, ahead of a planned move of the host from WSL2 to native Linux (#ff417210)
Depends-On: no-dep -- stands alone; related, not prerequisite: PLAN-ciquick-cpu.md (ci:quick gate CPU), PLAN-tooling-speed.md (Stop hook latency)
Priority: P1 -- load-reducing and throughput-raising; standing directive: load-reducing plans go first
Concurrency: parallel
Owns: .ci/rediacc_ci/ops/agent_stalls.py, .ci/rediacc_ci/tests/test_agent_stalls.py, scripts/ci-runner/verify-changed.ts, scripts/ci-runner/__tests__/verify-changed.test.ts, scripts/ci-runner/lease-seed.ts, scripts/ci-runner/run.ts, scripts/ci-runner/typecheck-incremental.ts, scripts/worktree/**, .claude/commands/writers-now.md, .claude/hooks/stop/wl_review.py, .claude/hooks/post-bash/review_commit.py, package.json
Live-Proof: none -- the measure boxes read agent transcripts and the round ledger, no deployed surface (closed #ff417210)
First-Seen: 2026-11-25
Owner: d778be9d
Updated: 2026-11-25

## Why

The Promoted queue moved 62 boxes in about 12 hours overnight (1301 to 1363 of 1842, 2026-11-24T18:31Z to 2026-11-25T06:04Z), about 5.2 boxes per hour, across 8 hourly `/writers-now` rounds.

Measured from the 91 writer transcripts of the lead session d778be9d in that window:
- Writers were active 73.2 hours in total, and 50.8 of those hours were spent waiting for a model response.
- 551 waits fell between 175 and 400 seconds, median 190 s, 29.9 hours in total. The writer deaths of the same night read "No response from API (waited 3m, then 10m on the retry)", so each wait is a first-byte timeout followed by a retry.
- The drain consult (Fable, read-only) put the stalled-request rate at 10% of writer requests against 2% for the lead, with writers at a median context of about 113k tokens.
- Writer verification took 7.9 hours of Bash across 71 lease agents: pytest 75 min, vitest 56 min, `--narrow` 146 s per run, 215 uncached typechecks. The lead re-ran accepts for 49 more minutes.
- Finished writers waited 9.4 hours in total for the lead to land them.
- 238 of the 480 open boxes are live runs (bench 109, VM 46, hostinger 40, production 43). One bench runner ran all night and ticked nothing.
- 207 per-commit review findings: 10 high, 68 medium, 129 low. Every fix commit is reviewed again.

The host is WSL2 on 24 cores, with load peaks to 134 before the throttle landed. A move to native Linux is planned, so every measurement here is host-agnostic and is taken again after the move (DT4).

## Design

**A. Measure the stall, then tune it.** One script reads agent transcripts and reports, per model and per window: requests, waits in the timeout band, wait hours against active hours, and the stall rate by concurrent writers and by context size. A probe runs identical small read-only writers at 2, 4 and 8 at once, at a small and a large context, so the cause separates into concurrency, context size or host network. The probe's answer decides whether a harness timeout setting changes, which is the operator's ruling.

**B. Fewer turns per writer, cheaper verification.** A writer brief covers 1 or 2 boxes, so its context stays small. One command, `npm run verify -- --changed`, maps the lease's changed files to their vitest and pytest targets plus a typecheck of the touched packages, built on the existing selectors (`scripts/ci-runner/quick-select.ts`, `.ci/rediacc_ci/quality/pytest_impact.py`). In a lease, `--narrow` anchors on the lease's own changed files instead of the copied main receipt (`scripts/ci-runner/lease-seed.ts:93-102`). The incremental typecheck cache is seeded from the main checkout, since `CACHE_DIR` is keyed on the checkout path and every lease starts cold (`scripts/ci-runner/typecheck-incremental.ts`). Full `ci:quick` stays in the main checkout only, as `scripts/ci-runner/quick-clone.ts:106-112` already enforces.

**C. Reviews inside the writer.** The per-commit review stays an independent tool-less model call (`.claude/hooks/stop/wl_review.py`). The writer waits for the record of each of its commits and fixes the blocking findings in the same lease while the code is still in its context. A "not a bug" verdict on a high finding goes to the lead.

**D. Landing and staffing.** One command picks a finished lease (submodules first, generated doc regions regenerated on conflict, new tests placed on their shard), then applies the ready ticks, and stops only on a real conflict. The lead runs it as each report lands, re-runs accepts only after a conflicted pick, and every round starts one runner per live target its rules admit.

## Tasks

- [x] **DT1** [writer] `.ci/rediacc_ci/ops/agent_stalls.py`: reads `~/.claude/projects/<project>/<session>/subagents/*.jsonl` and the lead transcript for a time window; prints per model the request count, waits in the 175-400 s band, wait hours, active hours and stall rate, bucketed by concurrent writers and by context size; `--json` for the ledger. Test `.ci/rediacc_ci/tests/test_agent_stalls.py` with fixture transcripts (a stall, a fast turn, a death). Accept: the pytest rc 0, and the 2026-11-24T18:31Z..2026-11-25T06:04Z window reports about 551 band waits and about 50.8 wait hours.
    (ticked) 2026-11-25T12:21:20Z by d778be9d: DT1 stall report: 12 tests pass; real window writers 489 band waits median 190 s, writers plus lead 557 waits 53.2 wait hours, stall rate 6.6 percent at 1 writer to 12.8 percent at 8 or more; landed de7bea052c
- [ ] **DT2** [lead] Stall probe: identical read-only writers at 2, 4 and 8 concurrent, each at a small (under 40k tokens) and a large (over 100k tokens) context, 30 minutes per cell; DT1 reads each cell. Accept: a table of stall rate per cell written under `## Findings` here, naming the factor that moves it.
- [ ] **DT3** [operator] Rule on the harness setting DT2 points at (the first-byte and request timeouts in `.claude/settings.json` env, a writer concurrency cap, or neither), with DT2's table in front of the ruling.
- [ ] **DT4** [live] After the host moves from WSL2 to native Linux: DT1 over one overnight drain and DT2 once more. Accept: before and after rows under `## Findings`.
- [x] **DT5** [writer] `.claude/commands/writers-now.md` writer brief: 1 or 2 boxes per writer, a context budget, the prose rules that refused 37 of 84 commits (R18 and R19 in short), one verify command per step (DT6), and the report shape `land --run` reads (DT12). Accept: `npx tsx scripts/gen/gen-docs.ts` rc 0 and the skill's own checks rc 0.
    (ticked) 2026-11-25T12:21:22Z by d778be9d: DT5 writer brief section: prose check rc 0, covering hook tests 137 passed; landed 6ab37f3c36
- [x] **DT6** [writer] `scripts/ci-runner/verify-changed.ts` wired as `npm run verify -- --changed`: the changed files of the lease or the working tree mapped to vitest files, pytest files (through `pytest_impact.py`) and a typecheck per touched package, one exit code, one summary line per step. Test `scripts/ci-runner/__tests__/verify-changed.test.ts`. Accept: the test rc 0; on a one-file `.ts` change it runs under 60 s and selects the sibling test.
    (ticked) 2026-11-25T12:21:20Z by d778be9d: DT6 npm run verify -- --changed: 7 controls pass, one-file .ts change runs in 6.4 s and selects the sibling test; landed 93620817f6
- [ ] **DT7** [writer] `--narrow` in a lease anchors on the lease's base and its changed files, not on the failed and changed sets of the copied main receipt (`scripts/ci-runner/lease-seed.ts:93-102`, the narrow set built in `scripts/ci-runner/run.ts`). Accept: a test pins the lease anchor; a one-file change in a lease runs `--narrow` under 40 s.
- [ ] **DT8** [writer] Seed the incremental typecheck cache into each lease from the main checkout (`scripts/ci-runner/typecheck-incremental.ts`, `scripts/ci-runner/lease-seed.ts`). Accept: the second typecheck in a fresh lease is warm, measured against a cold one.
- [ ] **DT9** [lead] Prove the per-commit review fires for a lease commit and that its record carries to the cherry-picked sha (records carry a `Patch-Id`). Accept: a lease commit's record found under the picked sha by `worklist.py --review-run`.
- [ ] **DT10** [writer] Writer review loop, after DT9: the brief (DT5) and `.claude/hooks/post-bash/review_commit.py` let a writer wait for each of its commits' records and fix the blocking findings in the same lease, with `Fixes-Review:` trailers; a not-a-bug verdict on a high finding is reported, never marked by the writer. Accept: a test with a planted high finding; the lease's report names it fixed.
- [ ] **DT11** [operator] Rule on the findings policy: today every finding is fixed before merge. The alternative fixes high findings before the push and batches medium and low per file cluster before the merge (`block_at` is `"high"` at `.claude/hooks/stop/wl_review.py:56`).
- [x] **DT12** [writer] `./run.sh worktree land <id> --run`: runs the picks (submodules first, then the gitlink), resolves a conflict confined to generated doc regions by regenerating with `npx tsx scripts/gen/gen-docs.ts --write`, places new tests with `npm run shard:place`, then runs `worklist.py --apply-ticks <me> --write`; stops and prints on any other conflict. Accept: tests for a clean pick, a generated-region conflict and a real conflict.
    (ticked) 2026-11-25T12:21:21Z by d778be9d: DT12 worktree land --run: 7 tests pass, lease suite 235 passed, help names --run; landed 6f2bf60567
- [x] **DT13** [writer] `.claude/commands/writers-now.md`: every round starts one runner per live target its rules admit (bench and hostinger at once, the VM fleet after a VERIFIED `vm:check`, production after its receipts), and the round report counts runners beside writers. The lead re-runs a writer's accepts only after a conflicted pick. Accept: the skill's checks rc 0.
    (ticked) 2026-11-25T12:21:23Z by d778be9d: DT13 one runner per admitted live target each round, accepts re-run only after a conflicted pick: prose check rc 0; landed c30103405e
- [ ] **DT14** [operator] Rule on a drain freeze: while a drain runs, tooling commits (`.claude/hooks/**`, `.claude/rediacc_hooks/**`, `scripts/ci-runner/**`) land only when they fix a blocker of the drain. 52 of 154 commits on the night of 2026-11-24 were tooling.
- [ ] **DT15** [live] After DT5-DT8, DT10, DT12 and DT13: one overnight drain measured by DT1 and the round ledger. Accept: at least 15 boxes per hour (from 5.2), stalled-wait share under 20% of writer active time, host load p90 under 24.

## Findings

(DT2 and DT4 tables land here.)

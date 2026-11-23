# PLAN: No writer limit -- remove the writer cap, the tree cap and every check, refusal and doc line built on them
Status: approved -- operator ruling #3ca908ee (2026-11-23, session ace763dd): remove the writer limits completely, at every effort level
Depends-On: no-dep -- every box edits hook, guard and lease code already at the 1121-1 tip
Priority: P1 -- the cap turned free capacity into refusals on 2026-11-23 (`--lease ... worker:queue` refused with "5 of 25 writer slots are busy")
Concurrency: exclusive -- one writer owns the whole sweep, because guards, the Stop hook and the lease verb read the cap together
Owns: agent/plans/PLAN-unlimited-writers.md, .claude/hooks/stop/wl_roster.py, .claude/hooks/stop/wl_planconc.py, .claude/hooks/stop/wl_cli.py, .claude/hooks/stop/wl_checks.py, .claude/hooks/stop/wl_standdown.py, .claude/hooks/stop/wl_boxready.py, .claude/hooks/stop/wl_planqueue.py, .claude/hooks/stop/worklist_messages.py, .claude/hooks/stop/test-*.py, .claude/rediacc_hooks/guards/block_agent_cap.py, .claude/rediacc_hooks/guards/test-block_agent_cap*.py, .claude/rediacc_hooks/guards/block_plan_concurrency.py, .claude/rediacc_hooks/guards/test-block_plan_concurrency.py, .claude/rediacc_hooks/tests/**, .claude/settings.json, .claude/config/effort.json, .ci/rediacc_ci/dev/worktree_lease.py, .ci/rediacc_ci/tests/test_dev_worktree_lease.py, .ci/config/env-manifest.json, .ci/policy/hook-exec-baseline.json, CLAUDE.md, .claude/commands/*.md, .claude/skills/**, docs/agent-reference/**
Live-Proof: none -- local agent tooling with no deployable surface, operator ruling #3ca908ee (closed with the operator's words)
Owner: ace763dd
First-Seen: 2026-11-23

## Ask

The writer cap (`wl_roster.WRITER_CAP = 25`, earlier `writer_cap: 4` in QUEUE.md) and the lease tool's tree cap were sized for a 5-hour usage window that no longer applies. Remove them outright, at every effort level: no constant, no setting, no refusal, no "slots" wording.

## Context (read 2026-11-23 against the tree; the writer re-reads each citation)

1. `.claude/hooks/stop/wl_roster.py:40-47` holds `WRITER_CAP = 25` and `writer_cap(root)`; `:620`, `:822` (`over_cap`), `:951` (`writer_cap` in the verdict) and `:2193` read it.
2. `.claude/rediacc_hooks/guards/block_agent_cap.py` refuses a writer spawn when `wl_roster.writer_cap(root)` writers are live (`:85`).
3. `.claude/hooks/stop/wl_planconc.py:980-988` refuses a spawn whose live writers plus same-message claims "fill writer_cap".
4. `.claude/hooks/stop/wl_cli.py:1975-1995` refuses `--lease <id> worker:queue` while "N of 25 writer slots are busy".
5. `.claude/hooks/stop/wl_checks.py:3572`, `:3753-3755`, `:3884`, `:4628-4647` gate CAP-SATURATED / CONCURRENCY-SATURATED waits on the cap; `worklist_messages.py:3063`, `:3097`, `:3102`, `:3239` render them and IDLE CAPACITY; `wl_standdown.py:5` (CAP_WAIT), `wl_boxready.py`, `wl_planqueue.py:1208` ("Writers: %d live of writer_cap %d").
6. `.ci/rediacc_ci/dev/worktree_lease.py` holds at most 25 trees on disk.
7. CLAUDE.md rule 2/4 text ("max 4", "writer cap (25)", "fixed in code"), `.claude/commands/writers-now.md` (roster budget, `worker:queue` on a full cap), `.claude/commands/wisdom.md` ("Writers count against writer_cap").

## Design

- Delete the constant and `writer_cap()`; every caller drops its comparison. Nothing replaces it: no QUEUE.md setting, no effort key.
- `block_agent_cap` is retired (file, settings.json wiring, tests, fixture, doc-registry row) in the same commit; the generated hook tables are regenerated.
- `block_plan_concurrency` keeps its file-overlap and `exclusive` rules (they protect the main checkout from two editors) and loses only the cap rule.
- `worker:queue` stays as the lease for work refused by `block_plan_concurrency` (a file clash) and is admitted whenever such a refusal exists; the "slots are busy" refusal goes.
- The Stop hook loses CAP-SATURATED WAIT; CONCURRENCY-SATURATED WAIT stays for file-clash queues. IDLE CAPACITY names ready writer boxes with no slot count.
- The lease tool keeps no tree-count limit; `gc` still collects landed trees.
- Docs say: no writer limit; the harness's own concurrent-subagent ceiling is the only bound, and file ownership still decides who edits what.

## Boxes

- [ ] U1 [writer] Remove `WRITER_CAP`/`writer_cap` and every comparison in wl_roster, wl_planconc, wl_cli, wl_checks, wl_standdown, wl_boxready, wl_planqueue and worklist_messages; CAP-SATURATED and "writer slots" wording gone. Accept: `grep -rnE "WRITER_CAP|writer_cap|writer slots|CAP-SATURATED|CAP_WAIT" .claude/hooks .claude/rediacc_hooks` prints nothing outside comments citing this plan; every touched hook suite rc 0.
- [ ] U2 [writer] Retire `block_agent_cap` (guard, tests, fixtures, settings.json wiring, generated hook docs) and drop the cap rule from `block_plan_concurrency`, keeping its overlap and exclusive rules. Accept: `test-block_plan_concurrency.py` rc 0 with a new case where 30 live writers do not refuse a disjoint spawn; `npx tsx scripts/gen/gen-docs.ts --write` leaves no diff after the commit; `npm run -s check:ci-guard-mutations` rc 0.
- [ ] U3 [writer] Remove the lease tool's tree-count limit. Accept: `test_dev_worktree_lease.py` rc 0 with a case leasing past the old 25.
- [ ] U4 [writer] Rewrite the CLAUDE.md, `.claude/commands/writers-now.md`, `.claude/commands/wisdom.md`, `.claude/skills/**` and docs/agent-reference lines that state a writer cap or slot budget. Accept: `grep -rniE "writer.?cap|writer slots|max 4 at a time" CLAUDE.md .claude/commands .claude/skills docs/agent-reference` prints nothing; `npm run -s check:ci-prose-style` shows no new finding.
- [ ] U5 [lead] One wave of more than 25 writers runs with no cap refusal from any guard or the Stop hook. Accept: the wave's spawn log quoted here with the writer count.

## Outcome

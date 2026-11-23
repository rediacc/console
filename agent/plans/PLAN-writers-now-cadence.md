# PLAN: writers-now cadence -- an hourly round enforced at effort high, a self-review that finds missed work before each repeat round, and stuck shell-waiting agents caught
Status: approved -- operator ruling #ac2de21f (2026-11-23, session ace763dd)
Depends-On: no-dep -- every box edits Stop-hook, skill and roster code already at the 1121-1 tip
Priority: P1 -- the operator had to type /writers-now by hand at effort high, repeat rounds found no new work, and a finished writer sat "waiting on 1 shell" for hours with no check firing
Concurrency: parallel -- one writer owns the sweep; its files are disjoint from every other live plan
Owns: agent/plans/PLAN-writers-now-cadence.md, .claude/hooks/stop/wl_checks.py, .claude/hooks/stop/wl_roster.py, .claude/hooks/stop/wl_liveness.py, .claude/hooks/stop/wl_planqueue.py, .claude/hooks/stop/worklist_messages.py, .claude/hooks/stop/wl_cli.py, .claude/hooks/stop/wl_floor.py, .claude/hooks/stop/wl_writersnow.py, .claude/hooks/stop/test-*.py, .claude/rediacc_hooks/tests/**, .claude/config/effort.json, .claude/commands/writers-now.md, .claude/settings.json, docs/agent-reference/**, scripts/data/doc-registry.md
Live-Proof: none -- local agent tooling with no deployable surface, operator ruling #ac2de21f (closed with the operator's words)
Owner: ace763dd
First-Seen: 2026-11-23

## Ask

Three changes the operator asked for together:

1. At effort `high` the Stop hook enforces a `/writers-now` round at least once per hour: a stop with no round started in the last 60 minutes blocks until one starts. The operator should never have to type the command at high.
2. A repeat round finds work the previous round missed. Before its survey, the round reads this session's own experience (what landed, what writers reported as owed or outside their Owns, review findings, worklist items added this context, blocked items whose blocker closed) and hands that list to the survey as seeds.
3. An agent shown as "waiting on 1 shell" whose report is final, or whose shell outlives a bound, is caught: the Stop hook names it as STUCK with the shell id and the exact `TaskStop`/`SendMessage` move, instead of counting it live forever.

## Context (read 2026-11-23 against the tree; the writer re-reads each citation)

1. `.claude/hooks/stop/wl_liveness.py:302` counts as live "each agent waiting on a shell it armed", with no time bound and no check of whether the agent's report already landed.
2. `.claude/hooks/stop/wl_roster.py:816` renders "<agent> waiting on shell <id>" as a live state; `:852` and `:1693` treat a live descendant as supervision.
3. Observed 2026-11-23: writer a7f511c739e4aa739 (stripe-disable) reported at ~17:2xZ with a final TICK block and still showed `waiting on 1 shell · since 4:49 PM` (its own `npm run ci -- --narrow`); the roster called it live, so no dead-writer or stuck check fired, and its item stayed leased.
4. The writers-now skill is `.claude/commands/writers-now.md`; nothing records when a round last ran, and no effort key names a writers-now cadence (`.claude/config/effort.json`).
5. Repeat rounds re-survey the same plan text, so work found only in reports (outside-Owns edits, follow-up defects, owed live halves) is invisible to the survey unless it was added to the worklist.

## Design

- **Round record.** `/writers-now` appends one row to `agent/ledgers/writers-now-rounds.jsonl` (session, UTC start, survey path, seed count) at its start, through a new verb `worklist.py --writers-now-start <me> <survey-path>`; the skill text calls it as step 0.
- **Cadence check.** A new check `writers-now-due` in `wl_checks.py`, keyed in `effort.json` as `{"block": "high", "advise": "smart"}`: it fires when the newest row for this session is older than 60 minutes (or absent) and the Promoted queue has open boxes, and names `/writers-now` as the next action. It stands down in the landing tree, in a `babysit`/`merge` phase, and while a round started under 60 minutes ago.
- **Self-review seeds.** A new module `wl_writersnow.py` builds the seed list from this session's own records: worklist items added or updated in this context, review findings opened in this context, `BLOCKED_BY:` items whose blocker is now closed, and the "owed" / "outside Owns" / "for the lead" lines of sub-agent reports captured by `wl_report.py`. `--writers-now-start` writes the seeds to `/tmp/writers-now/<branch>-<stamp>-seeds.md`; the skill hands that file to the survey agent, which must classify every seed (CODE / LIVE / PRESENT / closed) beside the plan boxes.
- **Stuck shell-waiter.** `wl_liveness`/`wl_roster` stop treating "waiting on a shell" as unconditionally live. An agent is STUCK when it waits on a shell AND either (a) its final report is captured (a `wl_report` row with a TICK block or a closing summary), or (b) the shell has run longer than 45 minutes. A STUCK agent is not live: its lease is reported under a new FLOOR-adjacent check `stuck-shell` naming the agent id, the shell id and the two moves (`TaskStop <shell>` then land the report, or `SendMessage` to resume). Effort key `{"block": "low", "advise": "quiet"}`.
- **Docs.** CLAUDE.md is not edited; `.claude/commands/writers-now.md` gains step 0 and the seeds step; docs/agent-reference gains one paragraph on the cadence.

## Boxes

- [ ] WN1 [writer] Round record: `worklist.py --writers-now-start <me> <survey>` appends to `agent/ledgers/writers-now-rounds.jsonl` and prints the round id; `.claude/commands/writers-now.md` calls it as step 0. Accept: a test appends a row and a second call within the hour appends a second row with its own id.
- [ ] WN2 [writer] Cadence check `writers-now-due` blocking at effort high, advising at smart, standing down in the landing tree, in babysit/merge and inside the 60-minute window. Accept: hook tests cover fire (no row, 61-minute-old row), silent (59-minute-old row, landing tree, babysit phase, empty Promoted queue), and the effort-table check `--effort-table` rc 0.
- [ ] WN3 [writer] Self-review seeds in `wl_writersnow.py`, written by `--writers-now-start`, and the skill step that hands the seeds file to the survey agent with the instruction to classify every seed. Accept: a fixture session with one outside-Owns report line, one closed-blocker item and one new review finding produces three seeds; the skill text names the seeds file.
- [ ] WN4 [writer] Stuck shell-waiter: an agent waiting on a shell is STUCK after its final report or after 45 minutes of shell runtime; the `stuck-shell` check names agent, shell and both moves; the roster no longer counts it live. Accept: tests for (a) report-captured waiter -> STUCK, (b) 46-minute waiter -> STUCK, (c) 10-minute waiter with no report -> live (control); the 2026-11-23 a7f511c739e4aa739 shape reproduced as a fixture fires.
- [ ] WN5 [lead] One hour at effort high with no operator-typed /writers-now: the hook starts a round by itself and the round's survey lists at least one seed-sourced item. Accept: the two writers-now-rounds.jsonl rows and the seed line quoted here.

## Outcome

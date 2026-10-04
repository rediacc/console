# PLAN: Stop-hook turbo mode, batch size per PR, and agent/plans/QUEUE.md as the only switchboard

Status: approved -- operator 2026-10-04: "please plan & implement it in this PR and enable it NOW"; rides PR #594
Owner: d778be9d
First-Seen: 2026-10-04
Depends-On: no-dep -- builds only on shipped modules (plan_gate, wl_planqueue, wl_prscope, wl_checks, refresh_pr_body)
Priority: P1 -- operator order 2026-10-04: turbo is enabled on this branch, and the next PRs carry a batch of plans instead of one
Concurrency: exclusive -- operator ruling 2026-09-26: every plan runs alone while the token budget is limited
Owns: .claude/hooks/stop/wl_planqueue.py, .claude/rediacc_hooks/plan_gate.py, .claude/hooks/post-bash/refresh_pr_body.py, .claude/hooks/stop/{wl_prscope,wl_checks,worklist_messages,worklist,wl_agents,wl_judge,wl_defersettle}.py, .claude/rediacc_hooks/guards/{block_admin_merge,block_push_to_protected_branch}.py, .ci/scripts/quality/{check_plan_implementation,check_plan_record}.py, .ci/config/stop-hook.json (deleted), .ci/policy/{worklist-env-registry.json,README.md}, .ci/rediacc_ci/quality/worklist_env_registry.py, .ci/config/{env-manifest,python-env-registry}.json, .ci/config/shards/quality-pytest.json, scripts/data/doc-registry.md, agent/plans/QUEUE.md, .claude/rediacc_hooks/tests/{test_wl_queue_settings,test_plan_gate,test_wl_prscope,test_wl_loop_next,test_wl_cadence,test_wl_leases,test_wl_message_catalogue,test_wl_roster,test_wl_advisories_rotation,test_wl_focus,wlfix}.py, .claude/hooks/stop/test-judge-schema.py, .claude/rediacc_hooks/guards/{test-block_admin_merge,test-block_push_to_protected_branch}.py, CLAUDE.md, docs/agent-reference/ci-gates.md, .claude/commands/pr-merge.md, .claude/agents/pr-babysitter.md
Worklist: #a2621a70

**Operator ask, 2026-10-04 (verbatim).**
- "there should be a (or planned) turbo mode for stop hook. normally we go with one plan per PR. But with turbo mode we aim to complete the plans as much as possible until the turbo mode is disabled. Can you investigate if it's implemented. If not, please plan & implement it in this PR and enable it NOW. Then the stop hook should push you to go for other plans. Be careful, do not start the plans unless the stop hook pings you since we also aim to fix the bugs. agent/plans/QUEUE.md should be the file for enabling/disabling those: stop hook system, turbo mode + batch size per PR. The batch size is new: it's the minimum plan implementation per PR. So, we batch multiple plans into single PR on each iteration. If you have any questions, ask them after investigation & planning. Migrate the existing enabling/disabling checks to agent/plans/QUEUE.md file as single source of truth." <!-- style-ok -->

**Operator answers, 2026-10-04 (/ask after planning), verbatim where quoted.**
- Batch size: "When turbo is enabled there is no limit for batch. It should do continiously. Additionally, there is a sub-agent limiter. The current limit is 4 writers. That value should also be read from the QUEUE.md file. Additionally, when operator enables the turbo mode it should start to work immediately. Aim is to go as much as the AI system can go in parallel with parallel writers." <!-- style-ok -->
- Solo marker: "Yes, add a solo marker".
- Off semantics: `stop_hook: off` allows every stop with a free notice; `turbo: off` keeps today's one-plan-per-PR loop.
- The "minimum enforcement" question went unanswered, so `batch_size` keeps the operator's first definition, "the minimum plan implementation per PR": the hook offers the merge path only once that many plans of the PR are finished (or the queue has no eligible plan left), and the merge gate never refuses a short PR.

## What was true when this was written

- **No turbo mode exists.** The code assumes one plan per PR in these places:
  - `.claude/rediacc_hooks/plan_gate.py:53` (`queue_head`) and `.claude/rediacc_hooks/plan_gate.py:81` (`with_plan_line`, which writes a single plan).
  - `.claude/rediacc_hooks/plan_gate.py:228`: `plan_merge_refusal` refuses a PR that names more than one plan unless it carries `Operational-Reason:`. It then checks only `plans[0]` (`.claude/rediacc_hooks/plan_gate.py:236`).
  - `.claude/hooks/post-bash/refresh_pr_body.py:155` writes `queue_head` as the PR's only `Plan:` line.
  - `.claude/hooks/stop/wl_prscope.py:83` (`next_queued` returns one plan). In `.claude/hooks/stop/wl_prscope.py:126`, `own` falls back to `{head}`.
  - The loop-next arms: `.claude/hooks/stop/wl_checks.py:2576` and `.claude/hooks/stop/wl_checks.py:4272`, with their strings at `.claude/hooks/stop/worklist_messages.py:2668`.
  - The CI clock: `clock_scope` at `.ci/scripts/quality/check_plan_implementation.py:227` always puts the queue head on the clock.
- **A Stop-hook off switch already exists. This corrects the investigation brief.**
  - `.claude/hooks/stop/worklist.py:1883` (`_stop_hook_disabled`) reads `.ci/config/stop-hook.json`. At `.claude/hooks/stop/worklist.py:1899`, `"enabled": false` exits 0 silently.
  - The test is `.claude/rediacc_hooks/tests/test_wl_leases.py:252`, and the switch is registered at `scripts/data/doc-registry.md:1084`.
  - This is the "existing enabling/disabling check" that must migrate. The `.claude/settings.json:98` wiring stays as it is.
- **Standing env switches:**
  - `WORKLIST_CADENCE` (`.claude/hooks/stop/wl_checks.py:4935`)
  - `WORKLIST_AGENT_HINT` (`.claude/hooks/stop/wl_agents.py:34`, read at import, consumed at `.claude/hooks/stop/wl_checks.py:1475` and `.claude/hooks/stop/wl_checks.py:1929`)
  - `WORKLIST_AGENT_PUSHBACK` (`.claude/hooks/stop/wl_agents.py:393`, consumed at `.claude/hooks/stop/wl_agents.py:466`)
  - `WORKLIST_JUDGE` (`.claude/hooks/stop/wl_judge.py:36`, plus a second reader at `.claude/hooks/stop/wl_defersettle.py:574`)

  The registry entries are at `.ci/policy/worklist-env-registry.json:71`, `.ci/policy/worklist-env-registry.json:102`, `.ci/policy/worklist-env-registry.json:193` and `.ci/policy/worklist-env-registry.json:371`. The hook fixtures set `WORKLIST_JUDGE` and `WORKLIST_CADENCE` at `.claude/rediacc_hooks/tests/wlfix.py:522` and `.claude/rediacc_hooks/tests/wlfix.py:524`.
- **Fixtures run against their own project.** `stop_env` sets `CLAUDE_PROJECT_DIR` to the fixture project, and `run_stop` resolves `root` from the event (`.claude/hooks/stop/wl_checks.py:2752`). So settings read from `root` reach the fixtures, while settings read from `hook_repo_root()` would leak the operator's live QUEUE.md into them.
- QUEUE.md parsing lives in `.claude/hooks/stop/wl_planqueue.py:24`, with markers at `.claude/hooks/stop/wl_planqueue.py:26`.
  - The render (`.claude/hooks/stop/wl_planqueue.py:297`) copies every byte outside the generated markers, so a new section survives regeneration.
  - `promoted_text` (`.claude/hooks/stop/wl_planqueue.py:46`) stops at the next `## ` heading. A `## Settings` section placed above `## Promoted` therefore never leaks into the entries.

## Design

**D1. One settings block.** agent/plans/QUEUE.md gains `## Settings`, placed between the header prose and `## Promoted`. It holds exactly one fenced block with info string `stop-hook`. Each line is `key: value`, optionally followed by ` -- <note>` (the note carries the operator's reason and date, replacing stop-hook.json's `since`/`reason`). These are the keys, defaults and accepted values:

```stop-hook
stop_hook: on        # on|off
turbo: off           # on|off
batch_size: 1        # integer >= 1: minimum finished plans before a turbo PR is offered for merge
writer_cap: 4        # integer >= 1: live writer agents at once (was wl_roster.WRITER_CAP)
cadence: on          # on|off (was WORKLIST_CADENCE)
agent_hint: on       # on|off (was WORKLIST_AGENT_HINT)
agent_pushback: on   # on|off (was WORKLIST_AGENT_PUSHBACK)
judge: on            # on|off (the standing half of WORKLIST_JUDGE)
```

**D2. One reader.**
- `wl_planqueue.settings(text) -> (Settings, problems)` is a frozen dataclass with fail-safe defaults. A missing section means all defaults and no problem. An unknown key, a bad value, a duplicate, a second fence or a section below Promoted is a problem: that key falls back to its default and the rest still parse. The fail-safe direction is hook on, turbo off, batch 1.
- `wl_planqueue.settings_for(root, rev="")` reads the working tree, or `git show rev:agent/plans/QUEUE.md` when a rev is given.
- `wl_planqueue.set_settings(text, updates) -> text` rewrites only the fence bytes. It creates the section above `## Promoted` when it is absent.
- `plan_gate` re-exports `settings_at(root, rev)` through its existing `_read` (`.claude/rediacc_hooks/plan_gate.py:88`), so the hook, guards and CI share one parser.
- Effective batch size is `batch_size if turbo else 1`, computed in one place (`plan_gate.batch_size(settings)`).

**D3. Migration: one source of truth. This is a clean break with no shims.**

| Switch | After | Env |
|---|---|---|
| `.ci/config/stop-hook.json` | `stop_hook:` | file deleted |
| `WORKLIST_CADENCE` | `cadence:` | read removed; `WORKLIST_CADENCE_MAX` (tuning) stays |
| `WORKLIST_AGENT_HINT` | `agent_hint:` | read removed; the `_MIN_*`/`_MAX_*` tuning knobs stay |
| `WORKLIST_AGENT_PUSHBACK` | `agent_pushback:` | read removed |
| `WORKLIST_JUDGE` | `judge:` is the standing policy | stays as a test seam only |

- **Judge precedence:** env `WORKLIST_JUDGE` set to `on` or `off` overrides QUEUE.md `judge:`, which overrides the default `on`. Any other env value is ignored.
- `wl_judge.JUDGE_DISABLED` becomes `wl_judge.disabled(settings)`, and `.claude/hooks/stop/wl_defersettle.py:574` calls the same function.
- `wl_agents.ENABLED` and `PUSHBACK_ENABLED` stop being import-time constants. They become `enabled(settings)` and `pushback_enabled(settings)`, called at `.claude/hooks/stop/wl_checks.py:1475`, `.claude/hooks/stop/wl_checks.py:1929` and `.claude/hooks/stop/wl_agents.py:466`.
- `run_stop` reads `settings_for(root)` once per stop and passes it down.
- **Fixtures** stop setting cadence and agent-hint through env. A new helper `wlfix.settings(**kw)` writes the fixture project's QUEUE.md through `set_settings`, the verb's own writer. Cadence defaults to `off` there, which keeps the reasoning recorded at `.claude/rediacc_hooks/tests/wlfix.py:530`.

**D4. `stop_hook: off`.**
- `_stop_hook_disabled` (`.claude/hooks/stop/worklist.py:1883`) reads `settings_for(root)`. It treats the hook as on when wl_planqueue cannot import or the block is malformed, the same "any doubt keeps the hook on" rule as today.
- When off, the bare Stop path emits a single `{"systemMessage": ...}` and exits 0. It runs no store load, gh read, judge or retro sync.
- The message costs nothing and carries:
  - (a) `Stop hook OFF (agent/plans/QUEUE.md stop_hook: off -- <note>)`;
  - (b) the `_BROKEN` sibling list when it is non-empty, which is already computed at import;
  - (c) the settings problems.
- The crash handler in `__main__` stays: a crash before the read still blocks. The worklist verbs are unaffected.

**D5. Turbo: continuous and parallel (supersedes the first draft's fixed batch).**
- Turbo has no maximum. While `turbo: on`, the live PR keeps taking plans: whenever a writer slot is free (live writers < `writer_cap`) and an eligible plan exists, the hook names the next one to start on a writer.
- Eligible, in `queue()` order (Promoted, then Generated): exists, has an open box, is not held (`.claude/hooks/stop/wl_planenforce.py:123`), is not already in the PR's plan set, and passes `block_plan_concurrency` against the live writers' plans (`Owns:`/`Concurrency:`). A `-- solo` Promoted entry (D11) is eligible only for an empty PR and then closes the PR to further plans.
- `plan_gate.next_turbo(root, live_plans, open_slots, rev="")` returns that list, prerequisites first (an unfinished prerequisite of a pick is picked before it, as `next_queued` does today).
- A plan joins the PR when the hook names it: `refresh_pr_body` appends it to the body's `Plan:` line (`with_plan_line` gains an append mode for turbo; turbo off keeps write-once). The PR's plan set is that line's plans plus their closure.
- "Start immediately": the turbo arm is evaluated on every stop, live PR included, so the stop after `turbo: on` lands already names plans to start.
- The session starts a plan ONLY when the hook names it (operator: "do not start the plans unless the stop hook pings you"); bug, red-CI and hook-integrity blocks outrank the turbo arm, so fixes come first. <!-- style-ok -->

**D6. Merge gate.**
- `plan_merge_refusal(root, body, rev)` reads `settings_at(root, rev)`. Guards pass the PR head (`.claude/rediacc_hooks/guards/block_admin_merge.py:304`, `.claude/rediacc_hooks/guards/block_push_to_protected_branch.py:361`).
- `Operational-Reason:` still admits. With turbo on at `rev`, a body naming any number of plans is admitted without a reason. Every named plan's boxes are checked (the `plans[0]`-only check goes), and so is every unfinished prerequisite in the closure.
- No minimum is enforced at merge (D-answers).

**D7. CI clock.**
- `clock_scope` (`.ci/scripts/quality/check_plan_implementation.py:227`) drops the unconditional queue head: the scope is the body's named plans plus their closure, else `[queue_head]` (no body or no `pull_request` event). The ticked-on-branch arm is unchanged.

**D8. Hook loop.**
- Turbo on, live PR, free slots, eligible plans: a new turbo arm (key `turbo-next`, T_MISSION) blocks with "TURBO: start <plan> on a writer (slot k of writer_cap); its first box is <box>". It names at most the free-slot count of plans.
- Turbo on, live PR, no free slot or no eligible plan, and fewer than `batch_size` plans finished: no new block; the existing PR PLAN SET OPEN and writer-roster checks hold the turn.
- Turbo on, at least `batch_size` plans finished (or nothing eligible left) and every named plan finished: the existing pr-finish path offers the merge. After the merge, LOOP NEXT names the next branch and the turbo picks for it.
- Turbo off: every arm is byte-identical to today (tests pin it).

**D9. The verb.**
- `worklist.py --queue-set <me> key=value ... [--note "<text>"]` checks identity, validates every pair before writing, rewrites through `set_settings`, writes atomically and prints `git add agent/plans/QUEUE.md`. It never commits.
- `--queue-set <me>` with no pairs prints the effective settings, the source of each value, and any problems.

**D10. PR #594.**
- #594's body names its plans and carries `Operational-Reason:`; this plan's `Plan:` entry is added with `gh api` and the reason extended ("operator 2026-10-04: turbo mode rides #594").
- Enabling turbo on this branch makes the turbo arm fire on #594 itself (D5, "start immediately"): queued plans the hook names join #594 as they start. That is the operator's intent; the per-commit and PR reviews cover each.

**D11. Solo marker.** A Promoted entry may end its note with ` -- solo` (`wl_planqueue.ENTRY` already captures the note). A solo plan runs alone in its PR under turbo. ci-consolidation is marked solo (the operator chose "One plan, one PR" for it); clean-review-ledger's "Own plan, next PR" meant "not riding #594", so it is not marked.

**D12. Writer cap.** `writer_cap` replaces the literal `.claude/hooks/stop/wl_roster.py:40` (`WRITER_CAP = 4`): `wl_roster.writer_cap(root)` reads the settings, and `.claude/rediacc_hooks/guards/block_agent_cap.py:101` and every `WRITER_CAP` reader call it. Default 4 when the block is missing or malformed.

## Boxes

- [ ] T1 Settings reader and writer in `.claude/hooks/stop/wl_planqueue.py`: `Settings`, `settings`, `settings_for`, `set_settings`. Proven by the new `.claude/rediacc_hooks/tests/test_wl_queue_settings.py` (defaults, every key, notes, unknown key, bad value, duplicate, two fences, section below Promoted, rev read, `set_settings` round-trip with byte-identical non-fence bytes, creation above Promoted). Mutation control: make an unknown key silently accepted, and the test must red.
- [ ] T2 Place the new pytest file in leg 2 of `.ci/config/shards/quality-pytest.json` (leg index at `.ci/config/shards/quality-pytest.json:204`, beside `test_plan_gate` at `.ci/config/shards/quality-pytest.json:389`). Proven by `npm run check:ci-shard-manifest-coverage`. Control: removing the id reds it.
- [ ] T3 `check:ci-plan-record` gains `RQ-SETTINGS` (`.ci/scripts/quality/check_plan_record.py:37` lists the checks): every settings problem is a finding. Proven by a fixture case in `.claude/rediacc_hooks/tests/test_wl_queue_settings.py` plus the gate's own planted control. Control: `turbo: onn` in a fixture QUEUE.md must red.
- [ ] T4 `.claude/rediacc_hooks/plan_gate.py`: `settings_at`, `next_turbo` (D5: queue order, held/finished/in-set filtered, prerequisites first, concurrency-compatible, solo handling) and `with_plan_line` append mode for turbo, `__all__` updated. Proven by `.claude/rediacc_hooks/tests/test_plan_gate.py` cases: held skipped, finished skipped, in-set skipped, a solo entry only for an empty PR, an exclusive plan not paired with a live writer's plan, prerequisites first, turbo off unchanged. Control: drop the held filter and the held case must red.
- [ ] T5 Rewrite `plan_merge_refusal` (`.claude/rediacc_hooks/plan_gate.py:216`) per D6. Proven by new rows in `test_plan_merge_refusal` (`.claude/rediacc_hooks/tests/test_plan_gate.py:123`): turbo on with every named plan ticked admitted at any count; the second named plan open refused; turbo on in the tree but off at `rev` refused; a reason still admits. Control: restore the `plans[0]`-only check and the second-plan-open row must red.
- [ ] T6 Guard docstrings and tests: `.claude/rediacc_hooks/guards/block_push_to_protected_branch.py:25` loses its "one Plan line" wording. Add a turbo-at-head case each to `.claude/rediacc_hooks/guards/test-block_admin_merge.py` and `.claude/rediacc_hooks/guards/test-block_push_to_protected_branch.py`. Control: make the guard read settings from the working tree, and the head-rev case must red.
- [ ] T7 `.claude/hooks/post-bash/refresh_pr_body.py:155`: turbo off writes `queue_head` once (today); turbo on appends each plan the hook named to the body's `Plan:` line. Proven by `.claude/rediacc_hooks/tests/test_plan_gate.py` next to `test_refresh_writes_the_queue_head_as_the_plan_line` (`.claude/rediacc_hooks/tests/test_plan_gate.py:181`): append adds without duplicating, turbo off identical to today. Control: append rewriting an existing entry must red.
- [ ] T8 CI clock per D7 in `.ci/scripts/quality/check_plan_implementation.py:227`. Update the C12 stand-ins (`.ci/scripts/quality/check_plan_implementation.py:803`, `.ci/scripts/quality/check_plan_implementation.py:864`) to `default_plans` and add control C15: a two-plan turbo body clocks both and no third queued plan; no body clocks the batch. Proven by `npm run check:ci-plan-implementation`, whose selftest runs the controls. Control: putting the head back unconditionally must fire C15.
- [ ] T9 `.claude/hooks/stop/wl_prscope.py`: `LoopState.turbo_picks` (from `next_turbo` with live writers and free slots), `own` from the body plans, and the post-merge next set. Proven by `.claude/rediacc_hooks/tests/test_wl_prscope.py` (turbo on a live PR with 2 free slots names 2 eligible plans; with 0 free slots names none; turbo off equals today). Control: ignoring live writers must red the 0-slot case.
- [ ] T10 The `turbo-next` arm in `.claude/hooks/stop/wl_checks.py` (after the CI/bug/pr-finish checks, near `.claude/hooks/stop/wl_checks.py:4272`), message `V_TURBO_NEXT` and the batch_size-aware pr-finish condition (D8); ARITY rows in `.claude/rediacc_hooks/tests/test_wl_message_catalogue.py`. Proven by `.claude/rediacc_hooks/tests/test_wl_loop_next.py` (turbo arm names plans and "start ONLY"; a red-CI block outranks it; turbo off byte-identical). Control: turbo arm firing with turbo off must red.
- [ ] T11 Migrate `stop_hook` per D4: rewrite `.claude/hooks/stop/worklist.py:1883` and `.claude/hooks/stop/worklist.py:1898`, add `N_STOP_HOOK_OFF` (with a literal fallback) and its ARITY row, delete `.ci/config/stop-hook.json`, and rewrite `test_l6` (`.claude/rediacc_hooks/tests/test_wl_leases.py:252`): off allows with the notice and no `decision`; a malformed block keeps the hook on; verbs keep working. Control: a stray `stop-hook.json` with `enabled:false` must no longer disable anything.
- [ ] T12 Migrate cadence, agent_hint and agent_pushback per D3: `.claude/hooks/stop/wl_checks.py:4935`, `.claude/hooks/stop/wl_agents.py:34`, `.claude/hooks/stop/wl_agents.py:393`. Add `wlfix.settings()`, drop `WORKLIST_AGENT_HINT` from `RESET_KNOBS` (`.claude/rediacc_hooks/tests/wlfix.py:77`) and the env at `.claude/rediacc_hooks/tests/wlfix.py:524`, and convert `.claude/rediacc_hooks/tests/test_wl_roster.py:688`, `.claude/rediacc_hooks/tests/test_wl_roster.py:801` and `.claude/rediacc_hooks/tests/test_wl_advisories_rotation.py:463`. Proven by `.claude/rediacc_hooks/tests/test_wl_cadence.py` flipping `cadence:` in the settings block. Control: setting env `WORKLIST_CADENCE=off` must change nothing.
- [ ] T13 Judge per D3: `wl_judge.disabled` replaces `.claude/hooks/stop/wl_judge.py:36` at `.claude/hooks/stop/worklist.py:453`, `.claude/hooks/stop/wl_checks.py:4714`, `.claude/hooks/stop/wl_checks.py:5190`, `.claude/hooks/stop/wl_checks.py:5214`, `.claude/hooks/stop/wl_checks.py:5222`, `.claude/hooks/stop/wl_checks.py:5257` and `.claude/hooks/stop/wl_defersettle.py:574`. Update the source pins at `.claude/rediacc_hooks/tests/test_wl_focus.py:623` and `.claude/hooks/stop/test-judge-schema.py:3083`. The messages at `.claude/hooks/stop/worklist_messages.py:1104`, `.claude/hooks/stop/worklist_messages.py:1412` and `.claude/hooks/stop/worklist_messages.py:1422` offer `judge: off` in QUEUE.md instead of the env var. Proven by a `.claude/rediacc_hooks/tests/test_wl_queue_settings.py` precedence table (env off > QUEUE on; env unset with QUEUE off gives off; env garbage gives QUEUE). Control: reversing the precedence must red.
- [ ] T14 Env registries: delete the three migrated names from `.ci/policy/worklist-env-registry.json` (`.ci/policy/worklist-env-registry.json:71`, `.ci/policy/worklist-env-registry.json:102`, `.ci/policy/worklist-env-registry.json:193`). Rewrite `WORKLIST_JUDGE`'s `why` (kind stays `handle`): "test seam only; standing on/off is QUEUE.md `judge:`; env on|off overrides". Remove the names from `.ci/config/env-manifest.json:987`, `.ci/config/env-manifest.json:992`, `.ci/config/env-manifest.json:1007`, `.ci/config/python-env-registry.json:1823`, `.ci/config/python-env-registry.json:1828` and `.ci/config/python-env-registry.json:1845`. Fix the "four on-default names" prose at `.ci/policy/README.md:418` and `.ci/rediacc_ci/quality/worklist_env_registry.py:3`. Proven by `npm run check:ci-worklist-env-registry`, `npm run check:ci-env-manifest` and `npm run check:ci-python-env-registry`. Control: leaving one stale entry must red the registry gate (it is both-directions).
- [ ] T15 The `--queue-set` verb in `.claude/hooks/stop/worklist.py`, its USAGE line (`.claude/hooks/stop/worklist_messages.py:2023`) and its usage/error strings with ARITY rows. Proven by `.claude/rediacc_hooks/tests/test_wl_queue_settings.py`: atomic write, invalid pair refused with the file untouched, no git commit made, bare form prints the sources. Control: a write that happens before validation must red the "untouched" case.
- [ ] T16 QUEUE.md prose: the header (agent/plans/QUEUE.md line 3, "One plan per PR by default") describes Settings, turbo and batch. Add the `## Settings` block with today's values (turbo off) and the stop-hook.json note carried over. Regenerate Generated with `npm run check:ci-plan-record -- --update`, which also lists this plan. Proven by `npm run check:ci-plan-record`.
- [ ] T17 Docs:
  - `CLAUDE.md:61` changes "works ONE plan per PR" to "one plan per PR, or with `turbo: on` a batch of `batch_size` queued plans; start a queued plan only when the hook names it; all switches live in agent/plans/QUEUE.md `## Settings`".
  - `.claude/commands/pr-merge.md:337`, `.claude/agents/pr-babysitter.md:3` and `.claude/agents/pr-babysitter.md:96` get the same rule.
  - `docs/agent-reference/ci-gates.md:421` gains the turbo admission.

  Proven by `npm run check:ci-plan-citations` and the docs gates in `ci:quick`.
- [ ] T18 Generated docs and locks: `npm run gen:docs` refreshes `scripts/data/doc-registry.md`, dropping the `stop-hook.json` row at `scripts/data/doc-registry.md:1084` and the env rows at `scripts/data/doc-registry.md:2076`, `scripts/data/doc-registry.md:2081` and `scripts/data/doc-registry.md:2096`. Run `npm run check:ci-gates-lock`, and regenerate with `npm run gen:gates-lock` only if it reds (no new gate id is expected). Proven by both checks green.
- [ ] T19 PR #594 per D10: add the `Plan:` line and extend `Operational-Reason:` with `gh api` (not `gh pr edit`, as `.claude/hooks/post-bash/refresh_pr_body.py` explains). Proven by `plan_merge_refusal` run on #594's body at head returning "" only once every box is ticked, and by the CI clock note listing exactly the three named plans.
- [ ] T20 Full suite and lane: run `npm run test:hooks` (all pytest shards, plus the hook `test-*.py` files), then `npm run ci:quick`, recording the receipt. Mutation sweep: re-run T5/T8/T10's controls, and each must red.
- [ ] T21 ENABLE NOW. The last implementation box: `worklist.py --queue-set d778be9d turbo=on writer_cap=4 batch_size=2 --note "operator 2026-10-04: turbo on"` on branch 1004-1, then commit agent/plans/QUEUE.md alone. Proven by `--queue-set d778be9d` printing `turbo: on (QUEUE.md)`, `npm run check:ci-plan-record` green, and the next Stop naming turbo picks (D5).
- [ ] T22 Writer cap per D12: `wl_roster.writer_cap(root)` replaces the literal at `.claude/hooks/stop/wl_roster.py:40`, used by `.claude/rediacc_hooks/guards/block_agent_cap.py:101` and every `WRITER_CAP` reader. Proven by `.claude/rediacc_hooks/tests/test_wl_roster.py` and `.claude/rediacc_hooks/guards/test-block_agent_cap.py` with `writer_cap: 2` in the fixture QUEUE.md (the third writer refused). Control: the literal 4 back in the guard must red the cap-2 case.
- [ ] T23 Solo marker per D11 in `.claude/hooks/stop/wl_planqueue.py` (`solo` on each entry) and agent/plans/QUEUE.md (ci-consolidation marked). Proven by a `.claude/rediacc_hooks/tests/test_wl_queue_settings.py` case and T4's solo case. Control: a solo entry batched with another plan must red.

## Open questions for the operator

All answered on 2026-10-04 (see "Operator answers" above).

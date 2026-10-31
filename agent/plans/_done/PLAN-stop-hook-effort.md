# PLAN: one effort level for the Stop hook

Status: done -- 2026-10-15, every box ticked (7 of 7); closed when check:ci-plan-record RF refused the open Status (operator order 2026-10-15, #1201d7b9). Was: approved. Operator /ask 2026-10-14: "Yes, as proposed (Recommended)" and "smart (Recommended)" for this session once it lands.
First-Seen: 2026-10-14
Owner: d778be9d
Depends-On: no-dep -- related, not ordered: PLAN-stop-hook-focus-mode.md and PLAN-stop-hook-turbo.md describe the switches this plan folds in
Operator ask (2026-10-14, verbatim): "Honestly disabling/enabling the stop hook, different options for focus, turbo etc. Can't we bind them into a single "effort"? Maybe: smart, low, high, ultra/turbo etc. Can you investigate and brainstorm? Maybe we can also have a modifiable list, to move some of the checks/tasks between the options instead of that complex switchings." <!-- style-ok -->
Approach: clean break. The replaced keys, the WORKLIST_FOCUS variable and the --focus verb go; no shims, no dual paths.
Priority: P1 -- operator-approved design, directly reduces the switch toggling seen 15 times in ten days
Concurrency: exclusive -- it rewrites the settings parser every Stop-hook check and five guards read
Owns: .claude/config/effort.json, .claude/hooks/stop/wl_planqueue.py, .claude/hooks/stop/wl_standdown.py, .claude/hooks/stop/wl_checks.py, .claude/hooks/stop/wl_judge.py, .claude/hooks/stop/worklist.py, .claude/hooks/stop/worklist_messages.py, .claude/rediacc_hooks/guards/block_turbo_early_push.py, .claude/rediacc_hooks/guards/block_focus_spawn.py, .claude/rediacc_hooks/tests/*.py, .ci/scripts/quality/check_plan_record.py, .ci/policy/worklist-env-registry.json, agent/plans/QUEUE.md, CLAUDE.md, .claude/output-styles/*.md

## Design (from the read-only investigation of 2026-10-14)

Today: 12 switches in the QUEUE.md `## Settings` fence (parsed at .claude/hooks/stop/wl_planqueue.py:94-101), a per-session `--focus babysit|merge` (.claude/hooks/stop/worklist.py:246-280, keep-list .claude/hooks/stop/wl_standdown.py:123), two automatic stand-down profiles (CAP_WAIT, PR_LOOP; .claude/hooks/stop/wl_standdown.py:120-129), about 130 env knobs (.ci/policy/worklist-env-registry.json), about 75 blocking check keys (registry .claude/hooks/stop/wl_checks.py:3709) and 52 advisory keys (outq_add, .claude/hooks/stop/wl_checks.py:1243). `stop_hook: off` returns before every check (.claude/hooks/stop/worklist.py:2192-2196), safety checks included, and it was flipped 10 times between 2026-10-04 and 2026-10-14.

Levels, each a superset of the one before:
- `quiet`: the FLOOR only (hook-blind, event-unparseable, cl-shape, adhoc-watch*, trapguard-errors, ci-red, ci-unreadable, roster-dead, roster-cap, unread-reports, wake-timer, agent-state and agent-absent when compaction is due). Judge off. Replaces `stop_hook: off`.
- `low`: FLOOR plus mission (open-items, plan-unimplemented, pr-finish, pr-review, commit-review, turbo-next, loop-next). Judge off.
- `smart` (default): plus owed work and record integrity; no-remaining and out-of-sync advise only; the judge runs on its five blocking keys without riders.
- `high`: every check as today; full judge with riders.
- `ultra`: high plus the throughput bundle (turbo on, writer_cap 15, plan_concurrency 5, batch_size 3).

`.claude/config/effort.json` holds one threshold per check key, `{"block": "<level>", "advise": "<level>"}` or `"floor"`, and each level's switch bundle. Settings resolve as effort, then bundle, then explicit per-key overrides in the QUEUE.md fence, into the one Settings object every guard already reads (plan_gate.settings_at, .claude/rediacc_hooks/plan_gate.py:171). The FLOOR is a literal frozenset in a sealed module beside wl_standdown.CORE, read from no environment variable.

Focus becomes `phase: build|babysit|merge`, a per-session overlay that only parks work and never adds a block. CAP_WAIT and PR_LOOP stay automatic.

The judge also gets two fixes found in this session: it is fed each item's state and latest tick evidence, not only its add text, so finished work is not re-raised; and sanitize_next_action (.claude/hooks/stop/wl_judge.py:1063) consults a rule list starting with the release-age window (.ci/config/release-age.json), so it cannot advise pinning a release inside its soak.

## Tasks

- [x] E1: `.claude/config/effort.json` with every blocking and advisory key once, the five level bundles and the FLOOR marked `floor` -- acceptance: a new effort-table gate exits 0, and planting an unknown key, a missing key, a demoted FLOOR key or `block` below `advise` each exits 1
    (ticked) 2026-10-14T09:20:28Z by d778be9d: commit:5fa63c3c0 effort series 3284097b9 0c20f339b 5fa63c3c0; test_wl_effort/judge_state/queue_settings 106 passed; effort-table gate planted controls rc 1 each; check:ci-plan-record rc=0
- [x] E2: wl_planqueue resolves effort -> bundle -> overrides into Settings; `stop_hook`, `cadence`, `agent_hint` and `agent_pushback` leave the fence as keys and remain only as overrides -- acceptance: pytest .claude/rediacc_hooks/tests/test_wl_queue_settings.py exits 0 with cases for every level and an override that wins
    (ticked) 2026-10-14T09:20:29Z by d778be9d: commit:5fa63c3c0 effort series 3284097b9 0c20f339b 5fa63c3c0; test_wl_effort/judge_state/queue_settings 106 passed; effort-table gate planted controls rc 1 each; check:ci-plan-record rc=0
- [x] E3: the Stop hook applies each key's threshold at the resolved level (block, advise or off) with the FLOOR blocking at every level -- acceptance: a test drives one key of each family through all five levels and the FLOOR keys at `quiet`
    (ticked) 2026-10-14T09:20:31Z by d778be9d: commit:5fa63c3c0 effort series 3284097b9 0c20f339b 5fa63c3c0; test_wl_effort/judge_state/queue_settings 106 passed; effort-table gate planted controls rc 1 each; check:ci-plan-record rc=0
- [x] E4: `--focus` becomes `--phase build|babysit|merge`, WORKLIST_FOCUS=off is removed with its registry entry, and block_focus_spawn reads the phase -- acceptance: pytest on the focus and standdown tests exits 0 and `worklist.py --focus` exits 2 as an unknown verb
    (ticked) 2026-10-14T09:20:32Z by d778be9d: commit:5fa63c3c0 effort series 3284097b9 0c20f339b 5fa63c3c0; test_wl_effort/judge_state/queue_settings 106 passed; effort-table gate planted controls rc 1 each; check:ci-plan-record rc=0
- [x] E5: the judge receives item state and tick evidence, and sanitize_next_action refuses an order that applies a pin inside the release-age soak -- acceptance: a test with a ticked item's stale add text yields no re-raise, and a planted "apply the 8.7.0 pin now" order inside the soak is stripped
    (ticked) 2026-10-14T09:20:33Z by d778be9d: commit:5fa63c3c0 effort series 3284097b9 0c20f339b 5fa63c3c0; test_wl_effort/judge_state/queue_settings 106 passed; effort-table gate planted controls rc 1 each; check:ci-plan-record rc=0
- [x] E6: QUEUE.md `## Settings` carries `effort: smart`, CLAUDE.md, the output style and the turbo and focus plans describe effort and phase, and the guards' fixtures use the new fence -- acceptance: npm run check:ci-plan-record, check:ci-prose-style and the hook test suite exit 0
    (ticked) 2026-10-14T09:20:34Z by d778be9d: commit:5fa63c3c0 effort series 3284097b9 0c20f339b 5fa63c3c0; test_wl_effort/judge_state/queue_settings 106 passed; effort-table gate planted controls rc 1 each; check:ci-plan-record rc=0
- [x] E7: this session's QUEUE.md switches from `stop_hook: off` to `effort: smart` -- acceptance: worklist.py --queue-set <me> effort=smart prints the resolved bundle and a Stop runs the smart profile
    (ticked) 2026-10-14T09:20:42Z by d778be9d: commit:5fa63c3c0 --queue-set effort=smart resolved judge core, cadence/agent_hint/agent_pushback on from the bundle, 61 block (12 FLOOR) and 14 advise

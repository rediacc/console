# PLAN: stop-hook focus mode, a wind-down stand-down for /pr-babysit and /pr-merge

Status: draft
Owner: d778be9d
First-Seen: 2026-09-25
Depends-On: PLAN-stop-hook-cap-saturated-wait.md
Worklist: none yet (the lead adds one item per box on approval)

**Operator order, 2026-09-25 (spec section Y, verbatim):**

> Add a session 'focus mode' that /pr-babysit and /pr-merge switch on (worklist verb --focus <me> babysit|merge, ended by --focus off or when the PR merges). While it's on: Finish, don't start. Running writers and in-flight items are allowed to finish. No new writers are spawned: the pre-agent guard refuses, except for babysit/merge fix work. The queue-slot and free-slot pushes are silent. The stop hook stops demanding open plan boxes, plan-adoption tracking, queued work and hygiene. It keeps the checks that protect the PR: CI red, a dead watch, unread reports, STATE.md near compaction, and hook integrity. Judge calls are skipped, as in the cap-saturated wait, and advisories are batched instead of emitted every stop, so the mode uses fewer tokens. When focus ends, the stop hook prints one line listing what was parked. Tests: focus on silences a plan-box push, keeps a CI-red block, and refuses a spawn; focus off restores all three. This mostly reuses the keep-list mechanism I just built for the cap-saturated wait.

**Why this depends on PLAN-stop-hook-cap-saturated-wait.md.** This plan moves that plan's keep-list out of `.claude/hooks/stop/wl_roster.py:53-111` and generalises it. It also re-targets that plan's tests (`.claude/rediacc_hooks/tests/test_wl_cap_wait.py:228-243`, `:279-313`). The code has landed, but its only box (T1) is still `[ ]`, so `wl_backlog._redirect` treats the edge as blocking. T0 below closes it.

**For spec X's migration (not written here, because X defines the grammar):** proposed `Priority: P0` (operator order "Y first"), `Concurrency: exclusive`, `Owns: .claude/hooks/stop/wl_standdown.py, .claude/hooks/stop/wl_checks.py, .claude/hooks/stop/wl_store.py, .claude/hooks/stop/wl_ci.py, .claude/hooks/stop/worklist.py, .claude/hooks/stop/worklist_messages.py, .claude/rediacc_hooks/guards/block_focus_spawn.py, .claude/commands/pr-*.md, .claude/agents/pr-babysitter.md`.

**Line numbers** refer to the working tree on `0923-1` on 2026-09-25. Re-anchor on the named function or constant if they drift.

## Tasks

One writer does T1-T4 and T6, in order: T1-T3 share `wl_checks.py`, `wl_store.py` and `worklist_messages.py`, and T4 imports T1's and T2's API. The lead does T0, T5 and T7.

- [x] T0 Lead: tick PLAN-stop-hook-cap-saturated-wait.md T1 with evidence (the passing `test_wl_cap_wait.py` run and its commit), and set its `Status:` to done, so this plan's `Depends-On:` edge resolves.
- [x] T1 [A] Create `.claude/hooks/stop/wl_standdown.py`, holding the stand-down profiles (section 2). Move `CAP_WAIT_KEEPS`, `CAP_WAIT_KEEP_PREFIXES`, `CAP_WAIT_COMPACTION_KEYS` and `cap_wait_keeps` out of `wl_roster.py:53-111`. Keep `cap_saturated_wait` in `wl_roster.py`, because it needs `WRITER_CAP`. Make `wl_checks.py:4096-4142` use `wl_standdown.keeps(profile, ...)`. Re-target `test_wl_cap_wait.py` c9/m1/m2 to the new file. Add `wl_standdown.py` to `sealed_modules` in `.ci/policy/worklist-env-registry.json`. This is a pure refactor plus the `pr-finish` always-tier fix, and the cap-wait suite must pass before T2 starts.
- [x] T2 [A] The focus state in the store (section 1):
  - a `focus` event kind and `S.focus_event`;
  - a `focus` out-parameter on `_fold_events`, carried on `Fold`;
  - `snapshot_events` re-emits the active focus;
  - the verb `worklist.py --focus <me> babysit|merge|off [--pr <n>] [--branch <b>]`, plus a status form;
  - queue leases are accepted with a free slot while focus is on (`worklist.py:1136-1145`).
- [x] T3 [A] The Stop-hook integration (sections 3-6):
  - resolve focus early and end it on merge or expiry;
  - the FOCUS profile filter and the `focus-pr-items` key;
  - judge skips at all four sites;
  - arm `ci_trouble` and `pr_body_freshness` from the focus branch;
  - skip the `plan-tasks`, `plan-backlog` and `plan-clock` producers;
  - advisory batching, hint suppression and the one-line parked summary;
  - the messages, and their `ARITY` rows in `test_wl_message_catalogue.py`.
- [x] T4 [A] Add the guard `.claude/rediacc_hooks/guards/block_focus_spawn.py` (`CHAIN = "pre-agent"`, `ORDER = 4`, `OWN_SUITE = True`, with `DEFECT` and `EDGE_CASES`) and its suite `.claude/rediacc_hooks/guards/test-block_focus_spawn.py`. Register it in `scripts/data/hook-inventory-baseline.json` and in `sealed_modules` (section 7).
- [ ] T5 Lead: edit the skills and docs (section 8): `.claude/commands/pr-babysit.md`, `.claude/commands/pr-merge.md`, `.claude/agents/pr-babysitter.md` and `CLAUDE.md:99-102`.
- [x] T6 [A] Add `.claude/rediacc_hooks/tests/test_wl_focus.py` with the cases and mutation controls in section 9. Update `.claude/hooks/stop/test-always-tier.py` for the new ladder key.
- [ ] T7 Lead: run `.ci/cache/toolchain/uv-tools/pytest/bin/python -m pytest .claude/rediacc_hooks/tests/test_wl_focus.py .claude/rediacc_hooks/tests/test_wl_cap_wait.py .claude/rediacc_hooks/tests/test_wl_message_catalogue.py .claude/rediacc_hooks/tests/test_wl_event_store.py .claude/rediacc_hooks/tests/test_guards_differential.py .claude/rediacc_hooks/tests/test_dispatch.py`, then `python3 .claude/hooks/stop/test-always-tier.py`, then `python3 .ci/scripts/quality/check_plan_boxes.py --update` for this plan's ledger row.

## 1. Where focus state lives: a `focus` event in the worklist JSONL store, per session

**Event shape.** It is written by `S.focus_event`, placed next to `status_event` (`wl_store.py:1233`), through `append_events`, so it lands in the session's own `agent/worklist/<slug>.jsonl`:

```json
{"ev":"focus","at":"<stamp>","by":"<me8>","o":"<me8>","mode":"babysit|merge|off",
 "branch":"<PR head ref>","pr":612|null,"why":"operator|merged|closed|expired|pr-resolved"}
```

- **Use `branch`, not `br`.** `append_events` sets `br` to the checkout branch at write time (`wl_store.py:732-735`). Writing `off` from `main` after `/pr-merge` must not rewrite which PR the focus was on.
- **`o` must be non-empty.** `C.owned_by_me(None, …)` is True (`wl_core.py:168-175`), so an untagged focus event would apply to every session. Both the verb and the fold reject an empty owner.

**Fold.**
- Add `focus=None` as an out-parameter to `_fold_events` (`wl_store.py:859`), handled like `statuses`: `elif kind == "focus": if focus is not None and ev.get("o"): focus[ev["o"][:8]] = dict(ev); continue`. It goes beside the `status` branch at `:914-923`.
- Pass a `focus_box` through `build()` (`:1065-1069`).
- Add `self.focus` to `Fold.__init__` (`:1017-1022`) and to the construction at `:1147`.
- The latest event wins because the fold is chronological, with the `ns` tiebreak from `:736`.

**Resolution.** `wl_standdown.active_focus(fold.focus, owned)` returns the newest event over every owner key where `owned(key)` holds, and returns None when its `mode == "off"`. The caller passes `lambda o: C.owned_by_me(o, session_id)`, so a proven lineage edge carries focus across compaction.

**Compaction survives.** `snapshot_events` (`wl_store.py:1412-1440`) appends, for each owner, the latest focus event only when its mode is not `off`. An ended focus is history, and dropping it is correct.

**The verb.** It lives in `worklist.py` beside `--intent` (`:2096-2141`) and sits before the unknown-verb catch (`:2300`), with `M.CLI_FOCUS_USAGE` next to `CLI_INTENT_USAGE` (`worklist_messages.py:644`) and a line in `M.USAGE`.
- `--focus <me> babysit|merge [--pr <n>] [--branch <b>]`:
  - `_identity_or_die(me, _die2)`;
  - the branch defaults to `C.git_branch`, and the verb refuses `main` or a detached HEAD;
  - without `--pr` it makes one `gh pr list --head <branch> --state open --json number` call; on failure it records `pr: null` and says so (the hook fills it in, section 3).
- `--focus <me> off`: writes `mode: off, why: operator`. If focus was not on, it prints that and exits 0.
- `--focus <me>`: prints mode, since, branch, PR and the parked count so far, read from `S.load_state(...)["standdown"]`. This is the post-compaction recovery read.

**Queue leases while focused.** `worklist.py:1136-1145` refuses `worker:queue` whenever a writer slot is free ("start the work instead"). In focus, starting the work is exactly what is forbidden, so the refusal is skipped when `active_focus` holds. Without this, work refused at spawn cannot be parked as the guard's own message instructs.

## 2. The stand-down profile (generalising the cap-wait keep-list)

The new module `.claude/hooks/stop/wl_standdown.py` is sealed, uses stdlib only, reads no environment, and is pure:

```python
class Profile(NamedTuple):
    name: str
    keeps: frozenset          # exact keys kept
    prefixes: tuple           # keys kept whatever their suffix
    always_keeps: frozenset   # kept only when always=True (a hook-bug branch)
    compaction_keys: frozenset  # kept only when compaction_due

def keeps(profile, key, always, compaction_due) -> bool
```

- **CORE** (shared by both profiles; the cap-wait list minus its cap-specific keys):
  - `event-unparseable`, `hook-blind`, `cl-shape`, `adhoc-watch`, `adhoc-watch-broken`;
  - `agent-bootstrap`;
  - `unread-reports`;
  - `completion`, `found-not-fixed`, `deferred-finding`, `deflected-finding`;
  - `roster-cap`, `roster-silent`, `roster-unleased`, `roster-dead`;
  - `ladder-gone`, `ladder-idle`.
- **PREFIXES:** `agent-pushback:`, `giveup-claim:`.
- **ALWAYS_KEEPS:** `pr-finish`. This fixes the cap-wait gap in finding 3.
- **COMPACTION:** `agent-state`, `agent-absent`.
- **`CAP_WAIT = Profile("cap-wait", CORE | {"queue-slot","defer-expired","undefaulted"}, …)`.** This is exactly today's set plus the `pr-finish` always fix.
- **`FOCUS = Profile("focus", CORE | {...}, …)`**, where the extra keys are:
  - `ci-red`, `review-red`, `ci-unreadable`, `review-unreadable`, `pr-unreadable`;
  - `pr-finish`, `pr-stale`, `diverged`;
  - `bg-report`;
  - `focus-pr-items`.

**Each key literal appears exactly once in the file.** This keeps every mutation control unambiguous (`mutated_hook` asserts `count(old) == 1`, `test_wl_cap_wait.py:269-273`), and it keeps the c9 producer scan meaningful.

**Precedence.** When both states hold, FOCUS governs. Focus is the operator's explicit declaration, and its judge skip already covers the cap wait's. `_profile = FOCUS if _focus else CAP_WAIT if _in_cap_wait else None`.

**Other constants in this module:**
- `FOCUS_MODES = ("babysit","merge")`;
- `FOCUS_BATCH_MIN = 30`;
- `FOCUS_MAX_HOURS = 24`;
- `FOCUS_PR_TTL_S = 180`;
- `FOCUS_ADVISORY_KEYS = {"ci-queue","ci-report","unread-reports","ladder","focus-ended"}`;
- `FOCUS_FIX_RE = re.compile(r"\bfocus-fix:#?([0-9a-f]{6,})\b")`;
- helpers `pr_token(focus) -> "pr:<n>"`, `pr_linked(text, focus)` and `batch_due(sd, now)`.

`FOCUS_BATCH_MIN` and `FOCUS_MAX_HOURS` are pinned as `literals` in the registry entry.

## 3. How focus starts and ends on each stop, and how the hook learns the PR merged

**Where it runs.** In `run_stop`, right after `state_doc` loads (`wl_checks.py:2268`) and before `classify_items` (`:2342`):

1. `_focus = wl_standdown.active_focus(fold.focus, owned)`.
2. If `_focus` is set, check two end conditions in order:
   - **Expiry:** the on-event is older than `FOCUS_MAX_HOURS`. Re-issuing the verb renews it. This backstop stops a forgotten focus from parking everything indefinitely.
   - **PR finished:** `wl_ci.focus_pr_end(root, worklist, session_id, _focus)` returns `"merged"`, `"closed"` or `""`.
3. On an end reason, write `S.focus_event(..., "off", why=reason)` and set `_focus = None`. This stop then runs the full battery.
4. If focus was on at the last stop and is now off (`state_doc["standdown"]["focus_at"]` is set and differs from the active on-event), queue the parked summary (section 6) and drop `state_doc["standdown"]`. This covers ending by the verb, by merge, and a flip from off back to on.

**The cheap merge check (`wl_ci.focus_pr_end`, new, next to `ci_trouble` at `wl_ci.py:710`):**
- It makes one GraphQL call through `_gh_json`: `repository{pullRequests(headRefName:"<branch>",states:[MERGED,CLOSED],first:5,orderBy:{field:UPDATED_AT,direction:DESC}){nodes{number state mergedAt closedAt}}}`.
- It picks the node whose `number == focus.pr`, or when the PR number is unknown, the newest node closed after `focus.at`, so a reused branch name cannot end it.
- It is cached in a `.focuspr-<me8>` sidecar for `FOCUS_PR_TTL_S`.
- **Cost:** at most one small call per 3 minutes, only while focus is on, and zero when focus is off.
- **When the read fails:** it returns `""`, so focus continues, and queues a class-1 advisory `focus-pr-unreadable`. The 24-hour cap bounds a permanently blind check.
- **A closed but unmerged PR** also ends focus. This is a judgment call: a closed PR has nothing left to protect.

**Filling in the PR number.** When `_focus.pr` is null and the CI read below returns `info["pr"]`, append a focus event with the same mode and `why: pr-resolved`. The guard needs the `pr:<n>` token in the store.

**Arming the CI read from the focus.**
- `wl_ci.ci_trouble` (`wl_ci.py:710-738`) gains `ref=None, owned=False`: `ref = ref or os.environ.get("WORKLIST_PUBLISH_REF","")`, and the `sole_live_session` early return (`:736-738`) is skipped when `owned`.
- `pr_body_freshness` (`wl_ci.py:52-60`) gains `ref=None` the same way.
- The call sites at `wl_checks.py:3373` and `:3409-3415` pass `ref=_focus["branch"], owned=True` when focused.
- The focus verb is the session declaring the PR its own, which is the one fact the multi-session gate could not know.
- The ceiling and acknowledgement exits (`wl_ci.py:773-789`) are unchanged.

## 4. The checks kept and silenced (the FOCUS profile), with their keys as they exist in code

### Kept: these still block in focus

| Operator's category | Key(s) | Producer |
|---|---|---|
| CI red / the PR itself | `ci-red`, `review-red` | `wl_checks.py:3430`, `:3486` |
| | `ci-unreadable`, `review-unreadable`, `pr-unreadable` (blind reads of the PR) | `:3419`, `:3484`, `:3382` |
| | `pr-finish` (the babysit finish line; always-tier hook-bug branch too) | `:3558`, `:3577` |
| | `pr-stale` (body older than the push, which reds `Quality / Static` next round) | `:3380` |
| | `diverged` (remote ahead of the publish ref, so the next push clobbers or fails) | `:3329` |
| | `focus-pr-items` (new: open items carrying `pr:<n>`, the PR's own fix work) | added beside `open-items`, `:2997` |
| | advisories `ci-report`, `ci-queue` (never batched) | `:3586`, `:3392` |
| A dead watch | `bg-report` (a shell whose stream stopped, not OS-confirmed) | `:2956`, `:2971` |
| | `adhoc-watch`, `adhoc-watch-broken` | `:3405`, `:3399` |
| | `ladder-gone`, `ladder-idle` | `:3885`, `:3893` |
| | `roster-dead`, `roster-silent`, `roster-unleased`, `roster-cap` (running writers allowed to finish still owe liveness) | `:2886`, `:2873`, `:2880`, `:2858` |
| Unread reports | `unread-reports` (+ its young advisory, never batched) | `:3736`, `:3738`, `:3740` |
| STATE.md near compaction | `agent-state`, `agent-absent`, only when `compaction_due` (same computation as `:4098-4106`) | `:3655`, `:3680` |
| Hook integrity | `event-unparseable`, `hook-blind`, `cl-shape` (exact key only) | `:2996`, `:4021`, `:3796` |
| One-shot latches (I1; hiding them spends them unseen) | `agent-bootstrap`, `agent-pushback:*`, `giveup-claim:*` | `:3672`, `:3608`, `:3623` |
| Ledger honesty (one-turn exits, start nothing) | `completion`, `found-not-fixed`, `deferred-finding`, `deflected-finding` | `:3135`, `:3960`, `:3967`, `:3979` |

### Silenced: parked, counted, and named on exit

| Operator's category | Key(s) | Producer |
|---|---|---|
| Open plan boxes | `plan-unimplemented`, `plan-drift` | `:3319`, `:3211` |
| | `cl-producing`, `cl-flip`, `cl-waves`, `cl-foreign`, `cl-foreign-waves`, `cl-shape:<slug>` | via `:3792` (`wl_checklist.py:340-441`) |
| | advisories `plan-tasks`, `plan-clock` (producers skipped in focus) | `:3270`, `:3321` |
| | `plan-fidelity` (a paid call, never computed; its guard at `:4002` extends) | `:2188` |
| Plan adoption tracking | `plan-adopted` | `:3243` |
| Queued work | `open-items` (all except PR-linked), `queue-slot`, `defer-expired`, `undefaulted`, `unjustified` | `:2998`, `:2892`, `:3077`, `:3060`, `:3104` |
| | `idle-stall`, `unblocked-claim`, `solo-grind`, `sweep-moment`, `idle`, `ci-waiting`, `stuck` | `:3019`, `:3021`, `:3643`, `:3056`, `:3875`, `:3949`, `:2985` |
| | `ladder-investigate`, `ladder-resolve` (age-only rungs), `intent-expired`, `pending-ask` | `:3879`, `:3900`, `:3188`, `:3039` |
| | advisory `plan-backlog:*` (producer skipped: adding it spends `backlog_nominated` at `:3297-3303`) | `:3289` |
| Hygiene | `stale-local`, `submodule`, `loop-died`, `many-work-crons`, `broken-schedule`, `bg-orphan` | `:3327`, `:3351`, `:3592`, `:3798`, `:3815`, `:3990` |
| | `unconfirmed`, `unstated`, `mislabelled`, `uncited`, `out-of-sync`, `no-remaining` | `:3828`, `:3996`, `:3998`, `:3954`, `:4016`, `:4037` |
| | `agent-state`, `agent-absent` outside the late band | `:3655`, `:3680` |
| Judge | every exit; the admission detector still runs (as in the cap wait) | `:4390`, `:4412-4415`, `:4421-4423`, `:4457` |

**Judgment calls beyond the spec's literal list, for operator veto:**
- `pr-finish`, `pr-stale`, `diverged`, `review-red` and `roster-silent` are kept.
- `submodule` and `pending-ask` are dropped.
- A closed but unmerged PR ends focus.
- The 24-hour cap applies.
- The guide is suppressed on a focused allow (section 6).

**`focus-pr-items`.** At `wl_checks.py:2997`, when focused: `_pr_open = [i for i in open_items if wl_standdown.pr_linked(i, _focus)]`; if any, `vadd("focus-pr-items", False, M.V_OPEN_ITEMS % (...))`. `open-items` is still produced unconditionally and dropped by the profile, so it is counted as parked. Add `"focus-pr-items"` to `PRIORITY_LADDER` T_MISSION (`wl_checks.py:2012-2034`). Without this, the babysit loop's own fix items would park along with everything else.

**The filter.** Replace the cap-only block at `wl_checks.py:4096-4142` with one block over `_profile`:
- compute `_compaction_due` as now;
- `_dropped` / `violations` go through `wl_standdown.keeps(_profile, k, a, _compaction_due)`;
- the compaction note is `N_CAP_WAIT_COMPACTION` or the new `N_FOCUS_COMPACTION`;
- the same `bgwait_due` stand-down;
- bookkeeping: `state_doc["capwait"]` stays as-is for the cap profile. For focus, `state_doc["standdown"]` gets `{"focus_at", "mode", "pr", "parked": {base_key: stops}, "adv_held", "batch_at"}`, where the base key is the part before `:`;
- the allow note is `N_CAP_WAIT` or `N_FOCUS`.

**Judge and stuck.** Define `_in_standdown = _in_cap_wait or bool(_focus)`. Use it in place of `_in_cap_wait` at `:2761` (stuck `supervised=`), `:4002` (planfid), `:4390` (audit batch), `:4422` (admission path) and `:4457` (main judge). Pass `disabled=wl_judge.JUDGE_DISABLED or _in_standdown` to `wl_defersettle.build_batch` at `:4413-4415`.

## 5. The spawn guard and the fix-work exception

The new guard `.claude/rediacc_hooks/guards/block_focus_spawn.py` copies `block_agent_cap.py`'s shape: `CHAIN = "pre-agent"`, `ORDER = 4` (contiguous after the cap guard's 3; `test_dispatch.py:117` checks contiguity), `OWN_SUITE = True`, a `DEFECT` tuple and `EDGE_CASES`. It reads no environment. Its decision, for an `Agent`/`Task` call:

1. **No active focus → ALLOW.** It locates the store the way the cap guard does (`C.project_root(C.project_start({"cwd": cwd}))`), `S.load(worklist, sync=False)`, then `wl_standdown.active_focus`.
2. **A read-only type → ALLOW.** It reuses `wl_roster.read_only_types`, as in `block_agent_cap.py:96-98`.
3. **`mode == "babysit"` and `subagent_type == "pr-babysitter"` → ALLOW.** This is the `/pr-babysit bg` loop itself.
4. **Babysit/merge fix work → ALLOW.** The spawn declares it with `focus-fix:#<item-id>` in `description` or `prompt`. The id must name a store item that:
   - is owned by this session (`C.owned_by_me` with a non-empty owner);
   - is in state `[ ]` or `[>]`;
   - carries the focus PR's `pr:<n>` token in its text.

   A bare label is not enough. The item is a store fact the Stop guide shows, and the P2.2 auto-lease (`wl_checks.py:2314-2341`) leases it to the new worker because `#<id>` appears in its first prompt.
5. **Anything else → DENY**, with `REFUSED_FOCUS`. It names the focus (mode, PR, since) and prints three exits:
   - declare fix work (`--add <me> "... pr:<n>/fix"`, then put `focus-fix:#<id>` in the spawn prompt);
   - park it (`--add`, then `--lease <me> <id> +120 worker:queue`, which section 1 makes legal);
   - `--focus <me> off`.

   It appends `{"at","kind","desc"}` to `worklist.with_suffix(".focusrefused-<me8>.jsonl")` for the parked summary, the way the ask-refusals ledger is kept.

It fails open when it cannot read the store, with a stderr note, the same contract as `UNCOUNTABLE` (`block_agent_cap.py:75-79`). The writer cap still applies to allowed spawns, because the cap guard at ORDER 3 runs first.

**`DEFECT`:** `("if not wl_standdown.pr_linked(", "if False and not wl_standdown.pr_linked(")`, which accepts any owned item as fix work.

## 6. Advisory batching, token cuts, and the one-line parked summary

**Filtering the queue.**
- `outq_drain` (`wl_checks.py:1313`) and `outq_digest` (`:1384`) gain `only=None`, a key predicate that restricts the candidates. Entries outside it stay queued untouched.
- On a focused **block**, the digest at `:4246` passes `only=lambda k: k in FOCUS_ADVISORY_KEYS` unless `batch_due`.
- On a focused **allow**, the drain at `:5041` passes the same predicate, so kept keys release in full every stop. When `batch_due`, `outq_digest` also delivers everything else as one line per entry, and multi-line bodies stay queued until focus ends.
- `batch_at` restamps on every release. `adv_held` counts what is held.

**Other token cuts while focused:**
- the block hint (`:4314-4322`) and the allow hint and popup (`:5050-5055`) are skipped;
- the guide is not emitted on a focused allow (`:4971`); `N_FOCUS` replaces it;
- there is no judge stamp, because the judge never runs.

**`N_FOCUS` (one line, every focused allow):** `FOCUS MODE (%s PR #%s since %s): %d check(s) parked, %d advisory(ies) held; CI red, dead watches, unread reports, STATE.md near compaction and hook integrity still block. Ends on --focus %s off or when the PR merges.`

**`N_FOCUS_ENDED` (the parked summary; one line, capped at 300 characters, top 6 keys then "+N more"):** `FOCUS ENDED (%s): parked for %s: %s; %d advisory(ies) held, draining from this stop; %d writer spawn(s) refused. The full battery applies from this stop.`
- It is queued with `outq_add(..., "focus-ended", text, 0, sticky=True)` on the stop that detects the end.
- A one-line priority-0 sticky entry is delivered by the block digest and by the allow drain alike, so it survives every exit path. The same queue-at-compute-time argument is at `wl_checks.py:1180-1182`.
- The refused count comes from the `.focusrefused-<me8>.jsonl` rows since `focus_at`.

Register `N_FOCUS`, `N_FOCUS_ENDED`, `N_FOCUS_COMPACTION`, `REFUSED_FOCUS` (guard-local) and `CLI_FOCUS_USAGE` in `ARITY` (`test_wl_message_catalogue.py:103-104` pattern).

## 7. Wiring

- **Sealed modules.** Add `.ci/policy/worklist-env-registry.json` `sealed_modules` entries for `.claude/hooks/stop/wl_standdown.py` (literals `FOCUS_BATCH_MIN: 30`, `FOCUS_MAX_HOURS: 24`) and `.claude/rediacc_hooks/guards/block_focus_spawn.py`.
- **Hook inventory.** Add the guard to `scripts/data/hook-inventory-baseline.json`, beside `:11`.
- **No new `_MODS` entry.** `wl_checks` imports `wl_standdown` directly, as it does `wl_roster` (`wl_checks.py:44`). LKG snapshots every `wl_*.py` (`wl_lkg.py:46`).
- **Dead-code test.** It scans guards as consumers (`test_wl_event_store.py:610-613`), so defs used only by the guard are not flagged.
- **PostCompact.** Add one line naming an active focus to the `--post-compact` output (`worklist.py:2070`). A compacted babysitter must know that spawns are refused.

## 8. Skill and doc edits (lead)

- **`.claude/commands/pr-babysit.md`:**
  - Preflight (after the resume-detection bullets, `:56-57`): switch focus on with `.claude/hooks/stop/worklist.py --focus <me> babysit [--pr <n>]`. Without `--pr` it resolves the open PR, and before the PR exists the hook fills it in.
  - Delegate §2 (`:71-74`): turn focus on before spawning. The `pr-babysitter` type is the allowed spawn.
  - §6 (`:96-100`) and the Inline section (`:102-111`): at the finish line, or on abandoning the wave, run `--focus <me> off`. Fix items are added with `pr:<n>/fix`, and worker spawns carry `focus-fix:#<id>`.
- **`.claude/agents/pr-babysitter.md`:**
  - Workers (`:139-147`): add the `focus-fix:#<id>` declaration to the worker contract, with the item carrying `pr:<n>/fix`.
  - Loop step 8 (`:110`): in in-context mode, run `--focus <me> off` at the finish line; in delegated mode, the lead does it.
- **`.claude/commands/pr-merge.md`:**
  - End of step 0 (`:29`): `--focus <me> merge --pr <console-pr>`.
  - Step 3 (`:133`): add a note that the merge ends focus automatically and the next stop prints the parked line, so steps 4-6 run under the full battery.
  - Step 8 (`:300`): `--focus <me> off` (a no-op if already ended).
- **`CLAUDE.md:99-102`:** add a second exception next to CAP-SATURATED WAIT. FOCUS MODE (`--focus`) stands down plan, queue and hygiene pushes while `/pr-babysit` or `/pr-merge` runs; CI red, dead watches, unread reports, STATE.md near compaction and hook integrity still block; writer spawns are refused except for declared `focus-fix` work.

## 9. Tests: `.claude/rediacc_hooks/tests/test_wl_focus.py`

**Fixture sources:**
- import `ci_setup`, `ci_rollup`, `ci_job` and `ci_run` from `test_wl_ci_status.py:59-150`;
- import `capturing_judge` and the `mutated_hook`, `band_env` and `stop` helpers from `test_wl_cap_wait.py` (the same cross-test import that file makes from `test_wl_roster.py`);
- the plan-box push fixture is a plan file `proj/agent/plans/PLAN-fx.md` with `Status: ready`, `Owner: deadbeef (adopted from cafe1234 2026-09-20)` (`wl_planfile.py:335-347`), `Depends-On: no-dep` and two `- [ ]` boxes. Its needle is "WAS ADOPTED BY THIS SESSION" (`worklist_messages.py:876`);
- the focus is turned on with `wl.cli("--focus", ME, "babysit", "--branch", "pub", "--pr", "543")`;
- the gh shim gains a `*states:[MERGED*` arm serving `ci-merged.json`, ahead of `query=*`;
- the spawn is driven through `dispatch.py block_focus_spawn` with `fix.env`, so the guard reads the same `WORKLIST_STORE_DIR`.

| Case | Setup | Expected |
|---|---|---|
| `f1_focus_silences_a_plan_box_push` | adopted plan + focus on | allow, `FOCUS MODE` present, "WAS ADOPTED" absent |
| `f1_control_no_focus_blocks` | same, no focus | block, "WAS ADOPTED" |
| `f2_focus_keeps_a_ci_red_block` | `ci_setup` + FAILURE rollup + focus on, run with `WORKLIST_PUBLISH_REF` unset | block, "CI IS RED ON PR #543" (the focus supplied the ref) |
| `f2_control_no_focus_no_ref_is_silent` | same, no focus | no "CI IS RED" (the 131b behaviour stands) |
| `f3_focus_refuses_a_writer_spawn` | focus on; spawn `general-purpose` | rc 2, "FOCUS" |
| `f3_controls` | Explore spawn; `focus-fix:#<id>` whose item carries `pr:543`; the same id without the token; an id owned by a peer | 0; 0; 2; 2 |
| `f4_focus_off_restores_all_three` | f1+f2+f3 world, then `--focus deadbeef off` | block naming both "WAS ADOPTED" and "CI IS RED"; the spawn is rc 0; the output carries "FOCUS ENDED (operator)" naming `plan-adopted` |
| `f5_merge_auto_ends_focus` | shim returns MERGED #543 closed after the on-event | a store `off` event with `why: merged`; "FOCUS ENDED (merged)"; the next spawn is allowed. Control: shim returns nothing, focus stays |
| `f6_judge_skipped` | focus + a PR-unlinked open item + `capturing_judge(CONTINUE)` | no `prompt.txt`. Control: focus off, `prompt.txt` exists |
| `f7_advisories_batched` | plant 4 priority-2 outq entries + one `unread-reports` | the focused allow shows only unread-reports; with `batch_at` planted 31 minutes ago the digest names all four |
| `f8_pr_linked_item_still_blocks` | focus + open item `... pr:543/fix` | block `focus-pr-items`. Control: an unlinked item allows |
| `f9_compaction_near_keeps_state_demand` | focus + band 1 + missing STATE.md | block with the compaction note. Control: band 0 allows |
| `f10_compaction_keeps_active_focus` | focus on, `worklist.py --compact` | still focused; an ended focus is not re-emitted |
| `f11_queue_lease_accepted_in_focus` | 0 writers, `--lease … worker:queue` | accepted under focus, refused without |
| `f12_expiry_ends_focus` | on-event planted 25 hours old | "FOCUS ENDED (expired)" |
| `f13_profiles_keys_have_producers` | static, over every profile in `wl_standdown` | every kept key has a producer (the c9 scan); every literal occurs once in `wl_standdown.py` |
| `f14_cap_wait_keeps_pr_finish_hook_bug` | cap-saturated + a forced `pr-finish` always branch | block (the finding-3 fix) |

**Mutation controls** follow the house rule of mutating a copy (`docs/agent-reference/TRAPS.md:288-291`) through `mutated_hook`:
- **m1:** `"ci-red",` removed from FOCUS in `wl_standdown.py` → f2 allows.
- **m2:** `active_focus` forced to `return None` → f1 blocks and f3's spawn is allowed. This proves both depend on the store read.
- **m3:** the judge-site `and not _in_standdown` at `:4457` removed → f6 writes `prompt.txt`.
- **m4:** `only=` dropped at the drain call → f7 shows every advisory on the first stop.
- **m5:** the guard's `DEFECT` → the no-token `focus-fix` is allowed. This also runs through `test_guards_differential.py`.
- **m6:** `focus_pr_end` forced to `return ""` → f5 does not end.
- **m7:** `"focus-pr-items",` removed → f8 allows.

**Existing tests touched:**
- `test_wl_cap_wait.py:228-243` (c9 iterates the profiles) and `:279-313` (m1/m2 target `wl_standdown.py`);
- `test_wl_message_catalogue.py` `ARITY`;
- `.claude/hooks/stop/test-always-tier.py` (`focus-pr-items` laddered);
- `test_dispatch.py` passes unchanged once `ORDER = 4` is contiguous.

## 10. Risks and unverified points

- **Guard latency.** It pays for one full `S.load` per Agent call while focused. If a measurement shows more than 200 ms, prefilter the store lines for `"ev":"focus"` and `"ev":"lineage"` before `json.loads`.
- **Unverified: the session id on a subagent's own spawns.** The plan assumes a `/pr-babysit bg` babysitter's Agent calls carry the lead's `session_id`. If they carry another id, the guard finds no focus and allows (fail-open, in the lax direction). Check one real payload.
- **Arming `ci_trouble` from the focus** makes `ci-red` fire where it never did before, but only for sessions that declared focus. The existing acknowledgement and `CI_MAX_BLOCKS` exits bound it (`wl_ci.py:773-789`).
- **`focus-pr-items`** depends on fix items carrying `pr:<n>`. The skill edits make that the convention, and an untagged fix item is parked, not lost; it is named in the exit line.

### Critical Files for Implementation
- /home/developer/console/.claude/hooks/stop/wl_checks.py
- /home/developer/console/.claude/hooks/stop/wl_standdown.py (new; the profile moved from /home/developer/console/.claude/hooks/stop/wl_roster.py:53-111)
- /home/developer/console/.claude/hooks/stop/wl_store.py
- /home/developer/console/.claude/rediacc_hooks/guards/block_focus_spawn.py (new; template /home/developer/console/.claude/rediacc_hooks/guards/block_agent_cap.py)
- /home/developer/console/.claude/rediacc_hooks/tests/test_wl_focus.py (new; helpers from test_wl_cap_wait.py and test_wl_ci_status.py)

## Progress (2026-09-25)

T0 done by the lead (PLAN-stop-hook-cap-saturated-wait.md Status: done). T1-T4 and T6 done by writer ad4621651cd7c8873; lead re-ran test_wl_focus 31, test_wl_cap_wait 16, test_wl_roster 46, test-block_focus_spawn 22 cases 0 failures; 8 mutation controls flip. Open: T5 (skill/doc edits, waits on PLAN-commit-as-you-go.md, which rewrites the same rule text) and T7.

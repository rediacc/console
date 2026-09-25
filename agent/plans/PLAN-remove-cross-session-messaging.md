# PLAN: remove cross-session messaging from the worklist Stop hook

Status: draft. Planning only; this plan has not changed any code.
Depends-On: no-dep -- related, not ordered: this plan re-scopes prose in PLAN-stop-hook-rulings-campaign.md and PLAN-uncommitted-work-exposure-check.md; it does not wait on them
Operator ruling (2026-09-24): "The stop hook system has a messaging system between claude sessions (not for sub-agents). Let's remove it completely since we drive the sessions usually with only one terminal now."
Approach: clean break. Nothing is kept for compatibility: no shims, no dual paths.

## 0. What the messaging system actually is

The messaging machinery has four layers. All four are session-to-session, and all four go.

1. **The request log.** `wl_requests.py` owns a separate JSONL sidecar at `$TMPDIR/claude-worklist/<slug>.requests` (`.claude/hooks/stop/wl_store.py:518-519`). It has its own event kinds (`ask`, `answer`, `decline`, `ack`, `escalate`, `reassign`) and its own fold (`wl_requests.py`, lines 40-87 in the last committed blob `326bae9f3857`). The CLI verbs are `--ask`, `--answer`, `--decline`, `--ack` and `--requests` (`.claude/hooks/stop/worklist.py:2014-2016`). `--ask operator` rides the same log.
2. **The inbox poll.** `--poll <me>` (`.claude/hooks/stop/worklist.py:2017-2023`, `wl_requests.py`, lines 411-431 in the last committed blob `326bae9f3857`) writes a `.pollmark-<me8>` marker. That marker enables `poll_fast_path` (`.claude/hooks/stop/wl_checks.py:1166-1300`), a silent Stop exit. The rest of the poll layer hangs off it:
   - the "two-cron shape" (a poll cron beside the work cron): `POLL_*`, `is_poll_cron`, the `no-poll` and `many-poll-crons` checks
   - the poll backoff ladder
   - the no-op wake ladder, whose only output (`quiet_wake_note`) is a poll-cron rung swap
   - the pollbase baseline
3. **The inbox waiter.** `wl_wait.py` is a background process that exits when new mail arrives. Its dependents:
   - the PostToolUse `--nudge` (wired at `.claude/rediacc_hooks/lifecycle.py:147`)
   - the `worklist.py --wait` forwarder (`.claude/hooks/stop/worklist.py:2120-2123`)
   - the Stop checks `no-waiter`, `waiter-lapsed`, `no-waiter-asked`, `waiter-drained` and `many-waiters`
   - `wl_liveness.waiter_tasks` and `confirmed_waiters`
   - the pre-bash guard `block_shell_background_waiter.py`

   **Decision: remove the waiter entirely.** Every rule that enforces it is gated on a live peer session: the nudge returns early when there are no peers (`wl_wait.py`, lines 583-591 in the last committed blob `20dff1b28045`), `no-waiter` needs `_peers` (`.claude/hooks/stop/wl_checks.py:3884-3890`), and `no-waiter-asked` needs an open request. Its one non-request wake source is new sub-agent reports on the branch. For this session's own agents that duplicates the harness task notification. For another session's agents on the same branch it is cross-session mail. `wl_report.py` (capture, `--reports`, and the `unread-reports` Stop check) stays.
4. **Stop-check surfaces:**
   - `requests`, `answers`, `xsession` (the `waiting-cross-session` Remaining state), `req-escalated`, `req-open`, `backoff`
   - the "open operator request is supervision" suppression (`.claude/hooks/stop/wl_checks.py:2712-2722`)
   - the request term in `phantom_identities`
   - `my_requests_sig` in `world_sig`

**What stays, and the dependencies to cut:**

| Keep | Depends on messaging? | Cut |
|---|---|---|
| Reporting peers' open items (the `others` and `orphans` sections (lines 5155-5210 in the pre-removal blob `5a8904da5ad6`), `others_briefs`, `N_AGENT_PEERS`, `CTX_POSTCOMPACT_PEERS`, `--brief` and the `.sessions` briefs) | No. It reads `classify_items` and `read_briefs`, never the request log. | None. `--brief` stays because peer reporting reads it. |
| `--migrate` | Prose only: `.claude/hooks/stop/worklist.py:1318` prints "requests addressed to %s are NOT moved; read them with --requests" | Delete that line. Edit `.claude/skills/migrate/SKILL.md:32,60`. |
| `--adopt` | No (`_adopt_cli` never touches `R`) | None. |
| `--reassign` (phantom repair, not listed as a keep but used by the phantom backstop) | Yes. `.claude/hooks/stop/worklist.py:1457-1470` moves open requests. `CLI_REASSIGN_*` text names requests and `--poll`. | Drop the request half. Items-only `reassign` store events stay. |
| Sub-agent roster and `--status` (wl_roster, including the SendMessage scan) | Yes, in one place. `wl_roster.roster_covers_all` (`.claude/hooks/stop/wl_roster.py:601-619`, working-tree numbering) treats an OS-confirmed `wl_wait` shell as covered through `L.confirmed_waiters`. | Drop the `waiters` term: a non-subagent task returns False there. Confirmed shells are still covered by `wl_liveness.all_waits_live` (`.claude/hooks/stop/wl_checks.py:2692-2697`, docstring `.claude/hooks/stop/wl_liveness.py:309`), so the net verdict does not change. **This is the one necessary change to the lead's uncommitted file. Do it last, after the lead commits.** |
| `test_wl_roster.py` | `test_s4_a_due_ping_forfeits_the_silent_poll_path` (`:668-690`) drives `--poll` | Delete that one test, after the lead commits. |

**Old history. Decision: ignore it, no scrub.**
- The tracked store `agent/worklist/*.jsonl` never held request events. Its kinds today are add, brief, lease, lineage, md, reassign (item reassigns), state, status, tomb, triage, unlease and update.
- Request events lived only in the untracked `$TMPDIR` sidecar `<slug>.requests`.
- `wl_store._fold_events` (`.claude/hooks/stop/wl_store.py:862-1000`) is an `if/elif` chain with no `else`, so an unknown `ev` such as `ask` is already skipped silently.
- After this change nothing opens `.requests`, `.pollmark-*`, `.pollbase-*`, `.waiter-*`, `.waiterlock-*`, `.waiternudge-*` or `.asknolisten-*`. They become inert `$TMPDIR` litter. No fold change is needed and nothing runs a one-shot job. A new test proves both properties (section 4).

## 1. Inventory

R = remove (whole file or block). E = edit. Line numbers are current HEAD, except wl_roster, which uses the working tree.

### Stop-hook core (`.claude/hooks/stop/`)

| file:line | R/E | What |
|---|---|---|
| `wl_requests.py` (all 463 lines) | R | Request log, CLI, escalation, poll, `print_inbox` |
| `wl_wait.py` (all ~720 lines) | R | Waiter, PostToolUse nudge, ask-nolisten ladder, `outstanding_work` |
| `.claude/hooks/stop/worklist.py:4,7-8,15-17,27` | E | Module docstring: drop "cross-session requests", "poll fast path", `my_requests_sig`, the no-op wake ladder and the `wl_requests` row |
| `.claude/hooks/stop/worklist.py:102,121` | E | Drop `"wl_requests"` from the sibling list and `R = _MODS["wl_requests"]` |
| `.claude/hooks/stop/worklist.py:1318` | E | Drop the `--migrate` "requests ... NOT moved" line |
| `.claude/hooks/stop/worklist.py:1394-1408,1457-1470,1471-1484` | E | `_reassign_cli`: remove the request half (`reqs`, `moved_reqs`, `R.append_request_event`) and update the docstring |
| `.claude/hooks/stop/worklist.py:1986` | E | Comment says `.sessions` is "what --ask's recipient check reads"; reword |
| `.claude/hooks/stop/worklist.py:2014-2023` | R | `--ask/--answer/--decline/--ack/--requests` and `--poll` dispatch. After removal they fall into the unknown-verb refusal at `:2157-2159` (exit 2). |
| `.claude/hooks/stop/worklist.py:2120-2123` | R | `--wait` forwarder to wl_wait |
| `.claude/hooks/stop/wl_checks.py:40,45` | E | Drop `import wl_requests` and `import wl_wait` |
| `.claude/hooks/stop/wl_checks.py:78-119` | R | Poll constants: `POLL_SCHEDULE_RE`, `POLL_COMMAND_RE`, `POLL_HOURLY_RE`, `POLL_BACKOFF_LADDER`, `POLL_WINDOW_S`, `POLL_FULL_MAX_MIN`, `XSESSION_ID_RE` |
| `.claude/hooks/stop/wl_checks.py:122-151` | R | `poll_backoff_tip` |
| `.claude/hooks/stop/wl_checks.py:153-226` | R | No-op wake ladder: `QUIET_WAKES_TO_RESCHEDULE`, `quiet_wake_sig/bump/note`. Its only output is a poll-cron rung swap, so it is dead once there is no poll cron. |
| `.claude/hooks/stop/wl_checks.py:228-247` | E | `broken_schedules` stays; its docstring cites the backoff ladder |
| `.claude/hooks/stop/wl_checks.py:250-305` | R | `canonical_poll_schedule`, `is_poll_cron`, `pollmark_path`, `pollbase_path`, `bank_pollbase` |
| `.claude/hooks/stop/wl_checks.py:784` | E | Comment about the fast path banking the checklist sig |
| `.claude/hooks/stop/wl_checks.py:1131-1300` | R | `xsession_ok`, `poll_fast_path` |
| `.claude/hooks/stop/wl_checks.py:1303-1304` | R | `WAITER_GRACE_NUDGES` |
| `.claude/hooks/stop/wl_checks.py:1860-1925` | E | `phantom_identities(..., reqs)`: drop the parameter and the `n_reqs` "open request(s)" term (`:1914-1922`) |
| `.claude/hooks/stop/wl_checks.py:2025-2040` | E | Tier-ladder prose: T_OWED no longer names "a peer's request, an answer ... not listening for" |
| `.claude/hooks/stop/wl_checks.py:2076-2079,2086` | E | Drop `requests`, `no-waiter-asked`, `no-waiter`, `waiter-lapsed`, `answers` and `xsession` from T_OWED |
| `.claude/hooks/stop/wl_checks.py:2117-2118,2130` | E | Drop `no-poll`, `many-poll-crons` and `many-waiters` from T_INTEGRITY |
| `.claude/hooks/stop/wl_checks.py:2295-2304` | R | The fast-path call in `run_stop` |
| `.claude/hooks/stop/wl_checks.py:2337-2365` | R | Escalation, `req-escalated` outq, `all_reqs` and `req_*` classification |
| `.claude/hooks/stop/wl_checks.py:2576-2578` | E | `live_poll_crons` goes; `live_work_crons = live_crons` (or rename the uses to `live_crons`) |
| `.claude/hooks/stop/wl_checks.py:2586-2591` | E | Comment: cur_sig now feeds the judge cache only |
| `.claude/hooks/stop/wl_checks.py:2633-2646,2685-2697` | E | Drop `_waiters_confirmed` and `_only_waiters`. The `_all_live` expression keeps `all_waits_live` and `roster_covers_all`. `bg_verdicts` is still computed lazily at `:2668-2671`. |
| `.claude/hooks/stop/wl_checks.py:2712-2722` | E | Drop the "open operator request is supervision" `_supervised` term and its v14 comment. `_supervised` starts False and the correlated-lease logic follows. |
| `.claude/hooks/stop/wl_checks.py:2800-2822` | E | I1 and I2 invariant prose: drop the `no-waiter-asked` and request examples |
| `.claude/hooks/stop/wl_checks.py:3099-3136` | R | `requests` and `answers` vadds |
| `.claude/hooks/stop/wl_checks.py:3180` | E | Comment: "a VERIFIED waiting-cross-session task counts as having a wake-up" |
| `.claude/hooks/stop/wl_checks.py:3819` | E | `phantom_identities(worklist, session_id, fold)` |
| `.claude/hooks/stop/wl_checks.py:3844-3848` | E | `cl_sig_now` / `checklists_sig` existed only to bank the pollbase: drop it and ignore `cl_live_now` |
| `.claude/hooks/stop/wl_checks.py:3857-3860` | R | The `no-poll` check |
| `.claude/hooks/stop/wl_checks.py:3861-3916` | R | `no-waiter` and `waiter-lapsed` |
| `.claude/hooks/stop/wl_checks.py:3918-3973` | R | `no-waiter-asked` plus its ladder bump and reset |
| `.claude/hooks/stop/wl_checks.py:3975-4013` | R | `waiter-drained` and `many-waiters` |
| `.claude/hooks/stop/wl_checks.py:4027-4028` | R | `many-poll-crons` |
| `.claude/hooks/stop/wl_checks.py:4053` | E | Drop `waiting-cross-session` from `state_re` |
| `.claude/hooks/stop/wl_checks.py:4056,4071-4079,4088-4100` | E | Drop `xw_bad`/`xw_ok`, the `waiting-cross-session` arm and the `xsession` vadd. `idle_tasks` no longer excludes `xw_ok`. Fix the comment at `:4090`. |
| `.claude/hooks/stop/wl_checks.py:4267-4287` | R | The no-op wake ladder block (`quiet_note` and its emit) |
| `.claude/hooks/stop/wl_checks.py:4286,4381,4424,5101` | R | `bank_pollbase(...)` calls |
| `wl_checks.py` lines 5119-5140 in the pre-removal blob `5a8904da5ad6` | R | The `backoff` outq (`_req_ages`, `poll_backoff_tip`) |
| `wl_checks.py` lines 5165-5193 in the pre-removal blob `5a8904da5ad6` | R | The `req-open` outq, including the `--answer operator` relay |
| `.claude/hooks/stop/wl_store.py:11,18` | E | Docstring: `.requests` "precedent" and sidecar list (drop `.requests`, `.pollbase-*`, `.pollmark-*`, `.waiter-*`, `.waiternudge-*`) |
| `.claude/hooks/stop/wl_store.py:518-519` | R | `requests_path` |
| `.claude/hooks/stop/wl_store.py:535` | E | Prose citing `.requests` as precedent |
| `.claude/hooks/stop/wl_store.py:2053` | E | `compact` docstring "The .requests sidecar is never touched" |
| `.claude/hooks/stop/wl_store.py:2468-2506` | E | `world_sig`: drop the `my_requests_sig(...)` blob term and the poll prose. The judge cache is invalidated once; that is harmless. |
| `.claude/hooks/stop/wl_store.py:2509-2545` | R | `my_requests_sig` |
| `.claude/hooks/stop/wl_core.py:40` | E | Comment: request from/to charset |
| `.claude/hooks/stop/wl_core.py:184` | E | `same_session` docstring: callers list "request routing ... the waiter" |
| `.claude/hooks/stop/wl_core.py:189-203` | R | `UNCHECKED_ME = ("operator",)` and its whole comment block. It exists only for `--answer operator`. |
| `.claude/hooks/stop/wl_core.py:204` | E | Comment "GENERALISED from --poll/--wait" |
| `.claude/hooks/stop/wl_core.py:243` | E | Drop the `if me in UNCHECKED_ME` branch in `check_me`. This tightens the check: `<me>=operator` is now identity-checked like any other value. |
| `.claude/hooks/stop/wl_core.py:234,276` | E | Prose "peer's message ... inbox" and "two inboxes": reword to items |
| `.claude/hooks/stop/wl_liveness.py:24,53-66` | E | Docstring references to `poll_fast_path` |
| `.claude/hooks/stop/wl_liveness.py:50-~90` | R | `blocking_rung_due`. Its only caller is `poll_fast_path` (`.claude/hooks/stop/wl_checks.py:1266,1275`). Also drop `:734` `_ = blocking_rung_due`. |
| `.claude/hooks/stop/wl_liveness.py:230-257` | R | `WAITER_MARK`, `waiter_tasks`, `confirmed_waiters` |
| `.claude/hooks/stop/wl_liveness.py:309` | E | Docstring "(a waiter or any other job ...)" |
| `.claude/hooks/stop/wl_checklist.py:20,62-~80,481-483` | E/R | `checklists_sig` is dead without the pollbase: remove it and its docstrings. Drop `live_count` from `checklist_findings` or leave it unused (writer's choice; prefer removing it). |
| `.claude/hooks/stop/wl_report.py:18-22,200,798` | E | Prose about the `.requests` ack ledger and "wl_wait's periodic scan" |
| `.claude/hooks/stop/wl_profile.py:25` | E | Comment naming wl_wait as a sanctioned waiter |
| `.claude/hooks/stop/wl_epic.py:3` | E | `.requests` cited as precedent |
| `.claude/hooks/stop/worklist_messages.py:149-164` | R | `V_REQUESTS_WAITING`, `V_ANSWERS_UNACKED` |
| `.claude/hooks/stop/worklist_messages.py:178-189` | E | `V_IDLE`: drop "(the 5-minute inbox poll does not count ...)" |
| `.claude/hooks/stop/worklist_messages.py:191-198` | R | `V_XSESSION_BAD` |
| `.claude/hooks/stop/worklist_messages.py:349-355` | E | `V_LOOP_DIED`: drop the poll parenthesis |
| `.claude/hooks/stop/worklist_messages.py:357-382` | R | `V_NO_POLL_CRON` |
| `.claude/hooks/stop/worklist_messages.py:384-389` | E | `V_MANY_WORK_CRONS`: "ONE work loop is the required shape" |
| `.claude/hooks/stop/worklist_messages.py:391-413` | R | `V_MANY_POLL_CRONS`, `V_MANY_WAITERS` and its comment |
| `.claude/hooks/stop/worklist_messages.py:530-541` | E | `CLI_UNKNOWN_VERB` verb list: drop `--poll --ask --answer --decline --ack --requests --wait` |
| `.claude/hooks/stop/worklist_messages.py:569-686` | R | `N_WAITER_NUDGE`, `N_WAITER_DRAINED`, `V_ASK_NOLISTEN_LADDER`, `V_ASK_NOLISTEN_CMD`, `V_NO_WAITER`, `V_WAITER_LAPSED` |
| `.claude/hooks/stop/worklist_messages.py:716-755` | E | `CLI_REASSIGN_USAGE`/`YOUNG`/`DONE`: items only. Drop the `requests:` row and `--poll`. |
| `.claude/hooks/stop/worklist_messages.py:885-896` | E | `N_CADENCE_PAUSE_CARRIED` and comment: "a worker or teammate is waiting", not "another session" |
| `.claude/hooks/stop/worklist_messages.py:1012-1020` | E | `V_BROKEN_SCHEDULE`: drop "inbox poll" and "poll backoff ladder" |
| `.claude/hooks/stop/worklist_messages.py:1521-1535` | E | `V_BG_REPORT`: drop `asks you to slow the poll cron` |
| `.claude/hooks/stop/worklist_messages.py:1628-1660` | R | `CLI_REQUEST_USAGE`, `CLI_ASK_OPERATOR_NO_DEFAULT`, `CLI_ASK_UNKNOWN_RECIPIENT`, `CLI_BODY_REFUSED` |
| `.claude/hooks/stop/worklist_messages.py:2133,2160-2170,2194-2197` | E | `USAGE`: title ("... and cross-session inbox"), the Query rows, the whole "Cross-session messaging" block, and the `--reassign` "and requests" text |
| `.claude/hooks/stop/worklist_messages.py:2234-2278` | R | `N_POLL_BACKOFF`, `N_QUIET_WAKE`, `N_QUIET_WAKE_CAPPED`, `N_POLL_BACKOFF_RESET` |
| `.claude/hooks/stop/wl_roster.py:597,601-619` (working tree) | E (last, after the lead commits) | `known_ids` docstring "the poll path"; `roster_covers_all` drops `L.confirmed_waiters` |
| `.claude/hooks/stop/wl_roster.py:932` | E (same step) | Comment "a silent poll stop does not rewrite it" |
| `.claude/hooks/stop/test-always-tier.py:59-63` | E | Drop `requests`, `no-waiter`, `no-waiter-asked` and `waiter-lapsed` from the I2 set (keep `unread-reports`). Drop the `no-poll`/`many-poll-crons`/`many-waiters` lists if they appear further down. |
| `.claude/hooks/stop/test-teammate-idle.py:129-145` | R | Section 5 (`blocking_rung_due`) |

### Hook wiring, guards, oracles

| file:line | R/E | What |
|---|---|---|
| `.claude/rediacc_hooks/lifecycle.py:147` | R | The `wl_wait.py --nudge` post-tool member |
| `.claude/settings.json:62` | E | post-tool `timeout` 135 → 75 (the sum of the remaining member budgets: 15 + 60) |
| `.claude/rediacc_hooks/guards/block_shell_background_waiter.py` | R | Its only target, wl_wait.py, is gone |
| `.claude/oracles/pre-bash/block-shell-background-waiter.sh` | R | Its differential twin |
| `.claude/rediacc_hooks/guards/*.py`, pre-bash `ORDER = 15..45` (31 files: `block_self_matching_pgrep` 15 … `block_unsatisfiable_pid_wait` 45) | E | Decrement ORDER by 1. `.claude/rediacc_hooks/tests/test_dispatch.py:142-190` requires a contiguous run. |
| `.claude/rediacc_hooks/tests/hookcases.py:2020-2062` | R | The background-waiter cases |
| `.claude/rediacc_hooks/hookio.py:159` | E | Comment citing block-shell-background-waiter.sh |
| `.claude/rediacc_hooks/guards/block_unverified_push.py:62-66` | E | Message: drop the `--ask` line; say "ask the operator or leave a `[?]`". **Its twin `.claude/oracles/pre-bash/block-unverified-push.sh` (lines 83-87 in the last committed blob `160f6ee8b01c`) must change byte-identically, because the differential compares stderr.** |
| `.claude/rediacc_hooks/guards/block_self_matching_pgrep.py:84,94,102` | keep | Generic example payloads ("wl_wait.py" is just a string). Leave them so the differential corpus is unchanged. |
| `.claude/hooks/trapguard/dispatch.py:6` | E | The citation of `wl_wait.py` (lines 139-143 in the last committed blob `20dff1b28045`) as evidence of the PostToolUse keys: move that fact into this docstring |
| `.ci/scripts/ci/ci-trace.py:50-51,58-63,495-504` | E | Keep the mandatory unit suffix, drop the sibling-tool rationale. The selftest check at `:501-504` asserts on the unit refusal only. |
| `.ci/rediacc_ci/quality/hook_integrity.py:135` | E | Docstring list of machinery files |
| `.ci/rediacc_ci/review/standing_orders_brief.py:15,278-282` | E/R | Drop the `WAITING FOR ME FROM PEER SESSIONS` section and its `--poll` call |
| `.ci/rediacc_ci/tests/test_review_standing_orders_brief.py:55,64-65,76,99,207,213,215,265,336` | E | Drop the canned `--poll` branch, the `poll` fixture key, the cases `poll-has-content` and `head-30-truncation-on-poll`, the marker, and `["--poll", ...]` from the anti-vacuity check. Add a NAMED DIVERGENCE: a helper that strips the recorded 3-line peer-poll block from each golden before comparing, docstring-dated 2026-09-24, with a control asserting the block is absent from live output. |
| `.ci/rediacc_ci/tests/goldens/standing-orders-brief/poll-has-content.golden`, `head-30-truncation-on-poll.golden` | R | Needed by the two-way corpus check |

### Docs, skills, registries

| file:line | R/E | What |
|---|---|---|
| `docs/agent-reference/TRAPS.md:593-594` | E | "ASK THE OWNER via `worklist.py --ask`" → ask the operator, or leave a `[?]` naming the conflict (CLAUDE.md:9 already says this) |
| `docs/agent-reference/ci-gates.md:23-24` | E | Same replacement |
| `docs/agent-reference/worklist-v10-brief.md:34-37` | E | Historical poll note: mark it historical, removed 2026-09-24 |
| `.claude/skills/migrate/SKILL.md:32,60` | E | Drop the "cross-session requests are not moved" row |
| `.claude/skills/ci-watch/SKILL.md:20` | E | Unit-suffix rationale without wl_wait |
| `.ci/config/env-manifest.json:929-931,940,958-960,983-988` | E | Drain `WORKLIST_POLL_*`, `WORKLIST_QUIET_WAKES`, `WORKLIST_REQUEST_*`, `WORKLIST_WAITER_*`, `WORKLIST_WAIT_*` |
| `.ci/policy/worklist-env-registry.json:546-564,619,734-751,892-927` | E | Same keys |
| `.ci/config/python-env-registry.json:1629-1645,1758-1761,1797-1803` | E (regenerate) | Same keys, plus the file rows for wl_requests and wl_wait |
| `.ci/config/prose-style-baseline.json:1863,1913` | E (drain) | Entries for the deleted files |
| `.ci/config/python-types-baseline.json:3317,3450` | E (drain) | Same |
| `scripts/data/hook-inventory-baseline.json:46` | E (drain) | The guard |
| `scripts/data/doc-registry-preport.json` `retired.hook-guards` | E | Add reasons for `.claude/hooks/stop/wl_requests.py`, `.claude/hooks/stop/wl_wait.py` and `.claude/rediacc_hooks/guards/block_shell_background_waiter.py`. **Never** `--snapshot --force`. |
| `scripts/data/doc-registry.md:455,463,584,589` | regen | Generated |
| `scripts/data/shape-duplication-seed-advisory.json:56` | verify | The reason text cites `wl_requests`. Edit only if check-shape-duplication flags a stale seed. |
| `.ci/rediacc_ci/tests/goldens/claude-hooks/*.golden` | keep | Frozen recordings. `test_guards_differential` iterates `guards.stems()` (`:345`), so cases naming a deleted guard are never run. Cross-feed payloads stay valid. |
| `agent/plans/PLAN-stop-hook-rulings-campaign.md:92-97` | lead | Two open boxes build on `--poll`. Re-scope them or record them abandoned through the plan verbs; writers do not touch plan files. |
| `agent/plans/PLAN-uncommitted-work-exposure-check.md:24,62,77,85` | lead | Placement text cites `poll_fast_path`; update the prose |

### Tests (`.claude/rediacc_hooks/tests/`)

| file | R/E | Detail |
|---|---|---|
| `test_wl_requests.py` | R (whole file) | 65-84, 69z |
| `test_wl_poll_and_waiting.py` | E, then rename to `test_wl_message_catalogue.py` (`git mv`) | Delete 101-116 (`:52-300`). Keep 117 and 118, and drop removed constants from the arity table (`:300-620`, incl. `:361`, `:558`). |
| `test_wl_waiter_controls.py` | E | Delete 163z_c1, 163z_c2, 163s (both) and 163d. Keep 163x/g/y/b/c/e/f. Fix the module docstring. |
| `test_wl_background_waits.py` | E | Delete 163r (both), 161, 163z, 163q (all five), 163w (all six), 13f. Keep 163v, 13a and 13d, and remove the waiter plumbing (`WAIT_PY`, the real-waiter helper `:107`, `:263`) if nothing else uses it. |
| `test_wl_report_inbox.py` | E | Delete 15, 15b, 16, 16b, 17, 17c, 18, 19, 20, 21, 22, 25, 25-control and 25b, plus the background-waiter helper `:158-170`. Keep capture, `--reports` and 24. Fix the docstring at `:3`. |
| `test_wl_identity.py` | E | Delete 187, 187c, 188 and 184w. Edit 181 (`:221` import), 184 (drop the `--ask/--answer/--poll/--wait` rows `:445-510`, `:585-628`), 184x (`:775-790`), 185 (`:682` drop `"--requests"` from `no_me`; `:701` expected set without `--ask`/`--poll`), and 190 (`:960-995`: reassign now asserts items only, with no `--poll`). |
| `test_wl_ci_queue_and_mail.py` | E | Delete 159 and 159g (operator asks) |
| `test_wl_checklists.py` | E | Delete 192, 201 (all three) and 202 (`checklists_sig`), plus `POLL` (`:203`) and `:234` |
| `test_wl_report_queue.py` | E | Delete 178, 178b, 180, 180b, 180c, 180d, 180e (poll baseline and quiet-wake ladder) |
| `test_wl_guide_and_deferrals.py` | E | Delete 152 (both) and 153 (both, fast-path forfeits). Check 146c for a `--poll` dependency and drop that leg. |
| `test_wl_agent_docs_and_focus.py` | E | Delete 153e |
| `test_wl_priority_ladder.py` | E | 230/230b are built on `no-waiter-asked`: delete them. Rebuild 232/232b (`:171-260`) around three current invariants (for example `unread-reports`, `roster-cap`, `ci-red`) with no request keys; `:222`'s "cross-session REQUEST(S)" string goes. |
| `test_wl_idle_and_evidence.py` | E | Delete 92b (poll cron is not a wake-up). Check 92a and 100 for the DEFAULT_CRONS change. |
| `test_wl_drift_loops_freshness.py` | E | 34/34b/34c: loop-death with one work cron; drop the surviving-poll leg |
| `test_wl_core_blocking.py` | E | 25 (two work crons) unchanged. 26 (canonical shape) is now one work cron. Check `PEER_BODY` (`:16`, prose only). |
| `.claude/rediacc_hooks/tests/test_wl_roster.py:668-690` | R (after the lead commits) | `test_s4` |
| `.claude/rediacc_hooks/tests/wlfix.py:44-48` | E | `DEFAULT_CRONS = [{"id": "w", "schedule": "17 * * * *"}]`. **This is load-bearing:** leaving `*/5` in would make every case fire `many-work-crons`. |
| `.claude/rediacc_hooks/tests/wlfix.py:55` | E | Drop `WORKLIST_QUIET_WAKES` from `RESET_KNOBS` |
| `.claude/rediacc_hooks/tests/wlfix.py:471-487` | R | `askid`, `askid_as` |
| `wlfix.py` | E | Drop any `poll_marker` or l1-driver helper used only by 184 |

## 2. Ordered edit steps

1. **The lead commits the in-flight work first:** `wl_roster.py`, `test_wl_roster.py`, and the other dirty stop files (`wl_defersettle.py`, `test-backlog.py`, `test-planfile.py`, `test-planindex.py`, `calibrate-judge-rules.py`). Writers must start from a clean `.claude/hooks/stop/`.
2. **Messages first.** In `worklist_messages.py`, delete and edit the constants listed in section 1. This lets later steps fail loudly on any stale `M.X` reference.
3. **Remove the entry points.** Delete `wl_requests.py` and `wl_wait.py`. Edit `worklist.py` (sibling list, dispatch, `_reassign_cli`, `_migrate_cli` line, docstring).
4. **Rip out the Stop battery.** Edit `wl_checks.py` top to bottom in the order of the inventory:
   - constants and helpers
   - `xsession_ok` and `poll_fast_path`
   - the tier sets
   - the `run_stop` blocks
   - the `bank_pollbase` calls
   - the `backoff` and `req-open` outqs

   Then make `live_work_crons` equal `live_crons`, and remove `phantom_identities`' `reqs` parameter.
5. **Clean the support modules:** `wl_store.py` (`requests_path`, `my_requests_sig`, `world_sig`), `wl_core.py` (`UNCHECKED_ME`), `wl_liveness.py` (waiter helpers, `blocking_rung_due`), `wl_checklist.py` (`checklists_sig`), and the prose-only edits in wl_report, wl_profile and wl_epic.
6. **Rewire the PostToolUse hook.** Remove the `.claude/rediacc_hooks/lifecycle.py:147` member and set the `settings.json` post-tool timeout to 75.
7. **Retire the guard.** Delete `block_shell_background_waiter.py` and its oracle, renumber the 31 pre-bash ORDERs, and delete the hookcases entries and the hookio comment. Update `block_unverified_push.py` and its oracle byte-identically.
8. **Periphery:** ci-trace.py, standing_orders_brief.py and its test and goldens, trapguard docstring, hook_integrity docstring, docs, skills.
9. **Tests:** rewrite wlfix, delete and edit per section 1, add the new tests from section 4, and edit `test-always-tier.py` and `test-teammate-idle.py`.
10. **Drain and regenerate** the registries (section 5).
11. **Roster edits last, after step 1 has landed:**
    - `wl_roster.roster_covers_all`: drop the waiter term
    - the two comments (`.claude/hooks/stop/wl_roster.py:597`, `:932`)
    - delete `test_s4`
12. **Plan files (lead only):** re-scope `PLAN-stop-hook-rulings-campaign.md` section 6 and update `PLAN-uncommitted-work-exposure-check.md` through the plan verbs.
13. **Run the gates** (section 6), then commit with explicit pathspecs.

## 3. Writer partition (2 disjoint sets)

**Writer A: stop core and its tests** (steps 2-5, 9, 11)
- `.claude/hooks/stop/`: `wl_requests.py` (delete), `wl_wait.py` (delete), `worklist.py`, `wl_checks.py`, `wl_store.py`, `wl_core.py`, `wl_liveness.py`, `wl_checklist.py`, `wl_report.py`, `wl_profile.py`, `wl_epic.py`, `worklist_messages.py`, `test-always-tier.py`, `test-teammate-idle.py`
- In step 11 only: `wl_roster.py`
- `.claude/rediacc_hooks/tests/`: `wlfix.py`, every `test_wl_*.py` listed in section 1, the new `test_wl_messaging_removed.py`, and `test_wl_roster.py` (step 11 only)

**Writer B: wiring, guards, periphery, registries** (steps 6-8, 10)
- `.claude/rediacc_hooks/lifecycle.py`, `.claude/settings.json`, `.claude/rediacc_hooks/hookio.py`
- `.claude/rediacc_hooks/guards/*.py` (the delete plus the ORDER sweep)
- `.claude/oracles/pre-bash/block-shell-background-waiter.sh` (delete), `.claude/oracles/pre-bash/block-unverified-push.sh`
- `.claude/rediacc_hooks/tests/hookcases.py`
- `.claude/hooks/trapguard/dispatch.py`
- `.ci/scripts/ci/ci-trace.py`, `.ci/rediacc_ci/review/standing_orders_brief.py`, `.ci/rediacc_ci/tests/test_review_standing_orders_brief.py`, `.ci/rediacc_ci/tests/goldens/standing-orders-brief/{poll-has-content,head-30-truncation-on-poll}.golden` (delete), `.ci/rediacc_ci/quality/hook_integrity.py`
- `docs/agent-reference/{TRAPS.md,ci-gates.md,worklist-v10-brief.md}`, `.claude/skills/{migrate,ci-watch}/SKILL.md`
- Step 10, run after Writer A is green: `.ci/config/{env-manifest,python-env-registry,prose-style-baseline,python-types-baseline}.json`, `.ci/policy/worklist-env-registry.json`, `scripts/data/{hook-inventory-baseline.json,doc-registry-preport.json,doc-registry.md}`

**Sequencing:**
- A and B can run in parallel through their code edits.
- B's step 10 waits for A, because the regenerators read the post-removal tree.
- The lead owns the `agent/plans/*` edits.

## 4. Tests

**Delete:** everything marked R in the Tests table of section 1. The whole-file deletion is `test_wl_requests.py`. `test_wl_poll_and_waiting.py` loses 101-116 and is renamed. In total about 90 functions are removed across the files listed.

**Add** a new file, `.claude/rediacc_hooks/tests/test_wl_messaging_removed.py`, using the `wl` fixture. Every positive assertion is paired with a control.

1. `test_removed_verbs_are_unknown`
   - For each of `--ask`, `--answer`, `--decline`, `--ack`, `--requests`, `--poll` and `--wait`, run `wl.cli(verb, wlfix.ME, "x")`:
     - `rc == 2`
     - stderr contains `unknown verb '<verb>'`
     - `'"decision"'` is absent from stdout and stderr
   - Run `--poll` once more with an open stdin pipe and an 8 s interpreter timeout, and assert it does not hang (the 163x shape).
   - CONTROL: `wl.cli("--list")` returns rc 0, and `wl.cli_as(pfx, "--brief", pfx, "t")` prints "brief recorded". This proves the harness can succeed, so the rc 2 above is not vacuous.
2. `test_help_no_longer_advertises_messaging`
   - `--help` output contains none of the seven verbs and none of "Cross-session messaging", "--poll", "wl_wait".
   - CONTROL: the output contains `--add` and `--reassign`.
3. `test_old_request_history_folds_cleanly`
   - Build a clean world, run the stop, and record the fold (`[(id, state, owner)]`) and the decision as the control.
   - `wl.setup()` the same world, then plant:
     - (a) `<worklist>.requests` with an `ask` addressed to ME, an `answer` to an ask from ME, an `escalate` and a `reassign`
     - (b) in the store event log: `{"ev":"ask",...}`, `{"ev":"answer",...}` and `{"ev":"ack",...}` lines
     - (c) a fresh `.pollmark-<me8>` and a matching `.pollbase-<me8>`
   - Assert:
     - the fold equals the control fold
     - the decision equals the control decision
     - the output contains none of "REQUEST", "INBOX", "ANSWERED"
     - the stop is NOT silent: a `.lastevent-<me8>.json` is written or the output is non-empty. That proves a leftover pollmark buys nothing.
     - `.requests` bytes are unchanged after the stop, so nothing reads or appends it.
4. `test_no_hook_still_wires_the_waiter`
   - `lifecycle.flat_commands("post-tool")` contains no `wl_wait`.
   - `lifecycle.entry_timeout("post-tool") == 75`.
   - CONTROL: `band-notice.py` and `onboard.py` are still members.
5. The deleted `many-waiters`/`no-poll` coverage turns into a shape assertion: with `DEFAULT_CRONS` holding one work cron, a clean stop allows. Add a `*/5` second cron and `many-work-crons` fires (inverting 25/26).

Also extend the existing test 185 (`test_wl_identity.py`): the derived verb set must not contain any of the seven removed verbs. Add that as an explicit negative assertion beside the existing positive one.

## 5. Regenerate and drain (run from the repo root after Writer A is green)

```
python3 .ci/scripts/quality/check_python_env_registry.py --write-baseline
python3 .ci/scripts/quality/check_python_types.py --write-baseline
python3 .ci/scripts/quality/check_prose_style.py check --write-baseline   # drain only; it refuses additions
# hand-drain (no writer flag): .ci/config/env-manifest.json, .ci/policy/worklist-env-registry.json,
#                              scripts/data/hook-inventory-baseline.json
# hand-add retired.hook-guards reasons in scripts/data/doc-registry-preport.json (3 keys)
npx tsx scripts/gen/gen-docs.ts --write
npx tsx scripts/gen/gen-docs.ts                   # verify mode
npx tsx scripts/gen/gen-docs.ts --diff-snapshot   # must print the 3 "retired" rows, 0 DROPPED
npx tsx scripts/gen/gen-manifest.ts               # verify only: no gate is added or removed, expect no diff
```

No generated skill reference covers the edited skills: `rdc/reference.md` is unrelated. `check:ci-skill-size` covers the SKILL.md edits. `gen:gates-lock` is not needed because no manifest entry changes.

## 6. Gates to run

```
python3 -m pytest .claude/rediacc_hooks/tests -q -n auto      # the hook suite, incl. test_dispatch ORDER contiguity,
                                                             # test_guards_differential, test_settings_collapse
python3 .claude/hooks/stop/test-always-tier.py
python3 .claude/hooks/stop/test-teammate-idle.py
python3 .ci/scripts/ci/ci-trace.py --selftest
python3 -m pytest .ci/rediacc_ci/tests/test_review_standing_orders_brief.py -q
npm run check:ci-pytest
npm run check:ci-hook-integrity
npm run check:ci-hooks-resolvable
npm run check:ci-dead-python
npm run check:ci-env-manifest
npm run check:ci-python-env-registry
npm run check:ci-worklist-env-registry
npm run check:ci-prose-style
npm run check:ci-python-types
npm run check:ci-guard-mention-anchoring
npm run check:ci-shape-duplication
npm run check:ci-skill-size
npm run gen:docs
npm run ci:quick            # then the full `npm run ci` before push
```

Finally, run a live smoke check in this session:
- `python3 .claude/hooks/stop/worklist.py --poll d778be9d` returns exit 2 with the unknown-verb text.
- `worklist.py --list --open d778be9d` is unchanged.
- The next Stop allows or blocks exactly as before, minus the removed keys.

### Critical Files for Implementation
- /home/developer/console/.claude/hooks/stop/wl_checks.py
- /home/developer/console/.claude/hooks/stop/worklist.py
- /home/developer/console/.claude/hooks/stop/worklist_messages.py
- /home/developer/console/.claude/hooks/stop/wl_store.py
- /home/developer/console/.claude/rediacc_hooks/tests/wlfix.py

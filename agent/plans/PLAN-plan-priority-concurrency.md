# PLAN: plan priority and plan concurrency. Rank ready plans, and let file ownership decide which writers may run side by side

Status: draft
Owner: d778be9d
First-Seen: 2026-09-25
Depends-On: PLAN-plan-dependencies.md, PLAN-stop-hook-retro-20260925.md#R20260925.5
Priority: P1 -- operator order 2026-09-25: second of Y/X/W/Z; it makes fanning out Z and W writers safe
Concurrency: parallel
Owns: .claude/hooks/stop/wl_{plandeps,planconc,roster,checks,store,backlog,planenforce,planrec}.py, .claude/hooks/stop/{worklist,worklist_messages}.py, .claude/hooks/stop/test-{plandeps,backlog}.py, .claude/rediacc_hooks/guards/{block,test-block}_plan_{without_depends,concurrency}.py, .claude/rediacc_hooks/tests/test_wl_{roster,leases,guide_and_deferrals,cap_wait,plan_priority}.py, .ci/scripts/quality/check_plan_deps.py, .ci/rediacc_ci/tests/gates/test_gate_plan_deps.py, scripts/data/hook-inventory-baseline.json
Worklist: #<add when tracked>

**Operator order, 2026-09-25 (section X, verbatim in the round's spec):** "Rank the work, not just order it. Depends-On: says what must come first. It doesn't say which of two ready plans matters more. That's why the stop hook kept naming whatever item was oldest in the queue. [...] The concurrency field is really about files. 'Exclusive' is only needed when two plans touch the same files, like today's A3 and scanner collision. Declaring the owned paths lets the hook decide instead of relying on a label."

**Why this plan depends on PLAN-plan-dependencies.md.** The spec says the new fields are "enforced by the same gate and pre-edit guard that enforce Depends-On:". **That gate and that guard do not exist yet.**
- `wl_plandeps.py`, `check_plan_deps.py` and `block_plan_without_depends.py` are all absent from the tree.
- PLAN-plan-dependencies.md is `Status: approved`, and all 12 of its boxes (T1-T12) are open.
- So this plan extends the grammar module, the gate and the guard that plan creates. It cannot start before their T1-T3 land.

**Why it depends on R20260925.5.** That box changes `queue_start` (`.claude/hooks/stop/wl_roster.py:602-612`), the same lines this plan reorders. This plan builds on its `waiting_on` skip instead of racing it.

**Line numbers** refer to the working tree on `0923-1`, measured 2026-09-25. Much of `.claude/hooks/stop/` is uncommitted there, so each citation also names a function to re-anchor on.

## Tasks

Two writers at most. Their Owns are disjoint:
- **Writer A** owns the grammar, the overlap engine, the gate, both guards and the record renderer.
- **Writer B** owns the stop-hook pickers, the roster, the worklist verbs and their tests.
- **The lead** owns the migration run, the /ask and the prose.

B starts once A has frozen the T1/T2 API (`parse_x`, `order_key`, `live_plans`, `spawn_verdict`).

- [ ] T1 [A] Grammar (section 1): extend `wl_plandeps.parse_header` with `Priority`, `Concurrency` and `Owns`. Add `X_HEADER_LINES = 12` and `set_x(text, fields)`, which appends at the end of the contiguous header block. Controls go in `.claude/hooks/stop/test-plandeps.py`.
- [ ] T2 [A] New `.claude/hooks/stop/wl_planconc.py` (sealed, no env reads, stdlib at import):
  - `normalize_owns`, `owns_overlap(a, b) -> [(ga, gb, witness)]` (section 4);
  - `item_plan(rec)` and `spawn_plans(text, by_id)` (section 3);
  - `live_plans(cwd, session_id, fold)` (section 3);
  - `spawn_verdict(...)` (section 5);
  - `rank(rel, graph)` with dependency inheritance, and `order_key(rec, ctx)` (section 2).
- [ ] T3 [A] Gate `check_plan_deps.py`:
  - findings D10-D17 with planted `--selftest` controls (section 6b);
  - the verbs `--overlaps` and `--migrate-x [--diff] [--save] [--apply <json> --write]` (section 7);
  - extend `test_gate_plan_deps.py`.
- [ ] T4 [A] Pre-edit guard `block_plan_without_depends.py`: require the three fields on required plans, freeze operator values, and accept the operator-directed escape (section 6a). Extend `test-block_plan_without_depends.py`, `EDGE_CASES` and `DEFECT`.
- [ ] T5 [A] New pre-agent guard `.claude/rediacc_hooks/guards/block_plan_concurrency.py`: `CHAIN = "pre-agent"`, `ORDER = 4`, `OWN_SUITE = True`, `DEFECT`, `EDGE_CASES`. Suite `test-block_plan_concurrency.py`, plus a row in `scripts/data/hook-inventory-baseline.json` (section 5).
- [ ] T6 [A] `wl_planrec`: add `Priority`, `Concurrency` and `Owns` to `HEADER_FIELD_KEYS` (`.claude/hooks/stop/wl_planrec.py:171`). `render()` (:832) emits them AFTER `Record-Sig`, so the spine stays inside `HEADER_LINES = 10` (:146). `revive()` (:2567) carries them over, or refuses when they are missing.
- [ ] T7 [B] The pickers order by `order_key` (section 2):
  - `guided_slice` sort and display (`.claude/hooks/stop/wl_checks.py:1482`, sort at :1601);
  - `open_items` order in `classify_items` (`.claude/hooks/stop/wl_store.py:1273`);
  - `wl_backlog.next_plan` (`.claude/hooks/stop/wl_backlog.py:190`) and its `render` WHY lines;
  - `wl_planenforce.evaluate`'s named box (`.claude/hooks/stop/wl_planenforce.py:425`).
- [ ] T8 [B] Roster (section 5c):
  - `queue_start` orders by `order_key` and skips concurrency-held items (`.claude/hooks/stop/wl_roster.py:602-612`);
  - `V_QUEUE_SLOT` names what was held back (`.claude/hooks/stop/worklist_messages.py:2505`);
  - a `roster-concurrency` backstop key in `ROSTER_KEYS` (`.claude/hooks/stop/wl_roster.py:51`);
  - `cap_saturated_wait` (:90) also covers "every queued item is held".
- [ ] T9 [B] `worklist.py`: `--lease ... worker:queue` is accepted with a free slot when the item's plan is concurrency-held (`.claude/hooks/stop/worklist.py:1136-1145`). `--list --open` shows priority through `guided_slice` (:920).
- [ ] T10 [B] Tests and mutation controls (section 8): new `test_wl_plan_priority.py`, plus extensions to `test_wl_roster.py`, `test_wl_leases.py`, `test_wl_cap_wait.py` and `test-backlog.py`.
- [ ] T11 [lead] Migration (section 7):
  - `check_plan_deps.py --migrate-x --save`;
  - review the AI proposals;
  - one approval table to the operator through AskUserQuestion;
  - `--apply ... --write`.
  It lands in the SAME commit as T3/T4, with the bulk-transform proof line.
- [ ] T12 [lead] Prose:
  - CLAUDE.md rule 4 (:131, "disjoint file ownership") and :37;
  - agent/README.md plan layout;
  - docs/agent-reference/plan-records.md header table;
  - pr-babysitter.md :147;
  - `npm run gen:docs`; the full hook suite; `check:ci-plan-*`.

## 0. Facts established

### How Depends-On: is parsed and enforced today

- **The only parser** is `wl_backlog.DEPENDS_ON_RE` (`.claude/hooks/stop/wl_backlog.py:38`) and `plan_depends_on` (:53). The field is documented there as "a new, OPTIONAL header" (:37).
- **The only consumer** is `_redirect` (:119), inside the ADVISORY backlog nomination `next_plan` (:190). It is never a vadd. It is called at `.claude/hooks/stop/wl_checks.py:3277`.
- **Plans carrying the field: 4 of 36 live ones.** They are cap-saturated-wait, plan-dependencies, config-passkey-optional and app-wide-org-selection.
- **No gate, no guard, and no worklist verb reads it.** A grep of `.ci`, `scripts`, `.claude/hooks` and `.claude/rediacc_hooks` finds only `wl_backlog.py` and `test-backlog.py`.
- **The mandatory form is designed but not built:** PLAN-plan-dependencies.md T1-T3 (`wl_plandeps.py`, `check_plan_deps.py` with D1-D9, and guard `block_plan_without_depends.py` at pre-edit ORDER 13).
- **An update to that plan's T3:** the `TWIN = None` it names is now spelled `OWN_SUITE = True`. The bash oracles were retired by A3 (`.claude/rediacc_hooks/tests/test_guards_differential.py:418-430`, `block_agent_cap.py:24`).

### The "next item" pickers, and why the oldest item wins

| Picker | Where | Order today |
|---|---|---|
| queue-slot "start #id" | `wl_roster.roster`, `.claude/hooks/stop/wl_roster.py:602-612`; vadd at `.claude/hooks/stop/wl_checks.py:2891-2902`; text at `.claude/hooks/stop/worklist_messages.py:2504-2511` | `lease_at` ascending: the K oldest queued items, where K is free slots minus HOLD_FOR |
| store guide | `guided_slice`, `.claude/hooks/stop/wl_checks.py:1482`; `rows.sort(key=lambda r: r[0])` at :1601 | obligation band only, so a stable sort leaves fold (creation) order within the band |
| open-items / idle-stall | `classify_items`, `.claude/hooks/stop/wl_store.py:1273-1325`; vadd at `.claude/hooks/stop/wl_checks.py:2997-3002`; idle-stall shows `open_items[:8]` | fold order |
| backlog nomination | `wl_backlog.next_plan`, `.claude/hooks/stop/wl_backlog.py:190` | plan mtime descending (the operator's earlier "DESC" rule) |
| plan-unimplemented named box | `wl_planenforce.evaluate`, `.claude/hooks/stop/wl_planenforce.py:425-429`, over `scope_rows` (:127) | newest first |

The "free-slot" push in the spec is the queue-slot vadd ("QUEUED WORK AND A FREE WRITER SLOT", `worklist_messages.py:2506`). There is no separate one. Item age is `rec["first"]` (`.claude/hooks/stop/wl_store.py:936`).

### How an item links to a plan, and a writer to an item

- **Item to plan.** The text convention is `PLAN-x.md [<8hex>]`. PLAN-plan-dependencies §2c gives it a parser, `wl_plandeps.linked_plan`; no parser exists yet. The only other link is a triaged item's recorded plan, `rec["triage"]["plan"]` when `v == "plan-subagent"` (`.claude/hooks/stop/wl_checks.py:1505-1506`). "Is this plan tracked?" is answered by basename containment (`wl_backlog._claimed`, :98).
- **Writer to item.**
  - A lease's `worker:<agent-id>` (`wl_core.WORKER`, `.claude/hooks/stop/wl_core.py:30`, stored as `rec["worker"]`).
  - AUTO-LEASE: an owned open item named `#<id>` in a live agent's first prompt is leased to that agent at stop time. See `.claude/hooks/stop/wl_checks.py:2312-2336`, `wl_leasehelp.first_prompt` (`.claude/hooks/stop/wl_leasehelp.py:110`), `item_refs` / `ITEM_REF` (:34, :28) and `auto_lease_candidates` (:137).
- **Consequence for the spawn guard.** The writer does not exist when the pre-agent guard runs, so there is no lease yet. What the guard can see is the spawn's `tool_input.prompt` / `description`, and that is the same text auto-lease later reads. So the plan a spawn serves is resolved from the prompt (section 3).

### Live writers

- **This session:** `wl_roster.live_writers_estimate` (`.claude/hooks/stop/wl_roster.py:961`, over `live_estimate` :861) gives rows `{id, type, desc, writer, waiting}`. Metas carry `jsonl`, and `first_prompt(jsonl)` gives each writer's prompt.
- **Other sessions:** only through the shared fold, as items in state `>` with a fresh lease and a worker other than `queue` or `lead`.
- **The pre-agent guard precedent:** `block_agent_cap.py`, `CHAIN = "pre-agent"` / `ORDER = 3` (:23-25). It exempts read-only types (:97), fails open when it cannot count (:99-102), and its Stop-side twin is the authoritative `roster-cap`.
- **`worker:queue` is refused while a slot is free** (`.claude/hooks/stop/worklist.py:1136-1145`). A concurrency-held item therefore cannot be queued today. T9 fixes that.

### The collision the spec cites

STATE.md (`agent/d778be9d/STATE.md:8-13`) and PLAN-stop-hook-retro-20260925.md §3 record the two collisions:
- the A3 writer edited golden files that a queued item also needed;
- the biome/TS7 wave was named by queue-slot while "package.json and biome.json [were] still uncommitted" from the scanner wiring.

In both cases the lead refused by hand what queue-slot demanded. That is the file-level rule this plan mechanises.

### Plan corpus, counted 2026-09-25

- **204 `PLAN-*.md` files under agent/plans:** 153 at top level and 51 in `_done/`.
- **Top level:**
  - 44 stubs (`moved`);
  - 74 finished records (`compacted`);
  - **36 required plans**: 35 live, plus the companion `PLAN-retire-bash-oracles.A0.md` with no Status. That is the same required set PLAN-plan-dependencies §1 defines; it measured 30 on 2026-09-24.
- **Header extent:** the largest header block among the 36 ends at line 12 (`PLAN-stop-hook-refactor-enforcement.md`, which has a blank-line gap). `Owner:` sits at line 5 or earlier everywhere.
- **The one parked record** (`PLAN-renet-fetch-hardening.md`) has `Record-Sig:` at line 7. Inserting 4 lines after `Status:` would push it to 11, outside `wl_planrec.HEADER_LINES = 10` (`.claude/hooks/stop/wl_planrec.py:146`). Section 1 therefore appends the fields at the end of the header block instead.

## 1. Grammar

Three lines. Each is anchored, has one spelling and no markdown emphasis (the plan-deps clean-break rule), and sits within `X_HEADER_LINES = 12`, the same as `plan_lifecycle.HEADER_LINES` (`.ci/rediacc_ci/quality/plan_lifecycle.py:78`).

```
Priority: P0|P1|P2|P3 [(operator)] [-- <reason>]
Concurrency: parallel [-- <reason>]
Concurrency: exclusive -- <reason, 12+ chars>
Owns: <glob>, <glob>, ...
Owns: none -- <reason, 12+ chars>
```

- **Regexes:**
  - `^Priority: (P[0-3])(?: \((operator)\))?(?: (?:--|—) (\S.*))?$`
  - `^Concurrency: (parallel|exclusive)(?: (?:--|—) (\S.*))?$`
  - `^Owns: (.+)$`
- **Priority.** The reason is optional (the spec says so). `(operator)` is the only marker. P0 is most urgent.
- **Concurrency.** `exclusive` must give a reason, because it stops every other plan and the reason is what the operator audits.
- **Owns.** Comma-separated globs, relative to the repo root.
  - Allowed syntax: `*`, `?`, `**`, `[...]` and `{a,b}` (at most 32 expansions per glob). A trailing `/` means `/**`.
  - Refused: an absolute path, `..`, `!` negation, a backslash, an empty item.
  - `none -- <reason>` is for plans that edit no files, for example the A0 appendix or an operator-action plan.
- **Implicit ownership, not declared:**
  - every plan owns its own file, `agent/plans/<basename>`;
  - overlap ignores `agent/worklist/**` and `agent/*/STATE.md`, which are append-only state written through verbs. The implementer confirms this list against which paths `worklist.py` writes.
- **Placement.** `set_x` appends the three lines directly after the last `Key: value` line of the header block that starts at `Status:`, so no existing field changes line number. Written after plan-deps' `Depends-On:` insertion, the worst cases are:
  - the renet record: fields at lines 9-11, with its spine still at 5-8;
  - `PLAN-env-to-bitwarden-v2.md`: lines 9-11.
- **Required set.** The same as `Depends-On:`: every non-stub `agent/plans/PLAN-*.md` whose Status is not in `wl_planfile.FINISHED_STATES` (`.claude/hooks/stop/wl_planfile.py:120`).
  - Exempt: stubs, `compacted` records and `_done/`/`_removed/`.
  - A plan revived by `--plan-revive` must gain the fields (T6).

**Out of scope:** an `(operator)` marker on Concurrency or Owns. The spec protects Priority only. Adding the marker to the other two later is a one-regex change.

## 2. Ordering: dependencies, then operator priority, then AI priority, then age

**`wl_planconc.rank(rel, graph) -> (op_rank, ai_rank)`:**
- an operator value `Pn (operator)` gives `(n, 4)`;
- an AI value `Pn` gives `(4, n)`;
- a missing or malformed field gives `(4, 4)`.

**Inheritance (decision D6).** A plan that other plans depend on, directly or transitively, takes the most urgent rank among itself and those dependents. Operator-ness is inherited as well. Without this, a P0 plan blocked on a P3 dependency waits behind every unrelated P1: "a dependency beats priority" would hold only between the two plans and not across the queue. The walk uses the reverse edges of plan-deps' `Graph`, which is loaded once per stop, and stops at cycles the same way `Graph.cycles` does.

**`order_key(rec, ctx)`** returns `(blocked, op_rank, ai_rank, age)`:
1. `blocked = 1` when the item's plan has non-empty `dep_roots` (plan-deps §2c), else 0. This is spec step i.
2. `op_rank`: spec step ii.
3. `ai_rank`: spec step iii.
4. `age`: spec step iv. Each picker keeps its own existing age direction:
   - items: `rec["first"]` ascending;
   - queue: `lease_at` ascending, the time spent in the queue;
   - backlog: mtime DESC, the operator's earlier ruling recorded at `.claude/hooks/stop/wl_backlog.py:3`.

**Items not linked to a plan (decision D3)** rank as an AI P2, `(4, 2)`. Urgent ad-hoc fixes are then not starved behind every P3 plan, and they do not jump past P0/P1 plans.

**Decision D1, the literal reading (recommended, and what the spec says).** The key is lexicographic, so every operator-ranked plan comes before every AI-ranked plan, and an operator P3 beats an AI P0. The alternative is `(effective_level, operator-first, age)`, which reads an operator P3 as a demotion. The /ask in T11 puts both, recommended option first.

**Call sites (T7/T8):**
- `guided_slice` (`.claude/hooks/stop/wl_checks.py:1601`): sort by `(band, order_key)`. Bands are obligations and stay first: a dead lease outranks any plan. Priority orders rows inside a band.
- `classify_items` (`.claude/hooks/stop/wl_store.py:1273`): collect `(order_key, disp)` for owned open items and sort `open_items` at the end. `others` and `deferred` keep fold order, which the oldest-first deferral checks rely on (`.claude/hooks/stop/wl_checks.py:3905`, :4397).
- `wl_roster.roster`: `queued = sorted(..., key=order_key)` replaces the `lease_at` sort at :602-604 (section 5c).
- `wl_backlog.next_plan` (`.claude/hooks/stop/wl_backlog.py:190`): order `eligible` by `(blocked, op, ai, -mtime)`. The first WHY line changes from "NEWEST first ..." to "Priority P1 (operator) -- <reason>; then newest".
- `wl_planenforce.evaluate` (:425): iterate `owned` in rank order before calling `first_box`.
- The ctx (Graph, parsed headers, `item_plan` map) is built once per stop. `wl_backlog` keeps its no-`wl_checks`-import rule (`.claude/hooks/stop/wl_backlog.py:23`); `wl_planconc` imports neither.

## 3. Which plan an item or a spawn serves

- **`item_plan(rec)`**, in this order:
  1. `wl_plandeps.linked_plan(basetext)` (`PLAN-x.md [<8hex>]`);
  2. the triage plan (`rec["triage"]["plan"]`);
  3. otherwise None.
- **`spawn_plans(text, by_id)`** reads the spawn's `prompt + description`, in this order:
  1. an explicit line `Plan: PLAN-x.md[, PLAN-y.md]` (new convention; T12 adds it to CLAUDE.md rule 4 next to "State the exact files each one owns");
  2. every `#<id>` (`wl_leasehelp.item_refs`) that resolves to an item with an `item_plan`. This is the same text auto-lease reads, so the plan the guard checks is the plan the lease records;
  3. a bare `PLAN-x.md [<8hex>]` token.

  It returns a set. A spawn serving several plans is checked against every one of them, with Owns taken as the union.
- **Declared Owns.** A line `Owns: <globs>` in the prompt, with the same grammar, is used only for a **planless** spawn (decision D4).
- **`live_plans(cwd, session_id, fold)`** returns `{plan_rel: [holder, ...]}`, combining:
  - this session: each `live_writers_estimate` row, then `metas[id]["jsonl"]`, then `first_prompt`, then `spawn_plans`. It also includes any fresh lease with `worker:<that id>` on an item with an `item_plan`;
  - other sessions: fold items in state `>` with `lease_state == "fresh"` and a worker not in {`queue`, `lead`} whose `item_plan` is set. A stale-but-fresh lease can cause a spurious refusal until it expires. The message names the lease so it can be released.
  - `worker:lead` and `worker:queue` are never holders.

## 4. Owns overlap

**`owns_overlap(A, B)` is exact and symbolic.** It needs no `git ls-files` on the spawn path, and it also covers files that do not exist yet.
1. `normalize_owns`: strip, apply the refusal rules (§1), expand braces, and turn a trailing `/` or a wildcard-free existing directory into `dir/**`.
2. Split each glob into `/` segments.
3. **`path_intersect(P, Q)`** is a DP over `(i, j)` segment positions:
   - `**` behaves like a `*` over whole segments (it can skip, or absorb one segment of the other side);
   - two ordinary segments advance together when `seg_intersect` holds;
   - the patterns intersect when `(len P, len Q)` is reachable.
4. **`seg_intersect(p, q)`** is the same DP over characters:
   - `*` either skips or absorbs one token of the other side;
   - `?` matches any single token;
   - a literal vs a literal must be equal;
   - a literal vs `[class]` tests membership;
   - a class vs a class is assumed non-empty, which over-approximates toward refusal, the safe side.
   - Cost is O(|p|·|q|) per pair. Around 36 plans with 10 or so globs each is negligible.
5. **Witness.** A traceback builds one concrete path (`*` becomes `x`, `**` becomes empty), so the refusal can say "both claim `.claude/hooks/stop/wl_roster.py`". The gate's `--overlaps` verb also materialises globs against `git ls-files` (with submodules) and prints real shared files.

**No Owns.**
- *Missing or malformed* on a required plan is CI finding D13 and a guard DENY at write time. At spawn time it **fails closed as `**`**: the spawn is refused with "PLAN-x.md declares no Owns; add it with `check_plan_deps.py --set-x`".
- *`Owns: none`*: a writer spawn serving that plan is refused (a writer for a plan that owns nothing is a contradiction).
- *Planless spawn* (decision D4):
  - while an exclusive plan is live, it is refused unless the prompt's `Owns:` is disjoint from that plan's Owns;
  - otherwise it is checked for overlap when the prompt declares `Owns:`;
  - with no declaration it is ALLOWED with a stderr note. Babysit/merge fix writers are planless, and Y's focus mode governs them.

## 5. Mutex and overlap enforcement

### (a) At spawn: `block_plan_concurrency.py` (pre-agent, ORDER 4, after the cap)

**Flow**, modelled on `block_agent_cap.run` (:82-107):
1. Not Agent/Task: ALLOW. A read-only type (`wl_roster.read_only_types`): ALLOW.
2. `S = spawn_plans(...)` and `L = live_plans(...)` minus the plans in S. A second writer for the same plan is the plan's own internal disjointness, and the plan's task split states it.
3. **DENY (mutex)** when some live plan in L is `exclusive`.
4. **DENY (mutex, symmetric; decision D5)** when some plan in S is `exclusive` and L is non-empty. A mutex that can be taken while others hold files is not a mutex.
5. **DENY (overlap)** when `owns_overlap(owns(s), owns(l))` holds for any s in S and l in L.
6. Planless: the rules in §4.
7. **Fails open, with a stderr line, on:** modules that cannot be imported; a fold that cannot be read; `live_writers_estimate` returning None when no cross-session lease is visible either. The Stop backstop (c) recounts from the authoritative event.

**The refusal text names:**
- the holder plan, its writers or leases, and its Concurrency;
- the overlapping globs and the witness path.

**Exits it prints:**
1. Queue the work: `worklist.py --lease <me> <id> +120 worker:queue`. This is accepted while the item is held (T9), and queue-slot names the item when the holder finishes.
2. If the plan over-claims, narrow its Owns with `check_plan_deps.py --set-x` (visible in the diff).
3. Dispatch read-only work as Plan/Explore instead.
4. Stop the holder (TaskStop) and release its lease.

**`DEFECT`** = the line that returns DENY for an exclusive holder, replaced by `pass`. The differential then sees the guard stop speaking on the mutex EDGE_CASE.

### (b) At queue: `worklist.py --lease worker:queue`

`.claude/hooks/stop/worklist.py:1136-1145` currently refuses a queue lease while a slot is free. T9 adds an allow branch: the item's `item_plan` is held (step 3, 4 or 5 of `spawn_verdict`, evaluated as if spawning for that plan). The note is stamped `HELD_BY:PLAN-y.md`. Otherwise the refusal stands, and R20260925.7's wording applies.

### (c) At stop: queue-slot, the backstop and the wait

- **`queue_start`** (`.claude/hooks/stop/wl_roster.py:602-612`):
  - `queued` is sorted by `order_key`;
  - the K candidates come from items that are neither `waiting_on` (R20260925.5) nor held (`spawn_verdict` against the roster's own live writers plus the fold's leases);
  - held items stay `covered` and are returned as `queue_held: [(id, reason)]`.
  - `defects` (:732) is unchanged, because held items are not in `queue_start`.
- **`V_QUEUE_SLOT`** (`.claude/hooks/stop/worklist_messages.py:2505`) gains one line per held item, at most 3, with the rest counted:

  ```
  held back: #abcd1234 [P1 op] -- PLAN-y.md is exclusive and live (writer a1b2c3d4)
  ```

  When every queued item is held, queue_start is empty and there is no vadd.
- **`roster-concurrency`**, a new key in `ROSTER_KEYS` (:51) and in the cap-wait keep list (`cap_wait_keeps`, :104). From the authoritative event, if two live writers serve plans that violate the mutex or overlap, it blocks with "stop one; the spawn guard was bypassed or blind". This is the two-layer pattern from `block_agent_cap.py`'s docstring.
- **`cap_saturated_wait`** (:90) also holds when `writers < WRITER_CAP` but `queued > 0`, `queue_start` is empty and every queued item is in `queue_held`. That is a concurrency-saturated wait. Its allow line gets a variant of `N_CAP_WAIT` (`worklist_messages.py:2514`) that names the holder plan.

**Residual, named here.** The lead's own inline edits are not governed by the mutex. The pre-agent guard only sees spawns. An open item of a held plan still shows in the guide, annotated `held: PLAN-y.md exclusive, live`, and its exit is the queue lease in (b). A pre-edit mutex for the lead is a possible follow-up, not in this plan.

## 6. Enforcement of the fields

### (a) Write time: `block_plan_without_depends.py`, extended

This is the plan-deps T3 guard. It already applies the Edit to the on-disk text and checks the resulting document.
- **Required plans:** DENY when Priority, Concurrency or Owns is missing, malformed or outside the 12-line window, or when a glob fails §1.
- **Operator freeze.** Parse the on-disk `Priority:`. If it carries `(operator)`, DENY when the resulting document drops the line, drops the marker, or changes the level or the reason (whitespace-normalised). A Write that replaces the file is checked the same way.
- **Operator-directed escape**, the only one, with no suppression token:
  - ALLOW the change when the new line still carries `(operator)` AND the operator's latest turn names both the plan (basename or slug) and the new `P[0-3]`;
  - "the operator's latest turn" is `wl_admit.turn_tools(transcript_path)`'s last operator text (`.claude/hooks/stop/wl_admit.py:334`, filtered by `_is_operator_turn` at :311), or an AskUserQuestion tool_result in the same tail;
  - the AI cannot write either one.
- **Introducing `(operator)` on a line that had none** follows the same rule. The AI cannot promote its own value to "operator" without an operator turn that says so.
- **Message:** "Priority on PLAN-x.md is operator-set; the AI never changes it. Ask the operator (AskUserQuestion), or they edit the line."
- **Residual:** Bash writes (`sed -i`, python) bypass the pre-edit chain. CI finding D17 is the backstop.

### (b) CI: `check_plan_deps.py`, new findings

| Code | Finding |
|---|---|
| D10 | a required plan has no `Priority:` |
| D11 | `Priority:` is malformed, or there are two lines |
| D12 | `Concurrency:` is missing or malformed, or `exclusive` has no reason of 12+ chars |
| D13 | `Owns:` is missing or malformed, or `none` has no reason |
| D14 | an Owns glob escapes the repo (absolute, `..`, `!`, backslash) or expands to more than 32 |
| D15 | a `parallel` plan claims a universal glob (`**`, `*`, `**/*`): exclusive in disguise |
| D16 | a header window overflow: an X field beyond line 12, OR the migration pushed `Status`/`Owner`/`Depends-On` or a record spine field (`Full-Text*`, `Record-Sig`) beyond line 10 |
| D17 | against `git merge-base HEAD origin/main`, an `(operator)` Priority was removed or demoted to an AI value. A level change that keeps the marker is printed as an INFO row for the operator to see, never red, because the operator's own hand edit looks identical. |
| D8 (extended) | the vacuity floor also requires at least 10 required plans with a parsed X triple |

- **Selftest:** each finding is planted into the clean fixture and must go red, and the clean fixture stays green. The `CONTROL_FLOOR` is raised to cover them.
- **New verb `--overlaps`:** a read-only report of every pair of required plans whose Owns overlap, with materialised shared files. It is advisory, since overlap only matters when both are live.

## 7. The one-pass migration

**Verb:** `check_plan_deps.py --migrate-x`. It reuses the grammar and the overlap engine, and it never writes without `--apply ... --write`.

1. **`--migrate-x` (default: print only).** For each of the 36 required plans, compute a seed:
   - **Priority:**
     - Status `executing`/`in-progress`/`active`/`mostly*`/`partially`/`phase` gives P1;
     - `approved`/`ready` gives P2;
     - `draft`/`proposed`/`design`/`parked`/unknown gives P3;
     - one level up (not past P1) when the plan quotes an "Operator order" dated within 7 days;
     - reason: `seed: Status <s>, <n> open boxes`.
   - **Owns:** repo paths cited in the plan's OPEN boxes (backticked paths and `path:line` anchors), falling back to the whole text when there are none.
     - Keep a path that exists, or that is a new file under an existing directory. Four or more siblings collapse to `dir/*.ext`.
     - Paths cited only as evidence ("measured in", "see") are dropped by a window of 6 words before the citation.
   - **Concurrency:**
     - `exclusive` when the open boxes mention `npm run gen:`, `regenerate`, `every file`, `repo-wide`, `mass`, `reflow` or `bulk`;
     - `exclusive` when the seed Owns has more than 40 materialised files;
     - otherwise `parallel`.
2. **`--migrate-x --save`** writes the seeds plus a per-file sha256 to `.ci/cache/plan-x-migration/proposal.json`. That path is ignored, so nothing tracked changes.
3. **The lead (the AI) reviews every row** and edits Priority reasons and Owns in the JSON. These become the AI proposals.
4. **`--migrate-x --table`** prints the one approval table:

   ```
   #  plan                         Status     open  Priority (why)            Conc.      Owns (n: first 2)                 overlaps with
   1  PLAN-retire-bash-oracles.md  approved   14    P2 (in flight, ...)       parallel   9: .claude/rediacc_hooks/guards/*  PLAN-plan-dependencies.md
   ...
   ```

   Then one AskUserQuestion:
   - "Approve all as shown" (recommended);
   - `Approve, with the changes I type`;
   - "Show the overlapping rows first";
   - "Hold the migration".

   D1-D7 ride as extra questions in the same /ask batch.
5. **Decision D2.** Rows the operator changes are written with `(operator)`. Rows approved as proposed stay AI values, so the AI may re-rank them later as work moves. Everything the operator typed is frozen.
6. **`--migrate-x --apply <json> --write`:**
   - refuses a file whose sha256 changed since `--save`;
   - validates every value through `parse_header` / `normalize_owns`;
   - writes the 3 lines via `set_x` (§1 placement) and nothing else;
   - prints `git diff --numstat`-shaped proof;
   - `--diff` without `--write` prints the unified diff of every file (the dry-run diff the spec asks to test).
7. **One commit**, with T3 and T4. No grandfather clause, same as plan-deps. The commit message carries the proof `block_unproven_bulk_transform` needs: "36 files, each diff exactly 3 added header lines (numstat 3 0)".
   - If plan-deps T10 (`Depends-On:` backfill) has not run yet, run it first in the same commit and state 4 lines.
   - The renet record takes the fields through this Python path, because `block_compacted_plan_edit.py` (ORDER 11) refuses an Edit to a record's header.

**Scope (decision D7).** "Every existing plan under agent/plans" is read as the 36 required plans. The other 168 are exempt:
- 44 stubs (pointers);
- 74 `compacted` records (their bytes come from `wl_planrec.render`; nothing can start them);
- 51 `_done/` (terminal; they expire after 40 days).

The alternative, writing to all 204, forces a re-render of 74 records for fields nothing will read.

## 8. Tests and mutation controls

Every case has a control that passes. Every mutation uses the private-copy `mutated_hook` pattern (`.claude/rediacc_hooks/tests/test_wl_cap_wait.py:253-273`), or a guard's `DEFECT` tuple.

**`.claude/rediacc_hooks/tests/test_wl_plan_priority.py` (new, B):**
- **o1, dependency beats priority.**
  - X is `P0 (operator)` and depends on Y, which is P3 and incomplete. Y's item comes before X's in `guided_slice`, `open_items`, `queue_start` and `next_plan`.
  - Control: Y finished, so X comes first.
  - Inheritance: with an unrelated P1 plan Z, the order is Y, then Z, then X.
  - Mutation: drop the `blocked` term from `order_key`, and o1 must fail.
- **o2, operator beats AI.**
  - A is `P2 (operator)` and B is `P0` (AI). A comes first (D1, literal reading).
  - Control: both AI, so B comes first.
  - Mutation: swap the op/ai terms, and o2 must fail.
- **o3, age.** Equal rank means the older `first` comes first. For the queue, the older `lease_at`.
- **o4.** An unlinked item ranks as AI P2, between a P1 plan and a P3 plan.
- **o5, guide display.** `- [ ] #id [P1 op] (upd 5m) ...` and `[P3]`, and bands are never reordered: a dead lease row still leads.

**`.claude/rediacc_hooks/guards/test-block_plan_concurrency.py` (new, A):**
- **m1, mutex refusal.** A live writer whose prompt names `#item` linked to E (`exclusive`), then a spawn for F: DENY, and the text names E and the writer.
  - Control m1c: E's writer is proven finished, so ALLOW.
  - Control m1d: a spawn for E itself, so ALLOW.
- **m2, symmetric mutex.** A spawn for exclusive E while F is live: DENY. Control: nothing live, so ALLOW.
- **v1, overlap refusal.** Live P owns `a/**`, and a spawn for Q owns `a/b.py`: DENY, and the witness `a/b.py` is printed.
  - Control v1c: Q owns `c/**`, so ALLOW.
- **v2, cross-session.** A peer's fresh `worker:<id>` lease on a P-linked item counts as live. Control: an expired lease does not.
- **n1.** A plan with no Owns: DENY (fail closed). `Owns: none`: DENY. A planless spawn with no `Owns:`: ALLOW with a note. Planless with overlapping declared Owns: DENY.
- **f1.** An unimportable stop dir: ALLOW with a stderr warning.
- **Read-only spawns:** ALLOW.
- **`DEFECT`** must turn the suite red, as `test_guards_differential.py` requires for OWN_SUITE guards.

**`owns_overlap` unit table (in `test-plandeps.py`, A):**
- `a/*.py` vs `a/b.py`: yes.
- `a/**` vs `a/b/c.ts`: yes.
- `a/*.py` vs `a/b/c.py`: no.
- `**/*.md` vs `docs/x.ts`: no.
- `{x,y}/z` vs `y/*`: yes.
- `wl_[a-c]*.py` vs `wl_roster.py`: no.
- `dir/` vs `dir/f`: yes.
- A witness is produced for every yes.

**Queue and roster (`test_wl_roster.py`, `test_wl_cap_wait.py`, `test_wl_leases.py`, B):**
- q1: the queued item of a held plan is skipped, and the next unheld one is named. Control: the holder finishes, so the held item is named.
  - Mutation: remove the held skip, and q1 must fail.
- q2: every queued item held gives no queue-slot vadd and gives the concurrency-saturated wait allow. Control: one unheld item gives the queue-slot block.
- q3: `roster-concurrency` fires on two live overlapping writers from the event. Control: disjoint writers.
- l1: `--lease worker:queue` with a free slot is accepted for a held item and refused for an unheld one (the existing refusal is the control).

**Operator freeze (`test-block_plan_without_depends.py`, A):**
- DENY: an Edit changing `P1 (operator)` to `P0 (operator)`; an Edit dropping the marker; a Write omitting the line; the AI introducing `(operator)` with no operator turn.
- ALLOW: an AI value change `P2` to `P1`; a prose edit; an operator-directed change with a transcript fixture whose last operator turn says "make PLAN-x.md P0".
- `DEFECT` on the freeze comparison must go red.
- Gate D17: plant a demotion against a fixture base, which goes red. A marker-kept level change gives INFO only, not red.

**Migration dry-run diff (`.ci/rediacc_ci/tests/gates/test_gate_plan_deps.py`, A):**
- On a fixture tree of 5 plans (live, the renet-shaped record, a stub, compacted, `_done/`):
  - `--migrate-x --diff` output equals a golden;
  - the tree is byte-identical afterwards (sha256 before and after);
  - only the 2 required plans appear;
  - the record's spine stays within line 10.
- `--apply` without `--write` writes nothing.
- `--apply` on a file changed since `--save` is refused.
- `--apply --write` yields numstat `3 0` per file.
- Mutation: remove the `--write` check, and the tree-unchanged assertion must fail.

**Wiring:**
- No new package.json gate (same gate), so no gates.lock lane change beyond what `npm run gen:gates-lock` recomputes for the manifest paths (add `.claude/hooks/stop/wl_planconc.py`);
- `hook-inventory-baseline.json` gets the new guard;
- the `test_canonical_sys_path_hop.py` BASELINE covers the new test files;
- `wl_planconc.py` is added as a sealed module in `.ci/policy/worklist-env-registry.json`;
- `gen:docs` (plan-records.md header table).

## 9. Decisions for the operator (put through /ask with T11; recommended option first)

- **D1:** order across plans. Literal lexicographic, where operator-ranked plans come first (spec wording), vs. effective level with operator breaking ties.
- **D2:** migration rows approved as proposed stay AI values, vs. all approved rows become `(operator)`.
- **D3:** unlinked items rank as AI P2, vs. last.
- **D4:** planless writers under a live exclusive plan are refused unless their declared Owns is disjoint, vs. always refused, vs. never.
- **D5:** exclusive is symmetric (an exclusive plan cannot start while others are live), vs. one-directional as literally worded.
- **D6:** priority inherits through Depends-On, vs. no inheritance.
- **D7:** migration scope is the 36 required plans, vs. all 204.

### Critical Files for Implementation
- /home/developer/console/.claude/hooks/stop/wl_roster.py
- /home/developer/console/.claude/hooks/stop/wl_checks.py
- /home/developer/console/.claude/rediacc_hooks/guards/block_agent_cap.py (template for the new pre-agent guard)
- /home/developer/console/.claude/hooks/stop/wl_backlog.py
- /home/developer/console/agent/plans/PLAN-plan-dependencies.md (defines wl_plandeps, check_plan_deps and block_plan_without_depends, which this plan extends; none of them exist yet)

## Operator rulings (2026-09-25, AskUserQuestion)

- **D1: literal lexicographic order.** Every operator-set priority comes before every AI-set one (an operator P3 beats an AI P0).
- D2-D7 take the plan's recommendation unless the operator says otherwise at the T11 migration table.

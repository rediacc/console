# PLAN: plan dependencies. A plan does not start before the plans it needs are finished

Status: approved
Owner: d778be9d
First-Seen: 2026-09-24
Depends-On: PLAN-stop-hook-continuity.md
Worklist: #9fb25f26

**Operator order, 2026-09-24:** "we should not start implementing a plan before the required plan completes. It should be a mandatory field and should have at least explicit 'no-dep' if there is really no dependency. Maybe we can also align the stop hook system to benefit from it to push what's needed to go first."

**Why this plan depends on PLAN-stop-hook-continuity.md.** Its P2.4 `BLOCKED_BY` machinery is what this plan reuses. That machinery (`wl_leasehelp.py`, `wl_store.classify_items`, the UNBLOCKED note in `wl_checks.py`) is uncommitted on branch `0923-1`, and that plan still has one open box (P2.6). This plan edits the same files. It is the first real `Depends-On:` edge.

**Line numbers** refer to the working tree on `0923-1`, measured 2026-09-24. Most of `.claude/hooks/stop/` is modified there and not committed.

## Operator rulings (2026-09-24, /ask)

- **Run it** (Recommended option chosen).
- **Allow task edges too** (overrides this plan's section 1 "declined"). `Depends-On:` also accepts `PLAN-y.md#<task-ref>`. The rewording hazard the planner raised must be designed out, not accepted:
  - a task edge names a STABLE task id, not the 8-hex content hash. Boxes gain an optional explicit id prefix (the retro plan's `**R20260924.3**` style, or `T3`), and an edge `PLAN-y.md#T3` resolves by that id;
  - an edge by content sig is also accepted, but the gate (new finding D9) reports a task edge whose target box no longer exists, and names the closest current box by id and text so a reword is a one-line fix, never a silent break;
  - completion of a task edge = that box is `[x]` with a `present`/ticked evidence row; the stop-hook FIRST row names that box directly;
  - tests: task-edge resolve, reworded-box D9 with suggestion, id-edge surviving a reword, task edge complete/incomplete in the lease/tick gate.

## Tasks

Two writers at most. Writer A owns the grammar, the CI gate, the guard, the record and move verbs, and the wiring. Writer B owns the worklist verbs and the stop hook. The lead owns the migration review and the prose. Every task after T1 needs T1's API frozen first.

- [ ] T1 [A] Create `.claude/hooks/stop/wl_plandeps.py`, the one home of the grammar (section 1). It holds `parse_header`, `resolve`, `is_complete`, `Graph.load(root)`, `cycles`, `roots(rel)`, `chain(rel, root)`, `linked_plan(item_text)`, `tracked_by(plan, fold)` (moved from `wl_backlog._claimed`, .claude/hooks/stop/wl_backlog.py:98) and `set_header(text, value)`. Use stdlib only at import time and import `wl_planfile` lazily inside `is_complete`. Controls go in `.claude/hooks/stop/test-plandeps.py` (section 5a).
- [ ] T2 [A] Add the CI gate `.ci/scripts/quality/check_plan_deps.py`. It carries findings D1-D8, `--selftest` controls with a `CONTROL_FLOOR`, and the verbs `--check`, `--draft` and `--set <path> "<value>" [--write]`. Add the plant test `.ci/rediacc_ci/tests/gates/test_gate_plan_deps.py`.
- [ ] T3 [A] Add the guard `.claude/rediacc_hooks/guards/block_plan_without_depends.py`. It sits in the pre-edit chain with `ORDER = 13` and `TWIN = None`, plus `EDGE_CASES`, a `DEFECT` tuple and its own suite `test-block_plan_without_depends.py`. The suite is required by .claude/rediacc_hooks/tests/test_guards_differential.py:596-620 for any guard with `TWIN = None`. Add the guard to `scripts/data/hook-inventory-baseline.json`.
- [ ] T4 [A] Records and moves:
  - add `Depends-On` to `wl_planrec.HEADER_FIELD_KEYS` (.claude/hooks/stop/wl_planrec.py:171) and emit it in `render()` right after `Owner` (.claude/hooks/stop/wl_planrec.py:832);
  - make `revive()` (.claude/hooks/stop/wl_planrec.py:2567) carry the record's `Depends-On:` into the revived header, or refuse without one;
  - make `check_plan_folders.py --move` (:459) refuse a move into `_removed/` while any required plan still depends on the plan being moved, and print those dependents.
- [ ] T5 [A] Wiring:
  - `package.json` gets a `ci-plan-deps` gate entry next to :192;
  - `scripts/ci-runner/manifest.ts` gets an entry after the `check:ci-plan-folders` entry (:2023-2044);
  - `.github/workflows/ci-quality.yml` gets a "Plan dependencies" step after :614;
  - then run `npm run gen:gates-lock`, `npm run gate:bind` and `npm run gen:docs` (ci-gates.md, the plan-records.md header table, doc-registry.md);
  - add BASELINE rows in `test_canonical_sys_path_hop.py` for the new test files.
- [ ] T6 [B] Make `wl_leasehelp.waiting_on` / `blocker_error` / `auto_lease_candidates` plan-aware (section 2c). Wire the per-stop `Graph` through `wl_store.classify_items` (.claude/hooks/stop/wl_store.py:1270-1290), including the fail-closed suffix for an untracked dependency.
- [ ] T7 [B] Add the verb gates in `worklist.py`:
  - `--lease` (:1014) and `--tick` (:945) are refused on a dependency-blocked linked item;
  - `--plan-tick` (`_plantick_cli`, :584) is refused unless the box has a `present` investigation row;
  - the `DEPS-WAIVED:` override applies to all three;
  - `--add` (:902) and `--migrate --plan` (:1308) print a NOTE naming the chain.
  - Update the messages and help text in `worklist_messages.py`: N_UNBLOCKED at :1199, help at :1925, plus the new REFUSED and NOTE strings.
- [ ] T8 [B] Stop-hook alignment, all described in section 3:
  - FIRST rows in `guided_slice` (.claude/hooks/stop/wl_checks.py:1237-1362);
  - plan-aware waiting rows (:1281);
  - the `N_UNBLOCKED_PLAN` variant in the UNBLOCKED block (:2051-2066);
  - `wl_planenforce.evaluate` names the chain root's box (:425);
  - `wl_backlog.next_plan` / `_redirect` switch to finished-only semantics (:119, :190);
  - `--add` recipes carry `PLAN-x.md [<sig>]` (.claude/hooks/stop/wl_planfile.py:658, .claude/hooks/stop/wl_backlog.py:343, the wl_planenforce render).
- [ ] T9 [B] Add the controls in `.claude/hooks/stop/test-depgate.py` (section 5c), and rewrite the DEPENDENCY controls in `test-backlog.py` to the new semantics.
- [ ] T10 [lead] Run `check_plan_deps.py --draft` and put the 13 plans with candidate edges to the operator through /ask (section 4). Apply all 30 values with `--set ... --write`. Land them in the same commit as T2 and T3, with a bulk-transform proof line in the commit message.
- [ ] T12 [A] Task edges per the operator ruling: stable task ids in boxes, `PLAN-y.md#<id>` and `#<sig>` edges, finding D9 with nearest-box suggestion, task-level completion in the lease/tick gate and the FIRST row.
- [ ] T11 [lead] Update the prose:
  - CLAUDE.md line 37 (the plan sentence);
  - agent/README.md layout section (:16-32);
  - docs/agent-reference/plan-records.md (a record carries `Depends-On`);
  - register `DEPS-WAIVED:` in docs/agent-reference/suppressions.md;
  - run the full hook suite, the four plan gates and `check:ci-gate-bind` / `check:ci-gates-lock`.

## 0. Facts established

### Plan headers today

**Counts, `agent/plans/PLAN-*.md` top level, first 10 lines, measured 2026-09-24:**
- 148 files.
- 147 carry `Status:`. The one without is `PLAN-retire-bash-oracles.A0.md`, a companion appendix.
- 91 carry `First-Seen:` and 82 carry `Owner:`.
- 0 carry `Depends-On:` anywhere in any folder.

**What those 148 files are:**
- 44 stubs (`Status: moved` plus `Moved-To:`);
- 74 finished records (`Status: compacted`);
- **30 real live plans**: 7 draft, 5 ready, 4 proposed, 3 executing, 1 parked, 1 companion with no Status, and 9 with odd status words (mostly-done, partially, phase, w, approved, active, in-progress, design, mostly).

`_done/` holds 51 plans (47 done, 2 superseded, 2 landed). `_removed/` does not exist yet.

**Where headers are parsed:**
- `wl_checks.py`:
  - `PLAN_STATUS_RE` at :586 and `PLAN_STATUS_INLINE_RE` at :587;
  - `PLAN_HEADER_LINES = 10` at :588;
  - `PLAN_OWNER_RE` at :590;
  - `plan_owner` at :611 and `plan_records` at :640.
- `wl_planfile.py`: `FINISHED_STATES` at :120, `NOT_STARTED_STATES` at :146, the adopted-Owner format at :337-347 and the `Ruling:` window at :369.
- `wl_planrec.py`: `HEADER_LINES = 10` at :146, `HEADER_FIELD_KEYS` at :171, `box_sig` at :652 and `render` at :832.
- `wl_planindex.py`: the census consumed by `wl_backlog._open_boxes` (.claude/hooks/stop/wl_backlog.py:87).
- `wl_planenforce.py`: reads Status through `recs` and Owner through the injected `plan_owner`.
- `wl_planfid.py`: task parsing only, no header fields.
- `.ci/rediacc_ci/quality/plan_lifecycle.py`:
  - `HEADER_LINES = 12` at :78;
  - `STATUS_RE`, `FIRST_SEEN_RE`, `MOVED_TO_RE`, `REMOVED_WHY_RE` and `BLOB_RE` at :95-99;
  - `FINISHED_STATES`, a mirror of wl_planfile's list, at :123.

**An optional `Depends-On:` already exists and nobody uses it.**
- `wl_backlog.py` defines `DEPENDS_ON_RE` at :38 and `plan_depends_on` at :53. `_resolve_dep` (:75) accepts a bare basename. `_redirect` (:119) blocks only while the target is neither finished nor claimed. That weaker rule was a deliberate choice ("would serialize the whole backlog", :123).
- The operator's order now requires the stronger rule: a dependency blocks until it is finished. This plan replaces that module's grammar and semantics outright (clean break).

**The plan gates** (package.json):
- `check:ci-plan-housekeeping` :169
- `check:ci-plan-boxes` :187
- `check:ci-plan-implementation` :188
- `check:ci-plan-record` :189
- `check:ci-plan-citations` :191
- `check:ci-plan-folders` :192

`.ci/scripts/quality/check_plan_boxes.py:97` and `.ci/scripts/quality/check_plan_implementation.py:77` both import the stop-hook directory through `paths.on_sys_path(paths.hooks_stop_dir(ROOT))`. That is the precedent this plan uses to keep the grammar in a single module.

### How plans move, and what "complete" means today

- **Layout.** `.ci/rediacc_ci/quality/plan_lifecycle.py:47-55`, `wl_store.AGENT_PLAN_SUBDIRS` (.claude/hooks/stop/wl_store.py:227) and `agent_plan_files` (:286), which drops stubs.
- **`--move`** (.ci/scripts/quality/check_plan_folders.py:27, :459; `_stamp` :515) does a `git mv` into the target folder, leaves a stub, and stamps `First-Seen:` and `moved_at`.
- **Folder by status.** `classify` (.ci/rediacc_ci/quality/plan_lifecycle.py:311) derives the state from Status alone. `folder_for` (:329) maps done to `_done/`, removed to `_removed/`, and **record states (`compacted`, `parked`) to `agent/plans/`**. Finding F2 (:399) refuses a folder that disagrees with the Status.
- **Expiry.** F3 (:425) expires terminal plans after 40 days and F4 (:448) expires untouched backlog plans after 90 days. An expired plan is deleted and leaves a tombstone row in `agent/INDEX.md` (`parse_tombstones` :681). That section does not exist yet; the first `_done/` expiries fall around 2026-10-31.
- **Conclusion.** "Complete" is a Status property, not a folder property. 74 finished records sit in `agent/plans/` on purpose. The Status can be trusted because check:ci-plan-boxes G-A3 refuses a finished Status over open boxes unless a `Ruling:` resolves (docs/agent-reference/plan-records.md:23-30).

### The stop hook's ordering machinery

**`BLOCKED_BY`** (wl_leasehelp.py):
- the regex is at :29, `blocked_by` at :43, `resolve` at :54 and `waiting_on` at :62;
- `blocker_error` at :72 refuses an unknown blocker, a closed blocker, the item itself, and a cycle;
- `auto_lease_candidates` at :143 skips waiting items.

**Consumers of `BLOCKED_BY`:**
- `worklist.py --add` :902-908 and `--update` :1006-1010;
- `wl_store.classify_items` :1283-1286: a waiting item is left out of `open_items`, and "the chain's root still blocks";
- the guide's waiting row, .claude/hooks/stop/wl_checks.py:1281-1289 (priority 3, "NEXT: nothing until they close");
- the UNBLOCKED sticky note, .claude/hooks/stop/wl_checks.py:2051-2066, text at .claude/hooks/stop/worklist_messages.py:1199;
- `.claude/hooks/stop/wl_roster.py:482`;
- help text at .claude/hooks/stop/worklist_messages.py:1925.

**Link from a worklist item to a plan box.** It is a text convention, `PLAN-x.md [<8hex>]`, with 200 occurrences in `agent/worklist/*.jsonl`. No code parses the pair:
- "Is this plan tracked?" is answered by basename containment: `wl_backlog._claimed` :98, and `plan_drift_rows` at .claude/hooks/stop/wl_checks.py:670 and :714.
- The 8-hex value is `wl_planrec.box_sig` (:652). `wl_claimcheck._SIG_RE` (:292) matches it as a whole token.

**Open plan boxes surfaced on the stop path:**

| Name | Kind | Location |
|---|---|---|
| plan-drift | vadd | .claude/hooks/stop/wl_checks.py:2829-2848 |
| plan-adopted | vadd | :2869 |
| plan-tasks | outq, priority 2 | :2856-2895 |
| plan-backlog | outq, priority 2 | :2902-2930 |
| plan-clock / plan-unimplemented | outq, or a vadd over the ceiling | :2940-2948, which names one box via `wl_planenforce.evaluate` / `first_box` (:160, :425) |

**The store-derived guide**, `guided_slice` (.claude/hooks/stop/wl_checks.py:1237), sorts `(priority, line)` rows at :1356 and is emitted on every full stop at :2437. The `open-items` vadd is at :2626.

### The guard at write time

`block_plan_without_tasks.py`:
- `CHAIN = "pre-edit"`, `TWIN = "pre-edit/block-plan-without-tasks.sh"`, `ORDER = 10` (:53-55);
- `PLAN_GLOBS` :61;
- `run` :256.

Its twin is a bash oracle, and `PLAN-retire-bash-oracles.md` (APPROVED, in flight) is retiring every oracle. Changing this guard now would mean regenerating goldens or oracle output in the middle of that plan. A **separate untwinned guard** (`TWIN = None` plus its own suite) avoids the collision. The precedent is `block_prose_style_edit.py` (ORDER 12), which also imports its engine with a scoped `sys.path` insert (:229-244).

`block_compacted_plan_edit.py` (ORDER 11) **refuses any Edit that touches a header field of a record**. So the one live `parked` record (`PLAN-renet-fetch-hardening.md`) can only get its field through Python. That is why T2 adds the `--set` verb.

## 1. The header field

**Syntax.** One line, anchored, inside the first 10 lines. Ten is the smallest header window among the four readers: wl_checks :588, wl_planrec :146, wl_backlog :40, plan_lifecycle :78. Clean break: no `**` emphasis variant, and a single spelling.

```
Depends-On: PLAN-a.md, PLAN-b.md
Depends-On: no-dep -- <reason, one line, 12+ chars>
```

- Tokens are **bare basenames** `PLAN-<slug>.md`, never paths. Every plan moves once at close, so a path would go stale on the day the dependency finishes.
- The `no-dep` separator is `--` or `—`; the operator's own example used the em dash.
- The reason has a minimum length of 12 characters, the same floor as `--defer`'s WHY (worklist.py ~:968), and a small vague-word refusal list: `none`, `n/a`, `tbd`, `nothing`.
- A list mixed with `no-dep` is malformed. So is a second `Depends-On:` line, and so is a field outside the window.

**Dependencies on single tasks of another plan: declined.** An edge like `PLAN-y.md#41f56150` would name a box signature. The signature is a hash of the box's first 120 normalised characters (`box_sig`, .claude/hooks/stop/wl_planrec.py:652), so any rewording of that box silently breaks the reference. Completion would then need ledger lookups in `.ci/config/plan-boxes.json`, which roughly doubles the grammar, the resolver and the test matrix. When partial ordering matters, the answer is to split Y into a core plan and a remainder and depend on the core; splitting a plan is ordinary authoring. Revisit only if the T10 review finds 3 or more edges where a split is wrong.

**Resolution of one token**, in `wl_plandeps.resolve`, in order:
1. A non-stub real file with that basename in `agent/plans/`, `_done/` or `_removed/`. If two real files share the basename, the result is `ambiguous`.
2. A stub (`is_stub`: `Status: moved` plus `Moved-To:`) is followed exactly once.
3. Not found: look for a tombstone row in `agent/INDEX.md` (`plan_lifecycle.parse_tombstones`). A tombstone whose recorded path is under `_done/` counts as `complete`. Any other tombstone (a backlog plan that expired, or a removed one) counts as `withdrawn`.
4. Otherwise the token is `dangling`.

**Renames.** A rename is a plain `git mv` with no stub, so it shows up as `dangling`. The gate names every plan that cites the old name, and the fix is one `--set` per citing plan. No rename machinery is added.

**Completion.**
- `complete(Y)` is true when Y resolves and its Status is in `wl_planfile.FINISHED_STATES` (.claude/hooks/stop/wl_planfile.py:120, which includes `compacted`), or when Y is a `_done/` tombstone.
- The folder is not consulted. F2 already keeps folder and Status in agreement, and 74 complete records live in `agent/plans/` by design.
- `parked` is incomplete. `removed` and `_removed/` are `withdrawn`: refused as a target by CI, and fail-closed at run time.

**`no-dep`** is a positive statement with a reason, so an absent field can never read as "no dependency".

**Which plans must carry the field.** Every non-stub plan in `agent/plans/` whose Status is not in `FINISHED_STATES`: active, backlog, parked, and anything with an unknown status such as A0. That is **30 plans today**.

**Exempt, and why:**
- Stubs are pointers, rewritten by `--move`.
- Finished records (`compacted`) are history. Nothing can start them, and their bytes come from `wl_planrec.render`.
- Everything in `_done/` and `_removed/` is terminal and expires in 40 days.
- Harness plans in `.claude/plans/*.md` are not part of the corpus.

A plan that leaves the exempt set must gain the field at that moment: a Status edit back to a live word goes through the guard, and `--plan-revive` goes through T4.

## 2. Enforcement at three points

### (a) Write time: `block_plan_without_depends.py`

- **Scope:** `agent/plans/PLAN-*.md` only, top level, both `*/agent/plans/PLAN-*.md` and `agent/plans/PLAN-*.md`.
- **It checks the resulting document, not a union of old and new text.**
  - A Write is checked on its content.
  - An Edit or MultiEdit is **applied to the on-disk text** (`old_string` → `new_string`, honouring `replace_all`, edits applied in sequence), and the result is checked. This is exact where the sibling guard's union is only approximate, and it catches an Edit that deletes the line.
- **Exempt when the result is:** `Status: moved`, or a Status in `FINISHED_STATES`.
- **Refused when the field is:** missing, malformed, dangling, withdrawn, ambiguous, a self-dependency, or creating a cycle with the on-disk headers of other plans (the `Graph` is loaded with the incoming text in place of this file).
- **No grandfather clause.** It lands in the same commit as the backfill.
- **The message** prints both accepted shapes and `check_plan_deps.py --draft <path>` for a suggestion.
- **Fails open** when the stop directory or the module is unimportable (the sibling's convention, block_plan_without_tasks.py header). CI D1-D7 is the backstop.

### (b) CI: the `ci-plan-deps` gate

**Findings.** Each has a planted control in `--selftest`, and the gate header carries a `---- gate ----` block (step: Plan dependencies, needs: none, selftest: true, lane: quality-branch).

| Code | Finding |
|---|---|
| D1 | a required plan has no field |
| D2 | malformed (every sub-shape listed in section 1) |
| D3 | dangling token |
| D4 | withdrawn target (`_removed/`, `Status: removed`, or a non-`_done` tombstone) |
| D5 | self-dependency |
| D6 | cycle among the headers, reported as a path `A -> B -> A` |
| D7 | ambiguous basename |
| D8 | vacuity floor: at least 10 required plans parsed, and every one either produced a verdict or a finding. Zero parsed is `CannotRun`, never green. |

**Verbs:**
- `--check` (default).
- `--draft [<path>]` prints and never writes. For each required plan it shows the proposed value, then every other plan cited in its text with that plan's Status and completeness, at most 2 citing lines each, and a MUTUAL flag.
- `--set <path> "<value>" [--write]` validates through `parse_header`/`resolve`/cycle, then inserts the line after `Status:` or replaces the existing one. It is dry-run by default. It is the only door for records, because of the ORDER-11 guard.

**Manifest paths:** `agent/plans/**`, `agent/INDEX.md`, the gate, `.claude/hooks/stop/wl_plandeps.py`, `.claude/hooks/stop/wl_planfile.py`.

### (c) Start time: the worklist, reusing `BLOCKED_BY` semantics

- **Link.** `linked_plan(text)` returns the plan an item implements. That is a `PLAN-<slug>.md` token **immediately followed by ` [<8hex>]`**, the existing convention. A bare mention of a plan, such as "write PLAN-x.md", does not link. Otherwise planning or review items for X would be refused, and a wrong refusal costs more than a missed one here.
- **Blockers.** `dep_roots(X)` gives the incomplete dependencies of X at the bottom of each chain: walk the `Depends-On` edges depth-first, and stop at an incomplete plan whose own dependencies are all complete.
- **Waiting (extends `waiting_on`).** An open item whose linked plan has non-empty `dep_roots` is `waiting` **only if every root is tracked** (`tracked_by`: some open, deferred or leased item of any owner names the root's basename; the `_claimed` rule). That keeps "the chain's root still blocks": the root's items hold their owner's stop.
  - If a root is **untracked**, the item **fails closed to open**, with the display suffix `   <- blocked: PLAN-x.md needs PLAN-y.md finished first, and nothing tracks PLAN-y.md; start there (see FIRST in the guide)`. The pattern is the worker:lead suffix at .claude/hooks/stop/wl_store.py:1299-1302.
  - A cycle anywhere in the item's chain also fails closed to open, because a wait on a cycle would hide the item forever.
- **`waiting_on` returns** item ids and plan basenames. The guide renders ids as `#id` and plans bare. `state_doc["waiting"]` keeps item ids as today, so the UNBLOCKED diff (.claude/hooks/stop/wl_checks.py:2053-2066) needs no change beyond choosing its message.
- **`blocker_error`** (:72) gains plan edges in its walk: a plan node's successors are the open items linked to it. So `BLOCKED_BY:#b` is refused when #b waits, through a plan, on the item being edited.
- **`auto_lease_candidates`** (:143) skips any item with non-empty `dep_roots`, tracked or not.

**Verbs, decided:**

| Verb | With incomplete deps | Why |
|---|---|---|
| `--lease` (.claude/hooks/stop/worklist.py:1014; the comma form at :927 goes through it per item) | **REFUSED** (exit 2) | Leasing is the start. |
| `--tick` (:945) | **REFUSED** (exit 2) | Without this, a session does the work inline without a lease and ticks it, and the order gate is decorative. |
| `--plan-tick` (:584) | **REFUSED**, unless `wl_planrec.investigation_for(root, rel, sig)` (:2021) holds a `present` row | `present` means the work was already in the tree, so recording it starts nothing. |
| `--add` (:902) | allowed, with a stderr NOTE naming the chain | The item simply classifies as waiting or fail-closed open. |
| `--migrate --plan` (:1308) | allowed, with a NOTE | Adoption is ownership, not implementation. |
| `--plan-investigate`, `--update`, `--defer` | not gated | They start nothing. |

**The refusal text** names the chain, the root, the root's first open box (`sig body`) and three exits:
1. finish the root;
2. change X's header if the edge is wrong, with `check_plan_deps.py --set` (visible in the diff, validated);
3. `DEPS-WAIVED: <reason, 12+ chars>` in the lease note or tick evidence.

The waiver is stored verbatim in the event text, shown in the guide as `(deps waived: <reason>)`, and registered in docs/agent-reference/suppressions.md, which governs every escape hatch. Exit 2 is the preferred one.

## 3. Stop-hook alignment: "push what's needed to go first"

**Carrier:** `guided_slice`, .claude/hooks/stop/wl_checks.py:1237. It is emitted on every full stop (:2437) and already ranks by priority (:1356).

Before the item loop, collect this session's open or waiting items linked to a plan with non-empty `dep_roots`, and group them by root. For each root, append a priority-0 FIRST row. Because the rows are appended first and the sort is stable, they lead the 0 band, ahead of X's own rows. Show at most 3 roots and count the rest: `+N more plan(s) must land first; worklist.py --list --open shows them`.

```
  - FIRST PLAN-stop-hook-rulings-campaign.md [Status: draft], 4 open box(es)
        chain: PLAN-stop-hook-continuity.md -> PLAN-remove-cross-session-messaging.md -> PLAN-stop-hook-rulings-campaign.md
        waiting on it: #a1b2c3d4, #e5f60718
        tracked by: nothing yet            | or: #9abc0def [>] owner 74de73ca (live)
        next box: 41f56150  Port the ruling ledger to the append-only store
        NEXT: worklist.py --add d778be9d "PLAN-stop-hook-rulings-campaign.md [41f56150] Port the ruling ledger to the append-only store"
                                            | or, when tracked by this session: work #9abc0def first
                                            | or, when a live peer tracks it: nothing for this session; the items above reopen when it is finished
```

**Waiting rows** (:1281) render `waiting (PLAN-stop-hook-rulings-campaign.md)` with `NEXT: nothing until PLAN-stop-hook-rulings-campaign.md is finished (a Status in FINISHED_STATES); it reopens by itself`.

**UNBLOCKED** (:2051) uses the new `M.N_UNBLOCKED_PLAN = "UNBLOCKED #%s: %s is finished, so it is open work again: %s"` when the item's last wait was a plan.

**Siblings made dependency-aware**, so that no advisory points at X while Y blocks it:
- `wl_planenforce.evaluate` (:425) names `first_box` of the **root** of the first owned row that has one, and says `(PLAN-x.md waits on it)`.
- `wl_backlog.next_plan` / `_redirect` (:119, :190) use `wl_plandeps` with finished-only semantics. A dependency tracked by a live peer makes X ineligible, and the next plan is tried. An untracked one is nominated in X's place, as today.
- The `--add` recipes carry `PLAN-x.md [<sig>] <body>` so that new items link by default: .claude/hooks/stop/wl_planfile.py:658 (sig via `wl_planrec.box_sig`), .claude/hooks/stop/wl_backlog.py:343, and the wl_planenforce door-2 line.

## 4. Migration of the existing plans

**Scope.** Only the 30 required plans (section 1). 44 stubs, 74 finished records and 51 `_done/` plans are exempt, for the reasons given there.

**Measured citation graph** among the 30:
- 12 cite no other plan, so their draft is `no-dep -- <reason>`.
- 5 cite only finished plans (compacted, `_done/`), which is harmless either way. Draft: `no-dep -- cites only finished plans: <names>`.
- **13 cite at least one incomplete plan**, about 17 candidate edges.
- Only 1 plan phrases a citation as a dependency ("depends on / blocked on / after ... lands"), and its target is already finished. Text phrasing therefore infers almost nothing, and **every candidate edge needs a human decision**.

**Known traps the review must settle:**
- **Two mutual pairs**, which would be D6 cycles if taken literally:
  - `PLAN-account-env-to-bws.md` ⇄ `PLAN-env-to-bitwarden-v2.md`;
  - `PLAN-stop-hook-overhaul.md` ⇄ `PLAN-stop-hook-rulings-campaign.md`.
- **Umbrella citations.** `PLAN-retire-bash-oracles.md` (APPROVED, in flight), `PLAN-b2-emit-matrix.md` and `PLAN-agent-tree-lifecycle.md` cite `PLAN-tooling-transformation.md` (ready, 646 KB umbrella). An edge from them to the umbrella would **block in-flight work behind an umbrella that finishes last**. Citation is not dependency.
- `PLAN-secret-namespace-migration.md` cites 3 plans that exist only in `agent/archive/plans/`. They are not dependencies.
- `PLAN-retire-bash-oracles.A0.md` is a companion appendix. Its value is `no-dep -- appendix of PLAN-retire-bash-oracles.md; carries no work of its own`.

**Review steps:**
1. `check_plan_deps.py --draft` produces the table.
2. The lead puts the 13 edge-candidate plans to the operator through `/ask` in batches of 4. Each question offers: edge as drafted, no edge (`no-dep -- related, not ordered: <plan>`), reverse the edge, or a custom answer. The recommended option comes first, and the mutual pairs are asked together.
3. The 17 `no-dep` drafts are applied by default and are visible in the diff for a post-hoc veto.
4. Apply everything with `--set <path> "<value>" --write`. The largest header block today ends at line 6, so one inserted line keeps every header key inside the 10-line window. The gate verifies this.
5. One commit, together with T2 and T3. The message carries the proof `block_unproven_bulk_transform` requires: "30 files, each diff exactly one added `Depends-On:` header line (git diff --numstat: 1 0 per file)".

## 5. Tests and controls, both directions

**5a. `test-plandeps.py`** (A). Each case is paired with a control that must pass.
- **parse:** each accepted shape (list, `no-dep --`, `no-dep —`) against each malformed sub-shape (path token, non-PLAN name, empty or trailing comma, `no-dep` without reason, reason under 12 characters, a vague reason, mixed, two lines, line 11).
- **resolve:** active; `_done`; followed stub; `_done` tombstone gives complete; backlog tombstone gives withdrawn; `_removed`; missing; ambiguous; self.
- **complete:** every `FINISHED_STATES` word; `compacted` in `agent/plans/` is complete; `draft` in `_done/` is still incomplete (Status wins; F2 owns the folder); `parked` is incomplete.
- **cycles:** a 2-cycle and a 3-cycle are reported with the path; a diamond is not.
- **roots/chain:** X→Y→Z with both Y and Z incomplete gives Z; Z complete gives Y; nothing incomplete gives none.
- **linked_plan:** `PLAN-x.md [41f56150] body` gives X; `write PLAN-x.md` gives None; a sig after the second token gives the second.
- `set_header` inserts after `Status:` and replaces an existing line.

**5b. Gate and guard** (A):
- `check_plan_deps.py --selftest`: D1-D8 each planted into a clean fixture must red, and the clean fixture must be green, with `CONTROL_FLOOR` asserted. `test_gate_plan_deps.py` does the same against a planted temp tree.
- `test-block_plan_without_depends.py` plus `EDGE_CASES`:
  - DENY: a Write without the field; malformed; dangling; `_removed` target; self; a cycle against an on-disk plan; an Edit deleting the line; an Edit to a plan that lacks it.
  - ALLOW: a valid list; `no-dep`; a stub; a finished record; a `_done/` path; `.claude/plans/x.md`; a non-plan doc; a prose Edit to a conforming plan.
  - The `DEFECT` tuple that disables the core condition must red the suite.
- `test-planrec.py`: a render round-trip keeps `Depends-On`; revive carries it, or refuses without it.
- `test_gate_plan_folders.py`: `--move` into `_removed/` is refused while there are dependents; allowed with none.

**5c. `test-depgate.py`** (B), each case paired:
- `--lease`/`--tick` on a linked item with an incomplete dependency is refused. Allowed when: the dependency is complete; the item is unlinked; `DEPS-WAIVED:` has 12+ characters (the waiver lands in the store line). A short waiver is refused.
- `--plan-tick` is refused against the dependency; allowed with a `present` investigation row, or with the dependency complete.
- `classify_items`: a tracked root gives waiting; an untracked root gives open plus the suffix; a cycle gives open.
- UNBLOCKED fires once when the root flips to finished, and not while it is unchanged.
- `guided_slice`: the FIRST row precedes X's rows and carries the exact chain string; at most 3 roots with the remainder counted; no FIRST row when there are no dependencies.
- `blocker_error` refuses a cycle through a plan edge and accepts an acyclic `BLOCKED_BY`.
- `auto_lease_candidates` skips an item blocked by a dependency.
- `wl_planenforce` names the root's box, and X's box when X has no dependencies.
- `test-backlog.py`: a claimed but unfinished dependency now makes X ineligible (this reverses the old control, citing the order); an unclaimed one redirects; a finished one does not block.

**Wiring checklist:**
- package.json :192;
- manifest.ts after :2044;
- ci-quality.yml after :614;
- gates.lock.json (`gen:gates-lock`);
- the gate block (`gate:bind`);
- generated docs regions: ci-gates.md, the plan-records.md header table, doc-registry.md (`gen:docs`);
- hook-inventory-baseline.json;
- test_canonical_sys_path_hop.py BASELINE;
- no new environment variables, so no env-registry rows;
- the stop-directory `test-*.py` files are picked up by `test_hooks_delegates.py`'s TAILED glob;
- CLAUDE.md :37 gets one sentence: "every live plan carries `Depends-On:` (plans, or `no-dep -- <reason>`), and the worklist refuses to lease or tick a box of a plan whose dependencies are unfinished";
- agent/README.md :16-32;
- docs/agent-reference/suppressions.md (`DEPS-WAIVED:`).

### Critical Files for Implementation
- /home/developer/console/.claude/hooks/stop/wl_leasehelp.py
- /home/developer/console/.claude/hooks/stop/wl_checks.py
- /home/developer/console/.claude/hooks/stop/worklist.py
- /home/developer/console/.claude/hooks/stop/wl_backlog.py
- /home/developer/console/.claude/rediacc_hooks/guards/block_plan_without_tasks.py

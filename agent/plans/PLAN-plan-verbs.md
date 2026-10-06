# PLAN: one-call plan verbs (`--plan-new`, `--plan-tick --investigate present`)

Status: draft -- parked: operator /ask 2026-10-06 left Part D out of PLAN-ci-consolidation's build; its design and boxes moved here unchanged so the work stays recorded. Not queued until the operator queues it.
Owner: d778be9d
First-Seen: 2026-10-06
Depends-On: no-dep -- split out of agent/plans/PLAN-ci-consolidation.md (Part D, candidate 6 of agent/reports/consolidation-investigation-2026-10-04.md)
Priority: P3 -- creating a plan takes 3 hand steps and a tick with an investigation takes 2 calls; nothing is red
Concurrency: parallel
Owns: .claude/hooks/stop/worklist.py, .claude/hooks/stop/wl_planrec.py, .claude/hooks/stop/worklist_messages.py, .claude/rediacc_hooks/tests/test_wl_plan_verbs.py, docs/agent-reference/plan-records.md

## Part D: plan verbs (candidate 6)

**`worklist.py --plan-new <me> <agent/plans/PLAN-<slug>.md> [--write]`.**
- **Refusals:**
  - the file is missing or is not under `agent/plans/`;
  - any of Status, Owner, First-Seen, Depends-On, Priority, Concurrency or Owns is missing;
  - the plan has no box;
  - the plan already has a ledger row (the refusal points to `--plan-tick`).
- **Steps, in order:**
  1. **Stage the file** with `git add -- <rel>`. This stages and never commits. It is needed because the ledger scan and INDEX read tracked plans only (`.ci/scripts/quality/check_plan_boxes.py:183-184`, #0b93d454).
  2. **Write the ledger row**, `merge_ledger(doc, rel, ledger_row(root, rel, text))` (`.claude/hooks/stop/wl_planrec.py:1975,2007`), into `.ci/config/plan-boxes.json`.
  3. **Refresh** with `R.refresh_index` (`.claude/hooks/stop/wl_planrec.py:1254`), which writes INDEX, its census and the QUEUE generated section through `_refresh_queue` (`:1280`).
- **Untouched:** Promoted, which no tool writes.
- **Output:** it prints the one commit line.

**`--plan-tick <me> <plan> <box> <evidence...> --investigate present <kind>:<tok> <kind>:<tok>... [--write]`.**
- **Order:** it builds the row with `R.plan_investigate` (`.claude/hooks/stop/wl_planrec.py:2244`), using the tick evidence as the note, which must clear INV_NOTE_MIN. It then passes the row as a new `inv_row=` parameter to `plan_tick` (`:2404`, which today looks it up at `:2453`). Nothing is written until both pass. The writes then go jsonl row, plan, ledger, index (`.claude/hooks/stop/worklist.py:794-796`).
- **Verdict:** only `present` is accepted, because only `present` licenses an immediate tick. Clause 1 already exempts it (`.claude/hooks/stop/wl_planrec.py:2340-2341`). `absent` and `partial` are refused with a pointer to `--plan-investigate`.
- **Other changes:** the usage texts at `.claude/hooks/stop/worklist_messages.py:2414,2455` are updated, and so is the dispatch at `.claude/hooks/stop/worklist.py:2518-2523`.

## Tasks
- [ ] T14 `--plan-new`. Proof: `test_wl_plan_verbs.py` in a tmp git repo checks that the ledger row equals `ledger_row`, that INDEX lists the plan, and that the QUEUE generated section lists it. Controls: skip the `git add` and INDEX omits the plan (the test fails); a missing Owns header is refused with nothing written.
- [ ] T15 `--plan-tick ... --investigate present ...`. Proof: one call in `test_wl_plan_verbs.py` writes the jsonl row and ticks the box. Controls: `--investigate partial` is refused; an unresolvable pointer is refused; in both cases plan, ledger and jsonl stay byte-identical.

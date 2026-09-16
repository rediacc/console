# PLAN: fix-in-session rule (rule 2 rewrite, --triage verb, judge tightening, plan-file convention)
Status: compacted
Owner: planning agent, branch 0731-2
Full-Text: f7a5351a9 agent/PLAN-fix-in-session-rule.md
Full-Text-Blob: de11703cc3f80d419da467c90f6da7494ade49e3
Record-Sig: ad22e290

## Why
The fix-in-session rule as written let a session REPORT a discovery instead of acting on
it, and let an issue reference close a finding. This plan rewrote CLAUDE.md rule 2, added
a `--triage` verb that answers INLINE, PLAN+SUBAGENT or OPERATOR-ONLY with the exact next
command, tightened the stop judge and the tick gate so an issue settles nothing without a
named door, and defined the `agent/PLAN-*.md` convention that makes a big finding's
design survive a compaction. The plan was itself the first instance of the convention it
defined.

## Outcome
SHIPPED. Header `done` is TRUE. Measured 2026-09-06, every named artifact is live.

- The verb: `worklist.py --triage` is in the usage banner and dispatches; `triage_item`
  is at `.claude/hooks/stop/wl_store.py:1413`.
- The judge path: `TRIAGE_SCHEMA` at `.claude/hooks/stop/wl_judge.py:177` and `run_triage`
  at `:346`.
- The checks and the plan-file helpers, all present in
  `.claude/hooks/stop/wl_checks.py` (blob bc44e67c925166eb059b2d58309757f503a9e729):
  `issue_only_evidence:681`, `plan_records:1154`, `plans_block:1377`,
  `plan_status_excerpt:1460`, `triage_context:1478`, and `guided_slice:2023` carrying the
  `root=None` parameter this plan added.
- The message constants are all in `worklist_messages.py`: `TRIAGE_PROMPT`,
  `CLI_TRIAGE_INLINE`, `CLI_TRIAGE_OPERATOR`, `CLI_TICK_ISSUE_DOOR`, `CTX_PLANS`.
- The doc half landed too: CLAUDE.md carries "Discovery is always in scope, and so is the
  fix" and the three doors with their `door:operator-only` tick evidence.
- The control cases survived a later refactor rather than being lost in it. The suite was
  split out of `test-worklist-v5.sh` into `.claude/hooks/stop/worklist-cases/`, and this
  plan's cases are now `16-triage-and-plans.sh` (blob
  bd06f9dcbc1a44fee3d39479cc5197996b503a23), whose header describes exactly this plan's
  subject: the `--triage` verb, its refusals and degradation, the judge path and the
  plan-file demand.
- Landing: console commit 28efbbf1c, "feat(hooks): the fix-in-session rule: --triage
  verb, tick door gate, durable plan files" (2026-08-01).

## Lessons
- The plan's own header already recorded a correction that a later reader would otherwise
  have to rediscover: the claim that the guide's "TRIAGED BIG" line reaches the stop judge
  through `remaining_lines` is WRONG, because `remaining_lines` is built from the
  classified item lists rather than from `guided_slice`. The intent holds; the mechanism
  named for it does not.
- Writing the correction into the plan at the moment it was found is the reason it is in
  this record at all. Nothing else in the tree carries it.
- A convention that is only described gets ignored; a convention whose first instance is
  the document defining it gets copied.

## Boxes
(this plan carried no checkbox tasks)

## Record
Record-Kind: compacted
Prior-Status: done
Compacted-By: 8f55d4f0
Compacted-At: 2026-09-06T17:32:37Z
Boxes: 0 attested, 0 open, 0 abandoned
Epics: none
Touched: CLAUDE.md
Gates: none
Why-Source: author
Read-History: `git show de11703cc3f80d419da467c90f6da7494ade49e3` recovers the text; `git log --find-object=de11703cc3f80d419da467c90f6da7494ade49e3 --all` names the commit

## History
- 2026-09-06T17:32:37Z compacted by 8f55d4f0 from `done` (record-sig ad22e290)

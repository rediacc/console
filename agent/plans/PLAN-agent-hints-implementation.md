# PLAN: agent hints in the stop hook, implementation
Status: compacted
First-Seen: 2026-09-17
Owner: 97604f47
Full-Text: f7a5351a9 agent/PLAN-agent-hints-implementation.md
Full-Text-Blob: 9e7c10012356718cff5eda813cae38e7287f31da
Record-Sig: 6a4a8866

## Why
The repo had accumulated specialist agents under `.claude/agents/` and sessions kept not using them; the operator had to point at them by hand twice in one day. The diagnosis was measured rather than argued: the word "bench" appeared zero times across the seven agent `description` fields and exactly once anywhere in the directory, in `account-dev.md`'s body. The knowledge existed
and the matching surface did not. This plan is the implementation half; it supersedes the design half of `agent/PLAN-agent-hints-in-stop-hook.md` and corrects that file's numbers by measurement.

## Outcome
SHIPPED, verified by RUNNING the gate on 2026-09-06.

- `.claude/hooks/stop/wl_agents.py` exists and carries the frozen API: `load_corpus`
at :350, `score` at :416, `best_hint` at :434.
- The tuning knobs shipped at the plan's own defaults: `MIN_SCORE` 2 (:51),
`MIN_MARGIN` 1 (:57).
- Delivery is through the existing advisory queue as designed:
`.claude/hooks/stop/wl_checks.py:2011` queues the section key `"agent-hint:%s"`, with the message constant at `.claude/hooks/stop/worklist_messages.py:1415`.
- The gate landed with the underscore filename this plan's section 1 insisted on:
`.ci/scripts/quality/check_agent_hint_liveness.py`, registered as `check:ci-agent-hint-liveness`.
- RUN HERE, exit 0: "all 13 agents are reachable by the hint matcher / every
specimen wins its own agent at MIN_SCORE=2 MIN_MARGIN=1, and all 5 neutral controls stayed silent / push-back fires for all 13 agents on a give-up claim, and stays silent on the same specimen without one / 4 planted defects were caught first, so this green means the check can fail".
- Section 6's description sharpening shipped too: `.claude/agents/backup-storage.md`
exists and `.claude/agents/account-dev.md:3` carries the bench sentence the plan dictated.

THE HEADER SAID `Status: READY TO IMPLEMENT` AND THE TREE DISAGREES. It is implemented. The console commit carrying it is 120cd9e73, "feat(backup): chunk-store cold path, rclone decommission, stop-hook cadence", an ancestor of origin/main. Note that a plain `git log --diff-filter=A` on the plan path names f7a5351a9 instead, because the plans were MOVED from `agent/0815-1/` into
`agent/` with no content change; `--follow` is required to reach the real commit.

DIVERGENCES. The corpus grew from the plan's 8 agents to 13 and the gate's specimen table grew with it. `load_corpus` takes `agents_dir_path` rather than the frozen `agents_dir`. One feature is in the tree and in no part of the plan: `pushback_for` at `.claude/hooks/stop/wl_agents.py:655`, with its own message block and its own gate assertions.

## Lessons
- A healthy corpus on a quiet stop looks exactly like a dead matcher, which is why
this shipped with a liveness gate rather than with tests over its internals.
- Widening the corpus made the matcher WORSE. Agent bodies were prototyped and added
a false positive; the bench gap that prompted the whole request was closed by sharpening three descriptions instead. More input is not more signal when the input is prose about the same subject.
- Tokenising the haystack once and intersecting sets was byte-identical to a regex
per term and 12 times faster (17.4 ms to 1.4 ms), and it removed the `read`-matches-`README` bug class by construction rather than by remembering a lookaround.
- The naming convention for a Python gate in `.ci/scripts/quality/` is underscores,
and getting it wrong would have made the gate invisible to its siblings. The design half of this work proposed hyphens.

## Boxes
(this plan carried no checkbox tasks)

## Record
Record-Kind: compacted
Prior-Status: ready
Compacted-By: 8f55d4f0
Compacted-At: 2026-09-06T17:06:09Z
Boxes: 0 attested, 0 open, 0 abandoned
Epics: none
Touched: package.json, scripts/ci-runner/manifest.ts, .github/workflows/ci-quality.yml, scripts/gates/check-ci-parity.ts, .claude/agents/account-dev.md, .ci/scripts/quality/check_gate_reachability_coverage.py, .ci/scripts/test/gates/test-worklist-hooks.sh, .ci/scripts/test/mutate-check.sh
Gates: check:ci-agent-hint-liveness, check:ci-parity
Why-Source: auto
Read-History: `git show 9e7c10012356718cff5eda813cae38e7287f31da` recovers the text; `git log --find-object=9e7c10012356718cff5eda813cae38e7287f31da --all` names the commit

## History
- 2026-09-06T17:06:09Z compacted by 8f55d4f0 from `ready` (record-sig 6a4a8866)

# PLAN: fix-in-session rule (rule 2 rewrite, --triage verb, judge tightening, plan-file convention)
Status: done
Owner: planning agent, branch 0731-2
Updated: 2026-07-31

This plan is itself the first instance of the convention it defines (section 0).
It is structured for a sub-agent to implement. Every file:line anchor below was
verified against the tree on 2026-07-31. House rule: no em dashes in any
authored text, including every new message constant.

## Status

Executing. The HOOK half is DONE and green; the DOC half is the orchestrator's.

LANDED (uncommitted, `.claude/hooks/stop/`): sections 0, 2, 3, 5, 6 and all
four of section 8.

- `worklist_messages.py`: 8 new constants (`TRIAGE_PROMPT`,
  `CLI_TRIAGE_{INLINE,PLAN,OPERATOR,SELF}`, `CLI_TICK_ISSUE_DOOR`,
  `CTX_PLANS`, `CTX_PLANS_EXCERPT`) plus the `_DOORS` fragment, and the five
  edits (`JUDGE_PROMPT`, `R_REGGATE_BLOCK`, `DEFER_AUDIT_PROMPT`,
  `CLI_ITEM_USAGE`, `USAGE`).
- `wl_store.py`: `triage_item` and the `triage` fold arm.
- `wl_judge.py`: `TRIAGE_SCHEMA` and `run_triage`.
- `wl_checks.py`: `issue_only_evidence`, the plan-file helpers
  (`plan_records`, `plans_block`, `plan_status_excerpt`), `triage_context`,
  the `guided_slice` root param and plan probe, the `handle_session_start`
  restructure, the `handle_post_compact` excerpt.
- `worklist.py`: `_triage_cli`, the verb dispatch, the tick door gate.
- `test-worklist-v5.sh`: cases 164 to 171 with their controls, plus the
  case-117 arity registrations. Suite 350 green before, 376 green after;
  `.claude/hooks/test-hooks.sh` 443 green.

Two things a later session should know. The plan's claim that the guide's
"TRIAGED BIG" line reaches the stop judge via `remaining_lines` is WRONG:
`remaining_lines` is built from the classified item lists, not from
`guided_slice`, so the judge sees the item as ordinary open work while the
plan-file annotation reaches only the session. The intent holds and no code
change was made for it. Separately, `test-worklist-v5.sh` was already failing
`shfmt -i 4 -ci` at two pre-existing spots in case 163e; that was fixed in
passing so the shell-format gate is clean.

DONE 2026-07-31. Sections 1 and 4 (CLAUDE.md rule-2 rewrite, the memory file,
MEMORY.md) were completed by the orchestrator; the hook half was independently
verified (suite re-run 378/378 after a bonus case 163f landed: the pure-wait
check-in now OS-verifies a worker before calling a silent stream POSSIBLY
STUCK, and `_needle` extracts quote-free segments so a quoted poll-loop
command is verifiable at all). Both planted-defect controls (tick door gate,
triage degrade) were reviewed from the implementer's evidence.

---

## 0. The plan-file convention (agent/)

### What it is

Planning agents write durable plans to `agent/PLAN-<slug>.md`,
committed with the branch, so plans survive session compaction and machine
loss. This is distinct from the gitignored `.agent/<branch>/` tree
(STATE.md/RULES.md, volatile per-branch notes; see
`wl_store.py:143-152` `agent_branch_dir`/`agent_state_path` and the refusal in
`worklist.py:359-363` when the dir is missing). STATE.md stays the volatile
cursor; PLAN files are the durable design record.

### Naming

- Path: `agent/PLAN-<slug>.md`. Slug is kebab-case
  `[a-z0-9-]{1,60}`. Multiple plans per branch coexist by slug.
- Required header, inside the first 10 lines of the file:

  ```
  # PLAN: <title>
  Status: draft
  Owner: <who>
  Updated: <YYYY-MM-DD>
  ```

- Status values: `draft` (designed, not started), `executing` (implementation
  underway; the implementer maintains a `## Status` section), `done` (executed;
  historical record), `superseded` (replaced; name the successor in the body).
  A missing or unparseable Status line reads as `UNKNOWN` and is surfaced
  loudly, never hidden.

### Staleness semantics

Plans are historical records once executed. Hooks surface only `draft`,
`executing`, and `UNKNOWN` plans; `done` and `superseded` appear only as a
count. The `## Status` section (required once Status is `executing`) is the
progress cursor a compact-recovered session needs.

### Hook changes

New helper in `wl_checks.py` (near `docs_drift`, wl_checks.py:518):

```python
PLAN_STATUS_RE = re.compile(r"^Status:\s*([A-Za-z-]+)\s*$", re.M)

def plan_records(root, branch):
    """[(relpath, status, lines)] for agent/PLAN-*.md.
    status is the parsed value lowercased, or 'UNKNOWN'. Empty list when
    the branch or directory is absent."""
```

Parse only the first 10 lines for Status. Sort newest mtime first.

`handle_session_start` (wl_checks.py:779): today it RETURNS EARLY when the
`DESIGN_DOCS` dir (`docs/ci-overhaul`, wl_checks.py:55) is absent
(wl_checks.py:782-783). Restructure: build the design-docs block (unchanged
when present, empty when absent) and a plans block, and emit if EITHER is
non-empty. Plans block: for the current branch (`C.git_branch(root)`,
wl_core.py:177; honors the `WORKLIST_AGENT_BRANCH` override the suite uses),
list non-done plans as
`  agent/PLAN-x.md [draft] (N lines)` plus one count line for
done/superseded ones. New message constant `CTX_PLANS` (see section 5) with the
instruction: read every non-done plan before acting; do not re-litigate
decisions recorded there; flip Status when you take one over.

`handle_post_compact` (wl_checks.py:812): append to the briefing (all three
existing branches of `msg`) a plans block: the listing above, plus the newest
non-done plan's `## Status` section body, capped at 1500 chars. Extract with a
simple split on `\n## ` and take the section titled `Status`. New constant
`CTX_PLANS_EXCERPT`.

Cost: SessionStart/PostCompact only. The Stop battery and the poll fast path
do not read plan files, except the one `os.path.exists` probe in section 2's
follow-through check.

---

## 1. CLAUDE.md Session Defaults rule 2 rewrite

All anchors in `/home/muhammed/monorepo/console/CLAUDE.md` (worktree copies
differ; use pwd).

### 1a. Replace the bullet at CLAUDE.md:38-42

Old (verbatim, for the Edit match):

```
- **Discovery is always in scope. Fixing has a test.** Fix it on the spot, and say you
  did, when ALL THREE hold: it is in code you are already editing, the fix is small and
  local (no new abstraction, no signature change rippling outward), and the run you are
  already doing proves it. Otherwise report it with a one-line repro and ask. Do not
  silently start a second project inside the first one.
```

New:

```
- **Discovery is always in scope, and so is the fix.** A finding is fixed in the
  session that finds it. Filing an issue never closes a finding. Small and local
  (no new abstraction, no signature change rippling outward): fix it inline
  immediately and say you did. Bigger than that: ask the machinery
  (`worklist.py --triage <me> <finding...>` answers INLINE, PLAN+SUBAGENT, or
  OPERATOR-ONLY with the exact next command), have a Plan agent write the design
  to `agent/PLAN-<slug>.md` (committed, survives compaction), then
  implement it THIS session: via a writer sub-agent when the fix's file set is
  disjoint from your current work or your context is heavy (disjoint ownership,
  max 2, rule 4), inline otherwise. The fix rides the current PR when
  risk-compatible, otherwise its own branch cut the same session.
- **Issues are a last resort with exactly three doors:** the fix needs
  operator-only powers (secrets, purchases, external accounts, production
  deploys); the operator explicitly deferred it when asked; or the target is
  outside this session's write access. "It is big" is not a door. Any last-resort
  issue must carry the evidence (exact command, exact output) and a ready-to-run
  brief a future session can execute without rediscovery, and its worklist item
  closes only with the door named in the tick evidence (`door:operator-only`,
  `door:operator-deferred`, or `door:no-write-access`).
```

### 1b. Reconcile the big-bang bullet at CLAUDE.md:50-55

Keep the existing text and append one sentence inside the same bullet, after
"...not after you have spent the session working around it.":

```
  The ask decides PACKAGING (one comprehensive change versus riding the current
  PR), never WHETHER the findings get fixed: park the ask as a [?] whose
  DEFAULT is "fix the cluster this session", and keep working anything that is
  safe under either packaging while it waits.
```

This removes the conflict: triage/fix-now governs each finding's fate; the
big-bang ask only clusters and sequences approved work.

### 1c. Verbs block at CLAUDE.md:73-81

Add one line after the `--tick` line:

```
  worklist.py --triage <me> [--id <id>] <finding...>  big/small verdict + next command
```

### 1d. Replace the closing bullet at CLAUDE.md:112-113

Old:

```
- **End with what you did NOT fix**, as a short "found, not fixed" list, and offer it as
  the next big-bang so nothing discovered gets lost.
```

New:

```
- **End with what remains**, which under this rule is short: operator-deferred
  `[?]` items and last-resort issues with their doors named. A "found, not
  fixed" entry that fits neither category means the fix-in-session rule was
  not followed; go back and fix it.
```

---

## 2. The triage verb: `worklist.py --triage`

### Interface

```
worklist.py --triage <me> [--id <item-id>] <finding text...>
```

- `<me>` validated by `C.PREFIX_RE` (wl_core.py:53), same as every verb
  (worklist.py:212-213).
- Empty finding text: exit 1, no event written (mirror of `--add`'s refusal,
  worklist.py:215-217).
- With `--id`: the item must exist and be owned by the caller (same checks as
  worklist.py:222-228). Without: `S.add_item(worklist, me, text)` first
  (wl_store.py:583), so every triaged finding is tracked. Print the id either
  way.
- Never on the Stop path: this is a CLI verb only; poll fast path
  (wl_checks.py:584) is untouched; no model call is ever added to `run_stop`.

Dispatch: add `"--triage"` to the verb tuple at worklist.py:471 and handle it
inside `_item_cli` BEFORE the `item_id = argv[2]` parse (worklist.py:221),
because like `--add` it takes free text.

### What the CLI can honestly know (decision inputs)

Gathered locally, cheap, and passed to the judge as context; also printed in
degraded mode so the session self-assesses on the same facts:

- the finding text (caller supplied);
- current branch (`C.git_branch`), and whether `agent/` exists;
- `git status --porcelain` first 40 lines: the files the session currently has
  in flight, which is what makes "disjoint file set" answerable;
- open item count from the fold (context-weight signal);
- the three-part test, stated as the criteria the model must apply;
- the three last-resort doors, verbatim.

Structured self-assessment flags (`--files <n>` etc.) were considered and
rejected: they restate the caller's own judgement, which is exactly what the
operator wants the machinery to second-guess. The judge model is the primary
mechanism; the degraded mode hands back the questions instead.

### Judge invocation

New in `wl_judge.py`, modeled byte-for-byte on `run_judge`
(wl_judge.py:153-210): `resolve_claude()`, `STOPHOOK_CHILD=1` in env (the
recursion guard, wl_judge.py:174-175), `--output-format json`,
`--json-schema`, `JUDGE_MODEL`, `JUDGE_BUDGET_USD`, `JUDGE_TIMEOUT_S`,
`cwd=<TMPDIR>/claude-worklist/.judge`, `stdin=DEVNULL`. Haiku cost basis is
recorded at wl_judge.py:20-22 ($0.011-0.026 warm); acceptable per the
operator.

```python
TRIAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["inline", "plan-subagent", "operator-only"]},
        "reason": {"type": "string", "maxLength": 300},
        "plan_slug": {"type": "string", "maxLength": 60},
    },
    "required": ["verdict", "reason", "plan_slug"],
    "additionalProperties": False,
}

def run_triage(finding, context):
    """(verdict_dict, error_string). Exactly one is non-None."""
```

`TRIAGE_PROMPT` lives in `worklist_messages.py` (section 5). `plan_slug` is
meaningful only for `plan-subagent` (empty string otherwise); the CLI
sanitizes it to `[a-z0-9-]` and falls back to the item id.

### Failure semantics (deliberate asymmetry with the stop judge)

The stop judge fails CLOSED because it gates an exit. Triage is a decision aid
on a CLI path: a judge error DEGRADES to the self-assessment printout with one
loud line naming the error, exit 0. `WORKLIST_JUDGE=off` (wl_judge.py:24)
degrades the same way, silently. Degraded mode records NO triage event: the
machinery must not claim a verdict it did not produce. The `add` event still
lands, so the finding is tracked regardless.

### Output (deterministic, CLI-rendered; the model supplies only verdict, reason, slug)

- `inline` -> `CLI_TRIAGE_INLINE`: verdict line with the reason, then the
  order: fix it now in this context, and when the run proves it,
  `worklist.py --tick <me> <id> '<evidence>'`.
- `plan-subagent` -> `CLI_TRIAGE_PLAN`: verdict line, the prefilled plan path
  `agent/PLAN-<slug>.md`, then the recipe:
  1. Agent tool, `subagent_type: Plan`, prompt: design the fix for the finding
     and write the plan to that exact path with a `Status: draft` header per
     the convention (section 0), file:line anchors verified, tests with
     controls.
  2. Flip the header to `Status: executing`, then implement THIS session: a
     writer sub-agent when the plan's file set is disjoint from the files in
     `git status` or the context is heavy (state its exact file ownership,
     max 2 writers, forbid `git checkout/restore/stash` and any
     sync/regenerate script), inline otherwise.
  3. Ride the current PR when risk-compatible, else cut the fix's own branch
     the same session. Tick with evidence.
- `operator-only` -> `CLI_TRIAGE_OPERATOR`: verdict line, the three doors
  verbatim, then: for a genuinely operator-owned decision,
  `--defer <me> <id> '<question> DEFAULT: <action> WHY: <door + specifics>
  HOW: <what settles it>'`; for a last-resort issue (operator-only powers or
  no write access), file it WITH evidence plus a ready-to-run brief and tick
  with the issue URL AND the door token (section 3a).
- degraded -> `CLI_TRIAGE_SELF`: the three-part test as questions, the three
  doors, and all three recipes, so the session picks one itself on the same
  facts.

### Recording (decision: yes, triage records)

On a successful judge verdict, append a new event kind:

```json
{"ev":"triage","id":"<rid>","at":"<stamp>","by":"<me>","v":"plan-subagent",
 "reason":"...","plan":"agent/PLAN-<slug>.md"}
```

`plan` present only for `plan-subagent`. Store changes in `wl_store.py`:

- New helper `triage_item(worklist, by, item_id, verdict, reason, plan="")`
  beside `update_item` (wl_store.py:601), appending under the same lock.
- Fold arm: in the event loop (wl_store.py:433, the
  `elif kind in ("state", "update", "lease", "tomb")` chain), add
  `elif kind == "triage":` guarded by the same unknown-id skip, setting
  `rec["triage"] = {"v": ev.get("v",""), "plan": ev.get("plan","")}`.
  Older hook builds ignore unknown kinds in this loop, so the event is
  forward-compatible by construction (verified: the chain at
  wl_store.py:382-467 falls through silently on unmatched kinds).

### Follow-through (the "did the big finding get its plan?" check)

`guided_slice` (wl_checks.py:716) gains an optional `root=None` keyword
(callers: worklist.py:197 passes the derived root; `run_stop` passes the root
it already has; `None` derives via `C.project_root`). For an item in state
` ` or `>` with `rec["triage"]["v"] == "plan-subagent"` and a recorded plan
path that does NOT exist on disk, the guide line becomes priority 0:

```
  - [ ] #<id> (upd <age>) TRIAGED BIG, plan file missing: <path>
        NEXT: write the plan (Plan agent) or re-triage: --triage <me> --id <id> <finding>
```

When the file exists, the normal line gains a suffix `plan: <path>`. This is
one `os.path.exists` per triaged item, bounded by the fold size; report-only
(a guide line, never a new block), so the stop path stays cheap and the
no-new-block invariant of the guide holds. The stop judge sees these lines via
`remaining_lines` (wl_checks.py:1974-1975), which is how a "big" finding that
never got its plan surfaces to the judge without new machinery.

---

## 3. Reggate/judge tightening: issues settle nothing without a door

The machinery (three exits, verdict enum at wl_reggate.py:37, the settle flow
at wl_checks.py:2001-2032) stays. The criteria sharpen in four places.

### 3a. The real hole: `--tick` accepts a bare issue URL today

`completion_evidence` (wl_checks.py:411-429) passes on ANY URL
(`URL_RE`, line 422), so `--tick <me> <id> 'filed as
https://github.com/rediacc/console/issues/560'` closes a finding right now.
That is the loophole the new rule outlaws. Fix at the tick site
(worklist.py:231-236), after the existing evidence check:

```python
if CK.issue_only_evidence(root, rest):
    die(M.CLI_TICK_ISSUE_DOOR % item_id)
```

New in `wl_checks.py`:

```python
ISSUE_REF_RE = re.compile(r"github\.com/\S+/issues/\d+|\bissues?\s+#\d+", re.I)
DOOR_RE = re.compile(r"door:(operator-only|operator-deferred|no-write-access)")

def issue_only_evidence(root, text):
    """True iff the evidence is ONLY an issue reference: an issue ref is
    present, no door is named, and the text with issue refs stripped carries
    no other evidence shape (completion_evidence on the remainder)."""
```

Shape-only by design, same division of labor as the WHY/HOW gate
(worklist.py:242-250): whether the named door is TRUE is the judge's question,
because every new tick already flows into the reggate/judge path
(wl_reggate.py:104-110, fix_signals at 136).

`CLI_TICK_ISSUE_DOOR` (new constant, section 5) names the three doors and the
rule: an issue closes a finding only through one of them, with evidence and a
ready-to-run brief in the issue.

### 3b. JUDGE_PROMPT (worklist_messages.py:823-824)

Old (verbatim):

```
Be strict about one specific failure: reporting a problem instead of fixing it.
This project's rules say defects found on the way get FIXED, not filed.
```

New:

```
Be strict about one specific failure: reporting a problem instead of fixing it.
This project's rules give a finding exactly two legitimate terminal states:
FIXED THIS SESSION (with evidence, and a regression gate when one is due), or
OPERATOR-DEFERRED (a [?] item the operator is genuinely needed for). "Filed an
issue" settles nothing by itself. It is legitimate only when the message names
one of the three last-resort doors: the fix needs operator-only powers, the
operator explicitly deferred it when asked, or the target is outside the
session's write access, and the issue carries evidence plus a ready-to-run
brief. An issue with no named door is a report wearing a resolution's clothes:
answer "continue" and direct the session to fix the finding.
```

No placeholders touched, so the case-117 arity pin is unaffected.

### 3c. R_REGGATE_BLOCK (worklist_messages.py:656-676)

Two edits, keeping all six `%s` placeholders:

- Exit 2 line: change `  2. DEFER to the operator: append to the worklist` to
  `  2. DEFER to the operator, the ONLY exit that ends a finding without a fix,
  and only for a decision that is genuinely theirs: append to the worklist`.
- After the exit 3 (REBUT) text, append:
  `\nFiling an issue is NOT a fourth exit: an issue gates nothing and settles `
  `nothing unless it names a last-resort door (operator-only powers, an `
  `explicit operator deferral, or a target outside this session's write access).`

### 3d. DEFER_AUDIT_PROMPT (worklist_messages.py:462)

Add one bullet under "Interrogate each record:" after the WHY bullet:

```
  - Does the WHY amount to "an issue exists for this"? An issue is not an
    inability. Findings are fixed in the session that finds them unless the
    WHY names operator-only powers, an explicit operator deferral, or a
    target outside the session's write access.
```

No placeholders added; `%(n)d`, `%(window)d`, `%(items)s` unchanged.

---

## 4. Memory update

Rewrite
`/home/muhammed/.claude/projects/-home-muhammed-monorepo-console/memory/feedback_fix_findings_proactively.md`
keeping its frontmatter shape (name, description, metadata.type: feedback) and
its Why / How to apply structure. New description:
"Findings are ALWAYS fixed in the finding session; issues are a last resort
with three doors; big fixes get a plan file then land the same session."

Body keeps the original operator quote and the derive-fallback-timeline story
in **Why:**, then replaces How to apply with: the always-fix rule; small=inline
now; big = `worklist.py --triage`, Plan agent to `agent/PLAN-*`,
implement same session (sub-agent when disjoint/heavy, max 2); rides the
current PR when risk-compatible, else own branch same session; issues only
through the three doors, always with evidence plus a ready-to-run brief, and
ticks carrying `door:` tokens; only genuine DECISIONS defer, as `[?]` with
DEFAULT (keep the existing links to [[feedback_prove_the_instrument]] and
[[feedback_no_unilateral_descope]]). Update MEMORY.md's one-line hook for the
entry to match.

---

## 5. New and changed message constants (worklist_messages.py)

New: `TRIAGE_PROMPT` (the judge prompt: three-part test, three doors, finding,
context; ends with the same "Never use em dashes" instruction the judge prompt
carries at line 872), `CLI_TRIAGE_INLINE`, `CLI_TRIAGE_PLAN`,
`CLI_TRIAGE_OPERATOR`, `CLI_TRIAGE_SELF`, `CLI_TICK_ISSUE_DOOR`, `CTX_PLANS`,
`CTX_PLANS_EXCERPT`.

Changed: `JUDGE_PROMPT` (3b), `R_REGGATE_BLOCK` (3c), `DEFER_AUDIT_PROMPT`
(3d), `CLI_ITEM_USAGE` (worklist_messages.py:706, add the --triage line and
the door rule to the --tick line), `USAGE` (worklist_messages.py:879, same two
additions).

Suite case 117 (test-worklist-v5.sh:2276) renders every constant at its
call-site arity and FAILS on unmapped new constants
("UNMAPPED new constant(s), add arity here", line 2365). Every new constant
must be added to its map with the exact arity used at its call site. This is
the existing control that a placeholder typo cannot land.

---

## 6. Test cases (test-worklist-v5.sh; every check fires on a planted defect and stays silent when clean)

Numbering continues from 163e (test-worklist-v5.sh:5045). The suite already
provides: `reqcli` (line 104) to drive the CLI, JSONL no-event assertions
(case 147, line 3385), planted events (case 148, line 3428), a shim `claude`
with call counter (`shim_judge_out`, line 3373), and
`WORKLIST_AGENT_BRANCH=agenttest` with `$BASE/proj/.agent/agenttest`
pre-created in `setup`. Plan fixtures live under
`$BASE/proj/agent/`.

- **164. --triage misuse**: no text -> exit 1 and NO event appended (the
  case-147 pattern is the model). Control: nothing else changes.
- **165. --triage degraded (judge off)**: with `WORKLIST_JUDGE=off`, prints
  the self-assessment (needles: `INLINE`, `PLAN+SUBAGENT`, `OPERATOR-ONLY`,
  `agent/`), exit 0; an `add` event landed (finding tracked); NO
  `"ev":"triage"` event (degraded mode must not claim a verdict). The absent
  triage event is the control proving recording is judge-path-only.
- **166. --triage ownership**: `--id` on another session's item is refused
  (same needle style as the ownership die at worklist.py:226-228).
- **167. --triage judge path via shim**: `shim_judge_out` returns
  `{"verdict":"plan-subagent","reason":"multi-file","plan_slug":"fix-x"}`;
  assert the printed recipe contains
  `agent/PLAN-fix-x.md`, a `"ev":"triage"` event landed with
  `"v":"plan-subagent"` and the plan path, and the shim was called exactly
  once (the call counter). Control: an `inline` shim verdict prints the
  --tick order and records `"v":"inline"` with empty plan.
- **168. plan follow-through in the guide**: plant an open item plus a triage
  event (`"v":"plan-subagent"`, plan path under `agent/`),
  file absent -> `--list --open deadbeef` shows `TRIAGED BIG, plan file
  missing`. Then create the file -> the demand disappears and the line gains
  `plan:` (silent control).
- **169. tick door gate**: tick with evidence that is only
  `filed as https://github.com/x/y/issues/560` -> refused (rc!=0), names all
  three doors, NO state event. Same tick plus `door:no-write-access` ->
  accepted. Regression controls: a plain `exit 0` tick and a verified-sha
  tick still pass (the URL_RE path for non-issue URLs must keep working:
  a tick citing a run URL with no issue ref is also asserted green).
- **170. SessionStart plans listing**: plant `PLAN-a.md` (`Status: draft`)
  and `PLAN-b.md` (`Status: done`); run `--session-start`; assert PLAN-a
  listed with `[draft]`, PLAN-b absent from the listing, done count present.
  Also assert the plans block emits when `docs/ci-overhaul` is ABSENT (the
  current early return at wl_checks.py:782-783 would eat it; this needle is
  the control on the restructure). Existing SessionStart behavior with
  design docs present is covered by keeping the current cases green.
- **171. PostCompact plan excerpt**: fresh STATE.md (`hand_now`), plant an
  `executing` plan whose `## Status` section carries a marker sentence;
  assert the marker appears in the PostCompact additionalContext, and a
  `done` plan's marker does not.
- **117 (existing)**: add every new constant's arity to its map; the case
  itself is the control.
- **Status UNKNOWN**: fold into 170: a `PLAN-c.md` with no Status line lists
  as `[UNKNOWN]` (surfaced, not hidden).

Suite invariant: `bash .claude/hooks/stop/test-worklist-v5.sh` fully green
(FAIL=0) before and after; CI runs it in Quality/Static (per
wl_reggate.py:224-231 the suite is itself the canonical gate artifact for
hook changes, accepted on change).

---

## 7. Implementation order and file ownership

Hook edits are committable now (they ride this branch or PR #550's
follow-up). One writer owns all hook files (they are tightly coupled; two
writers in this directory would collide on worklist_messages.py):

1. `worklist_messages.py`: new constants + the four edits (sections 3b-3d, 5).
2. `wl_store.py`: `triage_item`, the `triage` fold arm.
3. `wl_judge.py`: `TRIAGE_SCHEMA`, `run_triage`.
4. `wl_checks.py`: `issue_only_evidence`, `plan_records`, `guided_slice`
   root param + plan probe, `handle_session_start` restructure,
   `handle_post_compact` excerpt.
5. `worklist.py`: `--triage` dispatch in `_item_cli` and the verb tuple at
   line 471; the tick door gate at line 231-236; `--help` text via USAGE.
6. `test-worklist-v5.sh`: cases 164-171 plus the case-117 arity map entries.
7. Run the suite; fix to green.

Doc edits (any writer, or inline; no coupling to the hook files):

8. `CLAUDE.md` (section 1, four edits).
9. The memory file + MEMORY.md hook line (section 4).
10. Flip this plan's header to `Status: done` with a one-line result in
    `## Status`.

Constraints restated for the implementer: no em dashes in any authored text;
never `git checkout/restore/stash` (shared tree); the store is append-only
under its lock (wl_store.append_events), never rewritten; triage must never
run on the Stop path; the GHA no-op at worklist.py:485 sits AFTER the verb
dispatch, so CLI verbs keep working in CI and the suite's `GHA=''` pin stays
required.

---

## 8. Enhancements beyond the operator's list (marked)

- The `--tick` door gate (3a). The operator asked for reggate/judge prompt
  tightening; the prompt alone cannot stop a bare-issue-URL tick because
  `completion_evidence` accepts any URL by shape. The gate closes the actual
  hole; the prompts close the narrative one. Without it the sharpened wording
  is advisory.
- Degraded-mode-records-nothing (section 2): the machinery never claims a
  verdict it did not produce.
- The `[UNKNOWN]` status surfacing (section 0): a plan without a Status line
  is shown loudly rather than silently skipped, per the blind-check
  convention (V_PR_UNREADABLE pattern, worklist.py:56-57).
- `guided_slice` plan annotation for EXISTING plan files (`plan: <path>`),
  so the guide advertises where the design lives, not only when it is
  missing.

## 9. Claims not verified

- The suite is described as "350 cases" in the task; the file has 194
  `echo "== N."` case markers (many contain multiple pass/fail assertions).
  Nothing in this plan depends on the count.
- Judge cost figures are taken from the comment at wl_judge.py:20-22, not
  re-measured.
- PR #550 was not inspected; "hook edits ride the branch" is taken from the
  task statement.
- The claude CLI's `--json-schema` acceptance of TRIAGE_SCHEMA was not live-
  tested; it mirrors JUDGE_SCHEMA's proven shape (flat object, string enum),
  which the existing judge exercises on every gated stop.

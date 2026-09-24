# PLAN: a blocking plan-implementation gate, in the Stop hook and in CI, with enforced investigation before a box may be ticked

Status: done -- verified 2026-09-24: all 17 boxes ticked; .claude/hooks/stop/wl_planenforce.py, .ci/scripts/quality/check_plan_implementation.py and .ci/config/plan-implementation.json landed (b33cd58b7); .sh names below are history
Owner: d778be9d
First-Seen: 2026-09-22
Updated: 2026-09-22
Scope: design. Every measurement below was taken read-only against this checkout, branch `0914-1`, on 2026-09-22 at approximately 21:10 local. No file was written and no hook state was mutated. Numbers that differ from an earlier session summary are corrected here against the live tree and the discrepancy is explained rather than smoothed over.

The operator's rulings, verbatim, in the order they were given:

> "we plan but don't implement... I aim to eliminate 'planned but not implemented'."

> (offered three narrower scopes -- per-PR-diff, per-branch, per-plan-adoption -- after seeing the 27-plan/299-box/5-owner census and the 654-commit branch age) **"I go for ALL."**

> "I want to see all implemented" -- not "eventually".

> "we must investigate if they're implemented before implement... you must develop code for stop hook to enforce investigation before implementing a plan."

The last ruling is read together with `CLAUDE.md:107-121` (rule 3, "Verification comes before the claim"), in particular `CLAUDE.md:115-116` -- "Do not trust a report that has not been spot-checked, including a subagent's and this session's own from earlier.
Check the artifact, not the summary of it." -- and `CLAUDE.md:161-163` ("Search first ... Several campaign boxes closed by finding the work already landed and only the record was stale, not by doing it again"). The ask is that those two sentences stop being norms a session can forget and become a mechanism a session cannot skip.

---

## Part 0 -- What exists today, and the boundary each existing mechanism draws

Seven mechanisms in this tree sit close enough to this one that the eighth becomes a duplicate of one of them unless the boundary is written first. Each was read in full.

### 0.1 `wl_planfile.plan_rows` (`.claude/hooks/stop/wl_planfile.py:334`) asks whether boxes are TRACKED, not whether they are DONE

Its own design note 1 (`.claude/hooks/stop/wl_planfile.py:14-22`) forbids it from blocking, in these words: "A check that converted 18 plan tasks into 18 session-owned open items -- or that blocked until they existed -- would wedge EVERY turn of EVERY session until a multi-week migration finished." That reasoning is about TRACKING.
It is not an argument against the present plan, which asks a different question and carries its own rollout clock (Part 5) precisely so the wedge does not happen. **This module is not repurposed and not modified.**

### 0.2 `wl_backlog.next_plan` (`.claude/hooks/stop/wl_backlog.py:172`) is the ADVISORY half of exactly this ask, and stays advisory

Its docstring at `.claude/hooks/stop/wl_backlog.py:3` quotes the same operator sentence this plan answers. Its NEVER-GOALS block (`.claude/hooks/stop/wl_backlog.py:12-17`) says "NEVER blocks. No `vadd`, no verdict flip -- pinned by a control at the call site". The new gate is a SEPARATE module with a separate key.
`wl_backlog.py` is not edited, not promoted, and its control at `.claude/hooks/stop/test-planfile.py` must keep passing unchanged -- that is an acceptance criterion below, not a hope.

What IS reused from it, by import rather than by re-derivation: `_dead_peer` (`.claude/hooks/stop/wl_backlog.py:147-169`), which already resolves peer ownership through `wl_store.session_liveness` and already prints the `--migrate --plan` recipe. Part 6 depends on it.

### 0.3 The `plan-adopted` vadd (`.claude/hooks/stop/wl_checks.py:3128`) is the ONLY existing blocking plan-box check, and its scope is one marker

It fires only when `wl_planfile.is_adopted` (`.claude/hooks/stop/wl_planfile.py:321`) finds `(adopted from` in the Owner line -- the string `worklist.py --migrate --plan` writes via `ADOPTED_OWNER_FMT` (`.claude/hooks/stop/wl_planfile.py:316`, written at `.claude/hooks/stop/worklist.py:1016`). It sits at `T_MISSION` (`.claude/hooks/stop/wl_checks.py:1999`). Its message is `V_PLAN_ADOPTED` (`.claude/hooks/stop/worklist_messages.py:1070-1081`).

**This is the precedent, and the new gate is its scope widened from "adopted" to "ALL", per the operator's ruling.** The call-site comment at `.claude/hooks/stop/wl_checks.py:3119-3121` states the existing boundary in as many words: "a plan a session merely OWNS can carry eighteen boxes and would wedge every turn. A plan the session ADOPTED is different in kind".
The operator has now overruled that boundary. What the comment was RIGHT about is the wedge, and Part 5 is the answer to it.

### 0.4 `check:ci-plan-boxes` (`.ci/scripts/quality/check_plan_boxes.py`) already owns the CI-side corpus, the ledger, and five of the six ways a box can disappear

G-A0..G-A6 are in its docstring. The committed ledger is `.ci/config/plan-boxes.json` (`.ci/scripts/quality/check_plan_boxes.py:109`, mirrored at `.claude/hooks/stop/wl_planrec.py:137` as `LEDGER_REL`). Task signatures are the first 8 hex of `sha256(wl_planfid._norm(task)[:120])` (`.claude/hooks/stop/wl_planrec.py:648-654`).

**The new CI gate does not re-scan plans and does not fork the parser.** It reads `plan-boxes.json`, which `check:ci-plan-boxes` G-A0 already proves equals the tree. That is the whole reason the new gate can be small.

**Live finding, recorded here because rule 2 requires it:** `check:ci-plan-boxes` exits **1** on this tree right now.
```
$ .ci/scripts/quality/check_plan_boxes.py >/dev/null 2>&1; echo $?
1
```
Three disagreements, all pre-existing:
- `agent/plans/PLAN-stop-hook-behavioral-hints.md` says `Status: done` but has 1 open box (G-A3).
- `agent/plans/PLAN-haiku-model-routing.md` is new on this branch, 15 open boxes, no resolvable `Owner:` (G-A4).
- `agent/plans/PLAN-secret-namespace-migration.md` is new on this branch, 9 open boxes, no resolvable `Owner:` (G-A4).

All three are inside this plan's own subject matter and are drained as Task 0 below, before anything new lands.
The first is a perfect specimen of the failure being fixed: the box at `agent/plans/PLAN-stop-hook-behavioral-hints.md:264` carries, **inside the box text**, the sentence "NOT extracted: implemented independently ... matching the plan's own stated fallback for exactly this case".
The work is done, the finding was written into the box instead of into a tick, and the box is still `- [ ]`.

### 0.5 `worklist.py --plan-tick` (`.claude/hooks/stop/worklist.py:576-637`, `wl_planrec.plan_tick` at `.claude/hooks/stop/wl_planrec.py:1879`) is the tick primitive, and its evidence floor is 12 CHARACTERS

`.claude/hooks/stop/wl_planrec.py:1889-1895`: the only evidence test is `len(ev) < TICK_EVIDENCE_MIN`, and `TICK_EVIDENCE_MIN` is `12` (`.claude/hooks/stop/wl_planrec.py:1764`). **`plan_tick` never calls `wl_checks.completion_evidence`** -- grep for it in `wl_planrec.py` returns only docstring mentions at lines 416 and 454. So `--plan-tick <me> <plan> <sig> "done it, works"` is accepted today.

**This is the single widest hole in the tree and it is in the verb this plan must depend on.** The worklist's own `--tick` is stricter: `.claude/hooks/stop/worklist.py:703-705` calls `CK.completion_evidence(root, rest)` and dies with `M.CLI_TICK_NO_EVIDENCE` (`.claude/hooks/stop/worklist_messages.py:1583-1586`, "a real sha, a run id, a file:line that resolves, an exit code, or a URL").
The two verbs have drifted, and closing that drift is Task 2.

### 0.6 `wl_checks.completion_evidence` (`.claude/hooks/stop/wl_checks.py:455-486`) is half shape-check and half re-derivation, and the shape half is the lie surface

Read the function's first branch, `.claude/hooks/stop/wl_checks.py:462`:
```python
if RUN_ID_RE.search(text) or EXIT_RE.search(text) or URL_RE.search(text):
    return True
```
`RUN_ID_RE` is `\b\d{9,}\b` (`.claude/hooks/stop/wl_checks.py:449`), `EXIT_RE` is `\bexit(?:\s+code)?\s*[:=]?\s*\d+\b` (`:450`), `URL_RE` is `https?://\S+` (`:451`). **None of the three is ever resolved against anything.** `"exit 0"` passes. `"123456789"` passes. `"https://x/y"` passes.

The other two branches DO re-derive: a `file:line` goes through `citation_state` (`.claude/hooks/stop/wl_checks.py:390`), which opens the file and range-checks the line; a hex token goes through `git rev-parse --verify --quiet <tok>^{object}` (`.claude/hooks/stop/wl_checks.py:485`).
`citation_state`'s own docstring (`.claude/hooks/stop/wl_checks.py:398-406`) names the property this plan generalises: "Requiring a `<path>:<line>` is not bureaucracy, it is a FORCING FUNCTION: producing the citation means opening the file, and opening that file is the exact moment the claim collapses."

**So the repo already contains both halves of the answer, in one function, unlabelled.** The design below promotes the re-derived half and demotes the shape-only half.

### 0.7 `wl_claimcheck` (`.claude/hooks/stop/wl_claimcheck.py`) already asked "does the evidence demonstrate the claim", measured two mechanical tests, and found both unusable as blockers

This is the most important prior art and it must not be re-litigated. Its docstring at `.claude/hooks/stop/wl_claimcheck.py:7-14` reports two measurements over the live corpus of 342 real closing-tick notes:

- **Lexical overlap** between a claim and its own cited window: median 3 shared non-stopword tokens, **12.4% score zero**; the same notes re-paired with a stranger's citation score median 2, 26.0% zero. "At 'score below 1 is suspect' that falsely accuses one in eight genuine claims to catch one in four planted mismatches."
- **"the cited sha touches a file the claim names"** disagrees with **21 of the 59** ticks carrying both (36%), and inspection showed most of those 21 legitimate. "A blocker at 36% false positives is a nagging machine by arithmetic."

`.claude/hooks/stop/wl_claimcheck.py:16-32` then states four reasons the module is ADVISORY and "may not quietly become otherwise", including reason 3: "A false accusation here is uniquely corrosive, because the subject is the session's honesty.
Wrongly telling a truthful session that it fabricated evidence teaches it to write evidence that satisfies the checker rather than the reader." Its graduation criterion (`.claude/hooks/stop/wl_claimcheck.py:26-27`) requires 30 real verdicts in `agent/ledgers/census-claim-check.jsonl` before even the `resolved-untouched` arm may block.

**Consequence for this design, and it is binding: no semantic judgement of evidence may block. Only a re-derivation may block.** Part 3 is built on that line.

### 0.8 `wl_reggate.prove_new_gate` (`.claude/hooks/stop/wl_reggate.py:544-620`) is the ONE place in this repo that already refuses to trust a pasted exit code

It takes a claimed gate, finds the `check:*` key whose command names the script, checks reachability from `npm run ci`, then **actually runs it**: `wl_proc.run(["npm", "run", "--silent", key], cwd=root, timeout=REGGATE_TIMEOUT_S)` at `.claude/hooks/stop/wl_reggate.py:602-606`, and stores the real exit code in a marker keyed by the script's content hash (`.claude/hooks/stop/wl_reggate.py:607`).
`REGGATE_TIMEOUT_S` is 120s (`.claude/hooks/stop/wl_reggate.py:27`). The hash cache is what keeps it affordable: an unchanged gate is never re-run.

**This is the existence proof that "the hook re-derives the number rather than reading it" is affordable on the Stop path in this repo.** Part 3's Mechanism A is its generalisation.

### 0.9 `wl_planrec.resolve` (`.claude/hooks/stop/wl_planrec.py:326`) is the shared, eight-kind pointer resolver

`RESOLVE_KINDS = ("blob", "tree", "commit", "ancestor", "fileline", "gate", "plan", "trap")` at `.claude/hooks/stop/wl_planrec.py:303`.
Each kind's oracle, from its docstring at `.claude/hooks/stop/wl_planrec.py:329-352`: `blob`/`tree` via `git cat-file -t`; `commit` via `git rev-parse ^{commit}`; **`ancestor` via `git merge-base --is-ancestor <t> origin/main`, so "a pointer into a branch that was never merged cannot masquerade as a landed one"**; `fileline` delegates to `wl_checks.citation_state`; `gate` is a key in `package.json`'s `scripts`; `plan` is a file across four folders; `trap` is a `Trap-Id:` in `TRAPS.md`.

The comment above it (`.claude/hooks/stop/wl_planrec.py:299-301`) states the reuse rule this plan obeys: "a record's pointers must all be checkable by ONE call the gate and the CLI share ... a fresh path regex here would re-open every one of [citation_state's five extension rounds]."

**`resolve` is the vocabulary the investigation record speaks.** Nothing new is parsed.

---

## Part 1 -- What "ALL" means, measured against the live tree

### 1.1 The definition, and it is confirmed rather than assumed

**A plan is IN SCOPE when `wl_store.agent_plan_files` finds it, its `Status:` (parsed by `wl_checks.PLAN_STATUS_RE`, `.claude/hooks/stop/wl_checks.py:763`) is not in `wl_planfile.FINISHED_STATES` (`.claude/hooks/stop/wl_planfile.py:119-143`), and `wl_planfile.plan_boxes` resolves at least one open `- [ ]` box.**

That is the census this session used and it holds. Driven live through the real modules:

| | plans | open boxes |
|---|---|---|
| every tracked plan file (`wl_checks.plan_records`) | 119 | -- |
| `.ci/config/plan-boxes.json` totals | 119 | **299 open, 491 done** |
| **in scope by the definition above** | **26** | **298** |

### 1.2 The 27th plan, and why the two numbers differ

The ledger says 27 plans carry open boxes; the definition says 26. The difference is exactly one file: `agent/plans/PLAN-stop-hook-behavioral-hints.md`, `Status: done`, `Owner: d778be9d`, 1 open box at line 264. It leaves this gate's scope by `FINISHED_STATES` and is already owned by `check_plan_boxes.py`'s G-A3, which is reding on it today (0.4).

**Both numbers are right about different questions and neither is corrected into the other.** The Stop hook's scope is 26/298. The CI ledger's scope is 27/299.
The new CI gate reads the ledger and applies the same `FINISHED_STATES` filter, so it agrees with the hook by construction rather than by coincidence -- and it imports the frozenset from `wl_planfile` rather than copying it, the way `check_plan_boxes.py`'s G-A3 already does ("This INVERTS the Stop hook's own frozenset ... Same constant, imported, so the two halves cannot drift").

### 1.3 The corpus by status, and the fact that decides Part 5

| `Status:` | plans | open boxes |
|---|---|---|
| `draft` | 17 | **213** |
| `ready` | 4 | 39 |
| `partially` (parse artifact of "partially implemented") | 2 | 15 |
| `phase` (parse artifact of "phase N ...") | 1 | 15 |
| `executing` | 1 | 9 |
| `in-progress` | 1 | 7 |

**71% of the debt sits under `draft`, which `wl_planfile.NOT_STARTED_STATES` (`.claude/hooks/stop/wl_planfile.py:145-162`) exempts from every existing demand.** `wl_planfile`'s design note 4 (`.claude/hooks/stop/wl_planfile.py:52-73`) already recorded, on 2026-09-02, that this premise had stopped holding -- "`Status: draft` is the DEFAULT header on plans under active execution" -- and downgraded drafts to a one-line census rather than restoring the full demand.
This plan is where that half-measure is finished: **the new gate does NOT honour `NOT_STARTED_STATES`.** "ALL" means all, and the measurement is why: exempting `draft` would exempt 213 of 298 boxes and leave the gate asserting almost nothing.

Two of the six statuses (`partially`, `phase`) are parse artifacts of a `Status:` line the regex truncates at the first word. They are in scope anyway -- the blocklist shape at `.claude/hooks/stop/wl_planfile.py:116-118` is deliberate ("an unrecognised status is noisy rather than invisible") and an artifact is not a finished plan.

### 1.4 Ownership, live

| owner | plans | open boxes | `wl_store.session_liveness` verdict today |
|---|---|---|---|
| `d778be9d` | 14 | **188** | `live` (`.lastevent-d778be9d.json` written 0 min ago) |
| `f4da5c2e` | 4 | 48 | `idle` (newest event 2026-09-15T13:26:09Z) |
| `74de73ca` | 5 | 20 | `idle` (newest event 2026-09-04T21:49:48Z) |
| (no `Owner:` line) | 2 | 24 | n/a -- `wl_core.owned_by_me(None, sid)` is True, so these count as this session's |
| `8f55d4f0` | 1 | 18 | `idle` (newest event 2026-09-07T19:06:43Z) |

**212 boxes (188 + 24) are reachable by this session with no handoff. 86 belong to three peers, all three of which this machine reads as idle**, so all 86 are migratable today via `worklist.py --migrate d778be9d --plan <path>`. Part 6 is built on this.

(An earlier summary in this session said `d778be9d` owns 15 plans / 189 boxes. That is the ledger-scope number and includes the `Status: done` behavioral-hints plan from 1.2. The in-scope number is 14/188.)

### 1.5 The branch, and why a rollout mechanism is not optional

`git rev-list --count main..HEAD` = **654**. Branch `0914-1`. Merge-base `c6d3af163`, dated **2026-09-06 06:32:31 +0200** -- over two weeks of continuous checkout. PR `#589` already shipped from it and is `MERGED`; work has continued on the same branch since.

A gate that reds on the mere existence of an open box would, on the day it merged, red every Stop and every PR check on a tree carrying 298 boxes it did not create, owned across five identities.
`check_plan_boxes.py`'s own docstring already learned this lesson (`.ci/scripts/quality/check_plan_boxes.py:17-22`): "A GATE THAT REDS ON OPEN BOXES GETS SWITCHED OFF ... Failing on the mere existence of an open box would have been red on eight files at once, on the branch introducing the gate."

The operator saw these numbers and this branch age and still chose ALL. That ruling is not re-narrowed here. What it earns is a **clock**, not an exemption: Part 5.

### 1.6 The measurement that decides whether the proof rule can be retroactive

Corpus-wide, across all four plan folders:

```
$ grep -rhc "^    (ticked) " agent/plans/*.md agent/plans/_done/*.md agent/plans/_removed/*.md agent/*.md | paste -sd+ | bc
13
$ grep -rlc "^    (ticked) " agent/plans/*.md agent/plans/_done/*.md
agent/plans/PLAN-tooling-transformation.md
```

**13 evidence lines, all in one file, against 491 done boxes.** `--plan-tick` has been used on 2.6% of the boxes it was written for; the other 478 were flipped with the Edit tool and carry no evidence of any kind. There is nothing to re-check on them and never will be.

**Therefore the proof-of-implementation rule is strictly FORWARD-ONLY.** It binds the next tick, never a past one. This is not leniency -- it is the only version of the rule that is not vacuous, and saying so here prevents an implementer from "strengthening" it into a rule that reds 478 boxes it cannot possibly judge.

---

## Part 2 -- The blocking gate, Stop-hook half

### 2.1 Shape

A new module `.claude/hooks/stop/wl_planenforce.py`, mechanical, with **one** `vadd` key, `plan-unimplemented`, registered at `T_MISSION` in `PRIORITY_LADDER` (`.claude/hooks/stop/wl_checks.py:1991-2013`) beside the existing `plan-adopted`. The tier argument is the ladder's own (`.claude/hooks/stop/wl_checks.py:1974-1976`): "The thing this session was ASKED to do is not done ... Nothing else can matter more."

`wl_backlog.py`, `wl_planfile.py` and `wl_checks.py`'s existing plan blocks are not modified except for the single new call site and the single new ladder entry. Following `.claude/hooks/stop/wl_backlog.py:18`, `recs` and `plan_owner` are injected rather than imported, so the module never imports `wl_checks` and the selftest can drive it on fixtures.

### 2.2 The predicate, in order

1. **Corpus.** `plan_records(root)`, already computed once per stop at the `wl_checks` call site; reuse it, never a second scan.
2. **Status.** drop `FINISHED_STATES` (imported from `wl_planfile`). **Do not** drop `NOT_STARTED_STATES` -- see 1.3.
3. **Boxes.** `wl_planfile.plan_boxes(text)`; zero open boxes means silent. A plan with raw `- [ ]` lines the parser resolves to none is reported as BLIND and never as clean, per the `V_PR_UNREADABLE` convention `.claude/hooks/stop/wl_planfile.py:91` already states.
4. **The clock.** Compute the corpus ceiling (Part 5). If the live open-box count is at or under it, the gate is **silent** -- not advisory, silent. A clock that talks while it is satisfied is a clock nobody reads.
5. **Ownership split.** `C.owned_by_me(plan_owner(root, rel), session_id)` partitions the over-ceiling debt into `MINE` (blocks) and PEERS' (named, with recipes, never blocked on -- Part 6).
6. **The one named box.** The block names exactly ONE box: the first open box of the newest-mtime in-scope plan this session can reach, with its 8-hex signature from `wl_planrec.box_sig`, and the exact `--plan-investigate` / `--plan-tick` command pair.
  `wl_backlog.render`'s discipline applies verbatim (`.claude/hooks/stop/wl_backlog.py:261`): **no live counter anywhere in the text**, because a minute-precision age moves `outq_add`'s content signature on every stop and re-enqueues forever. Counts of boxes and plans are stable between edits and are safe.

### 2.3 What ends the block, and there are five doors

A block with one door is a wedge. All five are printed in the message:

1. `worklist.py --plan-investigate <me> <plan> <sig> <pointer>...` then `--plan-tick ... --write` -- the box is done and now says so.
2. The door is `worklist.py --add <me> "<box text>"`, which puts the box on the worklist where `open-items` already owns it. The plan's debt becomes worklist debt, which is the mechanism the whole hook is built on.
3. `worklist.py --migrate <me> --plan <path>` -- take a peer's idle plan, which stamps the adoption marker and moves it into door 1 or 2.
4. `worklist.py --defer <me> <id> '<q> DEFAULT: <action> WHY: ... HOW: ...'` -- the box is genuinely the operator's call. `.claude/hooks/stop/worklist.py:716-729` already enforces the WHY/HOW shape.
5. `worklist.py --plan-compact <me> <path> --park` -- the plan's TEXT is compacted while its work stays unfinished; `.claude/hooks/stop/wl_planfile.py:158-161` records that `parked` deliberately stays on every clock, so this buys a smaller file and never an exemption.

Editing `Status:` to a finished word is **not** a door: `check_plan_boxes.py` G-A3 reds on it, which is exactly what is happening on `PLAN-stop-hook-behavioral-hints.md` today (0.4). The message says so, because a door the gate will punish is worse than no door.

### 2.4 The latch, and why it is not the usual one

The existing advisories use `Demand` (`.claude/hooks/stop/wl_rules.py:133-176`) with a TTL and a max-fires cap. **A `T_MISSION` block must not have a fire cap** -- a mission that goes quiet after two asks is not a mission.
The bound instead comes from the ceiling itself: the block is silent whenever the corpus is at or under the clock, so the session can always end the block with a bounded amount of real work.
That is the property that distinguishes this from the three repeated-nag incidents (`PLAN-fix-stop-hook-completion-evidence-refire.md`, `PLAN-stop-hook-refactor-enforcement.md`, `PLAN-sweep-obligation-carry-forward.md`): **every one of those blocked with no reachable exit.** Here the exit is arithmetic and is printed in the message: "tick N more boxes, or move them, and this goes quiet."

---

## Part 3 -- Investigation enforcement: the hard part

### 3.1 The exact failure being closed

Today, a session or a subagent can write into `--tick` or `--plan-tick` a string that LOOKS like evidence and have it accepted with nothing checked:

- `--plan-tick` accepts any 12 characters (`.claude/hooks/stop/wl_planrec.py:1889`, 0.5).
- `--tick` accepts `"exit 0"`, `"123456789"` or any URL by shape alone (`.claude/hooks/stop/wl_checks.py:462`, 0.6).
- Nothing anywhere asserts that an investigation happened BEFORE the implementation, which is the half of `CLAUDE.md:161-163` ("Search first") that has no mechanism at all.

And the live corpus proves the failure is real in both directions: `agent/plans/_done/PLAN-stop-hook-behavioral-hints.md:264` is an implemented box left open with its own finding typed into the box text, and the 478 evidence-free done boxes of 1.6 are ticks nobody can check.

### 3.2 Four mechanisms, scored

Four genuinely different instruments, not four variants of one. Scored on the tree's real volume: 298 open boxes, 354 worklist ticks in `agent/worklist/*.jsonl`, and a Stop hook whose outer harness budget is 900s (`.claude/settings.json`, Stop hook `"timeout": 900`).

| | **A. Pointer re-derivation** | **B. Judge adjudication** | **C. Differential re-run** | **D. Subagent per tick** |
|---|---|---|---|---|
| **What it actually checks** | every pointer in the evidence resolves NOW, by the hook's own `git`/filesystem call, via `wl_planrec.resolve` | does the quoted excerpt demonstrate the quoted claim (semantic) | the named `check:*` gate's real exit code, obtained by running it | an independent reader re-opens the artifacts and agrees or not |
| **Oracle** | git objects, the filesystem, `package.json` scripts, `TRAPS.md` ids -- none forgeable by typing | an LLM's reading | the gate's own process exit | an LLM agent's reading, with tools |
| **False-accusation rate** | **0 by construction** -- it only ever says "this pointer does not resolve", which is a fact | **12.4%-36%, measured** (`.claude/hooks/stop/wl_claimcheck.py:9-11`) | 0 on the gate's own verdict | unmeasured, and unmeasurable without a second oracle |
| **Cost per box** | 1-3 `git cat-file`/`rev-parse` or one file read; sub-100ms | ~0 marginal (rides a judge call already paid; `.claude/hooks/stop/wl_judge.py:24` measures haiku at $0.011-0.026 and 4.9-20.0s per WHOLE call) | up to `REGGATE_TIMEOUT_S`=120s, **hash-cached** so an unchanged gate is free (`.claude/hooks/stop/wl_reggate.py:596-600`) | one agent run. Live measurement: the tick at `agent/worklist/d778be9d.jsonl:116` records an Explore agent re-verifying **8 boxes in 48 tool calls** |
| **Cost at 298 boxes** | ~300 git calls, seconds | n/a (one object per stop, not per box) | only for boxes claiming a gate; the cache collapses repeats | **~1,800 tool calls**, minutes-to-hours of wall clock, at a Stop hook with a 900s ceiling |
| **May it BLOCK?** | **Yes.** Nothing to calibrate, nothing to tune, no threshold | **No** -- forbidden in writing by `.claude/hooks/stop/wl_claimcheck.py:16-32`, and the graduation criterion at `:26-27` is unmet | **Yes**, and `wl_reggate.prove_new_gate` already does exactly this | No -- cannot block on a mechanism that cannot complete inside the hook's budget |
| **What a liar must now do** | open the artifact and find a line/object that really exists -- `citation_state`'s "forcing function" (`.claude/hooks/stop/wl_checks.py:400-403`) | write a plausible paragraph | make the gate actually pass | convince a second model |
| **What it still does NOT catch** | a real line that says nothing about the claim -- precisely the gap B was written for, and which B's own measurements prove is not mechanically closable | its own 12-36% error | a gate that cannot fail (`docs/agent-reference/TRAPS.md:48`, `check-cannot-fail`) | its own unmeasured error, at a cost nothing else here pays |
| **Precedent in this tree** | `wl_planrec.resolve` (`:326`), `citation_state` (`:390`), `check_plan_citations.py` | `wl_claimcheck` (advisory, live) | `wl_reggate.prove_new_gate` (`:544`) | none; never attempted here |

### 3.3 The verdict, and the honest statement of what it buys

**A blocks. C blocks, but only on the one pointer kind where it is already cheap. B rides along as an advisory, unchanged in character from `wl_claimcheck`. D is refused on cost, with the measurement above as the reason.**

The honest statement, written here so no reader mistakes the mechanism for more than it is:

> This does not make a lie impossible. It moves the cost of a lie from "type a plausible string" to "open the artifact, find a real object or a real line, and for a gate claim make the gate actually pass." That is the same bargain `citation_state` struck in 2026-08 and the only bargain the 342-tick measurement in `wl_claimcheck` supports. `docs/agent-reference/TRAPS.md:66` (`ruling-from-an-artifact-is-a-hypothesis`) applies to this mechanism too: the pointer resolving is a fact, the claim it is attached to is still a hypothesis, and B is what reads the hypothesis.

### 3.4 The investigation record

A new append-only ledger, `agent/ledgers/plan-investigation.jsonl`, in the same shape as the two ledgers already there (`agent/ledgers/census-claim-check.jsonl`, `census-plan-record.jsonl`), written through `wl_store._append_lines` under the same flock discipline `wl_claimcheck.census` uses (`.claude/hooks/stop/wl_claimcheck.py:407-422`), with the lock sidecar in `TMPDIR` for the reason stated at `.claude/hooks/stop/wl_claimcheck.py:395-404` (a fourth untracked `.lock` beside a tracked file is a defect the clean-tree gates would report).

One row per investigated box:

```json
{"at":"2026-09-23T09:14:02Z","by":"d778be9d","plan":"agent/plans/PLAN-x.md","sig":"13dc5108",
 "verdict":"absent","head":"2ed7d6726","br":"0914-1",
 "pointers":[["fileline","wl_hints.py:105"],["gate","check:ci-hint-corpus"],["commit","7dd14f98f"]],
 "resolved":[["fileline",true,"wl_hints.py:105"],["gate",true,"package.json scripts"],["commit",true,"7dd14f98f..."]],
 "note":"hint_pick exists; no corpus gate is registered under any name (grep over package.json scripts)"}
```

`verdict` is one of three, and the vocabulary matters:

- `absent` -- the work is not in the tree. Implement it.
- `present` -- **the work is ALREADY DONE and only the record is stale.** This is the case `CLAUDE.md:163` names ("Several campaign boxes closed by finding the work already landed and only the record was stale, not by doing it again") and `agent/plans/_done/PLAN-stop-hook-behavioral-hints.md:264` is a live instance of.
  A `present` verdict is a complete, honourable answer and licenses an immediate `--plan-tick`.
- `partial` -- some of it exists; `note` says which part, and the box stays open.

**A `present` verdict's pointers are the strongest ones the scheme can produce**, because they name the existing artifact. This is the single feature that makes the mechanism worth a session's time rather than a tax: it converts "go and check whether this is already done" from unrewarded diligence into the cheapest way to close a box.

### 3.5 The verb

`worklist.py --plan-investigate <me> <plan-path> <box-sig-or-substring> <verdict> <kind>:<token>... -- <note>`

Behaviour, all of it re-derivation and none of it trust:

1. Resolve `<plan-path>` and `<box-sig-or-substring>` through `wl_planrec.open_boxes` + `select_box` (`.claude/hooks/stop/wl_planrec.py:1768`, `:1786`). Ambiguity is a refusal, not a first-match -- `select_box`'s own rule, and it is right for the same reason here.
2. Refuse a `<verdict>` outside the three.
3. **Re-resolve every pointer through `wl_planrec.resolve(root, kind, token)` and refuse the whole row if any one fails**, naming which. At least **two** pointers of at least **two distinct kinds** are required: one pointer is a citation, two of different kinds is a triangulation, and the asymmetry is cheap.
4. A `gate:` pointer additionally requires the gate to be **reachable from `npm run ci`** -- `wl_reggate.gate_reachable(scripts, key, root)`, the same call `prove_new_gate` makes at `.claude/hooks/stop/wl_reggate.py:592` -- because `docs/agent-reference/TRAPS.md:48` (`check-cannot-fail`) and `check-gate-reachability.ts` both exist for gates that are defined and never run.
5. Refuse a `<note>` under 40 characters. A note is what a later reader uses; the 12-character floor at `.claude/hooks/stop/wl_planrec.py:1764` is the mistake being corrected, not copied.
6. Append the row. **Never commits** -- the same contract every verb in `worklist.py` keeps.

Ordinary shell quoting is the interface; no new parser is introduced. `--dry-run` prints the resolution table and writes nothing, matching `--plan-tick`'s own dry/`--write` split (`.claude/hooks/stop/worklist.py:619-623`).

### 3.6 The rule that makes it "investigation BEFORE implementation" rather than a post-hoc story

Two clauses, and the second is the one with teeth:

- **Clause 1 (ordering).** A row's `head` field records `git rev-parse HEAD` at write time. `--plan-tick` refuses when the tick's own cited commit is **not** a descendant of the investigation row's `head`.
  Mechanism: `git merge-base --is-ancestor <row.head> <cited-sha>`, the same primitive `wl_planrec.resolve`'s `ancestor` kind already uses (`.claude/hooks/stop/wl_planrec.py:356-365`). **An investigation written after the implementation commit cannot satisfy this**, because the commit would not be a descendant of a head recorded later.
- **Clause 2 (the negative claim is the investigation).** A `verdict: "absent"` row is a **falsifiable assertion about the tree at `row.head`**: "this work is not there". `--plan-tick` re-checks it.
  If the box's own tick evidence cites a `fileline` that already resolved at `row.head` -- checked with `git cat-file -e <row.head>:<path>` and a line-count read of that blob -- the tick is **refused**, because the investigation claimed absence of something the investigation itself could have found.

Clause 2 is the part that cannot be satisfied by a well-worded lie, and it is worth stating why in one sentence: **it is the only clause where the mechanism has an opinion the session did not supply.** Clauses about pointer resolution can be satisfied by finding any real pointer; this one compares two of the session's own claims against each other across a git revision, and a fabricated investigation contradicts the fabricated tick.

### 3.7 What is deliberately NOT built, and why

- **No "not-implemented" tick door.** A box is not closable by investigating it and declaring it hard. That would be `wl_admit`'s territory and it would make the whole gate optional in one command. The door for a box that cannot be worked now is the worklist (`--add`) or the operator (`--defer`), both of which keep it visible -- 2.3 doors 2 and 4.
- **No semantic threshold anywhere.** No overlap score, no similarity number, no "evidence quality" rating. `.claude/hooks/stop/wl_claimcheck.py:112-114` already measured that the one available score does not discriminate and stated that it "survives here as one weak input among several ... never a threshold in code". That sentence is inherited.
- **No retroactive proof demand.** 1.6 measured why: 478 of 491 done boxes carry nothing to check.
- **No new `WORKLIST_*` env name without a registry entry.** Every such name must be declared in `.ci/policy/worklist-env-registry.json`, enforced by `check:ci-worklist-env-registry`; `.claude/hooks/stop/wl_claimcheck.py:370-372` records a module deliberately using plain constants rather than pay that cost for an untunable rule.
  The same choice is taken here for the pointer-count and note-length floors; only the clock's numbers (Part 5) live in config, because they WILL be retuned.

### 3.8 The advisory layer, unchanged in character

`wl_claimcheck` continues to ride the existing judge call. One addition only: when the fix-set's tick is a **plan-box** tick, the prompt section is handed the investigation row's `note` and `verdict` beside the claim, so the judge is reading the investigation rather than inferring one. This adds prompt tokens to a call already being made and no new call.
Its verdict remains advisory and continues to append to `agent/ledgers/census-claim-check.jsonl`; its graduation criterion (`.claude/hooks/stop/wl_claimcheck.py:26-27`) is untouched.

---

## Part 4 -- The CI half

### 4.1 The gate

`.ci/scripts/quality/check_plan_implementation.py`, modelled directly on `.ci/scripts/quality/check_hint_corpus.py` (348 lines, commit `7dd14f98f`), which is this session's own worked example of the three-point wiring and the control-first shape.

Gate header, in the same position and format as `.ci/scripts/quality/check_hint_corpus.py:16-22`:

```
---- gate ----
step: Plan implementation clock
needs: none
selftest: true
lane: quality-branch
---- end gate ----
```

`quality-branch` (`.github/workflows/ci-quality.yml:513-522`) is the right lane and not `quality-content`: that job is `if: github.event_name == 'pull_request'` with `fetch-depth: 0` + `filter: blob:none`, which is exactly what the clock's `git log` reads need and exactly what `check:ci-plan-boxes` already uses for G-A1..G-A5.

### 4.2 Assertions

Named `P-A0..P-A6` following `check_plan_boxes.py`'s `G-` convention and its own warning about colliding id schemes (`.ci/scripts/quality/check_plan_boxes.py:26-30`).

- **P-A0** The ledger is the corpus. Read `.ci/config/plan-boxes.json`; do not re-scan `agent/`. Refuse if `check:ci-plan-boxes` would disagree -- the gate calls the ledger-vs-tree comparison from the sibling module rather than duplicating it.
- **P-A1** **The clock.** In-scope open-box count (ledger rows, minus `FINISHED_STATES` imported from `wl_planfile`) must be at or under the ceiling for today's date (Part 5). Over the ceiling is a **red**, naming the count, the ceiling, the date, and how many ticks close the gap.
- **P-A2** **Forward-only proof.** Every box that moved `open -> done` **between the merge-base ledger and the HEAD ledger** (`ledger_at(root, base)` vs the working ledger, `.claude/hooks/stop/wl_planrec.py:681`) must carry an `(ticked)` evidence line in the plan file and a matching `agent/ledgers/plan-investigation.jsonl` row whose `sig` matches and whose pointers **still resolve at HEAD**.
  Boxes already done at the merge-base are never judged (1.6).
- **P-A3** **Pointer re-derivation in CI.** Every pointer in every investigation row referenced by P-A2 is re-resolved through `wl_planrec.resolve` **in the CI checkout**, not trusted from the row's own `resolved` field.
  A row whose pointers resolved locally and not in CI is a finding, and the message says which kind failed. (`ancestor` is the kind most likely to differ, which is the point.)
- **P-A4** **Ordering.** For each P-A2 box, `git merge-base --is-ancestor <row.head> <the commit that ticked the box>`. Clause 1 of 3.6, enforced where the full topology is available.
- **P-A5** **Owner reachability.** A plan that this branch ADDS with open boxes must resolve an `Owner:`. This is `check_plan_boxes.py`'s G-A4 and is **not** re-implemented -- P-A5 asserts G-A4 is still registered and reachable, so the new gate reds if the old one is ever unwired. (`docs/agent-reference/TRAPS.md:48`'s recursive clause: the check of the check.)
- **P-A6** **Anti-vacuity.** A floor on plans scanned, a floor on boxes considered, and a refusal to render a verdict when the ledger resolves zero boxes from a corpus that plainly holds `- [ ]` lines. Copied in spirit from `check_plan_boxes.py`'s G-A6 and `check_hint_corpus.py`'s own refusal to judge the real corpus when a plant is not caught.

### 4.3 Three-point wiring, verbatim from `7dd14f98f`

1. `package.json`: `"check:ci-plan-implementation": ".ci/scripts/quality/check_plan_implementation.py"`, beside `check:ci-plan-boxes`.
2. `scripts/ci-runner/manifest.ts`: a `GATES` entry with `gate: true`, `leaves: ['.ci/scripts/quality/check_plan_implementation.py', '.ci/config/plan-implementation.json']`, and `ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-branch', step: 'Plan implementation clock' }`.
3. `.github/workflows/ci-quality.yml`: a step in the `quality-branch` job (which starts at `:513`), guarded `if: ${{ !cancelled() && steps.setup.outcome == 'success' }}` like every sibling.

Then regenerate: `npx tsx scripts/gen/gen-docs.ts --write` (the CLAUDE.md gate tables at `CLAUDE.md:285-308` are generated and `gate-test:docs-gen` fails on drift), and confirm `check:ci-gate-bind`, `check:ci-parity` and `check:ci-gate-reachability-coverage` are green.

The workflow filename was verified rather than assumed: `.github/workflows/ci.yml` is the orchestrator (`name: Console CI`) and calls the reusable `./.github/workflows/ci-quality.yml` at `.github/workflows/ci.yml:496`. **The gate steps live in `ci-quality.yml`.**

---

## Part 5 -- The rollout clock

### 5.1 The two candidate shapes, and why the second wins

| | **Grace cliff** (the shape `.ci/config/agent-session-archival.json` uses) | **Descending ceiling** (proposed) |
|---|---|---|
| Rule | silent for `grace_days` from landing, then red on any open box | red whenever open-box count exceeds `baseline - floor(days_since_landing * drain_per_day)` |
| Day 1 | silent | silent (ceiling == baseline) |
| Day `grace+1` | **red on 298 boxes at once** | red only if fewer than `drain_per_day * days` have been closed |
| Rewards | nothing, until the last day | every tick, immediately -- a day's drainage buys days of slack |
| Failure mode | one cliff, on a date, on whoever's PR runs next; the exact shape `agent-session-archival.json`'s own `$comment` warns about ("blaming whoever's branch runs CI next ... the exact shape that gets suppressed within a day") | a session that closes nothing for a week is red on the eighth day and knows the number a week in advance |
| Auditable from | one date | two committed files, `plan-implementation.json` + `plan-boxes.json` |

The cliff is the shape already in the tree, and its own config file argues against itself for exactly this case. **The descending ceiling is chosen.**

### 5.2 The numbers

`.ci/config/plan-implementation.json`, a new file in the shape `.ci/config/plan-lifecycle.json` and `.ci/config/agent-session-archival.json` establish (a `$comment` array carrying the reasoning, then the numbers):

```json
{
  "$comment": ["...why a ceiling and not a cliff; how the numbers were chosen; what would falsify them..."],
  "baseline_open": 298,
  "baseline_at": "<the date this gate MERGES, written by the implementer>",
  "drain_per_day": 7,
  "warn_slack": 20,
  "floor_open": 0
}
```

**`drain_per_day: 7`** clears 298 boxes in **43 days**. The operator's bias is short and aggressive; 7/day is one working day's drainage of a single 20-box plan every three days, which this session has demonstrably sustained (14 plans and 188 boxes were authored on this branch in 16 days).
10/day would clear it in 30 days and is the fallback if 7 proves slack; the number is in config precisely so a retune is not a code change, which is `plan-lifecycle.json`'s own stated reason for existing.

**`baseline_at` is the LANDING date, not any plan's age.** This is the operator-floated mechanism and it is adopted verbatim: nobody is punished for a plan written before the rule existed, and the clock still starts immediately and never stops.

**`warn_slack: 20`** is the band, the same humane device `plan-lifecycle.json`'s `warn_days: 26` against `delete_days: 33` provides: within 20 boxes of the ceiling the Stop hook speaks as an advisory at priority 2, over it as a `T_MISSION` block, and CI reds only over it.
`plan-lifecycle.json`'s `$comment` names why a clock-driven gate needs a warn band at all ("its verdict can flip overnight with no commit, which `scripts/lib/suppression-liveness.ts` normally bans").

**ONE number, read by both halves.** The Stop hook and the CI gate read this same file. `plan-lifecycle.json`'s `$comment` states the rule being obeyed: "Duplicating `33` into two scripts is exactly what would create the deadlock ... So neither gate may inline the number."

### 5.3 What the clock does NOT do

It does not stop. There is no renewal, no extension verb, and no allowlist. `docs/agent-reference/suppressions.md` governs every escape hatch in this repo and **this gate deliberately ships with none**, because an allowlist here would be an allowlist against "implement the plan", which is the whole ask.
A `floor_open` key exists at `0` so that a future operator decision to hold a standing floor is a config edit rather than a redesign; it is not used at landing.

### 5.4 The landing sequence

The gate lands **red-proof**: `baseline_open` is written from the ledger at landing time, so the ceiling on day 0 equals the live count and both halves are silent on the merge commit. The very first thing the gate does in anger is on day 1, at 291.

---

## Part 6 -- Multi-owner

### 6.1 The rule

**The block never demands that this session tick a box on a plan another session owns.** Ownership is resolved exactly once, by `wl_checks.plan_owner` (`.claude/hooks/stop/wl_checks.py:786`) through `PLAN_OWNER_RE` (`.claude/hooks/stop/wl_checks.py:767`), and compared with `wl_core.owned_by_me`, which treats an unowned plan as this session's for the reason `.claude/hooks/stop/wl_planfile.py:302-310` states ("wrongly claiming one costs a little reading, wrongly disowning one drops it silently").

### 6.2 Liveness is not re-derived

`wl_backlog._dead_peer` (`.claude/hooks/stop/wl_backlog.py:147-169`) is **imported and called**, not reimplemented. It already walks `wl_store.session_liveness` (`.claude/hooks/stop/wl_store.py:1291`), already skips `live`/`unknown` owners, and already returns the count plus the newest candidate.
Its own comment (`.claude/hooks/stop/wl_backlog.py:150-151`) states the reason this gate inherits: "implementing one without `worklist.py --migrate --plan` first would produce a committed document that contradicts who did the work."

### 6.3 The three-way split in the message

The block's text partitions the over-ceiling debt:

- **`MINE`** (`owned_by_me` true): named, with one box and its `--plan-investigate` / `--plan-tick` pair. Today: 212 boxes across 16 plans.
- **A PEER'S, and the peer reads IDLE**: named with `worklist.py --migrate <me> --plan <path>` and nothing else. Today: all three peers are idle, so all 86 boxes across 10 plans are in this bucket.
  Migration stamps the adoption marker via `ADOPTED_OWNER_FMT` (`.claude/hooks/stop/wl_planfile.py:316`, written at `.claude/hooks/stop/worklist.py:1016`), after which the plan is `MINE` and the existing `plan-adopted` vadd also applies -- the two blocks agree by construction because they read the same marker.
- **A PEER'S, and the peer reads LIVE**: **counted and subtracted from the ceiling comparison, with the subtraction stated in the text.** This is the one arithmetic concession in the design and it is necessary: demanding drainage of boxes a live peer is actively working would make the ceiling unreachable by any action this session can take, which is the no-reachable-exit shape Part 2.4 exists to avoid. A peer that goes idle drops back into bucket two on the next stop, with no state to remember.

Peer-owned boxes are **never** silently excluded from the census -- they are named and counted. `wl_backlog.render`'s own dead-peer block (`.claude/hooks/stop/wl_backlog.py:298-307`) is the format to follow.

### 6.4 The CI half does not know about sessions

CI has no liveness oracle and must not invent one. P-A1 therefore compares the **whole** in-scope count against the ceiling, with no ownership term. The asymmetry is deliberate and stated in the gate's docstring: the Stop hook knows who is running and adjusts what it DEMANDS OF THIS SESSION; CI knows only what landed and asserts what the BRANCH owes.
A branch whose peers are all idle owes all of it, which is true today.

---

## Part 7 -- Controls, and the anti-vacuity argument

`docs/agent-reference/TRAPS.md:48` (`check-cannot-fail`): "Before believing a clean result, make the check produce a RED on known-bad input **through the same path** ... This applies recursively: to the check, and to the check of the check." `.ci/scripts/quality/check_hint_corpus.py:10-11` is the shape: **every plant is driven before the real corpus is judged at all, and a plant that is not caught makes the gate declare itself broken and exit non-zero without judging anything.**

### 7.1 The two controls the operator named, verbatim

- **C1 -- the investigation-less tick is caught.** Plant, in a fixture tree: a plan with one open box, ticked to `- [x]` with an `(ticked)` evidence line reading `"exit 0, done, verified"` -- 22 characters, which clears `TICK_EVIDENCE_MIN` and clears `completion_evidence`'s `EXIT_RE` shape branch -- and **no** row in `plan-investigation.jsonl`.
  Assert: `--plan-tick` refuses it, the Stop-hook gate blocks on it, and `check_plan_implementation.py` P-A2 reds on it. **All three must fire**; a plant caught by only one of the three means two of the three paths are ornamental.
- **C2 -- the genuinely investigated tick passes.** Same fixture, plus an investigation row whose pointers are a real blob in the fixture's git repo and a real `file:line`, written at a `head` the tick's commit descends from, and a tick whose evidence cites that commit. Assert: silence from all three.
  **A control that only ever reds is half a control** -- this is the half that proves the gate is not a wall.

### 7.2 The plants that close the specific cheats

- **C3** pointers present but one does not resolve (a `commit:` naming a plausible 9-hex that is not an object) -> refused, naming which kind failed.
- **C4** two pointers of the SAME kind -> refused (3.5 clause 3).
- **C5** an investigation row written AFTER the implementation commit (`row.head` is a descendant of the cited commit, not an ancestor) -> refused by Clause 1 (3.6).
- **C6** a `verdict: "absent"` row whose tick then cites a `fileline` that already resolved at `row.head` -> refused by Clause 2 (3.6). **This is the single most important plant in the set**, because Clause 2 is the only place the mechanism holds an opinion the session did not supply.
- **C7** a `gate:` pointer naming a `check:*` key that exists in `package.json` but is **not reachable from `npm run ci`** -> refused (3.5 clause 4), which is `check-gate-reachability`'s own failure shape.
- **C8** the ceiling itself: a fixture at `baseline_open` on day 0 is silent; the same fixture at day 1 with zero ticks is red; the same fixture at day 1 with `drain_per_day` ticks is silent. **Three assertions, because a clock asserted at one point is a constant.**
- **C9** `wl_backlog` and `wl_planfile` are unchanged in behaviour: `test-planfile.py`'s existing control pinning `plan-tasks` as never-a-vadd, and `wl_backlog`'s own never-blocks control, both pass untouched. A new blocking module that silently promoted a neighbouring advisory would be the exact conflation the operator's brief forbids.
- **C10** the recursive clause: a control asserting that the Stop-hook half and the CI half read the **same** `plan-implementation.json` key names, so a rename in one cannot leave the other reading a default.

### 7.3 Where the controls live

Stop-hook side: `.claude/hooks/stop/test-planenforce.py`, beside its module, run by `.claude/hooks/test-hooks.sh` -- the placement `.claude/hooks/stop/wl_planfile.py:515` states as the convention ("Keeping them out of here keeps the import that every Stop pays for free of fixtures"). CI side: in-file, control-first, before the real judgement, exactly as `check_hint_corpus.py` does it.
`check:ci-test-file-orphans` exists to catch a suite that is committed and runs nowhere (`test-teammate-idle.py` was committed with 20 controls and ran nowhere), so registration is verified, not assumed.

---

## Part 8 -- Risks, each with its named mitigation

| Risk | Why it is real here | Mitigation |
|---|---|---|
| **The gate becomes the fourth repeated-nag incident** | Three are already on record: `PLAN-fix-stop-hook-completion-evidence-refire.md`, `PLAN-stop-hook-refactor-enforcement.md`, `PLAN-sweep-obligation-carry-forward.md`. All three blocked with no reachable exit | Five doors (2.3), an arithmetic exit printed in the message, and no fire cap precisely because the exit is reachable (2.4) |
| **The investigation verb becomes a ritual** | A session learns to produce two resolving pointers about anything | Clause 2 (3.6) is the answer, and C6 is its control. Beyond that, the census rows make the question answerable later rather than asserted now -- `wl_claimcheck`'s graduation-criterion discipline |
| **`drain_per_day: 7` proves wrong** | It is a judgement call on one session's observed cadence | It is in config, not code, for exactly the reason `plan-lifecycle.json`'s `$comment` gives. Falsifiable: if the ceiling is missed for two consecutive weeks with real work landing, the number is wrong, not the sessions |
| **A peer goes idle mid-drain and its 48 boxes land on this session** | `f4da5c2e` owns 48 boxes and last spoke 2026-09-15 | They land as a `--migrate --plan` recipe, never as a tick demand (6.3). Migration is an explicit act |
| **`check:ci-plan-boxes` is already red (0.4), so the new gate lands on a red foundation** | Measured today, exit 1 | Task 0: drain all three before anything new is wired. The new gate's P-A0 refuses to judge when the ledger disagrees with the tree, so it cannot paper over a red sibling |
| **Two other agents are editing `.ci/` and `agent/PLAN-*.md` in this session** | archival implementation on `PLAN-agent-session-archival.md` and `.ci/`; a general-purpose agent deleting stub plans and repointing citations | This plan's new files are disjoint: `wl_planenforce.py`, `test-planenforce.py`, `check_plan_implementation.py`, `plan-implementation.json`, `plan-investigation.jsonl`. The only shared files are `package.json`, `manifest.ts`, `ci-quality.yml` and `wl_checks.py`, each touched by one added line. **`.ci/config/agent-session-archival.json` is not touched.** Implementation must re-check ownership before starting, since stub deletions move plan paths this gate's census reads |
| **A session games the ceiling by deleting plans** | 298 boxes could be "drained" with `rm` | `check_plan_boxes.py` G-A1/G-A2/G-A5 already own every way a box can disappear, including deletion, un-checkboxing, rewriting, fencing and renaming out of the glob. P-A5 asserts that gate is still wired |

---

## Tasks

- [x] T0. Drain the three live `check:ci-plan-boxes` reds before anything new lands: tick `agent/plans/PLAN-stop-hook-behavioral-hints.md:264` (the work is done and the box text says so), and resolve `Owner:` on `PLAN-haiku-model-routing.md` and `PLAN-secret-namespace-migration.md` (24 boxes, currently unowned).
    (ticked) 2026-09-22T21:00:50Z by d778be9d: check_plan_boxes.py exits 0 on this tree; the last red was a false positive fixed at .ci/scripts/quality/check_plan_boxes.py:403 (_known_at_base), at 2ed7d6726e82098eddb62f1488670ad6e43ba872
  Regenerate and commit `.ci/config/plan-boxes.json`. Proof: `.ci/scripts/quality/check_plan_boxes.py` exits 0.
- [x] T1. Add `.ci/config/plan-implementation.json` with the `$comment` reasoning, `baseline_open` read from the ledger at landing, `baseline_at`, `drain_per_day: 7`, `warn_slack: 20`, `floor_open: 0`.
    (ticked) 2026-09-22T21:03:29Z by d778be9d: the clock config with its reasoning is at .ci/config/plan-implementation.json:90, baseline re-measured against the live tree rather than copied from the design, at 2ed7d6726e82098eddb62f1488670ad6e43ba872
- [x] T2. Close the `--plan-tick` evidence drift: make `wl_planrec.plan_tick` call `wl_checks.completion_evidence` in addition to the `TICK_EVIDENCE_MIN` floor, so the two tick verbs stop disagreeing. Control: the existing 12-character evidence `"done it, works"` is refused where it is accepted today.
    (ticked) 2026-09-22T21:03:29Z by d778be9d: plan_tick now calls it at .claude/hooks/stop/wl_planrec.py:2229; the control proving 'done it, works' is refused where it was accepted is in test-planenforce.py, at 2ed7d6726e82098eddb62f1488670ad6e43ba872
- [x] T3. Add `worklist.py --plan-investigate` per 3.5, with `--dry-run`, the `wl_planrec.resolve` re-derivation loop, the two-pointers-two-kinds rule, the `gate_reachable` clause, and the 40-character note floor.
    (ticked) 2026-09-22T21:03:29Z by d778be9d: the verb is dispatched at .claude/hooks/stop/worklist.py:1972 and its body re-resolves every pointer through wl_planrec.resolve, at 2ed7d6726e82098eddb62f1488670ad6e43ba872
- [x] T4. Add the append-only `agent/ledgers/plan-investigation.jsonl` writer, reusing `wl_store._append_lines` and the `TMPDIR` lock sidecar pattern from `wl_claimcheck.census`.
    (ticked) 2026-09-22T21:04:14Z by d778be9d: the writer is .claude/hooks/stop/wl_planrec.py:1927 and its reader at :1941, both through wl_store._append_lines under the TMPDIR sidecar, at 2ed7d6726e82098eddb62f1488670ad6e43ba872
- [x] T5. Add Clause 1 (ancestor ordering) and Clause 2 (the negative claim is falsifiable) to `--plan-tick`'s refusal path, per 3.6.
    (ticked) 2026-09-22T21:03:30Z by d778be9d: Clause 1 is at .claude/hooks/stop/wl_planrec.py:2141 and Clause 2 at :2174, both driven by controls C5 and C6, at 2ed7d6726e82098eddb62f1488670ad6e43ba872
- [x] T6. Write `.claude/hooks/stop/wl_planenforce.py`: the scope predicate (Part 1.1), the ceiling read (Part 5.2), the three-way ownership split calling `wl_backlog._dead_peer` (Part 6), and the render with no live counter.
    (ticked) 2026-09-22T21:03:30Z by d778be9d: the module is .claude/hooks/stop/wl_planenforce.py:358 (evaluate), with the ceiling, the three-way ownership split and the render that carries no live counter, at 2ed7d6726e82098eddb62f1488670ad6e43ba872
- [x] T7. Add the `plan-unimplemented` message to `worklist_messages.py`, modelled on `V_PLAN_ADOPTED` (`.claude/hooks/stop/worklist_messages.py:1070`), printing all five doors and the arithmetic exit.
    (ticked) 2026-09-22T21:04:14Z by d778be9d: V_PLAN_UNIMPLEMENTED is at .claude/hooks/stop/worklist_messages.py:1085, one hole for a body wl_planenforce.render computes, registered in the arity table, at 2ed7d6726e82098eddb62f1488670ad6e43ba872
- [x] T8. Wire one `vadd` call site in `wl_checks.py` beside the existing `plan-adopted` block, and one `plan-unimplemented` entry in `PRIORITY_LADDER`'s `T_MISSION` frozenset.
    (ticked) 2026-09-22T21:04:14Z by d778be9d: the vadd is at .claude/hooks/stop/wl_checks.py:3194 and the ladder entry at :2002; check_tier('plan-unimplemented') returns T_MISSION, at 2ed7d6726e82098eddb62f1488670ad6e43ba872
- [x] T9. Write `.claude/hooks/stop/test-planenforce.py` with controls C1-C10, and confirm `.claude/hooks/test-hooks.sh` runs it.
    (ticked) 2026-09-22T21:03:31Z by d778be9d: 71 controls, all passing, at .claude/hooks/stop/test-planenforce.py:600; check:ci-test-file-orphans reports 494 files reached, at 2ed7d6726e82098eddb62f1488670ad6e43ba872
- [x] T10. Write `.ci/scripts/quality/check_plan_implementation.py` with the `---- gate ----` header, P-A0..P-A6, and the control-first plant loop that refuses to judge the real corpus if any plant is not caught.
    (ticked) 2026-09-22T21:03:31Z by d778be9d: the gate is .ci/scripts/quality/check_plan_implementation.py:500, 20 plants driven and caught before any real judgement, at 2ed7d6726e82098eddb62f1488670ad6e43ba872
- [x] T11. Three-point wiring: `package.json` key, `scripts/ci-runner/manifest.ts` `GATES` entry with `leaves` naming both the script and its config, and the `quality-branch` step in `.github/workflows/ci-quality.yml`.
    (ticked) 2026-09-22T21:04:15Z by d778be9d: package.json key, manifest.ts entry at scripts/ci-runner/manifest.ts:1902 with one leaf matching what package.json resolves to, and the hand-written quality-branch step; check:ci-parity exit 0, at 2ed7d6726e82098eddb62f1488670ad6e43ba872
- [x] T12. Regenerate `npx tsx scripts/gen/gen-docs.ts --write`; confirm `check:ci-gate-bind`, `check:ci-parity`, `check:ci-gate-reachability-coverage`, `check:ci-test-file-orphans` and `gate-test:docs-gen` are all green.
    (ticked) 2026-09-22T21:04:13Z by d778be9d: gen-docs and gen-gates-lock regenerated; check:ci-gates-lock exit 0, check:ci-gate-bind exit 0, check:ci-parity exit 0 (347 gates, 2 workflow scopes, 9 exempt), check:ci-gate-reachability-coverage exit 0 over 337 registrations, check:ci-test-file-orphans exit 0 over 494 files, test_gate_docs_gen 6 passed
- [x] T13. Add the `plan_check` prompt-section addition to `wl_claimcheck`'s existing judge ride (3.8) -- investigation `verdict` and `note` beside the claim. No new judge call, no change to its advisory character, no change to its graduation criterion.
    (ticked) 2026-09-22T21:04:15Z by d778be9d: CLAIM_INVESTIGATION is at .claude/hooks/stop/wl_claimcheck.py:319 and rides the existing call site, no new judge call and no change to apply_verdict, at 2ed7d6726e82098eddb62f1488670ad6e43ba872
- [x] T14. Append a `TRAPS.md` entry for the lesson this plan is built on: an evidence string that satisfies a shape check is not a verification, and `.claude/hooks/stop/wl_checks.py:462` is where the shape-only branch lives. `Enforced-By: gate:check:ci-plan-implementation`.
    (ticked) 2026-09-22T21:03:32Z by d778be9d: the entry is at docs/agent-reference/TRAPS.md:1707 and check:ci-trap-registry resolves its Enforced-By pointer, floor bumped to 91 in both twins, at 2ed7d6726e82098eddb62f1488670ad6e43ba872
- [x] T15. Dogfood: run the full sequence on one real box -- `--plan-investigate`, then `--plan-tick --write` -- and record the resulting ledger row and plan diff as this plan's own first evidence.
    (ticked) 2026-09-22T21:03:32Z by d778be9d: the first real row and the resulting evidence line are at agent/plans/PLAN-plan-implementation-enforcement.md:504, written by the real CLI, at 2ed7d6726e82098eddb62f1488670ad6e43ba872

## Acceptance criteria

1. `.ci/scripts/quality/check_plan_boxes.py` exits **0** on the tree this lands on (T0), and continues to.
2. `.ci/scripts/quality/check_plan_implementation.py --selftest` catches **all ten** plants C1-C10 and exits non-zero without judging the real corpus if any one is missed.
3. On the landing commit, **both** halves are silent: the Stop hook does not emit `plan-unimplemented` and the CI gate exits 0, because `baseline_open` equals the live in-scope count on `baseline_at`.
4. On a synthetic clock one day past landing with zero boxes closed, **both** halves fire, and the CI gate's message names the count, the ceiling, and the number of ticks that close the gap.
5. `worklist.py --plan-tick` refuses `"exit 0, done, verified"` where it accepts it today, and the refusal names `completion_evidence`'s real requirement.
6. `worklist.py --plan-investigate` refuses a pointer that does not resolve, refuses two pointers of one kind, refuses an unreachable `gate:` key, and refuses a note under 40 characters -- each with its own control.
7. Clause 2 (3.6) is proven by C6: an `absent` investigation followed by a tick citing a `file:line` that already resolved at the investigation's own `head` is **refused**.
8. `wl_backlog.py` and `wl_planfile.py` are **unmodified**, and their existing never-blocks controls pass untouched.
9. No new `WORKLIST_*` environment name is introduced without a `.ci/policy/worklist-env-registry.json` entry; `check:ci-worklist-env-registry` is green.
10. `check:ci-gate-bind`, `check:ci-parity`, `check:ci-gate-reachability-coverage`, `check:ci-test-file-orphans` and `gate-test:docs-gen` are all green after T12.
11. The gate ships with **zero** allowlist, suppression or bypass entries, and `docs/agent-reference/suppressions.md` gains no row for it.
12. T15's dogfood produces one real investigation row and one real ticked box, and both are cited by `file:line` in the closing report.

## Notes for the implementer

- Read `wl_claimcheck.py`'s docstring (`:1-32`) before writing any semantic check. Its measurements are the reason this design has none, and re-deriving them costs a day.
- Read `wl_reggate.prove_new_gate` (`:544-620`) before writing the `gate:` pointer path. The hash cache at `:596-600` is what makes it affordable, and the "first sight of an untouched gate" branch at `:559-566` is the guard against a glob widening turning one stop into a sixteen-minute gate run.
- `wl_planfid.TASK_MATCH` and the token-overlap matcher in `wl_planfile.match_item` (`:245`) are **not** used by this design. The box signature (`wl_planrec.box_sig`, `:648`) is exact and is what the ledger, the record and the investigation row all speak. Do not reintroduce fuzzy matching into a blocking path.
- `--plan-tick` writes **two files** and they must land in the same commit (`.claude/hooks/stop/worklist.py:632-637`). The investigation ledger is a **third**. Say so in the success message, or `check:ci-plan-boxes` reads the ledger's staleness as a box that vanished.

### Critical Files for Implementation

- `/home/developer/console/.claude/hooks/stop/wl_planrec.py` -- `resolve` (`:326`), `plan_tick` (`:1879`), `box_sig` (`:648`), `open_boxes`/`select_box` (`:1768`/`:1786`), `TICK_EVIDENCE_MIN` (`:1764`)
- `/home/developer/console/.claude/hooks/stop/wl_checks.py` -- `completion_evidence` (`:455`), `citation_state` (`:390`), `PRIORITY_LADDER` (`:1991`), the `plan-adopted` vadd call site (`:3114-3150`)
- `/home/developer/console/.claude/hooks/stop/worklist.py` -- `--plan-tick` (`:576`), `--tick` (`:703`), `--migrate --plan` (`:975-1020`)
- `/home/developer/console/.ci/scripts/quality/check_plan_boxes.py` -- the ledger corpus, G-A0..G-A6, and the control-first shape the new gate copies
- `/home/developer/console/.ci/scripts/quality/check_hint_corpus.py` -- the worked three-point-wiring example from commit `7dd14f98f`, gate header at `:16-22`

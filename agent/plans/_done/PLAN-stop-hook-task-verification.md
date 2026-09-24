# PLAN: Stop-hook task-completion verification (claim -> citation -> tree)
Status: done
Owner: d778be9d
First-Seen: 2026-09-22

## Part 0 -- What verifies a completion claim today. Measured, not assumed.

Seven mechanisms were read in full. None of them verifies that a task marked done corresponds to a real, present change in the tree. Each is named below with what it actually asserts.

| # | Mechanism | What it proves | What it does NOT prove |
|---|---|---|---|
| 1 | `check_plan_boxes.py` `sig()` (`.ci/scripts/quality/check_plan_boxes.py:138-145`) | `sha256(_norm(task)[:120])` -- a hash of the box's own text. G-A1 asserts a box open at merge-base has a legal home at HEAD | Nothing about the tree. `transition_problems` line `:514` -- `if bsig in head_open or bsig in head_done: continue` -- ticking is the silent legitimate path, asserted by the control at `:754` ("G-A1 CONTROL: TICKING a box is silent"). The ledger row carries `status/owner/folder/moved_at/open/done/*_sigs` and no evidence field at all (verified live across all 111 rows of `.ci/config/plan-boxes.json`) |
| 2 | `check_plan_record.py` R1-R4 | A compacted record's `Full-Text-Blob` is a real blob, byte-equal to `<sha9>:<path>`, and R4 proves `done=` against `git show <sha9>:.ci/config/plan-boxes.json` | R4 proves the box was recorded as done in the ledger at that commit -- i.e. that someone ticked it and regenerated the ledger. Mechanism 1 shows that costs nothing. Record bytes recoverable is not the same as work landed |
| 3 | `wl_reggate.py` | "Is there a gate protecting this fix." Module docstring `:3-6`; `fix_signals` `:363-429` detects `^(fix|revert)[(!:]` commits and new `- [x]` ticks | Explicitly not "did the described change happen". `apply_regression_verdict:665-741` verifies the judge's claims (a named gate is a real key, a new gate is wired+green) -- never the session's claim |
| 4 | `wl_planfid.py` | Whether worklist items are a faithful decomposition of an operator-approved plan (docstring `:1-20`) | Decomposition, not completion. Its own residuals list at `:44-64` says the repo's `agent/PLAN-*.md` convention is out of scope |
| 5 | `wl_checks.plan_drift_rows:829` / `plan_records` | A plan whose session ticked/added/updated items since the plan was last written | Reads `Status:` and mtime. Reports the box's stated state |
| 6 | `wl_planfile.reconcile:267-288` | `untracked` / `stale_open` / `reopened` -- plan box state vs worklist item state | Two self-reports compared to each other. A `- [x]` box whose item is ticked is silent. Neither side is ground truth |
| 7 | `check_plan_citations.py` | Citations on added lines resolve | Its own "NOT ASSERTED" section: "Nothing here checks that the cited line SAYS what the sentence claims. That is `wl_checks.cited_excerpts`'s job and ultimately a reader's." |

The repo has already conceded this in writing. `docs/agent-reference/TRAPS.md:1553`, "A stale `Status:` header is a CLAIM; the tree is EVIDENCE", carries `Enforced-By: JUDGMENT-ONLY` and a residue that reads "No parser can know whether a plan's header describes the tree... the only refutation is measuring the code it describes." It names both directions of the failure -- "Boxes
marked open were DONE in the tree; a plan carrying `Status: executing` had its executing wave finished."

The Autopilot-App incident the operator referenced is not written down anywhere. A grep for "autopilot", "already created", "reported blocked", "false claim", "stale claim" over `docs/agent-reference/TRAPS.md` returns one unrelated hit (`:734`, a wait-loop PID trap). It is absent from every `agent/*/STATE.md` and from `agent/plans/PLAN-remove-autopilot.md`. That is itself a gap:
the incident exists only in the operator's memory and this session's context, so nothing stops its recurrence from reading as novel.

## Part 1 -- The gap, named precisely

### 1.1 The distinction the sibling fix did not cross

`agent/plans/PLAN-fix-stop-hook-completion-evidence-refire.md` (landed `e0fe455f7`) fixed scope: I7 now reads a tick's closing note (`rec["lastnote"]`) instead of its 6,084-char accumulated history, so a real sha stops being buried behind worker-id tokens. Confirmed at `.claude/hooks/stop/wl_reggate.py:372-374` and the call site `.claude/hooks/stop/wl_checks.py:2952`.

That is "the tick carries a citation, and the check looks in the right place for it." It is not "the citation, when resolved, proves the claim." The two are different problems and only the first is enforced.

Side note, an instance of the very shape this plan is about: that plan file still reads `Status: draft` with all nine task boxes `- [ ]`, though `e0fe455f7` landed the work. Exactly docs/agent-reference/TRAPS.md:1553's first direction.

### 1.2 The load-bearing finding: a documented delegation that does not exist

`.claude/hooks/stop/wl_checks.py:440-441`, `completion_evidence`'s own docstring:

> "Deliberately shape-based: whether the evidence SUPPORTS the claim is the reggate judge's question, since every new tick already flows into it."

`citation_state`'s docstring repeats it at `:374-375`: "Whether the cited text actually SUPPORTS the claim is the judge's question."

The reggate judge is never asked that question. `REGGATE_PROMPT` (`.claude/hooks/stop/worklist_messages.py:1799-1861`) asks exactly five, all about regression coverage: (0) was this found by a gate, (1) blind spot, (2) existing coverage, (3) recurrence, (4) surface. Nothing asks whether the tick's evidence supports the tick's claim. The `regression_gate` schema (`.claude/hooks/stop/wl_judge.py:79`) has no field for it.

The delegation is also false a second way: `fix_signals:397-427` emits one unit per stop, and `tick_touches_code` routes docs-only ticks to `banked_only`. So "every new tick already flows into it" is untrue for docs-only ticks and for every tick past the first on a busy stop.

This is the gap. Two independent checks point at a judge that was never given the question. Closing it is mostly a matter of actually asking, on a call that already happens.

### 1.3 A live defect in the one primitive the design depends on

`citation_state` takes one hop through a plan stub (`.claude/hooks/stop/wl_checks.py:386-390`, via `S.plan_stub_target`) so that citations written before a plan moved still resolve. `cited_excerpts` (`:400-428`) does not: it reads `pathlib.Path(root) / rel` raw at `:413` and `continue`s at `:418` when `line > len(lines)`.

Verified live:

```
citation_state('.', 'agent/PLAN-tooling-transformation.md:495')
  -> (True, 'agent/plans/PLAN-tooling-transformation.md:495')
cited_excerpts('.', 'agent/PLAN-tooling-transformation.md:495')
  -> ''            # the stub is 5 lines; line 495 is "past EOF"
```

Measured over all 342 real closing-tick notes in `agent/worklist/*.jsonl`: 186 citations resolve, and 9 of them (4.8%) hand the judge an empty excerpt. Every one is a plan-stub path. The comment at `:384` says the stub keeps 523 citations of that one path resolving.

So today, for exactly the citations that survived a plan move, the judge's "check it rather than guess" block is silently blank -- and a design that scored claims on excerpt content would read those as unsupported. This must be fixed before anything is built on top of it.

## Part 2 -- Why the naive design fails. Two measurements, both negative.

Both were run against the live corpus (342 ticks, 186 resolving citations), using the repo's own `CITE_RE`/`citation_state`/`cited_excerpts`, not a fresh regex -- the discipline `check_plan_citations.py`'s header demands. The first pass used a hand-rolled path regex and mis-parsed every `.claude/...` dotfile path, reporting 298 dead citations where the real number is 175. That
error is recorded here because it is the exact trap the gate docstrings warn about.

### 2.1 Keyword overlap between claim text and cited excerpt does not discriminate

Score = count of shared non-stopword tokens between the tick note and the cited +-4-line window, with the citation path's own tokens excluded from both sides (they match for free). Adversarial control: each note re-paired with a different tick's resolving citation -- a citation that resolves but cannot support the claim.

```
REAL  note/own-citation      n=177  median=3   score<1: 12.4%   score<2: 30.5%
ADVERSARIAL note/other-cite  n=177  median=2   score<1: 26.0%   score<2: 45.8%
```

At "score < 1 is suspect" this falsely accuses 1 in 8 genuine claims to catch 1 in 4 planted mismatches. At `<2` it is 30.5% vs 45.8%. The distributions overlap almost completely.

This kills lexical overlap as a blocking instrument, and it must not be quietly re-proposed as one. It is weak corroboration at best -- usable only as one input among several handed to a judge, never as a verdict.

### 2.2 "The cited sha touches a file the claim names" is also too noisy alone

Of 342 ticks, 191 carry no resolvable commit sha and 92 carry a sha but name no path. Of the 59 that carry both: 38 agree, 21 (36%) disagree. Inspection of the 21 shows most are legitimate -- the tick cites a sha for the code change and names a plan file it updated in a different commit. A blocker at 36% false-positive is a nagging machine.

### 2.3 What the measurements actually establish

No single mechanical test separates true from false completion claims well enough to refuse a stop. That is not a reason to build nothing; it is a reason to put the mechanical layer where it belongs -- computing corroboration and handing it to a judge that is already being paid for -- rather than letting it render verdicts it cannot support.

## Part 3 -- The design

### 3.1 The trigger: candidate (a), and only (a)

Extend the existing I7 path on the stop that already runs a fresh judge call. Weighed against the alternatives:

- (a) every worklist tick with evidence -- CHOSEN. `.claude/hooks/stop/wl_checks.py:4319`: `if not reg_signals and not audit_batch: verdict = cached_stop_verdict(...)`. When `reg_signals` is non-empty -- i.e. a tick or a fix commit -- the cache is bypassed and a fresh `run_judge` always fires. The marginal cost of asking one more question there is prompt tokens, not a model call.
  It reuses `fix_signals`' unit selection (one per stop), `reg_sig` (`:2425`), the `fixsets` settle ledger (`:4441`), `seen_ticks`, and the branch budget in `agent/reggate/*.jsonl`. Nothing new is sampled, scheduled or invented.
- (b) every plan box tick -- REJECTED for v1. `check_plan_boxes.py` runs in CI (`lane: quality-branch`), has no judge, and its ledger has nowhere to put evidence. Adding an evidence column is a schema change to a file G-A1's unforgeability depends on. Deferred to Part 3.8 as a follow-on that reuses whatever v1 proves out.
- (c) conversational prose -- OUT OF SCOPE. See 3.6.

### 3.2 What "verified" means, mechanically, per evidence shape

A new module `.claude/hooks/stop/wl_claimcheck.py` computes a corroboration profile for the one tick `fix_signals` selected. Purely mechanical, no model, bounded git calls. Shapes, in the order `completion_evidence` already enumerates them:

| Evidence shape | Mechanical test | Verdict emitted |
|---|---|---|
| `file:line` | `citation_state(root, cite)` resolves and `cited_excerpts` (stub-hop fixed, 3.4-T1) returns non-empty text | `resolved` + the excerpt text, carried into the prompt |
| `file:line` | resolves, but the cited file is not in `fixset_files(root, reg_ids)` -- the real, git-computed list the session touched | `resolved-untouched` -- the strongest mechanical mismatch available (see 3.3) |
| commit sha | `_diff_tree_files(root, sha)` (`.claude/hooks/stop/wl_reggate.py:293`) is non-empty | `commit` + the file list, basename-intersected with paths the claim names |
| run-id / exit code / URL | none available from inside the hook | `unverifiable-shape` -- stated as such, never scored as support |
| no resolvable citation | already handled by I7 | untouched. Do not re-litigate `PLAN-fix-stop-hook-completion-evidence-refire.md`: I7 owns "is there a citation" and keeps owning it. This layer only runs on ticks that already passed I7 |

The profile carries a lexical-overlap number computed as in 2.1 -- reported to the judge as a datum with its measured discrimination stated in the prompt ("overlap is weak: 12.4% of genuine claims score 0"), so the judge is not invited to treat it as proof. It is never a threshold in code.

### 3.3 The adversarial case, and the one heuristic that earns its place

The shape: a tick whose citation resolves but does not demonstrate the claim.

Constructible instance, from this tree. Item `b328b9d3` ticks with the note "Explore agent re-verified all 8 boxes live... W7P4-Q (agent/PLAN-tooling-transformation.md:495, GITHUB_AUTOPILOT_APP_ID unset)". Today: `citation_state` resolves it through the stub, `cited_excerpts` returns empty, `completion_evidence` passes on the resolving citation, I7 is silent, and the reggate judge
is never asked whether `:495` says anything about `GITHUB_AUTOPILOT_APP_ID`. Change the line number to any other in-range value and every existing check behaves identically. That is the adversarial case, live, with no fabrication required.

The detection heuristic, `resolved-untouched`. Of everything measured, one signal is both mechanical and low-noise:

> A tick claims work. Its citation resolves to `path:line`. Git says this session did not touch `path` at all -- `path` is absent from `wl_reggate.fixset_files(root, reg_ids)`, which is `_diff_tree_files` over the fix-set with a `git status --porcelain` fallback (`.claude/hooks/stop/wl_reggate.py:315-327`), and the fix-set is non-empty.

This is path equality against git's own answer, not word similarity. It has no threshold to tune. Crucially, `fixset_files` is already computed on this exact code path (`.claude/hooks/stop/wl_checks.py:4281`) and already injected into the judge prompt as `FIXSET_GROUND_TRUTH` (`.claude/hooks/stop/worklist_messages.py:1786-1797`) for the sweep/proof questions -- the plumbing exists and is used.

Its limits, named rather than implied:

1. A claim about work done in an earlier session, or in a submodule, legitimately cites a file this session did not touch. So `resolved-untouched` is a hint to the judge, never a block. `FIXSET_GROUND_TRUTH` already carries the antidote sentence for the sweep question and the same one applies here.
2. A determined false claim with a plausible citation still passes. If the session cites a file it did touch, for a change that is real but is not the claimed one, every mechanical channel agrees and only the judge -- reading the excerpt beside the claim -- can dissent. That is the honest ceiling, and it is why the judge call is not optional.
3. Lexical overlap adds almost nothing (2.1) and is reported with its own error rate attached so it cannot be over-weighted.
4. Shape-only evidence (run-id, exit code, URL) is unverifiable from inside the hook.
   A tick whose only evidence is `exit 0` yields a profile of `unverifiable-shape` and the judge is told the mechanical layer found nothing to check -- which is different from checked and found wanting, and must read differently. This is the `PLAN-fix-stop-hook-completion-evidence-refire.md` lesson generalised: a check that cannot see must say it cannot see.

### 3.4 Concretely, what changes

T1 -- fix `cited_excerpts`' stub blindness (prerequisite, standalone). `.claude/hooks/stop/wl_checks.py:413` gains the same `S.plan_stub_target` hop `citation_state:386-390` already has. Best factored as a shared `_resolve_cite_path(root, rel)` used by both, so the two cannot drift -- a second copy is the divergence this bug is. Fixes today's silently-blank judge citation block independent of
everything else. Control: the live pair from 1.3 (resolves -> non-empty), plus a non-stub path unchanged, plus a stub-pointing-at-a-stub refused (`check:ci-plan-folders` F5 forbids it).

T2 -- `wl_claimcheck.py`, following the `wl_shapedup`/`wl_classsweep` module shape exactly: `CLAIM_MARKER`, `CLAIM_SCHEMA`, `CLAIM_PROMPT`, `profile(root, evidence_text, fixset_files)` (mechanical, no model), `prompt_section(profile)`, `apply_verdict(out, profile)`.

T3 -- schema + prompt wiring. A `claim_check` object, optional at the top level, made required by `wl_judge.judge_schema_for` (`:675-698`) iff `CLAIM_MARKER` is in `extra` -- the established one-rule-per-marker pattern. Fields: `supported` (`yes`/`partial`/`no`/`unverifiable`), `why` (<=300), `instruction` (<=300).

T4 -- the call site. `wl_checks.py` around `:2952` computes the profile for the surviving tick; the section is appended to `reg_extra` near `:4290`. Failure semantics follow `wl_classsweep`/`wl_shapedup`, not `regression_gate`: a missing or malformed `claim_check` never fails closed. `.claude/hooks/stop/wl_classsweep.py:34` states the reasoning and it transfers verbatim -- the only thing this object
can do is add an advisory, so degrading loses a demand rather than granting an exit.

T5 -- the settle path, which is the whole difference between a demand and a wall. Keyed on `reg_sig`, written into `reg_state["fixsets"][reg_sig]` on the same stop (`:4441`), so an answered claim is never re-asked -- the identical mechanism that makes reggate cost-bounded. Plus a `wl_rules.Demand("claimcheck-<sig12>", ttl_min=120, max_fires=2)` latch, so even an unsettled profile
stops firing.

### 3.5 Advisory, not blocking. Decided, with reasons.

`claim_check` is advisory: `outq_add(..., prio=2)`, never `wl_rules.apply_order`, never `decision: block`. Reasons in order of weight, matching the rigor of `PLAN-stop-hook-refactor-enforcement.md` section 1.4:

1. The measurements forbid it. Section 2.1 and 2.2: the best lexical heuristic falsely accuses 12.4% of genuine claims; the best sha heuristic disagrees with 36% of real ticks. A blocking check on those numbers is a nagging machine by arithmetic. Section 2 exists so this cannot be hand-waved.
2. This session has now paid for the repeated-nag failure twice. `PLAN-fix-stop-hook-completion-evidence-refire.md` fixed a check that blocked 10+ consecutive stops with no reachable exit;
  `PLAN-stop-hook-refactor-enforcement.md` section 1.5 names "the actual lesson of the completion-evidence bug: that check re-fired forever because the finding could not be settled." Shipping a third blocker whose false-negative rate is measured at 12-36% would be remarkable.
3. A false negative here is uniquely corrosive. The subject is the session's honesty. A check that wrongly accuses a truthful session of fabricating evidence teaches it to write evidence that satisfies the checker rather than the reader -- strictly worse than not asking. `wl_planfid.py`'s docstring makes the same argument for why `wl_admit` never blocks:
  "punishing that teaches evasion; the honesty is the asset and must not be taxed."
4. The layering is already decided. I7 refuses a completion with no evidence and keeps refusing. This layer asks whether the evidence holds -- a judgement, and judgements in this hook demand rather than refuse (`wl_classsweep`, `wl_shapedup`, `wl_bravedefault` are all non-blocking by design).
5. CLAUDE.md rule 2 is not engaged. Nothing here suppresses an existing gate; I7's verdict is untouched.

"Enforcement" is still met, in the sense section 1.4 established: the message is unavoidable, arrives in the session's own context, names the tick and the citation, carries a mechanically-computed profile the session cannot deny, and a judged verdict with a concrete next step.

Graduation criterion, stated so "advisory forever" is not the silent outcome. After 30 real `claim_check` verdicts are logged, `--report` answers from the rows: if `supported: no` verdicts that the session then conceded (by re-ticking with better evidence) exceed 80% of `no` verdicts, the `resolved-untouched` arm alone graduates to `apply_order`. Write the criterion into the module
docstring, where the decision lives.

### 3.6 Scope boundary, stated plainly

This cannot and will not verify a claim made only in conversational prose.

The Stop hook can read `event["last_assistant_message"]` and a 2 MB transcript tail (`wl_core.transcript_tail:707`), and I7's `ev_tasks` arm already greps `last_msg` for a `#<id>` row (`.claude/hooks/stop/wl_checks.py:2956`). So the boundary is not "the hook is blind to prose" -- it is narrower and must be said exactly:

> The hook sees the final assistant message of a turn, and only at stop time. It cannot see a claim made mid-turn, in a sub-agent's transcript (`.claude/hooks/stop/wl_planfid.py:62-64` already records sub-agent plans as out of reach), or in a message the session later supersedes. "The GitHub Autopilot App is blocked" said in the middle of a turn, over a tracked file nobody edited and a worklist nobody ticked, leaves no artifact and is not reachable by this or any Stop-hook design.

The design therefore binds only claims that touch a tracked file, a worklist tick, or a plan box. Anything else is out of scope by construction, not by omission.

### 3.7 Budget, and how this avoids becoming the third repeated-nag incident

| Brake | Instrument | Value |
|---|---|---|
| No new model call | Rides the fresh `run_judge` that `reg_signals` already forces (`.claude/hooks/stop/wl_checks.py:4319`) | +0 calls |
| Prompt growth bounded | One tick, <=3 citations at +-4 lines (`cited_excerpts` defaults), <=40 fix-set files (`.claude/hooks/stop/wl_judge.py:735`) | ~900 chars on a fix stop that already carries ~17,700 of rubric (`.claude/hooks/stop/wl_shapedup.py:11`) |
| Never ask twice about one claim | `reg_state["fixsets"][reg_sig]` (`.claude/hooks/stop/wl_checks.py:4441`) | permanent |
| Never ask forever | `wl_rules.Demand(ttl_min=120, max_fires=2)` (`.claude/hooks/stop/wl_rules.py:133-183`) | 2 fires |
| Never displace a real violation | `outq_add(prio=2)`; drains on the allow path only | `OUTQ_PER_STOP` |
| Cannot wedge a stop | Non-blocking + `wl_classsweep` fail-open semantics (`.claude/hooks/stop/wl_classsweep.py:34`) | n/a |
| Bounded git work | `citation_state` x <=3, `_diff_tree_files` x <=3, `fixset_files` already computed | <=7 git calls |

### 3.8 Explicitly deferred

- Plan-box ticks (trigger (b)) -- after v1 has 30 logged verdicts.
- Writing the Autopilot-App incident into `docs/agent-reference/TRAPS.md`. It belongs there regardless of this plan (Part 0), and `check:ci-trap-registry`'s `TRAP_FLOOR` must be bumped with it.

## Tasks

- [x] T1a. Extract `_resolve_cite_path(root, rel)` in `.claude/hooks/stop/wl_checks.py` carrying the `S.plan_stub_target` hop currently inline at `:386-390`; call it from both `citation_state` and `cited_excerpts:413`. One definition, so the two cannot drift again.
    (ticked) 2026-09-23T11:19:19Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] T1b. Add controls to `.claude/hooks/stop/test-completion-evidence.py` (or a sibling) for the live pair: `cited_excerpts('.', 'agent/PLAN-tooling-transformation.md:495')` must return non-empty text post-fix, and a CONTROL asserting the pre-fix code returns `''`, so the fixture cannot silently stop testing anything.
    (ticked) 2026-09-23T11:19:19Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
  Plus: a non-stub path unchanged; a genuinely out-of-range line still skipped.
- [x] T1c. Re-run the 342-tick corpus measurement from section 1.3 and assert the empty-excerpt count falls from 9/186 to 0. This number is the acceptance criterion for T1. Live run against `agent/worklist/*.jsonl` (via `wl_store.load(sync=False)`, 693 closed items, 91 resolving citations): 0 empty excerpts.
    (ticked) 2026-09-23T11:19:19Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] T2. Write `.claude/hooks/stop/wl_claimcheck.py`: `CLAIM_MARKER`, `CLAIM_SCHEMA` (`supported`/`why`/`instruction`), `CLAIM_PROMPT`, `profile(root, evidence_text, fixset_files)`, `prompt_section(profile)`, `apply_verdict(out, profile)`.
    (ticked) 2026-09-23T11:19:19Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
  Module docstring must state the section 2.1/2.2 measurements, the advisory decision (section 3.5), the graduation criterion, and the scope boundary (section 3.6) -- the reasons must live where the code is.
- [x] T3. `profile()` emits per-citation verdicts `resolved` / `resolved-untouched` / `commit` / `unverifiable-shape`, using `citation_state`, the fixed `cited_excerpts`, `wl_reggate._diff_tree_files` and `wl_reggate.fixset_files`. No new regex for paths, shas or citations -- reuse `CITE_RE`, `SHA_RE`, `_EVIDENCE_PATH`.
    (ticked) 2026-09-23T11:19:19Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
  `check_plan_citations.py`'s header records why a fresh one re-opens five paid-for extension rounds; section 2's own first pass re-opened the dotfile one.
- [x] T4. `CLAIM_PROMPT` states the measured weakness of lexical overlap verbatim ("12.4% of genuine claims score 0"), carries the `FIXSET_GROUND_TRUTH`-style antidote sentence for `resolved-untouched` (work may predate this session), and asks exactly one question: does the quoted citation demonstrate the quoted claim?
    (ticked) 2026-09-23T11:19:19Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] T5. Wire `claim_check` into `wl_judge.JUDGE_SCHEMA` as optional-at-top-level, made required by `judge_schema_for` (`:675-698`) iff `CLAIM_MARKER` is in `extra`. Follow the `class_sweep`/`brave_default` precedent, not `regression_gate`'s: malformed or missing must never fail closed.
    (ticked) 2026-09-23T11:19:19Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] T6. Call site: compute the profile near `wl_checks.py` :2952 for the tick that survives `fix_signals`' unit selection; append `prompt_section` to `reg_extra` near `:4290`. Pass the already-computed `reg_fixset_files` (`:4281`) rather than recomputing.
    (ticked) 2026-09-23T11:19:19Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] T7. Settle path: record the verdict in `reg_state["fixsets"][reg_sig]` on the same stop as the reggate settle (`:4441`) so a claim is asked about exactly once; add the `wl_rules.Demand("claimcheck-<sig12>", 120, 2)` latch. Control: the same `reg_sig` on a second stop produces no prompt section at all.
    (ticked) 2026-09-23T11:19:19Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] T8. Emit via `outq_add(..., prio=2, sticky=True)`. Assert in a test that `wl_claimcheck` never calls `wl_rules.apply_order` and never returns `decision: block` -- the advisory decision pinned as code, not as a comment.
    (ticked) 2026-09-23T11:19:19Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] T9. Adversarial control, the case this exists for: a fixture tick whose citation resolves but is unrelated (the `b328b9d3` shape from section 3.3 -- a real plan path, a real in-range line, a claim about `GITHUB_AUTOPILOT_APP_ID` that the line does not mention). Assert the profile marks it `resolved-untouched` and that the prompt section fires.
    (ticked) 2026-09-23T11:19:19Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
  Pair it with a CONTROL that must NOT fire: a tick citing a file the fix-set really touched, scoring silent.
- [x] T10. Vacuity control, per `check_plan_boxes.py` G-A6 and `wl_classsweep`'s precedent: a tick with no citations, a tree where `fixset_files` is empty, and an unreadable git must each yield `unverifiable-shape` and say so, never a clean profile. A check that cannot see must report that it cannot see.
    (ticked) 2026-09-23T11:19:19Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] T11. Append a `claim_check` row per verdict to `agent/ledgers/` (the `check_plan_record.py` census precedent, `.ci/scripts/quality/check_plan_record.py:52-58`) so the section 3.5 graduation criterion is answerable from rows rather than from memory.
    (ticked) 2026-09-23T11:19:19Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] T12. Run `.claude/hooks/stop/test-completion-evidence.py`, `test-reggate-ledger.py`, `test-judge-schema.py`, `.claude/rediacc_hooks/tests/test_wl_regression_gate.py`, then `check:ci-pytest`. Confirm `test_90_ticks_are_the_uncommitted_tree_signal`'s "I7 blocks before the reggate settle" invariant is untouched -- this plan adds a layer after I7 and must not reorder it.
    (ticked) 2026-09-23T11:19:19Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
  All re-run and independently verified (not just trusted from the implementing agent's report): `test-completion-evidence.py` 4/4+4/4+stub-hop+claim-check green, `test-judge-schema.py` 418/418, `test-planrec.py` 199/199, `test-planfile.py` 130/130, `test-planindex.py` 58/58, `test-reggate-ledger.py` 19/19, `test-adhoc-watch.py` 15/15, `test-plan-status-parse.py` 22/22,
  `test-teammate-idle.py` 20/20, `test_wl_regression_gate.py`+`test_wl_idle_and_evidence.py`+`test_wl_core_blocking.py` 63/63 (includes `test_90_ticks_are_the_uncommitted_tree_signal`, passing). `ruff check`/`ruff format --check` clean on all 4 touched files. `check_prose_style.py` 0 new findings. `check_judged_rule_wiring.py` discovers `wl_claimcheck` (6 rules total, was 5).
  `check_schema_call_sites.py`, `check_dead_python.py`, `check_worklist_env_registry.py` all green.
- [x] T13. Dogfood before claiming: run the hook against the live `agent/worklist/d778be9d.jsonl` and confirm a real tick produces a profile whose excerpts are non-empty and whose `resolved-untouched` verdict matches `git status`.
    (ticked) 2026-09-23T11:19:19Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
  Tick the boxes on this plan only with that run's output as evidence -- a plan about false completion claims closing on an unverified claim would be the joke writing itself. Run against the real store: a `commit`-shaped tick (`247367f86`) profiled correctly against `_diff_tree_files`' real 4-file list; a `resolved`-shaped tick (`.claude/commands/pr-merge.md:53`) produced a
  non-empty excerpt whose text matches the claim's own subject. No `resolved-untouched` case occurred naturally in the live corpus sampled; T9's adversarial fixture covers that shape directly.

## Risks

1. It becomes the third repeated-nag incident. Mitigated by six brakes (section 3.7), the advisory decision (section 3.5), and T7's settle path -- the one thing the completion-evidence bug lacked.
2. The judge over-trusts the lexical score. Mitigated by T4 stating the error rate inside the prompt. Residual: a model may still weight a number it is told is weak.
3. `resolved-untouched` fires on legitimate cross-session citations. Mitigated by the antidote sentence and by never blocking. Measured rate unknown until T11 has rows -- that is what the census is for.
4. T1 changes `citation_state`'s shared resolver. It is called by I7, by `check_plan_citations.py` and by `completion_evidence`. T1a must be landed and run alone, with the full suite, before T2 starts.
5. Advisory forever. Mitigated by the section 3.5 graduation criterion, written into the module docstring rather than into this plan, so a reader finds it where the decision lives.

## Landed

T1 landed and verified this session (247367f86). T2-T13 landed via a dispatched Opus writer agent and independently re-verified (not merely trusted) against the tree: every test count in T12 was re-run by this session, `wl_claimcheck.py`'s functions were read against the report's claims, and T13's dogfood used real production ticks rather than the agent's own fixtures.

Five places where implementation diverged from the plan's own assumptions, each a genuine correction rather than a descope:

1. T6's two cited locations could not both be true: the plan says compute the profile "near `:2952`" while also passing `reg_fixset_files` "already computed (`:4281`)" -- that list does not exist yet at `:2952`. The profile is computed at the later call site, where `reg_fixset_files` is live.
  A plan's line-number claims about code it has not run are a hypothesis, and this is the concrete instance.
2. The advisory's own queue slot displaced a real reggate report line: a `degraded` claim-check note at `prio=2` pushed the regression gate's "settled as one-off" line out of the per-stop drain window, caught by `test_90_ticks_are_the_uncommitted_tree_signal` going red, not by review.
  Fixed by folding `yes`/`degraded` verdicts into `verdict["reason"]` instead of a queue slot, so only an actionable verdict (`resolved-untouched`, a real mismatch) takes report space.
3. No `WORKLIST_CLAIM_*` env knobs exist, unlike the sibling latches: `check:ci-worklist-env-registry` reds on any undeclared `WORKLIST_*` name, and registering one was out of this plan's scope. The latch uses fixed constants (120 min, 2 fires) instead, with the reason recorded in code.
4. The census lock lives under `TMPDIR`, not beside the ledger like the plan implied by analogy to `census-plan-record.jsonl`'s sidecar: `agent/ledgers/*.lock` has no `.gitignore` entry and none could be added within this plan's file ownership.
5. `CLAIM_PROMPT` is deliberately excluded from `rubric-calibration.json`'s hashed `SOURCES` list -- that gate's own docstring forbids hashing a rubric with no live fixtures in `calibrate-judge-rules.py`, and none exist for this prompt yet.

Two pre-existing, unrelated findings surfaced during verification and left alone, confirmed genuinely pre-existing (not touched by this session's diff): `check:ci-python-lint` red at HEAD on `S101`/`ISC004` findings in two test files last touched by `430b54ede`, weeks before this work. `check_hook_integrity.py`'s missing-from-inventory finding for `block_unsatisfiable_pid_wait.py`
(added earlier this session by unrelated work, `470475d6e`) was fixed inline as a small, local, same-session finding (`scripts/data/hook-inventory-baseline.json`), per the fix-it-in-session rule rather than left as a residual.

## Notes for the implementer

### Critical Files for Implementation

- `.claude/hooks/stop/wl_checks.py` -- `citation_state:369`, `cited_excerpts:400`, `completion_evidence:437`, I7 at `:2951-2974`, judge call at `:4365`, settle at `:4441`
- `.claude/hooks/stop/wl_reggate.py` -- `fix_signals:363`, `_diff_tree_files:293`, `fixset_files:315`, `apply_regression_verdict:665`
- `.claude/hooks/stop/wl_judge.py` -- `JUDGE_SCHEMA:79`, `judge_schema_for:675`, `run_judge:700` and its `fixset_files` grounding at `:731-740`
- `.claude/hooks/stop/worklist_messages.py` -- `FIXSET_GROUND_TRUTH:1786`, `REGGATE_PROMPT:1799`, `V_COMPLETION_*`
- `.claude/hooks/stop/wl_classsweep.py` -- the fail-open, non-blocking module template (`:34`) that `wl_claimcheck.py` must follow

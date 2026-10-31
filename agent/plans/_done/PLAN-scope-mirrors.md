# PLAN: the ci-scope-mirrors gate, a gate that keeps CLAUDE.md's PR-scope rules and their hand-written mirrors in agreement

Status: done -- 2026-10-20, every box ticked (11 of 11), merged to main with PR #600 (52a24264c)
Depends-On: no-dep -- agent/plans/PLAN-turbo-local-first.md (all boxes ticked) wrote the latest hand-mirrored sentence this gate protects
Owner: d778be9d
First-Seen: 2026-10-08
Priority: P1 -- drift is live now (findings F1-F8 below); 9ef3ab0b4 had to copy one sentence into five files by hand, and nothing checks that the copies agree
Concurrency: parallel -- the files under Owns; block_plan_concurrency refuses a writer that overlaps them
Owns: .ci/rediacc_ci/quality/scope_mirrors.py, .ci/scripts/quality/check_scope_mirrors.py, .ci/rediacc_ci/tests/test_quality_scope_mirrors.py, .ci/rediacc_ci/tests/gates/test_gate_scope_mirrors.py, .ci/config/scope-mirrors.json, .ci/config/scope-mirrors-baseline.json, CLAUDE.md, .claude/output-styles/standing-orders.md, .claude/skills/pr-epics/SKILL.md, .claude/skills/pr-epics/trailers.md, .claude/commands/pr-babysit.md, .claude/commands/pr-merge.md, .claude/agents/pr-babysitter.md, .claude/rediacc_hooks/guards/block_settled_questions.py, .claude/rediacc_hooks/tests/goldens/block_settled_questions.jsonl, agent/plans/QUEUE.md, package.json, scripts/ci-runner/manifest.ts, scripts/ci-runner/gates.lock.json, .github/workflows/ci-quality.yml, .ci/config/shards/quality-content.json, docs/agent-reference/ci-gates.md, docs/agent-reference/TRAPS.md
Worklist: #e70faed1

The line citations below were read on 2026-10-08 at 162bc9200. The design is a hypothesis about code nobody has run yet (rule 3). The writers re-check each citation, and the gate's first live run (SM4) replaces the predicted findings with measured ones.

## Why

CLAUDE.md is the only place the PR-scope rules are written down. At least seven other files restate them in their own words, and those restatements are the copies an agent actually reads while it works:

- push cadence: `CLAUDE.md:22`
- one branch, one PR: `CLAUDE.md:23`
- merge condition: `CLAUDE.md:24-25`
- one plan per PR, the plan set, a queued plan starting only when the hook names it, an epic carrying its plan, the queue switches: all in `CLAUDE.md:61`

Commit 9ef3ab0b4 shows the drift class. It added one sentence (turbo batch-end) to `CLAUDE.md:22` and copied it by hand into six places:

- `.claude/output-styles/standing-orders.md:13` (verbatim)
- `.claude/skills/pr-epics/trailers.md:37` (verbatim)
- `.claude/agents/pr-babysitter.md:101` (paraphrased into an existing sentence)
- `.claude/commands/pr-merge.md:340` (paraphrased)
- the `MESSAGE` constant at `.claude/rediacc_hooks/guards/block_settled_questions.py:108-135` (paraphrased; its golden had to be re-recorded)

That commit happened to reach every mirror. Earlier changes did not, and their misses are still in the tree. Each one below is a prediction until SM4 measures it.

| # | Where | Disagrees with | What is wrong |
|---|---|---|---|
| F1 | `.claude/output-styles/standing-orders.md:15` | `CLAUDE.md:24-25` | The merge condition reads "once every plan box is ticked and CI Complete is green". It leaves out `wl_review.py --check` and the required `Review Complete`. |
| F2 | `.claude/skills/pr-epics/SKILL.md:26` | `CLAUDE.md:61` | The plan set reads "(its `Plan:` plans and their unfinished prerequisites)". It leaves out the operator-added plans carried by `Operational-Reason:`. |
| F3 | `.claude/commands/pr-babysit.md:118` | `CLAUDE.md:61` | Same omission as F2. It also says "works one plan per PR" with no turbo branch. |
| F4 | `.claude/rediacc_hooks/guards/block_settled_questions.py:119-120` | `CLAUDE.md:54` | The quote "put the whole cluster into a single plan and ask to run it." drops the parenthetical "(root cause, siblings, ...)" without marking the cut with an ellipsis. It is a misquote. |
| F5 | `CLAUDE.md:61` (the canonical itself is behind the code) | `.claude/hooks/stop/wl_planqueue.py:92-105` `SETTINGS_KEYS` | The switch list leaves out `turbo_push`, `plan_concurrency` and `backup_push_h`. |
| F6 | `CLAUDE.md:22` (canonical behind the code) | `.claude/rediacc_hooks/guards/block_turbo_early_push.py:44` `KINDS = ("ci-cd", "red-fix", "deadline", "backup")` | CLAUDE.md says "until then only a backup push with no PR is allowed", but the guard admits four reason kinds through `TURBO_PUSH_REASON`. No mirror names `TURBO_PUSH_REASON`. `.claude/agents/pr-babysitter.md:101` says "push a red's fix at once", and under batch-end the guard refuses that push unless it carries `TURBO_PUSH_REASON='red-fix: ...'`. |
| F7 | `CLAUDE.md:24` (canonical behind the code) | `.claude/rediacc_hooks/plan_gate.py:505-506` | CLAUDE.md says `main` moves "once every plan box is ticked". In the code, `Operational-Reason:` admits the merge with open boxes. `.claude/commands/pr-merge.md:112` and `:170` already say so, which means mirror and canonical contradict each other. Checking for missing terms cannot see a contradiction (named blind spot, D9). |
| F8 (side finding) | `.claude/commands/pr-babysit.md:110` | `CLAUDE.md:5` (worktree warning) | It hard-codes `/home/muhammed/monorepo/console/.claude/agents/pr-babysitter.md`. |

The `CLAUDE.md:22-25` / `:61` rules have no gate today. The nearest siblings each check something else:

- `scripts/gates/check-merge-method-prose.ts` checks one rejected flag.
- `scripts/gates/check-directive-quotes.ts` checks NIS2 quotes against a vendored snapshot.
- `scripts/gates/check-doc-region-parity.ts` checks generated tables.

## Design

**D1. The canonical text is CLAUDE.md prose with anchors around it, not a second copy.** Each scope clause in CLAUDE.md is wrapped inline:

```
<!-- scope: pr.turbo-batch-end -->Under `turbo: on` ... fires.<!-- /scope -->
```

The sentence stays the one source and gains no duplicate. A fenced block of rule ids with their text, separate from the prose, was rejected because CLAUDE.md would then hold two copies of each rule that could drift from each other, which is the defect this gate exists to stop.

A generated region was also rejected:

- gen-docs regions emit tables only (`scripts/gate-bind.ts` aside, `renderBody` at `scripts/gates/check-doc-region-parity.ts:126-139`).
- Most mirrors weave the rule into their own sentences.
- A Python `MESSAGE` cannot carry markers without printing them to the user.

Grammar for the canonical side:

- Open: `<!-- scope: <id>[ -- <note>] -->`.
- Close: `<!-- /scope -->`. The close is required in CLAUDE.md, so a span is one sentence or clause, not a whole bullet.
- Ids match `^pr\.[a-z0-9-]{3,40}$`.
- An anchor inside a backtick code span or a fenced block is prose, not an anchor. Docs that describe the syntax must not trip the gate (TRAPS `detector-matches-its-own-prose`, `docs/agent-reference/TRAPS.md:798`).

**D2. The clauses for v1.** The atoms listed are proposals; SM4 confirms them on the real tree.

| id | canonical span | atoms (each must be a normalized substring of the canonical span) | code oracle |
|---|---|---|---|
| `pr.push-cadence` | `CLAUDE.md:22` sentence 1 | "at an epic milestone", "every 2 hours", "unpushed commits" | none |
| `pr.turbo-batch-end` | `CLAUDE.md:22` sentence 2, rewritten for F6 | `turbo: on`, `turbo_push: batch-end`, `backup_push_h`, `TURBO_PUSH_REASON` | `block_turbo_early_push.py` `KINDS`, all-in-span |
| `pr.one-branch-one-pr` | `CLAUDE.md:23` | `block_second_branch`, `block_second_open_pr` | none |
| `pr.merge-condition` | `CLAUDE.md:24-25`, rewritten for F7 | `--rebase --auto`, "CI Complete", `wl_review.py --check`, "Review Complete", `Operational-Reason:` | none |
| `pr.ff-fallback` | `CLAUDE.md:26` | `:main`, "CI Complete", `Operational-Reason:` | none |
| `pr.one-plan-per-pr` | `CLAUDE.md:61` "works one plan per PR, or with `turbo: on` a batch ..." | "one plan per PR", `turbo: on` | none |
| `pr.plan-set` | `CLAUDE.md:61` "(its `Plan:` plans, the operator-added ones ..., and their unfinished prerequisites)" | `Plan:`, `Operational-Reason:`, "unfinished prerequisites" | none |
| `pr.queued-plan-start` | `CLAUDE.md:61` "A queued plan starts only when the hook names it" | "starts only when the hook names it" | none |
| `pr.epic-carries-plan` | `CLAUDE.md:61` "An epic carries its plan ..." | `--epic <me> new --plan` | none |
| `pr.queue-switches` | `CLAUDE.md:61` switch list, rewritten for F5 | none | `wl_planqueue.py` `SETTINGS_KEYS`, equal-backticked |

**D3. The registry, `.ci/config/scope-mirrors.json`.** Per clause it holds:

- `sha`: sha256[:12] of the normalized canonical span.
- `atoms` and an optional `oracle` of the form `{path, const, rule: all-in-span|equal-backticked}`.
- `sentinels`: distinctive atoms used by the C9 scan.
- `mirrors`: a list of `{path, mode, where?}`.

`where` takes three forms:

- missing: an inline `<!-- scope: <id> -->` anchor in the mirror. In a mirror the close is optional; with no close, the span runs to the end of the block, meaning the paragraph or list item.
- `frontmatter:description`: YAML front matter, where a comment would end up inside the description string.
- `py:<CONST>`: a module-level string constant read through `ast.parse`, never imported.

The mirror map (the "Cited" column is the current location):

| path | where | clauses : mode |
|---|---|---|
| `.claude/output-styles/standing-orders.md` | `:13` | push-cadence:terms, turbo-batch-end:verbatim |
| `.claude/output-styles/standing-orders.md` | `:15` | one-branch-one-pr:terms, merge-condition:terms, ff-fallback:terms |
| `.claude/skills/pr-epics/trailers.md` | `:37` | push-cadence:terms, turbo-batch-end:verbatim |
| `.claude/skills/pr-epics/SKILL.md` | `:26` | plan-set:terms, epic-carries-plan:terms |
| `.claude/commands/pr-babysit.md` | `:60` | one-branch-one-pr:terms |
| `.claude/commands/pr-babysit.md` | `:118` | one-plan-per-pr:terms, plan-set:terms |
| `.claude/commands/pr-merge.md` | `:2` (frontmatter) and `:27` | merge-condition:terms (`:27`) |
| `.claude/commands/pr-merge.md` | `:184-188` | ff-fallback:terms |
| `.claude/commands/pr-merge.md` | `:340` | one-plan-per-pr, plan-set, queued-plan-start, epic-carries-plan, turbo-batch-end: all terms |
| `.claude/agents/pr-babysitter.md` | `:3` (frontmatter) | one-plan-per-pr:terms |
| `.claude/agents/pr-babysitter.md` | `:96` | one-plan-per-pr, plan-set, queued-plan-start: terms |
| `.claude/agents/pr-babysitter.md` | `:97` | epic-carries-plan:terms |
| `.claude/agents/pr-babysitter.md` | `:101` | turbo-batch-end:terms |
| `.claude/agents/pr-babysitter.md` | `:106` | merge-condition:terms |
| `.claude/agents/pr-babysitter.md` | `:114` | one-branch-one-pr:terms |
| `.claude/rediacc_hooks/guards/block_settled_questions.py` | `py:MESSAGE` | push-cadence:terms, turbo-batch-end:terms; the whole constant is also a quote source (D5) |
| `agent/plans/QUEUE.md` | `:3` | one-plan-per-pr:terms, turbo-batch-end:terms |

**D4. Drift is matched on anchored ids and normalized text, never fuzzy prose.** Normalization runs in this order:

1. Strip HTML comments.
2. Drop `**` and `__`.
3. Drop backticks, keeping their contents.
4. Fold smart quotes and dashes to ASCII.
5. Collapse whitespace, including the Python string's newlines and indent.
6. Casefold.

Three modes:

- `verbatim`: the normalized canonical span must be a substring of the normalized mirror span. Both turbo copies already are.
- `terms`: every atom must be a substring of the mirror span. This is a deterministic set test, chosen over similarity scoring.
- `ref`: the span must name `CLAUDE.md` or another mirror's path instead of restating the rule. It skips the atom test, and the success line prints how many ref spans exist so exemptions stay visible.

**D5. Checks**, each red message naming path:line, clause id and the fix:

| Check | Rule | Baselinable? |
|---|---|---|
| C0 floors | at least 9 clauses, at least 25 mirror checks, every clause has at least one mirror or an oracle; counts printed on success | no |
| C1 canonical anchors | each registry id is opened and closed exactly once in CLAUDE.md; no unknown id, no nesting, no unclosed anchor | no |
| C2 pin | `sha(canonical span) == registry.sha`; otherwise "canonical clause X changed: re-read its N mirrors (listed), update them, then `--repin X`" | no |
| C3 config integrity | every atom is a substring of its canonical span | no |
| C4 mirror located | an anchor, front-matter key or Python constant that is gone is red, never silently skipped | no |
| C5 verbatim | per D4 | yes |
| C6 terms | per D4 | yes |
| C7 quotes | every double-quoted fragment in a quote source, split on `...`/`…`, trailing `.,;:` stripped, must be a substring of normalized CLAUDE.md, excluding gen-docs regions (the `scripts/gates/check-directive-quotes.ts` approach, header lines 34-40) | yes |
| C8 oracle | `all-in-span`: every constant value appears in the span; `equal-backticked`: the backticked `snake_case` tokens in the span equal the constant set; read through `ast.literal_eval` on the assignment, no import | no |
| C9 unregistered restatement | a sentinel found in a block of the corpus (`CLAUDE.md`, `.claude/{commands,agents,output-styles}/*.md`, `.claude/skills/**/*.md`, `agent/plans/QUEUE.md`) with no anchor for that clause | yes |
| C10 orphan anchor | an anchor in a mirror whose (path, id) pair is not in the registry | no |

**D6. `--repin <id>|--all`** writes `sha` only when every mirror of that clause passes C5/C6 against the new canonical, or carries an already-baselined finding. It also prints the backticked tokens in the new canonical span that are not atoms, so a new code token (as `TURBO_PUSH_REASON` would have been) is a reviewed choice. A repin therefore cannot absorb drift. There is no `--force`; `scripts/lib/shrink-only-baseline.ts:30-33` explains why.

**D7. Shrink-only baseline, `.ci/config/scope-mirrors-baseline.json`.**

- Only C5, C6, C7 and C9 findings can be baselined.
- Ids are `<path>:<clause>:<check>:<sha8 of the normalized offending span>`, keyed on text and never on line numbers (`.claude/agents/gate-author.md:52-53`).
- Decisions go through `.ci/rediacc_ci/quality/shrink_only.py:22,31` (`baseline_additions`, `write_verdict`).
- `--write-baseline` refuses any growth; `--first-seed` is accepted once.
- A baselined finding that has been fixed is red until drained.
- Target: the baseline ships empty. SM5 fixes F1-F8 in this PR (rule 2). An entry is seeded only if its fix needs an operator ruling, and that entry gets a `[?]` with `DEFAULT:`.

**D8. Implementation shape.** Python, stdlib only:

- logic in `.ci/rediacc_ci/quality/scope_mirrors.py`
- by-path entry point `.ci/scripts/quality/check_scope_mirrors.py`, following `.ci/scripts/quality/check_trap_registry.py` and `.ci/scripts/quality/check_plant_proofs.py`, carrying a `---- gate ----` header: `step: PR scope rules agree with their CLAUDE.md source`, `needs: none`, `lane: quality-content`, `selftest: true`
- `derivedId` (`scripts/lib/gate-header.ts:318-326`) gives the `ci-scope-mirrors` gate
- `--root <dir>` for the gate test

Language policy puts `.ci`/`.claude` tooling in Python (`docs/agent-reference/suppressions.md`, language-policy row). The guard constants need `ast`, which TypeScript only has as `pyConst`, a single-line reader (`scripts/lib/doc-providers.ts:1494`). Controls build mutants with `rediacc_ci.controls.plant`, never a raw `.replace` (`.ci/scripts/quality/check_python_control_plants.py`). The manifest entry has no `paths:` (`.claude/agents/gate-author.md:85`).

**D9. Blind spots, named in the gate's docstring and its success line.**

- A mirror that ADDS an exception the canonical lacks, or contradicts it while still containing every atom, passes `terms`. F7 is that shape. It is fixed on the canonical side here and is not detectable later.
- The C8 code oracle covers constant tuples only. Behaviour that lives in a function body, such as `plan_merge_refusal`, is outside it.
- C9 sees only the corpus listed in C9.

**D10. Writer split** (rule 4: at most 4 writers, disjoint files; writers never commit or run regenerate scripts):

| Who | Model | Owns | Notes |
|---|---|---|---|
| W-gate | opus (the artifact is the oracle) | the four `.ci/...scope_mirrors*` files | |
| W-prose | sonnet (the oracle exists once SM1 lands) | `standing-orders.md`, `pr-epics/SKILL.md`, `pr-epics/trailers.md`, `pr-babysit.md`, `pr-merge.md`, `pr-babysitter.md`, `agent/plans/QUEUE.md` header prose only | anchors plus mirror fixes |
| Lead | | CLAUDE.md (canonical anchors and the F5/F6/F7 rewrites), `.ci/config/scope-mirrors*.json`, the `MESSAGE` in `block_settled_questions.py` plus `regolden.py`, all wiring and generators, `ci-gates.md`, `TRAPS.md` | |

W-gate and the lead's CLAUDE.md anchoring run in parallel; the D1 grammar is the contract between them.

## Tasks

- [x] **SM1 (W-gate): gate module, entry point and selftest, controls first.** Write the selftest cases and run them against a stub `check()` that returns `[]`. They must FAIL first, which proves the controls can fail. Then implement C0-C10, `--repin`, `--write-baseline`/`--first-seed` and `--root`. Fixture: a mini CLAUDE.md with 2 clauses, a registry, a verbatim mirror, a terms mirror and a `py:MESSAGE` mirror. Accept: `.ci/scripts/quality/check_scope_mirrors.py --selftest` rc 0.
    (ticked) 2026-10-08T22:17:04Z by d778be9d: commit:77e969dc8 check:ci-scope-mirrors rc=0 (65 controls, 10 clauses, 31 mirror checks); pytest 39 passed
- [x] **SM2 (W-gate): unit tests in `.ci/rediacc_ci/tests/test_quality_scope_mirrors.py`.** Normalization, the anchor parser (backtick and fence controls), the ellipsis split and the `ast` constant reader. Accept: pytest rc 0.
    (ticked) 2026-10-08T22:17:37Z by d778be9d: commit:77e969dc8 check:ci-scope-mirrors rc=0 (65 controls, 10 clauses, 31 mirror checks); pytest 39 passed; SM9 live plant rc 1
- [x] **SM3 (lead): canonical anchors and registry.** Wrap the ten D2 spans in CLAUDE.md. Write `.ci/config/scope-mirrors.json` from D3, then `--repin --all` (expected to be refused until SM5). Run the gate on the real tree and record its full findings list in this plan under `## First run`, with stdout and stderr read separately. Accept: C1, C3, C4 and C10 green; the remaining reds match F1-F8 or are added to the list.
    (ticked) 2026-10-08T22:17:39Z by d778be9d: commit:77e969dc8 check:ci-scope-mirrors rc=0 (65 controls, 10 clauses, 31 mirror checks); pytest 39 passed; SM9 live plant rc 1
- [x] **SM4 (lead): reconcile the predictions.** Each of F1-F8 is either confirmed by a finding line or struck with the reason. Any finding not predicted is added as F9 and up.
    (ticked) 2026-10-08T22:17:41Z by d778be9d: commit:77e969dc8 check:ci-scope-mirrors rc=0 (65 controls, 10 clauses, 31 mirror checks); pytest 39 passed; SM9 live plant rc 1
- [x] **SM5a (W-prose): mirror anchors and fixes.** F1, F2, F3 and F8, plus a `TURBO_PUSH_REASON='red-fix: ...'` clause in `.claude/agents/pr-babysitter.md:101` (F6). Add `<!-- scope: ... -->` anchors per the D3 map. Accept: the gate reports no C4, C5, C6 or C10 finding on these files.
  - Amended 2026-10-09 (review 41346c12.3): the Accept result is shown by the clean run itself. `npm run check:ci-scope-mirrors` on the live tree at 434b2b4e8 exits 0 with "0 baselined" and no finding line, which means no C4, C5, C6 or C10 finding on any mirror, these files included; F1, F2, F3 and F8 were each replayed on a `--root` copy at rc 1 before their fix.)
    (ticked) 2026-10-08T22:17:43Z by d778be9d: commit:77e969dc8 check:ci-scope-mirrors rc=0 (65 controls, 10 clauses, 31 mirror checks); pytest 39 passed; SM9 live plant rc 1
- [x] **SM5b (lead): canonical corrections.**
    - F5: add `turbo_push`, `plan_concurrency` and `backup_push_h` to `CLAUDE.md:61`.
    - F6: rewrite `CLAUDE.md:22` sentence 2 to name `TURBO_PUSH_REASON` and the four kinds, keeping "only a backup push opens no PR".
    - F7: `CLAUDE.md:24` names the `Operational-Reason:` exception.
    - Log F6 and F7 as DECISIONS in the round log for post-hoc veto: each documents operator-ordered code that already exists, not a new rule.
    - Then fix the mirror wording SM5a could not have known in advance, and `--repin --all`.
    (ticked) 2026-10-08T22:17:45Z by d778be9d: commit:77e969dc8 check:ci-scope-mirrors rc=0 (65 controls, 10 clauses, 31 mirror checks); pytest 39 passed; SM9 live plant rc 1

  Accept: gate rc 0.
- [x] **SM5c (lead): F4.** Fix the quote in `.claude/rediacc_hooks/guards/block_settled_questions.py:119-120` with an ellipsis. Run `regolden.py guards --reason "scope-mirrors F4: quote ellipsis"`. Accept: `pytest .claude/rediacc_hooks/tests/test_guards_differential.py -k block_settled` rc 0, and gate C7 green.
    (ticked) 2026-10-08T22:17:47Z by d778be9d: commit:77e969dc8 check:ci-scope-mirrors rc=0 (65 controls, 10 clauses, 31 mirror checks); pytest 39 passed; SM9 live plant rc 1
- [x] **SM6 (W-gate): gate test `.ci/rediacc_ci/tests/gates/test_gate_scope_mirrors.py`.** Copy the real CLAUDE.md, the mirrors, the registry and the baseline into a tmp root (no write to a tracked file: `.ci/scripts/quality/check_gate_test_real_file_plants.py`), then run the entry point with `--root`. Controls:
    - **T1 untouched:** rc 0, and the printed counts are at or above the floors.
    - **T2 the 9ef3ab0b4 miss, replayed:** delete the turbo sentence from the tmp `trailers.md` only. Expect rc 1 with a finding naming `.claude/skills/pr-epics/trailers.md` and `pr.turbo-batch-end`, and NO finding naming `standing-orders.md`, `pr-babysitter.md` or `pr-merge.md` (an untouched mirror stays silent).
    - **T3 canonical edited, mirrors not:** append a clause to the tmp CLAUDE.md `pr.plan-set` span. Expect rc 1, C2 naming the clause, and zero C5/C6 lines.
    - **T4 terms drift:** remove `Operational-Reason:` from the tmp `.claude/agents/pr-babysitter.md:96` span. Expect rc 1 with C6 naming that file only.
    - **T5 quote drift:** change one word inside a tmp `MESSAGE` quote. Expect C7. With the change written as `...`, expect silence.
    - **T6 anchor deleted:** expect C4, not silence.
    - **T7 oracle:** add a value to the tmp `KINDS`. Expect C8.
    - **T8 unregistered restatement:** add a paragraph with `turbo_push: batch-end` to a tmp `.claude/commands/handoff.md`. Expect C9. With `<!-- scope: pr.turbo-batch-end -->` added but no registry row, expect C10 instead.
    - **T9 repin refuses while T2's plant is in place;** after the plant is reverted, repin is allowed.
    - **T10 baseline:** a growth write is refused; a drain is allowed.
  - Amended 2026-10-09 (review 41346c12.2): `.ci/rediacc_ci/tests/gates/test_gate_scope_mirrors.py` holds T1-T10 plus the empty-tree case, 11 tests, each plant on a temp copy; all pass in the 39-test run. With the gate's C5 and C9 checks disabled, all 11 go red. Since b8c817aca, T1 holds each floor equal to its measured count.)
    (ticked) 2026-10-08T22:17:49Z by d778be9d: commit:77e969dc8 check:ci-scope-mirrors rc=0 (65 controls, 10 clauses, 31 mirror checks); pytest 39 passed; SM9 live plant rc 1
- [x] **SM7 (lead): wiring.**
    1. package.json: `"the ci-scope-mirrors gate": ".ci/scripts/quality/check_scope_mirrors.py"` (the bare path, per `scripts/gate-bind.ts` header lines 5-8).
    2. A `scripts/ci-runner/manifest.ts` entry: `gate: true`, leaves set to the entry point, `ci.step` equal to the header step, job `quality-content`, no `paths`.
    3. `npm run gate:bind -- --dry-run`, read the diff, then `--write`. The step lands in the quality-content region at `.github/workflows/ci-quality.yml:1404`.
    4. `npm run gen:gates-lock`, then `npx tsx scripts/gen/gen-docs.ts --write`.
    (ticked) 2026-10-08T22:17:51Z by d778be9d: commit:77e969dc8 check:ci-scope-mirrors rc=0 (65 controls, 10 clauses, 31 mirror checks); pytest 39 passed; SM9 live plant rc 1

  Accept: `npm run check:ci-parity`, `npm run check:ci-gate-bind`, `npm run check:ci-gates-lock`, `.ci/scripts/quality/check_gate_reachability_coverage.py`, and `npm run ci -- --quick --list | grep scope-mirrors` all rc 0 or hit.
- [x] **SM8 (lead): documentation.**
    - `docs/agent-reference/ci-gates.md` gets a quick-fix row: "C2 red: edit the mirrors it lists, then `--repin <id>`; never repin first".
    - A TRAPS entry "a rule mirrored by hand drifts in the copy nobody re-reads", with `Trap-Id: hand-mirrored-rule-drift` and `Enforced-By: gate:the ci-scope-mirrors gate`, so `check:ci-trap-registry` F4/F5 prove the gate is live.
    (ticked) 2026-10-08T22:17:52Z by d778be9d: commit:77e969dc8 check:ci-scope-mirrors rc=0 (65 controls, 10 clauses, 31 mirror checks); pytest 39 passed; SM9 live plant rc 1

  Accept: both gates rc 0.
- [x] **SM9: live plant proof on the real tree, two passes in one script (TRAPS `mutation-needs-both-directions`, `docs/agent-reference/TRAPS.md:230`).** Pass 1: `npm run the ci-scope-mirrors gate` rc 0 on the clean tree. Pass 2: the T2 plant applied to a copy with `--root` gives rc 1, and the stderr line names the trailers mirror. Tick with both exit codes.
  - Amended 2026-10-09 (review 41346c12.1): pass 1 on the clean tree exits 0; pass 2, the T2 plant on a `--root` copy, exits 1 with the stderr line `✗ C5 .claude/skills/pr-epics/trailers.md:37 [pr.turbo-batch-end] verbatim mirror no longer contains the canonical text of CLAUDE.md:22`.)
    (ticked) 2026-10-08T22:17:54Z by d778be9d: commit:77e969dc8 check:ci-scope-mirrors rc=0 (65 controls, 10 clauses, 31 mirror checks); pytest 39 passed; SM9 live plant rc 1

## First run

Measured 2026-10-08 in a scratch clone of 956c6cfd3. Stdout and stderr were read separately on every run.

**Run 0: CLAUDE.md anchored, registry unpinned, mirrors untouched.** rc 1, 72 findings. Every one of the 31 registered mirror spans was C4, because no mirror was anchored yet. Each of the ten clauses was C2 (unpinned). C7 at `.claude/rediacc_hooks/guards/block_settled_questions.py:174` was F4. C9 named every unanchored restatement, plus the side hits listed as F9 and F10 below.

**Run 1: mirrors anchored and fixed, `--repin --all`.** rc 0, all 10 clauses repinned. The gate printed rc 0: `10 clauses (floor 10), 31 mirror checks (floor 31) over 31 spans (2 verbatim, 29 terms, 0 ref), 6 quote fragments from 1 source(s), 2 oracle(s), C9 swept 51 files / 3670 blocks, 0 baselined`.

**Predictions, each replayed.** The pre-fix text was planted into a `--root` copy of the fixed tree, with the anchors kept, and the gate's own finding was read (rc 1 on every replay):

- **F1, confirmed and wider.** `C6 .claude/output-styles/standing-orders.md:15 [pr.merge-condition]` was missing `wl_review.py --check`, Review Complete and `Operational-Reason:`. The same line also missed the fallback's conditions: `[pr.ff-fallback]` was missing `:main`, CI Complete and `Operational-Reason:`.
- **F2, confirmed.** `C6 .claude/skills/pr-epics/SKILL.md:26 [pr.plan-set]` was missing `Operational-Reason:`.
- **F3, confirmed.** `C6 .claude/commands/pr-babysit.md:118`: `[pr.one-plan-per-pr]` was missing `turbo: on`, and `[pr.plan-set]` was missing `Operational-Reason:`.
- **F4, confirmed.** `C7 .claude/rediacc_hooks/guards/block_settled_questions.py:175 [quote]` quoted CLAUDE.md as "put the whole cluster into a single plan and ask to run it", which it does not say. The quote now reads `single plan ... and ask`. The golden was re-recorded: 18 records changed, `err` only, 0 rc changes.
- **F5, confirmed.** `C8 CLAUDE.md:61 [pr.queue-switches]`: the backticked keys differ from `SETTINGS_KEYS` at `.claude/hooks/stop/wl_planqueue.py:101`, missing `backup_push_h`, `plan_concurrency` and `turbo_push`.
- **F6, confirmed on both sides.** Canonical: `C8 CLAUDE.md:22 [pr.turbo-batch-end]`, the span lacks the `KINDS` values ci-cd, deadline and red-fix from `.claude/rediacc_hooks/guards/block_turbo_early_push.py:46`. Mirror: `C6 .claude/agents/pr-babysitter.md:101 [pr.turbo-batch-end]` was missing `TURBO_PUSH_REASON`. CLAUDE.md:22 now names the guard, `TURBO_PUSH_REASON` and the four kinds, and keeps the rule that a `backup` push opens no PR. Turbo has been off since the operator's ruling of 2026-10-08; the sentence still describes the setting. DECISION for post-hoc veto: it documents operator-ordered code that already exists, and adds no new rule.
- **F7, confirmed in the code, and undetectable as predicted (D9).** In `.claude/rediacc_hooks/plan_gate.py`, `plan_merge_refusal` returns "" on `has_operational_reason` before any box is read. The canonical now names the exception, so `Operational-Reason:` is a merge-condition atom: replaying the old canonical gives C3 (atom not in span) plus C2, and a mirror that drops it gives `C6 .claude/agents/pr-babysitter.md:106 [pr.merge-condition]`. DECISION for post-hoc veto, for the same reason as F6.
- **F8, confirmed by reading; outside the gate.** `.claude/commands/pr-babysit.md:110` hard-coded `/home/muhammed/monorepo/console/.claude/agents/pr-babysitter.md` and now reads `.claude/agents/pr-babysitter.md`. The gate does not check paths, so this was a fix by hand.
- **F9 (new), gate configuration.** The proposed sentinel "fast-forward fallback" fired C9 on five REFERENCES to the fallback in `/pr-merge`: `.claude/agents/pr-babysitter.md:131,158,227`, `.claude/commands/pr-babysit.md:106` and `.claude/commands/pr-merge.md:262`. None of them restates its conditions. The sentinels were narrowed to phrases that only a restatement carries, each measured over the corpus before it was chosen: "one direct push", "works one plan per PR", "one plan per PR, or", "An epic carries its plan", and the batch-end key in its "(the default)" form, so that the QUEUE.md `## Settings` key docs (lines 20 and 30, outside the one line this plan edits there) are not read as restatements. `pr.merge-condition` has no sentinel: `wl_review.py --check` appears in 12 corpus blocks that are finish-line instructions, not restatements.
- **F10 (new), a gate parser defect, fixed.** `md_blocks` read a CommonMark indented code block as prose, and C9 called the `worklist.py --epic <me> new --plan` listing at `.claude/skills/pr-epics/SKILL.md:20` a restatement. A block indented four spaces is now code when it opens after a blank line or a heading outside a list. Selftest controls cover both directions, and the indented-code control was seen to FAIL with the fix switched off.

Also fixed on the way, unpredicted: the entry point `.ci/scripts/quality/check_scope_mirrors.py` had no exec bit. package.json invokes it by bare path, and the SM6 gate test refused it (`gate not executable`). Its mode is now 100755.

## Risks

- **Other sessions editing rule 1 hit C2 at once.** That is the purpose. The red message must list every mirror as path:line plus the repin command, so a reader who has never seen this plan can act on it.
- **Anchors in CLAUDE.md cost about 300 bytes of prompt.** That is accepted. Front-matter and Python mirrors carry no anchors (D3).
- **`gate:bind --write` rewrites every region.** The header at `scripts/gate-bind.ts:2595` records duplicate emission happening twice. Run `--dry-run` first.

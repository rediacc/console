# PLAN: route the cheap-tier work to Haiku, by task shape

Status: phase 0-1 done, phase 2 (calibration batch) next
Owner: d778be9d
First-Seen: 2026-09-22
Operator ask: "we burn a lot of tokens with stop hook... investigate where we can use haiku model for sub-agents. Which task categories and which languages are better to leverage haiku... implement planned changes to encourage haiku model wherever possible. I suppose python and typescript could be the targets but not limited to them." <!-- style-ok -->

Designed by a read-only Plan subagent. Every path/line below was opened and read.

## 0. Two premises the operator's framing carried, both corrected before designing

**The Stop hook is not the cost.** `.claude/hooks/stop/wl_judge.py:23` already pins `claude-haiku-4-5-20251001`, on measurement rather than taste (`.claude/hooks/stop/wl_judge.py:24`: haiku $0.011-$0.026/call warm vs sonnet $0.231 for the same judgement). The judge fires only when work genuinely remains open, and `.claude/hooks/stop/wl_judge.py:36` caches only clean "stop" verdicts
-- so a long run with open items pays fresh for every "continue". That is the design working, not a leak. **No change proposed to the judge.** The perceived cost is the session and its subagents, which the judge merely bookends.

**"Python and TypeScript" is not the axis.** Surveying `git log --oneline -100`, the dominant class is `refactor(ci): N bash twins port to Python/pytest` (`7a9bda6d7` -- 97 bash gate tests ported; `e812c74e1` -- 8 more; `62599afc0`, `2e50af60a`, `1ea0c7340`, `02dc20665`, `4ee160b3b`, and a dozen siblings). Python is where those land; it is a property of this quarter's migration
campaign, not of the work's difficulty. `36dd93635` also lands in Python and is the hardest judgment call in the last hundred commits. **The axis is task shape. Language is noise.**

## 1. The decision rule

**Choose the model by the shape of the task, never by its language or its domain.**

**Haiku** when all three hold:
1. **Derived, not invented.** The output is a transformation of an artifact that already exists -- a port, a translation, a mechanical sweep, a rename, or a read-only survey of what is already in the tree.
2. **A pre-existing oracle decides correctness**, without a human reading the diff: a K=5 shadow ledger, a golden differential, a gate that already fails on the old artifact, ruff/gofmt/prettier, or -- for read-only work -- the requirement that every claim arrive as a `file:line` the caller can open.
3. **Being wrong is loud.** The failure mode is a red check, not a silent gap.

**Opus** when the artifact created *is* the oracle. New guards, new gates, threat models, schema design, and multi-file planning have no pre-existing thing to be checked against; their correctness is "did the author think of the right cases", which no gate can ask. Also Opus for anything adversarial or closed-world ("every way an agent could spell this").

**Sonnet is an escalation tier, not a default.** The one sanctioned use is `docs/i18n/CONVENTIONS.md:30` -- a named language whose Haiku naturalization reads awkward by the judge's `naturalness` score. Nothing else defaults to Sonnet.

**The load-bearing caveat, which must not be dropped when this rule is quoted:** the oracle is what makes a cheap model safe, not the model. Condition 2 is not a nice-to-have that a confident session may waive. This repo's anti-vacuity discipline proves "this gate can fail given the code as written"; it cannot prove "the author thought of the right threat model."
`.claude/rediacc_hooks/guards/block_push_to_protected_branch.py` is the worked counter-example: its header enumerates nine spellings of a dangerous push and then documents, in the same breath, a tenth it deliberately does not close. No oracle existed to notice the gap; a person reasoning adversarially did. A design gap ships silently. A bad port does not.

### 1a. Where the rule lives

Both, in this repo's established split:

- **`CLAUDE.md:134`** -- replace the current one-liner (`Opus for code and design, Sonnet for translation and naturalization`) with a three-line shape rule plus a pointer. It sits inside rule 4, "Reach for subagents" (`CLAUDE.md:122`), which is where a session is already reading when it dispatches.
- **`docs/agent-reference/model-routing.md`** (new) -- the full rule, the oracle caveat, the worked examples from section 5, and the measurement table from section 6.

This matches eight existing precedents in CLAUDE.md of the form "**[docs/agent-reference/X.md](...)** carries the rest" (`CLAUDE.md:189`, `:203`, `:241`, `:247`, `:253`, `:264`, `:270`, `:272`). **Not generated from one another** -- no generator produces agent-reference prose, and inventing one for two files is not worth a new failure mode. The proposed `ci-agent-model-roster` gate in
section 4 is what keeps them from drifting.

**Wiring note:** after adding the doc, run `npx tsx scripts/gen/gen-docs.ts --write` and confirm `npx tsx scripts/gen/gen-docs.ts` (verify mode) exits 0 -- `scripts/data/doc-registry.md` is generated and may need the new file's row. Do not hand-edit it.

## 2. The 13 `subagent_type` definitions: zero frontmatter changes

All 13 declare `model:` in frontmatter. Twelve are `opus`; only `.claude/agents/test-advisor.md:5` is `haiku`.

**Recommendation: change none of them.** This is a deliberate call, not timidity, and the reason is structural: a `subagent_type` here is defined by DOMAIN. The model is decided by SHAPE. A domain spans both shapes, so frontmatter is the wrong place to encode a shape rule.

`i18n-guardian` covers both a 12-locale mechanical sweep (gates are the oracle, Haiku) and diagnosing why a cross-locale gate fired (judgment, Opus). `gate-author` covers both writing a brand-new anti-vacuity gate (the artifact is the oracle, Opus) and porting an existing bash gate-test to pytest (case-for-case differential, Haiku). Flipping either file's frontmatter would be wrong
half the time, in whichever direction it was flipped.

`test-advisor` is the exception that proves the rule, and is why it should stay `haiku`: its domain is a bounded classification ("which of six CI surfaces does this belong on"), so its shape is constant and a frontmatter default is meaningful. It is the template for any future agent that earns a Haiku default -- constant shape, not cheap subject matter.

**The mechanism for the Haiku slice is the per-call `model` override**, for which precedent already exists at `.claude/agents/pr-babysitter.md:142` ("Cheap tiers for mechanical bulk is the point"). Three agent bodies get a short `## Model` section documenting their own split, so a session dispatching them does not have to re-derive it:

| file | change | rationale |
|---|---|---|
| `.claude/agents/gate-author.md` | add `## Model` section: new gate design -> session default (Opus); porting an existing gate/gate-test with a case-for-case differential -> `model: haiku` override | this agent's two modes are the plan's two poles |
| `.claude/agents/i18n-guardian.md` | rewrite `## Model choice` (line 77) per section 3, and state that locale sweeps run Haiku while gate-failure diagnosis runs the session default | also fixes the stale note |
| `.claude/agents/pr-babysitter.md:142` | change `mechanical sweeps, doc/format churn -> **Sonnet** worker` to **Haiku**, keeping Sonnet named only as the escalation tier | highest-volume win; gated on section 6, see ordering |

The other ten agent files are untouched.

### 2a. The larger win is not in these 13 files at all

`CLAUDE.md:126` already instructs "Investigate with them by default... run several at once. Ask each for conclusions with `file:line` evidence, never file dumps." Those `Explore` / `general-purpose` dispatches have no frontmatter and no declared model, and by volume they dwarf the 13 domain agents. They also satisfy all three Haiku conditions cleanly -- derived (the tree already
contains the answer), oracled (`file:line` evidence is checkable by the caller, and `CLAUDE.md:115` already requires spot-checking), and loud (a bad citation fails to resolve). Making read-only fan-out default to Haiku is the single highest-leverage line in this plan, and it is a CLAUDE.md edit, not an agent-file edit.

## 3. The i18n conflict: the investigation's premise is inverted

The brief asked for a choice between "change reality to Haiku" and "fix the docs to say Sonnet." Neither. The reality is already Haiku and the docs that say so are correct.

Read directly:

- `packages/www/src/i18n/translations/.naturalized-hashes.json` `$meta.models` records `claude-haiku-4-5` for all twelve languages. Not sonnet.
- `.claude/agents/i18n-guardian.md:79` asserts "The ledger's `$meta.models` recording `claude-sonnet-5` across all twelve languages is DELIBERATE, not drift... Do not 'fix' it back." That sentence is false about the tree as it stands today.
- History explains it without ambiguity.
The note landed in `f7a5351a9` (2026-08-18), when the ledger genuinely did read `claude-sonnet-5`. `b3a23cc36` (2026-08-19) and `b8de2f586` (2026-08-20) then migrated every language back to `claude-haiku-4-5` -- `b8de2f586`'s own diff flips the last five (`pt`, `ru`, `zh`, `ja`, `ko`). The migration happened after the note and the note was never updated.
- `docs/i18n/CONVENTIONS.md:26` ("Model: use haiku (cheapest) -- IMPORTANT for cost") and `CLAUDE.md:195` are therefore accurate, not stale.

So there is no policy conflict to adjudicate -- there is one stale sentence contradicting the artifact it describes. The reason it went unnoticed is worth recording: `scripts/gates/check-naturalization-model-policy.ts:51` permits `['haiku', 'sonnet', 'opus']` as a family set, so both the old sonnet ledger and the current haiku ledger are green. The gate was built to catch a vendor
drift (`registry.py` silently running `kimi`, per its header) and correctly does not adjudicate between the three sanctioned families.

**This finding also strengthens the whole plan:** twelve languages of production marketing copy have been naturalized on Haiku for a month, through a shrink-only contamination baseline, cross-locale detection, and de-contamination gates, with no quality rollback. That is the strongest empirical evidence in the tree that Haiku plus a real oracle works, and it is the precedent the
section 6 acceptance criterion should be measured against.

### Exact edits

- **`.claude/agents/i18n-guardian.md:77-79`** -- replace the `## Model choice` section with the true statement: haiku across all twelve, matching `docs/i18n/CONVENTIONS.md:26` and `CLAUDE.md:195`; note that sonnet appeared in the ledger between `f7a5351a9` and `b8de2f586` and was migrated back; keep the "do not flip this casually" energy but attach it to the correct model.
Preserve the `$meta.models` pointer -- that is the part a session needs.
- **`agent/programs/www-simplification/research/01-SYNTHESIS.md:208,449`** and **`agent/programs/www-simplification/research/RESEARCH-i18n-ci.md:157,459`** -- leave untouched.
These are dated research records, and this repo freezes a record once written (the same convention `agent/plans/PLAN-remove-autopilot.md` applies to `docs/ci-overhaul/06-progress.md`). They were accurate on the day they were written. Rewriting them falsifies the history that explains the stale note. The new `docs/agent-reference/model-routing.md` carries one line noting the 2026-08
sonnet interlude and its resolution, which is where a future reader should land.
- **No change** to `CLAUDE.md:195`, `docs/i18n/CONVENTIONS.md`, the ledger, or `scripts/gates/check-naturalization-model-policy.ts`.

## 4. The new gate: yes, but not the one that was proposed

**Rejected: a gate that infers task shape from an agent's prose and flags drift from Opus/Haiku/Sonnet convention.** It cannot have an honest control.
A planted defect would have to be "an agent whose description implies the wrong shape", and shape-from-prose is precisely the judgment call the rule exists to have a human make. A gate that cannot state what a planted defect looks like is a gate that cannot fail, which `.claude/agents/gate-author.md`'s own anti-vacuity discipline forbids. Building it would manufacture a green that
means nothing.

**Recommended instead: a new gate named `ci-agent-model-roster`**, a small keyset gate in the spirit of `.ci/scripts/quality/check_agent_hint_liveness.py` (which already scans `.claude/agents/*.md` and asserts a specimen keyset equals the agent-file set in both directions) and of `scripts/gates/check-naturalization-model-policy.ts` (which "deliberately does NOT adjudicate which model is
best... the gate only insists the change be made ON PURPOSE, in CLAUDE.md and here together"). Same bargain, applied to the agent roster:

1. Every `.claude/agents/*.md` declares a `model:` whose family is in `{opus, haiku, sonnet}` -- a version bump within a family passes, a change of family or vendor does not (copy the family-matching approach at `scripts/gates/check-naturalization-model-policy.ts:51`).
2. **Every agent declaring a non-`opus` model must be named, by filename, in `docs/agent-reference/model-routing.md`, with a reason.** This is the load-bearing half. It does not judge whether `haiku` is right for `test-advisor`; it insists that flipping any agent to a cheap tier leaves a written reason behind, in the same commit.
3. The doc's named set must not contain agents that no longer exist or that have reverted to `opus` -- keyset equality in both directions, exactly as `.ci/scripts/quality/check_agent_hint_liveness.py` does for specimens.

Controls (all plantable in a `tempfile` fixture, following `.ci/scripts/quality/check_agent_hint_liveness.py:213-230`'s `write_agent` helper): an agent with `model: gpt-4` is reported; an agent with `model: haiku` absent from the doc is reported; a doc entry for a deleted agent is reported; a doc entry for an agent that reverted to opus is reported; and the real roster as it stands
is not. If any planted defect passes, the gate declares itself broken and exits non-zero without a verdict.

Roughly 150 lines. **Three-point wiring is mandatory** per `.claude/agents/gate-author.md` -- `package.json` key, `scripts/ci-runner/manifest.ts` GateSpec, and a workflow step or an explicit `kind: 'test'` ride -- then regenerate `scripts/ci-runner/gates.lock.json` with `npx tsx scripts/gen/gen-gates-lock.ts --write` and verify with the no-flag invocation. `check:ci-parity` and
`check:ci-gate-reachability-coverage` will catch a two-point wiring.

**Note the irony and respect it:** this new gate is itself a section-1 "Opus" task -- the artifact is the oracle, there is no pre-existing differential. Do not dispatch it to Haiku.

## 5. Worked examples

Three real patterns from this session, with the call a future session should make.

**(a) Port another bash gate-test to pytest** -- the `e812c74e1` / `7a9bda6d7` shape, of which dozens remain.

    Agent(subagent_type="gate-author", model="haiku",
          description="Port check-X.sh's cases to test_gate_x.py",
          prompt="Port .ci/scripts/test/gates/check-X.sh to
                  .ci/rediacc_ci/tests/gates/test_gate_x.py. Verify case-for-case
                  against the twin BEFORE the twin is deleted. You own exactly those
                  two paths. Acceptance: pytest green on the new file, and the
                  case count matches the twin's. Do not commit or push.")

Derived (the twin exists), oracled (case-for-case differential, and `check:ci-dead-bash` / `check:ci-parity` catch the wiring), loud (red pytest). All three conditions. **Haiku.** Note the frontmatter stays `opus` -- the override carries the slice.

**(b) Write a new hook guard** -- the `36dd93635` shape.

    Agent(subagent_type="gate-author",
          description="New guard: block <dangerous class> from the Bash tool",
          prompt="...")   # no model override -- session default, Opus

Invented, not derived. The guard is the oracle. Correctness is "did every spelling get enumerated", and `block_push_to_protected_branch.py`'s header shows what that costs: nine spellings enumerated, plus an honest note about a tenth gap left open on purpose. **Opus.** Never delegate this class down, however mechanical the final diff looks.

**(c) Read-only survey** -- the highest-volume class, per section 2a.

    Agent(subagent_type="Explore", model="haiku",
          description="Find every caller of X",
          prompt="Report every call site of X as file:line with one line of context.
                  Conclusions only, no file dumps. If a claim has no file:line,
                  omit it.")

Derived, oracled (every citation resolves or it does not), loud. **Haiku.** The `file:line`-only contract is not style here, it is condition 2, and it is what makes the cheap tier safe.

**(d) The borderline call, stated so it is not re-litigated:** re-naturalize 12 locales after an English key change -> **Haiku**. It looks like creative writing, which is why instinct reaches for a bigger model, but the i18n gate battery (completeness, cross-locale, de-contamination, interpolation-consistency, no-untranslated-values) is a genuine pre-existing oracle, and section 3
establishes that twelve languages have shipped this way for a month. Escalate a single named language to Sonnet only on a low `naturalness` score, per `docs/i18n/CONVENTIONS.md:30`.

## 6. Rollout order and acceptance

**Yes, calibrate before trusting the wider rollout**, following `.claude/hooks/stop/calibrate-judge-rules.py`: a hand-run, opt-in, real-fixture harness that costs money and is not a CI gate, whose header states the discipline exactly ("does haiku, reading a real session message, actually recognise...? That needs the model, a network, and about two cents a case, which is exactly
what a CI gate must not need").

**But measure the right variable.** For an oracle-backed port, "is the output correct" is already answered by the oracle -- a wrong port is red. The real risk of a cheap model here is rounds: if a Haiku worker needs four correction cycles where Opus needed one, the orchestrating session pays the difference in its own expensive context and the saving inverts. That, not correctness,
is what the calibration batch must measure.

### Acceptance criterion

Take the next 5 bash-to-pytest gate-test ports (the section 5(a) class, the most plentiful remaining work). Dispatch each to a Haiku worker under the section 5(a) contract. Record per port, in a dated table in `docs/agent-reference/model-routing.md`: worker model, correction rounds to oracle-green, wall-clock, and worker cost.

Haiku is accepted for this class if all of:

- [ ] >=4 of 5 reached oracle-green within <=2 correction rounds.
- [ ] Zero required an Opus takeover (a worker that had to be abandoned and redone is a failure regardless of rounds).
- [ ] Zero produced a case-count regression against the bash twin that the differential did not catch -- i.e. no port was green and short of cases. This is the one that would falsify the whole oracle premise, and it is worth checking by hand on all five.
- [ ] Measured end-to-end cost (worker + orchestrator correction rounds) is below 50% of the Opus median for the same class.

If it fails, the honest outcome is narrowing, not abandonment: keep Haiku for section 5(c) read-only surveys (where the evidence contract is stronger and the blast radius is a wasted dispatch) and revert 5(a) to the session default. Record the result either way -- a negative result in that table is worth as much as a positive one, and it is what stops the next session re-running
this experiment from scratch.

The table lives beside the rule for the same reason `.claude/hooks/stop/wl_judge.py:24` keeps its measurement inline with `JUDGE_MODEL`: a model choice with its measurement attached survives a rewrite; one without it gets re-litigated on taste.

### Ordering

1. **Phase 0, doc-only, zero risk, no behavior change.** `CLAUDE.md:134` rewrite + pointer; new `docs/agent-reference/model-routing.md`; `gen-docs.ts --write` and verify. Ships alone.
2. **Phase 1, the stale i18n note.** Section 3's `.claude/agents/i18n-guardian.md:77-79` rewrite. Independent of everything else; can ride phase 0's commit.
3. **Phase 2, the calibration batch.** Section 6's five ports, hand-run, results recorded. Blocks phases 3 and 4. No further routing changes until this table exists.
4. **Phase 3, the roster gate.** The new `ci-agent-model-roster` gate plus three-point wiring and `gates.lock.json` regeneration. After phase 0, because the gate asserts against the doc phase 0 creates. Dispatch to Opus (section 4).
5. **Phase 4, the pr-babysitter flip, only if phase 2 passed.** `.claude/agents/pr-babysitter.md:142` Sonnet -> Haiku for mechanical sweeps and doc/format churn, Sonnet retained as the named escalation tier. This is the highest-volume change in the plan and the one with real downside if the calibration disappoints, so it goes last and is conditional.
6. **Phase 5, the three agent-body `## Model` sections** (section 2's table, minus `.claude/agents/pr-babysitter.md:142` which phase 4 owns). Cosmetic once the doc exists; batch with phase 4.

## 7. Explicitly out of scope

- **The Stop-hook judge.** Already Haiku (`.claude/hooks/stop/wl_judge.py:23`), on measurement. Section 0.
- **Autopilot's dispatcher.** `.ci/rediacc_ci/autopilot/autopilot_gate.py` `DEFAULT_MODEL = "claude-sonnet-5"` / `MODEL_ALLOWED = "claude-sonnet-5,claude-opus-5"` is a `claude-code-action@` GitHub Actions workflow input, a different mechanism from the `Agent` tool this plan governs.
Beyond that, `agent/plans/PLAN-remove-autopilot.md` deletes the entire `.ci/rediacc_ci/autopilot/` tree; editing those constants now creates a merge conflict against that removal in exchange for nothing. **Touch no Autopilot file.**
- **`scripts/gates/check-naturalization-model-policy.ts`.** Its permissive `{haiku, sonnet, opus}` family set is correct for its purpose (catching vendor drift). Narrowing it to haiku-only would red the tree on any sanctioned per-language escalation that `docs/i18n/CONVENTIONS.md:30` explicitly allows.
- **The naturalized ledger and the 12 locale files.** Already Haiku. Nothing to migrate.
- **`agent/programs/www-simplification/research/*`.** Frozen records. Section 3.

## 8. Tasks

- [x] Rewrite `CLAUDE.md:134` as the shape rule + pointer to the new doc.
- [x] Write `docs/agent-reference/model-routing.md` (rule, oracle caveat, section 5 examples, the 2026-08 i18n sonnet interlude note, and the empty measurement table phase 2 fills).
- [x] Add the read-only-fan-out-defaults-to-Haiku line to `CLAUDE.md:126`'s bullet (section 2a).
- [x] Run `npx tsx scripts/gen/gen-docs.ts --write`; confirm verify mode exits 0.
- [x] Rewrite `.claude/agents/i18n-guardian.md:77-79` to state haiku, with the `f7a5351a9` -> `b8de2f586` history.
- [ ] Run the phase-2 calibration batch: 5 bash-to-pytest ports on Haiku workers; record model, rounds, wall-clock, cost per port.
- [ ] Hand-verify all 5 ports for case-count parity against their bash twins (the falsifying check).
- [ ] Record the batch result, pass or fail, in the `model-routing.md` table, dated.
- [ ] Write `.ci/scripts/quality/check_agent_model_roster.py` with its five controls (Opus, not Haiku).
- [ ] Wire it three ways: `package.json` key, `scripts/ci-runner/manifest.ts` GateSpec, workflow step or declared `kind: 'test'`.
- [ ] Regenerate `scripts/ci-runner/gates.lock.json` (`gen-gates-lock.ts --write`); verify with the no-flag run.
- [ ] Confirm `npm run check:ci-parity` and `check:ci-gate-reachability-coverage` exit 0.
- [ ] If and only if phase 2 passed: flip `.claude/agents/pr-babysitter.md:142` mechanical/doc-churn tier from Sonnet to Haiku, keeping Sonnet as the named escalation.
- [ ] Add `## Model` sections to `.claude/agents/gate-author.md` and `.claude/agents/i18n-guardian.md`.
- [ ] Regenerate the plan-boxes ledger: `.ci/scripts/quality/check_plan_boxes.py --update` (writes `.ci/config/plan-boxes.json`), and confirm `check:ci-plan-citations`, `check:ci-plan-boxes`, `check:ci-plan-folders` exit 0.
- [ ] Full CI green.

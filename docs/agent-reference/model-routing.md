# Model routing

CLAUDE.md's rule 4 names the summary; this carries the rest.

## The rule

Choose the model by the shape of the task, never by its language or its domain.

**Haiku** when all three hold:

1. **Derived, not invented.** The output is a transformation of an artifact that already exists: a port, a translation, a mechanical sweep, a rename, or a read-only survey of what is already in the tree.
2. **A pre-existing oracle decides correctness**, without a human reading the diff: a K=5 shadow ledger, a golden differential, a gate that already fails on the old artifact, ruff/gofmt/prettier, or, for read-only work, the requirement that every claim arrive as a `file:line` the caller can open.
3. **Being wrong is loud.** The failure mode is a red check, not a silent gap.

**Opus** when the artifact created IS the oracle. New guards, new gates, threat models, schema design, and multi-file planning have no pre-existing thing to be checked against; their correctness is "did the author think of the right cases," which no gate can ask. Also Opus for anything adversarial or closed-world ("every way an agent could spell this").

**Sonnet is an escalation tier, not a default.** The one sanctioned use is `docs/i18n/CONVENTIONS.md` -- a named language whose Haiku naturalization reads awkward by the judge's `naturalness` score. Nothing else defaults to Sonnet.

## The load-bearing caveat

The oracle is what makes a cheap model safe, not the model. Condition 2 is not a nice-to-have a confident session may waive. This repo's anti-vacuity discipline proves "this gate can fail given the code as written"; it cannot prove "the author thought of the right threat model."
`.claude/rediacc_hooks/guards/block_push_to_protected_branch.py` is the worked counter-example: its header enumerates nine spellings of a dangerous push and then documents, in the same breath, a tenth it deliberately does not close. No oracle existed to notice the gap; a person reasoning adversarially did. A design gap ships silently. A bad port does not.

## The 13 subagent_type definitions: zero frontmatter changes

A `subagent_type` is defined by DOMAIN.
The model is decided by SHAPE.
A domain spans both shapes, so frontmatter is the wrong place to encode a shape rule.
`i18n-guardian` covers both a 12-locale mechanical sweep (gates are the oracle, Haiku) and diagnosing why a cross-locale gate fired (judgment, Opus).
`gate-author` covers both writing a brand-new anti-vacuity gate (the artifact is the oracle, Opus) and porting an existing bash gate-test to pytest (case-for-case differential, Haiku). Flipping either file's frontmatter would be wrong half the time.

`.claude/agents/test-advisor.md` is the exception, and stays `model: haiku`: its domain is a bounded classification ("which of six CI surfaces does this belong on"), so its shape is constant and a frontmatter default is meaningful. It is the template for any future agent that earns a Haiku default: constant shape, not cheap subject matter.

The mechanism for the Haiku slice is the per-call `model` override on the `Agent` tool, the same mechanism `.claude/agents/pr-babysitter.md` already uses for its own mechanical-sweep tier.

## The i18n note, and a 2026-08 interlude worth recording

The naturalized-hashes ledger (`packages/www/src/i18n/translations/.naturalized-hashes.json`, `$meta.models`) records `claude-haiku-4-5` for all twelve languages today, matching `docs/i18n/CONVENTIONS.md` and CLAUDE.md's i18n section.
Between commit `f7a5351a9` (2026-08-18) and `b8de2f586` (2026-08-20) the ledger briefly read `claude-sonnet-5` across all twelve, and an agent-file note from that window said so; the migration back to Haiku two days later never got the note updated.
The docs were never wrong. Twelve languages of production marketing copy have shipped on Haiku for over a month, through the full i18n gate battery (completeness, cross-locale, de-contamination, interpolation-consistency), with no quality rollback -- the strongest empirical evidence in this tree that Haiku plus a real oracle works.

## Worked examples

**Port another bash gate-test to pytest**, the highest-volume remaining class:

    Agent(subagent_type="gate-author", model="haiku",
          description="Port check-X.sh's cases to test_gate_x.py",
          prompt="Port .ci/scripts/test/gates/check-X.sh to
                  .ci/rediacc_ci/tests/gates/test_gate_x.py. Verify case-for-case
                  against the twin BEFORE the twin is deleted. Acceptance: pytest
                  green on the new file, and the case count matches the twin's.")

Derived, oracled (case-for-case differential, `check:ci-dead-bash` / `check:ci-parity` catch the wiring), loud (red pytest). Haiku. The `subagent_type` frontmatter stays `opus`; the override carries the slice.

**Write a new hook guard:**

    Agent(subagent_type="gate-author",
          description="New guard: block <dangerous class> from the Bash tool",
          prompt="...")   # no model override -- session default, Opus

Invented, not derived. The guard IS the oracle. `block_push_to_protected_branch.py`'s header shows what "did every spelling get enumerated" costs: nine spellings enumerated, plus an honest note about a tenth gap left open on purpose. Never delegate this class down, however mechanical the final diff looks.

**Read-only survey:**

    Agent(subagent_type="Explore", model="haiku",
          description="Find every caller of X",
          prompt="Report every call site of X as file:line with one line of context.
                  If a claim has no file:line, omit it.")

Derived, oracled (every citation resolves or it does not), loud. Haiku. The `file:line`-only contract is condition 2 itself, not house style.

**Re-naturalize locales after an English key change:** Haiku. It reads like creative writing, which is why instinct reaches for a bigger model, but the i18n gate battery is a genuine pre-existing oracle and the interlude above is the evidence it holds. Escalate a single named language to Sonnet only on a low `naturalness` score.

## Calibration

Before the highest-volume routing change lands (the `pr-babysitter.md` mechanical/doc-churn tier moving from Sonnet to Haiku), the next 5 bash-to-pytest gate-test ports are dispatched to Haiku workers under the worked-example contract above and measured here.

The variable that matters is not correctness -- the oracle already answers that -- it is CORRECTION ROUNDS. A Haiku worker needing four correction cycles where Opus needed one inverts the saving in the orchestrating session's own context.

Acceptance: >=4 of 5 ports reach oracle-green within <=2 correction rounds; zero require an Opus takeover; zero produce a case-count regression the differential itself did not catch (checked by hand on all five, since this is the check that would falsify the whole premise); measured end-to-end cost is below 50% of the Opus median for the same class.

| date | port | worker model | rounds | wall-clock | cost | result |
|---|---|---|---|---|---|---|
| _pending_ | | | | | | |

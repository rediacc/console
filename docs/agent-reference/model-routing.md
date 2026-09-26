# Model routing

CLAUDE.md's rule 4 names the summary; this carries the rest.

## The rule

Choose the model by the shape of the task, never by its language or its domain.

**Haiku** for READ-ONLY work, and for very small, low-risk follow-ups. Two slices, and nothing else:

1. **Read-only investigation.** Search and survey fan-out, "find every caller of X", "which files spell this convention", bounded classification over a fixed set of answers. The output is a report, not an artifact, and the contract is that every claim arrives as a `file:line` the caller can open.
2. **A very small, low-risk follow-up.** A one-line correction to something that already exists and has already been read: a typo, a stale path in a comment, a single call site the sweep missed. Small enough that the caller reads the whole diff without leaving the summary.

**Haiku is NOT routed general write or implementation work.** Not a port, not a translation of one file's logic into another's, not a mechanical sweep, not doc churn, not "it is only a rename". This holds even when a pre-existing oracle would decide correctness and being wrong would be loud, which is exactly the carve-out that used to license it.
The operator retired that carve-out on 2026-09-23; see `D-M1` in [agent/DECISIONS.md](../../agent/DECISIONS.md) and ruling 1 below.

**Opus** when the artifact created IS the oracle. New guards, new gates, threat models, schema design, and multi-file planning have no pre-existing thing to be checked against; their correctness is "did the author think of the right cases," which no gate can ask. Also Opus for anything adversarial or closed-world ("every way an agent could spell this").

**Sonnet is an escalation tier, not a default.** The one sanctioned use is `docs/i18n/CONVENTIONS.md` -- a named language whose Haiku naturalization reads awkward by the judge's `naturalness` score. Nothing else defaults to Sonnet.

**The i18n naturalization pipeline is a different mechanism and is unchanged.** Its `--model haiku` default is a flag on a script, not an `Agent` write dispatch, and it is governed by [docs/i18n/CONVENTIONS.md](../i18n/CONVENTIONS.md) and CLAUDE.md's i18n section. Ruling 1 is about sub-agent dispatch and does not reach it.

## The load-bearing caveat

The oracle was never a licence on its own, and since 2026-09-23 it is not a licence at all for write work.

What the oracle argument got right is still true in the negative direction: without an oracle, a cheap model is unsafe. This repo's anti-vacuity discipline proves "this gate can fail given the code as written"; it cannot prove "the author thought of the right threat model".
`.claude/rediacc_hooks/guards/block_push_to_protected_branch.py` is the worked counter-example: its header enumerates nine spellings of a dangerous push and then documents, in the same breath, a tenth it deliberately does not close. No oracle existed to notice the gap; a person reasoning adversarially did.

What it got wrong is the converse. An oracle bounds the failures it was built to catch, and a port is not only its case count: it is also what the port silently dropped, what it renamed on the way, and what it touched outside the two files it was told it owned. A green differential says nothing about any of those.
That is the gap the operator's ruling closes, and it closes it by removing the dispatch rather than by adding another check.

## The 13 subagent_type definitions: zero frontmatter changes

A `subagent_type` is defined by DOMAIN. The model is decided by SHAPE. A domain spans both shapes, so frontmatter is the wrong place to encode a shape rule. `i18n-guardian` covers both a 12-locale pipeline run (its own mechanism, above) and diagnosing why a cross-locale gate fired (judgment, Opus).
`gate-author` writes gates, and every mode of it is now a session-default dispatch: writing a brand-new anti-vacuity gate and porting an existing bash gate-test to pytest both produce an artifact, and ruling 1 puts the second one back on the session default alongside the first.

`.claude/agents/test-advisor.md` is the exception, and stays `model: haiku`. Its domain is a bounded classification ("which of six CI surfaces does this belong on"), so its shape is constant and it produces a recommendation rather than an artifact, which makes a frontmatter default meaningful.
It is the template for any future agent that earns a Haiku default: read-only, constant shape, not cheap subject matter.

The mechanism for the Haiku slice is the per-call `model` override on the `Agent` tool.

## The i18n note, and a 2026-08 interlude worth recording

The naturalized-hashes ledger (`packages/www/src/i18n/translations/.naturalized-hashes.json`, `$meta.models`) records `claude-haiku-4-5` for all twelve languages today, matching `docs/i18n/CONVENTIONS.md` and CLAUDE.md's i18n section.
Between commit `f7a5351a9` (2026-08-18) and `b8de2f586` (2026-08-20) the ledger briefly read `claude-sonnet-5` across all twelve, and an agent-file note from that window said so; the migration back to Haiku two days later never got the note updated.

The docs were never wrong. Twelve languages of production marketing copy have shipped on Haiku through the full i18n gate battery (completeness, cross-locale, de-contamination, interpolation-consistency), with no quality rollback. That record stands, and it is the reason the pipeline keeps its Haiku default.
It is not evidence about sub-agent write dispatch, which is a different mechanism with a different failure mode: the pipeline's output is one key at a time against a hash ledger, while a write dispatch owns a file set and a working tree.

## Worked examples

**Read-only survey**, the class Haiku exists for here:

    Agent(subagent_type="Explore", model="haiku",
          description="Find every caller of X",
          prompt="Report every call site of X as file:line with one line of context.
                  If a claim has no file:line, omit it.")

Read-only, and every citation resolves or it does not. Haiku. The `file:line`-only contract is house rule and safety net at once.

**A very small follow-up:**

    Agent(subagent_type="general-purpose", model="haiku",
          description="Fix the stale path in one comment",
          prompt="In <file>, the comment on line N cites <old path>, which moved to
                  <new path>. Change that one citation. Touch nothing else.")

One line, already read by the caller, and the whole diff fits in the report. Haiku. Anything that grows past this while the agent is running comes back to the session, it does not get a bigger prompt.

**Port a bash gate-test to pytest:**

    Agent(subagent_type="gate-author",
          description="Port check-X.sh's cases to test_gate_x.py",
          prompt="...")   # no model override -- session default

This is the dispatch the old rule sent to Haiku, and ruling 1 takes it back. Derived and oracled it may be, but it produces an artifact and owns a file set, so it runs on the session default.

**Write a new hook guard:**

    Agent(subagent_type="gate-author",
          description="New guard: block <dangerous class> from the Bash tool",
          prompt="...")   # no model override -- session default, Opus

Invented, not derived. The guard IS the oracle. `block_push_to_protected_branch.py`'s header shows what "did every spelling get enumerated" costs: nine spellings enumerated, plus an honest note about a tenth gap left open on purpose. Never delegate this class down, however mechanical the final diff looks.

**Re-naturalize locales after an English key change:** the i18n pipeline, not an `Agent` dispatch. It stays `--model haiku` per `docs/i18n/CONVENTIONS.md`, and escalates a single named language to Sonnet on a low `naturalness` score.

## Rulings

Numbered by this document. `agent/DECISIONS.md` cites them as `D-M<n>`, and `<n>` is the number here.

### 1. Haiku is not routed general write or implementation work (2026-09-23, operator)

**The ruling, verbatim:** "I give up about haiku write agents! They should only be used for read-only investigation and for very small follow-ups." <!-- style-ok -->

**What it changes.** The three-condition carve-out that used to license a Haiku write dispatch -- derived, plus a pre-existing oracle, plus a loud failure -- is withdrawn. Those conditions no longer authorize anything on their own. Haiku keeps the two slices named at the top of this file and loses the rest.

**What it does not change.** Read-only investigation and search fan-out, which CLAUDE.md rule 4 already defaults to Haiku. `.claude/agents/test-advisor.md`'s frontmatter default. The i18n naturalization pipeline's `--model haiku`. The Opus half of the rule. Sonnet as an escalation tier.

**The calibration batch this file used to carry is cancelled.** Its table was to hold five bash-to-pytest ports dispatched to Haiku workers, measured on correction rounds rather than on correctness, and its whole premise was the carve-out above. It was never run and it will not be.
The design that proposed it is `agent/plans/PLAN-haiku-model-routing.md`, whose phase-2 boxes this ruling supersedes; the plan is kept rather than deleted, so the reasoning that led here stays readable.

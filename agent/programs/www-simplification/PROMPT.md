# PROMPT: www-simplification

Execute the www simplification big-bang. Start at
`agent/programs/www-simplification/README.md` and follow its read order:
`01-verified-context.md`, `02-locked-decisions.md`, `03-bugs-and-gates.md`,
`04-execution-guide.md`. The evidence behind every number is in `research/`
(17 documents) - consult it, do not re-run it.

**Validation ethos.** Every `file:line` in those documents is a hypothesis:
re-verify against the tree, run the real thing, and read stdout and stderr
separately. Plant a control before trusting any zero; this program already caught
four instruments reporting success without having run, and they are listed in
`01-verified-context.md`.

**Ask the four operator decision points in `README.md` in ONE early round**, not
one at a time. Each carries a RECOMMENDED default, so an unanswered one still has
a defined action.

**Before any tracked file is edited, cut a fresh `MMDD-N` branch.** The tree is
parked on `main` and cannot take these commits. Everything stays local and
uncommitted otherwise: no push, no PR unless the operator asks in-task. Never
`git checkout/restore/stash/clean`; repair forward.

## Staffing

Opus is the default for coding sub-agents. **Fable for the challenging pieces and
for every planning agent: w5 (anchors, because F2 rewrites fragment identity
across 936 translated files), w8 (illustration de-texting, because the
translations must be lifted out of 573 SVGs and no tool does that today), and w9
(the constellation, because its geometry must encode a taxonomy that does not
exist yet).** Sonnet for all translation and naturalization work, delegated to
sub-agents, which is the operator's cost policy.

At most **2 concurrent writers**, with disjoint file ownership stated verbatim in
every prompt. Investigation agents fan out freely. Spot-check every sub-agent
report against the artifact before building on it. **Never put the hero and the
below-fold homepage work in one slot** (`src/pages/[lang]/index.astro`), and never
run the token wave beside the primitive wave (`public/styles/main.css`).

## Program state

    ~/.claude/projects/-home-muhammed-monorepo-console/programs/www-simplification/
      MANIFEST.md      update at every wave boundary
      reports/         reports/<phase>-<agent>.md, one per writing or planning agent
      checkpoints/     an uncommitted-tree patch at every wave boundary

Read reports and artifacts, never bare summaries.

## Checklist and worklist

The checklist is `agent/programs/www-simplification/CHECKLIST.md`.

**All eleven wave items are ALREADY SEEDED**, tagged to the handoff session
`e6500e92`, each carrying its checklist token `cl:www-simplification/<wN>`. Do not
add them again; that would double-cover every wave. **Take them over instead:**

    worklist.py --reassign <me> e6500e92

The Stop hook blocks ANY stopping session while a wave is neither ticked in the
checklist nor covered by such an item, which is why they were seeded at handoff
rather than left for you: an uncovered wave blocks unrelated peer sessions too.

Tick a `wN` box only after its store item is ticked with probed evidence. When
every wave is ticked, set `Status: done`.

## Testing

Testing and concurrency support are first-class deliverables, not follow-ups.
Twelve regression gates are part of the scope, not a coda, and **each must be
demonstrated to fail on a planted mutation.** A gate that cannot fail is a
headline finding. Seven of the twelve encode bugs that exist today and land RED
before their fixes, so each fix turns one green.

## Definition of done

Every wave ticked and `Status: done`. All 12 gates green **and each proven able to
fail**. The scorecard re-run with the recorded instruments: homepage decoded JS
under 500,000 B (from 6,998,912), painted font sizes at 8 or fewer (from 23),
painted colours at 16 or fewer (from 43), mobile height at 7,000 px or less (from
11,795). Zero dead in-page fragments across all 1,107 pages. Zero horizontal
overflow at 1440 and 390 in every locale including Arabic. No em dash in any
authored text, in any language. And the four metrics we already beat left
unchanged rather than "improved": unused-CSS percentage, DOM nodes and depth,
above-fold density, accessibility violations.

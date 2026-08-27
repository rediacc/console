# PLAN: a resumable rebase executor with an AI in the loop

Status: designed, not implemented
Owner: session 9d92d9b6, branch 0826-3
Updated: 2026-08-27

## Context

The operator vetoed a narrowing I made. I had built `--git --execute` for
`force-push` only and made it REFUSE on `rebase-submodules`,
`resolve-gitlinks` and `merge-submodule`, reasoning that a conflicting rebase
halts mid-list needing a human, and that `Plan` is a flat list with no resume or
rollback. Two independent design passes agreed with me.

The operator's answer:

> "We have AI. AI should receive a prompt to continue and/or what happened. So,
> it should fix conflicts and try again where he lefts. Let's ultrathink what we
> can do for a more automated and reliable approach."

That inverts the premise. I treated "a conflict needs a human" as grounds to
refuse. The human is not the only resumption point: an agent handed the halt
context is one too. The question is not whether to stop at a conflict, it is
what to hand back when we do.

## The evidence this design is built on

Not hypotheses. I drove two full rebases of `0826-3` by hand on 2026-08-26/27
and every conflict fell into exactly three kinds:

| conflict | kind |
|---|---|
| `private/account` gitlink, twice | **oracle-decidable** |
| `.claude/settings.json` (both waves added hooks) | mechanical union |
| `wl_agents.py` stopword list | mechanical union |
| `scripts/ci-runner/manifest.ts` (6 hunks, both added gate entries) | mechanical union, by id |
| `docs/ci-overhaul/06-progress.md`, twice | mechanical union |
| `.ci/lib/local-common.sh` (`npm install` vs `install:natives`) | decidable from `.npmrc` |
| `run.sh` `setup()` (two designs for one function) | **judgement** |
| `test-worklist-v5.sh` (monolith vs 22 case files) | **judgement** |

Ten conflicts. **One needed an oracle that already exists. Six were mechanical.
Two genuinely needed the operator.** That ratio is the whole argument for
automating: refusing all ten to protect the two is a bad trade.

## The load-bearing insight: git already owns the state

`Plan` does not need a state machine, and building one would be the expensive,
unreliable thing. **`git rebase` is already resumable.** On a halt git persists
everything that matters in `.git/rebase-merge/`: `msgnum` and `end` (step N of
M), `stopped-sha`, `git-rebase-todo` (what remains), plus the index carrying
conflict stages 1/2/3 per path.

So the missing piece is not persistence. It is a verb that READS that state,
classifies what stopped it, resolves what is decidable, and reports the rest
precisely. Anything we persist ourselves is a second copy of a truth git already
holds, and a second copy drifts.

## The design

Three verbs. None of them reimplements rebase.

### `--git rebase-status`

Read-only. Answers "where am I and why did it stop", in one screen:

- step N of M, the stopped SHA and its subject;
- every conflicted path with its stages by NUMBER (never ours/theirs);
- a CLASSIFICATION per path (below);
- the pre-rebase snapshot if one was taken, so recovery is one command away.

This alone is worth shipping before anything writes. It is the "what happened"
half of the operator's sentence, and it is exactly the prompt an agent needs.

### `--git rebase-resolve [--execute]`

For each conflicted path, classify and act:

- **gitlink** -> `resolve_gitlink_target`, which already decides this with zero
  judgement and refused correctly on genuine divergence. Proven twice today: it
  named `5f55c91` (the rebased tip, in NEITHER conflict stage) unaided.
- **append-only registry** -> union. Applies to a list whose entries are
  independent and keyed (`manifest.ts` by `id:`, a settings hook array, a
  markdown section per wave). NEVER a blind textual union: see the invariant
  below.
- **anything else** -> do not touch it. Emit the halt report and stop.

### `--git rebase-continue [--execute]`

`rebase-resolve`, then `git add` the resolved paths, then
`git rebase --continue`, then loop until done or until an unresolvable conflict
stops it. `--skip` is never issued, at any point.

## Why the mechanical half is the dangerous half, and what it costs

A textual union is NOT free, and today proved it in the worst way. Merging both
waves' additions to `wl_agents._STOPWORD_TEXT` produced adjacent Python string
literals with no separating space, so `touched` + `see` concatenated into
`touchedsee` and **two real stopwords silently stopped existing**. The file
parsed. The suite passed. Nothing failed.

So every mechanical resolution MUST be followed by an invariant check that the
union did not change meaning, and the resolver must refuse a class it has no
invariant for:

| class | invariant after union |
|---|---|
| JSON (settings, manifests) | parses, AND the entry-id set equals the union of both sides' ids, AND no duplicate ids |
| Python/shell token lists | token COUNT equals the sum, and no token appears that was in neither side (catches a glued seam) |
| markdown sections | both sides' heading sets survive |

If no invariant exists for a file, it is not mechanical. It is judgement.

## What escalation looks like

The halt report is the prompt. It must carry, per conflicted path: the stages by
number, the two subjects being combined, the classification and WHY, and the
recovery command. No summary of the diff -- the agent can read the file. What it
cannot reconstruct is which commit is being replayed onto what, and that is
precisely what `.git/rebase-merge/` knows and a session does not.

## Sequencing

1. `rebase-status`, read-only. Ship alone; it is useful with no writer.
2. The classifier plus its invariants, as pure functions with controls. This is
   where the bugs will be, so it gets the same injectable-runner treatment
   `Plan.run` and `equivalent()` already use.
3. `rebase-resolve --execute`, gitlink class only. That class is already proven.
4. Registry classes, one at a time, each gated on its invariant.
5. `rebase-continue`, the loop.

## Verification

- Fixture repos with a genuinely conflicted gitlink and a genuinely conflicted
  registry, driven end to end. There is no git fixture harness in this repo
  today; step 2 has to build one, and that is the real cost of this plan.
- The glued-seam case is a REQUIRED control: union two token lists where one
  lacks a trailing space and assert the invariant catches it. That defect
  shipped today and passed every existing check.
- Both directions on every classifier: a gitlink conflict must classify as
  gitlink, and a `setup()`-style conflict must classify as judgement and stay
  untouched.
- `--skip` must appear nowhere. Assert it as a source-level ban, the way
  `check-git-tool-safety.ts` bans `--ours`/`--theirs`.

## What this plan does NOT do

No rollback of a partially-applied rebase. `git rebase --abort` already exists,
is atomic, and returns to the pre-rebase state recorded in step 0. Wrapping it
would add a second recovery path with worse guarantees than the one git ships.

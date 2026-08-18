# `agent/` — working notes for AI sessions

TRACKED, on purpose, and this note records the reversal because the tree used to
be a gitignored `.agent/` for the opposite reason. Hiding them kept them out of
PR diffs, and also kept every session's STATE.md out of review and out of CI's
reach entirely. They are now committed, and the CI cost is paid by a zero-job
`agent` module in `.ci/scripts/ci/scope-map.cjs` rather than by hiding the tree
from git.

The original worry stands and is worth restating: these must never become a
committed lie the way `docs/ci-overhaul/` did when it drifted 44 commits behind
the code it described. Being tracked makes that failure MORE visible, not less --
this very file was caught describing a layout the same change had replaced.

## Layout

    agent/
      README.md              this file
      RULES.md               settled facts and standing constraints. SHARPEN.
      PLAN-<slug>.md         durable designs; survive compaction.
      <session-prefix>/
        STATE.md             what is true NOW and what happens next. REWRITE.
      programs/
        <slug>/              /handoff program suites
      archive/
        <label>/             frozen history, moved here when work concludes

**No branch anywhere in the path** (operator decision, 2026-08-18: "avoid using
branch name in folder path, instead let's only use the session name"). The
branch was the wrong key and the tree proved it: session `97604f47` owned three
separate STATE.md files at once, under `main`, `0815-1` and `backup-storage`,
because a `/pr-merge` moved the checkout under a live session and the hook
quietly started writing somewhere else. The compact-recovery document is the
one artifact that must not fork when the branch does. Two things fall out and
both are improvements: a detached HEAD no longer disables the freshness check,
and `archive/` is the only place a branch name still appears -- as a LABEL on
frozen history, which is what it was always good at.

`archive/<label>/` is frozen and nothing in the hooks reads it. `archive` and
`programs` are the two reserved names under `agent/`; every other directory
there is a session (`wl_store.AGENT_RESERVED_DIRS`).

`TRAPS.md` is NOT here. The standing lookup material -- TRAPS.md, ci-gates.md,
suppressions.md -- lives in `docs/agent-reference/`, because it is reference
prose that outlives every session, while everything under `agent/` is
per-session state or a durable design record.

## The one idea

**Split by LIFETIME, not by topic.** The single-file handover this replaces
failed because it forced four different lifetimes through one 1500-character
budget:

| Lives for | Goes in | Discipline |
|---|---|---|
| Minutes | `<session>/STATE.md` | Rewrite every time |
| The work | `RULES.md`, `PLAN-<slug>.md` | Sharpen; edit in place when wrong |
| Forever | `docs/agent-reference/TRAPS.md` | Append; never prune |
| History | `archive/<label>/` | Frozen when the work concludes |

Measured on the old scheme: about 40% of every handover was standing rules being
re-typed verbatim, and 8 rewrites in one session were rejected for exceeding the
budget. When space ran out the first thing trimmed was the hard-won trap, which
is precisely the item with the most durable value.

## Why `TRAPS.md` is the exception

Everything else here is kept small deliberately. `TRAPS.md` is allowed to grow,
because each entry cost a real CI round or a wasted session to learn, none of it
is branch-specific, and sharpening one away means paying for it twice. A long
`TRAPS.md` is the file succeeding, not failing.

Keep entries to what bit, why, and a citation that proves it. A trap without a
run id or a `file:line` is a rumour.

## Freshness

Only `STATE.md` is enforced. Rules and traps cannot go stale by the clock, only
by being wrong, so gating them by age is pure noise. This is the second thing the
old scheme got wrong: one freshness rule over a document that was mostly
timeless.

## Starting a new session

    mkdir -p agent/<session-prefix>
    # write a fresh STATE.md via `worklist.py --state`; never copy one forward

That is the whole bootstrap. There is no RULES.md to copy forward any more:
`agent/RULES.md` is one document every session reads and sharpens in place.
A session that needs a rule of its own can still keep `agent/<session>/RULES.md`
and it wins over the shared one, but nothing in this repo has ever needed to.

The copy-forward ritual was the tell that the file was never per-branch: a
document copied verbatim across every branch is repo-level with a manual step
in front of it. `docs/agent-reference/TRAPS.md` carries over by doing nothing,
and now so does `RULES.md`.

## When work concludes

Move the finished session directories into `archive/<label>/`, where `<label>`
is whatever names that work best -- historically a branch name, and branch names
are still fine HERE because the archive is a record rather than a live path.
Before archiving, promote anything in `RULES.md` that turned out to be true of
the REPO into `TRAPS.md`, because the archive is read rarely and `TRAPS.md` is
read always.

## `STATE.md` is one OWNED SECTION per session (since 2026-08-09)

The document was per BRANCH once, sessions are per SESSION, and this repo
routinely runs several sessions in one checkout. So `STATE.md` is a set of
owned, timestamped sections -- a shape that survives the 2026-08-18 move to a
per-session path because it is what makes a document adoptable at all:

    ## SESSION 2fd369e0 2026-08-09T21:05:00Z
    <that session's body: 250-4000 chars, with a '## Next action' section>

    ## SESSION 99ccf057 2026-08-09T18:30:00Z
    <that session's body>

Rules that follow from it:

- **You send ONE section body, never the document.** `worklist.py --state <me>`
  reads your body from stdin and writes it to YOUR OWN file at
  `agent/<session-prefix>/STATE.md`. The tool writes your `## SESSION`
  heading and its timestamp for you, and refuses a body that already carries one.
  Since 2026-08-14 there is no shared document to merge into: the single file was
  SPLIT precisely because a whole-file write could delete every peer's section at
  once (`wl_store.agent_session_dir`). A peer cannot overwrite what it cannot
  address.
- **Freshness is yours alone.** The 15-minute clock reads YOUR section's
  heading stamp, so a peer writing cannot silence your obligation and your
  stale section cannot hide behind their fresh one. It is still world-keyed:
  an unchanged world never stales anything.
- **A peer's STATE.md is never your problem and never yours to touch.** It is a
  sibling DIRECTORY, and read-only to you by construction rather than by
  etiquette (`wl_store.agent_peer_sections`). A malformed peer file does not
  block you. Read theirs for cross-session context (which files they own and you
  must not sweep); never rewrite or delete one.
- **Dead sections are reaped, not lost.** A section whose owner has been silent
  for `WORKLIST_DEAD_HOURS` (24) is dropped by the next write, and its body is
  appended to `<worklist>.agentstate.reaped.<session>.md` first. Your own
  section is never reaped, at any age.
- **A pre-section document is adopted, not destroyed**, under a
  `## SESSION legacy` heading, and ages out through the same reap path.

Why: on 2026-08-09 the staleness gate nagged one session about a document
another session owned, it obeyed, and a live campaign's entire state document
was destroyed. Merge semantics are what make that impossible; the section
format is what merge semantics need.

## Enforcement (live since 2026-07-30)

The Stop hook enforces this layout. `STATE.md` freshness is world-keyed: 15
minutes AND the world signature must have moved, judged per section as above;
writes go through `worklist.py --state <me>` (body on stdin), which refuses
thin (<250), bloated (>4000) or aimless (no `## Next action` section) bodies
and prints which sections it kept and which it reaped. **Every direct tool
write to STATE.md is DENIED** by a PreToolUse guard
(`block-agent-state-shape.sh`): `Write`, `Edit`, `MultiEdit` and
`NotebookEdit` alike. A shape-valid whole-file `Write` destroys peers exactly
as thoroughly as the old CLI did, and no shell guard can enforce a merge, so
the one writer that owns the path is the only writer. A missing
`agent/<session-prefix>/` blocks once with the bootstrap command and is never
auto-created. **A detached HEAD no longer disables anything** (2026-08-18):
the check needed a branch to find the file, so it went report-only during every
interactive rebase; with the branch out of the path there is nothing to resolve
and the gate runs mid-rebase like any other stop. The judge is fed the `## `
titles of `docs/agent-reference/TRAPS.md`, never bodies.

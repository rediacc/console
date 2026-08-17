# `.agent/` — working notes for AI sessions

Gitignored on purpose. These are working notes, not documentation: they must
never land in a PR diff, never be policed by the CI gates, and never become a
committed lie the way `docs/ci-overhaul/` did when it drifted 44 commits behind
the code it described.

## Layout

    .agent/
      README.md          this file
      TRAPS.md           shared across every branch. APPEND ONLY.
      <branch>/
        STATE.md         what is true NOW and what happens next. REWRITE.
        RULES.md         settled facts and standing constraints. SHARPEN.
      archive/
        <branch>/        moved here when a branch merges

## The one idea

**Split by LIFETIME, not by topic.** The single-file handover this replaces
failed because it forced four different lifetimes through one 1500-character
budget:

| Lives for | Goes in | Discipline |
|---|---|---|
| Minutes | `<branch>/STATE.md` | Rewrite every time |
| The branch | `<branch>/RULES.md` | Sharpen; edit in place when wrong |
| Forever | `TRAPS.md` | Append; never prune |
| History | `archive/<branch>/` | Frozen at merge |

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

## Starting a new branch

    mkdir -p .agent/<branch>
    cp .agent/<previous-branch>/RULES.md .agent/<branch>/RULES.md   # then sharpen
    # write a fresh STATE.md; never copy one forward

`TRAPS.md` is shared, so it carries over by doing nothing. That is the point.

## When a branch merges

Move `<branch>/` into `archive/`. Before archiving, promote anything in its
`RULES.md` that turned out to be true of the REPO rather than the branch into
`TRAPS.md`, because the archive is read rarely and `TRAPS.md` is read always.

## `STATE.md` is one OWNED SECTION per session (since 2026-08-09)

The document is per BRANCH; sessions are per SESSION; and this repo routinely
runs several sessions in one checkout. So `STATE.md` is a set of owned,
timestamped sections:

    ## SESSION 2fd369e0 2026-08-09T21:05:00Z
    <that session's body: 250-4000 chars, with a '## Next action' section>

    ## SESSION 99ccf057 2026-08-09T18:30:00Z
    <that session's body>

Rules that follow from it:

- **You send ONE section body, never the document.** `worklist.py --state <me>`
  reads your body from stdin and MERGES it in place under a lock; every other
  section comes out byte-identical. The tool writes your `## SESSION` heading
  and its timestamp for you, and refuses a body that already carries one.
- **Freshness is yours alone.** The 15-minute clock reads YOUR section's
  heading stamp, so a peer writing cannot silence your obligation and your
  stale section cannot hide behind their fresh one. It is still world-keyed:
  an unchanged world never stales anything.
- **A peer's section is never your problem and never yours to touch.** A
  malformed peer section does not block you. Read theirs for cross-session
  context (which files they own and you must not sweep); never rewrite or
  delete one.
- **Dead sections are reaped, not lost.** A section whose owner has been silent
  for `WORKLIST_DEAD_HOURS` (24) is dropped by the next write, and its body is
  appended to `<worklist>.agentstate.reaped.<branch>.md` first. Your own
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
the one writer that can merge is the only writer. A missing `.agent/<branch>/`
blocks once with the bootstrap commands and is never auto-created. A detached
HEAD makes the check report-only (set `WORKLIST_AGENT_BRANCH` to re-enable it
mid-rebase). The judge is fed the `## ` titles of `TRAPS.md`, never bodies.

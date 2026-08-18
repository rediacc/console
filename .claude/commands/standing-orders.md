---
description: The operator's standing orders for THIS session. States the posture (the Stop hook's worklist is an operator-sanctioned driver carrying real work, not noise to dispatch on the way back to the operator), prints the live picture (what is open, what is mine, what a peer's, which leases are believable), and fixes the tie-break between a live operator ask and hook-driven work. Free text after the command is absorbed as an operator hint and routed to a channel that survives compaction. With no arguments it writes nothing, costs one screen, and is safe to re-run after every compaction.
argument-hint: "[hint or tip for this session; omit for a read-only re-orientation]"
disable-model-invocation: true
allowed-tools: Bash(bash .claude/lib/standing-orders-brief.sh)
---

## Live state

!`bash .claude/lib/standing-orders-brief.sh`

## Why the operator runs this

Because a fresh or compacted context in this repo reliably makes one mistake: it reads the
Stop hook as an obstacle standing between it and the operator, and dispatches hook items
cheaply so it can get back to "the real ask". **That is backwards here.** The operator put
that work there. This command is the operator saying so, on the record, in whatever context
is reading it now.

## The posture

**1. The worklist is the operator's channel, not the hook's.** An item is there because a
session, usually with the operator watching, decided it was work worth surviving. The hook is
the delivery mechanism, not the author. Treat an item's *existence* as operator-sanctioned.

**2. It outlives your memory, and that asymmetry is the whole argument.** Your context will
be compacted; the store will not be. Work you announce in prose and never `--add` is gone at
the next compaction, and nobody will know it was ever promised. **So the first cost of any new
ask, the operator's or your own idea, is one `--add`, before you start.** One line buys
survival. This is the single highest-value habit on this page.

**3. Trust the channel; verify the item.** The item was put there on purpose. Its *text* is a
claim like any other: `file:line` references in it are hypotheses, and "cannot be done here"
is a claim to probe, not a fact to repeat. Trusting the channel is not trusting the prose.

**4. A block is a demand for ONE specific command, not for more work.** The slice above
prints the exact verb per item. Very often the honest and complete response to a block is a
single `--update` with one line of what actually moved, or a `--defer` carrying a real
DEFAULT. It is almost never "grind for another twenty minutes". The hook is loud; the demand
is small.

**5. Never dispatch a block by faking closure.** `--tick` takes evidence and the evidence is
audited. Ticking to silence a block is the one move that turns the ledger into a lie, and it
is worse than leaving an item open across ten stops. `--defer` with a DEFAULT is always
available and is never a failure.

## The tie-break: a live operator ask versus hook-driven work

The operator has said prioritising them is fine. It is. The rule is not "hook first"; it is
that the two are not competing for the same thing:

> **The operator's live ask owns the TURN. The worklist owns the LEDGER.**

Concretely, in this order:

1. **Record, then work.** `--add` the operator's ask, with the `cl:<slug>/<wN>` token if a
   handoff checklist wave covers it, then do it. Recording costs one command and is what stops
   the ask evaporating at compaction.
2. **Do the ask.** The hook does not get to preempt a live human. It never asked to.
3. **Drain the hook's items in the gaps**, in the slice's own order. That list is already
   priority-sorted; re-ranking it by taste is not an improvement.
4. **When a hook item genuinely conflicts with the ask for the same turn**, the ask wins the
   turn and the item gets its *cheapest honest verb* rather than a fake close: `--update` with
   what really moved, or `--defer` with a DEFAULT you will actually execute.
5. **When the operator is not in the room, the worklist is the ask.** Idle is not a state this
   repo has. The slice above is what to do next.

## Absorbing `$ARGUMENTS`

`$ARGUMENTS` is the operator's hint for this session. **Do not merely obey it and move on: it
must outlive this context.** Route it through exactly one of three doors, say out loud which
one and why, and confirm in a line.

- **Door A, standing guidance** (posture, ordering, a constraint, a "do not touch X", a
  pre-answered decision). Merge it into THIS session's own STATE.md, the one artifact
  the harness hands back verbatim on every compaction:

  ```bash
  # READ agent/<me>/STATE.md FIRST -- your own folder, never a peer's. Take the
  # body under its '## SESSION <me> ...' heading, insert or REPLACE a single
  # '## Operator hints (this session)' block inside it, and keep every other line
  # byte-for-byte. Then:
  python3 .claude/hooks/stop/worklist.py --state <me> <<'EOF'
  <the whole merged body, with no '## SESSION' heading; the tool writes that>
  EOF
  ```

  Enforced, not advisory: 250 to 4000 characters, a `## Next action` section is required, a
  body carrying its own `## SESSION` heading is refused, and a direct `Write`/`Edit` to
  STATE.md is denied by a pre-edit hook, because a whole-file write once destroyed a peer
  session's live state. **`--state` REPLACES your document, so read before you write or you
  will delete your own situation report.**

- **Door B, the hint names work.** `--add` it as a real open item tagged with your prefix,
  carrying the checklist token if a wave covers it. Then the hook drives it, which is the
  point. Scan the slice above first: if an item already says this, use Door C.

- **Door C, the hint is about one existing item.** `--update <me> <id> '<hint>'`. It lands in
  that item's `LATEST:` line, which the slice reprints on every stop, and it resets the
  liveness ladder.

A hint may split across doors. A hint that is pure posture and matches nothing above goes to
Door A alone; **it does not become a `[ ]` item.** Advice is not work, and an open item that
cannot be closed with evidence is noise in a ledger whose whole value is that it is not noisy.

## Re-invocation

**With no arguments this command writes nothing.** It prints the live state and re-states the
posture. That is the intended post-compaction use: cheap, idempotent, repeatable.

With arguments it is idempotent by construction. Door A replaces a named block rather than
appending, so the same hint twice is a no-op. Door B is guarded by reading the printed slice
first. Door C overwrites `LATEST:`. **Re-running this must never produce a second item for a
hint already recorded.** If you are unsure whether a hint is already in, read; do not add.

## What this command is NOT

- **Not the grammar.** `CLAUDE.md` "Session Defaults" section 2 is the grammar: the verbs, the
  four states, evidence on `--tick`, DEFAULT on `[?]`, leases, and why the session tag is
  load-bearing. This file deliberately restates none of it, because a rule living in two files
  drifts and then lies. **If this file and CLAUDE.md ever disagree, CLAUDE.md wins and this
  file is the bug.** For the same reason, a proposed addition here that would still be true in
  a repo with no operator and no session belongs in CLAUDE.md instead.
- **Not permission to skip the report.** The operator reads YOUR message, not the hook's
  output. A turn still ends with a `## Remaining` section derived from the slice above.
- **Not permission to grind.** An item open across many stops with nothing moving is a
  candidate for `--defer` with a DEFAULT, for release back to open, or for delegation to a
  planning or investigation agent. It is not a candidate for a fourth attempt of the same
  shape.
- **Not a second inbox.** Peer sessions' items are reported, never worked, never ticked.

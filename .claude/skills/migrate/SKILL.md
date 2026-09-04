---
name: migrate
description: Continue another session's remaining worklist items in this session. Lists sessions that still have open work and are not running here, ASKS which ones to continue, then re-tags their open, in-flight and deferred items to this session and prints the predecessor's next action. Use after a harness restart, after switching machines, or when a stop report names a session with work nobody owns.
user-invocable: true
self-improving: false
---

# migrate: work that outlived the session that started it

The worklist store is tracked in git (`agent/worklist/<writer>.jsonl`), so a
`git pull` on a second machine brings every open item with it. What it cannot
bring is an owner: those items belong to a session that is not running here, so
they are visible to everyone and blocking nobody. This is the verb that adopts
them.

## Run it

    ME="${CLAUDE_CODE_SESSION_ID:0:8}"
    python3 .claude/hooks/stop/worklist.py --migrate "$ME" --candidates --json

An empty list is a normal, common answer, not a failure: say so and stop. A
session that is LIVE on this machine is deliberately excluded — its work is not
yours to take, and the listing says which artifact proved it.

## Then ASK, and never assume

One `AskUserQuestion` call, `multiSelect: true`, `header: "Continue"`. The
question names this session and the consequence:

> Which sessions should this session (`<me>`) continue? Their open, in-flight
> and deferred items will be re-tagged to `<me>`; the originals are ticked
> "migrated to", nothing is deleted, and cross-session requests are not moved.

One option per candidate. Label is `<prefix> (<branch>) <n> open`; the
description carries the verdict and its evidence, the age, whether the last
event came from this machine, and the one-line brief. **Pre-select nothing and
recommend nothing.** The whole reason this is a question is that the answer is
not derivable: two sessions on one branch at one time look identical from here,
and picking for the operator is how a colleague's work gets swept up.

More than 16 candidates: page by newest first and say how many remain.

## Then move, one named prefix at a time

    python3 .claude/hooks/stop/worklist.py --migrate "$ME" <prefix> [<prefix>...]

Print its output unedited — it is the report of what moved and what it refused.
Then fold the printed `HANDED OFF NEXT ACTION` into your own STATE.md under
`## Next action` (its first step must be work, not a wait), and commit
`agent/worklist/<me>.jsonl` and `agent/<me>/STATE.md` **by name**, or the
migration does not travel to the next machine.

## What it does and does not touch

| moved | left alone |
|---|---|
| `[ ]` open items | `[x]` done items (history) |
| `[>]` in-flight, **lease reset** | cross-session requests (`--requests`) |
| `[?]` deferrals, **DEFAULT window preserved** | the predecessor's STATE.md (a peer's document) |

The lease is reset rather than carried because its worker was a background task
of the previous session, on the previous machine. Re-leasing would claim a live
worker that cannot exist and stop the liveness ladder from ever asking about it.
The deferral's `upd` stamp IS carried, so a `[?]` whose default was twenty
minutes from executing still has twenty minutes, not a fresh window.

## Three things that will bite otherwise

**Safe to run twice.** Whether an item has already moved is computed from the
migration record on the new item, never from note text, so a second run moves
nothing and says so.

**Re-tag, not alias.** After the move the items are *yours*, which is the point:
the Stop hook blocks on them exactly as it would on work you typed. The
`(<prefix>)` tag inside the text still names whoever wrote it, because that
stays true.

**A restart is not a compaction.** `--adopt` proves one conversation split in
two and refuses without harness evidence; a restart leaves none, which is
exactly the gap this verb fills. Use `--adopt` when the evidence exists — it
keeps one identity — and `--migrate` when it does not.

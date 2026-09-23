---
name: migrate
description: Continue another session's remaining work in this session. Lists sessions that still have open work and are not running here -- worklist items, and/or an unresolved STATE.md "Next action" left behind even after every item was ticked -- ASKS which ones to continue, then re-tags their open, in-flight and deferred items to this session and prints the predecessor's next action. Use after a harness restart, after switching machines, or when a stop report names a session with work nobody owns.
user-invocable: true
self-improving: false
---

# migrate: work that outlived the session that started it

The worklist store is tracked in git (`agent/worklist/<writer>.jsonl`), so a `git pull` on a second machine brings every open item with it. What it cannot bring is an owner: those items belong to a session that is not running here, so they are visible to everyone and blocking nobody. This is the verb that adopts them.

## Run it

    ME="${CLAUDE_CODE_SESSION_ID:0:8}"
    python3 .claude/hooks/stop/worklist.py --migrate "$ME" --candidates --json

An empty list is a normal, common answer, not a failure: say so and stop. A session that is LIVE on this machine is deliberately excluded — its work is not yours to take, and the listing says which artifact proved it.

**A candidate can carry zero worklist items.** Ticking every `[ ]`/`[>]`/`[?]` before dying does not mean nothing is left: `agent/<prefix>/STATE.md`'s newest "## Next action" section is checked too (bounded by `WORKLIST_HANDOFF_STALE_HOURS`, 720h, so this does not resurrect handoffs from months ago).
Such a candidate shows `0 worklist item(s), but a STATE.md Next action below` -- read that text, it is the whole reason the prefix is listed. This exists because it was missing once: a session that had ticked every item still had a live PR-babysit wave and an unresolved next step named only in its STATE.md, and `--candidates` reported nothing.

**A candidate can also be named by a committed PLAN.** Any `agent/plans/PLAN-*.md` carrying open boxes, whose `Status:` is not finished and whose `Owner:` resolves to a session that is not live here, puts that owner in the listing on its own: no worklist item and no STATE.md section required.
Such a candidate shows `0 worklist item(s), but N committed plan(s) with M open box(es)` followed by one `PLAN <path> [status] N open / M ticked` line per plan (capped at `WORKLIST_MIGRATE_PLANS_SHOW`, default 3, with a `+K more plan(s)` tail).
There is deliberately NO age cutoff on this half, unlike the STATE.md one: a plan clears itself when its owner goes live, when its status becomes finished, or when its last box is ticked, so there is no stale cursor to age out. Measured 2026-09-17, before this existed: 99 open boxes across 11 plans owned by three idle sessions, and no surface in this repo named one of them.

## Then ASK, and never assume

One `AskUserQuestion` call, `multiSelect: true`, `header: "Continue"`. The question names this session and the consequence:

> Which sessions should this session (`<me>`) continue? Their open, in-flight
> and deferred items will be re-tagged to `<me>`; the originals are ticked
> "migrated to", nothing is deleted, and cross-session requests are not moved.

One option per candidate. Label is `<prefix> (<branch>) <n> open`, and `<n>` counts BOTH stores: the candidate's open, in-flight and deferred worklist items PLUS the open boxes of every plan it carries (`counts.open + counts.inflight + counts.deferred + sum(plans[].open)` in the JSON).
A session whose only remaining work is a committed design must not read as `0 open`, or the option the operator most needs to see is the one that looks emptiest. `0 open` is still valid and now means exactly one thing: a STATE.md-only candidate, with real work named in prose and none of it counted anywhere.
The description carries the verdict and its evidence, the age, whether the last event came from this machine, and the one-line brief, or the STATE.md Next-action excerpt when there is no worklist brief to quote.
**Pre-select nothing and recommend nothing.** The whole reason this is a question is that the answer is not derivable: two sessions on one branch at one time look identical from here, and picking for the operator is how a colleague's work gets swept up.

More than 16 candidates: page by newest first and say how many remain.

## Then move, one named prefix at a time

    python3 .claude/hooks/stop/worklist.py --migrate "$ME" <prefix> [<prefix>...]

Print its output unedited — it is the report of what moved and what it refused. Then fold the printed `HANDED OFF NEXT ACTION` into your own STATE.md under `## Next action` (its first step must be work, not a wait), and commit `agent/worklist/<me>.jsonl` and `agent/<me>/STATE.md` **by name**, or the migration does not travel to the next machine.

## Then OFFER the predecessor's open plans, because a handoff is not enough

The move step prints `<prefix> also owns N open plan(s), not moved`, and a plan is never adopted silently, since it is a committed document. That leaves a gap the operator hit on 2026-09-20: a session was continued, its handoff named plan boxes to work, and the stop hook showed none of them, because the plans still named the predecessor as Owner and a plan a session does not own is
skipped outright. Only an ADOPTED plan (its Owner line reads `(adopted from <prev> <date>)`) becomes this session's mission and blocks a stop while its boxes are untracked.

So when the output lists open plans, or the handed-off next action names a plan file or plan box ids, ask in one more `AskUserQuestion` (`multiSelect: true`, `header: "Adopt plans"`, one option per plan with its status and open/ticked counts, nothing pre-selected), then run `worklist.py --migrate "$ME" --plan <path> [<path>...]` for the chosen ones and commit the edited plan files
by name. Adopting a plan is the statement that this session is executing it, and the hook holds the session to that.

## What it does and does not touch

| moved | left alone |
|---|---|
| `[ ]` open items | `[x]` done items (history) |
| `[>]` in-flight, **lease reset** | cross-session requests (`--requests`) |
| `[?]` deferrals, **DEFAULT window preserved** | the predecessor's STATE.md (a peer's document) |
| nothing at all, unless `--plan <path>` names it | the predecessor's committed plans |

`--plan <path> [<path>...]` is the ONLY thing here that writes a peer's plan, and it writes only the paths it is handed. It re-stamps that plan's `Owner:` line to this session inside the header's first ten lines, sets an existing `Updated:` line to today, and touches no `- [ ]` or `- [x]` line, so `check:ci-plan-boxes` A0 signatures and A1 never-deleted stay byte-identical.
It refuses a finished status and refuses a plan with no open boxes, and says so instead of writing. Run `npm run check:ci-plan-record -- --update` afterwards, which the command itself asks for on every successful rewrite: the census keys freshness on byte size, so an un-regenerated `agent/INDEX.md` puts a staleness banner on the next SessionStart.

The lease is reset rather than carried because its worker was a background task of the previous session, on the previous machine. Re-leasing would claim a live worker that cannot exist and stop the liveness ladder from ever asking about it. The deferral's `upd` stamp IS carried, so a `[?]` whose default was twenty minutes from executing still has twenty minutes, not a fresh window.

## Three things that will bite otherwise

**Safe to run twice.** Whether an item has already moved is computed from the migration record on the new item, never from note text, so a second run moves nothing and says so.

**Re-tag, not alias.** After the move the items are *yours*, which is the point: the Stop hook blocks on them exactly as it would on work you typed. The `(<prefix>)` tag inside the text still names whoever wrote it, because that stays true.

**A restart is not a compaction.** `--adopt` proves one conversation split in two and refuses without harness evidence; a restart leaves none, which is exactly the gap this verb fills. Use `--adopt` when the evidence exists — it keeps one identity — and `--migrate` when it does not.

**Naming a zero-item prefix still prints its handoff.** The move step (`--migrate "$ME" <prefix>`) prints `nothing left to migrate` for a prefix with no worklist items, but it ALWAYS checks that prefix's STATE.md for a `HANDED OFF NEXT ACTION` block too, even then — it used to `continue` past that check on exactly this path, so naming the one prefix this section exists for (zero
items, real work) printed nothing at all.

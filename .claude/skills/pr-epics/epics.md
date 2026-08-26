# epics: grouping a wave, and publishing it

An epic is a **label over** worklist items, never an item itself. The items stay
individually tracked, ticked and evidenced; the epic only groups them so a PR
body can carry one section each and the review can run once each.

    worklist.py --epic <me> new "<title>"       prints the new id
    worklist.py --epic <me> add <eid> <ids...>  additive, safe to repeat
    worklist.py --epic <me> list                what exists and what it covers
    worklist.py --publish <me> <branch>         render agent/pr/<branch>.md

## Why a sidecar

`compact()` rewrites the event log to the minimal set reproducing the current
fold: `md`, `add`, `lease`. A novel event kind there is **destroyed on the next
compact**, silently. Measured on this repo: after a compact the log held only
`{md: 1, add: 29}`, every `state`/`triage`/`lease` event folded away.

`record_intent` hit this first and says so at its own definition. `wl_epic.py`
stores epics in `<worklist>.epics` for the same reason. If you add anything to
this family, register the suffix in `wl_store.py`'s sidecar docstring:
`check-tracked-sidecars.sh` **parses that list**, so a sidecar missing from it is
one the gate cannot see.

## Why the snapshot exists

The store lives in TMPDIR (`/tmp/claude-worklist/<repo-slug>.events.jsonl`), so
CI can never read it. `--publish` renders to `agent/pr/<branch>.md`, which is in
the repo and is therefore the contract every downstream gate diffs against.
Stale snapshot, red gate: that is the design, not an accident.

`agent/` is tracked deliberately, and so are `agent/PLAN-*.md` and each session's
`STATE.md`. Nothing here needs un-gitignoring.

## Two behaviours worth knowing

**Orphans are reported, never hidden.** An item in no epic gets a "Not in any
epic" section. Silence there would be indistinguishable from having no such work.

**Rendering uses the display identity**, `brief_text()` (what the item first said
plus its latest note), never `rec["text"]`, which accumulates every update note
forever and would put twenty concatenated lines into a PR body.

## A test must not write into the repo

`--publish` honours `WORKLIST_PUBLISH_ROOT`. Use it in any harness: without it a
test run resolves the real repo root and leaves a snapshot in a **tracked**
directory, dirtying a tree other sessions are working in.

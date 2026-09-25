# Plan records: the grammar of a compacted plan

A plan in `agent/` is compacted rather than deleted. The file keeps its path, so every citation of it still resolves, and its full text moves into a git BLOB that the record points at. What is left behind is a RECORD: a short, fixed-shape document a future session can read in one screen and verify against the tree.

This page is the grammar. It is the reference for anyone writing one by hand, reviewing one in a diff, or changing `--plan-compact`.

## Why a blob and not a commit

This repository merges with `gh pr merge --rebase`, so a commit sha recorded on a branch is rewritten at merge. Measured 2026-09-06: of the commit-shaped tokens already cited in plans, 37 of 71 no longer resolved. A blob id is content-addressed and survives the rebase, which is why `render()` writes `Full-Text-Blob` unconditionally while `Full-Text` (a short sha plus a path, both
of which a rebase can invalidate) is written only when it is known.

To read a record's full text:

    git show <blob>
    git log --find-object=<blob> --all

The second command names the commit the blob arrived in, which is the part a plain `git show` cannot tell you.

## The two statuses

`compacted` is a finished plan: every box is attested. `parked` is a plan whose TEXT is compacted but whose work is not done, so it stays on the housekeeping clock on purpose. A parked record is not a quieter way of finishing something.

## Decided, not done: a finished Status with a `Ruling:`

A plan whose open boxes the operator DECIDED will not be done closes like any other plan (`Status: superseded` or `abandoned`, then `check:ci-plan-folders --move` into `_done/`), with one extra header line naming the decision:

    Ruling: #d9785655
    Ruling: "<the operator's words>" in docs/ci-overhaul/04-decisions.md

Every reference on the line must re-resolve on every run: a `#<id>` must be a CLOSED item in the committed worklist store (not `[?]`, not open, not tombstoned), and a quote must occur, whitespace-normalised, in the named non-plan file. `check:ci-plan-boxes` G-A3 refuses a finished Status over open boxes without such a line, and the Stop hook reports the same plan until it has one. Under a resolving ruling the boxes leave every count, and the `_done/` sweeper may later delete the file without G-A1 or G-A5 reading it as a lost box.

The gate proves that a closed decision exists, not that it says what the header claims, so the header should quote the decision. `parked` is not this state: its boxes stay on every clock.

## The grammar

The table below is GENERATED from `.claude/hooks/stop/wl_planrec.py` by `npx tsx scripts/gen/gen-docs.ts --write`, and `check:ci-doc-region-parity` fails when the committed bytes and the code disagree. Do not hand-edit between the markers.

It is generated for one specific reason. A grammar that lives in code and is ALSO typed into prose has two copies, and the prose copy is the one nobody re-derives: this repository has already shipped a document telling readers there were "254 fast gates" against a live 312, and a `.dead-bash-allowlist` that said "the 17 gate scripts" against 131. Both were true when written. A
record grammar decays the same way, and the reader who inherits the stale copy is a session hand-writing a record that the gate will then refuse.

Order in the table is the order the renderer emits, NOT alphabetical, because order is part of the grammar: the header block must land inside the header window or `wl_checks.plan_records` cannot see the `Status:` line, and the whole file then reads as an ordinary plan with an unparseable header. That is worse than not compacting it, because it stays on the housekeeping clock while
LOOKING like a record.

<!-- >>> gen-docs: plan-record-grammar -->
<!-- Generated from wl_planrec.py. Hand-edits are reverted by `gen-docs --write` and reported by check:ci-doc-region-parity. -->

Scans: the record grammar in .claude/hooks/stop/wl_planrec.py: its bounds, header fields, sections, trailer keys and annotation lines.

| Element | Kind | Rule | Read from |
|---|---|---|---|
| `Status values` | bound | `compacted` or `parked` | `RECORD_STATES` |
| `header window` | bound | first `10` lines | `HEADER_LINES` |
| `record size` | bound | `6 * 1024`, override `WORKLIST_RECORD_MAX_BYTES` | `RECORD_MAX_BYTES` |
| `per box` | bound | `160`, override `WORKLIST_RECORD_PER_BOX_BYTES` | `RECORD_PER_BOX_BYTES` |
| `blob ratio` | bound | `2`, override `WORKLIST_RECORD_BLOB_RATIO` | `BLOB_RATIO` |
| `Status` | header field | always, in HEADER_FIELD_KEYS | `render()` |
| `Owner` | header field | optional, in HEADER_FIELD_KEYS | `render()` |
| `Full-Text` | header field | optional, in HEADER_FIELD_KEYS | `render()` |
| `Full-Text-Blob` | header field | always, in HEADER_FIELD_KEYS | `render()` |
| `Record-Sig` | header field | always, in HEADER_FIELD_KEYS | `render()` |
| `Depends-On` | header field | optional, in HEADER_FIELD_KEYS | `render()` |
| `Priority` | header field | optional, in HEADER_FIELD_KEYS | `render()` |
| `Concurrency` | header field | optional, in HEADER_FIELD_KEYS | `render()` |
| `Owns` | header field | optional, in HEADER_FIELD_KEYS | `render()` |
| `Compacted-At` | header field | accepted in the header block; `render()` writes it in the `## Record` trailer | `HEADER_FIELD_KEYS` |
| `Compacted-By` | header field | accepted in the header block; `render()` writes it in the `## Record` trailer | `HEADER_FIELD_KEYS` |
| `Extends` | header field | accepted when parsing, never written by `render()` | `HEADER_FIELD_KEYS` |
| `Related` | header field | accepted when parsing, never written by `render()` | `HEADER_FIELD_KEYS` |
| `Supersedes` | header field | accepted when parsing, never written by `render()` | `HEADER_FIELD_KEYS` |
| `## Why` | section | authored; an empty one renders as `<FILL: ...>` | `PROSE_SECTIONS` |
| `## Outcome` | section | authored; an empty one renders as `<FILL: ...>` | `PROSE_SECTIONS` |
| `## Lessons` | section | authored; an empty one renders as `<FILL: ...>` | `PROSE_SECTIONS` |
| `## Boxes` | section | generated by `render()`, never authored | `render()` |
| `## Record` | section | generated by `render()`, never authored | `render()` |
| `## History` | section | generated by `render()`, never authored | `render()` |
| `Record-Kind` | `## Record` trailer | written when set, omitted when empty | `render()` |
| `Prior-Status` | `## Record` trailer | written when set, omitted when empty | `render()` |
| `Compacted-By` | `## Record` trailer | written when set, omitted when empty | `render()` |
| `Compacted-At` | `## Record` trailer | written when set, omitted when empty | `render()` |
| `Boxes` | `## Record` trailer | written when set, omitted when empty | `render()` |
| `Epics` | `## Record` trailer | written when set, omitted when empty | `render()` |
| `Touched` | `## Record` trailer | written when set, omitted when empty | `render()` |
| `Gates` | `## Record` trailer | written when set, omitted when empty | `render()` |
| `Why-Source` | `## Record` trailer | written when set, omitted when empty | `render()` |
| `Read-History` | `## Record` trailer | written when set, omitted when empty | `render()` |
| `RECORD_LINE_RE` | line pattern | `^ {4}\(record\) sig=([0-9a-f]{8}) done=([0-9a-f]{9}\|open\|abandoned)[ \t]*$` | `RECORD_LINE_RE` |
| `TICK_LINE_RE` | line pattern | `^ {4}\(ticked\) ` | `TICK_LINE_RE` |
| `BOX_LINE_RE` | line pattern | `^\s*[-*+]\s+\[([ xX?>])\]\s+(\S.*)$` | `BOX_LINE_RE` |

38 row(s). Generated by `npx tsx scripts/gen/gen-docs.ts --write`; do not hand-edit.

<!-- <<< gen-docs -->

## What the table cannot tell you

Three things, all of which the code enforces and none of which is a row:

1. **`Record-Sig` covers the SPINE, not the prose, and the difference is deliberate.**
`record_sig()` hashes the status, both halves of the pointer, and every box line with its signature and its `done=` value. So a swapped blob, a downgraded status, a re-worded box or a forged `done=` all move it. `## Why`, `## Outcome`, `## Lessons`, `## Record` and `## History` are NOT covered: prose has to stay correctable, and a signature that broke on every appended history line
is a signature everyone learns to ignore.
2. **`done=` is proved against `.ci/config/plan-boxes.json`'s HISTORY, never against the plan
file's own.** A box line that says a thing was finished is a CLAIM; the ledger is the evidence. This is why the `(record)` line is an attestation and the `(ticked)` line beside it is only a note.
3. **The size budget has a floor as well as a ceiling.** The record is capped, and the blob it
points at must be at least the blob ratio times the record's size. That second half is anti-vacuity, not style: a "record" that is as long as what it replaced has compacted nothing, and one pointing at a blob smaller than itself is pointing at the wrong object.

## Where the rest of it lives

- `.claude/hooks/stop/wl_planrec.py` is the implementation: `parse`, `derive`, `render`,
`record_sig`, `launder`, `render_index`.
- `agent/INDEX.md` is the generated index of every record, one row per plan.
- `.ci/config/plan-boxes.json` is the committed second reading of every plan's boxes.
- `docs/agent-reference/TRAPS.md` carries the two record traps: a derived title falling back to
a slug, and a stale `Status:` header being a claim rather than evidence.

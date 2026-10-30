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

## Live proof: a plan that touches a deployable surface

A plan whose `Owns:` globs hit a deployable surface closes only on a live receipt from bench or hostinger. The design is `agent/plans/PLAN-tested-on-bench.md`; the surface map is `.ci/config/proof-tiers.json`, read through `.ci/rediacc_ci/proof/surfaces.py`. Deploy tooling and proof tooling are not surfaces. A plan is a **required plan** when its `Owns:` globs hit at least one mapped surface; a plan owning only tooling is not required, so it owes no `Live-Proof:` line, and a `none` line it writes anyway still has to cite a ruling.

**The header.** One anchored line inside the first 12 lines of the plan file (`X_HEADER_LINES` in `wl_plandeps.py`, the window `Owns:` and `Concurrency:` share), parsed by `parse_live_proof` in `.claude/hooks/stop/wl_plandeps.py` (the same parser serves the pre-edit guard and the gate), in one of two forms:

- `Live-Proof: bench|hostinger[, <target>...] -- <reason>` declares the targets. The reason needs at least 12 characters. `edge` and `stable` are refused by name.
- `Live-Proof: none -- <reason>` is the opt-out. The reason must cite a ruling, either a closed worklist item (`#<id>`) or a committed operator quote (`"<quote>" in <path>`), resolved by `resolve_live_proof_waiver`. A `none` with no resolvable citation is refused.

Every touched surface must be covered by one declared target that the surface admits (`surfaces.<name>.live` in the map). The VM tier and the live tier do not substitute for each other.

**The box.** A plan that declares targets carries one `LP-<target> [live]` box per target, each with an `Accept: live-proof <target> <check-id> [args]` sub-line. The box closes only when a VERIFIED receipt row matches its plan, box signature, target and Accept line.

**The verb.** `PYTHONPATH=.ci python3 -m rediacc_ci.ops.live_proof record --plan <rel> --box <sig> --target bench|hostinger --check <id> [--write]` runs one registry check (`tiers.live.checks`, a fixed argv with no free arguments) and, with `--write`, appends the row to the committed ledger `agent/ledgers/live-proof.jsonl`. A dry run is the default, only a VERIFIED row is written, and a FAILED or NOT_VERIFIED run keeps its log in `.ci/cache/live-proof/` and writes nothing. There is no retroactive mode: every receipt is a fresh run. `verify [--plan <rel>]` re-judges the ledger locally with `proof.live_tier.validate_row`. Exit codes are in `.ci/rediacc_ci/ops/live_proof.py`: 0 VERIFIED, 1 FAILED or NOT_VERIFIED, 2 a request the registry or the plan refuses.

**The agent verb.** `worklist.py --live-proof <me> <plan> <LP-box-sig> [--write] [--tick]` reads the box's Accept line through `live_tier.accept_of`, runs the recorder above as a subprocess, and with `--tick` closes the box through the `--plan-tick` path once the VERIFIED row it named reads back from the ledger. The evidence line is `live-proof <id> <target> <check> rc=<rc> v=<version>`. With no plan it lists the open LP boxes. The logic is `.claude/hooks/stop/wl_liveproof.py`. It never commits, so the ledger row, the plan and `.ci/config/plan-boxes.json` ride one commit.

**The ledger is recorder-only.** `block_live_proof_ledger_write` (pre-edit) and `block_live_proof_ledger_shell_write` (pre-bash) refuse every hand write to `agent/ledgers/live-proof.jsonl`, because LP5's id hash alone would pass a hand-written row. The recorder keeps the run's log in `.ci/cache/live-proof/<id>.log`, and `validate_row` re-reads it when present and refuses a digest that differs from `check.log_sha256`.

**The receipt.** The envelope is shared by both tiers (`.ci/rediacc_ci/proof/receipt.py`): `tier`, `schema`, `status`, `tree`, `head`, `dirty`, `inputs`, `surfaces`, `submodules` and `renet`. The live body (`.ci/rediacc_ci/proof/live_tier.py`, schema 1) adds `id`, `at`, `by`, `plan`, `box`, `target`, `region`, `deploy` (`surface`, `worker`, `version_id`, `source`, `deployed_head`, `confirmed_live`), `check` (`id`, `args`, `argv`, `rc`, `duration_s`, `log_sha256`, `tail`) and `ladder` (`vm`). The `id` is `lp-` plus 12 hex of the row's hash. Deploy identity is read and confirmed live, never believed: bench through the version `deploy_bench` recorded and wrangler's 100% report, hostinger through the remote renet hash matching the local build's sha256.

**The ladder.** For a row surface with a VM phase (renet, cli-remote, account) the recorder first requires `vm_tier.admit` to admit the head tree, so a VERIFIED `npm run vm:check -- --changed` receipt on the same tree comes before any live run, and the row records its run id in `ladder.vm`. CI cannot read the VM cache, so this is a recorder refusal and not a gate rule. The recorder also applies `receipt.identity_refusal` (dirty-tree, checkout-mismatch, modified-checkout, build-mismatch, modified-build, not-live) and refuses a secret shape in the row.

**The LP rules.** LP1 (a required plan has no valid `Live-Proof:` line) and LP2 (a `none` whose ruling does not resolve) are implemented in `wl_plandeps.live_proof_findings`, which the pre-edit guard `block_plan_without_depends` shares. The gate `npm run check:ci-plan-live-proof` (`.ci/scripts/quality/check_plan_live_proof.py`, lane `quality-branch`) judges all seven, LP2 also covering a declared target no touched surface admits and a touched surface left uncovered: LP3 (a missing or Accept-less `LP-<target>` box), LP4 (an LP box ticked with no matching VERIFIED, clean receipt), LP5 (an invalid receipt: head not an ancestor of the tick, inputs digest changed, deploy not at head or not confirmed live, bad version id or row id, secret shape), LP6 (a required plan finished without a valid receipt per target) and LP7 (vacuity: an empty map, zero required plans, an unregistered check id). LP4 to LP6 judge only transitions committed after `tiers.live.baseline_at` in `.ci/config/proof-tiers.json`. Zero parsed plans is CANNOT RUN (exit 77), never green.

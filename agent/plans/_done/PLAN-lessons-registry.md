# PLAN: lessons registry — documentation anchors on the trap registry

Status: done -- 2026-10-20, every box ticked (9 of 9), merged to main with PR #600 (52a24264c)
Depends-On: no-dep -- extends `check:ci-trap-registry`, which is already on main; no open plan has to finish first
Owner: d778be9d
First-Seen: 2026-10-08
Priority: P2 -- operator /ask 2026-10-04 asked for a design; nothing is blocked on it
Concurrency: parallel -- two writers with separate files (section "Writer split"); the lead alone writes TRAPS.md
Owns: .ci/rediacc_ci/quality/trap_registry.py, .ci/scripts/quality/check_trap_registry.py, .ci/rediacc_ci/tests/test_quality_trap_registry.py, .ci/rediacc_ci/tests/gates/test_gate_trap_registry.py, .ci/rediacc_ci/tests/goldens/twins/quality.check-trap-registry.jsonl, docs/agent-reference/TRAPS.md, .ci/config/python-env-registry.json
Worklist: #077d85c1

## Why (2026-10-04, branch 1004-1)

- A 1004-1 commit, rewritten by its rebase-merge, deleted the "Rules learned this session" block from `agent/d778be9d/STATE.md`. The block held the wake timer, the ci:quick drop, shard legs, env registries and pathsOrigin.
- The review finding was closed as not-a-bug with the claim "each dropped lesson lives durably" in CLAUDE.md, a plan and gates (the per-commit review record of 5aab82b4, its line 24, readable after the review-directory prune in commit 4eccaeac4).
- Nothing checks that claim. If any of those places loses its sentence, the lesson is gone and every gate stays green.

## What exists (investigated 2026-10-08)

1. **`docs/agent-reference/TRAPS.md` is already a lessons registry with a gate.**
   - Each `## ` entry has a trailer of `Trap-Id` / `Enforced-By` / `Residue` (`docs/agent-reference/TRAPS.md:9-17`).
   - `check:ci-trap-registry` (`package.json:131`, `scripts/ci-runner/manifest.ts:1303`) runs `.ci/scripts/quality/check_trap_registry.py`. The logic is in `.ci/rediacc_ci/quality/trap_registry.py`.
   - Assertions F1-F6 (`.ci/rediacc_ci/quality/trap_registry.py:16-41`):
     - F4 checks each pointer resolves: `gate:` against manifest + package.json at `:266-270`, `hook:` against the trapguard RULES at `:289-305`, `file:` at `:374-392`.
     - F5 checks each pointer is live: `gate: true` at `:272-285`, firing and silent hook cases at `:353-370`, two-hop reachability at `:413-428`.
     - F6 runs its controls first.
   - Today: 99 entries, 47 of them JUDGMENT-ONLY.
2. **The gap is the `file:<path>:<line>` kind.** It only proves the line exists and is not blank (`.ci/rediacc_ci/quality/trap_registry.py:374-392`). The same weakness is in `wl_checks.citation_state` (`.claude/hooks/stop/wl_checks.py:223-245`).
   - Example: delete the wake-timer sentence at `CLAUDE.md:101` and `file:CLAUDE.md:101` stays green, because the next line moves up into its place.
   - `docs/agent-reference/HINTS.md` has 9 `Source: file:CLAUDE.md:<N>` pointers with the same blind spot.
3. **`trap:<id>` is already citable** from plans and hints: `TRAP_REF_RE` (`.claude/hooks/stop/wl_planrec.py:246`), `resolve` kind `trap` (`.claude/hooks/stop/wl_planrec.py:417-423`), and `POINTER_KIND` (`.ci/scripts/quality/check_hint_corpus.py:47`). Lessons that become TRAPS entries are citable with no new work.
4. **Box identity already exists.**
   - `sig` is a sha256 of the normalised first 120 characters (`.ci/scripts/quality/check_plan_boxes.py:144-151`).
   - `loose_sig` ignores directory prefixes (`.ci/scripts/quality/check_plan_boxes.py:154-164`).
   - It is restated as `box_sig` in `.claude/hooks/stop/wl_planrec.py:801-808`.
   - Compacted plans keep `(record) sig=XXXXXXXX` lines (`.claude/hooks/stop/wl_planrec.py:205-207`).
5. **Guard enumeration already exists.**
   - `guards.stems()` (`.claude/rediacc_hooks/guards/__init__.py:58-71`) is loaded by `Registry.dispatched_guards` (`.ci/rediacc_ci/quality/trap_registry.py:430-445`).
   - Guards are tested two ways: `check 2` / `check 0 guards/<stem>.py` cases in `.claude/rediacc_hooks/tests/hookcases.py` (for example `:242-257`), or a sibling `test-<stem>.py`.
6. **Other mechanisms checked and rejected as the home:**
   - HINTS.md is reminders, "not an enforcement mechanism" (`docs/agent-reference/HINTS.md:5`).
   - `check:ci-guard-mention-anchoring` (`.ci/scripts/quality/check_guard_mention_anchoring.py`) probes guard regexes against prose.
   - `check:ci-suppression-liveness` (`scripts/gates/check-suppression-liveness.ts`) checks that suppressed things still exist.
   - `agent/ledgers/hint-proposals.jsonl` is a proposal inbox.
   - `scripts/data/doc-registry.md` is generated tables (`scripts/gen/gen-docs.ts`).
   - None of these carries a lesson-to-location map.
7. **The stop-hook parser constrains the grammar.** `wl_store.trap_entries` (`.claude/hooks/stop/wl_store.py:486-534`) and `parse_corpus` (`.ci/rediacc_ci/quality/trap_registry.py:198-239`) both end the trailer at the first line they don't recognise. A new trailer line is safe only after `Residue:`.
   - Lessons with live pointers and an empty Residue never reach the judge prompt (`.claude/hooks/stop/wl_store.py:536-556`), so seeding them adds no prompt cost.
8. **The registry already lacks a check-in.** 99 entries against `TRAP_FLOOR_DEFAULT = 98` (`.ci/rediacc_ci/quality/trap_registry.py:168`). This is the unratcheted-floor case its own header describes at `:64-70`.
9. **None of the session's lessons is in TRAPS.md.** A grep of TRAPS.md for re-sign, basename, cacheprovider, strict-config, wl_wake, --retro, shard and pathsOrigin finds nothing.

## Design

**Where the registry lives:** `docs/agent-reference/TRAPS.md`. No new file.
- The TRAPS.md boundary is "fooled vs blocked" (`docs/agent-reference/TRAPS.md:3-5`). Every seed below is a fooled shape: a step is silently skipped, a timer silently killed, a box silently re-signed, or a pytest run collects nothing.
- The gate id, manifest entry, package.json script, the hand-written `ci-quality.yml` step, the shard legs and `gates.lock.json` all stay unchanged.
- The gate has no `paths` on purpose (`.ci/scripts/quality/check_trap_registry.py`, the `why:` text), so an edit to CLAUDE.md always runs it.

**Grammar change.** `Documented-In:` is a new optional trailer key, used 0..n times, and must come after `Residue:`:

```
## <title>
Trap-Id: <id>
Enforced-By: <ptr>[, <ptr>...] | JUDGMENT-ONLY
Residue: <text>
Documented-In: text:CLAUDE.md a `timeout` above its sleep
Documented-In: doc:docs/agent-reference/ci-gates.md#The pre-push lane (`npm run ci:quick`)
Documented-In: box:PLAN-gate-drop-receipt-verify#G4@<sig8>
Documented-In: trap:check-cannot-fail
```

- One anchor per line, and the value is the rest of the line. This is needed because `Enforced-By` splits on commas and spaces (`.ci/rediacc_ci/quality/trap_registry.py:536`), which would break a phrase.
- `Documented-In` never counts as enforcement. A documented lesson with no instrument is `JUDGMENT-ONLY` plus a Residue plus anchors. Otherwise the cheapest pointer would be the one people name, which is the hazard the gate's header warns about at `:13-14`.

**Anchor kinds and how each resolves.** All are resolved under a new seam, `TRAP_ANCHOR_ROOT` (default: repo root).

| Kind | Where | Resolves when | Moved but still there: green | Gone or reworded: red |
|---|---|---|---|---|
| `text:<path> <phrase>` | Documented-In | the phrase, with whitespace collapsed, appears in the file; phrase must be at least 12 characters | lines inserted above, the sentence re-wrapped, the line number changed | phrase deleted or reworded. If it now appears in another tracked `.md`, the red names that path ("repoint to …") instead of accepting it, because the registry must name where the lesson really is |
| `doc:<path>#<heading>` | Documented-In | a heading at any level, outside code fences, whose text matches exactly | heading moved or changed level | heading renamed: red, with the nearest headings suggested by difflib |
| `box:<slug>#<label>@<sig8>` | Documented-In | the plan is found in any plan folder (same list as `PLAN_FOLDERS`, `.claude/hooks/stop/wl_planrec.py:231`), a box with that label (first token, for example `G4`) exists, and its `check_plan_boxes.sig` equals sig8; a compacted plan resolves through a `(record) sig=` line | plan moved to `_done/`, or compacted | label found but sig changed: "re-signed", with the new sig shown (this is the tick-text trap itself); label gone: red |
| `trap:<id>` | Documented-In | a Trap-Id in the same corpus | (ids never change) | dangling id |
| `guard:<stem>` | Enforced-By (new) | the stem is in `guards.stems()`, loaded the way `dispatched_guards` loads it | (stems are stable) | stem gone, with nearest stems suggested. Liveness is two-sided: either a sibling `test-<stem>.py`, or both a `check 2` and a `check 0 guards/<stem>.py` case in `hookcases.py` |
| `gate:` / `hook:` / `file:` | Enforced-By (existing) | unchanged | — | unchanged |

- **`gate:`:** the operator asked about gates.lock.json. `gate_resolves` already reads manifest + package.json, and `check:ci-gates-lock` keeps the lock faithful to the manifest, so the answer is the same. It stays as it is, to avoid touching the frozen controls.
- **`file:<path>:<N>` is refused in Documented-In.** That kind is exactly the blind spot from finding 2. A selftest control pins the blindness on purpose (C5 below).

**No writer verb.** The gate prints the correction in its red message (the new sig, the new path, or the nearest heading or stem), and a person edits TRAPS.md in the same commit. Silently re-pointing an anchor would defeat the gate.

## Writer split

- **Writer A (worker): gate code.** Owns `.ci/rediacc_ci/quality/trap_registry.py` and the docstring of `.ci/scripts/quality/check_trap_registry.py`, plus `.ci/config/python-env-registry.json` only if `TRAP_ANCHOR_ROOT` isn't already covered by the existing `"*name"` row at `:996-999`. Register it with `npm run env:register` (`docs/agent-reference/ci-gates.md:108`). The resolvers are pure functions inside trap_registry.py; a separate module is only extracted if T10 is done.
- **Writer B (worker): tests.** Owns the existing modules `.ci/rediacc_ci/tests/test_quality_trap_registry.py` and `.ci/rediacc_ci/tests/gates/test_gate_trap_registry.py`. Both are already in the shard manifest (`.ci/config/shards/quality-pytest.json:160`, `:469`). Not creating a new test module means no shard leg is needed.
- **Lead (d778be9d) only:**
  - `docs/agent-reference/TRAPS.md`, which is single-writer per `docs/ci-overhaul/08-driver-contract.md:72`.
  - The `TRAP_FLOOR_DEFAULT` bump, landing in the same commit as the new entries.
  - The golden re-record (`.ci/rediacc_ci/tests/regolden.py --source port` with a reason).
- **CLAUDE.md, ci-gates.md, HINTS.md:** read only. Session Defaults stay byte-identical (`docs/ci-overhaul/08-driver-contract.md:73`).

## Tasks

- [x] L1 Writer A: `parse_corpus` accepts `Documented-In:` lines after `Residue:`.
  - New F3c: a `Documented-In` before `Residue` reds, because it would cut off the stop-hook parser at `.claude/hooks/stop/wl_store.py:520-530`.
  - `Entry` gets a `documented_in` list.
  - The golden parser test compares five fields (`.ci/rediacc_ci/tests/test_quality_trap_registry.py:52-91`); its frozen corpora contain no new key, so it stays green unchanged. Acceptance: `python3 -m pytest .ci/rediacc_ci/tests/test_quality_trap_registry.py -q`.
    (ticked) 2026-10-08T19:27:23Z by d778be9d: commit:be59366ee check_trap_registry rc=0; test_quality_trap_registry passes
- [x] L2 Writer A: `text:` and `doc:` resolvers.
  - Fence-aware heading scan (reuse `FENCE_RE`), whitespace-collapsed phrase search, 12-character minimum.
  - Red messages show the found-elsewhere path and the difflib suggestion.
  - New `TRAP_ANCHOR_ROOT` seam in `SEAMS` (`.ci/rediacc_ci/quality/trap_registry.py:150-162`).
    (ticked) 2026-10-08T19:26:48Z by d778be9d: commit:be59366ee check_trap_registry rc=0 (108 entries, 14 anchors); pytest 301 passed; L9 14/14 red
- [x] L3 Writer A: `box:` resolver.
  - Find the plan across all folders.
  - Match by label, then check the sig with the same formula as `check_plan_boxes.sig`. Assert they are equal in a test, because they can't be imported both ways (see `.claude/hooks/stop/wl_planrec.py:801-808`).
  - Fall back to `(record) sig=` lines.
    (ticked) 2026-10-08T19:26:53Z by d778be9d: commit:be59366ee check_trap_registry rc=0 (108 entries, 14 anchors); pytest 301 passed; L9 14/14 red
- [x] L4 Writer A: `guard:` kind in Enforced-By: resolves via `stems()` and requires two-sided liveness. Also `trap:` cross-references, checked after the whole corpus is parsed. Add the new kinds to the unknown-pointer message (`:584-588`) and to the `Shape` counts and success line (`:448-458`), so a collapse in any kind shows up.
    (ticked) 2026-10-08T19:26:56Z by d778be9d: commit:be59366ee check_trap_registry rc=0 (108 entries, 14 anchors); pytest 301 passed; L9 14/14 red
- [x] L5 Writer A: F6 controls, each red with its required message, added to `run_controls` (`.ci/rediacc_ci/quality/trap_registry.py:723`). Fixtures are built from scratch (`fixture_corpus`, `:613`), never by editing a copy:
  - C1: `text:` present → green.
  - C2: phrase deleted → red "not found".
  - C3: 30 lines inserted above and the phrase re-wrapped across two lines → green (moved but still there).
  - C4: phrase moved to another `.md` → red naming the new path.
  - C5: the blindness pin. After the C2 deletion, `file_resolves("<path>:<N>")` still returns True. If someone later makes `file:` content-aware, this control flips and the header must be updated.
  - C6: heading renamed → red with suggestion.
  - C7: heading moved / changed level → green.
  - C8: box present → green.
  - C9: evidence written into the box line (the re-sign trap) → red "re-signed".
  - C10: plan moved to `_done/` → green.
  - C11: plan compacted to a record → green.
  - C12: label removed → red.
  - C13: guard stem deleted → red.
  - C14: guard with a firing case only → red "one-sided".
  - C15: guard with a sibling test → green.
  - C16: `Documented-In` before `Residue` → red.
  - C17: phrase under 12 characters → red.
  - C18: `Documented-In: file:X:N` → red.
  - C19: an unknown anchor kind → red.
  - C20: dangling `trap:` → red.
  - C21: Documented-In with an empty Enforced-By → red (existing F3).
    (ticked) 2026-10-08T19:26:59Z by d778be9d: commit:be59366ee check_trap_registry rc=0 (108 entries, 14 anchors); pytest 301 passed; L9 14/14 red

  Acceptance: `npm run check:ci-trap-registry` prints a controls line with the new count, and the real tree stays green.
- [x] L6 Writer B: gate tests against the real tree (`.ci/rediacc_ci/tests/gates/test_gate_trap_registry.py`).
  - Copy each Documented-In target into a tmp `TRAP_ANCHOR_ROOT` and run `--scan-only` with the real corpus and real resolvers.
  - (a) Unchanged copy → green.
  - (b) Delete the `CLAUDE.md` wake-timer sentence → red naming `wake-timer-timeout-above-sleep`.
  - (c) Re-wrap that sentence and insert lines above it → green.
  - (d) Rename the ci-gates heading → red naming the entry.
  - Each red is preceded by its green control in the same test.
    (ticked) 2026-10-08T19:27:02Z by d778be9d: commit:be59366ee check_trap_registry rc=0 (108 entries, 14 anchors); pytest 301 passed; L9 14/14 red
- [x] L7 Lead: add the `Documented-In` key and the anchor table to the TRAPS.md header (`docs/agent-reference/TRAPS.md:9-25`), and update the "Every pointer must RESOLVE" paragraph.
    (ticked) 2026-10-08T19:27:04Z by d778be9d: commit:be59366ee check_trap_registry rc=0 (108 entries, 14 anchors); pytest 301 passed; L9 14/14 red
- [x] L8 Lead: seed the ten entries below. Raise `TRAP_FLOOR_DEFAULT` from 98 to 109 in the same commit (99 entries today + 10). Re-record the frozen floor in `.ci/rediacc_ci/tests/goldens/twins/quality.check-trap-registry.jsonl` with `regolden.py --source port --reason "lessons registry seed"`. Acceptance: `npm run check:ci-trap-registry`, `python3 -m pytest .ci/rediacc_ci/tests/test_quality_trap_registry.py .ci/rediacc_ci/tests/gates/test_gate_trap_registry.py -q`, `npm run check:ci-python-env-registry`.
  - Amended 2026-10-08 (review 4b091d92.1): the box's "99 entries today + 10 = 109" count was off by one. The registry holds 108 entries and `TRAP_FLOOR_DEFAULT` is 108 (`.ci/rediacc_ci/quality/trap_registry.py:213`), which is what `check_trap_registry` reported (108 entries, floor 108).)
    (ticked) 2026-10-08T19:27:07Z by d778be9d: commit:be59366ee check_trap_registry rc=0 (108 entries, 14 anchors); pytest 301 passed; L9 14/14 red
- [x] L9 Lead: a mutation proof on a disposable clone, never the shared tree. Delete each seeded anchor's target one at a time and confirm each turns red with that entry's id. Record the 10/10 count in the tick evidence.
  - Amended 2026-10-08 (review 4b091d92.2): the mutation proof covered all 14 documentation anchors the registry holds, which includes the ten seeded ones, so "14/14 red" is the box's count at its full width and not the "10/10" it names.)
    (ticked) 2026-10-08T19:27:10Z by d778be9d: commit:be59366ee check_trap_registry rc=0 (108 entries, 14 anchors); pytest 301 passed; L9 14/14 red
- L10 and L11 moved on 2026-10-09 to agent/plans/PLAN-lessons-registry-followups.md, executing their recorded DEFAULT (defer). This PR's plan-implementation clock covers every plan the branch ticked, and a `[?]` box counts as open there.

## Seed lessons (L8)

Writing the final titles and body text is the lead's job. Each seed's pointers are proven by the gate in L8 and L9, not by this table.

| # | Trap-Id | Enforced-By | Documented-In | Residue |
|---|---|---|---|---|
| S1 | `wake-timer-timeout-above-sleep` | `file:.claude/hooks/stop/wl_wake.py` (`harness_timeout_ms` `:115`, unknown-argument refusal `:153`), `file:.claude/hooks/stop/wl_checks.py` (`wake-timer` invariant `:2268`) | `text:CLAUDE.md a \`timeout\` above its sleep`, `text:CLAUDE.md as a background Bash call` | nothing reads the Bash call's `timeout` (see L11) |
| S2 | `ci-quick-drops-touched-slow-gate` | `guard:block_unverified_push` | `text:docs/agent-reference/ci-gates.md A touched slow gate that ci:quick drops is recorded, and the push waits for it.`, `box:PLAN-gate-drop-receipt-verify#G4@<sig>` (the plan is now in `_done/`, which exercises the moved-plan path) | empty |
| S3 | `new-test-module-needs-shard-leg` | `gate:check:ci-shard-manifest-coverage` | `text:docs/agent-reference/ci-gates.md places each missing unit and drops the ids of units that no longer exist` | empty |
| S4 | `env-read-needs-both-registries` | `gate:check:ci-python-env-registry`, `gate:check:ci-worklist-env-registry` | `text:docs/agent-reference/ci-gates.md A new environment variable is registered with one command` | empty |
| S5 | `manifest-paths-needs-paths-origin` | `gate:check:ci-paths-origin` | `text:scripts/ci-runner/manifest.ts pathsOrigin: 'declared'` | empty |
| S6 | `tick-text-resigns-the-box` (commit 739e4d139, item #06c807ed) | `guard:block_plan_box_rewrite`, `gate:check:ci-plan-boxes` | `trap:` cross-reference to S7 | empty |
| S7 | `bare-basename-citation` (CI run 37190043363, items #74f48292 and #fcaee69b) | `gate:check:ci-plan-citations`, `file:.claude/hooks/stop/wl_planrec.py` (`refuse_unresolved_citations`, commit 162bc9200) | `text:.claude/hooks/stop/wl_planrec.py Write the full repo-relative path` | empty |
| S8 | `no-cacheprovider-vs-strict-config` | `JUDGMENT-ONLY` | `text:.ci/rediacc_ci/tests/gates/test_twin_parity.py Disabling that plugin UNREGISTERS the \`cache_dir\` ini key`, `text:pyproject.toml --strict-config  an unknown key in THIS table is an error` | a nested pytest run against the repo's ini with `-p no:cacheprovider` exits 4 and collects nothing; nothing refuses it |
| S9 | `gh-field-typed-vs-raw` | `JUDGMENT-ONLY` | `text:.claude/rediacc_hooks/shellscan.py "raw-field"` and the flag regex at `.claude/rediacc_hooks/guards/block_raw_pr_body_edit.py:67` | `-F` converts `true` and numbers and reads `@file`; `-f` sends a literal string. No guard judges which one was meant |
| S10 | `retro-flag-after-bare-dashdash` | `file:.claude/hooks/stop/worklist.py` (the `--retro`/`--evidence` cut at `:860-866`) | `text:.claude/hooks/stop/worklist.py accepted anywhere BEFORE the bare` | only a trailing `--retro` is recovered; one in the middle of the note is silent note text |

**S9 and S10 are confirmed (2026-10-08).** S9: in this session a `gh api -f body=@file` posted the literal path `@file` as a PR comment; it was deleted and reposted with `-F`, which reads the file. S10: the `--retro` cut at `.claude/hooks/stop/worklist.py:864` was narrowed from "`--retro` anywhere after `--`" to "only a trailing `--retro`", so one in the middle of a note is note text. S8 is confirmed by the worker briefs of the same session.

## Risks

- **Phrase anchors make rewording a doc a red.** That is the intent: the person rewording re-points the anchor in the same commit, and the red message gives the new location. The 12-character minimum and the found-elsewhere hint keep this cheap.
- **Over-long phrases break easily.** Guidance in the TRAPS.md header: anchor the distinctive clause, not the whole sentence.
- **The box sig formula exists twice.** L3's equality test keeps the copies in step, as `test-planrec.py` already does for `box_sig`.

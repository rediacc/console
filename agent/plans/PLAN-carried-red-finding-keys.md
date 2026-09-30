# PLAN: Carried reds carry findings, not gates
Status: done
Owner: d778be9d
Updated: 2026-09-30
Depends-On: no-dep -- the guard, the receipt and carried-reds.json all exist
Priority: P2 -- a carried gate can hide a new finding at push time
Concurrency: parallel -- disjoint from the in-flight writers' files
Owns: scripts/ci-runner/findings.ts, scripts/ci-runner/run.ts, .ci/rediacc_ci/log.py, .ci/scripts/quality/check_plan_implementation.py, .ci/config/carried-reds.json, .claude/rediacc_hooks/guards/block_unverified_push.py, .claude/rediacc_hooks/guards/test-block_unverified_push.py, .claude/rediacc_hooks/tests/test_guard_chained_state.py, .claude/rediacc_hooks/tests/goldens/block_unverified_push.jsonl

Worklist #6608cc6e (second half). Designed by a Plan agent 2026-09-30; lead note: check:ci-plan-implementation is not in the quick lane, so a quick receipt never lists it as failed. The current entry's keys cannot come from a quick receipt; decide the entry from the gate's own run (it currently fails only on uncommitted plan boxes in a working tree), and if it is green on HEAD the v2 file starts with an empty `carried` list.

## Problem (measured)

- `.claude/rediacc_hooks/guards/block_unverified_push.py:383-394` turns every entry whose reason is at least 80 characters into a bare gate id. `:401` (unnamed) and `:404` (stale) then compare gate ids only. So while `check:ci-plan-implementation` is carried, a 29th finding of any kind (a new P-A2 box, a P-A3 pointer, a registration or vacuity finding from `check_plan_implementation.py:773-839`) pushes without comment.
- The receipt cannot tell findings apart. `scripts/ci-runner/run.ts:1709` records `failed` as ids only. The captured streams are in `results` (`run.ts:1647`, `GateResult.stdout/stderr` at `pool.ts:98-99`) and are thrown away.
- A `✗` line is the wrong unit. 108 of 130 `scripts/gates/*.ts` and 45 of 156 `.ci/scripts/quality/*.py` print `✗`, and in the sample the `✗` line is usually a summary header with a count in it (`✗ ${issues.length} issue(s)`, `✗ docker npm pins (%d problem(s)):`), with the details on indented lines under it. 92 gate files put `${…length|count|size}` inside a `✗` template. The one gate actually carried today prints `x` rather than `✗` (`check_plan_implementation.py:58,861`) and indents all 28 findings under one header (`:863`). Hashing `✗` lines would give one key for 28 findings, and the key would change whenever the count changed.
- A per-entry regex over the output moves the stability problem into carried-reds.json, and a loose regex quietly carries everything.

## Design

**1. Finding key: an explicit line the gate emits (recommended).** A gate that takes part prints one line per finding, to stdout or stderr:
`::finding::<key>`, where `<key>` matches `^[A-Za-z0-9._:/@#-]{1,200}$` and ANSI is stripped before matching. The gate builds the key from stable identity, never from counts, line numbers or commit shas. For plan-implementation: `P-A2:no-evidence:<rel>#<sig>` and `P-A2:no-row:<rel>#<sig>`, with `sig` from `check_plan_boxes.sig` (`check_plan_boxes.py:144`), which is a hash of the task text. Findings from the other sources (registration, vacuity, held, P-A3, P-A4) use `<rule>:<sha256(msg with [0-9a-f]{7,40} and \d+ masked)[:12]>`. A gate that emits nothing parsable counts as NOT reporting findings. It is never read as "zero findings".
The helpers are `emit_finding(key)` in `.ci/rediacc_ci/log.py` and `emitFinding()` in a new `scripts/ci-runner/findings.ts`. The parser also lives in `findings.ts`.

**2. What the receipt stores.** Add `findings: Record<gateId, string[] | null>` to `Receipt` (`run.ts:1334`), with one entry per failed gate only:
- `string[]` holds the keys, deduped and sorted by plain code-unit order (not `localeCompare`).
- `null` means the gate emitted no valid `::finding::` line, or went over the cap.
- The cap is 512 keys per gate (200 chars each, so at most about 100 KB). Over the cap the value becomes `null` and the runner warns loudly.

Object keys are inserted in sorted gate-id order, so `JSON.stringify` output is deterministic for identical gate output. `wallMs`, `finishedAt` and `utilisation` already vary between runs, so the claim is scoped: the `findings` block is byte-stable, the receipt as a whole is not. The value is built at `run.ts:1709` from `results` using `parseFindings(r.stdout + '\n' + r.stderr)`.

**3. carried-reds.json schema (clean break).**
```json
{"version": 2, "carried": [
  {"gate": "check:ci-plan-implementation",
   "findings": ["P-A2:no-row:agent/plans/PLAN-biome-only-lint.md#<sig>", "..."],
   "reason": ">= 80 chars"}]}
```
- `findings` is a non-empty array of keys, or the string `"*"`.
- Several entries for one gate are allowed, and their keys are unioned.
- `"*"` must not appear alongside keyed entries for the same gate.
- `"*"` has a stricter bar: reason of at least 160 characters, AND the receipt must show `findings[gate] === null`. Whole-gate carry is only for gates that do not speak the protocol yet. A gate that emits keys must be carried by key.
- An entry with no `findings`, or with `[]`, or with no `version: 2`, is refused as a schema error. It is not skipped silently.

**4. Guard logic** (replaces `block_unverified_push.py:381-404`). Inputs are the carried map `gate -> set|"*"` (built from entries that clear the bar) and `rf = receipt.get("findings") or {}`.
- **Gate unnamed** (a failed gate not in the map): refuse, with the existing text at `:409`.
- **Gate stale** (a carried gate not in `failed`): refuse, keeping the "NOT failing" wording, which `tests/test_guard_chained_state.py` asserts.
- For a failed gate carried by `"*"`: if `rf.get(g)` is not None, refuse ("g emits findings; carry them by key, not '*'").
- For a failed gate carried by keys:
  - if `rf.get(g)` is None, refuse ("g reported no parsable findings (or an old receipt); keyed carry cannot be verified -- re-run npm run ci:quick");
  - **(a) new** = emitted minus carried: refuse, naming each key;
  - **(b) stale** = carried minus emitted: refuse, naming each key ("remove them").
- On allow, the NOTE at `:425` prints `gate (N findings carried)` or `gate (*)`.

A receipt with no `findings` field (older run.ts) behaves like `null` for every gate, so keyed carries fail closed.

**5. Other readers.** The only code reader is the guard. Its fixtures (`block_unverified_push.py:142-170`) use the old schema and feed the frozen golden (`tests/goldens/block_unverified_push.jsonl`), and `tests/test_guard_chained_state.py:176` builds an old-schema file. All of these change in the same commit. `scripts/data/doc-registry.md:1024` still names the guard as the only consumer, so no edit is needed there. The `_comment` in carried-reds.json still names `block-unverified-push.sh`, so rewrite it. Mentions in docs and plans are history and are left alone.

## Files

- `scripts/ci-runner/findings.ts` (new): `parseFindings`, `emitFinding`, cap and sort
- `scripts/ci-runner/run.ts`: `Receipt.findings` (:1334), literal (:1709), selftest controls (:810, and the count at :1311)
- `.ci/rediacc_ci/log.py`: `emit_finding`
- `.ci/scripts/quality/check_plan_implementation.py`: emit keys for each finding (:304-340, :861-863), plus a control
- `.ci/config/carried-reds.json`: v2, 28 keys copied from a fresh receipt, `_comment` rewritten
- `.claude/rediacc_hooks/guards/block_unverified_push.py`: logic at :379-430, FIXTURES at :142-170 (+ new worlds)
- `.claude/rediacc_hooks/guards/test-block_unverified_push.py`: cases after :224
- `.claude/rediacc_hooks/tests/test_guard_chained_state.py:176`: v2 fixture
- `.claude/rediacc_hooks/tests/goldens/block_unverified_push.jsonl`: regenerated with `regolden.py block_unverified_push --reason ...`

## Tests (each planted defect has a clean control)

All cases go in `test-block_unverified_push.py`. The receipt uses `put(..., findings={...})` and entries go through `carry()`. K1 and K2 are keys.

1. **New finding.** Plant: receipt `[K1,K2]`, carried `[K1]`, so 2 (refuse), and K2 appears in the message. Control: carried `[K1,K2]` gives 0.
2. **Stale finding.** Plant: receipt `[K1]`, carried `[K1,K2]`, so 2 ("K2"). Control: same as case 1's control.
3. **Keyed carry of a gate that emits nothing.** Plant: receipt `findings: {g: null}`, carried `[K1]`, so 2. Control: `"*"` with a 160-character reason and `null` gives 0.
4. **`"*"` over a gate that does emit.** Plant: receipt `[K1]` with `"*"`, so 2. Control: `null` with `"*"` gives 0, which is the same control as case 3.
5. **`"*"` below the stricter bar.** Plant: `"*"` with a 100-character reason, so 2. Control: 160 characters gives 0.
6. **Old receipt.** Plant: no `findings` field and a keyed carry, so 2. Control: the field present with matching keys gives 0.
7. **Schema.** Plant: v1 entry `{gate, reason}` gives 2. Control: v2 gives 0. Also plant `findings: []` for 2.
8. The existing gate-level cases (unnamed second gate, stale gate, low-effort reason, narrowed run, HEAD vs worktree) are moved to v2 entries, and their expected codes do not change.
9. **Runner selftest** (`run.ts` selftest). Plant: a gate prints `✗ 3 issue(s)` with no `::finding::` line, which must give `null`, not `[]`. Also: duplicate and unsorted keys must come out deduped and sorted; ANSI-wrapped keys must parse; a key with a space must be rejected; 513 keys must give `null`. Control: two valid lines give exactly `[a,b]`.
10. **Emitter control** in `check_plan_implementation.py`. Plant: box C1 must emit `::finding::P-A2:no-row:<rel>#<sig>`. Control: running it twice with a different commit gives identical keys.
11. **Differential.** New FIXTURES worlds `push-red-finding-new` (2) and `push-red-finding-carried` (0), and the golden is regenerated.

## Tasks

- [x] `findings.ts`: parser, cap, sort, and TS emitter, with selftest controls (test 9)
    (ticked) 2026-09-30T14:52:44Z by d778be9d: verified by commit 58f8e3353: parseFindings, the 512 cap, code-unit sort and emitFinding landed with run.ts selftest controls (76 assertions)
- [x] `run.ts`: `Receipt.findings`, built in sorted order at :1709
    (ticked) 2026-09-30T14:52:45Z by d778be9d: verified by commit 58f8e3353: Receipt.findings is built by receiptFindings in gate-id order; the push-clone receipt carried it end to end
- [x] `log.py`: `emit_finding`. `check_plan_implementation.py`: keys for every finding source, plus control 10
    (ticked) 2026-09-30T14:52:46Z by d778be9d: verified by commit 58f8e3353: emit_finding and finding_key landed; check_plan_implementation.py prints a key per finding and control C11 plants six defects
- [x] Guard: v2 parse, the `"*"` bar, arms (a) and (b), null handling, NOTE text
    (ticked) 2026-09-30T14:52:47Z by d778be9d: verified by commit 58f8e3353: parse_carried and carried_verdict implement v2, the 160-char star bar, new and stale arms and fail-closed null
- [x] Guard tests 1-8. FIXTURES worlds from test 11. `test_guard_chained_state.py` fixture
    (ticked) 2026-09-30T14:52:48Z by d778be9d: verified by commit 58f8e3353: 44 cases cover plan tests 1-8 plus the two new FIXTURES worlds; chained-state fixture moved to v2
- [x] `regolden.py block_unverified_push --reason "carried-reds v2: findings-level carry"`
    (ticked) 2026-09-30T14:52:49Z by d778be9d: verified by commit 58f8e3353: golden regenerated with regolden.py reason carried-reds v2; 992 differential and drift cases pass
- [x] Run `npm run ci:quick`, copy the 28 keys from the receipt into carried-reds.json v2, rewrite `_comment`, commit, re-run, and push through the guard
    (ticked) 2026-09-30T14:52:50Z by d778be9d: verified by commit 58f8e3353: superseded as written: the gate exits 0 at a clean HEAD so the v2 file starts with carried empty; the receipt path was proven end to end in the push clone

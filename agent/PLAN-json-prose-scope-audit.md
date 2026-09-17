# PLAN: bring .ci/config and .ci/policy JSON into the prose-style gate's scope

Status: done
Owner: d778be9d
Updated: 2026-09-16

## Tasks

- [x] Convert include-list matching from bare suffix to fnmatch glob, in both discover() (prose_style.py) and _in_scope() (block_prose_style_edit.py guard).
- [x] Add json_prose_lines(): physical-line scanner, decoded string VALUES only, skipping identifier/example keys (patterns, exceptions, text, id, glob, schema, $schema, format, version).
- [x] Wire the .json arm into extract().
- [x] Add SCOPE_BY_SUFFIX[".json"] = "comment" (reuse comment, not a new scope, so R18 stays in effect).
- [x] Add ".ci/config/*.json" and ".ci/policy/*.json" to globals.include in prose-style-rules.json.
- [x] Seed the 3597 (was 3542) baseline with the real pre-existing findings via --write-baseline --accept-new.
- [x] Fix a real bug found along the way: write_baseline()'s by_rule tally counted raw findings instead of deduping by fid, drifting from count by exactly the number of repeated (path, rule, text) triples (8 repeats, +11 in the real tree).
- [x] Regression test for the by_rule fix, proven against the reverted implementation before being kept.
- [x] Verify: check:ci-prose-style, --selftest, pytest, check:ci-python-lint all green; pre-edit guard tested directly for correct in/out-of-scope narrowing.

## 1. Root cause

`.ci/rediacc_ci/quality/prose_style.py`'s `include` list (`globals.include` in `.ci/config/prose-style-rules.json`) had no `.json` entry at all, at either edit-time (the pre-edit hook) or in `check:ci-prose-style`. This was found live: `.ci/config/prose-style-rules.json`'s own `exempt_paths` reasons hit 528 and 993 characters, invisible to the very R18 rule they exist to argue for
(fixed separately in `64269e4ee`, converting `reason` to an optional array of lines).

## 2. The two blockers a naive "just add .json" fix would hit

**Blocker A -- `include` was matched by SUFFIX, not by glob.** `os.path.splitext(".ci/config/*.json")[1]` is `.json`; a path glob written to narrow the scope would silently admit every `.json` in the tree. Fixed by switching both `discover()` and the guard's `_in_scope()` to `fnmatch.fnmatchcase(rel, pattern)` against the raw `include` entries.

**Blocker B -- `.json` would extract ZERO lines and pass silently.** `extract()` dispatched every non-`.md`/`.py` suffix to `cstyle_comment_lines`, which skips anything inside quotes -- in JSON, that is every string. A naive `.json` addition without a dedicated extractor arm would be a green over a corpus of zero prose lines. Fixed by adding `json_prose_lines()`.

## 3. Survey of the actual .json surface (measured against the live tree)

- `git ls-files -- '*.json'`: 742 files.
- After a whole-tree scan, 740 findings outside `.ci/config`/`.ci/policy` are
substantially product copy (translated CLI help strings where second person
  is the correct register, e.g. `packages/shared/src/cli-contract/data/contract.json`) <!-- style-ok -->
and generated projections/session records (`.ci/shadow/w7p5a-status.json`, 77 findings alone; `package-lock.json`; `scripts/data/*.json`). Linting the CLI copy would be wrong in substance, not merely noisy.
- Scoped to `.ci/config/*.json` + `.ci/policy/*.json`: 23 files, 7,878 prose
lines, 55 findings (measured directly against the corpus this session, slightly above the 38 first estimated before the full sweep ran).

## 4. Resolving JSON-string-vs-physical-line

**Physical line for `raw`, decoded string value for `text`.** Not a parsed walk: `json.load` gives no line numbers, so a `Finding` (anchored to a line) could not be built from one, and a decoded-string-length measure would let a long string sitting at deep indentation pass while the file is unreadable as text. This keeps the exact `Line(lineno, raw, text)` contract every other
suffix already has, and rewards the array-of-lines convention this repo already uses in several places (`exempt_why`, `exclude_why`, the now-array `reason`) for free: each array element is its own physical line, measured on its own.

Narrowing is by KEY-SKIP (`JSON_SKIP_KEYS`), not a key-allowlist: an allowlist drops genuine prose sitting under an unexpected key (`.ci/config/docker-npm-pin-exclusions.json`'s `BLOCKER:` reason lives under a key that is itself a file path). A short skip-list for known-identifier/example keys is both safer and smaller.

## 5. gates.lock.json stays out of scope, and why

`scripts/ci-runner/gates.lock.json`'s 6 long lines map 1:1 to `scripts/ci-runner/manifest.ts` (fixed for source readability in `2b67a5122`, independently of this plan). Verified directly: wrapping the TS string literals into multi-line concatenation left `gates.lock.json`'s own lines byte-identical -- JSON cannot represent a continued string, so a long value is one physical line
regardless of how the emitting source is spelled. The deciding fact is not "generated" (several kept-in-scope files are generated too) but that `blocker` is a **typed field**: `scripts/ci-runner/gate-spec.ts` declares `blocker: string`, validated by `.ci/rediacc_ci/core/blocker_validator.py`. Widening it to `string | string[]` changes a typed interface and its validator and tests
-- a real, separate change, not a formatting one. The narrow `include` glob already excludes this file with no extra entry needed.

`.ci/config/python-env-registry.json`, `language-policy-baseline.json`, `plant-proof-baseline.json`, `tracked-credentials-baseline.json`, and `.ci/policy/hook-exec-baseline.json` are the opposite case: their long "note"/"why" strings come from an untyped Python string constant a human edits directly (e.g. `.ci/rediacc_ci/quality/python_env_registry.py:156-168`, itself already
wrapped as multi-line concatenation -- the JSON output is still one line, confirming the same serialization argument). These stay in scope as real, drainable debt: the fix is a future change to what each generator *emits* (a list literal instead of a joined string), not something this pass does.

## 6. Baseline debt seeded

55 pre-existing findings across `.ci/config/*.json` and `.ci/policy/*.json` seeded via `check_prose_style.py check --write-baseline --accept-new`.
Included: R18 (line length) in the generated-baseline `note`/`why` fields
named above; R1/R2 in `prose-style-rules.json`'s own rule descriptions and examples (`.ci/config/prose-style-rules.json:4,27,159-160` etc.) -- permanent and correct, since R1's own description cannot state the rule about that
pronoun without using it, exactly the same shape `agent/pr/*.md`'s <!-- style-ok -->
generated-artifact exemption already argues from a different angle.

## 7. A real bug found while seeding: by_rule drift

`write_baseline()`'s `by_rule` tally counted every raw `Finding` before deduplication by `fid`, while `count`/`grouped`/`findings` (the actual stored data) dedupe by `fid` via a dict/set. `fid` hashes `(path, rule, text)` and not the line number, so the identical template string flagged on two physical lines of one file collapses to ONE entry everywhere except `by_rule`. Measured
live: 8 such repeats inflated `by_rule`'s sum by 11 (3608 vs. the correct 3597), and the same raw count leaked into the printed "N finding(s) frozen" success message. Both fixed to dedupe by `fid` first; pinned by `test_by_rule_sum_matches_count_when_a_finding_repeats`, proven to fail against the reverted implementation before being kept.

## 8. Verification

```
npm run check:ci-prose-style              # 2519 file(s), 3597 baselined, 0 new
python3 .ci/scripts/quality/check_prose_style.py --selftest   # 71 controls
pytest .ci/rediacc_ci/tests/test_quality_prose_style.py       # 163 passed
npm run check:ci-python-lint              # 1051 files clean
```

Plus a direct test of the pre-edit guard's scope narrowing: a real R1 violation inside `.ci/config/*.json` blocks; the identical content inside an out-of-scope `.json` (simulating `contract.json`'s legitimate second-person CLI copy) does not. </content>

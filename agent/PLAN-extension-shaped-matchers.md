# Extension-shaped matchers: the W7 P5 precondition

Status: executing

**Status:** executing. Written and largely executed 2026-09-08 by session `f4da5c2e`.
Commits 1 and 2 are LANDED; all five matchers are RESOLVED (one fixed, two refuted with
evidence, two ported); commit 3 is the only remaining work and is in flight.

W7 P5 deletes 521 bash files. A tool that identifies a gate by the `.sh` extension stops
seeing that gate the moment it is ported, and the failure is SILENT -- a matcher that
stops matching reports nothing at all. After deletion such a matcher matches NOTHING
while its tool still exits 0. **This plan is the precondition on the `W7P5-c` box.**

Two read-only sweeps inventoried the estate, two Plan agents triaged the two hard cases,
and every load-bearing claim below was re-measured by the driver rather than taken from
a report. Both agents refuted the hypothesis they were given, and both refutations are
the useful part.

## What is already fixed

Eleven matchers were found beyond the five widened during wave 9. **Six are done**, each
with a control proven to fire when reverted:

| what | where |
|---|---|
| the `GATE_SHAPED` widening, previously pinned by nothing | `.ci/scripts/test/gates/test-ci-parity.sh` plants a `check_planted_port.py` step |
| dead path constants in ported gates | `.ci/scripts/test/gates/test-gate-paths-exist.sh` scans `*.py`, with `in_doc` and `in_self` skips |
| a ported battery test deriving an unmatchable id | `scripts/lib/gate-header.ts:262` normalises `_` to `-` |
| a ported gate invoking a gitignored path | `.ci/rediacc_ci/quality/ci_scans_tracked_paths.py` and its twin, in lockstep |
| a deleted twin leaving its port unexcused | `.ci/rediacc_ci/quality/toolchain_pins.py` EXEMPT lists |
| a stale duplication verdict from a narrow cache key | `.ci/rediacc_ci/tests/test_shapedup_corpus_sig.py`, new |

## Finding 1: A6 cannot fire on Python at all

The first reading of this was wrong and is corrected here. Widening
`.ci/rediacc_ci/quality/toolchain_pins.py`'s `GATE_PATHSPECS` to `*.py` reports
SEVENTEEN gates as trusting PATH. **All seventeen are FALSE**, and not because A6
confuses a pinned tool with an unpinned one -- every match is PROSE in a docstring or a
string literal, because A6's only comment filter is `^\s*#`. Nine are the same sentence.

The real defect is the mirror image. `GATED_TOOLS` at
`.ci/rediacc_ci/quality/toolchain_pins.py:201` is a hand-written four-tool string and
`A6_INVOKE_RE` at `:464` requires whitespace after the tool name -- a bash command word.
Driven by the driver:

    proc.run(["ruff", "check"])        -> False
    shellcheck -S warning foo.sh       -> True

So A6 has **zero** capability over Python. Two structural facts follow: there is no
Python `toolchain_acquire` (`.ci/rediacc_ci/core/toolchain.py` is a pins reader, no
`check()`, no `acquire()`), and A6 is file-local while a ported gate is shim plus
library, so widening only `.ci/scripts/**` is vacuous by construction.

**Sequence, each step landing on BOTH sides in one commit or the `w7p2-toolchain-pins`
differential breaks:** build `core.toolchain.check(tool, expected)`; move
`python_lint.resolve_ruff`'s rung 2 onto it and re-drive `w7p2-python-lint`; land a
call-anchored per-extension matcher plus the widened corpus and EXEMPT globs; re-drive
`w7p2-toolchain-pins`. The matcher was measured to yield exactly ONE match across 393
files, and is expressible in the bash twin's grep pipeline.

## Finding 2: the duplication counter has been scanning 1 of 43 in one family

Measured by the driver: `git ls-files '.claude/hooks/pre-bash/block-*.sh'` returns **1**;
`git ls-files '.claude/rediacc_hooks/guards/block_*.py'` returns **42**. W5 ported the
guards and `FAMILIES` at `scripts/gates/check-shape-duplication.ts:89-94` still names only the
bash spelling. The gate's own docstring calls that family the one carrying the incident
histories the guards exist for.

`refuseIfEmpty` at `:273-288` cannot see it: it guards the WHOLE corpus, which the
~150-file `scripts/check-*.ts` family satisfies forever. **The fix is a per-family FLOOR,
not per-family non-emptiness** -- one file is not empty and was still a dead family. The
same shape bites P5 the moment it deletes 77 `check-*.sh`, which is 6709 windows leaving
one family silently.

## Finding 3: every line number the counter prints is wrong

Measured by the driver: `import pathlib` is at `.ci/scripts/quality/check_npmrc.py:66`
and `normalise()` reports it at line 4. The string-literal replacement at
`scripts/gates/check-shape-duplication.ts:135-137` does not preserve line count; the
block-comment arm at `:141-152` already carries the fix and states the rule. 275 of 348
files drift by more than 2 lines, worst 814. Two of the 25 `accepted` entries cite lines
that are not where they say.

### RESOLVED 2026-09-09 by box U5, and the tokenizer underneath this plan has MOVED

The coordinate half above is fixed. But the diagnosis was incomplete in a way that
matters to commit 3: the row-preserving wrappers kept the LINE COUNT and still **deleted
the code between the quotes**. Measured with the arms live: 5957 multi-line literal
matches swallowing 36582 newlines across 237 of 352 files, and
`scripts/gates/check-unverified-downloads.ts` normalising **318 lines to 21** -- its trigger an
apostrophe inside a REGEX CHARACTER CLASS at `:60`, not the apostrophe-in-a-message this
plan describes.

Fixing the quote arm exposed two siblings it had been hiding, so the tokenizer is now ONE
left-to-right pass rather than four sweeps: a backtick inside an awk pattern in a shell
single-quoted string cost `.ci/scripts/quality/check-trap-registry.sh` 296 of its 394
normalised lines, and the block-comment stripper ran the same hole in reverse, a glob's
`*/` closing a `/*` opened 27 lines earlier.

**Every count below that predates 2026-09-09 is now stale, and the direction is UP.**
Corpus 53174 -> 68274 normalised lines, 222 files grew and none shrank; windows 42979 ->
54630; shapes at 3+ copies 244 -> 279, of which 190 keep their fingerprint under both
tokenizers. `accepted` SHRANK 25 -> 12 -- 9 were already dead, 4 are now excluded
mechanically by `isSharedHelperCall`, 3 re-keyed.

Two latent defects in the gate itself were found and fixed on the way, both of which
would have cost this plan its record: `--seed` wrote only `{generated, files, shapes}`,
so a single `--seed --force` would have DELETED all 25 hand-written BLOCKER reasons; and
`accepted` had no liveness half at all, which is why 9 of the 25 had silently died.

## EVERY `scripts/check-*.ts` PATH IN THIS PLAN MOVED, 2026-09-09

W9 P2 relocated all **125** `check-*.ts` from `scripts/` into `scripts/gates/`, and zero
remain at the old path. This plan cites the old location throughout -- `FAMILIES` at
`scripts/gates/check-shape-duplication.ts:89-94`, the string-literal arms at `:135-137`, and the
"~150-file `scripts/check-*.ts` family" the per-family floor was written for.

**Read every such citation in this document as `scripts/gates/`.** The gate itself has
already been repointed: its `FAMILIES` row is now
`{ pathspec: 'scripts/gates/check-*.ts', floor: 100 }`, and the family is 125 files, not
the "~150" this plan estimated.

**The corpus this plan is measured against therefore moved twice in one day** -- once when
U5's tokenizer rewrite grew it from 53174 to 68274 normalised lines, and again when the
files changed directory. Commit 3 must re-derive; nothing measured before 2026-09-09
survives either change.

**A transient state worth naming so it is not mistaken for a defect:**
`check:ci-shape-duplication` is RED while that move lands, with
`ERR_MODULE_NOT_FOUND ... scripts/gates/check-shape-duplication.ts`, because `package.json` still
resolves the old path. That is the move in flight, not the gate: the driver repoints
`package.json`, `manifest.ts` and `gates.lock.json` from the writer's fragments, and those
three are the reason W9 P2 runs alone in its wave.

## Finding 4: the 62 shapes are not the scaffold, until the coordinates are fixed

The 16-copy shape is the findings report wrapped by the formatter, not the `sys.path`
hop -- `normalise` keeps identifiers, so each entry point's `from rediacc_ci.quality
import <mod>` line makes its windows unique. Fix the coordinates and a **44-copy** shape
appears, and that one IS the scaffold.

It is extractable, and the constraint was settled with ruff rather than argued: a helper
FUNCTION call before the imports is `E402`, a stdlib import after the hop is `I001`, but
`import _cipath  # noqa: F401` is clean. **That E402 ruling was re-confirmed independently
on 2026-09-09 under ruff 0.16.1** while box PRE-A1 swept the remaining hops: `sys.path`
mutation before a module-level import is exempt and NOTHING else is, so
`paths.on_sys_path("/x")` before an import is `E402` where the bare insert is not.

**AND THE 44-COPY FIGURE IS NOW STALE.** It was measured with the broken tokenizer. The
`FAMILIES` widening onto `.ci/scripts/quality/check_*.py`,
`.ci/rediacc_ci/tests/gates/test_gate_*.py` and `.claude/rediacc_hooks/guards/block_*.py`
reported 76 new shapes headed by that 44-copy scaffold, and both numbers were taken
before the tokenizer saw the code the quote arms were eating. **Commit 3 must RE-MEASURE
the widening before adopting any of those figures**, and the scaffold itself is smaller
than it was: PRE-A1 took the hand-written `sys.path` file set from 44 to 36 on the same
day, so part of what that shape counted has already been extracted by a different route. A second, unambiguous extraction: a
byte-identical `def subject(gate)` in three watchdog gate tests belongs in `harness`.

## The three commits, in order, BEFORE W7 P5

1. **Detector.** ~~Newline-preserving literal replacement~~ **DONE 2026-09-08** --
   coordinates are exact (`check_npmrc.py:66` reports 66, was 4), window count
   44446 -> 48613, cost was the 4 predicted shell shapes plus 5 overlapping
   sub-windows, all accepted per-fingerprint. ~~per-family floors~~ **DONE** --
   `FAMILIES` is a `{pathspec, floor}` table checked per family in `tracked()`, proven
   to fire by raising the pre-bash floor to its pre-port 43. Family D's floor of 1 is
   recorded as a scar at the row. ~~Python-aware `isImportish`~~ **DONE** (`from X import Y`, with a
   control that reds when the alternative is removed). ~~content-free continuation~~
   **DONE** as `isContentFree`, majority rule like its siblings: zero new findings on the
   existing corpus and 245 shapes still at 3+ copies against an empty seed. STILL TO DO
   in this commit:
   content-free-continuation and shared-helper-call exclusions; per-family floors. Costs
   4 accepted entries, each reusing `ddcaba9721fd`'s argument verbatim. On the existing
   corpus these predicates add ZERO findings, and with an empty seed the tree still
   yields 133 shapes -- the gate keeps its teeth.
2. **Extraction, while the corpus still cannot see it.** `_cipath.py` plus the 75 entry
   points; `harness.watchdog_subject()` plus its 3 callers. Green by construction, and
   provable against the twins P5 has not yet deleted. **This is why it goes before P5.**
3. **Widen** to three families, not two: `check_*.py`, `test_gate_*.py`, and
   `guards/block_*.py`. About 11 shapes remain, each accepted against a precedent
   already in the file.

## Finding 5: the class is a PREDICATE class, not only a glob class

Four members found by asking, of each matcher, "what else here assumes TypeScript?" --
each fixed with a control proven to red when reverted:
`check-shape-duplication.ts` `isImportish` (no `from X import Y`) and `isMessageish`
(knew `echo "S" >&2` and `print(..., file=sys.stderr)`, not `sys.stderr.write("S")`, so
half the Python report idiom counted as copied code); `validate-cli-examples.ts`
`COMMAND_PATH_IGNORE` (knew `__tests__`/`.test.ts`/`.spec.ts`, not `tests/` or
`test_*.py`); `scripts/lib/command-path-checker.ts:174` (comment skip knew `//`, `*`,
`/*`, not `#`).

`isMessageish` is deliberately NOT widened to `gate.log_fail`: a repeated call to an
already-shared helper is the separate exclusion seed entry `98b21fa52e5d` names, and a
control keeps it out.

**`validate-cli-examples`'s `.py` globs are DEFERRED**, cost measured: **17 -> 7 -> 6** as
the two exclusion fixes landed. The last six are commands quoted in DOCSTRINGS, which no
`#` skip reaches; the scan needs the triple-quote state machine
`test-gate-paths-exist.sh` already grew. Landing it before that means six false errors
against a gate whose whole job is quoting broken commands.

## The five matchers: all RESOLVED, and not all of them were defects

Closing this section honestly matters more than closing it fast — two of the five turned
out NOT to be the bug, and recording that is the difference between a plan and a to-do
list someone ticked.

**FIXED, with its bash twin mirrored.** `.ci/rediacc_ci/quality/workflows.py:632`
`check_gh_slurp_jq` walked `.ci/scripts` taking only `.sh`, so once W7 ported the quality
gates it stopped reading 72 `.py` files that mention `gh`. Widened to both — and the first
attempt FAILED ITS OWN CONTROL, which is the instructive part: a per-line "ends with an
open bracket" continuation test misses the commonest Python spelling, because in a wrapped
`subprocess.run([...])` the `"gh", "api", …` line opens nothing, so the join ends two lines
before `--slurp` and `--jq` meet. Replaced by a running BRACKET DEPTH. Mirrored into
`.ci/scripts/quality/check-workflows.sh:453` because the port had silently DIVERGED and the
shadow assertion was passing only because no offender exists on this tree — a green for the
wrong reason.

**PORTED (the predicate class, not the glob class).**
`.ci/rediacc_ci/quality/git_op_conditionals.py` detection is bash idiom (`[[ ]]`, `$?`), so
widening the glob alone would have scanned Python, found nothing, and LOOKED widened.
Predicate ported and mirrored; corpus now 116 shell + **186 python** where the python half
was 0. `scripts/gen/validate-cli-examples.ts` landed its `.py` globs with the residue driven
**17 → 7 → 6 → 5 → 1 → 0**.

**REFUTED, and they must NOT be widened.** `scripts/gates/check-ci-parity.ts:577`/`:586` is a set
equality in both directions between the on-disk battery and the manifest's `qualityGateTest`
entries: a deleted twin still declared fires by name. `.ci/rediacc_ci/quality/pool_writer_safety.py:543`
refuses on an empty set. Both are DIFFERENTIALS against what `run-all.sh` actually runs, so
under the pin rule they must keep naming the twin, and both fail LOUD during P5 rather than
silently. The same holds for the four FLOOR/COUNT findings (`gate_id_convention.py:229`,
`shfmt.sh:71-73`, `test_battery.py:352`, `pool_writer_safety.py:545`).

## Two premises in this plan were WRONG, found by measuring

Recorded because a plan that hides its own corrections teaches nothing.

1. **The six `validate-cli-examples` residuals were not docstrings.** This plan said they
   were and prescribed a triple-quote state machine. None of the six was: one `#` comment,
   four planted control fixtures, one prose string. The state machine was built anyway,
   measured at ZERO change across 386 tracked `.ci/**/*.py`, and REMOVED.
2. **`.claude/rediacc_hooks/**/*.py` is 58 files; `*.py` is 64.** Git's default pathspec is
   wildmatch WITHOUT pathname mode, so `**/` demands a literal slash and drops the six
   top-level modules — including `hookio.py`, which DEFINES `git_out`, the helper every
   finding flows through. Any count in this plan using the `**/` spelling is short by six.

## One defect found on the way, fixed, and outside every brief

`.claude/rediacc_hooks/guards/warn_remote_drift.py:197`: `hookio.git_out` without `want_rc`
returns `""` on failure indistinguishably from success, and `shellscan.py:582` then joins
`this_root + "/" + hint`, so a relative `-C nested` resolved to `/nested` instead of
`<repo>/nested`. Guarded with ALLOW rather than a block: an advisory drift hook that cannot
establish where it is has no standing to judge a command.


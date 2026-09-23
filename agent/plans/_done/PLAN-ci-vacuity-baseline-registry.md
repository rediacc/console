# PLAN: Python control plants — make a vacuous mutant impossible, not merely reported
Status: done 2026-09-22 -- the last box (`test_gate_python_control_plants.py`) is now real, 7/7 passing, independently re-run by session d778be9d after the writer's own report (not trusted on claim alone). Zero open boxes remain.
First-Seen: 2026-09-17
<!-- Was `done` until 2026-09-09, which was false: `done` is in FINISHED_STATES and this
     plan still carries one real, unstarted box. The file it asks for,
     .ci/rediacc_ci/tests/gates/test_gate_python_control_plants.py, does not exist. A plan
     whose status outruns its boxes is the thing the plan-record machinery exists to
     catch, and this one is owned by f4da5c2e, so it was mine to correct. -->
Owner: d778be9d (adopted from f4da5c2e 2026-09-22)
Updated: 2026-09-22

The filename says "baseline registry" because that is what the triage predicted. **The design rejects a baseline.** The name is kept so the worklist pointer resolves; see §2 for why the instrument changed.

## Tasks

- [x] Add `plant()`, `plant_re()` and `VacuousPlantError` to `.ci/rediacc_ci/controls.py`, raising on a missing needle, on `old == new`, and on a byte-identical result
- [x] Cover the harness in `.ci/rediacc_ci/tests/test_controls.py`, both directions, with `old == new` as its own distinct refusal
- [x] Convert the genuine plants in the other 8 files — 38 sites across drill_verdicts,
      release_bump_skip, renet_tier_map, review_cap_coherence, release_signing_coverage,
      autopilot_breakpoint_alignment; every selftest exits 0
- [x] Convert `.ci/scripts/quality/check_plan_record.py` — 17 mutant constructions on `clean`, gate exit 0, identity plant proven to raise
- [x] Convert `compose_env.py` (2), `npmrc.py` (3), `account_portal.py` (1) — all selftests exit 0
- [x] Convert `.ci/rediacc_ci/quality/review_turn_capacity.py` (5 sites) and DELETE the identity leg that was at `:480`
- [x] Adjust the floors this file's conversion moved: its derived floor `+3`→`+2`, and the external `>= 12`→`>= 11` in `.ci/rediacc_ci/tests/test_quality_review_turn_capacity.py:218`, each with its reason recorded in place
- [x] Rename the LOCAL `plant` helpers to `expect_finding` — `.ci/scripts/quality/check_plan_record.py` (13 calls)
      and `cli_doc_coverage.py` (8 calls). A THIRD remains at
      `.ci/rediacc_ci/tests/gates/test_gate_watchdog_monitor_ordering.py:98`, left alone because
      that tree is a live writer's; the gate's resolve-the-import rule covers it regardless
- [x] Write `.ci/scripts/quality/check_python_control_plants.py` — 9 controls pass; it
      resolves `plant` to the IMPORT so a local `def plant` earns no credit
- [x] RESOLVE THE FALSE POSITIVES — settled with TWO shape-based exemptions, no
      allowlist: sibling substitutions in one call are normalisation, and a result
      compared back against its own source already carries a vacuity proof. Real tree
      now 128 modules, 69 plant() sites, ZERO findings; 13 controls; both exemptions
      planted open and both mirrors fire
- [x] Make zero discovered `plant()` sites a RED distinct from an empty directory — both arms driven against real starved trees via `PY_CONTROL_PLANTS_ROOT`, and the helper returns WHICH arm fired so the two cannot cover for each other
- [x] Add `.ci/rediacc_ci/tests/gates/test_gate_python_control_plants.py` with the real-tree plant, the historical `max_turns=140` plant, and the unmodified-copy mirror
- [x] WITHDRAWN, not done: the anti-vacuity harness copies `.ci/rediacc_ci` wholesale, so it feeds this gate its real inputs and cannot starve it. A registry row claiming a diagnostic that cannot fire would be a false entry in a hand-verified list; the coverage lives in the gate's own controls instead
- [x] Correct the disclosure in BOTH `control_vacuity` twins together — `py_unscanned` is now a delegation naming the owning gate; `.ci/rediacc_ci/tests/test_quality_control_vacuity.py` 11/11
- [x] Registration applied: `package.json` key, `manifest.ts` entry in `quality-static`, `gate-bind --write` emitted the step at `.github/workflows/ci-quality.yml:292`, `gen:gates-lock` → 459 gates. Reachable from `npm run ci`. NOTE: `gate-bind` scans only git-TRACKED files, so a new gate must be `git add`-ed to be discoverable at all

## 0. What I got wrong, corrected before anything else

I raised this finding as *"`check:ci-control-vacuity` is blind to 50 of 127 live quality gates, and widening the glob reds the tree with 31 findings because 31 of the 50 have no `--selftest`."* **Two of those three clauses are wrong**, and I verified the corrections against the tree rather than accepting them:

- **`--selftest` is not the signal, and "no control" is not a finding.**
`.ci/rediacc_ci/quality/control_vacuity.py:280-281` reads `if not has_control(lines): continue`. A gate with no control is SKIPPED. So widening the glob does not produce 31 findings; the 31/33 count measured a different gate's subject entirely.
- **The gate's predicate is narrower than "stops a gate being green when it cannot
fail."** Three stages at `:280-289`: no control → `continue`; control built by construction → `exempt`; only `proves_plant_landed` failing is a finding.
- The count of `check-*.sh` (77) and `check_*.py` (50) was right, but the surface
that matters is larger: `.ci/rediacc_ci/quality/` holds 77 ported gate modules that the disclosure at `.ci/rediacc_ci/quality/control_vacuity.py:388` does not count at all, and that is where the debt actually lives.

## 1. The real finding, and it is sharper than the one I filed

`.ci/scripts/quality/check-control-vacuity.sh:183-193` says, verbatim:

> of the 21 Python gates, ZERO build a control mutant by substitution … **What must
> not happen is that changing silently.** … so the number of unscanned gates is now
> part of the green line.

**It changed, and it changed silently.** 21 → 50. The property went from true to false. The tripwire its author installed was a number inside a SUCCESS message — which `shadow-gate.ts` classifies as chatter, not a finding, as `.ci/rediacc_ci/quality/control_vacuity.py:390-395` itself notes. The gate predicted its own failure mode and implemented the alarm as something nothing
reads.

**The class is: a disclosure is not a control.**

Measured day-one set: 12 files, 71 substitution-built plant sites, 3 proof assertions in total. Largest offender `.ci/scripts/quality/check_plan_record.py` (20 sites, 0 proofs).

**One live defect, verified at `.ci/rediacc_ci/quality/review_turn_capacity.py:480`:**

```python
_FIXTURE_HEALTHY.replace("max_turns=140", "max_turns=140").replace(
```

`old == new` — provably vacuous. A dead leg chained ahead of a real `.replace`, so it moves no verdict today, and it sits in the port of the very gate `control_vacuity` uses as its own control (`CONTROL_GATE`, `.ci/rediacc_ci/quality/control_vacuity.py:150`).

## 2. Why NOT a shrink-only baseline

A baseline is right under three joint conditions, and this meets none:

1. **Debt too large to drain in one change.** Language policy: 521 paths, each its
own port. Here: 71 sites, one mechanical rewrite.
2. **Heterogeneous fixes.** Here every GENUINE PLANT is the same three tokens.
**CORRECTED 2026-09-08 while converting:** the count of 71 is NOT 71 plants. It includes `.replace` used for PARSING and for NORMALISING BOTH SIDES OF A COMPARISON, which must NOT be converted — `.ci/rediacc_ci/quality/release_key_canonical.py:651-652` strips newlines off `welded` and `_ARMOR` to compare their content, and wrapping either in `plant()` would break a passing test,
since `plant()` raises when the needle is absent and is a mutant constructor, not a normaliser. So the conversion is per-site judgement, not the mechanical rewrite this plan first claimed. That does not change the verdict against a baseline — it strengthens it, because a baseline would have frozen the parsing sites as debt they are not.
3. **No harness could make the class impossible.** Here one can:
`.ci/rediacc_ci/controls.py`, already imported by all 12 files' selftests.

Condition 3 decides it, and this repo has written the argument down twice already — `scripts/lib/shrink-only-baseline.ts:25-31` (*"a class, not an instance… seven chances to drift"*) and the duplication table in `.claude/skills/testing/gates.md`. **71 hand-written no-op-prone substitutions is that table's next row.** A baseline would freeze the instances and leave the class
unowned.

Doctrinal objection too: `check_language_policy.py` states the baseline is drained in the same commit that fixes files, never to make a red go away. If the whole set CAN be drained in the landing change, seeding a baseline is seeding it to make a red go away. **A baseline whose correct lifetime is one commit is a suppression with better manners.**

Instrument instead: a harness plus a gate that requires the harness. A `plant()` that cannot produce a vacuous mutant, and a gate refusing raw substitution inside a control region. Zero legitimate exemptions, so no exemption mechanism — the strongest possible reason not to build one.

## 3. The edit set (anchors verified against the tree)

`.ci/rediacc_ci/controls.py` gains module-level `plant` / `plant_re`, free functions rather than `Controls` methods because several files build fixtures at module level where no `ctl` exists. `plant()` prints nothing — it is a constructor, not an assertion.

The 12 files convert mechanically. **Watch the derived floors**: removing the now redundant proof at `.ci/rediacc_ci/quality/review_turn_capacity.py:499-503` drops a `ctl.check`, so the `+3` at `:489` becomes `+2`. `.ci/scripts/quality/check_plan_record.py` needs the `sys.path` hop spelled as in `.ci/scripts/quality/check_npmrc.py:17`.

The new gate is NOT a widened `control_vacuity`. Three reasons in descending force: the live gate is the bash twin (`package.json:140`) and `.ci/rediacc_ci/tests/test_quality_control_vacuity.py:189` requires byte-identical output, so widening means writing an AST-equivalent predicate **in bash**; invariant 5 forbids deleting the twin, so widening means maintaining a bash
Python-parser until W7 P5; and the predicate is genuinely different — `control_vacuity` asks "is there a proof?", this asks "did you use the harness?".

Predicate: inside a control region, `X.replace(...)` / `re.sub(..., X)` where `X` is
a **bare `Name`** is a finding; `plant(...)` is not. The bare-`Name` restriction IS the exemption mechanism and needs no allowlist — it is what excludes `datetime.replace(tzinfo=…)` and `str(ROOT).lstrip("/").replace("/","-")`.
Measured: with the restriction 12 files, without it 14, and both extras are false
positives.

The `control_vacuity` disclosure edit must land in both twins in one commit or `.ci/rediacc_ci/tests/test_quality_control_vacuity.py:189` reds — which is the control working.

## 4. Controls — fires on a plant, silent when clean, both directions

On `plant()` itself: happy path returns; missing needle raises; **`old == new` raises with its own distinct message** (this is what catches `.ci/rediacc_ci/quality/review_turn_capacity.py:480`, so it is not hypothetical); empty subject raises; `plant_re` both ways; a multi-occurrence mirror.

On the detector, every rule with its mirror: raw substitution in a control region is a finding / the `plant()` form is silent; a non-`Name` receiver is silent; a `.replace` outside a control region is silent; one inside a docstring is silent.

**The anti-vacuity control this design most needs**: the discovered set is the `plant()` call sites, so if the harness is ever renamed and the gate not updated, every module looks compliant and the gate goes green having verified nothing. Zero `plant()` calls found must be RED, with a message distinct from "empty directory".

On the real tree: the gate exits 0 as landed; rewriting one `plant()` back to a raw substitution in a COPY reds and names the file; reintroducing the historical `max_turns=140` identity reds; and the unmodified copy exits 0, without which the first two are satisfied by a gate that reds on everything.

## 5. Ordering, and why a W7 P4 cutover needs no hand edit

Three commits, one PR: harness (changes no verdict) → conversion (all 71 sites; any site that cannot be converted is a real finding fixed in that same commit, which is the language-policy drain rule without the baseline file) → gate (plus registration, bind, anti-vacuity row, twin disclosure).

At the third the tree is already clean, so **the gate is green the day it lands and its first red is a real regression.** That property is exactly what a baseline would have purchased, bought with ordering instead.

Cutover interaction is the load-bearing advantage over a baseline. Scope is two globs, not a file list, so a port landing under `.ci/rediacc_ci/quality/` is in scope the moment it exists: no registration, no baseline row, no hand edit. If its selftest carries substitution plants the gate reds **in the cutover PR**, where the author is already in the file. With a baseline, every
such cutover would need a hand-added row in a file whose whole point is that rows only ever leave it — the first author who added one to get a cutover through would have inverted the instrument and the second would have cited the first.

Sequencing: the conversion touches 11 files under `.ci/rediacc_ci/quality/`, the tree
W7 P4 is actively rewriting. Land as one PR and rebase rather than interleaving.

## 7. MEASURED ON FIRST RUN: the no-false-positives claim is wrong

The gate ran against the real tree and produced 7 findings. Judged one by one:

- **2 were my implementation bug.** `.ci/rediacc_ci/quality/no_otlp_creds.py:373` — `SPACE_RE.sub("", " \t\n")`.
For `.sub`/`.subn` the RECEIVER is a compiled regex, not the fixture; that call exercises the pattern itself. Fixed by narrowing `SUBSTITUTORS` to `.replace` alone.
- **1 was a genuine miss, now converted.** `.ci/scripts/quality/check_plan_record.py:1090`
`with_ph.replace("Status: parked", "Status: compacted", 1)` is a real mutant on a lowercase local, which the earlier `_UPPER`/`clean` sweeps did not reach.
- **4 REMAIN AND ARE NOT CONVERTIBLE**, which is the finding:
  - `.ci/rediacc_ci/quality/release_key_canonical.py:651-652` normalise BOTH SIDES of a comparison
    (`welded` vs `_ARMOR`, "one line break gone"). Not mutants.
  - `.ci/scripts/quality/check_plan_record.py:1155-1157` is a plant with a DELIBERATE FALLBACK CHAIN:
    `drifted = cen.replace(A)`, then `if drifted == cen: drifted = cen.replace(B)`.
    It already handles its own no-op, more cleverly than `plant()` can — `plant()`
    raises on the first miss and would destroy the fallback.

**SETTLED 2026-09-08 by two SHAPE-based exemptions**, and neither is an allowlist, so §2's argument survives intact:

1. **Sibling substitutions in one call are normalisation.** Two of them as arguments
of the same call are normalising both sides of a comparison; a mutant is never compared against another mutant of its own shape.
2. **A result compared back against its own source already carries a vacuity
proof.** This deliberately mirrors `control_vacuity`'s `proves_plant_landed`, so the two gates agree instead of contradicting. It exempts the fallback chain, which is STRONGER than `plant()` can be — `plant()` raises on the first miss and would destroy the second attempt.

Rejected: `flows into a gate invocation` (dataflow this cannot do cheaply) and a
`soft=` variant of `plant()` (a vacuity harness with an opt-out is not one).

Shipping the gate at 4 known false positives would produce exactly the outcome §2 warns about: a gate suppressed within a day, still looking like coverage.

## 6. Residual risks, named now

- The gate keys on the function name `plant`. Real coupling, and **no longer
hypothetical**: `.ci/rediacc_ci/quality/cli_doc_coverage.py:282` already defines a LOCAL `def plant(...)` that is not the harness, with ten call sites. A gate that only counts `plant(` would read those ten as compliant while they use no harness at all — a false negative, which is worse than the blindness being fixed. The gate must therefore resolve the NAME to the import, not match
the token; the zero-sites refusal does not cover this and is a separate mitigation. Both local helpers get renamed regardless.
- A `Name` bound to a non-string whose `.replace` means something else inside a
control region would be flagged. Measured across all 127 files: **zero** today. The answer to the first one is a named divergence at the call site, not an allowlist file.
- `.ci/scripts/quality/check_plan_record.py` has no `---- gate ----` header; converting it must not
drift into a registration change.

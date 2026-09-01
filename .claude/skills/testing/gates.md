# Static gates — `check:ci-*`

For defects visible without running the product: wiring, source invariants,
content shape, a rule that must hold across a corpus.

## Where the file goes

`scripts/check-*.ts`, `packages/*/scripts/check-*.ts` (a gate about www belongs
beside www), `.ci/scripts/quality/check-*.sh` or `check_*.py`.

## Three-point wiring, all three required

1. `package.json` → `"check:ci-<name>": "tsx scripts/check-<name>.ts --selftest && tsx scripts/check-<name>.ts"`
2. `scripts/ci-runner/manifest.ts` → an entry with `id`, `run`, `gate: true`, `leaves`, and its `ci` step
3. `.github/workflows/ci-quality.yml` → the step named in the manifest

`ci.yml:479` calls `ci-quality.yml`, so a wired key is reachable from `npm run ci`.

## Proof

- `npm run check:ci-parity` — the local set and the CI surface agree BOTH ways
- `.ci/scripts/quality/check_gate_reachability_coverage.py` — no registration is unreachable
- `npx tsx scripts/ci-runner/run.ts --list | grep <key>` — it is in the set that actually runs
- **plant the defect**: re-introduce the bug, run the gate, require exit 1

## The trap that costs a whole gate

An assertion that re-asks a question the code already answered cannot fire.
Real case, 2026-08-24: `units.length && SHELL_LANGS[lang] !== 1`, where the
function already returned `[]` for a non-shell language. The two halves were the
same question, the conjunction was dead, and the planted defect came back green.

Judge the code against something the code does not own — the gate's own list,
an independent corpus, a separate oracle.

## Anti-vacuity

Discovering zero inputs must FAIL, not pass. Print the counts on success so a
collapse is visible in the log instead of inferred from an absent complaint.

## Before you write the 3rd one

Twice this repo reached this by hand and wrote it down: `shrink-only-baseline.ts:25-31`
(*"a class, not an instance … seven chances to drift"*) and
`block-adhoc-sanctioned.sh:4-8` (a new class is *"a row rather than a 22nd copy"*).
Nothing asks on its own. Measured 2026-09-01, already past a third copy:

| shape | copies | the harness that should own it |
|---|---|---|
| the assertion closure | **35** of 101 `check-*.ts` | none — `shrink-only-baseline.ts:181` factors the control *data*, not the loop |
| the `test-helpers` preamble | **85** of 118 `test-*.sh` | `.ci/scripts/test/lib/test-helpers.sh` |
| `mktemp -d` + hand-written `trap` | **28** | `with_temp_dir` (`test-helpers.sh:73`), used by 26 |
| colour constants | **28** inline, **7** redeclared | `scripts/utils/console.ts`, TTY-gated, imported by 10 |

Not hypothetical: five copies inline unconditional `\x1b[…` and pipe raw escape bytes into
non-TTY CI logs, while `scripts/utils/console.ts:8-15` TTY-gates them for its ten importers.
Copying is sometimes right, and the answer is a **named divergence**, not a shrug:
`run_gate()` is duplicated 23× with three incompatible return contracts. Say which.
Never the findings report — 10 gates, 10 distinct hashes. Count duplication in the
scaffolding, never in the reasons.

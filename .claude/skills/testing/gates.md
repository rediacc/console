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

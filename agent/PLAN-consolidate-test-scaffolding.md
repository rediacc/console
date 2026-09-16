# Consolidate the duplicated gate-test scaffolding

Status: done
Owner: 8f55d4f0

## Why

Three gate tests carry byte-identical scaffolding that 137 of their 143 siblings get from
`.ci/scripts/test/lib/test-helpers.sh`:

- `.ci/scripts/test/gates/test-toolchain.sh`
- `.ci/scripts/test/gates/test-run-sh.sh`
- `.ci/scripts/test/gates/test-devbox-probes.sh`

Each declares the same `ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"`,
the same `fails=0` and `count=0`, the same `ok()` and `no()`, and the same
`"<subject>: $fails of $count control(s) failed"` exit block. The bodies were diffed and
differ only in the subject label. None of the three states a reason for not sourcing the
shared helper, so this is duplication rather than divergence.

The count reached three today because W6 extended `test-run-sh.sh` from 14 controls to 23.
It was two before, under the duplication gate's threshold.

## The trap this repeats, and why a subset conversion is forbidden

`.ci/scripts/lib/gate-controls.sh` was extracted earlier for exactly this shape after the
duplication gate caught a `_c()` tally at three copies. The extraction converted ONE of the
three. That took the count to two, below the gate's threshold, so the gate went quiet while
the new library's header asserted the job was done. The remaining two were found today, by
a different route, and converted.

So: all three, or none. Converting two would silence the gate at its own threshold and
leave the third looking finished.

## What is NOT being changed

`test-helpers.sh` speaks `log_pass`/`log_fail`/`assert_eq`. These three speak `ok`/`no`
with a running tally. Rewriting roughly a hundred call sites across three files to the
helper's vocabulary is not consolidation, it is a rewrite with its own defect budget. The
tally vocabulary is added to the shared helper instead, so the call sites do not move.

## Boxes

- [x] Added `ok`, `no` and `tally_finish` to `test-helpers.sh` with their counters.
      `gate_tally_reset` was NOT needed and was dropped: the counters initialise at
      source time and each gate test is its own process, so nothing ever needs to reset
      them mid-run. A reset verb with no caller is a seam that invites misuse.
- [x] Converted all THREE files in one change; every `ok`/`no` call site untouched.
- [x] Proved output unchanged: stdout and stderr captured separately before and after
      for all three. Six streams, all byte-identical, exit 0 each.
- [x] Proved the shared tally still FAILS: a fixture with a planted failing assertion
      prints `✗ probe: 1 of 2 control(s) failed` and exits 1, while the clean run prints
      `✓ probe: 2 control(s) passed` and exits 0.

## What the design got wrong

**The scaffolding blocks were not quite byte-identical after all, and a strict match
caught it.** `test-run-sh.sh` and `test-devbox-probes.sh` separate `ok()` from `no()` with
a blank line; `test-toolchain.sh` does not. The first conversion pass asserted an exact
block and refused on the first file rather than converting two of three and reporting
success. That refusal is the reason all three moved together, so the mismatch was worth
more than the retry cost.

The claim in the Why section stands with that correction: the bodies of the FUNCTIONS are
identical, and it is only the whitespace between them that varies.

## Outcome

`check:ci-shape-duplication` went from 13 NEW shapes at 3+ copies to 4, and none of the
four is in a file this plan touched. `check:ci-shell-lint` and `check:ci-shell-format`
both exit 0.

The four remaining shapes are a separate finding and are NOT this plan's business. One of
them was deliberately left alone by the media workstream on the reasoning
this plan opens with: converting its single copy would take that shape from 3 to 2 and
silence the gate with the other two unfixed.

That shape's fingerprint is deliberately NOT reproduced here. check-shape-duplication
emits a 12-hex id, and check:ci-plan-citations judges any 9-to-40 hex token in a plan as
a blob or commit citation and refuses it when it resolves to neither, which is the right
rule: 37 of 71 commit-shaped tokens already in agent/ are dead pointers. An id that is
not a git object has no business looking like one. Print the current set instead, which
also cannot go stale the way a copied id does:

    npm run check:ci-shape-duplication


## Record

Triaged: worklist #d3e48191, ticked with the evidence above.

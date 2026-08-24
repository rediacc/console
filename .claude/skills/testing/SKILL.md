---
name: testing
description: Where a regression test for a given fix belongs in this repo's CI, and what counts as proof it runs. Use when a fix has landed and something must stop it coming back, or when a gate is demanded and a check-*.ts is the wrong instrument.
user-invocable: false
self-improving: true
---

# testing — which surface owns this fix

`ci.yml` has six regression surfaces. Picking the wrong one produces a test that
passes without covering anything. Route first, then open that surface's file.

| the fix changes | surface | file |
|---|---|---|
| source-level invariant, wiring, content shape | static gate | [gates.md](gates.md) |
| CLI or renet behaviour on a real machine | E2E | [e2e.md](e2e.md) |
| VM provisioning, KVM, `rdc ops` | ops | [ops.md](ops.md) |
| install, update, packaging, `rdc.sh` env | install | [install.md](install.md) |
| a pure function, a parser, a formatter | unit | [unit.md](unit.md) |
| a `.claude/hooks` script | hooks | [hooks.md](hooks.md) |

## The two questions, in order

1. **Could the defect be seen without running the product?** Yes → static gate.
   No → one of the runtime surfaces. A behavioural bug given a `check-*.ts` gets
   a gate that asserts the source still looks right, which is not the same claim.
2. **What proves it runs?** Not that the file exists. Each surface's file names
   its own proof; a gate nobody's job selects is worth nothing.

## Rules that hold on every surface

- **Control first.** Write the failing case, watch it fail, then fix. A test
  written after a green run asserts the green.
- **Plant the defect.** Re-introduce the bug and require the new test to go red.
  A test that cannot fail is the failure mode, not an edge case.
- **Name what it cannot see.** Every test has a blind spot; say it in the file
  and in the success output, or a green will be read as more than it is.
- **Sweep the class.** One bad call site usually has siblings. Grep before
  declaring it fixed.

## Coverage of the surfaces themselves

Two surfaces have a gate that notices a MISSING test: E2E
(`check-e2e-coverage.sh`, both directions) and hooks
(`check_test_file_orphans.py`). The ops workflow has no such gate of its own,
but the machines it provisions are exercised by the E2E suites, so most ops
regressions surface there rather than going unwatched.

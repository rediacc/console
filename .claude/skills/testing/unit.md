# Unit — `test-unit`, vitest

For a pure function: a parser, a formatter, a resolver, a state machine, a
comparison. Something whose inputs and outputs you can write down.

## Where the case goes

Beside the code it covers, in that package's `__tests__` directory. For the CLI
that is `packages/cli/src/**/__tests__/`, mirroring the module layout.

Run: `.ci/scripts/test/run-unit.sh --coverage`, which is what `ct-tests.yml`'s
`test-unit` job runs. Per package: `cd packages/cli && npm test`.

## When a unit test is the WRONG answer

A unit test over a mock proves the mock agrees with the test. Output shape, exit
codes and error paths are invisible to it, and those are where this repo's
defects actually live. If the fix was to what a command PRINTS, what it EXITS
with, or how it behaves against a real machine, the unit test will pass on the
broken version — go to [e2e.md](e2e.md).

Rule of thumb: if writing the test needs a mock of anything the product owns,
you are on the wrong surface.

## Proof

- the file is under a `__tests__` directory the runner globs
- `test-unit` green on the PR head
- **plant it**: revert the fix in the function, require the case to fail

## Coverage

`--coverage` is on in CI. It reports lines, not claims: a covered line with no
assertion about its result is not tested. Read the assertion, not the number.

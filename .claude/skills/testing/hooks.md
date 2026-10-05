# Hooks: `.claude/hooks`

For a Stop-hook check, a pre-bash guard, a context hook. These run on every turn of every session, so a broken one is felt immediately and a silent one never is.

## Where the case goes

Next to the hook, named `test-*.py`, and **listed in the delegate table of `.claude/rediacc_hooks/tests/test_hooks_delegates.py`** (`COUNTED` when it prints a control count worth flooring, `TAILED` when its exit code and a non-empty tail are the claim). That listing is the wiring: without it the file is an orphan that reports its own green to whoever runs it by hand. The bash
harness `.claude/hooks/test-hooks.sh` held that table until it was ported to pytest; four suites were written against it after the port and reached CI through it alone, which is how the drift was found when it was retired.

`.ci/scripts/quality/check_test_file_orphans.py` fails on an unreached test file. It exists because `test-teammate-idle.py` shipped with 20 passing controls and ran nowhere, while both existing wiring gates stayed green: they ask "is what we declared wired?", not "is there anything here we forgot to declare?".

## The mutation harness is the point

A hook check asserts on behaviour nobody watches, so the controls need controls. The pattern in `.claude/hooks/context/test-context-bands.py`: a `MUTANTS` list pairing a source edit with the check names it MUST turn red, run against a mutated copy in a temp dir.

Two traps paid for in this repo:

- **A tautological control.** Assertions that re-derive the expected value from
their own inputs never touch production code. Export the real function and assert against it.
- **A renamed check that the mutant dispatch still routes by the old name.** The
mutant then runs against the wrong pass and reports green.

## The pytest to run, and why it may wait

`.ci/cache/toolchain/uv-tools/bin/pytest` is the session entry point, and it is a wrapper that `.ci/bootstrap.sh` writes over uv's symlink, not the binary itself. It draws cores from the machine-wide lease in `.ci/rediacc_ci/core_lease.py`: `-n N` takes up to N tokens, `-n auto` takes every free one, a serial run takes one, and `-n` is rewritten to the grant. So a suite started beside a running pre-push gets the cores left over instead of taking all of them a second time.
When every token is held it waits, and prints a `core_lease: ... waiting` line on stderr naming `core_lease.py status`, which shows who holds them. That line means a queue, not a hang. With `CI_CORE_LEASE_HELD` set (the ci-runner, or a `check_pytest.py` that already leased) the wrapper passes straight through. `bash .ci/bootstrap.sh --check` shows a `lease` row; ABSENT there means the path is still uv's bare symlink and runs outside the lease.

## Proof

- `.ci/cache/toolchain/uv-tools/bin/pytest -q .claude/rediacc_hooks/tests/test_hooks_delegates.py` exits 0
- the new file appears as a node id in that run
- every mutant turns its named checks red

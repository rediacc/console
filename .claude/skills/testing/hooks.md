# Hooks — `.claude/hooks`

For a Stop-hook check, a pre-bash guard, a context hook. These run on every turn
of every session, so a broken one is felt immediately and a silent one never is.

## Where the case goes

Next to the hook, named `test-*.py` or `test-*.sh`, and **called from
`.claude/hooks/test-hooks.sh`**. That call is the wiring: without it the file is
an orphan that reports its own green to whoever runs it by hand.

`.ci/scripts/quality/check_test_file_orphans.py` fails on an unreached test
file. It exists because `test-teammate-idle.py` shipped with 20 passing controls
and ran nowhere, while both existing wiring gates stayed green — they ask "is
what we declared wired?", not "is there anything here we forgot to declare?".

## The mutation harness is the point

A hook check asserts on behaviour nobody watches, so the controls need controls.
The pattern in `.claude/hooks/context/test-context-bands.py`: a `MUTANTS` list
pairing a source edit with the check names it MUST turn red, run against a
mutated copy in a temp dir.

Two traps paid for in this repo:

- **A tautological control.** Assertions that re-derive the expected value from
  their own inputs never touch production code. Export the real function and
  assert against it.
- **A renamed check that the mutant dispatch still routes by the old name.** The
  mutant then runs against the wrong pass and reports green.

## Proof

- `bash .claude/hooks/test-hooks.sh` exits 0
- the new file appears in that suite's output
- every mutant turns its named checks red

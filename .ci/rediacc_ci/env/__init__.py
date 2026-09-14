"""Python ports of `.ci/scripts/env/*.sh`, box W7P6.

WHY THIS SUBPACKAGE EXISTS. `.ci/scripts/env/` holds the generators that write
the `.env` files the E2E harness reads, and it had no Python at all before this
box. Like `rediacc_ci/deploy/` and `rediacc_ci/build/`, nothing here is a
registered quality gate: no module carries a `---- gate ----` header,
`scripts/gate-bind.ts` does not read this package, and no `manifest.ts` entry
follows from a module living here. These are `run:` targets and developer
commands.

THE ACCEPTANCE THIS BOX WORKS TO is a shadow-gate ledger under `.ci/shadow/`
asserting `equivalence holds` at K=5 against the bash twin, produced with
`scripts/lib/shadow-gate.ts` and an `--old`/`--new` pair rather than a
registered `--pair` id, plus a byte-for-byte differential pytest file under
`.ci/rediacc_ci/tests/`. For `create_e2e_env` the differential compares the
GENERATED FILE as well as the two streams and the exit code, because the file
is the product and the streams are almost entirely progress chatter.

CUTOVER IS A LATER, DRIVER-ONLY BOX. Every caller still invokes the bash twin
(`.ci/scripts/env/create-e2e-env.sh`), and the twin stays the live
implementation until the ledger exists and the driver flips the call sites.
Nothing here removes, edits or shadows its twin.

Deliberately no re-exports, same reasoning as `rediacc_ci/__init__.py`: a
consumer should import exactly the module it needs.
"""

__all__: list[str] = []

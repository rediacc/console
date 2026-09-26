"""The ported quality gates.

WHY A SUBPACKAGE AND NOT `check_*.py` FILES ON THEIR OWN. Contract section 5d requires a gate's ENTRY POINT to live where `scripts/gate-bind.ts` can see it -- `.ci/scripts/quality/`, or `.ci/rediacc_ci` since the 2026-09-06 amendment -- and says the entry point may be "three lines of import and dispatch" while the logic lives in the package. That split is what this directory is the
other half of.

The split is not bureaucracy. A gate's logic is the part a PYTEST case wants to call directly, and a module that is only reachable by running a script is a module whose error paths are tested by nobody. Every port here exposes `main(argv) -> int` and a `selftest()`, both importable, so the same code is driven three ways: by the entry point in `.ci/scripts/quality/`, by its own
`--selftest`, and by a test.

THE BASH TWIN OUTLIVES ITS PORT UNTIL A LEDGER LICENSES THE RETIREMENT. Until a port has a committed differential ledger row over K distinct trees (`scripts/lib/shadow-gate.ts`, invariant 5), the evidence that it kept the twin's verdict does not exist, and deleting it would destroy the only thing the port can be compared against. Both files live side
by side until the ledger says otherwise; W7 P5 then retires the twin, and the ledger stays as the licence record.

WHAT EVERY PORT IN HERE PRESERVES, because these are the properties the tree's gates are judged on and a port that keeps the happy path and loses these has kept nothing:

  * ANTI-VACUITY. Exit 0 with zero PASS lines is a failure. Every gate that
    enumerates a corpus refuses when the corpus collapses, and says so in the
    repository's own refusal vocabulary rather than reporting a clean tree.
  * MIN FLOORS. A floor is not decoration; it is the only thing standing between
    a collapsed glob and a green report. Floors are carried across at the same
    values, and the message that names the floor is carried with them, because
    the wording is what stops the next reader from simply lowering it.
  * EXIT 77 IS CANNOT-RUN, NEVER A VERDICT. A gate that could not run says so
    with 77 and is never counted as a pass. None of the ports in this first batch
    uses it -- their twins do not either -- and it is stated here so a later port
    does not invent a different number for the same idea.
  * `--selftest` IS AN ADDITION, NOT A PRESERVED BEHAVIOUR, and it is the one
    place these ports deliberately do something their twins do not. Only 4 of the
    77 `check-*.sh` gates carry a self-test at all, and all four run it INLINE on
    every invocation rather than behind a flag. The ports keep whatever inline
    controls their twin had, byte for byte, AND add a flag that drives the
    decision function through its plants and their mirrors. The consequence worth
    knowing: a twin invoked as `check-www-build-token.sh --selftest` would treat
    that string as a directory name, and the port intercepts it. No caller does
    that, and the differential never passes it to the old side.
  * STDERR CARRIES THE MESSAGES, STDOUT CARRIES DATA. `rediacc_ci.log` is the
    single logger; see its docstring for the 2026-09-06 stream-swap incident that
    made the rule explicit.
"""

__all__: list[str] = []

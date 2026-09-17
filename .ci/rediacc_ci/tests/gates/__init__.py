"""The bash gate-test battery, ported to pytest, one module per `.ci/scripts/test/gates/test-*.sh`.

WHY A PACKAGE AND NOT A BARE DIRECTORY: the same reason `rediacc_ci.tests` is one. Without `__init__.py` pytest's prepend import mode imports each file by its bare basename, and `test_harness.py` here would collide with any future `test_harness.py` elsewhere -- the second one collected simply does not run, and a whole file of controls disappears with no red. With this file the
modules are `rediacc_ci.tests.gates.*`, unique by construction.

COEXISTENCE, NOT REPLACEMENT. Every module here names its `.ci/scripts/test/gates/` twin in a module-level `BASH_TWIN`, and `test_twin_parity.py` drives BOTH on every run and refuses to let them disagree. The bash original is not deleted by the change
that ports it; it is deleted by a later change, once the parity test has been green
across enough runs to be believed. A twin that has stopped agreeing is a regression in the port, and the only way to see that is to keep running both.

Nothing is exported. The suite is run, not imported.
"""

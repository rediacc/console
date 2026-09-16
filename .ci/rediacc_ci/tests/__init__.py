"""Tests for rediacc_ci, importable as `rediacc_ci.tests`.

AN `__init__.py` AND NOT A BARE DIRECTORY, for one concrete reason: without it
pytest's default prepend import mode inserts each test file's own directory onto
sys.path and imports it by bare module name. Two test files called `test_paths.py`
in two different suites then collide with "import file mismatch", and the second
one to be collected simply does not run -- a whole file of controls that vanishes
without a red. The driver contract schedules two more test roots
(`.ci/tests/gates`, `.claude/rediacc_hooks/tests`), so that collision is a matter
of when, not whether. With this file the tests are `rediacc_ci.tests.test_paths`,
which is unique by construction.

Nothing is exported. The suite is run, not imported.
"""

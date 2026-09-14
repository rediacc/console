"""Python ports of `.ci/scripts/signal/*.sh`, box W7P6.

Sibling of `rediacc_ci.release` and `rediacc_ci.version`; see those packages'
docstrings for why the subpackage exists, why there is no `---- gate ----`
header (these are plain workflow `run:` targets, not registered gates), and why
the caller cutover is a separate, later box, never this one. `.ci/scripts/
signal/` held one bash script and zero Python before this box.

NAMED `ci_signal`, NOT `signal`. `check:ci-pytest` (`.ci/rediacc_ci/
check_pytest.py`) is run as a script by `package.json`, which puts
`.ci/rediacc_ci/` itself at `sys.path[0]`; a package literally named `signal`
there shadows the stdlib module for every later `import signal` in the whole
tree (`proc.py`'s `os.killpg(..., signal.SIGKILL)` included), and Python's own
`AttributeError` names the exact file to rename. Driver-fixed on discovery
rather than left as a workaround, since nothing else in this box's naming
needs to collide with a stdlib module name.
"""

__all__: list[str] = []

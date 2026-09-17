"""Python ports of `.ci/scripts/version/*.sh`, box W7P6.

Sibling of `rediacc_ci.release` and `rediacc_ci.deploy`; see those packages'
docstrings for why the subpackage exists, why there is no `---- gate ----` header (these are plain utility scripts, not registered gates), and why the workflow/caller cutover is a separate, later box, never this one. `version/` held 4 bash scripts and zero Python before this box.
"""

__all__: list[str] = []

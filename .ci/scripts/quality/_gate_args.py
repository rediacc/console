"""The entry points in this directory import the argument check by this name; it lives in `rediacc_ci.quality.gate_args`.

`import _cipath` below puts `.ci` on `sys.path` first, so an entry point that imports nothing else from the package (a stdlib-only gate) still resolves the import.
"""

import _cipath
from rediacc_ci.quality.gate_args import Parsed, accepted_text, parse, problem, scan

__all__ = ["Parsed", "accepted_text", "parse", "problem", "scan"]

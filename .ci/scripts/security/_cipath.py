"""Put `.ci` on `sys.path` so an entry point in this directory can import `rediacc_ci`.

A path invocation puts only the script's own directory on `sys.path`, so a sibling `import _cipath` is the one import that resolves before `.ci` is reachable. Same pattern as `.ci/scripts/quality/_cipath.py`, which carries the full reasoning (why an import for side effect, why the depth is checked).
"""

import pathlib
import sys

CI_DIR = pathlib.Path(__file__).resolve().parents[2]

if not (CI_DIR / "rediacc_ci" / "__init__.py").is_file():
    raise RuntimeError(
        "_cipath computed %s as the .ci directory, but there is no rediacc_ci "
        "package in it. This file has moved: it must stay in .ci/scripts/security/, "
        "two directories below .ci." % CI_DIR
    )

sys.path.insert(0, str(CI_DIR))

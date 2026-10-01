"""Put `.ci` on `sys.path` so an entry point in this directory can import `rediacc_ci`.

Same pattern as `.ci/scripts/quality/_cipath.py`, three directories below `.ci` here.
"""

import pathlib
import sys

CI_DIR = pathlib.Path(__file__).resolve().parents[3]

if not (CI_DIR / "rediacc_ci" / "__init__.py").is_file():
    raise RuntimeError(
        "_cipath computed %s as the .ci directory, but there is no rediacc_ci "
        "package in it. This file has moved: it must stay in .ci/scripts/ci/profiler/, "
        "three directories below .ci." % CI_DIR
    )

sys.path.insert(0, str(CI_DIR))

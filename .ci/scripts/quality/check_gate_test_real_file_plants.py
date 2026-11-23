#!/usr/bin/env python3
"""Run `rediacc_ci.quality.gate_test_real_file_plants` by path, with the same argument check its own entry makes.

The gate is declared by the `---- gate ----` header in `.ci/rediacc_ci/quality/gate_test_real_file_plants.py` and registered from it
(`npm run gen:gates`), which runs the module directly; this file stays for callers that run it by path.
"""

import sys

import _cipath
import _gate_args
from rediacc_ci.quality import gate_test_real_file_plants

if __name__ == "__main__":
    _gate_args.parse("check_gate_test_real_file_plants.py", sys.argv[1:], switches=("--selftest",))
    if "--selftest" in sys.argv:
        gate_test_real_file_plants.controls()
        print("%s✓%s selftest" % (gate_test_real_file_plants.GREEN, gate_test_real_file_plants.NC))
        sys.exit(0)
    sys.exit(gate_test_real_file_plants.main())

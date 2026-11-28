#!/usr/bin/env python3
"""Run `rediacc_ci.quality.config_server_key_constant` by path, with the same argument check its own entry makes.

The gate is declared by the `---- gate ----` header in `.ci/rediacc_ci/quality/config_server_key_constant.py` and registered from it
(`npm run gen:gates`), which runs the module directly; this file stays for callers that run it by path.
"""

import sys

import _cipath
from rediacc_ci.quality import config_server_key_constant

if __name__ == "__main__":
    sys.exit(config_server_key_constant.main(sys.argv[1:]))

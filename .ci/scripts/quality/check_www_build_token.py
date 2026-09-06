#!/usr/bin/env python3
"""Entry point for the ported www-build-token gate. Logic is in the package.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can
see it; the logic lives in `rediacc_ci.quality.www_build_token`, which is
importable by pytest and by the port's own `--selftest`.

The bash twin `.ci/scripts/quality/check-www-build-token.sh` carries the
`---- gate ----` header and remains the registered gate. This file carries none,
on purpose: two headers for one subject would run the same check twice and turn a
port defect into two unrelated-looking reds.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from rediacc_ci.quality import www_build_token

if __name__ == "__main__":
    raise SystemExit(www_build_token.main(sys.argv[1:]))

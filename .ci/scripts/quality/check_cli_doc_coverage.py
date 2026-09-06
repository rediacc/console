#!/usr/bin/env python3
"""Entry point for the ported cli-doc-coverage gate.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can
see it; the logic lives in `rediacc_ci.quality.cli_doc_coverage`.

No `---- gate ----` header: the bash twin remains the registered gate until the
differential ledger says the port kept its verdict.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from rediacc_ci.quality import cli_doc_coverage

if __name__ == "__main__":
    raise SystemExit(cli_doc_coverage.main(sys.argv[1:]))

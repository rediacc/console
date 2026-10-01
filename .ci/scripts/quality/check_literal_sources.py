#!/usr/bin/env python3
"""Entry point for the literal-sources gate.

The logic lives in `rediacc_ci.quality.literal_sources`; this file exists so the registry can invoke it BY PATH, the same split `check_actions_vars.py` uses. The `---- gate ----` header is HERE and not on the module, because `gate-bind` reads the file package.json names.

---- gate ----
step: Literal sources
needs: none
lane: quality-static
selftest: true
why: every origin, bucket, slug, image registry, owned path, address and port is written once in .ci/config/well-known.env and read everywhere else; a registered value typed out in code, or an owned literal spreading across files unregistered, is a finding.
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import literal_sources

if __name__ == "__main__":
    raise SystemExit(literal_sources.main(sys.argv[1:]))

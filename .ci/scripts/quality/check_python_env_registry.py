#!/usr/bin/env python3
"""Entry point for the Python environment registry gate.

The logic lives in `rediacc_ci.quality.python_env_registry`; this file exists so the registry can invoke it BY PATH, for the parity-tokenizer reason recorded in `gate-header.ts`'s `derivedRun` and in `_cipath`'s docstring. The `---- gate ----` header is HERE and not on the module, because `gate-bind` reads the file package.json names.

---- gate ----
step: Python env registry
needs: none
lane: quality-static
selftest: true
why: an environment read is an undeclared input, and until this landed nothing
     in the tree could say which Python modules had one. Seeded 2026-09-09 at
     445 module:NAME pairs across 164 modules; the set is shrink-only and
     set-equal in BOTH directions, so the registry can neither be trimmed to
     escape a finding nor pre-loaded with one
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import python_env_registry

if __name__ == "__main__":
    raise SystemExit(python_env_registry.main(sys.argv[1:]))

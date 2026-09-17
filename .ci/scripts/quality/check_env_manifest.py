#!/usr/bin/env python3
"""Entry point for the environment-variable manifest gate.

The logic lives in `rediacc_ci.quality.env_manifest`; this file exists so the registry can invoke it BY PATH, for the parity-tokenizer reason recorded in `gate-header.ts`'s `derivedRun` and in `_cipath`'s docstring.

---- gate ---- step: Env manifest needs: none lane: quality-static selftest: true why: an environment variable is an undeclared input, and nothing in this tree could
     answer "who supplies this value and who may read it" without a fresh grep that
     is wrong in both directions. Five readers derive the corpus from tracked files
     on every run -- no count is ever written down -- and four set-arithmetic clauses
     hold it against an eight-shard classification, the eighth shard being tombstones
     so that "a dead name came back" and "a new name is unclassified" are the same
     assertion rather than two mechanisms to keep in sync
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import env_manifest

if __name__ == "__main__":
    raise SystemExit(env_manifest.main(sys.argv[1:]))

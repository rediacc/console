#!/usr/bin/env python3
"""Entry point for the secret-supply gate.

The logic lives in `rediacc_ci.quality.secret_supply`; this file exists so the registry can invoke it BY PATH, for the parity-tokenizer reason recorded in `gate-header.ts`'s `derivedRun` and in `_cipath`'s docstring. The `---- gate ----` header is HERE and not on the module, because `gate-bind` reads the file package.json names.

---- gate ----
step: Secret supply
needs: none
lane: quality-static
selftest: true
why: a name the env manifest declares vault-supplied that no vault holds is a
     credential whose supply is unstated, and nothing in this tree could name
     that set. Only the FIRST line of this field survives the parser, so the
     rest is for a human: the same file carries the truncation spec for
     private/account/.env, one destination per assigned name, each destination
     a claim checked against the vault map rather than a note. The dev-shared
     and admin-bootstrap seedings are door:operator-only and every blocked name
     is printed in full on every run
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import secret_supply

if __name__ == "__main__":
    raise SystemExit(secret_supply.main(sys.argv[1:]))

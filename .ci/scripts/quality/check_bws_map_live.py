#!/usr/bin/env python3
"""Entry point for the live Bitwarden map comparison.

The logic and the controls live in `rediacc_ci.quality.bws_map_live`; this file exists so the registry can invoke it BY PATH. Why it is local-only, and why a missing token is exit 77 rather than a pass, is argued in that module's docstring.

---- gate ----
kind: local-only
blocker: BLOCKER: no CI job has the bws CLI. The quality-security job holds the BWS token, but bitwarden/sm-action fetches by UUID through its own client and nothing installs the CLI, so a step would print SKIP on every run and could never fail. Locally the token file and the CLI exist, and the gate exits 77 (blocked, counted in the receipt) where they do not.
needs: none
why: a secret deleted from Bitwarden lingers in .ci/config/bws-secret-map.json until a
     job that requests it fails at run time, and check:ci-bws-map is offline by design.
     This compares the map's names with the live store, by name and UUID, never a value.
---- end gate ----
"""

import sys

import _cipath
from rediacc_ci.quality import bws_map_live

if __name__ == "__main__":
    raise SystemExit(bws_map_live.main(sys.argv[1:]))

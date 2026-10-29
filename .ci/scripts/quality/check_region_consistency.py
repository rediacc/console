#!/usr/bin/env python3
"""Entry point for check:ci-region-consistency. The logic is in `rediacc_ci.quality.region_consistency`.

The seven account targets (stable and edge in eu, us and asia, plus bench) must be one shape, modulo the per-target differences the module names: regions.json, every account and proxy wrangler toml, and the secret-supply profiles that feed each target's secret push. `--live` adds the same check against Cloudflare (Workers, Worker secret names, R2 buckets with their jurisdiction, D1 ids); the housekeeping workflow's `cf-leftovers` job runs that half nightly with its read token.

Registered by path, not as `python3 -m`, because check:ci-parity resolves `-m` to the leaf `[python3]` (see `_cipath`).

---- gate ----
step: Region consistency
run: .ci/scripts/quality/check_region_consistency.py --selftest && .ci/scripts/quality/check_region_consistency.py
selftest: true
needs: none
lane: quality-static
why: Each per-target fact is written in regions.json, two wrangler tomls and a bws profile, and the seven targets
     were grown one at a time; a target missing what the other six have, or naming another target's bucket, key
     or Worker, is invisible to every single-file gate.
---- end gate ----
"""

import sys

import _cipath
from rediacc_ci.quality import region_consistency

if __name__ == "__main__":
    raise SystemExit(region_consistency.main(sys.argv[1:]))

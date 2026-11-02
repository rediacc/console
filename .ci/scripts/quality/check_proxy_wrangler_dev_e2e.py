#!/usr/bin/env python3
"""Entry point for the proxy wrangler-dev e2e gate. Logic is in the package.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can see it; the logic lives in `rediacc_ci.quality.proxy_wrangler_dev_e2e`, which the gate's own `--selftest` exercises.

The Worker and its container were each tested alone and never together: this runs the Worker under `wrangler dev` with its container on the local docker host and proves a request reaches `rdc serve --mode container` (agent/plans/PLAN-cloudflare-proxy.md box A6).

Hand-registered, with no gate header, as `local-only`: it needs docker and the Containers runtime of `wrangler dev`, which no ci-quality.yml step has (scripts/ci-runner/manifest.ts carries the BLOCKER).
"""

import sys

import _cipath
from rediacc_ci.quality import proxy_wrangler_dev_e2e

if __name__ == "__main__":
    raise SystemExit(proxy_wrangler_dev_e2e.main(sys.argv[1:]))

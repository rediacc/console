#!/usr/bin/env python3
"""Entry point for the proxy image smoke gate. Logic is in the package.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can see it; the logic lives in `rediacc_ci.quality.proxy_image_smoke`, which the gate's own `--selftest` exercises.

The executor image was never built or booted by CI; it shipped with no renet (B2) and died at boot without REDIACC_TOKEN (B1), and nothing noticed.

---- gate ----
kind: local-only
id: check:ci-proxy-image-smoke
blocker: BLOCKER: a full docker build of the executor image (npm ci of the workspace plus the CLI bundle) that also needs a renet-linux-amd64 to stage; no CI job builds renet before the quality lanes, and wiring it into ci-build-docker is a workflow change outside the proxy writer file set (PLAN-cloudflare-proxy.md Writer A)
needs: submodules
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import proxy_image_smoke

if __name__ == "__main__":
    raise SystemExit(proxy_image_smoke.main(sys.argv[1:]))

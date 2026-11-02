#!/usr/bin/env python3
"""Entry point for the proxy image smoke gate. Logic is in the package.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can see it; the logic lives in `rediacc_ci.quality.proxy_image_smoke`, which the gate's own `--selftest` exercises.

The executor image was never built or booted by CI; it shipped with no renet (B2) and died at boot without REDIACC_TOKEN (B1), and nothing noticed.

Hand-registered, with no gate header: CI runs it in `.github/workflows/ci-build-renet.yml` job `proxy-image-smoke`, the one place a freshly built renet-linux-amd64 exists to stage, and a header can only bind a step in ci-quality.yml (scripts/gate-bind.ts WORKFLOW).
"""

import sys

import _cipath
from rediacc_ci.quality import proxy_image_smoke

if __name__ == "__main__":
    raise SystemExit(proxy_image_smoke.main(sys.argv[1:]))

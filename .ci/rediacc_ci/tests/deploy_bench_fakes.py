"""Entry point `test_ops_cf_family` runs in place of `rediacc_ci.ops.deploy_bench`: the real `main`, with the two steps whose children cannot run in the scratch-PATH world replaced by recorders.

`_ensure_signers` spawns `control_db` and a `bws_env exec --profile deploy-signer` child (a real Bitwarden call), and `smoke` GETs the live bench host. Neither can be answered by the fake `npx` and `curl` that stand in for Cloudflare there, so each is replaced here and covered by `test_deploy_bench_repeatability.py`, which drives both against a fake runner. Everything else is the shipped code, so the differential against the retired bash still compares the real deploy.
"""

from __future__ import annotations

import sys

from rediacc_ci.ops import deploy_bench


def main(argv: list[str]) -> int:
    deploy_bench._ensure_signers = lambda *_a, **_k: None
    deploy_bench.smoke = lambda *_a, **_k: None
    return deploy_bench.main(argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

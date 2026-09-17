#!/usr/bin/env python3
"""Port of `.ci/scripts/deploy/deploy-edge.sh`.

Deploys the edge marketing Worker (edge.rediacc.com) from `workers/www` with
`wrangler.edge.toml`. No D1, no migrations, no region: the account API for edge
is served by the separate `edge-rediacc-account-{eu,us,asia}` Workers that
`deploy-account.sh --target edge` puts up, and this script knows nothing about
them.

IT IS NOT `deploy-account.sh` WITH THE MIGRATIONS REMOVED, and the differences
are the reason this is its own file rather than a flag. Against its sibling:

  * IT PARSES NO ARGUMENTS AT ALL. There is no `parse_args` call (:12-14 of the
    twin has the source line and then goes straight to the repo root), so
    `--region eu` is silently ignored rather than rejected. Pinned in the
    differential, because "it takes no options" and "it refuses options" are
    different behaviours and only one of them is true here.
  * THE INSTALL CONDITION IS DIFFERENT. This one is `[[ ! -d "node_modules" ]]`
    alone (:31); the account script also requires wrangler to be absent from
    PATH. A machine with a global wrangler therefore runs `npm install` here and
    does not there. Reproduced, not harmonised.
  * The config path is a LITERAL, `wrangler.edge.toml`, not composed from
    anything, so there is no missing-region case and no config-name family.

NOTHING HERE REACHES CLOUDFLARE IN A TEST. `npx` and `npm` are the only external
tools; the differential (`.ci/rediacc_ci/tests/test_deploy_deploy_edge.py`) puts
RECORDING FAKES for both on a scratch PATH and points both sides at a fixture
repo root. `.ci/shadow/w7p5a-status.json` records this path as blocked only for
the "one real run" clause and says in as many words that the mocked parity
ledger is separate, achievable work. This is that piece.

THE FAILURE THIS SCRIPT CANNOT REPORT, named because it is the vacuity class:
`CLOUDFLARE_ACCOUNT_ID` is required and then never used by anything in this
file. It is `require_var`'d at :24 and read only by wrangler itself, out of the
environment. A caller who exports the WRONG account id passes every check here
and finds out from Cloudflare.

K=5 LEDGER: `.ci/shadow/w7p6-deploy-edge.observations.jsonl`.
"""

from __future__ import annotations

import os
import subprocess
import sys
import typing

from rediacc_ci import log
from rediacc_ci.core import common

if typing.TYPE_CHECKING:
    import pathlib

# `$REPO_ROOT/workers/www` (:14). The MARKETING worker's directory, shared with the stable www deploy, which uses `wrangler.toml` from the same place.
WORKER_SUBDIR = ("workers", "www")

# `wrangler.edge.toml` (:16, :35). A literal in the twin, twice, so it is a constant here once and the differential asserts the twin still spells it the same way.
CONFIG = "wrangler.edge.toml"

# The two variables `require_var` demands (:23-24), in the twin's order. The FIRST missing one ends the run, so the order is observable.
REQUIRED_VARS = ("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID")

# See the docstring: demanded, then never read by this script.
THE_ACCOUNT_ID_IS_CHECKED_AND_UNUSED = True

# `parse_args` IS NOT CALLED (contrast `deploy-account.sh:16` and `deploy-proxy.sh:23`), so every argument is discarded in silence.
ARGUMENTS_ARE_IGNORED = True


def strip_newlines(token: str) -> str:
    """`printf '%s' "$TOKEN" | tr -d '\\r\\n'` (:28).

    DELIBERATELY NOT IMPORTED FROM `deploy_account.py`, which carries a line
    with the same bytes today. Each port is a port of ONE file, and a shared
    helper would silently change this script the day someone edits that one --
    the same reason `purge_media_cache.py` keeps its own `auth_headers` beside
    an almost-identical sibling. The differential re-derives both twins' lines
    and asserts they still agree, so the duplication is checked rather than
    assumed.

    `tr -d` deletes BYTES, and in UTF-8 neither 0x0D nor 0x0A can appear inside
    a multi-byte sequence, so deleting the characters and deleting the bytes
    agree for every input.
    """
    return token.replace("\r", "").replace("\n", "")


def deploy_argv() -> list[str]:
    """`npx wrangler deploy --config wrangler.edge.toml` (:35)."""
    return ["npx", "wrangler", "deploy", "--config", CONFIG]


def needs_npm_install(worker_dir: pathlib.Path) -> bool:
    """`if [[ ! -d "node_modules" ]]` (:31).

    ONE CONDITION, unlike the account sibling: a global wrangler does not stop
    the install here.
    """
    return not (worker_dir / "node_modules").is_dir()


def _run(argv: list[str]) -> int:
    """One child with BOTH streams inherited, as the twin leaves them."""
    return subprocess.run(argv, check=False).returncode


def main(argv: list[str]) -> int:
    del argv  # the twin parses nothing; see ARGUMENTS_ARE_IGNORED

    worker_dir = common.repo_root().joinpath(*WORKER_SUBDIR)

    if not (worker_dir / CONFIG).is_file():
        log.error("Edge worker config not found at %s/%s" % (worker_dir, CONFIG))
        return 1

    os.chdir(worker_dir)

    for name in REQUIRED_VARS:
        try:
            common.require_var(name)
        except common.RefusalError as exc:
            exc.report()
            return exc.code

    # `export CLOUDFLARE_API_TOKEN` after the strip: children see the clean one.
    os.environ["CLOUDFLARE_API_TOKEN"] = strip_newlines(os.environ["CLOUDFLARE_API_TOKEN"])

    if needs_npm_install(worker_dir):
        status = _run(["npm", "install"])
        if status != 0:
            return status  # `set -e`

    log.step("Deploying edge worker (edge.rediacc.com)...")
    status = _run(deploy_argv())
    if status != 0:
        return status  # `set -e`
    log.info("Edge worker deployed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

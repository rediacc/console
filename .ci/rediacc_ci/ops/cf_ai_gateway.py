"""Cloudflare AI Gateway settings as code (agent/plans/PLAN-console-ai-credits.md D3).

    PYTHONPATH=.ci python3 -m rediacc_ci.ops.cf_ai_gateway [--dry-run | --check] [--config <path>]

WHAT IT DOES. Reads `.ci/config/ai-gateway.json`: `settings_defaults` merged with each `gateways.<id>` override gives the settings of gateway `<id>`. The run lists `.../ai-gateway/gateways`, then `POST`s a missing gateway, `PUT`s a drifted one and leaves a matching one alone, so a second run against unchanged JSON writes nothing and prints `0 change(s)`. Only the keys the JSON names are compared; a field it does not name is the dashboard's.

MODES. `--dry-run` prints the settings each gateway would get and makes no request, so it reads no secret and needs no network. `--check` reads the gateways, writes nothing, and exits 1 when one is missing or a setting differs from the JSON (a hand change in the dashboard). Without either flag the run applies the JSON.

AUTH. `CF_MANAGEMENT_TOKEN`, a token with AI Gateway Edit. The credential reaches curl on its stdin (`rediacc_ci.core.curl_stdin`), never argv, and is never printed.

NOT HERE. The gateway spend limit, the Unified Billing top-up and the low-balance email have no API field; they are the operator's dashboard steps and sit under `dashboard_only` in the JSON.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import typing

from rediacc_ci import paths
from rediacc_ci.ops import cf_auth

CONFIG_REL = ".ci/config/ai-gateway.json"


class GatewayError(Exception):
    """A step failed; the message goes to stderr and the exit status is 1."""


def load_config(path: pathlib.Path) -> dict[str, dict]:
    """Gateway id -> its full settings, after merging `settings_defaults`."""
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise GatewayError("cannot read %s: %s" % (path, exc)) from None
    defaults = cfg.get("settings_defaults")
    gateways = cfg.get("gateways")
    if not isinstance(defaults, dict) or not isinstance(gateways, dict) or not gateways:
        raise GatewayError("%s needs a settings_defaults map and a non-empty gateways map" % path)
    out = {}
    for gid, override in gateways.items():
        if not isinstance(override, dict):
            raise GatewayError("%s: gateway %s must map to an object" % (path, gid))
        out[gid] = {**defaults, **override}
    return out


def drift(existing: dict, want: dict) -> list[str]:
    """The settings where `existing` differs from `want`, empty when it matches."""
    return [
        "%s %r -> %r" % (key, existing.get(key), value)
        for key, value in sorted(want.items())
        if existing.get(key) != value
    ]


class Api:
    """The ai-gateway/gateways calls, authenticated with one token."""

    def __init__(self, auth: cf_auth.Auth, account_id: str):
        self.auth = auth
        self.base = "%s/accounts/%s/ai-gateway/gateways" % (cf_auth.CF_API_BASE, account_id)

    def _send(self, method: str, url: str, payload: dict | None = None) -> dict:
        data = json.dumps(payload) if payload is not None else None
        body = cf_auth.curl_json(
            method, url, self.auth.headers, data, content_type=payload is not None
        )
        if body.get("success") is not True:
            raise GatewayError(
                "%s %s failed: %s" % (method, url.rsplit("/", 1)[-1], cf_auth._errors(body))
            )
        return body

    def list(self) -> dict[str, dict]:
        result = self._send("GET", self.base + "?per_page=100").get("result")
        if not isinstance(result, list):
            raise GatewayError("listing gateways returned no result list")
        return {str(g.get("id")): g for g in result if isinstance(g, dict)}

    def create(self, gid: str, settings: dict) -> None:
        self._send("POST", self.base, {"id": gid, **settings})

    def update(self, gid: str, settings: dict) -> None:
        self._send("PUT", "%s/%s" % (self.base, gid), {"id": gid, **settings})


def dry_run(want: dict[str, dict], out: typing.TextIO) -> int:
    for gid, settings in sorted(want.items()):
        print("WOULD SET %s %s" % (gid, json.dumps(settings, sort_keys=True)), file=out)
    print("%d gateway(s) configured (dry run, no request made)" % len(want), file=out)
    return 0


def run(api: Api, want: dict[str, dict], check: bool, out: typing.TextIO | None = None) -> int:
    """Make the account's gateways match `want` (or only report, with `check`); return the exit status."""
    out = sys.stdout if out is None else out
    existing = api.list()
    changes = 0
    for gid, settings in sorted(want.items()):
        have = existing.get(gid)
        if have is None:
            changes += 1
            print(("MISSING %s" if check else "CREATE %s") % gid, file=out)
            if not check:
                api.create(gid, settings)
            continue
        diffs = drift(have, settings)
        if not diffs:
            print("UNCHANGED %s" % gid, file=out)
            continue
        changes += 1
        print("%s %s: %s" % ("DRIFT" if check else "UPDATE", gid, "; ".join(diffs)), file=out)
        if not check:
            api.update(gid, settings)
    if check:
        print("%d gateway(s) differ from %s" % (changes, CONFIG_REL), file=out)
        return 1 if changes else 0
    print("%d change(s)" % changes, file=out)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cf_ai_gateway", description=__doc__.split("\n\n")[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="print the settings, no request")
    mode.add_argument("--check", action="store_true", help="exit 1 on drift, write nothing")
    parser.add_argument("--config", type=pathlib.Path, default=None)
    parser.add_argument("--account-id", default=cf_auth.DEFAULT_ACCOUNT_ID)
    args = parser.parse_args(argv)
    config = args.config or paths.from_root(*CONFIG_REL.split("/"))
    try:
        want = load_config(config)
        if args.dry_run:
            return dry_run(want, sys.stdout)
        token = os.environ.get("CF_MANAGEMENT_TOKEN")
        if not token:
            raise GatewayError("set CF_MANAGEMENT_TOKEN (a token with AI Gateway Edit)")
        return run(Api(cf_auth.Auth(token=token), args.account_id), want, args.check)
    except (GatewayError, cf_auth.CfAuthError) as exc:
        print("cf_ai_gateway: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

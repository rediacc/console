"""Apply the Cloudflare rate-limiting rules declared in `.ci/config/cf-waf-rules.json` to the account Workers' zones.

    PYTHONPATH=.ci python3 -m rediacc_ci.ops.apply_cf_waf_rules [--dry-run]

WHY IT EXISTS. agent/plans/PLAN-free-license.md R10 and F8: `POST /account/api/v1/licenses/free` takes no credential, so the D1 counter in private/account/src/services/free-license.service.ts (8 new FREE licences per IP key per 72 h) is the real bound, and a zone rate rule stops a flood before any request reaches the Worker or D1.

WHAT IT DOES, per zone in the config:

  1. Builds one rule per config entry. Its expression names the method, the path and every account hostname; the hostnames come from the `routes` of workers/account/wrangler.*.toml (bench, the edge regions and the stable regions), so the config never keeps a second list that drifts.
  2. Reads the zone's `http_ratelimit` phase entrypoint ruleset and finds each rule by its `ref`.
  3. With `--dry-run`, prints one line per rule (`create`, `update` or `unchanged`) and the rule body, and writes nothing. Without credentials the dry run prints the planned rules alone and says that it compared nothing.
  4. Otherwise creates the entrypoint (PUT) when the zone has none, appends a missing rule (POST), and replaces a drifted one (PATCH). Rules it does not own (no matching `ref`) are left alone.

More than one rule carrying one `ref` is a failure, never a guess.

Auth: `CLOUDFLARE_API_TOKEN`, or `CF_GLOBAL_API_KEY` + `CF_EMAIL`, through `PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env exec --profile <p> -- ...`. The credential headers go on curl's stdin, never on argv.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tomllib
from collections.abc import Callable
from typing import TYPE_CHECKING

from rediacc_ci import paths
from rediacc_ci.core import curl_stdin
from rediacc_ci.well_known import CF_API_BASE

if TYPE_CHECKING:
    from pathlib import Path

CONFIG_REL = ".ci/config/cf-waf-rules.json"
WRANGLER_GLOB = "wrangler.*.toml"
PHASE = "http_ratelimit"

HELP = """Apply the Cloudflare rate-limiting rules in .ci/config/cf-waf-rules.json.

Usage:
  apply_cf_waf_rules            create or update each rule
  apply_cf_waf_rules --dry-run  print what would change, never mutate

Auth: CLOUDFLARE_API_TOKEN, or CF_GLOBAL_API_KEY + CF_EMAIL.
"""

# (method, url, body) -> (http status, decoded JSON body)
Transport = Callable[[str, str, "dict | None"], "tuple[int, dict]"]


class ApplyError(Exception):
    """A step failed; the message goes to stderr and the exit status is 1."""


def load_config(root: Path) -> dict:
    try:
        config = json.loads((root / CONFIG_REL).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ApplyError("cannot read %s: %s" % (CONFIG_REL, exc)) from None
    if not config.get("zones") or not config.get("rules"):
        raise ApplyError("%s declares no zones or no rules" % CONFIG_REL)
    refs = [rule.get("ref") for rule in config["rules"]]
    if len(set(refs)) != len(refs) or not all(refs):
        raise ApplyError("%s: every rule needs a unique, non-empty ref" % CONFIG_REL)
    return config


def account_hosts(root: Path) -> list[str]:
    """Every custom-domain pattern in workers/account/wrangler.*.toml, sorted."""
    hosts: set[str] = set()
    for path in sorted((root / "workers" / "account").glob(WRANGLER_GLOB)):
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise ApplyError("cannot parse %s: %s" % (path.name, exc)) from None
        for route in data.get("routes") or []:
            pattern = route.get("pattern") if isinstance(route, dict) else route
            if isinstance(pattern, str) and pattern:
                hosts.add(pattern.split("/", 1)[0])
    if not hosts:
        raise ApplyError("no account hostnames found in workers/account/%s" % WRANGLER_GLOB)
    return sorted(hosts)


def rule_body(rule: dict, hosts: list[str]) -> dict:
    """The Cloudflare rule object for one config entry."""
    host_set = " ".join('"%s"' % host for host in hosts)
    expression = (
        '(http.host in {%s} and http.request.method eq "%s" and http.request.uri.path eq "%s")'
        % (
            host_set,
            rule["method"],
            rule["path"],
        )
    )
    return {
        "ref": rule["ref"],
        "description": rule["description"],
        "expression": expression,
        "action": rule["action"],
        "enabled": True,
        "ratelimit": {
            "characteristics": ["cf.colo.id", "ip.src"],
            "period": int(rule["periodSeconds"]),
            "requests_per_period": int(rule["requestsPerPeriod"]),
            "mitigation_timeout": int(rule["mitigationTimeoutSeconds"]),
        },
    }


# The fields this applier owns on a rule; Cloudflare adds id, version and
# last_updated, which a comparison must ignore.
OWNED_FIELDS = ("ref", "description", "expression", "action", "enabled", "ratelimit")


def drifted(current: dict, wanted: dict) -> bool:
    return any(current.get(field) != wanted[field] for field in OWNED_FIELDS)


def curl_transport() -> Transport:
    headers = auth_headers()

    def call(method: str, url: str, body: dict | None) -> tuple[int, dict]:
        argv = ["curl", "-sS", "-X", method, "-w", "\n%{http_code}", *headers]
        if body is not None:
            argv += ["-H", "Content-Type: application/json", "-d", json.dumps(body)]
        argv.append(url)
        argv, config = curl_stdin.stdin_headers(argv)
        proc = subprocess.run(argv, input=config, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise ApplyError("%s %s failed: %s" % (method, url, proc.stderr.strip()[:300]))
        text, _, status = proc.stdout.rpartition("\n")
        try:
            decoded = json.loads(text) if text.strip() else {}
        except ValueError:
            raise ApplyError("%s %s did not return JSON" % (method, url)) from None
        return int(status or 0), decoded if isinstance(decoded, dict) else {}

    return call


def auth_headers() -> list[str]:
    token = os.environ.get("CLOUDFLARE_API_TOKEN")
    key = os.environ.get("CF_GLOBAL_API_KEY")
    email = os.environ.get("CF_EMAIL")
    if token:
        return ["-H", "Authorization: Bearer %s" % token]
    if key and email:
        return ["-H", "X-Auth-Email: %s" % email, "-H", "X-Auth-Key: %s" % key]
    raise ApplyError("set CLOUDFLARE_API_TOKEN or CF_GLOBAL_API_KEY + CF_EMAIL")


def has_credentials() -> bool:
    return bool(
        os.environ.get("CLOUDFLARE_API_TOKEN")
        or (os.environ.get("CF_GLOBAL_API_KEY") and os.environ.get("CF_EMAIL"))
    )


def _checked(method: str, url: str, status: int, body: dict) -> dict:
    if 200 <= status < 300 and body.get("success") is not False:
        return body
    errors = body.get("errors") or []
    detail = "; ".join(str(e.get("message", e)) for e in errors if isinstance(e, dict))
    raise ApplyError(
        "%s %s refused by Cloudflare (HTTP %s): %s" % (method, url, status, detail or "no detail")
    )


def apply_zone(
    zone: dict, wanted: list[dict], transport: Transport | None, dry_run: bool
) -> list[str]:
    """Reconcile one zone; returns the printed lines."""
    name = zone["name"]
    base = "%s/zones/%s/rulesets" % (CF_API_BASE, zone["zoneId"])
    lines: list[str] = []
    if transport is None:
        for rule in wanted:
            lines.append("[PLAN] %s %s (no credentials: nothing compared)" % (name, rule["ref"]))
            lines.append("       " + json.dumps(rule, sort_keys=True))
        return lines

    entry_url = "%s/phases/%s/entrypoint" % (base, PHASE)
    status, body = transport("GET", entry_url, None)
    if status == 404:
        ruleset = None
    else:
        ruleset = _checked("GET", entry_url, status, body).get("result") or {}

    if ruleset is None:
        lines.extend(
            "[MISS] %s %s: no %s entrypoint, would create it with this rule"
            % (name, rule["ref"], PHASE)
            for rule in wanted
        )
        if dry_run:
            lines.extend("       " + json.dumps(rule, sort_keys=True) for rule in wanted)
            return lines
        status, body = transport("PUT", entry_url, {"rules": wanted})
        _checked("PUT", entry_url, status, body)
        lines.extend(
            "[OK]   %s %s created (new entrypoint)" % (name, rule["ref"]) for rule in wanted
        )
        return lines

    ruleset_id = ruleset.get("id")
    existing = ruleset.get("rules") or []
    for rule in wanted:
        matches = [r for r in existing if r.get("ref") == rule["ref"]]
        if len(matches) > 1:
            raise ApplyError(
                "%s: %d rules carry ref %s; remove the extras first"
                % (name, len(matches), rule["ref"])
            )
        if not matches:
            lines.append("[MISS] %s %s: create" % (name, rule["ref"]))
            if dry_run:
                lines.append("       " + json.dumps(rule, sort_keys=True))
                continue
            url = "%s/%s/rules" % (base, ruleset_id)
            status, body = transport("POST", url, rule)
            _checked("POST", url, status, body)
            lines.append("[OK]   %s %s created" % (name, rule["ref"]))
        elif drifted(matches[0], rule):
            lines.append("[DIFF] %s %s: update (id=%s)" % (name, rule["ref"], matches[0].get("id")))
            if dry_run:
                lines.append("       " + json.dumps(rule, sort_keys=True))
                continue
            url = "%s/%s/rules/%s" % (base, ruleset_id, matches[0].get("id"))
            status, body = transport("PATCH", url, rule)
            _checked("PATCH", url, status, body)
            lines.append("[OK]   %s %s updated" % (name, rule["ref"]))
        else:
            lines.append(
                "[OK]   %s %s unchanged (id=%s)" % (name, rule["ref"], matches[0].get("id"))
            )
    return lines


def run(dry_run: bool, root: Path | None = None, transport: Transport | None = None) -> int:
    root = root or paths.repo_root()
    config = load_config(root)
    hosts = account_hosts(root)
    wanted = [rule_body(rule, hosts) for rule in config["rules"]]
    if transport is None and (not dry_run or has_credentials()):
        transport = curl_transport()
    print("account hosts: %s" % " ".join(hosts))
    for zone in config["zones"]:
        for line in apply_zone(zone, wanted, transport, dry_run):
            print(line)
    return 0


def main(argv: list[str]) -> int:
    dry_run = False
    for arg in argv:
        if arg == "--dry-run":
            dry_run = True
        elif arg in ("-h", "--help"):
            sys.stdout.write(HELP)
            return 0
        else:
            print("unknown arg: %s" % arg, file=sys.stderr)
            return 2
    try:
        return run(dry_run)
    except ApplyError as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

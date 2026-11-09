"""Port of `scripts/ops/apply-cf-redirect-rules.sh` (149 lines): apply and verify the Cloudflare apex redirect rule for rediacc.com.

    PYTHONPATH=.ci python3 -m rediacc_ci.ops.apply_cf_redirect_rules [--dry-run] [--zone <rediacc.com|rediacc.cloud>]

WHY IT EXISTS. Google Search Console reported ~58 indexed URLs on the bare apex `rediacc.com/*` returning 404, because the apex used to CNAME to a dead GitHub Pages site. The Worker-side redirect table (`workers/www/src/redirects.json`) only sees `www.rediacc.com`, so a zone-level Redirect Rule has to bounce apex to www before the Worker runs.

ZONES (PLAN-website-routing-and-mail W0). With no `--zone` the run is the original one: the rediacc.com zone and its apex rule only. `--zone <name>` applies that zone's whole rule list from `RULE_SETS`: rediacc.com gets the apex rule and `edge.rediacc.com` -> www (the host goes once rename L11 lands), rediacc.cloud gets its apex and `www.rediacc.cloud` 301 to `https://www.rediacc.com/`. A zone with no `http_request_dynamic_redirect` ruleset gets one created holding the missing rules. A redirect rule only fires on a proxied record, so the placeholder DNS records are a separate (live) step.

IDEMPOTENT. It reads the zone's `http_request_dynamic_redirect` ruleset, checks that a 301 `redirect` rule with the apex expression exists, creates it (POST to the ruleset's rules, which appends and leaves the existing ones alone) when it does not, then smoke-tests the public path and prints the console.rediacc.com advisory. `--dry-run` never mutates.

Auth: `CLOUDFLARE_API_TOKEN`, or `CF_GLOBAL_API_KEY` + `CF_EMAIL`.

RULE T: WHERE THIS DELIBERATELY DIFFERS FROM THE BASH (each pinned by a test in `tests/test_ops_apply_cf_redirect_rules.py` that fails on the bash behaviour).

  1. A CLOUDFLARE ERROR SHOWS CLOUDFLARE'S MESSAGE. `curl -sSf` turned every 4xx into curl's `error: 403` with the JSON body that explains it discarded; each call now reads the body and prints `errors[].message`.
  2. MORE THAN ONE MATCHING RULESET OR RULE IS A FAILURE. `jq -r '... | .id'` printed one id per match and the script then interpolated a multi-line value into a URL.
  3. THE SMOKE TEST IS ONE HEAD REQUEST, and its verdict is the port's own parse of the status line and `Location`, not `head -1 | awk '{print $2}'` twice over the network.
  4. THE ADVISORY CANNOT UNDO A SUCCESS. The last lookup ran under `set -e`, so a failing DNS query after the rule had been created ended the run with curl's exit 22. It is best-effort here, and an account with no such record prints `no DNS record` where the bash printed `null proxied=null`.
  5. THE CREATE REQUEST IS A SINGLE RULE OBJECT. The bash posted `{"rules": [<rule>]}`, which Cloudflare rejects with 400 `invalid JSON: unknown field "rules"`: the create path had never worked. Run live on 2026-10-01 with the apex rule deleted first, the bash exited 22 and left the apex without its redirect. The port posts the bare rule and reads the new id from the last rule of the returned ruleset.
  6. `--help` PRINTS THIS MODULE'S USAGE, not every column-zero comment in the script (`grep '^#'`).
"""

from __future__ import annotations

import dataclasses
import json
import os
import subprocess
import sys

from rediacc_ci.core import curl_stdin
from rediacc_ci.well_known import APEX_DOMAIN, CF_API_BASE, PRODUCT_DOMAIN, SITE_ORIGIN

ZONE_ID = "9e802649c143c9cefd811d8fd671d31c"  # rediacc.com
# Zone ids by name. rediacc.cloud: created by rename L3 (PLAN-product-domain-rename.md), the product zone.
ZONE_IDS = {
    APEX_DOMAIN: ZONE_ID,
    PRODUCT_DOMAIN: "30f0c9cf60109cd4e10eb2d0a285b0db",
}
REDIRECT_PHASE = "http_request_dynamic_redirect"
API = CF_API_BASE
APEX_EXPR = '(http.request.full_uri wildcard r"https://' + APEX_DOMAIN + '/*")'
APEX_TARGET_EXPR = (
    'wildcard_replace(http.request.full_uri, r"https://'
    + APEX_DOMAIN
    + '/*", '
    + 'r"'
    + SITE_ORIGIN
    + '/${1}")'
)
SMOKE_URL = "https://" + APEX_DOMAIN + "/solutions/backup-verification/"


@dataclasses.dataclass(frozen=True)
class Rule:
    """One 301 redirect rule: what it matches, where it goes and how its live behaviour is smoke-tested."""

    label: str
    expression: str
    target_expression: str
    description: str
    smoke_url: str
    ok_text: str
    preserve_query_string: bool = True
    # A fixed target URL goes in `target_url.value`. Cloudflare parses `target_url.expression` as a ruleset expression, and a bare quoted string there is refused with "Filter parsing error (1:1) ... expected identifier character" (live, 2026-11-09).
    target_value: str = ""


APEX_RULE = Rule(
    label="apex",
    expression=APEX_EXPR,
    target_expression=APEX_TARGET_EXPR,
    description="Redirect from root to WWW",
    smoke_url=SMOKE_URL,
    ok_text="[OK]   " + APEX_DOMAIN + "/* -> www." + APEX_DOMAIN + "/* (live, 301)",
)


def _host_rule(label: str, host: str, target: str, description: str, keep_path: bool) -> Rule:
    """A rule for every URL on `host`: to `target` as a fixed URL, or with the path and query carried over."""
    expression = '(http.request.full_uri wildcard r"https://' + host + '/*")'
    if keep_path:
        target_expression = (
            'wildcard_replace(http.request.full_uri, r"https://'
            + host
            + '/*", r"'
            + target
            + '/${1}")'
        )
    else:
        target_expression = ""
    return Rule(
        label=label,
        expression=expression,
        target_expression=target_expression,
        target_value="" if keep_path else target + "/",
        description=description,
        smoke_url="https://" + host + "/",
        ok_text="[OK]   %s/* -> %s (live, 301)" % (host, target),
        preserve_query_string=keep_path,
    )


# The rule list each `--zone` applies. No `--zone` is [APEX_RULE] on the rediacc.com zone, the original run.
RULE_SETS: dict[str, tuple[Rule, ...]] = {
    APEX_DOMAIN: (
        APEX_RULE,
        _host_rule(
            "edge",
            "edge." + APEX_DOMAIN,
            SITE_ORIGIN,
            f"edge host moves to www (product hosts are on {PRODUCT_DOMAIN})",
            keep_path=True,
        ),
    ),
    PRODUCT_DOMAIN: (
        _host_rule(
            "cloud-apex",
            PRODUCT_DOMAIN,
            SITE_ORIGIN,
            "Product-domain apex sends people to the marketing site",
            keep_path=False,
        ),
        _host_rule(
            "cloud-www",
            "www." + PRODUCT_DOMAIN,
            SITE_ORIGIN,
            "www on the product domain sends people to the marketing site",
            keep_path=False,
        ),
    ),
}
HELP = (
    """Apply + verify the Cloudflare apex redirect rule for """
    + APEX_DOMAIN
    + """ -> www."""
    + APEX_DOMAIN
    + """.

Usage:
  apply_cf_redirect_rules            verify, create if missing
  apply_cf_redirect_rules --dry-run  verify only, never mutate
  apply_cf_redirect_rules --zone <"""
    + "|".join(RULE_SETS)
    + """>
                                     apply that zone's whole rule list

Auth: CLOUDFLARE_API_TOKEN, or CF_GLOBAL_API_KEY + CF_EMAIL.
"""
)


class ApplyError(Exception):
    """A step failed; the message goes to stderr and the exit status is 1."""


def auth_headers() -> list[str]:
    token = os.environ.get("CLOUDFLARE_API_TOKEN")
    key = os.environ.get("CF_GLOBAL_API_KEY")
    email = os.environ.get("CF_EMAIL")
    if token:
        return ["-H", "Authorization: Bearer %s" % token]
    if key and email:
        return ["-H", "X-Auth-Email: %s" % email, "-H", "X-Auth-Key: %s" % key]
    raise ApplyError("set CLOUDFLARE_API_TOKEN or CF_GLOBAL_API_KEY + CF_EMAIL")


def _api(headers: list[str], method: str, url: str, body: dict | None = None) -> dict:
    argv = ["curl", "-sS", "-X", method, *headers]
    if body is not None:
        argv += ["-H", "Content-Type: application/json", "-d", json.dumps(body)]
    argv.append(url)
    # The credential headers go on curl's stdin (`curl_stdin`), never on its argv.
    argv, config = curl_stdin.stdin_headers(argv)
    proc = subprocess.run(argv, input=config, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise ApplyError("%s %s failed: %s" % (method, url, proc.stderr.strip()[:300]))
    try:
        decoded = json.loads(proc.stdout)
    except ValueError:
        raise ApplyError("%s %s did not return JSON" % (method, url)) from None
    if not isinstance(decoded, dict) or decoded.get("success") is False:
        errors = decoded.get("errors") if isinstance(decoded, dict) else None
        detail = "; ".join(str(e.get("message", e)) for e in errors or [] if isinstance(e, dict))
        raise ApplyError("%s %s refused by Cloudflare: %s" % (method, url, detail or "no detail"))
    return decoded


def rule_ids(ruleset: dict, rule: Rule) -> list[str]:
    """Ids of every 301 redirect rule carrying `rule`'s expression."""
    rules = (ruleset.get("result") or {}).get("rules") or []
    return [
        r["id"]
        for r in rules
        if r.get("expression") == rule.expression
        and r.get("action") == "redirect"
        and ((r.get("action_parameters") or {}).get("from_value") or {}).get("status_code") == 301
    ]


def apex_rule_ids(ruleset: dict) -> list[str]:
    """Ids of every 301 redirect rule carrying the apex expression."""
    return rule_ids(ruleset, APEX_RULE)


def rule_payload(rule: Rule) -> dict:
    """The rule itself: the `POST .../rulesets/<id>/rules` endpoint takes ONE rule object and answers with the whole ruleset."""
    return {
        "expression": rule.expression,
        "action": "redirect",
        "action_parameters": {
            "from_value": {
                "status_code": 301,
                "preserve_query_string": rule.preserve_query_string,
                "target_url": (
                    {"value": rule.target_value}
                    if rule.target_value
                    else {"expression": rule.target_expression}
                ),
            }
        },
        "description": rule.description,
    }


def new_rule_payload() -> dict:
    return rule_payload(APEX_RULE)


def _smoke(rules: tuple[Rule, ...]) -> None:
    print()
    print("smoke test:")
    for rule in rules:
        proc = subprocess.run(
            ["curl", "-sI", rule.smoke_url], capture_output=True, text=True, check=False
        )
        lines = proc.stdout.splitlines()
        status = lines[0].split()[1] if lines and len(lines[0].split()) > 1 else ""
        location = ""
        for line in lines:
            if line.lower().startswith("location:"):
                location = line.split(None, 1)[1].strip() if len(line.split(None, 1)) > 1 else ""
        if status == "301" and ("www." + APEX_DOMAIN) in location:
            print(rule.ok_text)
        else:
            print(
                "[WARN] smoke test unexpected: status=%s location=%s" % (status, location),
                file=sys.stderr,
            )


def _advisory(headers: list[str], zone_id: str) -> None:
    try:
        records = _api(
            headers, "GET", ("%s/zones/%s/dns_records?name=console." + APEX_DOMAIN) % (API, zone_id)
        )
        result = records.get("result") or []
        cname = (
            "%s proxied=%s" % (result[0].get("content"), str(result[0].get("proxied")).lower())
            if result
            else "no DNS record"
        )
    except ApplyError as exc:
        cname = "lookup failed (%s)" % exc
    print()
    print("advisory:")
    print(("  console." + APEX_DOMAIN + " -> %s") % cname)
    print("  Not proxied; CF Redirect Rules can't intercept it.")
    print("  Fix (manual): flip proxied=true on that CNAME + add a redirect rule,")
    print("  OR change the CNAME to an orange-clouded host we control.")
    print("  Priority: low (1 URL in GSC 404 list).")


def _create_ruleset(headers: list[str], zone: str, zone_id: str, missing: list[Rule]) -> str:
    """Create the zone's redirect ruleset holding `missing`; return its id."""
    created = _api(
        headers,
        "POST",
        "%s/zones/%s/rulesets" % (API, zone_id),
        {
            "name": "redirect rules for %s" % zone,
            "kind": "zone",
            "phase": REDIRECT_PHASE,
            "rules": [rule_payload(r) for r in missing],
        },
    )
    ruleset_id = (created.get("result") or {}).get("id")
    if not ruleset_id:
        raise ApplyError("CF API did not return a ruleset id for zone %s" % zone)
    return ruleset_id


def run(dry_run: bool, zone: str | None = None) -> int:
    zone_name = zone or APEX_DOMAIN
    rules = RULE_SETS[zone_name] if zone else (APEX_RULE,)
    zone_id = ZONE_IDS[zone_name]
    headers = auth_headers()
    listing = _api(headers, "GET", "%s/zones/%s/rulesets" % (API, zone_id))
    ruleset_ids = [r["id"] for r in listing.get("result") or [] if r.get("phase") == REDIRECT_PHASE]
    if len(ruleset_ids) > 1:
        raise ApplyError("more than one %s ruleset on zone %s" % (REDIRECT_PHASE, zone_id))
    if not ruleset_ids:
        # A zone that never had a redirect rule has no ruleset: create it with every rule.
        print("[MISS] no %s ruleset on zone %s" % (REDIRECT_PHASE, zone_name))
        if dry_run:
            print("       (dry-run: would create it with %d rule(s))" % len(rules))
            return 0
        ruleset_id = _create_ruleset(headers, zone_name, zone_id, list(rules))
        print("[OK]   created ruleset %s with %d rule(s)" % (ruleset_id, len(rules)))
        _smoke(rules)
        return 0
    ruleset_id = ruleset_ids[0]
    print("ruleset: %s" % ruleset_id)

    current = _api(headers, "GET", "%s/zones/%s/rulesets/%s" % (API, zone_id, ruleset_id))
    missing: list[Rule] = []
    for rule in rules:
        present = rule_ids(current, rule)
        if len(present) > 1:
            raise ApplyError(
                "more than one %s redirect rule is present: %s" % (rule.label, " ".join(present))
            )
        if present:
            print("[OK]   %s redirect rule present (id=%s)" % (rule.label, present[0]))
        else:
            print("[MISS] %s redirect rule absent" % rule.label)
            if dry_run:
                print("       (dry-run: would create it)")
            missing.append(rule)
    if dry_run and missing:
        return 0
    for rule in missing:
        created = _api(
            headers,
            "POST",
            "%s/zones/%s/rulesets/%s/rules" % (API, zone_id, ruleset_id),
            rule_payload(rule),
        )
        created_rules = (created.get("result") or {}).get("rules") or []
        new_id = created_rules[-1].get("id") if created_rules else None
        if not new_id:
            print("[FAIL] CF API did not return a rule id", file=sys.stderr)
            print(json.dumps(created, indent=2), file=sys.stderr)
            return 1
        print("[OK]   created %s redirect rule id=%s" % (rule.label, new_id))
    _smoke(rules)
    if zone_name == APEX_DOMAIN:
        _advisory(headers, zone_id)
    return 0


def main(argv: list[str]) -> int:
    dry_run = False
    zone: str | None = None
    args = list(argv)
    while args:
        arg = args.pop(0)
        if arg == "--dry-run":
            dry_run = True
        elif arg == "--zone":
            if not args or args[0] not in RULE_SETS:
                print("--zone takes one of: %s" % " ".join(RULE_SETS), file=sys.stderr)
                return 2
            zone = args.pop(0)
        elif arg in ("-h", "--help"):
            sys.stdout.write(HELP)
            return 0
        else:
            print("unknown arg: %s" % arg, file=sys.stderr)
            return 2
    try:
        return run(dry_run, zone)
    except ApplyError as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

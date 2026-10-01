"""Port of `scripts/ops/apply-cf-redirect-rules.sh` (149 lines): apply and verify the Cloudflare apex redirect rule for rediacc.com.

    PYTHONPATH=.ci python3 -m rediacc_ci.ops.apply_cf_redirect_rules [--dry-run]

WHY IT EXISTS. Google Search Console reported ~58 indexed URLs on the bare apex `rediacc.com/*` returning 404, because the apex used to CNAME to a dead GitHub Pages site. The Worker-side redirect table (`workers/www/src/redirects.json`) only sees `www.rediacc.com`, so a zone-level Redirect Rule has to bounce apex to www before the Worker runs.

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

import json
import os
import subprocess
import sys

from rediacc_ci.well_known import APEX_DOMAIN, CF_API_BASE, SITE_ORIGIN

ZONE_ID = "9e802649c143c9cefd811d8fd671d31c"  # rediacc.com
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
HELP = (
    """Apply + verify the Cloudflare apex redirect rule for """
    + APEX_DOMAIN
    + """ -> www."""
    + APEX_DOMAIN
    + """.

Usage:
  apply_cf_redirect_rules            verify, create if missing
  apply_cf_redirect_rules --dry-run  verify only, never mutate

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
    proc = subprocess.run(argv, capture_output=True, text=True, check=False)
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


def apex_rule_ids(ruleset: dict) -> list[str]:
    """Ids of every 301 redirect rule carrying the apex expression."""
    rules = (ruleset.get("result") or {}).get("rules") or []
    return [
        r["id"]
        for r in rules
        if r.get("expression") == APEX_EXPR
        and r.get("action") == "redirect"
        and ((r.get("action_parameters") or {}).get("from_value") or {}).get("status_code") == 301
    ]


def new_rule_payload() -> dict:
    """The rule itself: the `POST .../rulesets/<id>/rules` endpoint takes ONE rule object and answers with the whole ruleset."""
    return {
        "expression": APEX_EXPR,
        "action": "redirect",
        "action_parameters": {
            "from_value": {
                "status_code": 301,
                "preserve_query_string": True,
                "target_url": {"expression": APEX_TARGET_EXPR},
            }
        },
        "description": "Redirect from root to WWW",
    }


def _smoke() -> None:
    print()
    print("smoke test:")
    proc = subprocess.run(["curl", "-sI", SMOKE_URL], capture_output=True, text=True, check=False)
    lines = proc.stdout.splitlines()
    status = lines[0].split()[1] if lines and len(lines[0].split()) > 1 else ""
    location = ""
    for line in lines:
        if line.lower().startswith("location:"):
            location = line.split(None, 1)[1].strip() if len(line.split(None, 1)) > 1 else ""
    if status == "301" and ("www." + APEX_DOMAIN) in location:
        print("[OK]   " + APEX_DOMAIN + "/* -> www." + APEX_DOMAIN + "/* (live, 301)")
    else:
        print(
            "[WARN] smoke test unexpected: status=%s location=%s" % (status, location),
            file=sys.stderr,
        )


def _advisory(headers: list[str]) -> None:
    try:
        records = _api(
            headers, "GET", ("%s/zones/%s/dns_records?name=console." + APEX_DOMAIN) % (API, ZONE_ID)
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


def run(dry_run: bool) -> int:
    headers = auth_headers()
    listing = _api(headers, "GET", "%s/zones/%s/rulesets" % (API, ZONE_ID))
    ruleset_ids = [
        r["id"]
        for r in listing.get("result") or []
        if r.get("phase") == "http_request_dynamic_redirect"
    ]
    if not ruleset_ids:
        raise ApplyError("no http_request_dynamic_redirect ruleset on zone %s" % ZONE_ID)
    if len(ruleset_ids) > 1:
        raise ApplyError("more than one http_request_dynamic_redirect ruleset on zone %s" % ZONE_ID)
    ruleset_id = ruleset_ids[0]
    print("ruleset: %s" % ruleset_id)

    current = _api(headers, "GET", "%s/zones/%s/rulesets/%s" % (API, ZONE_ID, ruleset_id))
    present = apex_rule_ids(current)
    if len(present) > 1:
        raise ApplyError("more than one apex redirect rule is present: %s" % " ".join(present))
    if present:
        print("[OK]   apex redirect rule present (id=%s)" % present[0])
    else:
        print("[MISS] apex redirect rule absent")
        if dry_run:
            print("       (dry-run: would create it)")
            return 0
        created = _api(
            headers,
            "POST",
            "%s/zones/%s/rulesets/%s/rules" % (API, ZONE_ID, ruleset_id),
            new_rule_payload(),
        )
        rules = (created.get("result") or {}).get("rules") or []
        new_id = rules[-1].get("id") if rules else None
        if not new_id:
            print("[FAIL] CF API did not return a rule id", file=sys.stderr)
            print(json.dumps(created, indent=2), file=sys.stderr)
            return 1
        print("[OK]   created apex redirect rule id=%s" % new_id)
    _smoke()
    _advisory(headers)
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

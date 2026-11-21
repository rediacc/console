"""`./run.sh enterprise dns ensure [--check]` (PLAN-enterprise-tenants box E3): the one wildcard record that sends every company host to Cloudflare's edge.

    ./run.sh enterprise dns ensure [--check]

`ensure` makes one proxied `AAAA * -> 100::` in the product zone (the originless address for a Worker-only host), through `ops.cf_dns.ensure_record`, and asserts that Universal SSL is enabled, active and covers `*.<product domain>`. A `*` record of another type is refused. `--check` reads and asserts and changes nothing.

EXIT CODES. 0 every claim holds (and, without `--check`, the record exists); 1 a claim failed, named on stderr; 2 usage.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from rediacc_ci.ops import apply_cf_redirect_rules as redirects
from rediacc_ci.ops import cf_dns
from rediacc_ci.well_known import PRODUCT_DOMAIN

if TYPE_CHECKING:
    from collections.abc import Sequence

WILDCARD = "*." + PRODUCT_DOMAIN
ORIGINLESS = "100::"
COMMENT = "wildcard for Worker-only hosts"
EXIT_USAGE = 2
USAGE = (__doc__ or "").split("\n\n")[1]


class DnsClaimError(Exception):
    """A claim about the zone does not hold; the message names it."""


def ensure(check_only: bool, http: cf_dns.Http | None = None) -> str:
    """Make the wildcard record and assert Universal SSL; the returned line says what was done. `check_only` changes nothing."""
    try:
        call = http or cf_dns.live_http(redirects.auth_headers())
        if check_only:
            found = cf_dns.records(PRODUCT_DOMAIN, WILDCARD, call)
            clash = [r for r in found if r.get("type") != "AAAA"]
            if clash:
                raise DnsClaimError(
                    "%s already has a %s record, not an AAAA" % (WILDCARD, clash[0].get("type"))
                )
            mine = [r for r in found if r.get("content") == ORIGINLESS and r.get("proxied")]
            if not mine:
                raise DnsClaimError(
                    "no proxied AAAA %s -> %s record at %s" % ("*", ORIGINLESS, WILDCARD)
                )
            action = "present"
        else:
            action = cf_dns.ensure_record(
                PRODUCT_DOMAIN, WILDCARD, "AAAA", ORIGINLESS, True, COMMENT, call
            ).action
        enabled, hosts, status = cf_dns.universal_ssl(PRODUCT_DOMAIN, call)
    except (cf_dns.DnsError, redirects.ApplyError) as exc:
        raise DnsClaimError(str(exc)) from None
    if not enabled:
        raise DnsClaimError("Universal SSL is not enabled for %s" % PRODUCT_DOMAIN)
    if status != "active":
        raise DnsClaimError("the Universal SSL certificate is %s, not active" % status)
    if not cf_dns.covers(hosts, WILDCARD):
        raise DnsClaimError(
            "the Universal SSL certificate does not cover %s (covers: %s)"
            % (WILDCARD, ", ".join(hosts) or "nothing")
        )
    return "%s %s; Universal SSL active and covers %s" % (WILDCARD, action, WILDCARD)


def main(argv: Sequence[str], *, http: cf_dns.Http | None = None) -> int:
    args = list(argv)
    if args in (["-h"], ["--help"]):
        print(USAGE)
        return 0
    if not args or args[0] != "ensure" or any(a != "--check" for a in args[1:]):
        print(USAGE, file=sys.stderr)
        return EXIT_USAGE
    try:
        print(ensure("--check" in args[1:], http))
    except DnsClaimError as exc:
        print("enterprise dns: %s" % exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

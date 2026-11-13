"""One small Cloudflare DNS and TLS client (PLAN-enterprise-tenants E1).

    PYTHONPATH=.ci python3 -m rediacc_ci.ops.cf_dns ensure <zone> <name> <type> <content> [--proxied] [--comment <text>] [--dry-run]
    PYTHONPATH=.ci python3 -m rediacc_ci.ops.cf_dns show <zone> [<name>]
    PYTHONPATH=.ci python3 -m rediacc_ci.ops.cf_dns ssl <zone>

`<zone>` is a zone name from `apply_cf_redirect_rules.ZONE_IDS`. `<name>` is the full host name. Auth is `apply_cf_redirect_rules.auth_headers` (`CLOUDFLARE_API_TOKEN`, or `CF_GLOBAL_API_KEY` + `CF_EMAIL`).

`ensure_record` is idempotent: it creates the record, updates it in place when content, proxied flag or comment differ, and leaves it alone when they match. It refuses a record of another type at the same name (A and AAAA may share a name; a CNAME shares with nothing). A record comment never carries a company label: a comment containing, as a whole word, any label of the host name below the zone is refused (an apex record has no such label). `show` reads every page of the zone's records.

A Cloudflare error shows Cloudflare's own `errors[].message`. Nothing here runs a live call unless the CLI is invoked.
"""

from __future__ import annotations

import dataclasses
import json
import re
import sys
import typing

from rediacc_ci.ops import apply_cf_redirect_rules as redirects
from rediacc_ci.ops import cf_auth

Http = typing.Callable[[str, str, "dict | None"], dict]

ADDRESS_TYPES = frozenset({"A", "AAAA"})
USAGE = __doc__
PAGE_SIZE = 100
MAX_PAGES = 100


class DnsError(Exception):
    """A DNS or TLS request or precondition failed; the message is what the operator sees."""


@dataclasses.dataclass(frozen=True)
class Ensured:
    """What `ensure_record` did: `created`, `updated` or `unchanged`."""

    action: str
    record_id: str


def zone_id(zone: str) -> str:
    """The zone id for a zone name."""
    try:
        return redirects.ZONE_IDS[zone]
    except KeyError:
        raise DnsError(
            "unknown zone %s (known: %s)" % (zone, ", ".join(redirects.ZONE_IDS))
        ) from None


def live_http(headers: list[str]) -> Http:
    """The live transport over `cf_auth.curl_json`, which keeps the credential off curl's argv."""

    def http(method: str, path: str, body: dict | None = None) -> dict:
        try:
            return cf_auth.curl_json(
                method,
                cf_auth.CF_API_BASE + path,
                headers,
                None if body is None else json.dumps(body),
            )
        except cf_auth.CfAuthError as exc:
            raise DnsError(str(exc)) from None

    return http


def _result(body: dict, what: str) -> typing.Any:
    if body.get("success") is not True:
        raise DnsError("%s failed: %s" % (what, cf_auth._errors(body)))
    return body.get("result")


def records(zone: str, name: str | None, http: Http) -> list[dict]:
    """The zone's DNS records, filtered to `name` when given."""
    base = "/zones/%s/dns_records?per_page=%d" % (zone_id(zone), PAGE_SIZE)
    if name:
        base += "&name=" + name
    out: list[dict] = []
    for page in range(1, MAX_PAGES + 1):
        body = http("GET", "%s&page=%d" % (base, page), None)
        found = list(_result(body, "listing DNS records") or [])
        out += found
        total = (body.get("result_info") or {}).get("total_pages")
        if len(found) < PAGE_SIZE or (isinstance(total, int) and page >= total):
            return out
    raise DnsError("listing DNS records: more than %d pages" % MAX_PAGES)


def _check_comment(zone: str, name: str, comment: str) -> None:
    # The apex has no host label: its zone labels are the product's own name, not a company's.
    host = "" if name == zone else name.removesuffix("." + zone)
    labels = [x for x in host.split(".") if x and x != "*"]
    lowered = comment.lower()
    for label in labels:
        # A whole word only: the label `ci` must not refuse `decision log`.
        if re.search(r"(?<![a-z0-9])%s(?![a-z0-9])" % re.escape(label.lower()), lowered):
            raise DnsError("the record comment must not carry a host label (found %r)" % label)


def _conflicts(existing: dict, rtype: str) -> bool:
    other = existing.get("type")
    if other == rtype:
        return False
    return not (other in ADDRESS_TYPES and rtype in ADDRESS_TYPES)


def ensure_record(
    zone: str,
    name: str,
    rtype: str,
    content: str,
    proxied: bool,
    comment: str,
    http: Http,
    dry_run: bool = False,
) -> Ensured:
    """Create, update in place or leave unchanged the one `rtype` record at `name`."""
    _check_comment(zone, name, comment)
    found = records(zone, name, http)
    clash = [r for r in found if _conflicts(r, rtype)]
    if clash:
        raise DnsError(
            "%s already has a %s record; refusing to add %s" % (name, clash[0].get("type"), rtype)
        )
    same = [r for r in found if r.get("type") == rtype]
    if len(same) > 1:
        raise DnsError("%s has %d %s records; refusing to pick one" % (name, len(same), rtype))
    wanted = {
        "type": rtype,
        "name": name,
        "content": content,
        "proxied": proxied,
        "ttl": 1,
        "comment": comment,
    }
    base = "/zones/%s/dns_records" % zone_id(zone)
    if not same:
        if dry_run:
            return Ensured("created", "")
        made = _result(http("POST", base, wanted), "creating %s %s" % (rtype, name))
        return Ensured("created", str((made or {}).get("id", "")))
    current = same[0]
    rid = str(current.get("id", ""))
    if (
        current.get("content") == content
        and bool(current.get("proxied")) == proxied
        and (current.get("comment") or "") == comment
    ):
        return Ensured("unchanged", rid)
    if not dry_run:
        _result(http("PUT", "%s/%s" % (base, rid), wanted), "updating %s %s" % (rtype, name))
    return Ensured("updated", rid)


def _covers(host: str, pattern: str) -> bool:
    if pattern == host:
        return True
    if not pattern.startswith("*."):
        return False
    head, dot, tail = host.partition(".")
    return bool(head) and bool(dot) and tail == pattern[2:]


def universal_ssl(zone: str, http: Http) -> tuple[bool, list[str], str]:
    """`(enabled, hosts covered, status)` from the zone's Universal SSL settings and certificate packs."""
    zid = zone_id(zone)
    settings = _result(
        http("GET", "/zones/%s/ssl/universal/settings" % zid, None), "reading Universal SSL"
    )
    packs = _result(
        http("GET", "/zones/%s/ssl/certificate_packs?status=all" % zid, None),
        "reading certificate packs",
    )
    enabled = bool((settings or {}).get("enabled"))
    hosts: list[str] = []
    statuses: list[str] = []
    for pack in packs or []:
        statuses.append(str(pack.get("status", "")))
        for host in pack.get("hosts") or []:
            if host not in hosts:
                hosts.append(host)
    status = "active" if "active" in statuses else (statuses[0] if statuses else "none")
    return enabled, hosts, status


def covers(hosts: list[str], host: str) -> bool:
    """Whether any certificate host pattern covers `host` (a `*.zone` pattern covers one label)."""
    return any(_covers(host, h) for h in hosts)


def main(argv: list[str], http: Http | None = None) -> int:
    args = list(argv)
    if not args or args[0] in ("-h", "--help"):
        print(USAGE)
        return 0 if args else 2
    verb, rest = args[0], args[1:]
    flags = {a for a in rest if a in ("--proxied", "--dry-run")}
    comment = ""
    if "--comment" in rest:
        at = rest.index("--comment")
        if at + 1 >= len(rest):
            print("--comment needs a value", file=sys.stderr)
            return 2
        comment = rest[at + 1]
        rest = rest[:at] + rest[at + 2 :]
    pos = [a for a in rest if not a.startswith("--")]
    dry = "--dry-run" in flags
    try:
        call = http or live_http(redirects.auth_headers())
        if verb == "ensure" and len(pos) == 4:
            res = ensure_record(
                pos[0], pos[1], pos[2], pos[3], "--proxied" in flags, comment, call, dry
            )
            print("%s%s %s" % ("(dry-run) would be " if dry else "", res.action, pos[1]))
            return 0
        if verb == "show" and len(pos) in (1, 2):
            for r in records(pos[0], pos[1] if len(pos) == 2 else None, call):
                print(
                    "%s %s %s proxied=%s"
                    % (r.get("type"), r.get("name"), r.get("content"), bool(r.get("proxied")))
                )
            return 0
        if verb == "ssl" and len(pos) == 1:
            enabled, hosts, status = universal_ssl(pos[0], call)
            print("enabled=%s status=%s hosts=%s" % (enabled, status, ",".join(hosts)))
            return 0
    except (DnsError, redirects.ApplyError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1
    print(USAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

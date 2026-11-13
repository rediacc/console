"""`rediacc_ci.ops.cf_dns` over a recording transport: no network, no curl."""

from __future__ import annotations

import pytest

from rediacc_ci.ops import apply_cf_redirect_rules as redirects
from rediacc_ci.ops import cf_dns
from rediacc_ci.well_known import PRODUCT_DOMAIN

ZONE = PRODUCT_DOMAIN
ZID = redirects.ZONE_IDS[ZONE]
WILD = "*." + ZONE


class Rec:
    """A recording transport: returns the queued bodies and keeps every (method, path, body)."""

    def __init__(self, listing: list[dict] | None = None, extra: list[dict] | None = None):
        self.calls: list[tuple[str, str, dict | None]] = []
        self.listing = listing or []
        self.extra = list(extra or [])

    def __call__(self, method: str, path: str, body: dict | None = None) -> dict:
        self.calls.append((method, path, body))
        if self.extra:
            return self.extra.pop(0)
        if method == "GET":
            return {"success": True, "result": self.listing}
        return {"success": True, "result": {"id": "new1"}}

    def writes(self) -> list[tuple[str, str, dict | None]]:
        return [c for c in self.calls if c[0] != "GET"]


def rec(**kw) -> dict:
    base = {
        "id": "r1",
        "type": "AAAA",
        "name": WILD,
        "content": "100::",
        "proxied": True,
        "comment": "originless",
    }
    return {**base, **kw}


ENSURE_KEYS = ("zone", "name", "rtype", "content", "proxied", "comment")


def ensure(http, **kw):
    args = {
        "zone": ZONE,
        "name": WILD,
        "rtype": "AAAA",
        "content": "100::",
        "proxied": True,
        "comment": "originless",
    }
    args.update(kw)
    unknown = set(args) - {*ENSURE_KEYS, "dry_run"}
    assert not unknown, "ensure() would drop %s" % sorted(unknown)
    return cf_dns.ensure_record(
        http=http,
        zone=str(args["zone"]),
        name=str(args["name"]),
        rtype=str(args["rtype"]),
        content=str(args["content"]),
        proxied=bool(args["proxied"]),
        comment=str(args["comment"]),
        dry_run=bool(args.get("dry_run", False)),
    )


def test_create_posts_one_record():
    http = Rec()
    res = ensure(http)
    assert res.action == "created"
    assert http.writes() == [
        (
            "POST",
            "/zones/%s/dns_records" % ZID,
            {
                "type": "AAAA",
                "name": WILD,
                "content": "100::",
                "proxied": True,
                "ttl": 1,
                "comment": "originless",
            },
        )
    ]


def test_unchanged_writes_nothing():
    http = Rec([rec()])
    assert ensure(http).action == "unchanged"
    assert http.writes() == []


def test_update_in_place_on_content_change():
    http = Rec([rec(content="100::1")])
    res = ensure(http)
    assert res.action == "updated"
    assert [w[:2] for w in http.writes()] == [("PUT", "/zones/%s/dns_records/r1" % ZID)]


def test_proxied_flag_change_updates():
    http = Rec([rec(proxied=False)])
    assert ensure(http).action == "updated"
    body = http.writes()[0][2]
    assert body is not None
    assert body["proxied"] is True
    http = Rec([rec(proxied=False)])
    assert ensure(http, proxied=False).action == "unchanged"


def test_conflicting_type_refused():
    http = Rec([rec(type="CNAME", content="x.example.net")])
    with pytest.raises(cf_dns.DnsError, match="CNAME"):
        ensure(http)
    assert http.writes() == []


def test_a_and_aaaa_share_a_name():
    http = Rec([rec(type="A", content="192.0.2.1", proxied=False)])
    assert ensure(http).action == "created"


def test_dry_run_never_writes():
    http = Rec([rec(content="old")])
    assert ensure(http, dry_run=True).action == "updated"
    assert http.writes() == []
    http = Rec()
    assert ensure(http, dry_run=True).action == "created"
    assert http.writes() == []


def test_comment_with_label_refused():
    http = Rec()
    with pytest.raises(cf_dns.DnsError, match="label"):
        ensure(http, name="acme." + ZONE, comment="tenant Acme edge")
    assert http.calls == []


def test_comment_without_label_passes():
    http = Rec()
    assert ensure(http, name="acme." + ZONE, comment="tenant host").action == "created"


def test_a_short_label_matches_whole_words_only():
    """8d3cf5ea.1: the label `ci` refuses the word `ci` and not `decision`."""
    http = Rec()
    assert ensure(http, name="ci." + ZONE, comment="decision log").action == "created"
    with pytest.raises(cf_dns.DnsError, match="label"):
        ensure(Rec(), name="ci." + ZONE, comment="the ci edge")


def test_an_apex_record_comment_may_name_the_product():
    """8d3cf5ea.2: the apex has no host label, so a zone label in the comment is fine."""
    product = ZONE.split(".")[0]
    http = Rec()
    assert ensure(http, name=ZONE, comment="%s apex" % product).action == "created"


def test_records_reads_every_page():
    """8d3cf5ea.3: a zone with more than one page lists all of them."""
    pages = {
        1: [{"id": str(i), "type": "A"} for i in range(cf_dns.PAGE_SIZE)],
        2: [{"id": "last", "type": "A"}],
    }
    seen: list[str] = []

    def http(_method, path, _body=None):
        seen.append(path)
        page = int(path.rsplit("page=", 1)[1])
        return {"success": True, "result": pages[page]}

    assert len(cf_dns.records(ZONE, None, http)) == cf_dns.PAGE_SIZE + 1
    assert len(seen) == 2
    assert len(cf_dns.records(ZONE, None, Rec([{"id": "x"}]))) == 1


def test_ensure_helper_refuses_a_keyword_it_would_drop():
    """Review 09b714f6.1: an extra keyword fails loudly instead of passing without being exercised."""
    with pytest.raises(AssertionError, match="ttl"):
        ensure(Rec(), ttl=300)


def test_unknown_zone_refused():
    with pytest.raises(cf_dns.DnsError, match="unknown zone"):
        cf_dns.records("nope.example", None, Rec())


def test_cloudflare_error_message_shown():
    http = Rec(extra=[{"success": False, "errors": [{"message": "Authentication error"}]}])
    with pytest.raises(cf_dns.DnsError, match="Authentication error"):
        cf_dns.records(ZONE, None, http)


SETTINGS = {"success": True, "result": {"enabled": True}}
PACKS = {
    "success": True,
    "result": [
        {"status": "pending_validation", "hosts": ["old." + ZONE]},
        {"status": "active", "hosts": [ZONE, WILD]},
    ],
}


def test_ssl_coverage_parse():
    http = Rec(extra=[SETTINGS, PACKS])
    enabled, hosts, status = cf_dns.universal_ssl(ZONE, http)
    assert (enabled, status) == (True, "active")
    assert WILD in hosts
    assert [c[1] for c in http.calls] == [
        "/zones/%s/ssl/universal/settings" % ZID,
        "/zones/%s/ssl/certificate_packs?status=all" % ZID,
    ]


def test_ssl_disabled_and_no_packs():
    off = {"success": True, "result": {"enabled": False}}
    http = Rec(extra=[off, {"success": True, "result": []}])
    assert cf_dns.universal_ssl(ZONE, http) == (False, [], "none")


def test_covers_one_label_only():
    assert cf_dns.covers([WILD], "acme." + ZONE)
    assert not cf_dns.covers([WILD], "a.b." + ZONE)
    assert not cf_dns.covers([ZONE], "acme." + ZONE)


def test_cli_ensure_and_error_exit(capsys):
    argv = ["ensure", ZONE, WILD, "AAAA", "100::", "--proxied", "--comment", "x"]
    assert cf_dns.main(argv, Rec()) == 0
    assert "created" in capsys.readouterr().out
    bad = Rec([rec(type="CNAME")])
    assert cf_dns.main(["ensure", ZONE, WILD, "AAAA", "100::"], bad) == 1
    assert "CNAME" in capsys.readouterr().err


def test_cli_show_and_ssl(capsys):
    assert cf_dns.main(["show", ZONE], Rec([rec()])) == 0
    assert "AAAA" in capsys.readouterr().out
    assert cf_dns.main(["ssl", ZONE], Rec(extra=[SETTINGS, PACKS])) == 0
    assert "status=active" in capsys.readouterr().out
    assert cf_dns.main(["bogus"], Rec()) == 2

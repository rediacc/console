"""`./run.sh enterprise dns ensure [--check]` (PLAN-enterprise-tenants box E3): the wildcard record and the Universal SSL claims, over a fake Cloudflare. No live call."""

from __future__ import annotations

import pytest

from rediacc_ci.enterprise import dns
from rediacc_ci.ops import apply_cf_redirect_rules as redirects
from rediacc_ci.well_known import PRODUCT_DOMAIN

ZID = redirects.ZONE_IDS[PRODUCT_DOMAIN]
WILD = "*." + PRODUCT_DOMAIN


class FakeCf:
    """DNS records and Universal SSL of one zone; every call is recorded."""

    def __init__(self, records=(), enabled=True, status="active", hosts=(WILD, PRODUCT_DOMAIN)):
        self.records = [dict(r) for r in records]
        self.enabled = enabled
        self.status = status
        self.hosts = list(hosts)
        self.calls: list[tuple[str, str]] = []

    def __call__(self, method, path, body=None):
        self.calls.append((method, path.split("?")[0]))
        base = "/zones/%s" % ZID
        if method == "GET" and path.startswith(base + "/dns_records"):
            name = path.split("name=")[1] if "name=" in path else None
            found = [r for r in self.records if name in (None, r["name"])]
            return {"success": True, "result": found}
        if method == "POST" and path == base + "/dns_records":
            self.records.append({**body, "id": "new1"})
            return {"success": True, "result": {"id": "new1"}}
        if path == base + "/ssl/universal/settings":
            return {"success": True, "result": {"enabled": self.enabled}}
        if path.startswith(base + "/ssl/certificate_packs"):
            return {"success": True, "result": [{"status": self.status, "hosts": self.hosts}]}
        raise AssertionError("unexpected call %s %s" % (method, path))

    def writes(self):
        return [c for c in self.calls if c[0] != "GET"]


def _wild(rtype="AAAA", content=dns.ORIGINLESS, proxied=True):
    return {
        "id": "w1",
        "type": rtype,
        "name": WILD,
        "content": content,
        "proxied": proxied,
        "comment": dns.COMMENT,
    }


def test_an_absent_wildcard_is_created_proxied_to_the_originless_address():
    cf = FakeCf()
    line = dns.ensure(False, cf)
    assert cf.records[0]["type"] == "AAAA"
    assert cf.records[0]["content"] == dns.ORIGINLESS
    assert cf.records[0]["proxied"] is True
    assert "created" in line


def test_a_present_wildcard_is_a_no_op():
    cf = FakeCf([_wild()])
    line = dns.ensure(False, cf)
    assert cf.writes() == []
    assert "unchanged" in line


def test_a_wildcard_of_another_type_is_refused_and_nothing_is_written():
    cf = FakeCf([_wild(rtype="CNAME", content="x.example")])
    with pytest.raises(dns.DnsClaimError, match="CNAME"):
        dns.ensure(False, cf)
    assert cf.writes() == []


@pytest.mark.parametrize(
    ("kw", "needle"),
    [
        ({"enabled": False}, "not enabled"),
        ({"status": "pending_validation"}, "pending_validation"),
        ({"hosts": (PRODUCT_DOMAIN,)}, "does not cover"),
    ],
)
def test_universal_ssl_claims_each_refuse_by_name(kw, needle):
    cf = FakeCf([_wild()], **kw)
    with pytest.raises(dns.DnsClaimError, match=needle):
        dns.ensure(False, cf)


def test_check_writes_nothing_when_the_wildcard_is_absent_and_names_it():
    cf = FakeCf()
    with pytest.raises(dns.DnsClaimError, match="no proxied AAAA"):
        dns.ensure(True, cf)
    assert cf.writes() == []
    assert cf.records == []


def test_check_passes_on_a_complete_zone_without_a_write():
    cf = FakeCf([_wild()])
    assert "present" in dns.ensure(True, cf)
    assert cf.writes() == []


def test_check_refuses_an_unproxied_or_foreign_wildcard():
    with pytest.raises(dns.DnsClaimError, match="no proxied AAAA"):
        dns.ensure(True, FakeCf([_wild(proxied=False)]))
    with pytest.raises(dns.DnsClaimError, match="CNAME"):
        dns.ensure(True, FakeCf([_wild(rtype="CNAME", content="x.example")]))


def test_check_still_asserts_universal_ssl():
    with pytest.raises(dns.DnsClaimError, match="not enabled"):
        dns.ensure(True, FakeCf([_wild()], enabled=False))


def test_main_exit_codes(capsys):
    assert dns.main(["ensure", "--check"], http=FakeCf([_wild()])) == 0
    assert dns.main(["ensure", "--check"], http=FakeCf()) == 1
    assert "no proxied AAAA" in capsys.readouterr().err
    assert dns.main([], http=FakeCf()) == 2
    assert dns.main(["ensure", "--force"], http=FakeCf()) == 2
    assert dns.main(["-h"]) == 0

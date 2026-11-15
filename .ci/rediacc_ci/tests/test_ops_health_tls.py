"""The local refresh lets the served certificate decide a handshake-ok tls probe (the Worker cannot read a peer certificate), within the probe's issuer scope, and recomputes the verdict by the Worker's own rule."""

from __future__ import annotations

import datetime
import json
import pathlib

from rediacc_ci import paths
from rediacc_ci.ops import ops_health as oh

NOW = datetime.datetime(2026, 11, 15, 12, 0, tzinfo=datetime.UTC)
CFG = oh.load_config(pathlib.Path("/nonexistent"))
ENV = {"OPS_HEALTH_URL": "https://ops-health.example.test", "OPS_HEALTH_READ_TOKEN": "r"}
STALE_CT = "2026-12-06T10:24:36Z"
STALE_DETAIL = (
    'handshake ok; newest certificate (issuer "Let\'s Encrypt", cache) expires %s, 20 day(s): '
    "warning, under 21" % STALE_CT
)
JAN_2027 = datetime.datetime(2027, 1, 15, tzinfo=datetime.UTC)


def status(probes, verdict="red"):
    return {
        "last_cron_at": oh.iso(NOW - datetime.timedelta(minutes=5)),
        "targets_sha": "abc",
        "verdict": verdict,
        "probes": probes,
        "ingest": [],
    }


def web(probes, verdict="red"):
    doc = status(probes, verdict)

    def fetch(_method, _url, _headers, _body):
        return oh.Reply(200, json.dumps(doc))

    return fetch


def probe(ident="tls:erp.rediacc.io", state="red", detail=STALE_DETAIL):
    return {"probe": ident, "state": state, "since": "2026-11-15T10:00:00Z", "detail": detail}


def no_run(*_args) -> oh.Result:
    raise AssertionError("no rdc call expected")


def check(fetch, handshake, cfg=CFG):
    return oh.offbox_check(cfg, ENV, fetch, no_run, NOW, False, handshake=handshake)


LETS_ENCRYPT = "countryName=US organizationName=Let's Encrypt commonName=R10"
GTS = "countryName=US organizationName=Google Trust Services commonName=WE1"


class Served:
    """A fake handshake answering one notAfter and issuer (or None for a failed handshake)."""

    def __init__(self, date, issuer=LETS_ENCRYPT):
        self.date = date
        self.issuer = issuer
        self.calls: list = []

    def __call__(self, host, port, timeout):
        self.calls.append((host, port, timeout))
        return None if self.date is None else oh.ServedCertificate(self.date, self.issuer)


def test_later_served_certificate_clears_a_stale_ct_red():
    hs = Served(JAN_2027)
    out = check(web([probe()]), hs)
    assert out["rc"] == 0
    assert out["verdict"] == "green"
    assert hs.calls == [("erp.rediacc.io", 443, oh.HANDSHAKE_TIMEOUT_S)]


def test_served_detail_says_the_served_certificate_decided():
    doc = status([probe()])
    oh.refresh_tls_probes(doc, CFG, NOW, Served(JAN_2027))
    detail = doc["probes"][0]["detail"]
    assert "served certificate expires 2027-01-15T00:00:00Z" in detail
    assert "CT answer %s" % STALE_CT in detail


def test_served_certificate_that_is_itself_near_expiry_stays_red():
    later_ct = STALE_DETAIL.replace(STALE_CT, "2026-11-25T00:00:00Z")
    out = check(
        web([probe(detail=later_ct)]), Served(datetime.datetime(2026, 12, 1, tzinfo=datetime.UTC))
    )
    assert out["rc"] == 1
    assert "warning, under 21" in out["detail"]
    assert "served certificate expires 2026-12-01T00:00:00Z" in out["detail"]


def test_failed_handshake_changes_nothing():
    out = check(web([probe()]), Served(None))
    assert out["rc"] == 1
    assert STALE_CT in out["detail"]


def test_served_certificate_equal_to_the_ct_date_still_decides():
    """091c4c29.1: an equal date used to be skipped, leaving the Worker's answer; the served date now decides, so a certificate 20 days out is red on its own expiry."""
    out = check(web([probe()]), Served(datetime.datetime(2026, 12, 5, 10, 24, tzinfo=datetime.UTC)))
    assert out["rc"] == 1
    assert "local handshake" in out["detail"], out


def test_unknown_probe_with_no_ct_date_is_judged_by_the_served_certificate():
    """2026-11-15: certspotter 503 and crt.sh timing out left a dozen hosts unknown, and an unknown probe makes the verdict unknown."""
    unknown = probe(
        "tls:svc.example.test",
        state="unknown",
        detail='handshake ok; days to expiry unknown for issuer "Let\'s Encrypt" (certspotter answered 503; The operation was aborted due to timeout)',
    )
    out = check(web([unknown], verdict="unknown"), Served(JAN_2027))
    assert out["rc"] == 0, out


def test_control_a_failed_worker_handshake_is_never_overruled():
    failed = probe(
        "tls:svc.example.test", state="red", detail="handshake failed: connection refused"
    )
    hs = Served(JAN_2027)
    out = check(web([failed]), hs)
    assert out["rc"] == 1
    assert hs.calls == []


def test_non_tls_and_unparsed_probes_are_not_handshaken():
    hs = Served(JAN_2027)
    out = check(web([probe("https:erp"), probe(detail="handshake failed")]), hs)
    assert out["rc"] == 1
    assert hs.calls == []


def test_unknown_worker_state_with_a_crtsh_date_is_judged_by_the_served_certificate():
    detail = (
        "handshake ok; expiry not judged for any issuer: certspotter failed (x), "
        "crt.sh fallback newest 2026-09-07T00:00:00Z may be stale"
    )
    hs = Served(JAN_2027)
    out = check(web([probe("tls:mail.rediacc.io:465", "unknown", detail)], "unknown"), hs)
    assert out["rc"] == 0
    assert hs.calls[0][:2] == ("mail.rediacc.io", 465)


def test_another_red_probe_keeps_the_verdict_red():
    out = check(web([probe(), probe("https:x", "red", "boom")]), Served(JAN_2027))
    assert out["rc"] == 1


def test_served_certificate_reads_a_failed_connection_as_none():
    assert oh.served_certificate("127.0.0.1", 1, 0.5) is None


def test_a_served_certificate_earlier_than_the_ct_date_decides_a_green_ct_red():
    """a0f45d3d.1: the host serves a certificate that expires before the newest CT one (a renewal not installed yet), so clients see the earlier expiry."""
    ct_green = (
        'handshake ok; newest certificate (issuer "Let\'s Encrypt", cache) expires '
        "2027-06-01T00:00:00Z, 198 day(s)"
    )
    served = datetime.datetime(2026, 11, 20, tzinfo=datetime.UTC)
    out = check(web([probe(state="green", detail=ct_green)], verdict="green"), Served(served))
    assert out["rc"] == 1
    assert "served certificate expires 2026-11-20T00:00:00Z" in out["detail"]
    assert "critical, under 7" in out["detail"]
    # control: a served certificate as late as the CT one stays green
    out = check(
        web([probe(state="green", detail=ct_green)], verdict="green"),
        Served(datetime.datetime(2027, 6, 1, tzinfo=datetime.UTC)),
    )
    assert out["rc"] == 0


def test_a_served_certificate_from_another_issuer_never_overrules_an_issuer_scoped_answer():
    """091c4c29.5: the probe is scoped to the origin's Let's Encrypt issuance, so a Cloudflare edge certificate says nothing about it."""
    out = check(web([probe()]), Served(JAN_2027, issuer=GTS))
    assert out["rc"] == 1
    assert STALE_CT in out["detail"]
    # control: the same certificate from the scoped issuer decides
    assert check(web([probe()]), Served(JAN_2027))["rc"] == 0
    # control: an `any issuer` answer takes whichever issuer the host serves
    any_issuer = probe(
        state="unknown",
        detail="handshake ok; days to expiry unknown for any issuer (certspotter answered 503)",
    )
    assert check(web([any_issuer], verdict="unknown"), Served(JAN_2027, issuer=GTS))["rc"] == 0


def _with_ingest(rows, probes=None, verdict="red"):
    doc = status(probes if probes is not None else [probe()], verdict)
    doc["ingest"] = rows

    def fetch(_method, _url, _headers, _body):
        return oh.Reply(200, json.dumps(doc))

    return fetch


def _ingest(source, state, hours_old):
    return {
        "source": source,
        "state": state,
        "at": oh.iso(NOW - datetime.timedelta(hours=hours_old)),
        "detail": "x",
    }


def test_a_fresh_red_ingest_entry_keeps_the_verdict_red_after_a_probe_clears():
    out = check(_with_ingest([_ingest("local-machine-x", "red", 1)]), Served(JAN_2027))
    assert out["rc"] == 1
    assert out["verdict"] == "red"


def test_a_stale_red_ingest_entry_is_ignored_as_the_worker_ignores_it():
    """The Worker counts a red entry only while it is younger than its `max_age_h` (local-* is 24 h)."""
    configured = oh.load_config(paths.repo_root())
    stale = _with_ingest([_ingest("local-machine-x", "red", 30)])
    out = check(stale, Served(JAN_2027), configured)
    assert out["rc"] == 0
    assert out["verdict"] == "green"
    # control: the same entry counts when it is younger than the limit, and with no table at all
    assert (
        check(_with_ingest([_ingest("local-machine-x", "red", 3)]), Served(JAN_2027), configured)[
            "rc"
        ]
        == 1
    )
    assert check(stale, Served(JAN_2027))["rc"] == 1


def test_an_unknown_ingest_entry_never_decides_the_verdict():
    """091c4c29.4: the Worker's verdict reads probes for unknown and ingest only for red, so an unknown entry beside green probes is green there too."""
    out = check(_with_ingest([_ingest("local-machine-x", "unknown", 1)]), Served(JAN_2027))
    assert out["rc"] == 0
    assert out["verdict"] == "green"


def test_a_cleared_probe_beside_an_unknown_one_leaves_the_verdict_unknown():
    other = probe("https:x", "unknown", "slow")
    out = check(_with_ingest([], probes=[probe(), other], verdict="red"), Served(JAN_2027))
    assert out["verdict"] == "unknown"
    assert out["rc"] == 2


def test_a_stale_cron_stays_unknown_after_a_probe_changes():
    doc = status([probe(state="unknown", detail=STALE_DETAIL)], "unknown")
    doc["last_cron_at"] = oh.iso(NOW - datetime.timedelta(hours=3))
    oh.refresh_tls_probes(doc, CFG, NOW, Served(JAN_2027))
    assert doc["verdict"] == "unknown"

"""The ops-health `dmarc` check against a fake rdc runner that plays the mail container: the streamed parser runs in-process over recorded report shapes, and no rdc call, SSH or DNS lookup leaves the process."""

from __future__ import annotations

import base64
import datetime
import gzip
import io
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import zipfile
from email.message import EmailMessage

import pytest

from rediacc_ci.ops import dmarc_parser as dp
from rediacc_ci.ops import dmarc_reports as dr
from rediacc_ci.ops import ops_health as oh
from rediacc_ci.well_known import APEX_DOMAIN, INFRA_DOMAIN, OPERATOR_EMAIL

REPO = pathlib.Path(__file__).resolve().parents[3]
TODAY = datetime.date(2026, 11, 16)
# 2026-11-15T00:00Z .. 2026-11-15T23:59:59Z
BEGIN, END = 1794700800, 1794787199

HOSTINGER = "72.61.137.225"
SES_IP = "69.169.224.17"
M365_IP = "40.107.22.91"
ZOHO_IP = "185.20.209.14"
STRANGER = "203.0.113.50"

# --------------------------------------------------------------------------- recorded report shapes


def google_xml(records):
    """Google's shape: no namespace, `<version>` absent, a zip attachment."""
    rows = "".join(
        """
  <record>
    <row>
      <source_ip>%s</source_ip>
      <count>%d</count>
      <policy_evaluated>
        <disposition>%s</disposition>
        <dkim>%s</dkim>
        <spf>%s</spf>
      </policy_evaluated>
    </row>
    <identifiers>
      <header_from>%s</header_from>
    </identifiers>
    <auth_results>
      <dkim>
        <domain>%s</domain>
        <result>%s</result>
        <selector>default</selector>
      </dkim>
      <spf>
        <domain>%s</domain>
        <result>%s</result>
      </spf>
    </auth_results>
  </record>"""
        % (
            ip,
            n,
            "none" if "pass" in (dk, sp) else "reject",
            dk,
            sp,
            dom,
            dom,
            dk,
            dom,
            sp,
        )
        for ip, n, dk, sp, dom in records
    )
    domain = records[0][4] if records else APEX_DOMAIN
    return (
        """<?xml version="1.0" encoding="UTF-8" ?>
<feedback>
  <report_metadata>
    <org_name>google.com</org_name>
    <email>noreply-dmarc-support@google.com</email>
    <extra_contact_info>https://support.google.com/a/answer/2466580</extra_contact_info>
    <report_id>4150712881276541092</report_id>
    <date_range>
      <begin>%d</begin>
      <end>%d</end>
    </date_range>
  </report_metadata>
  <policy_published>
    <domain>%s</domain>
    <adkim>s</adkim>
    <aspf>r</aspf>
    <p>reject</p>
    <sp>reject</sp>
    <pct>100</pct>
    <np>reject</np>
  </policy_published>%s
</feedback>
"""
        % (BEGIN, END, domain, rows)
    ).encode()


def microsoft_xml(records, report_id="b8a0d7f2e5c94f1e8f1c0e3a6d2b4c71"):
    """Outlook.com's shape: xsd/xsi namespace declarations, `<version>`, `<envelope_to>` and a gzip attachment."""
    rows = "".join(
        """<record><row><source_ip>%s</source_ip><count>%d</count><policy_evaluated>"""
        """<disposition>%s</disposition><dkim>%s</dkim><spf>%s</spf></policy_evaluated></row>"""
        """<identifiers><envelope_to>outlook.com</envelope_to><envelope_from>%s</envelope_from>"""
        """<header_from>%s</header_from></identifiers><auth_results><dkim><domain>%s</domain>"""
        """<selector>s1</selector><result>%s</result></dkim><spf><domain>%s</domain><scope>mfrom</scope>"""
        """<result>%s</result></spf></auth_results></record>"""
        % (
            ip,
            n,
            "none" if "pass" in (dk, sp) else "reject",
            dk,
            sp,
            dom,
            dom,
            dom,
            dk,
            dom,
            sp,
        )
        for ip, n, dk, sp, dom in records
    )
    return (
        """<?xml version="1.0"?><feedback xmlns:xsd="http://www.w3.org/2001/XMLSchema" """
        """xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><version>1.0</version>"""
        """<report_metadata><org_name>Enterprise Outlook</org_name>"""
        """<email>dmarcreport@microsoft.com</email><report_id>%s</report_id>"""
        """<date_range><begin>%d</begin><end>%d</end></date_range></report_metadata>"""
        """<policy_published><domain>%s</domain><adkim>s</adkim><aspf>r</aspf><p>reject</p>"""
        """<sp>reject</sp><pct>100</pct><fo>1</fo></policy_published>%s</feedback>"""
        % (report_id, BEGIN, END, records[0][4], rows)
    ).encode()


def yahoo_xml(records, report_id="1794787199.574123"):
    """Yahoo's shape: the DMARC 2.0 default namespace and a gzip attachment."""
    rows = "".join(
        """
 <record>
  <row>
   <source_ip>%s</source_ip>
   <count>%d</count>
   <policy_evaluated>
    <disposition>none</disposition>
    <dkim>%s</dkim>
    <spf>%s</spf>
   </policy_evaluated>
  </row>
  <identifiers>
   <header_from>%s</header_from>
  </identifiers>
  <auth_results>
   <spf>
    <domain>%s</domain>
    <result>%s</result>
   </spf>
  </auth_results>
 </record>"""
        % (ip, n, dk, sp, dom, dom, sp)
        for ip, n, dk, sp, dom in records
    )
    return (
        """<?xml version="1.0"?>
<feedback xmlns="urn:ietf:params:xml:ns:dmarc-2.0">
 <report_metadata>
  <org_name>Yahoo</org_name>
  <email>dmarchelp@yahooinc.com</email>
  <report_id>%s</report_id>
  <date_range>
   <begin>%d</begin>
   <end>%d</end>
  </date_range>
 </report_metadata>
 <policy_published>
  <domain>%s</domain>
  <adkim>s</adkim>
  <aspf>r</aspf>
  <p>reject</p>
  <sp>reject</sp>
  <pct>100</pct>
 </policy_published>%s
</feedback>
"""
        % (report_id, BEGIN, END, records[0][4], rows)
    ).encode()


def tlsrpt_json(domain=APEX_DOMAIN, failed=0):
    doc = {
        "organization-name": "Google Inc.",
        "date-range": {
            "start-datetime": "2026-11-15T00:00:00Z",
            "end-datetime": "2026-11-15T23:59:59Z",
        },
        "contact-info": "smtp-tls-reporting@google.com",
        "report-id": "2026-11-15T00:00:00Z_%s" % domain,
        "policies": [
            {
                "policy": {
                    "policy-type": "sts",
                    "policy-domain": domain,
                    "mx-host": [f"mail.{INFRA_DOMAIN}"],
                },
                "summary": {
                    "total-successful-session-count": 14,
                    "total-failure-session-count": failed,
                },
                "failure-details": (
                    [
                        {
                            "result-type": "certificate-expired",
                            "sending-mta-ip": "209.85.220.41",
                            "receiving-mx-hostname": f"mail.{INFRA_DOMAIN}",
                            "failed-session-count": failed,
                        }
                    ]
                    if failed
                    else []
                ),
            }
        ],
    }
    return gzip.compress(json.dumps(doc).encode())


def zipped(name, data):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(name, data)
    return buf.getvalue()


def mail(subject, attachment=None, body="This is an aggregate report."):
    msg = EmailMessage()
    msg["From"] = "noreply-dmarc-support@google.com"
    msg["To"] = "dmarc@rediacc.com"
    msg["Subject"] = subject
    msg.set_content(body)
    if attachment is not None:
        name, ctype, data = attachment
        maintype, subtype = ctype.split("/")
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=name)
    return msg.as_string()


def google_mail(records):
    return mail(
        f"Report domain: {APEX_DOMAIN} Submitter: google.com Report-ID: 4150712881276541092",
        (
            f"google.com!{APEX_DOMAIN}!%d!%d.zip" % (BEGIN, END),
            "application/zip",
            zipped("google.com!rediacc.com.xml", google_xml(records)),
        ),
    )


def microsoft_mail(records, report_id="b8a0d7f2e5c94f1e8f1c0e3a6d2b4c71"):
    return mail(
        "Report Domain: %s Submitter: enterprise.protection.outlook.com Report-ID: <%s>"
        % (records[0][4], report_id),
        (
            "enterprise.protection.outlook.com!%s!%d!%d.xml.gz" % (records[0][4], BEGIN, END),
            "application/gzip",
            gzip.compress(microsoft_xml(records, report_id)),
        ),
    )


def yahoo_mail(records, report_id="1794787199.574123"):
    return mail(
        "Report Domain: %s Submitter: yahoo.com" % records[0][4],
        (
            "yahoo.com!%s!%d!%d.xml.gz" % (records[0][4], BEGIN, END),
            "application/gzip",
            gzip.compress(yahoo_xml(records, report_id)),
        ),
    )


def tls_mail(failed=0):
    return mail(
        f"Report Domain: {APEX_DOMAIN} Submitter: google.com Report-ID: <2026.11.15T00.00.00Z+{APEX_DOMAIN}@google.com>",
        (
            f"google.com!{APEX_DOMAIN}!1794700800!1794787199!001.json.gz",
            "application/tlsrpt+gzip",
            tlsrpt_json(failed=failed),
        ),
    )


ALL_KNOWN = {
    (OPERATOR_EMAIL, "DMARC"): [
        {
            "uid": "11",
            "text": google_mail(
                [
                    (HOSTINGER, 10, "pass", "pass", APEX_DOMAIN),
                    (M365_IP, 3, "fail", "fail", APEX_DOMAIN),
                ]
            ),
        },
        {"uid": "12", "text": yahoo_mail([(HOSTINGER, 2, "pass", "pass", APEX_DOMAIN)])},
        {"uid": "13", "text": tls_mail()},
        {"uid": "14", "text": mail("Welcome to the DMARC folder", body="not a report")},
    ],
    ("muhammed@rediacc.io", "DMARC"): [
        {
            "uid": "7",
            "text": microsoft_mail(
                [
                    (SES_IP, 40, "pass", "pass", INFRA_DOMAIN),
                    (ZOHO_IP, 2, "fail", "fail", INFRA_DOMAIN),
                ]
            ),
        },
    ],
}

# --------------------------------------------------------------------------- the fake container

PARSE_RE = re.compile(
    r"^printf %s (\S+) \| base64 -d \| docker exec -i mail-server python3 -I - (\S+)$"
)
MARK_RE = re.compile(
    r"^docker exec mail-server doveadm flags add -u (\S+) '\\Seen' mailbox (\S+) uid ([\d,]+)$"
)


class Container:
    """A scripted `rdc term connect mail@hostinger -c`: the parse command runs the streamed parser over `boxes`; the mark command is recorded."""

    def __init__(self, boxes, *, fail_parse=None, fail_mark=False, box_errors=()):
        self.boxes = boxes
        self.fail_parse = fail_parse
        self.fail_mark = fail_mark
        self.box_errors = set(box_errors)
        self.calls: list[list] = []
        self.marked: dict[tuple, list] = {}

    def fetch(self, user, mailbox):
        if (user, mailbox) in self.box_errors:
            msg = "doveadm fetch %s %s rc 75: Mailbox doesn't exist" % (user, mailbox)
            raise dp.FetchError(msg)
        return list(self.boxes.get((user, mailbox), []))

    def __call__(self, argv, env, _timeout):
        self.calls.append(list(argv))
        assert env[oh.NO_PROVISION_ENV] == "1"
        assert argv[1:6] == ["--config", "eu-bench", "term", "connect", "mail@hostinger"]
        assert argv[6] == "-c"
        command = argv[7]
        hit = PARSE_RE.match(command)
        if hit:
            if self.fail_parse is not None:
                return self.fail_parse
            script = base64.b64decode(hit.group(1)).decode()
            assert script == pathlib.Path(dp.__file__).read_text(encoding="utf-8")
            spec = json.loads(base64.b64decode(hit.group(2)))
            doc = dp.collect(spec["mailboxes"], self.fetch)
            return oh.Result(0, dp.MARKER + json.dumps(doc) + "\n")
        matches = [MARK_RE.match(p) for p in command.split(" && ")]
        if all(matches):
            if self.fail_mark:
                return oh.Result(
                    75, "", f"doveadm({OPERATOR_EMAIL}): Error: Mailbox DMARC: lock timeout"
                )
            for found in matches:
                if found is not None:
                    user, mailbox, uids = found.groups()
                    self.marked[(user, mailbox)] = uids.split(",")
            return oh.Result(0)
        return oh.Result(99, "", "unexpected command %r" % command)


RDNS = {
    STRANGER: "mail.spoofer.example",
    M365_IP: "mail-am6eur05on2091.outbound.protection.outlook.com",
    "198.51.100.7": "b224-17.smtp-out.eu-central-1.amazonses.com",
}


def resolver(ip):
    return RDNS.get(ip, "")


@pytest.fixture
def root(tmp_path):
    (tmp_path / ".ci" / "config").mkdir(parents=True)
    shutil.copy(REPO / dr.KNOWN_REL, tmp_path / dr.KNOWN_REL)
    return tmp_path


def edit_known(root, **changes):
    path = root / dr.KNOWN_REL
    doc = json.loads(path.read_text())
    doc.update(changes)
    path.write_text(json.dumps(doc))


def run(root, container, today=TODAY):
    return dr.run(root, runner=container, env={"PATH": "/usr/bin"}, resolve=resolver, today=today)


def text(out):
    return "\n".join(out["lines"])


# --------------------------------------------------------------------------- verdicts


def test_all_known_is_green_and_marks_only_the_report_messages(root):
    box = Container(ALL_KNOWN)
    out = run(root, box)
    assert out["rc"] == 0, text(out)
    assert out["counts"] == {"aggregate": 3, "tlsrpt": 1, "other": 1, "records": 5, "failed": 5}
    # The non-report message (uid 14) is never marked.
    assert box.marked == {
        (OPERATOR_EMAIL, "DMARC"): ["11", "12", "13"],
        ("muhammed@rediacc.io", "DMARC"): ["7"],
    }
    assert f"old-provider Microsoft 365, the old {APEX_DOMAIN} provider (ruled 2026-11-16)" in text(
        out
    )
    assert "Zoho EU" in text(out)
    assert text(out).splitlines()[-1].startswith("dmarc: green")


def test_a_new_failing_source_is_red_naming_it_and_its_report_stays_unread(root):
    boxes = dict(ALL_KNOWN)
    boxes[(OPERATOR_EMAIL, "DMARC")] = [
        *ALL_KNOWN[(OPERATOR_EMAIL, "DMARC")],
        {"uid": "15", "text": yahoo_mail([(STRANGER, 9, "fail", "fail", APEX_DOMAIN)], "y-2")},
    ]
    box = Container(boxes)
    out = run(root, box)
    assert out["rc"] == 1
    line = text(out).splitlines()[-1]
    assert line.startswith(
        f"dmarc.source.new: {APEX_DOMAIN} from %s (rdns mail.spoofer.example)" % STRANGER
    )
    assert "9 message(s)" in line
    assert "reported by Yahoo" in line
    assert dr.KNOWN_REL in line
    assert box.marked[(OPERATOR_EMAIL, "DMARC")] == ["11", "12", "13"]


def test_ours_failing_is_red(root):
    box = Container(
        {
            (OPERATOR_EMAIL, "DMARC"): [
                {"uid": "3", "text": google_mail([(HOSTINGER, 4, "fail", "fail", APEX_DOMAIN)])},
            ]
        }
    )
    out = run(root, box)
    assert out["rc"] == 1
    assert f"dmarc.ours.failing: {APEX_DOMAIN} from %s (hostinger mail server" % HOSTINGER in text(
        out
    )
    assert "4 message(s) (dkim fail, spf fail)" in text(out)
    assert box.marked == {}


def test_ours_matched_by_forward_confirmed_rdns_suffix(root):
    box = Container(
        {
            (OPERATOR_EMAIL, "DMARC"): [
                {
                    "uid": "3",
                    "text": google_mail([("198.51.100.7", 1, "fail", "fail", APEX_DOMAIN)]),
                },
            ]
        }
    )
    out = run(root, box)
    assert "dmarc.ours.failing" in text(out)
    assert "Amazon SES" in text(out)


def test_acknowledged_through_silences_ours_failing_up_to_the_day(root):
    boxes = {
        (OPERATOR_EMAIL, "DMARC"): [
            {"uid": "3", "text": google_mail([(HOSTINGER, 4, "fail", "fail", APEX_DOMAIN)])},
        ]
    }
    edit_known(root, acknowledged_through={APEX_DOMAIN: "2026-11-15"})
    assert run(root, Container(boxes))["rc"] == 0
    edit_known(root, acknowledged_through={APEX_DOMAIN: "2026-11-14"})
    assert run(root, Container(boxes))["rc"] == 1


def test_old_provider_failing_is_silent(root):
    box = Container(
        {
            ("muhammed@rediacc.io", "DMARC"): [
                {"uid": "7", "text": microsoft_mail([(ZOHO_IP, 3, "fail", "fail", INFRA_DOMAIN)])},
            ]
        }
    )
    out = run(root, box)
    assert out["rc"] == 0, text(out)
    assert box.marked == {("muhammed@rediacc.io", "DMARC"): ["7"]}


def test_old_provider_passing_dmarc_is_red(root):
    box = Container(
        {
            (OPERATOR_EMAIL, "DMARC"): [
                {"uid": "3", "text": google_mail([(M365_IP, 2, "pass", "fail", APEX_DOMAIN)])},
            ]
        }
    )
    out = run(root, box)
    assert out["rc"] == 1
    assert (
        f"dmarc.ruled.passing: {APEX_DOMAIN} from %s (Microsoft 365, the old {APEX_DOMAIN} provider, old-provider"
        % M365_IP
        in text(out)
    )
    assert "DNS still authorizes it" in text(out)
    assert box.marked == {}


def test_old_provider_ruling_is_scoped_to_its_domain(root):
    # Zoho failing for rediacc.com is not the rediacc.io ruling: a new source.
    box = Container(
        {
            (OPERATOR_EMAIL, "DMARC"): [
                {"uid": "3", "text": google_mail([(ZOHO_IP, 1, "fail", "fail", APEX_DOMAIN)])},
            ]
        }
    )
    assert f"dmarc.source.new: {APEX_DOMAIN} from %s" % ZOHO_IP in text(run(root, box))


def test_old_provider_volume_over_the_daily_limit_is_red(root):
    box = Container(
        {
            ("muhammed@rediacc.io", "DMARC"): [
                {
                    "uid": "7",
                    "text": microsoft_mail([(ZOHO_IP, 12, "fail", "fail", INFRA_DOMAIN)], "r-1"),
                },
                {
                    "uid": "8",
                    "text": yahoo_mail([(ZOHO_IP, 9, "fail", "fail", INFRA_DOMAIN)], "r-2"),
                },
            ]
        }
    )
    out = run(root, box)
    assert out["rc"] == 1
    assert (
        f"dmarc.ruled.volume: Zoho EU, the old {INFRA_DOMAIN} provider ({INFRA_DOMAIN}): 21 message(s) on 2026-11-15, over the 20 a day limit"
        in text(out)
    )
    assert box.marked == {}


def test_old_provider_at_the_daily_limit_is_green(root):
    box = Container(
        {
            ("muhammed@rediacc.io", "DMARC"): [
                {
                    "uid": "7",
                    "text": microsoft_mail([(ZOHO_IP, 20, "fail", "fail", INFRA_DOMAIN)], "r-1"),
                },
            ]
        }
    )
    assert run(root, box)["rc"] == 0


def _history(root, first, per_day):
    path = dr.history_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    reports = {
        "old|%s" % day: {
            "ruling": f"Zoho EU, the old {INFRA_DOMAIN} provider",
            "day": day,
            "count": n,
        }
        for day, n in per_day.items()
    }
    path.write_text(json.dumps({"first": first, "reports": reports}))


def _zoho(count):
    return Container(
        {
            ("muhammed@rediacc.io", "DMARC"): [
                {
                    "uid": "7",
                    "text": microsoft_mail(
                        [(ZOHO_IP, count, "fail", "fail", INFRA_DOMAIN)], "r-new"
                    ),
                },
            ]
        }
    )


def test_old_provider_volume_jump_over_the_trailing_average_is_red(root):
    days = {
        (datetime.date(2026, 11, 14) - datetime.timedelta(days=n)).isoformat(): 1 for n in range(14)
    }
    _history(root, "2026-10-20", days)
    out = run(root, _zoho(6))
    assert out["rc"] == 1
    assert "dmarc.ruled.volume: Zoho EU" in text(out)
    assert "6.0x the 14-day average of 1.00" in text(out)


def test_trailing_average_controls(root):
    days = {
        (datetime.date(2026, 11, 14) - datetime.timedelta(days=n)).isoformat(): 1 for n in range(14)
    }
    # Under 5x the average: green.
    _history(root, "2026-10-20", days)
    assert run(root, _zoho(4))["rc"] == 0
    # 5x and more, but the history is younger than the trailing window: green.
    _history(root, "2026-11-10", days)
    assert run(root, _zoho(6))["rc"] == 0


def test_history_counts_a_reread_report_once(root):
    box = Container(
        {
            ("muhammed@rediacc.io", "DMARC"): [
                {
                    "uid": "7",
                    "text": microsoft_mail([(ZOHO_IP, 15, "fail", "fail", INFRA_DOMAIN)], "r-1"),
                },
            ]
        }
    )
    run(root, box)
    run(root, box)
    hist = json.loads(dr.history_path(root).read_text())
    assert sum(r["count"] for r in hist["reports"].values()) == 15
    assert hist["first"] == TODAY.isoformat()


def test_tlsrpt_failure_is_red(root):
    box = Container({(OPERATOR_EMAIL, "DMARC"): [{"uid": "4", "text": tls_mail(failed=3)}]})
    out = run(root, box)
    assert out["rc"] == 1
    assert (
        f"dmarc.tlsrpt.failure: {APEX_DOMAIN}, 3 failed TLS session(s) (certificate-expired), reported by Google Inc."
        in text(out)
    )


def test_malformed_attachment_names_its_failure_and_stays_unread(root):
    bad = mail(
        f"Report Domain: {APEX_DOMAIN} Submitter: google.com",
        (f"google.com!{APEX_DOMAIN}!1!2.zip", "application/zip", b"PK\x03\x04garbage"),
    )
    box = Container(
        {
            (OPERATOR_EMAIL, "DMARC"): [
                {"uid": "5", "text": bad},
                {"uid": "6", "text": yahoo_mail([(HOSTINGER, 1, "pass", "pass", APEX_DOMAIN)])},
            ]
        }
    )
    out = run(root, box)
    assert out["rc"] == 1
    line = text(out).splitlines()[-1]
    assert line.startswith(f"dmarc.report.malformed: {OPERATOR_EMAIL} DMARC uid 5")
    assert f"google.com!{APEX_DOMAIN}!1!2.zip (application/zip): zip does not open" in line
    assert box.marked == {(OPERATOR_EMAIL, "DMARC"): ["6"]}


@pytest.mark.parametrize(
    "doc",
    [
        b'<?xml version="1.0"?><!DOCTYPE feedback SYSTEM "feedback.dtd"><feedback/>',
        b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><feedback>&a;</feedback>',
    ],
)
def test_xml_with_a_doctype_or_entity_is_refused(doc):
    with pytest.raises(dp.ReportError, match="DOCTYPE"):
        dp.parse_aggregate(doc)


def test_nothing_unread_marks_nothing_and_is_green(root):
    box = Container({})
    out = run(root, box)
    assert out["rc"] == 0
    assert len(box.calls) == 1


def test_an_unreadable_mailbox_is_unknown(root):
    box = Container({}, box_errors={("muhammed@rediacc.io", "DMARC")})
    out = run(root, box)
    assert out["rc"] == 2
    assert "Mailbox doesn't exist" in text(out)


def test_a_failed_read_is_unknown_and_names_the_error(root):
    box = Container(
        {},
        fail_parse=oh.Result(
            1, "", "ssh: connect to host 72.61.137.225 port 22: Connection refused"
        ),
    )
    out = run(root, box)
    assert out["rc"] == 2
    assert "Connection refused" in text(out)
    assert len(box.calls) == 1


def test_a_failed_mark_is_unknown_without_hiding_a_red(root):
    out = run(root, Container(ALL_KNOWN, fail_mark=True))
    assert out["rc"] == 2
    assert "marking 4 report(s) Seen failed (rc 75)" in text(out)
    boxes = {
        (OPERATOR_EMAIL, "DMARC"): [
            {"uid": "3", "text": google_mail([(STRANGER, 1, "fail", "fail", APEX_DOMAIN)])},
            {"uid": "4", "text": yahoo_mail([(HOSTINGER, 1, "pass", "pass", APEX_DOMAIN)])},
        ]
    }
    assert run(root, Container(boxes, fail_mark=True))["rc"] == 1


def test_the_shipped_rulings_file_loads():
    known = dr.load_known(REPO / dr.KNOWN_REL)
    assert {r["verdict"] for r in known["rulings"]} == {"old-provider"}
    assert {r["ruled"] for r in known["rulings"]} == {"2026-11-16"}
    assert known["target"] == {
        "config": "eu-bench",
        "repo": "mail@hostinger",
        "container": "mail-server",
    }


def test_a_ruling_without_a_date_or_with_an_unknown_verdict_is_refused(root):
    path = root / dr.KNOWN_REL
    doc = json.loads(path.read_text())
    doc["rulings"][0].pop("ruled")
    path.write_text(json.dumps(doc))
    with pytest.raises(dr.KnownError, match="no `ruled` date"):
        dr.load_known(path)
    doc["rulings"][0]["ruled"] = "2026-11-16"
    doc["rulings"][0]["verdict"] = "fine"
    path.write_text(json.dumps(doc))
    with pytest.raises(dr.KnownError, match="verdict 'fine'"):
        dr.load_known(path)


def test_a_registry_reference_is_composed_and_an_unknown_one_is_refused(root):
    path = root / dr.KNOWN_REL
    known = dr.load_known(path)
    assert known["mailboxes"][0]["user"] == OPERATOR_EMAIL
    assert known["rulings"][0]["domains"] == [APEX_DOMAIN]
    assert "${" not in json.dumps([r["name"] for r in known["rulings"]])
    doc = json.loads(path.read_text())
    doc["mailboxes"][0]["user"] = "${WK_NO_SUCH_KEY}"
    path.write_text(json.dumps(doc))
    with pytest.raises(dr.KnownError, match="WK_NO_SUCH_KEY is not in"):
        dr.load_known(path)


# --------------------------------------------------------------------------- the streamed script is self-contained


def test_the_streamed_parser_runs_alone_under_python_isolated_mode(tmp_path):
    """The exact bytes streamed run under `python3 -I -` with no rediacc_ci on the path, reading a fake doveadm."""
    rows = [{"uid": "21", "text": google_mail([(HOSTINGER, 1, "pass", "pass", APEX_DOMAIN)])}]
    (tmp_path / "rows.json").write_text(json.dumps(rows))
    doveadm = tmp_path / "bin" / "doveadm"
    doveadm.parent.mkdir()
    doveadm.write_text("#!/bin/sh\ncat %s\n" % (tmp_path / "rows.json"))
    doveadm.chmod(0o755)
    arg = base64.b64encode(
        json.dumps({"mailboxes": [{"user": "u@x", "mailbox": "DMARC"}]}).encode()
    ).decode()
    proc = subprocess.run(
        [sys.executable, "-I", "-", arg],
        input=pathlib.Path(dp.__file__).read_text(encoding="utf-8"),
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={"PATH": "%s:%s" % (doveadm.parent, os.environ.get("PATH", ""))},
        timeout=60,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    line = next(ln for ln in proc.stdout.splitlines() if ln.startswith(dp.MARKER))
    doc = json.loads(line[len(dp.MARKER) :])
    msg = doc["mailboxes"][0]["messages"][0]
    assert (msg["uid"], msg["kind"]) == ("21", "report")
    assert msg["reports"][0]["records"][0]["ip"] == HOSTINGER


# --------------------------------------------------------------------------- review findings


def test_an_unwritable_history_is_unknown_and_marks_nothing(root):
    (root / ".ci" / "cache").write_text("a file where the cache directory belongs")
    box = Container(ALL_KNOWN)
    out = run(root, box)
    assert out["rc"] == 2, text(out)
    assert "history:" in text(out)
    assert box.marked == {}


def test_a_writable_history_control_marks_and_is_green(root):
    box = Container(ALL_KNOWN)
    assert run(root, box)["rc"] == 0
    assert box.marked


def test_a_corrupt_history_file_is_unknown_once_then_repaired(root):
    path = dr.history_path(root)
    path.parent.mkdir(parents=True)
    path.write_text("{not json")
    out = run(root, Container(ALL_KNOWN))
    assert out["rc"] == 2, text(out)
    assert run(root, Container(ALL_KNOWN))["rc"] == 0


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p["summary"].update({"total-successful-session-count": "many"}),
        lambda p: p.update({"summary": ["not", "a", "dict"]}),
        lambda p: p.update({"policy": "not a dict"}),
    ],
)
def test_a_tlsrpt_with_a_bad_count_or_shape_is_a_malformed_message_not_a_raise(mutate):
    doc = json.loads(gzip.decompress(tlsrpt_json()))
    mutate(doc["policies"][0])
    out = dp.parse_message(
        mail("Report-ID", ("r.json", "application/tlsrpt+json", json.dumps(doc).encode()))
    )
    assert out["kind"] == "malformed"
    assert out["reports"] == []


def test_a_tlsrpt_with_good_counts_still_parses():
    out = dp.parse_message(
        mail("Report-ID", ("r.json.gz", "application/tlsrpt+gzip", tlsrpt_json(failed=2)))
    )
    assert out["kind"] == "report"
    assert out["reports"][0]["policies"][0]["failed"] == 2


def test_an_octet_stream_pdf_is_other_but_an_octet_stream_report_is_read():
    pdf = dp.parse_message(mail("invoice", ("invoice.pdf", "application/octet-stream", b"%PDF-1.4 x")))
    assert pdf["kind"] == "other"
    named = dp.parse_message(
        mail("Report-ID", ("report.dat", "application/octet-stream", tlsrpt_json()))
    )
    assert named["kind"] == "report"


def test_a_non_wk_reference_in_the_rulings_is_refused_not_passed_through(root):
    path = root / dr.KNOWN_REL
    doc = json.loads(path.read_text())
    doc["mailboxes"][0]["user"] = "${APEX_DOMAIN}"
    path.write_text(json.dumps(doc))
    with pytest.raises(dr.KnownError, match="not a"):
        dr.load_known(path)

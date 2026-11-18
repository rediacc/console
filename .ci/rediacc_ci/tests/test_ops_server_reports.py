"""The Server-Reports folder in the ops-health `dmarc` check (rediacc_ci.ops.dmarc_reports with the server-reports classifier of rediacc_ci.ops.dmarc_parser).

Fixtures are recorded shapes: SES events wrapped by SNS (the event is a JSON string inside the notification's `Message`), the Postfix daily summary, and the SNS subscription confirmation. Every rule has a control that flips its verdict, so a rule that stops firing fails a test. No real mail server is touched.
"""

from __future__ import annotations

import base64
import datetime
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys

import pytest

from rediacc_ci.ops import dmarc_parser as dp
from rediacc_ci.ops import dmarc_reports as dr
from rediacc_ci.ops import ops_health as oh

REPO = pathlib.Path(__file__).resolve().parents[3]
TODAY = datetime.date(2026, 11, 18)
USER = "muhammed@rediacc.io"
BOX = (USER, "Server-Reports")
SNS = "no-reply@sns.amazonaws.com"
POSTFIX = "mailserver-report@mail.rediacc.io"

# --------------------------------------------------------------------------- recorded shapes


def mail(sender, subject, body):
    return f"From: {sender}\r\nTo: ops@rediacc.com\r\nSubject: {subject}\r\nContent-Type: text/plain\r\n\r\n{body}\r\n"


def sns_mail(event, sender=SNS, subject="Amazon SES Email Event Notification"):
    note = {
        "Type": "Notification",
        "MessageId": "00000000-0000-0000-0000-000000000001",
        "TopicArn": "arn:aws:sns:eu-central-1:111111111111:ses-events",
        "Message": json.dumps(event),
    }
    return mail(sender, subject, json.dumps(note))


def delay(domain, delay_type="TransientCommunicationFailure", n=1):
    addrs = [{"emailAddress": f"user{i}@{domain}"} for i in range(n)]
    return {
        "eventType": "DeliveryDelay",
        "mail": {"destination": [a["emailAddress"] for a in addrs]},
        "deliveryDelay": {"delayType": delay_type, "delayedRecipients": addrs},
    }


def bounce(domain, btype="Transient", sub="General"):
    addrs = [{"emailAddress": f"user@{domain}"}]
    return {
        "eventType": "Bounce",
        "mail": {"destination": [a["emailAddress"] for a in addrs]},
        "bounce": {"bounceType": btype, "bounceSubType": sub, "bouncedRecipients": addrs},
    }


def complaint(domain):
    addrs = [{"emailAddress": f"user@{domain}"}]
    return {
        "eventType": "Complaint",
        "mail": {"destination": [a["emailAddress"] for a in addrs]},
        "complaint": {"complainedRecipients": addrs},
    }


def confirmation():
    return mail(
        SNS,
        "AWS Notification - Subscription Confirmation",
        "You have chosen to subscribe to the topic arn:aws:sns:eu-central-1:111111111111:ses-events.",
    )


def postfix_mail(rejected=0, deferred=0, bounced=0, sender=POSTFIX):
    body = (
        "Postfix log summaries for Nov 17\n\nGrand Totals\n------------\nmessages\n\n"
        f"     12   received\n     12   delivered\n      0   forwarded\n"
        f"{deferred:7d}   deferred  ({deferred}  deferrals)\n"
        f"{bounced:7d}   bounced\n{rejected:7d}   rejected (3%)\n      0   reject warnings\n"
    )
    return mail(sender, "Postfix summary for mail.rediacc.io sent Tue Nov 17 2026", body)


def rows(*texts, start=1):
    return [{"uid": str(start + i), "text": t} for i, t in enumerate(texts)]


# --------------------------------------------------------------------------- the fake container

PARSE_RE = re.compile(
    r"^printf %s (\S+) \| base64 -d \| docker exec -i mail-server python3 -I - (\S+)$"
)
MARK_RE = re.compile(
    r"^docker exec mail-server doveadm flags add -u (\S+) '\\Seen' mailbox (\S+) uid ([\d,]+)$"
)


class Container:
    """A scripted `rdc term connect mail@hostinger -c`: the parse command runs the streamed parser over `messages`; mark commands are recorded; any other command is a failure (nothing is ever moved or deleted)."""

    def __init__(self, messages, *, fail_parse=None, box_error=False):
        self.messages = messages
        self.fail_parse = fail_parse
        self.box_error = box_error
        self.calls: list[str] = []
        self.marked: list[str] = []

    def fetch(self, user, mailbox):
        if (user, mailbox) == BOX:
            if self.box_error:
                raise dp.FetchError(f"doveadm fetch {user} {mailbox} rc 75: Login refused")
            return list(self.messages)
        return []

    def __call__(self, argv, env, _timeout):
        assert env[oh.NO_PROVISION_ENV] == "1"
        command = argv[7]
        self.calls.append(command)
        if PARSE_RE.match(command):
            if self.fail_parse is not None:
                return self.fail_parse
            spec = json.loads(base64.b64decode(PARSE_RE.match(command).group(2)))
            doc = dp.collect(spec["mailboxes"], self.fetch)
            return oh.Result(0, dp.MARKER + json.dumps(doc) + "\n")
        parts = [MARK_RE.match(p) for p in command.split(" && ")]
        if all(parts):
            for found in parts:
                assert found.group(2) == "Server-Reports"
                assert len(found.group(3).split(",")) <= dr.MARK_CHUNK
                self.marked += found.group(3).split(",")
            return oh.Result(0)
        return oh.Result(99, "", f"unexpected command {command!r}")


@pytest.fixture
def root(tmp_path):
    (tmp_path / ".ci" / "config").mkdir(parents=True)
    shutil.copy(REPO / dr.KNOWN_REL, tmp_path / dr.KNOWN_REL)
    return tmp_path


def run(root, container):
    return dr.run(
        root, runner=container, env={"PATH": "/usr/bin"}, resolve=lambda _ip: "", today=TODAY
    )


def text(out):
    return "\n".join(out["lines"])


def verdict(root, *mails):
    box = Container(rows(*mails))
    out = run(root, box)
    return out, box


# --------------------------------------------------------------------------- benign


def test_the_benign_backlog_is_green_and_every_message_is_marked_seen(root):
    out, box = verdict(
        root,
        sns_mail(delay("example.com")),
        sns_mail(bounce("example.com")),
        confirmation(),
        postfix_mail(rejected=3, deferred=1, bounced=0),
    )
    assert out["rc"] == 0, text(out)
    assert box.marked == ["1", "2", "3", "4"]
    assert "server-reports: 4 unread message(s), 4 benign (marked Seen), 0 red" in text(out)


@pytest.mark.parametrize(
    "domain",
    ["example.org", "example.net", "mail.example.com", "host.test", "x.invalid", "a.example"],
)
def test_every_reserved_test_domain_is_benign(root, domain):
    out, box = verdict(root, sns_mail(delay(domain)))
    assert out["rc"] == 0, text(out)
    assert box.marked == ["1"]


@pytest.mark.parametrize("domain", ["notexample.com", "example.com.evil.io", "gmail.cocm"])
def test_a_lookalike_of_a_reserved_domain_is_a_real_domain(root, domain):
    out, box = verdict(root, sns_mail(delay(domain)))
    assert out["rc"] == 1
    assert domain in text(out)
    assert box.marked == []


# --------------------------------------------------------------------------- red by event


def test_a_delay_to_a_real_domain_is_red_naming_event_domain_and_count_never_the_address(root):
    out, box = verdict(
        root,
        sns_mail(delay("rediacc.com", "RecipientServerError")),
        sns_mail(delay("rediacc.com", "RecipientServerError")),
        sns_mail(delay("example.com")),
    )
    assert out["rc"] == 1
    assert (
        "server-reports.ses: DeliveryDelay RecipientServerError to rediacc.com, 2 message(s)"
        in text(out)
    )
    assert "user0@" not in text(out)
    # The benign neighbour is marked, the reds stay unread.
    assert box.marked == ["3"]


def test_a_delay_control_example_com_alone_is_green(root):
    out, _ = verdict(root, sns_mail(delay("example.com", "RecipientServerError")))
    assert out["rc"] == 0


def test_a_permanent_bounce_to_a_reserved_domain_is_red(root):
    out, box = verdict(root, sns_mail(bounce("example.com", "Permanent", "General")))
    assert out["rc"] == 1
    assert "Bounce Permanent/General to example.com, 1 message(s)" in text(out)
    assert box.marked == []


def test_a_transient_bounce_control_is_green(root):
    out, _ = verdict(root, sns_mail(bounce("example.com", "Transient", "General")))
    assert out["rc"] == 0


def test_a_content_rejected_bounce_is_red_even_to_a_reserved_domain(root):
    out, box = verdict(root, sns_mail(bounce("example.com", "Transient", "ContentRejected")))
    assert out["rc"] == 1
    assert "Bounce Transient/ContentRejected to example.com" in text(out)
    assert box.marked == []


def test_a_transient_bounce_to_a_real_domain_is_red(root):
    out, _ = verdict(root, sns_mail(bounce("live.com")))
    assert out["rc"] == 1
    assert "Bounce Transient/General to live.com" in text(out)


def test_a_complaint_is_red_even_to_a_reserved_domain(root):
    out, box = verdict(root, sns_mail(complaint("example.com")))
    assert out["rc"] == 1
    assert "Complaint to example.com" in text(out)
    assert box.marked == []


def test_an_ses_event_with_no_recipient_is_red(root):
    event = {"eventType": "DeliveryDelay", "deliveryDelay": {"delayType": "X"}}
    out, _ = verdict(root, sns_mail(event))
    assert out["rc"] == 1
    assert "no recipient domain" in text(out)


def test_an_unhandled_ses_event_type_is_red(root):
    event = delay("example.com")
    event["eventType"] = "Delivery"
    out, _ = verdict(root, sns_mail(event))
    assert out["rc"] == 1
    assert "unhandled SES event Delivery" in text(out)


# --------------------------------------------------------------------------- postfix summaries


@pytest.mark.parametrize(
    ("key", "limit"),
    [("rejected", 200), ("deferred", 50), ("bounced", 5)],
)
def test_a_postfix_summary_is_red_above_its_limit_and_green_at_it(root, key, limit):
    at, _ = verdict(root, postfix_mail(**{key: limit}))
    assert at["rc"] == 0, text(at)
    over, box = verdict(root, postfix_mail(**{key: limit + 1}))
    assert over["rc"] == 1
    assert (
        f"server-reports.postfix: Postfix summary sent Tue Nov 17 2026: {key} {limit + 1} (limit {limit})"
        in text(over)
    )
    assert box.marked == []


def test_the_postfix_limits_come_from_the_config_file(root):
    path = root / dr.KNOWN_REL
    doc = json.loads(path.read_text())
    doc["server_reports"]["postfix"]["max_rejected"] = 2
    path.write_text(json.dumps(doc))
    out, _ = verdict(root, postfix_mail(rejected=3))
    assert out["rc"] == 1


def test_a_postfix_summary_without_counts_is_red(root):
    out, _ = verdict(root, mail(POSTFIX, "Postfix summary for mail.rediacc.io sent today", "empty"))
    assert out["rc"] == 1
    assert "Postfix summary without a rejected count" in text(out)


def test_a_postfix_summary_count_with_a_k_suffix_is_read(root):
    body = postfix_mail(rejected=2).replace("2   rejected", "2k   rejected")
    out, _ = verdict(root, body)
    assert out["rc"] == 1
    assert "rejected 2000 (limit 200)" in text(out)


# --------------------------------------------------------------------------- subscription, sender, shape


def test_a_subscription_confirmation_is_marked_seen(root):
    out, box = verdict(root, confirmation())
    assert out["rc"] == 0
    assert box.marked == ["1"]


def test_a_json_subscription_confirmation_is_marked_seen(root):
    note = json.dumps({"Type": "SubscriptionConfirmation", "Token": "t"})
    out, box = verdict(root, mail(SNS, "AWS Notification - Subscription Confirmation", note))
    assert out["rc"] == 0
    assert box.marked == ["1"]


def test_an_unknown_sender_is_red_naming_its_domain_only(root):
    out, box = verdict(root, sns_mail(delay("example.com"), sender="alerts@unknown-sender.example"))
    assert out["rc"] == 1
    assert (
        "server-reports.unknown: mail from the unknown sender domain unknown-sender.example"
        in text(out)
    )
    assert "alerts@" not in text(out)
    assert box.marked == []


def test_a_known_sender_control_with_the_same_body_is_green(root):
    out, _ = verdict(root, sns_mail(delay("example.com")))
    assert out["rc"] == 0


def test_a_known_sender_of_a_shape_it_does_not_send_is_red(root):
    out, _ = verdict(root, sns_mail(delay("example.com"), sender=POSTFIX))
    assert out["rc"] == 1
    assert "shape ses-event is not one this sender sends" in text(out)


def test_an_unknown_shape_from_a_known_sender_is_red(root):
    out, box = verdict(root, mail(SNS, "Something else", "free text"))
    assert out["rc"] == 1
    assert "of unknown shape: no known server mail shape" in text(out)
    assert box.marked == []


def test_an_sns_notification_without_an_ses_event_is_red(root):
    note = json.dumps({"Type": "Notification", "Message": "plain words"})
    out, _ = verdict(root, mail(SNS, "Amazon SES Email Event Notification", note))
    assert out["rc"] == 1
    assert "without an SES event JSON" in text(out)


# --------------------------------------------------------------------------- listing, marking, never moving


def test_red_messages_are_listed_once_grouped_not_one_line_each(root):
    mails = [sns_mail(delay("rediacc.com")) for _ in range(50)]
    out, _ = verdict(root, *mails)
    lines = [ln for ln in out["lines"] if ln.startswith("server-reports.ses")]
    assert lines == [
        "server-reports.ses: DeliveryDelay TransientCommunicationFailure to rediacc.com, 50 message(s)"
    ]


def test_the_red_listing_is_capped_with_a_remainder_line(root):
    mails = [sns_mail(delay(f"d{i}.rediacc.com")) for i in range(dr.SERVER_RED_LINES + 5)]
    out, _ = verdict(root, *mails)
    assert (
        len([ln for ln in out["lines"] if ln.startswith("server-reports.ses")])
        == dr.SERVER_RED_LINES
    )
    assert "server-reports: 5 more red group(s), 5 message(s)" in text(out)


def test_a_large_backlog_is_marked_in_chunks_and_nothing_else_runs(root):
    mails = [sns_mail(delay("example.com")) for _ in range(1000)]
    out, box = verdict(root, *mails)
    assert out["rc"] == 0
    assert sorted(box.marked, key=int) == [str(i) for i in range(1, 1001)]
    assert len(box.calls) == 2
    # One parse and one mark call; no command moves or deletes anything.
    assert "expunge" not in " ".join(box.calls)
    assert "move" not in box.calls[1]


def test_the_next_run_sees_only_unread_mail(root):
    box = Container([])
    assert run(root, box)["rc"] == 0
    assert len(box.calls) == 1


# --------------------------------------------------------------------------- the mail server cannot be read


def test_an_unreadable_mail_server_is_red_naming_the_cause_not_unknown(root):
    box = Container(
        [],
        fail_parse=oh.Result(
            1, "", "doveadm(muhammed): Error: Login refused: IP address rebind refused"
        ),
    )
    out = run(root, box)
    assert out["rc"] == 1
    assert "dmarc.mail.unreadable" in text(out)
    assert "Login refused" in text(out)


def test_an_unreadable_server_reports_mailbox_is_red(root):
    box = Container([], box_error=True)
    out = run(root, box)
    assert out["rc"] == 1
    assert "dmarc.mail.unreadable: muhammed@rediacc.io Server-Reports" in text(out)


def test_a_timed_out_read_is_red(root):
    box = Container([], fail_parse=oh.Result(124, "", "", timed_out=True))
    out = run(root, box)
    assert out["rc"] == 1
    assert "timed out" in text(out)


# --------------------------------------------------------------------------- config and the streamed parser


def test_the_shipped_config_lists_the_server_reports_folder():
    known = dr.load_known(REPO / dr.KNOWN_REL)
    assert {"user": USER, "mailbox": "Server-Reports", "kind": "server-reports"} in known[
        "mailboxes"
    ]
    assert known["server"]["postfix"] == {"max_rejected": 200, "max_deferred": 50, "max_bounced": 5}


def test_a_server_reports_mailbox_without_its_section_is_refused(root):
    path = root / dr.KNOWN_REL
    doc = json.loads(path.read_text())
    del doc["server_reports"]
    path.write_text(json.dumps(doc))
    with pytest.raises(dr.KnownError, match="server_reports"):
        dr.load_known(path)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d["mailboxes"][-1].update(kind="bogus"),
        lambda d: d["server_reports"]["senders"][0].update(shapes=["nope"]),
        lambda d: d["server_reports"]["postfix"].pop("max_bounced"),
        lambda d: d["server_reports"].update(reserved_domains=[], reserved_tlds=[]),
    ],
)
def test_a_malformed_server_reports_config_is_refused(root, mutate):
    path = root / dr.KNOWN_REL
    doc = json.loads(path.read_text())
    mutate(doc)
    path.write_text(json.dumps(doc))
    with pytest.raises(dr.KnownError):
        dr.load_known(path)


def test_the_streamed_parser_classifies_server_mail_under_isolated_mode(tmp_path):
    (tmp_path / "rows.json").write_text(json.dumps(rows(sns_mail(delay("rediacc.com")))))
    doveadm = tmp_path / "bin" / "doveadm"
    doveadm.parent.mkdir()
    doveadm.write_text("#!/bin/sh\ncat %s\n" % (tmp_path / "rows.json"))
    doveadm.chmod(0o755)
    spec = {"mailboxes": [{"user": "u@x", "mailbox": "Server-Reports", "kind": "server-reports"}]}
    arg = base64.b64encode(json.dumps(spec).encode()).decode()
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
    msg = json.loads(line[len(dp.MARKER) :])["mailboxes"][0]["messages"][0]
    assert msg["kind"] == "server-report"
    assert msg["report"]["domains"] == ["rediacc.com"]
    assert "@rediacc.com" not in json.dumps(msg["report"])

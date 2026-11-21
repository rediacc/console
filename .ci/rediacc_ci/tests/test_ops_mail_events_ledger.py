"""The mail-events ledger of the ops-health `dmarc` check: a red SES message on a real domain clears only through a row COMMITTED to git (operator ruling 2026-11-18, "Agent logs, commit clears").

`--log` appends one row per (day, event, type, domain) with hashed ids; the judging run reads the ledger as committed at HEAD, never the working-tree copy. The mail server is the scripted container of test_ops_server_reports; the repository is a temp git repo.
"""

from __future__ import annotations

import datetime
import json
import os
import shutil
import subprocess

import pytest

from rediacc_ci.ops import dmarc_parser as dp
from rediacc_ci.ops import dmarc_reports as dr
from rediacc_ci.tests.test_ops_server_reports import (
    REPO,
    TODAY,
    Container,
    bounce,
    delay,
    rows,
    sns_mail,
)

LEDGER = dr.LEDGER_REL
NOW = datetime.datetime(2026, 11, 18, 9, 30, 0, tzinfo=datetime.UTC)
GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.com",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.com",
}


def git(root, *args):
    subprocess.run(["git", *args], cwd=root, env=GIT_ENV, check=True, capture_output=True)


def with_headers(raw, msg_id, date="Tue, 17 Nov 2026 10:00:00 +0000"):
    """The recorded mail with the headers SNS sets: x-amz-sns-message-id and a Date."""
    head, body = raw.split("\r\n\r\n", 1)
    return f"{head}\r\nX-Amz-Sns-Message-Id: {msg_id}\r\nDate: {date}\r\n\r\n{body}"


def live(domain, msg_id, **kw):
    return with_headers(sns_mail(delay(domain, **kw)), msg_id)


@pytest.fixture
def root(tmp_path):
    (tmp_path / ".ci" / "config").mkdir(parents=True)
    shutil.copy(REPO / dr.KNOWN_REL, tmp_path / dr.KNOWN_REL)
    git(tmp_path, "init", "-q")
    (tmp_path / "seed.txt").write_text("seed\n")
    git(tmp_path, "add", "--", "seed.txt")
    git(tmp_path, "commit", "-q", "-m", "seed")
    return tmp_path


def run(root, container):
    return dr.run(
        root, runner=container, env={"PATH": "/usr/bin"}, resolve=lambda _ip: "", today=TODAY
    )


def log(root, container):
    return dr.log_events(root, runner=container, env={"PATH": "/usr/bin"}, now=NOW)


def ledger_rows(root):
    path = root / LEDGER
    return [json.loads(ln) for ln in path.read_text().splitlines()] if path.is_file() else []


def commit_ledger(root):
    git(root, "add", "--", LEDGER)
    git(root, "commit", "-q", "-m", "ledger", "--", LEDGER)


MAILS = (
    live("live.com", "id-1"),
    live("live.com", "id-2"),
    live("live.com", "id-3", delay_type="RecipientServerError"),
    with_headers(sns_mail(bounce("gmail.com", "Permanent", "General")), "id-4"),
)


def test_log_writes_one_row_per_day_event_type_domain_with_hashed_ids(root):
    out = log(root, Container(rows(*MAILS)))
    assert out["rc"] == 0, out["lines"]
    written = ledger_rows(root)
    assert [(r["date"], r["event"], r["type"], r["domain"], r["count"]) for r in written] == [
        ("2026-11-17", "Bounce", "Permanent/General", "gmail.com", 1),
        ("2026-11-17", "DeliveryDelay", "RecipientServerError", "live.com", 1),
        ("2026-11-17", "DeliveryDelay", "TransientCommunicationFailure", "live.com", 2),
    ]
    assert written[2]["logged_at"] == "2026-11-18T09:30:00Z"
    assert all(len(i) == 16 for r in written for i in r["ids"])
    assert "id-1" not in (root / LEDGER).read_text()
    assert "@" not in (root / LEDGER).read_text()
    assert f"git commit -F <msg-file> -- {LEDGER}" in "\n".join(out["lines"])


def test_the_log_output_carries_no_address(root):
    out = log(root, Container(rows(*MAILS)))
    assert "@" not in "\n".join(out["lines"]).replace("<msg-file>", "")


def test_a_second_log_appends_nothing(root):
    box = Container(rows(*MAILS))
    log(root, box)
    before = (root / LEDGER).read_text()
    out = log(root, box)
    assert out["rc"] == 0
    assert (root / LEDGER).read_text() == before
    assert "no red Server-Reports message outside the ledger" in out["lines"][0]


def test_benign_mail_is_never_logged(root):
    out = log(root, Container(rows(with_headers(sns_mail(delay("example.com")), "id-9"))))
    assert out["rc"] == 0
    assert not (root / LEDGER).exists()


def test_a_missing_ledger_is_empty_and_the_red_stays_red(root):
    box = Container(rows(*MAILS))
    out = run(root, box)
    assert out["rc"] == 1
    assert box.marked == []
    assert "to live.com, 2 message(s)" in "\n".join(out["lines"])
    assert dr.load_ledger(root) == {"committed": set(), "working": set(), "problems": []}


def test_a_red_covered_by_a_head_committed_row_is_marked_seen(root):
    log(root, Container(rows(*MAILS)))
    commit_ledger(root)
    box = Container(rows(*MAILS))
    out = run(root, box)
    assert out["rc"] == 0, "\n".join(out["lines"])
    assert box.marked == ["1", "2", "3", "4"]


def test_a_red_logged_but_not_committed_stays_red(root):
    log(root, Container(rows(*MAILS)))
    box = Container(rows(*MAILS))
    out = run(root, box)
    text = "\n".join(out["lines"])
    assert out["rc"] == 1
    assert box.marked == []
    assert "logged, not committed" in text
    assert (
        "DeliveryDelay TransientCommunicationFailure to live.com (logged, not committed), 2 message(s)"
        in text
    )


def test_the_head_read_control_a_working_copy_read_would_clear_it(root):
    """Control: the working-tree ids ARE in the file, so a judge that read the file instead of HEAD would clear the reds; the verdict stays red only because of the HEAD read."""
    log(root, Container(rows(*MAILS)))
    ids = dr.load_ledger(root)
    assert ids["working"]
    assert not ids["committed"]
    box = Container(rows(*MAILS))
    assert run(root, box)["rc"] == 1
    commit_ledger(root)
    assert dr.load_ledger(root)["committed"] == ids["working"]
    assert run(root, Container(rows(*MAILS)))["rc"] == 0


def test_a_message_outside_the_committed_rows_stays_red(root):
    log(root, Container(rows(*MAILS)))
    commit_ledger(root)
    fresh = live("live.com", "id-new")
    box = Container(rows(MAILS[0], fresh))
    out = run(root, box)
    assert out["rc"] == 1
    assert box.marked == ["1"]


def test_the_parser_hashes_the_sns_message_id_and_reads_the_day():
    one = dp.classify_server(live("live.com", "id-1"))
    assert one["id"] == dp.hashlib.sha256(b"id-1").hexdigest()[:16]
    assert one["date"] == "2026-11-17"
    assert "id-1" not in json.dumps(one)
    assert dp.classify_server(live("live.com", "id-2"))["id"] != one["id"]


def test_the_parser_falls_back_when_the_headers_are_missing():
    bare = dp.classify_server(sns_mail(delay("live.com")))
    assert len(bare["id"]) == 16
    assert bare["date"] == ""


def test_a_git_failure_reading_head_is_red_not_an_empty_ledger(root):
    """Control: a repository without the ledger path reads empty with no problem; a broken HEAD must name the git error."""
    assert dr.load_ledger(root)["problems"] == []
    (root / ".git" / "HEAD").write_text("garbage\n")
    ledger = dr.load_ledger(root)
    assert ledger["committed"] == set()
    assert any("git ls-tree" in p and "HEAD:" + LEDGER in p for p in ledger["problems"])
    out = run(root, Container(rows(*MAILS)))
    assert out["rc"] == 1
    assert any(line.startswith("mail-events.unreadable:") for line in out["lines"])


def test_a_corrupt_ledger_line_is_red_and_the_parsable_rows_still_count(root):
    """Control: with the garbage line removed the same ledger reads clean and clears the reds."""
    log(root, Container(rows(*MAILS)))
    path = root / LEDGER
    good = path.read_text()
    bad = good.count("\n") + 1
    path.write_text(good + "{not json\n")
    commit_ledger(root)
    ledger = dr.load_ledger(root)
    assert ledger["committed"]
    assert ledger["problems"] == [
        "mail-events.unreadable: HEAD:%s line %d is not valid JSON" % (LEDGER, bad),
        "mail-events.unreadable: %s line %d is not valid JSON" % (LEDGER, bad),
    ]
    box = Container(rows(*MAILS))
    out = run(root, box)
    assert out["rc"] == 1
    assert box.marked == ["1", "2", "3", "4"]
    assert any("line %d is not valid JSON" % bad in x for x in out["lines"])
    path.write_text(good)
    commit_ledger(root)
    assert dr.load_ledger(root)["problems"] == []
    assert run(root, Container(rows(*MAILS)))["rc"] == 0


def test_a_non_utf8_ledger_is_a_red_line_with_the_offset_not_a_traceback(root):
    """Control: the same path with valid UTF-8 reads clean."""
    path = root / LEDGER
    path.parent.mkdir(parents=True)
    path.write_bytes(b'{"ids": []}\n')
    assert dr.load_ledger(root)["problems"] == []
    path.write_bytes(b'{"ids": []}\n\xff\xfe\n')
    assert dr.load_ledger(root)["problems"] == [
        "mail-events.unreadable: %s is not UTF-8 (byte offset 12)" % LEDGER
    ]
    commit_ledger(root)
    both = dr.load_ledger(root)["problems"]
    assert "mail-events.unreadable: HEAD:%s is not UTF-8 (byte offset 12)" % LEDGER in both
    out = run(root, Container(rows(*MAILS)))
    assert out["rc"] == 1
    assert any("not UTF-8" in line for line in out["lines"])


def _failing_git(monkeypatch, verb, effect):
    """dr.subprocess.run with one git verb replaced by `effect(argv)`; every other call is the real one."""
    real = subprocess.run

    def fake(argv, *args, **kwargs):
        if len(argv) > 1 and argv[0] == "git" and argv[1] == verb:
            return effect(argv)
        return real(argv, *args, **kwargs)

    monkeypatch.setattr(dr.subprocess, "run", fake)


def test_a_git_show_failure_on_a_committed_ledger_is_red(root, monkeypatch):
    """Control: the same committed ledger reads clean through the real `git show`."""
    log(root, Container(rows(*MAILS)))
    commit_ledger(root)
    assert dr.load_ledger(root)["problems"] == []
    _failing_git(
        monkeypatch,
        "show",
        lambda argv: subprocess.CompletedProcess(argv, 128, stdout=b"", stderr=b"boom"),
    )
    problems = dr.load_ledger(root)["problems"]
    assert any("git show rc=128: boom" in p and "HEAD:" + LEDGER in p for p in problems)


def test_a_git_that_cannot_run_is_red_not_an_empty_ledger(root, monkeypatch):
    def broken(_argv):
        raise OSError("no git here")

    _failing_git(monkeypatch, "ls-tree", broken)
    problems = dr.load_ledger(root)["problems"]
    assert any("git failed: no git here" in p for p in problems)


def test_a_root_without_a_repository_reads_empty_with_no_problem(tmp_path):
    ledger = dr.load_ledger(tmp_path)
    assert ledger["committed"] == set()
    assert ledger["problems"] == []


def test_a_repository_with_no_commits_reads_an_empty_ledger(tmp_path):
    """Finding 0352d15d.4: `ls-tree HEAD` fails on an unborn HEAD, which is an empty ledger and not a red line. Control: a HEAD that is not a ref stays red (see the broken-HEAD case)."""
    git(tmp_path, "init", "-q")
    ledger = dr.load_ledger(tmp_path)
    assert ledger["committed"] == set()
    assert ledger["problems"] == []


def test_a_show_ref_failure_other_than_absent_is_red_not_an_empty_ledger(root, monkeypatch):
    """Finding 0fc324d6.1: only `show-ref` exit 1 means the HEAD branch has no commit; a fatal exit 128 is a red line. Control: the same repository reads clean through the real show-ref."""
    log(root, Container(rows(*MAILS)))
    commit_ledger(root)
    assert dr.load_ledger(root)["problems"] == []
    _failing_git(
        monkeypatch,
        "show-ref",
        lambda argv: subprocess.CompletedProcess(argv, 128, stdout=b"", stderr=b"fatal"),
    )
    problems = dr.load_ledger(root)["problems"]
    assert any("git show-ref rc=128: fatal" in p for p in problems)


def test_a_valid_json_line_that_is_not_a_row_is_red_naming_its_line(root):
    """Finding 0352d15d.3. Control: a row with an ids list reads clean."""
    path = root / LEDGER
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"ids": ["a"]}\n[1]\n{"ids": "abc"}\n')
    problems = dr.load_ledger(root)["problems"]
    assert problems == [
        "mail-events.unreadable: %s line 2 is not a ledger row" % LEDGER,
        "mail-events.unreadable: %s line 3 is not a ledger row" % LEDGER,
    ]
    path.write_text('{"ids": ["a"]}\n')
    assert dr.load_ledger(root)["problems"] == []


def test_log_appends_nothing_while_the_ledger_has_problems(root):
    """Finding 0352d15d.2. Control: with the bad line gone the same log appends its rows."""
    path = root / LEDGER
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json\n")
    before = path.read_bytes()
    out = log(root, Container(rows(*MAILS)))
    assert out["rc"] == 1
    assert out["lines"][-1] == "mail-events: nothing appended until the ledger reads cleanly"
    assert path.read_bytes() == before
    path.unlink()
    assert log(root, Container(rows(*MAILS)))["rc"] == 0
    assert ledger_rows(root)

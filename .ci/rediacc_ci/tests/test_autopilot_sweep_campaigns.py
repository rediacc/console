"""Differential: `rediacc_ci.autopilot.sweep_campaigns` against its twin `.ci/scripts/autopilot/sweep-campaigns.sh`.

NO NETWORK AND NO STUBS, because the twin has none either: the sweeper's whole design is that the decision is made from a PR list and a directory of comment dumps, so it can be exercised offline. Both sides call the REAL `state-comment.sh`, which is the point -- the trust rule (author equality plus exact header prefix) lives there, and a test that stubbed it would prove the port
calls something, not that a lookalike comment is refused.

THE LOOKALIKE IS THE FIXTURE THAT MATTERS. Console is public, so the attack is a comment from any account whose body claims `campaign: open`. Every case below that expects a dispatch is accompanied by one that must NOT dispatch: wrong author, right author with the wrong header, campaign `closed`, campaign absent. A test with only the positive direction would agree with the twin
while the author check was deleted.

RELATIVE PATHS ON PURPOSE. Each side runs with its own private `cwd`, and the warning line quotes the dump path it was given, so the fixtures pass `--comments-dir comments` rather than an absolute path. An absolute path would put two different temp directories into the two sides' stderr and force a masked comparison for no reason.

K=5 LEDGER: `.ci/shadow/w7p6-sweep-campaigns.observations.jsonl`, recorded in a
disposable scratch git repository outside this checkout.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
from typing import Any

from rediacc_ci import paths
from rediacc_ci.autopilot import sweep_campaigns as sc

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "autopilot" / "sweep-campaigns.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "autopilot" / "sweep_campaigns.py"
BASH = shutil.which("bash") or "/bin/bash"

BASE_ENV = {
    "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
    "HOME": os.environ.get("HOME", "/tmp"),
    "LC_ALL": "C",
    "LANG": "C",
    "PYTHONPATH": str(ROOT / ".ci"),
    "PYTHONDONTWRITEBYTECODE": "1",
}

BOT = "rediacc-autopilot[bot]"

# `state-comment.sh`'s HEADER, and a body that does not start with it is not a state comment however well it is worded.
HEADER = "### Autopilot state (machine-maintained, do not edit)"


def body(campaign: str = "open", *, header: str = HEADER) -> str:
    """A rendered state comment carrying one campaign value."""
    return (
        "%s\n"
        "state: fixing | round: 2/8 | head: abc1234 | last_run: 99/1 handled | "
        "campaign: %s | model: opus | rounds_max: 8 | last_sig: none | sig_count: 0\n"
        "\n#### Round ledger\n\n#### Ruled out\n\n#### DECISIONS (post-hoc review)\n"
    ) % (header, campaign)


def comment(cid: int, author: str, text: str) -> dict[str, Any]:
    return {"id": cid, "author": author, "body": text}


def _tree(base: pathlib.Path, prs: Any, dumps: dict[int, Any], *, prs_raw: bytes | None = None):
    (base / "comments").mkdir(parents=True, exist_ok=True)
    (base / "prs.json").write_bytes(
        prs_raw if prs_raw is not None else json.dumps(prs).encode("utf-8")
    )
    for number, payload in dumps.items():
        (base / "comments" / ("%d.json" % number)).write_text(json.dumps(payload), encoding="utf-8")


def _run(subject: pathlib.Path, base: pathlib.Path, argv: list[str]):
    runner = [BASH] if subject.suffix == ".sh" else [sys.executable]
    proc = subprocess.run(
        [*runner, str(subject), *argv],
        capture_output=True,
        env=dict(BASE_ENV),
        check=False,
        cwd=str(base),
        timeout=120,
    )
    return proc.returncode, proc.stdout, proc.stderr


DEFAULT_ARGV = ["--prs", "prs.json", "--comments-dir", "comments", "--bot", BOT]


def _sides(
    name: str,
    prs: Any,
    dumps: dict[int, Any] | None = None,
    argv: list[str] | None = None,
    *,
    prs_raw: bytes | None = None,
):
    results = []
    with tempfile.TemporaryDirectory() as td:
        for subject in (TWIN, PORT):
            base = pathlib.Path(td) / subject.stem
            base.mkdir(parents=True)
            _tree(base, prs, dumps or {}, prs_raw=prs_raw)
            results.append(_run(subject, base, list(argv) if argv is not None else DEFAULT_ARGV))
    old, new = results
    assert new[0] == old[0], "%s: exit diverged: %r vs %r\n twin: %r\n port: %r" % (
        name,
        old[0],
        new[0],
        old[2],
        new[2],
    )
    assert new[1] == old[1], "%s: stdout diverged:\n twin: %r\n port: %r" % (name, old[1], new[1])
    assert new[2] == old[2], "%s: stderr diverged:\n twin: %r\n port: %r" % (name, old[2], new[2])
    return old


def test_open_campaigns_are_swept_and_lookalikes_are_not() -> None:
    """One tree carrying every decision this script can make."""
    dumps = {
        11: [comment(1, BOT, body("open"))],
        12: [comment(2, BOT, body("closed"))],
        13: [comment(3, BOT, body("none"))],
        # A lookalike: perfect body, wrong author.
        14: [comment(4, "mallory", body("open"))],
        # Right author, wrong header: not a state comment.
        15: [comment(5, BOT, body("open", header="### Autopilot state"))],
        # Two comments from the bot; the NEWEST (highest id) wins.
        16: [comment(6, BOT, body("open")), comment(7, BOT, body("closed"))],
        17: [comment(8, BOT, body("closed")), comment(9, BOT, body("open"))],
    }
    exit_code, stdout, stderr = _sides("mixed", [{"number": n} for n in sorted(dumps)], dumps)
    assert exit_code == 0
    assert stdout == b"11\n17\n", stdout
    assert b"7 scanned PR(s)" in stderr
    assert b"2 open campaign(s)" in stderr


def test_output_is_ascending_whatever_the_input_order() -> None:
    dumps = {n: [comment(n, BOT, body("open"))] for n in (3, 21, 7)}
    exit_code, stdout, _ = _sides("unsorted", [{"number": n} for n in (21, 3, 7)], dumps)
    assert exit_code == 0
    assert stdout == b"3\n7\n21\n", "sort -n was not reproduced (this is a numeric sort)"


def test_pr_list_shapes() -> None:
    """The two accepted spellings, plus everything that is silently ignored."""
    dumps = {5: [comment(1, BOT, body("open"))]}
    # A bare [N, ...] list.
    assert _sides("bare-numbers", [5], dumps)[1] == b"5\n"
    # Junk entries: strings, nulls, objects with no number, nested arrays.
    assert _sides("junk", ["x", None, {"title": "t"}, [], 5], dumps)[1] == b"5\n"
    # A top-level object is not an array, so `if type == "array"` yields [].
    assert _sides("object-input", {"number": 5}, dumps)[1] == b""
    # A duplicate is scanned twice by both, so the number is printed twice.
    exit_code, stdout, stderr = _sides("duplicate", [5, 5], dumps)
    assert exit_code == 0
    assert stdout == b"5\n5\n"
    assert b"2 scanned PR(s)" in stderr


def test_a_missing_dump_warns_and_is_not_counted_as_scanned() -> None:
    """ "Could not look" is not "not armed"."""
    dumps = {5: [comment(1, BOT, body("open"))]}
    exit_code, stdout, stderr = _sides("missing-dump", [5, 6], dumps)
    assert exit_code == 0
    assert stdout == b"5\n"
    assert b"no comment dump for PR #6 at comments/6.json" in stderr
    assert b"1 scanned PR(s)" in stderr, "the unreadable PR was counted as scanned"


def test_empty_sweep() -> None:
    """A documented, quiet zero. Named here so the number is visible: this is also what a completely empty input directory produces."""
    exit_code, stdout, stderr = _sides("empty", [])
    assert exit_code == 0
    assert stdout == b""
    assert b"0 open campaign(s) across 0 scanned PR(s)" in stderr


def test_usage_and_missing_inputs() -> None:
    for name, argv in (
        ("no-prs", ["--comments-dir", "comments", "--bot", BOT]),
        ("no-dir", ["--prs", "prs.json", "--bot", BOT]),
        ("no-bot", ["--prs", "prs.json", "--comments-dir", "comments"]),
        ("empty-bot", ["--prs", "prs.json", "--comments-dir", "comments", "--bot="]),
    ):
        code, _, err = _sides(name, [], argv=argv)
        assert code == 2, name
        assert b"usage: sweep-campaigns.sh" in err

    code, _, err = _sides(
        "prs-absent", [], argv=["--prs", "nope.json", "--comments-dir", "comments", "--bot", BOT]
    )
    assert code == 1
    assert b"Required file" in err

    code, _, err = _sides(
        "dir-absent", [], argv=["--prs", "prs.json", "--comments-dir", "nope", "--bot", BOT]
    )
    assert code == 1
    assert b"Required directory" in err


def test_a_malformed_pr_list_fails_with_jqs_own_words() -> None:
    """The parse error IS the observable, which is why the port spawns jq here rather than reproducing the message."""
    code, stdout, err = _sides("malformed-prs", None, prs_raw=b"{not json")
    assert code == 5, "jq's runtime exit code is 5, not 1 or 2"
    assert stdout == b""
    assert err.startswith(b"jq: parse error:"), err


def test_an_unreadable_dump_stops_the_sweep_after_partial_output() -> None:
    """`state-comment.sh select` failing takes the whole sweep down, and the numbers already printed stay printed. Both halves are compared."""
    dumps = {1: [comment(1, BOT, body("open"))], 2: {"not": "an array"}}
    code, stdout, err = _sides("bad-dump", [1, 2], dumps)
    assert code != 0
    assert stdout == b"1\n", "the sweep did not keep the output it had already produced"
    assert b"jq: error" in err, err
    assert b"Cannot index string" in err, err
    assert b"open campaign(s) across" not in err, "the summary was printed after a failure"


def test_pure_helpers_are_exercised_directly() -> None:
    assert sc.sort_numeric(["21", "3", "7"]) == ["3", "7", "21"]
    # The last-resort byte comparison for equal numeric keys.
    assert sc.sort_numeric(["07", "7"]) == ["07", "7"]
    assert sc.jq_raw(None) == "null"
    assert sc.jq_raw(True) == "true"
    assert sc.jq_raw("open") == "open"
    assert sc.jq_raw(7) == "7"
    assert sc.raw_field("", "found") == "", "empty jq input must not raise"
    assert sc.raw_field('{"found":true}', "found") == "true"
    assert sc.raw_field('{"found":false}', "body") == "null", (
        "an absent field renders as jq's `null`, not as Python's None"
    )
    assert sc.script_dir().is_dir()
    assert os.path.isfile(sc.state_comment())

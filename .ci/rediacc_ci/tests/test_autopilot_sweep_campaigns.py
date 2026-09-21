"""`rediacc_ci.autopilot.sweep_campaigns`, driven against the bytes its bash twin produced.

THE TWIN HAS BEEN DELETED. While both copies existed this file ran `.ci/scripts/autopilot/sweep-campaigns.sh` and the port over one fixture tree and compared exit code, stdout and stderr, byte for byte, with no shape-compared arm and no exemption.

The ledger `.ci/shadow/w7p6-sweep-campaigns.observations.jsonl` holds 5 rows of that comparison, recorded in a disposable scratch git repository outside this checkout. Every case now compares against `goldens/sweep-campaigns/`, which holds the twin's OWN recorded bytes, captured on its last day in the tree, and each golden's provenance header carries the blob sha, so `git cat-file
-p <sha>` still yields the program that produced them.

THREE CHANNELS AND NO MORE, because this subject writes nothing that survives it. Its `mktemp -d` work directory holds one `body.txt` handed to the state-comment reader and is removed however the scan ends, so there is no durable artifact to freeze and a section recording an empty tree every time would be decoration. The product is the list of PR numbers on stdout and the counted
summary on stderr.

NO NETWORK AND NO STUBS, because the twin had none either: the sweeper's whole design is that the decision is made from a PR list and a directory of comment dumps, so it can be exercised offline. Both implementations call the REAL state-comment reader, which is the point. The trust rule (author equality plus the exact header prefix) lives there, and a recording made against a
stubbed reader would prove the port calls something, not that a lookalike comment is refused. The twin spawned `state-comment.sh` and the port spawns the sibling port by path.

THE LOOKALIKE IS THE FIXTURE THAT MATTERS. Console is public, so the attack is a comment from any account whose body claims `campaign: open`. The recording that carries a dispatch also carries the cases that must NOT dispatch: wrong author, right author with the wrong header, campaign `closed`, campaign absent. A corpus with only the positive direction would agree with the twin
while the author check was deleted.

RELATIVE PATHS ON PURPOSE. Each case runs in its own private working directory and the warning line quotes the dump path it was given, so every case passes `--comments-dir comments` rather than an absolute path. An absolute path would have put two different temp directories into the two sides' stderr and forced a masked comparison for no reason, and it would now put one into the
goldens.

WHAT IS MASKED is therefore almost nothing, and the two tokens exist only so that a golden cannot quietly acquire a path. The case directory becomes `<case>` and the checkout root becomes `<repo>`; no recording in this corpus contains either, which is the property the relative paths above buy.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.autopilot import sweep_campaigns as sc
from rediacc_ci.tests import frozen

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
PORT = ROOT / ".ci" / "rediacc_ci" / "autopilot" / "sweep_campaigns.py"
SLUG = "sweep-campaigns"

BASH = shutil.which("bash") or "/bin/bash"
PYTHON = sys.executable

BASE_ENV = {
    "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
    "LC_ALL": "C",
    "LANG": "C",
    "PYTHONPATH": str(ROOT / ".ci"),
    "PYTHONDONTWRITEBYTECODE": "1",
}

BOT = "rediacc-autopilot[bot]"

# The state-comment reader's HEADER, and a body that does not start with it is not a state comment however well it is worded.
HEADER = "### Autopilot state (machine-maintained, do not edit)"


def body(campaign: str = "open", *, header: str = HEADER) -> str:
    """A rendered state comment carrying one campaign value."""
    return (
        "%s\n"
        "state: fixing | round: 2/8 | head: abc1234 | last_run: 99/1 handled | "
        "campaign: %s | model: opus | rounds_max: 8 | last_sig: none | sig_count: 0\n"
        "\n#### Round ledger\n\n#### Ruled out\n\n#### DECISIONS (post-hoc review)\n"
    ) % (header, campaign)


def comment(cid: int, author: str, text: str) -> dict[str, typing.Any]:
    return {"id": cid, "author": author, "body": text}


# Every decision this script can make, in one tree: an open campaign, a closed one, one with no campaign value, a lookalike with the wrong author, a right-author comment with the wrong header, and two PRs carrying two bot comments each where the NEWEST must win in both directions.
MIXED = {
    11: [comment(1, BOT, body("open"))],
    12: [comment(2, BOT, body("closed"))],
    13: [comment(3, BOT, body("none"))],
    14: [comment(4, "mallory", body("open"))],
    15: [comment(5, BOT, body("open", header="### Autopilot state"))],
    16: [comment(6, BOT, body("open")), comment(7, BOT, body("closed"))],
    17: [comment(8, BOT, body("closed")), comment(9, BOT, body("open"))],
}

UNSORTED = {n: [comment(n, BOT, body("open"))] for n in (3, 21, 7)}
ONE_OPEN = {5: [comment(1, BOT, body("open"))]}

DEFAULT_ARGV = ["--prs", "prs.json", "--comments-dir", "comments", "--bot", BOT]

# name -> the PR list, the comment dumps, and the argv. `prs_raw` writes the PR list VERBATIM, which is the only way to put bytes jq cannot parse into it.
CASE_KW: dict[str, dict[str, typing.Any]] = {
    "every-decision-in-one-tree": {
        "prs": [{"number": n} for n in sorted(MIXED)],
        "dumps": MIXED,
    },
    "an-unsorted-pr-list": {"prs": [{"number": n} for n in (21, 3, 7)], "dumps": UNSORTED},
    "a-bare-number-list": {"prs": [5], "dumps": ONE_OPEN},
    "junk-entries": {"prs": ["x", None, {"title": "t"}, [], 5], "dumps": ONE_OPEN},
    "a-top-level-object": {"prs": {"number": 5}, "dumps": ONE_OPEN},
    "a-duplicate-pr": {"prs": [5, 5], "dumps": ONE_OPEN},
    "a-missing-comment-dump": {"prs": [5, 6], "dumps": ONE_OPEN},
    "an-empty-sweep": {"prs": []},
    "without-prs": {"prs": [], "argv": ["--comments-dir", "comments", "--bot", BOT]},
    "without-a-comments-dir": {"prs": [], "argv": ["--prs", "prs.json", "--bot", BOT]},
    "without-a-bot": {"prs": [], "argv": ["--prs", "prs.json", "--comments-dir", "comments"]},
    "an-empty-bot": {
        "prs": [],
        "argv": ["--prs", "prs.json", "--comments-dir", "comments", "--bot="],
    },
    "a-prs-file-that-is-absent": {
        "prs": [],
        "argv": ["--prs", "nope.json", "--comments-dir", "comments", "--bot", BOT],
    },
    "a-comments-dir-that-is-absent": {
        "prs": [],
        "argv": ["--prs", "prs.json", "--comments-dir", "nope", "--bot", BOT],
    },
    "a-malformed-pr-list": {"prs": None, "prs_raw": b"{not json"},
    "an-unreadable-comment-dump": {
        "prs": [1, 2],
        "dumps": {1: [comment(1, BOT, body("open"))], 2: {"not": "an array"}},
    },
}

CASES = tuple(CASE_KW)


def fixture(base: pathlib.Path, name: str) -> None:
    """This case's PR list and comment dumps, in a directory of its own."""
    kw = CASE_KW[name]
    (base / "comments").mkdir(parents=True, exist_ok=True)
    raw = kw.get("prs_raw")
    (base / "prs.json").write_bytes(
        raw if raw is not None else json.dumps(kw["prs"]).encode("utf-8")
    )
    for number, payload in (kw.get("dumps") or {}).items():
        (base / "comments" / ("%d.json" % number)).write_text(json.dumps(payload), encoding="utf-8")


def run(subject: pathlib.Path, base: pathlib.Path, name: str) -> tuple[int, str, str]:
    """One subject, once, over this case's own tree."""
    base.mkdir(parents=True, exist_ok=True)
    fixture(base, name)
    env = dict(BASE_ENV)
    env["HOME"] = str(base)
    runner = [BASH] if subject.suffix == ".sh" else [PYTHON]
    proc = subprocess.run(
        [*runner, str(subject), *CASE_KW[name].get("argv", DEFAULT_ARGV)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        cwd=str(base),
        timeout=120,
    )

    def mask(text: str) -> str:
        return text.replace(str(base), "<case>").replace(str(ROOT), "<repo>")

    return proc.returncode, mask(proc.stdout), mask(proc.stderr)


def render(code: int, stdout: str, stderr: str) -> str:
    return frozen.render(code, stdout, stderr)


def recorded(name: str) -> tuple[int, str, str]:
    text = frozen.read(SLUG, name)
    exit_line, rest = text.split("\n", 1)
    stdout, stderr = rest.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)
    return int(exit_line.removeprefix("exit: ")), stdout, stderr


def port(tmp_path: pathlib.Path, name: str) -> tuple[int, str, str]:
    return run(PORT, tmp_path / name, name)


def compare(tmp_path: pathlib.Path, name: str) -> tuple[int, str, str]:
    want = recorded(name)
    got = port(tmp_path, name)
    labels = ("exit code", "stdout", "stderr")
    # `strict=True`: the tuple and the labels must stay the same length, and a silently truncated zip is how a comparison stops checking its last field.
    for label, a, b in zip(labels, want, got, strict=True):
        assert a == b, "%s: %s diverged:\n--- recorded ---\n%s\n--- port ---\n%s" % (
            name,
            label,
            a,
            b,
        )
    return got


@pytest.mark.parametrize("name", CASES)
def test_port_matches_the_twins_recorded_output(tmp_path: pathlib.Path, name: str) -> None:
    compare(tmp_path, name)


def test_every_case_has_a_golden_and_no_golden_is_orphaned() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, set(CASES))


def test_no_recording_carries_an_absolute_path() -> None:
    """The relative-path rule in the module docstring, asserted rather than trusted. A case that started passing an absolute fixture path would put a tempdir into a golden and only fail months later, on a machine whose tempdir is spelled differently."""
    for name in CASES:
        for stream in recorded(name)[1:]:
            assert "<case>" not in stream, name
            assert "<repo>" not in stream, name


# --------------------------------------------------------------------------- What the recordings say ---------------------------------------------------------------------------


def test_open_campaigns_are_swept_and_lookalikes_are_not() -> None:
    """One tree carrying every decision this script can make."""
    code, stdout, stderr = recorded("every-decision-in-one-tree")
    assert code == 0
    assert stdout == "11\n17\n", stdout
    assert "7 scanned PR(s)" in stderr
    assert "2 open campaign(s)" in stderr


def test_output_is_ascending_whatever_the_input_order() -> None:
    code, stdout, _ = recorded("an-unsorted-pr-list")
    assert code == 0
    assert stdout == "3\n7\n21\n", "sort -n was not reproduced (this is a numeric sort)"


def test_pr_list_shapes() -> None:
    """The two accepted spellings, plus everything that is silently ignored."""
    assert recorded("a-bare-number-list")[1] == "5\n"
    # Junk entries: strings, nulls, objects with no number, nested arrays.
    assert recorded("junk-entries")[1] == "5\n"
    # A top-level object is not an array, so `if type == "array"` yields [].
    assert recorded("a-top-level-object")[1] == ""
    # A duplicate is scanned twice, so the number is printed twice.
    code, stdout, stderr = recorded("a-duplicate-pr")
    assert code == 0
    assert stdout == "5\n5\n"
    assert "2 scanned PR(s)" in stderr


def test_a_missing_dump_warns_and_is_not_counted_as_scanned() -> None:
    """ "Could not look" is not "not armed"."""
    code, stdout, stderr = recorded("a-missing-comment-dump")
    assert code == 0
    assert stdout == "5\n"
    assert "no comment dump for PR #6 at comments/6.json" in stderr
    assert "1 scanned PR(s)" in stderr, "the unreadable PR was counted as scanned"


def test_empty_sweep() -> None:
    """A documented, quiet zero. Named here so the number is visible: this is also what a completely empty input directory produces."""
    code, stdout, stderr = recorded("an-empty-sweep")
    assert code == 0
    assert stdout == ""
    assert "0 open campaign(s) across 0 scanned PR(s)" in stderr


def test_usage_and_missing_inputs() -> None:
    for name in ("without-prs", "without-a-comments-dir", "without-a-bot", "an-empty-bot"):
        code, _, stderr = recorded(name)
        assert code == 2, name
        assert "usage: sweep-campaigns.sh" in stderr

    code, _, stderr = recorded("a-prs-file-that-is-absent")
    assert code == 1
    assert "Required file" in stderr

    code, _, stderr = recorded("a-comments-dir-that-is-absent")
    assert code == 1
    assert "Required directory" in stderr


def test_a_malformed_pr_list_fails_with_jqs_own_words() -> None:
    """The parse error IS the observable, which is why the port spawns jq here rather than reproducing the message."""
    code, stdout, stderr = recorded("a-malformed-pr-list")
    assert code == 5, "jq's runtime exit code is 5, not 1 or 2"
    assert stdout == ""
    assert stderr.startswith("jq: parse error:"), stderr


def test_an_unreadable_dump_stops_the_sweep_after_partial_output() -> None:
    """The state-comment reader failing takes the whole sweep down, and the numbers already printed stay printed. Both halves are recorded."""
    code, stdout, stderr = recorded("an-unreadable-comment-dump")
    assert code != 0
    assert stdout == "1\n", "the sweep did not keep the output it had already produced"
    assert "jq: error" in stderr, stderr
    assert "Cannot index string" in stderr, stderr
    assert "open campaign(s) across" not in stderr, "the summary was printed after a failure"


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
    argv = sc.state_comment_argv()
    assert os.path.isfile(argv[-1]), "the spawned sibling is not on disk: %r" % argv
    assert argv[-1].endswith("/state_comment.py"), "the spawn stopped naming the port: %r" % argv
    assert sc.child_env()["PYTHONPATH"].endswith("/.ci"), "the child cannot import rediacc_ci"


# --------------------------------------------------------------------------- The control: these goldens can actually fail ---------------------------------------------------------------------------


# A throwaway entry point that loads the real module, replaces its numeric sort with Python's default string sort, and runs `main`. See the control below for why the plant is a wrapper rather than a copy of the file.
PLANT = """import sys

from rediacc_ci.autopilot import sweep_campaigns as subject

subject.sort_numeric = sorted
raise SystemExit(subject.main(sys.argv[1:]))
"""


def test_a_planted_lexicographic_sort_is_caught(tmp_path: pathlib.Path) -> None:
    """THE CONTROL ON THE GOLDENS, aimed at the one thing a weaker corpus would lose.

    `LC_ALL=C sort -n` is a NUMERIC sort, and Python's default is not: over `21, 3, 7` the twin printed `3 7 21` and a port using plain `sorted` prints `21 3 7`. The set of numbers, the counts on stderr and the exit code are all identical, so a corpus that checked membership rather than bytes would stay green while the sweeper handed its caller a differently ordered list.

    THE PLANT IS A WRAPPER, NOT A COPY OF THE FILE, and that is a property of the subject rather than a convenience. The module resolves both the sibling it spawns and that child's `PYTHONPATH` from its OWN location (`state_comment_argv`, `child_env`), so a copy at any other path spawns a reader that is not there. The wrapper imports the tracked module unmodified and replaces one
    attribute in its own process, so the file on disk is never written to at all.
    """
    original = PORT.read_text(encoding="utf-8")

    mutant = tmp_path / "plant" / "mutant.py"
    mutant.parent.mkdir(parents=True)
    mutant.write_text(PLANT, encoding="utf-8")

    name = "an-unsorted-pr-list"
    want = recorded(name)
    assert want[1] == "3\n7\n21\n", "the recorded corpus moved"
    planted = run(mutant, tmp_path / "planted", name)
    assert planted[1] == "21\n3\n7\n", "the plant did not change the order"
    assert sorted(planted[1].split()) == sorted(want[1].split()), "the plant changed the SET too"
    assert planted[0] == want[0], "the plant was supposed to be invisible in the exit code"
    assert planted[2] == want[2], "the plant was supposed to be invisible on stderr"

    compare(tmp_path / "good", name)
    assert PORT.read_text(encoding="utf-8") == original

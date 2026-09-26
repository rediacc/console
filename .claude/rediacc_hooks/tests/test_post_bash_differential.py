"""The proof for the two ported post-bash hooks: a differential against a frozen golden.

WHY THESE TWO ARE NOT IN `test_guards_differential.py`. That file's subject is a GUARD: a pure function of an event whose whole contract is (rc, stdout, stderr) over a payload. `cancel-old-ci.sh` and `refresh-pr-body.sh` are not guards. They always exit 0, nothing registers them in a chain, and their observable behaviour is a conversation with `git` and `gh` -- which is
exactly why they need a fixture the guard differential has no place for. Their answer depends on what those two programs said, so the comparison has to hold that constant.

THE STUBS ARE THE SEAM. Each case declares a table of `argv -> (rc, stdout, stderr)`; the stub looks its own invocation up and answers from it, so the port is handed the identical bytes a recording session handed it.

THE BODY FILE IS COMPARED, NOT JUST THE CALL. `refresh-pr-body` writes a temp file and hands it to `gh api -F body=@<path>`. The path is a `mktemp` name that differs between runs by construction, so the stub COPIES the file's contents into a per-run recording and the argv is normalised to `body=@<TMP>`. What is compared is the DOCUMENT the hook composed.

WHERE THE RECORDED ANSWER CAME FROM, since PLAN-retire-bash-oracles A3. Until then this file also ran the tracked bash originals at `.claude/oracles/post-bash/` and compared the port against them directly (`test_port_and_twin_agree`). A1 froze those answers into `tests/goldens/post-bash.jsonl`, A2 pointed the comparison at that file, and A3 deleted the oracle tree and the
bash-side test once the golden was proven to match. `test_port_matches_golden` below is the only comparison now.

ANTI-VACUITY. `test_the_cases_are_not_all_silent` refuses a corpus where every case produced the same empty answer, which is what a stub table that stopped being reached would look like. `test_a_planted_defect_is_caught` mutates a COPY of each port -- the trailing space the retired twin's `tr '\\n' ' '` left in the branch list, and the block-stripping awk -- and requires the
comparison against the GOOD port to go red, because a green that has never been shown to be able to go red is not evidence.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import tempfile

import pytest

from rediacc_hooks.tests import goldenio, guardcorpus

ROOT = guardcorpus.repo_root()
PORTS = ROOT / ".claude" / "hooks" / "post-bash"

SUBJECTS = {
    "cancel-old-ci": PORTS / "cancel_old_ci.py",
    "refresh-pr-body": PORTS / "refresh_pr_body.py",
}

# The stub both sides run. It normalises a `body=@<path>` argument to a fixed token and copies that file into the recording, so a `mktemp` name cannot make the two sides differ for a reason that is not about either of them.
STUB = r"""#!/usr/bin/env python3
import json, os, pathlib, sys

name = pathlib.Path(sys.argv[0]).name
argv = []
for arg in sys.argv[1:]:
    if arg.startswith("body=@"):
        body = pathlib.Path(arg[len("body=@") :])
        rec = pathlib.Path(os.environ["STUB_RECORD"])
        rec.write_text(body.read_text(encoding="utf-8") if body.is_file() else "<missing>", encoding="utf-8")
        arg = "body=@<TMP>"
    argv.append(arg)
key = "\x1f".join([name, *argv])
table = json.loads(pathlib.Path(os.environ["STUB_TABLE"]).read_text(encoding="utf-8"))
answer = table.get(key, table.get(name + "\x1f<default>", {}))
with open(os.environ["STUB_CALLS"], "a", encoding="utf-8") as handle:
    handle.write(key.replace("\x1f", " ") + "\n")
sys.stdout.write(answer.get("out", ""))
sys.stderr.write(answer.get("err", ""))
sys.exit(answer.get("rc", 0))
"""


def _key(*argv):
    return "\x1f".join(argv)


def _default(name):
    return _key(name, "<default>")


# ---------------------------------------------------------------------------
# The tables. Each case is (subject, label, payload, stub table, extra env).
# ---------------------------------------------------------------------------

BRANCH = "0914-1"
TIP = "a" * 40


def _git(branch=BRANCH, tip=TIP, log="- `abc123def` a subject", short="abc123def"):
    table = {
        _default("git"): {"rc": 0},
        _key("git", "-C", "<ROOT>", "rev-parse", "--abbrev-ref", "HEAD"): {"out": branch + "\n"},
        _key("git", "-C", "<ROOT>", "rev-parse", "origin/" + BRANCH): {"out": tip + "\n"},
        _key("git", "-C", "<ROOT>", "rev-parse", "--short=9", "origin/" + BRANCH): {
            "out": short + "\n"
        },
        _key("git", "-C", "<ROOT>", "log", "-5", "--format=- `%h` %s", "origin/" + BRANCH): {
            "out": log + "\n"
        },
    }
    if branch == "":
        table[_key("git", "-C", "<ROOT>", "rev-parse", "--abbrev-ref", "HEAD")] = {"rc": 128}
    return table


def _runs_query(tip=TIP, branch=BRANCH):
    return _key(
        "gh",
        "run",
        "list",
        "--repo",
        "rediacc/console",
        "--branch",
        branch,
        "--json",
        "databaseId,status,headSha",
        "--jq",
        '.[] | select(.status == "in_progress" or .status == "queued") '
        '| select(.headSha != "%s") | .databaseId' % tip,
    )


def _pr_list(repo="rediacc/console", branch=BRANCH):
    return _key(
        "gh",
        "pr",
        "list",
        "--repo",
        repo,
        "--head",
        branch,
        "--state",
        "open",
        "--json",
        "number",
        "--jq",
        ".[0].number",
    )


REPO_VIEW = _key("gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner")

BODY_WITH_BLOCK = (
    "Some description.\n"
    "\n"
    "<!-- pushed-head:begin -->\n"
    "**Last pushed:** `oldoldold`\n"
    "\n"
    "- `000000000` an older subject\n"
    "<!-- pushed-head:end -->"
)

CASES: list[tuple[str, str, dict, dict]] = [
    (
        "cancel-old-ci",
        "no push in the command",
        {"tool_input": {"command": "ls -la"}},
        _git(),
    ),
    (
        "cancel-old-ci",
        "an absent command key is scanned as the word null",
        {"tool_input": {}},
        _git(),
    ),
    (
        "cancel-old-ci",
        "on main the hook stands down",
        {"tool_input": {"command": "git push"}},
        _git(branch="main"),
    ),
    (
        "cancel-old-ci",
        "a detached head is not a branch",
        {"tool_input": {"command": "git push"}},
        _git(branch="HEAD"),
    ),
    (
        "cancel-old-ci",
        "rev-parse failing leaves no branch to query",
        {"tool_input": {"command": "git push"}},
        _git(branch=""),
    ),
    (
        "cancel-old-ci",
        "nothing superseded, so only the description advisory",
        {"tool_input": {"command": "git push origin " + BRANCH}},
        dict(_git(), **{_default("gh"): {"rc": 0}, _runs_query(): {"out": ""}}),
    ),
    (
        "cancel-old-ci",
        "two superseded runs are force-cancelled",
        {"tool_input": {"command": "git push origin " + BRANCH}},
        dict(
            _git(),
            **{
                _default("gh"): {"rc": 0},
                _runs_query(): {"out": "111\n222\n"},
                _key(
                    "gh", "api", "repos/rediacc/console/actions/runs/111/force-cancel", "-X", "POST"
                ): {"out": '{"cancelled":111}\n'},
                _key(
                    "gh", "api", "repos/rediacc/console/actions/runs/222/force-cancel", "-X", "POST"
                ): {"out": '{"cancelled":222}\n'},
            },
        ),
    ),
    (
        "cancel-old-ci",
        "a force-cancel that fails is not counted",
        {"tool_input": {"command": "git push origin " + BRANCH}},
        dict(
            _git(),
            **{
                _default("gh"): {"rc": 0},
                _runs_query(): {"out": "111\n"},
                _key(
                    "gh", "api", "repos/rediacc/console/actions/runs/111/force-cancel", "-X", "POST"
                ): {"rc": 1, "err": "boom\n"},
            },
        ),
    ),
    (
        "cancel-old-ci",
        "an explicit refspec adds its destination branch",
        {"tool_input": {"command": "git push origin %s && git push origin HEAD:0728-2" % BRANCH}},
        dict(_git(), **{_default("gh"): {"rc": 0}}),
    ),
    (
        "cancel-old-ci",
        "flags and the remote name are not branches",
        {"tool_input": {"command": "git push --force-with-lease origin main"}},
        dict(_git(), **{_default("gh"): {"rc": 0}}),
    ),
    (
        "refresh-pr-body",
        "no push in the command",
        {"tool_input": {"command": "ls -la"}},
        _git(),
    ),
    (
        "refresh-pr-body",
        "git pushed is not git push",
        {"tool_input": {"command": "echo git pushed"}},
        _git(),
    ),
    (
        "refresh-pr-body",
        "a dry run describes nothing",
        {"tool_input": {"command": "git push --dry-run origin " + BRANCH}},
        _git(),
    ),
    (
        "refresh-pr-body",
        "no repo name means no REST call to make",
        {"tool_input": {"command": "git push"}},
        dict(_git(), **{_default("gh"): {"rc": 0}, REPO_VIEW: {"out": ""}}),
    ),
    (
        "refresh-pr-body",
        "no open PR for the branch",
        {"tool_input": {"command": "git push"}},
        dict(
            _git(),
            **{
                _default("gh"): {"rc": 0},
                REPO_VIEW: {"out": "rediacc/console\n"},
                _pr_list(): {"out": "null\n"},
            },
        ),
    ),
    (
        "refresh-pr-body",
        "the block is replaced and the PATCH succeeds",
        {"tool_input": {"command": "git push"}},
        dict(
            _git(),
            **{
                _default("gh"): {"rc": 0},
                REPO_VIEW: {"out": "rediacc/console\n"},
                _pr_list(): {"out": "543\n"},
                _key("gh", "pr", "view", "543", "--json", "body", "--jq", ".body"): {
                    "out": BODY_WITH_BLOCK + "\n"
                },
                _key(
                    "gh",
                    "api",
                    "repos/rediacc/console/pulls/543",
                    "-X",
                    "PATCH",
                    "-F",
                    "body=@<TMP>",
                ): {"out": '{"ok":true}\n'},
            },
        ),
    ),
    (
        "refresh-pr-body",
        "a failing PATCH is reported on stderr",
        {"tool_input": {"command": "git push"}},
        dict(
            _git(),
            **{
                _default("gh"): {"rc": 0},
                REPO_VIEW: {"out": "rediacc/console\n"},
                _pr_list(): {"out": "543\n"},
                _key("gh", "pr", "view", "543", "--json", "body", "--jq", ".body"): {
                    "out": "A body with no block at all\n"
                },
                _key(
                    "gh",
                    "api",
                    "repos/rediacc/console/pulls/543",
                    "-X",
                    "PATCH",
                    "-F",
                    "body=@<TMP>",
                ): {"rc": 1},
            },
        ),
    ),
    (
        "refresh-pr-body",
        "an empty commit log leaves the body alone",
        {"tool_input": {"command": "git push"}},
        dict(
            _git(log=""),
            **{
                _default("gh"): {"rc": 0},
                REPO_VIEW: {"out": "rediacc/console\n"},
                _pr_list(): {"out": "543\n"},
            },
        ),
    ),
]


def _world(base: pathlib.Path, table: dict, *, with_gh: bool = True) -> tuple[dict, pathlib.Path]:
    """One run's stub PATH, project directory, table file and recording paths."""
    root = base / "repo"
    root.mkdir()
    stubs = base / "stubs"
    stubs.mkdir()
    resolved = {k.replace("<ROOT>", str(root)): v for k, v in table.items()}
    table_file = base / "table.json"
    table_file.write_text(json.dumps(resolved), encoding="utf-8")
    for name in ("git", "gh") if with_gh else ("git",):
        path = stubs / name
        path.write_text(STUB, encoding="utf-8")
        path.chmod(0o755)
    env = {
        "PATH": "%s:%s" % (stubs, os.environ.get("PATH", "/usr/bin:/bin")),
        "CLAUDE_PROJECT_DIR": str(root),
        "STUB_TABLE": str(table_file),
        "STUB_RECORD": str(base / "record.txt"),
        "STUB_CALLS": str(base / "calls.txt"),
        "HOME": str(base),
        "TMPDIR": str(base),
        "LC_ALL": "C",
        "LANG": "C",
        "TZ": "UTC",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    return env, base


def _run(argv, payload, env, cwd) -> tuple[int, bytes, bytes]:
    proc = subprocess.run(
        argv,
        input=payload.encode("utf-8"),
        capture_output=True,
        check=False,
        env=env,
        cwd=str(cwd),
        timeout=120,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _answer(subject, payload, table, base, *, port_path=None, with_gh=True):
    port = SUBJECTS[subject]
    env, work = _world(base, table, with_gh=with_gh)
    argv = ["python3", str(port_path or port)]
    rc, out, err = _run(argv, payload, env, work)
    record = base / "record.txt"
    calls = base / "calls.txt"
    return {
        "rc": rc,
        "out": out.replace(str(work).encode(), b"<work>"),
        "err": err.replace(str(work).encode(), b"<work>"),
        "body": record.read_text(encoding="utf-8") if record.is_file() else None,
        "calls": calls.read_text(encoding="utf-8").replace(str(work), "<work>")
        if calls.is_file()
        else "",
    }


# --------------------------------------------------------------------------- The golden mode (PLAN-retire-bash-oracles A2) ---------------------------------------------------------------------------
#
# AGAINST A FROZEN RECORD. Until PLAN-retire-bash-oracles A3, `test_port_and_twin_agree` ran the real oracle here and compared it against the port on every call; A1 froze that oracle's answers into `goldens/post-bash.jsonl`, A2 pointed this section at that file, and A3 deleted the oracle-running test once the golden was proven to match.

GOLDEN_PATH = goldenio.golden_path("post-bash")


def golden_key(subject, label, payload_doc, table):
    return goldenio.case_key(
        "%s:%s" % (subject, label),
        json.dumps(payload_doc, sort_keys=True),
        json.dumps(table, sort_keys=True),
    )


def _encode_answer(answer):
    """`_answer`'s dict, JSON-safe: bytes decoded with the same `surrogateescape` this whole suite uses, then made UTF-8-clean field by field."""
    return {
        "rc": answer["rc"],
        "out": goldenio.encode_field(answer["out"].decode("utf-8", "surrogateescape")),
        "err": goldenio.encode_field(answer["err"].decode("utf-8", "surrogateescape")),
        "body": None if answer["body"] is None else goldenio.encode_field(answer["body"]),
        "calls": goldenio.encode_field(answer["calls"]),
    }


def _decode_answer(record):
    return {
        "rc": record["rc"],
        "out": goldenio.decode_field(record["out"]).encode("utf-8", "surrogateescape"),
        "err": goldenio.decode_field(record["err"]).encode("utf-8", "surrogateescape"),
        "body": None if record["body"] is None else goldenio.decode_field(record["body"]),
        "calls": goldenio.decode_field(record["calls"]),
    }


@pytest.mark.parametrize(
    ("subject", "label", "payload_doc", "table"),
    CASES,
    ids=["%s: %s" % (c[0], c[1]) for c in CASES],
)
def test_port_matches_golden(subject, label, payload_doc, table):
    _header, silent, records = goldenio.read_golden(GOLDEN_PATH)
    key = golden_key(subject, label, payload_doc, table)
    want = goldenio.lookup(silent, records, key)
    assert want is not None, (
        "no golden record for %s / %s (key %s) -- run regolden.py post-bash --reason '<why>'"
        % (subject, label, key)
    )
    payload = json.dumps(payload_doc)
    with tempfile.TemporaryDirectory() as td:
        new = _answer(subject, payload, table, pathlib.Path(td))
    assert new == _decode_answer(want), (
        "%s / %s diverged from the golden:\n--- golden ---\n%r\n--- port ---\n%r"
        % (subject, label, want, new)
    )


def test_post_bash_golden_exists():
    assert GOLDEN_PATH.is_file(), (
        "%s is missing -- run regolden.py post-bash --reason '<why>' to freeze it" % GOLDEN_PATH
    )


def test_a_missing_gh_stands_the_refresh_hook_down():
    """`command -v gh || exit 0`, driven with `gh` absent from PATH."""
    payload = json.dumps({"tool_input": {"command": "git push"}})
    with tempfile.TemporaryDirectory() as td:
        answer = _answer("refresh-pr-body", payload, _git(), pathlib.Path(td), with_gh=False)
    assert answer["rc"] == 0


def test_the_cases_are_not_all_silent():
    """ANTI-VACUITY: a table nothing reaches would make every comparison above compare two empty answers."""
    seen = set()
    bodies = 0
    for subject, _label, payload_doc, table in CASES:
        payload = json.dumps(payload_doc)
        with tempfile.TemporaryDirectory() as td:
            answer = _answer(subject, payload, table, pathlib.Path(td))
        seen.add((answer["rc"], answer["out"], answer["err"]))
        if answer["body"] is not None:
            bodies += 1
    assert len(seen) >= 5, "the corpus produced only %d distinct answers" % len(seen)
    assert bodies >= 1, "no case ever composed a PR body, so the document is never compared"


PLANTS = {
    # The trailing space `tr '\n' ' '` leaves in the branch list, which the advisory prints verbatim.
    "cancel-old-ci": ('"".join(b + " " for b in branches)', '" ".join(branches)'),
    # The block-stripping awk: dropping the END arm leaves everything after the marker deleted.
    "refresh-pr-body": ("        if line == END:\n            skip = False\n", ""),
}


@pytest.mark.parametrize("subject", sorted(PLANTS))
def test_a_planted_defect_is_caught(subject):
    """A green that has never been shown to be able to go red is not evidence."""
    port = SUBJECTS[subject]
    source = port.read_text(encoding="utf-8")
    old_text, new_text = PLANTS[subject]
    assert old_text in source, "%s: the plant's anchor moved: %r" % (subject, old_text)
    broken_src = source.replace(old_text, new_text)
    assert broken_src != source

    with tempfile.TemporaryDirectory() as td:
        broken = pathlib.Path(td) / ("broken_%s.py" % port.stem)
        broken.write_text(broken_src, encoding="utf-8")
        fired = False
        for case_subject, _label, payload_doc, table in CASES:
            if case_subject != subject:
                continue
            payload = json.dumps(payload_doc)
            with tempfile.TemporaryDirectory() as good_td:
                good = _answer(case_subject, payload, table, pathlib.Path(good_td))
            with tempfile.TemporaryDirectory() as bad_td:
                bad = _answer(case_subject, payload, table, pathlib.Path(bad_td), port_path=broken)
            if bad != good:
                fired = True
                break
    assert fired, "PLANT DID NOT FIRE for %s: this differential cannot see the defect" % subject
    assert port.read_text(encoding="utf-8") == source


def test_python3_is_available():
    """The control on the harness itself: the port side may not be skipped into a green."""
    assert shutil.which("python3"), "python3 is missing, so the port never ran"

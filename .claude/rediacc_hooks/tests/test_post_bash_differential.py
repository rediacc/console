"""The proof for the two ported post-bash hooks: a differential against their bash twins.

WHY THESE TWO ARE NOT IN `test_guards_differential.py`. That file's subject is a GUARD: a pure function of an event whose whole contract is (rc, stdout, stderr) over a payload. `cancel-old-ci.sh` and `refresh-pr-body.sh` are not guards. They always exit 0, nothing registers them in a chain, and their observable behaviour is a conversation with `git` and `gh` -- which is
exactly why they need a fixture the guard differential has no place for. Their answer depends on what those two programs said, so the comparison has to hold that constant on both sides.

THE STUBS ARE THE SEAM, and they are ONE pair of programs shared by both sides. A stub per side would prove that two transcriptions agree. Each case declares a table of `argv -> (rc, stdout, stderr)`; the stub looks its own invocation up and answers from it, so the bash and the port are handed identical bytes in identical order.

THE BODY FILE IS COMPARED, NOT JUST THE CALL. `refresh-pr-body` writes a temp file and hands it to `gh api -F body=@<path>`. The path is a `mktemp` name and differs between the two runs by construction, so the stub COPIES the file's contents into a per-run recording and the argv is normalised to `body=@<TMP>`. What is compared is the DOCUMENT the hook composed, which is
the thing the twin's awk-and-printf block exists to produce.

THE ORACLES ARE THE REAL TRACKED FILES at `.claude/oracles/post-bash/`, never a copy made here: a differential against a transcription proves the transcription. They are read-only in this suite.

ANTI-VACUITY. `test_the_cases_are_not_all_silent` refuses a corpus where every case produced the same empty answer, which is what a stub table that stopped being reached would look like. `test_a_planted_defect_is_caught` mutates a COPY of each port -- the trailing space the twin's `tr '\\n' ' '` leaves in the branch list, and the block-stripping awk -- and requires the
comparison to go red, because a green that has never been shown to be able to go red is not evidence.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import tempfile

import pytest

from rediacc_hooks.tests import guardcorpus

ROOT = guardcorpus.repo_root()
ORACLES = ROOT / ".claude" / "oracles" / "post-bash"
PORTS = ROOT / ".claude" / "hooks" / "post-bash"

SUBJECTS = {
    "cancel-old-ci": (ORACLES / "cancel-old-ci.sh", PORTS / "cancel_old_ci.py"),
    "refresh-pr-body": (ORACLES / "refresh-pr-body.sh", PORTS / "refresh_pr_body.py"),
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


def _answer(subject, payload, table, base, *, which, port_path=None, with_gh=True):
    twin, port = SUBJECTS[subject]
    env, work = _world(base, table, with_gh=with_gh)
    argv = ["bash", str(twin)] if which == "old" else ["python3", str(port_path or port)]
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


def _both(subject, payload_doc, table, *, with_gh=True, port_path=None):
    payload = json.dumps(payload_doc)
    with tempfile.TemporaryDirectory() as td:
        old_base = pathlib.Path(td) / "old"
        new_base = pathlib.Path(td) / "new"
        old_base.mkdir()
        new_base.mkdir()
        old = _answer(subject, payload, table, old_base, which="old", with_gh=with_gh)
        new = _answer(
            subject, payload, table, new_base, which="new", with_gh=with_gh, port_path=port_path
        )
    return old, new


@pytest.mark.parametrize(
    ("subject", "label", "payload_doc", "table"),
    CASES,
    ids=["%s: %s" % (c[0], c[1]) for c in CASES],
)
def test_port_and_twin_agree(subject, label, payload_doc, table):
    old, new = _both(subject, payload_doc, table)
    assert new == old, "%s / %s diverged:\n--- twin ---\n%r\n--- port ---\n%r" % (
        subject,
        label,
        old,
        new,
    )


def test_a_missing_gh_stands_the_refresh_hook_down():
    """`command -v gh || exit 0`, driven with `gh` absent from PATH on both sides."""
    old, new = _both(
        "refresh-pr-body", {"tool_input": {"command": "git push"}}, _git(), with_gh=False
    )
    assert old["rc"] == 0
    assert new == old


def test_the_cases_are_not_all_silent():
    """ANTI-VACUITY: a table nothing reaches would make every comparison above compare two empty answers."""
    seen = set()
    bodies = 0
    for subject, _label, payload_doc, table in CASES:
        _old, new = _both(subject, payload_doc, table)
        seen.add((new["rc"], new["out"], new["err"]))
        if new["body"] is not None:
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
    _twin, port = SUBJECTS[subject]
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
            good_old, good_new = _both(case_subject, payload_doc, table)
            assert good_new == good_old
            _old, bad = _both(case_subject, payload_doc, table, port_path=broken)
            if bad != good_old:
                fired = True
                break
    assert fired, "PLANT DID NOT FIRE for %s: this differential cannot see the defect" % subject
    assert port.read_text(encoding="utf-8") == source


def test_the_oracles_are_the_tracked_files():
    """The bash side must be the real tracked original, not a copy this suite made."""
    for subject, (twin, port) in SUBJECTS.items():
        assert twin.is_file(), "%s: the oracle is gone: %s" % (subject, twin)
        assert port.is_file(), "%s: the port is gone: %s" % (subject, port)
        tracked = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "--error-unmatch", str(twin.relative_to(ROOT))],
            capture_output=True,
            check=False,
        )
        assert tracked.returncode == 0, "%s is not tracked, so it is not an oracle" % twin


def test_python3_and_bash_are_both_available():
    """The control on the harness itself: neither side may be skipped into a green."""
    assert shutil.which("bash"), "bash is missing, so the twin side never ran"
    assert shutil.which("python3"), "python3 is missing, so the port side never ran"

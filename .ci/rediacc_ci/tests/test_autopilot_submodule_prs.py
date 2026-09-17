"""Differential: `rediacc_ci.autopilot.submodule_prs` against its twin `.ci/scripts/autopilot/submodule-prs.sh`.

THE FAKE `gh` IS A SAFETY CONTROL, NOT A CONVENIENCE, and this subject is the one in the wave where that sentence is literal: its success path is `gh pr create`, which OPENS A PULL REQUEST, and `gh pr edit --body-file`, which REPLACES a pull request's body. GitHub restores neither. `--repo` comes straight off the command line. So a case that reached the real binary would open real
PRs in whatever repository the fixture named and overwrite a real body with a fixture. Four things stop that, and the first is asserted rather than assumed:

  1. the stub directory is FIRST on PATH, and `test_the_fake_gh_is_the_gh`
     resolves `gh` through that PATH and fails if anything else wins;
  2. every fixture names `acme/...`, which does not exist;
  3. `GH_TOKEN` is a fixture string and `GH_CONFIG_DIR` points into the temp
     tree, so a leaked real `gh` fails auth rather than writing;
  4. the fake RECORDS every argv, so a case that somehow produced no call log
     would fail rather than pass quietly.

THE CALL LOG AND THE BODY FILES ARE THE ARTIFACT. Everything this script does is a `gh` call: which repository, which head branch, what title, and -- the part that matters most -- the exact body bytes it would put on the console PR. Both sides' `--body-file` arguments point into their own `mktemp -d`, so the fake normalises the path to `<work>/<name>` and copies the CONTENT out for
comparison. A port that logged the right sentences and posted the wrong body would sail through a stdout-only comparison.

TWO PRESERVED DEFECTS ARE PINNED BY NAME:
`test_an_unterminated_block_swallows_the_rest` (a BEGIN marker with no END makes the rebuild drop everything after it, losing operator text) and `test_a_dry_run_rebuilds_onto_an_empty_body` (a dry run never reads the live body, so what it prints is not what the round would post). Both are defect reports in test form; if either twin behaviour is repaired, the test goes red and the
repair gets noticed here.

K=5 LEDGER: `.ci/shadow/w7p6-submodule-prs.observations.jsonl`, recorded in a
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
from rediacc_ci.autopilot import submodule_prs as sp

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "autopilot" / "submodule-prs.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "autopilot" / "submodule_prs.py"
BASH = shutil.which("bash") or "/bin/bash"

FAKE_GH = '''#!/usr/bin/python3
"""A recording fake `gh`. Every write verb is answered, none is performed."""
import json
import os
import shutil
import sys

argv = sys.argv[1:]


def flag(name, default=""):
    return argv[argv.index(name) + 1] if name in argv else default


logged = []
skip_next = False
for i, arg in enumerate(argv):
    if skip_next:
        # The value of --body-file was already logged in normalised form.
        skip_next = False
        continue
    if arg == "--body-file":
        path = argv[i + 1]
        name = os.path.basename(path)
        shutil.copyfile(path, os.path.join(os.environ["FAKE_GH_BODIES"], name))
        logged += ["--body-file", "<work>/" + name]
        skip_next = True
        continue
    logged.append(arg)

with open(os.environ["FAKE_GH_LOG"], "a") as fh:
    fh.write("\\t".join(logged) + "\\n")

verb = " ".join(argv[:2])
if verb == os.environ.get("FAKE_GH_FAIL", ""):
    sys.stderr.write("gh: fake %s failure\\n" % verb)
    sys.exit(1)

if verb == "pr list":
    existing = json.loads(os.environ.get("FAKE_GH_EXISTING", "{}"))
    url = existing.get(flag("--repo"), "")
    if url:
        sys.stdout.write(url + "\\n")
    sys.exit(0)

if verb == "pr create":
    sys.stdout.write(
        "https://github.com/%s/pull/%s\\n"
        % (flag("--repo"), os.environ.get("FAKE_GH_NEW_PR", "77"))
    )
    sys.exit(0)

if verb == "pr view":
    with open(os.environ["FAKE_GH_CONSOLE_BODY"]) as fh:
        sys.stdout.write(fh.read())
    sys.exit(0)

if verb == "pr edit":
    sys.exit(0)

sys.stderr.write("fake gh: unhandled verb %r\\n" % verb)
sys.exit(9)
'''

REPO = "acme/widget"
PR = "31"
BRANCH = "0906-1"

BASE_ARGV = ["--verdict", "verdict.json", "--repo", REPO, "--pr", PR, "--branch", BRANCH]


def _stub_bin(base: pathlib.Path) -> str:
    """The fake `gh` first on PATH. See `test_the_fake_gh_is_the_gh`."""
    stub = base / "bin"
    stub.mkdir(exist_ok=True)
    fake = stub / "gh"
    fake.write_text(FAKE_GH, encoding="utf-8")
    fake.chmod(0o755)
    return "%s:%s" % (stub, os.environ.get("PATH", "/usr/bin:/bin"))


def _run(subject: pathlib.Path, base: pathlib.Path, argv: list[str], env_extra: dict[str, str]):
    call_log = base / "gh-calls.log"
    call_log.write_text("", encoding="utf-8")
    bodies = base / "gh-bodies"
    bodies.mkdir(exist_ok=True)
    console_body = base / "console-body.txt"
    if not console_body.exists():
        console_body.write_text("", encoding="utf-8")
    env = {
        "PATH": _stub_bin(base),
        "HOME": str(base),
        "LC_ALL": "C",
        "LANG": "C",
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "FAKE_GH_LOG": str(call_log),
        "FAKE_GH_BODIES": str(bodies),
        "FAKE_GH_CONSOLE_BODY": str(console_body),
        "GH_TOKEN": "not-a-real-token",
        "GH_CONFIG_DIR": str(base / "gh-config"),
    }
    env.update(env_extra)
    runner = [BASH] if subject.suffix == ".sh" else [sys.executable]
    proc = subprocess.run(
        [*runner, str(subject), *argv],
        capture_output=True,
        env=env,
        check=False,
        cwd=str(base),
        timeout=120,
    )
    calls = [line for line in call_log.read_text(encoding="utf-8").splitlines() if line]
    written = {p.name: p.read_bytes() for p in sorted(bodies.iterdir())}
    return proc.returncode, proc.stdout, proc.stderr, calls, written


def verdict_json(*submodules: dict[str, Any]) -> bytes:
    return json.dumps({"submodules": list(submodules)}).encode("utf-8")


def sub(path: str, message: str = "fix(renet): the thing") -> dict[str, Any]:
    return {"path": path, "message": message}


def _sides(
    name: str,
    argv: list[str] | None = None,
    *,
    verdict: bytes | None = None,
    console_body: str | None = None,
    env: dict[str, str] | None = None,
    exact_stderr: bool = True,
):
    argv = list(argv) if argv is not None else list(BASE_ARGV)
    env_extra = {"AUTOPILOT_ALLOW_PUSH": "true"}
    env_extra.update(env or {})
    results = []
    with tempfile.TemporaryDirectory() as td:
        for subject in (TWIN, PORT):
            base = pathlib.Path(td) / subject.stem
            base.mkdir(parents=True)
            if verdict is not None:
                (base / "verdict.json").write_bytes(verdict)
            if console_body is not None:
                (base / "console-body.txt").write_text(console_body, encoding="utf-8")
            results.append(_run(subject, base, argv, env_extra))
    old, new = results
    labels = ("exit", "stdout", "stderr", "gh calls", "gh body files")
    for i, label in enumerate(labels):
        if label == "stderr" and not exact_stderr:
            continue
        assert new[i] == old[i], "%s: %s diverged:\n twin: %r\n port: %r" % (
            name,
            label,
            old[i],
            new[i],
        )
    return old


def test_no_submodules_is_a_quiet_zero() -> None:
    """ "The round named no submodules" exits 0 and touches nothing."""
    exit_code, _, stderr, calls, _ = _sides("none", verdict=verdict_json())
    assert exit_code == 0
    assert calls == []
    assert b"the round named no submodules; nothing to open or link" in stderr
    # And it exits 0 even with the stage flag OFF, because nothing would be written either way. That ordering is the twin's, and it is deliberate.
    exit_code, _, _, calls, _ = _sides(
        "none-flag-off", verdict=verdict_json(), env={"AUTOPILOT_ALLOW_PUSH": ""}
    )
    assert exit_code == 0
    assert calls == []


def test_a_new_submodule_pr_is_opened_and_linked() -> None:
    """The full path: look, create, read the console body, write it back."""
    exit_code, _, stderr, calls, bodies = _sides(
        "create", verdict=verdict_json(sub("private/renet")), console_body="Existing body."
    )
    assert exit_code == 0
    assert calls[0].startswith("pr\tlist\t--repo\tacme/renet\t--head\t0906-1\t--state\topen")
    assert calls[1] == (
        "pr\tcreate\t--repo\tacme/renet\t--head\t0906-1\t--base\tmain\t--title\t"
        "fix(renet): the thing\t--body-file\t<work>/body.txt"
    ), calls[1]
    assert calls[2] == 'pr\tview\t31\t--repo\tacme/widget\t--json\tbody\t--jq\t.body // ""'
    assert calls[3] == "pr\tedit\t31\t--repo\tacme/widget\t--body-file\t<work>/body-new.md"
    assert bodies["body.txt"] == (
        b"Submodule change for acme/widget#31.\n\nOpened by the autopilot harness "
        b"alongside the console PR; review there.\n"
    )
    assert bodies["body-new.md"] == (
        b"Existing body.\n"
        b"\n<!-- autopilot-submodule-prs:begin -->\n"
        b"**Submodule PRs**\n\n"
        b"- `private/renet` -> https://github.com/acme/renet/pull/77\n"
        b"<!-- autopilot-submodule-prs:end -->\n"
    ), bodies["body-new.md"]
    assert b"opened acme/renet PR for branch 0906-1" in stderr
    assert b"linked 1 submodule PR(s)" in stderr


def test_an_existing_pr_is_reused() -> None:
    """Idempotence half 1: a second round on the same branch opens nothing."""
    exit_code, _, stderr, calls, bodies = _sides(
        "reuse",
        verdict=verdict_json(sub("private/renet")),
        env={
            "FAKE_GH_EXISTING": json.dumps({"acme/renet": "https://github.com/acme/renet/pull/5"})
        },
    )
    assert exit_code == 0
    assert not any(call.startswith("pr\tcreate") for call in calls), "a duplicate PR was opened"
    assert b"reusing existing acme/renet PR for branch 0906-1" in stderr
    assert b"/pull/5" in bodies["body-new.md"]


def test_the_block_is_rebuilt_not_appended() -> None:
    """Idempotence half 2: last round's links are replaced, not accumulated."""
    stale = (
        "Operator text above.\n"
        "<!-- autopilot-submodule-prs:begin -->\n"
        "**Submodule PRs**\n\n"
        "- `private/elite` -> https://github.com/acme/elite/pull/1\n"
        "<!-- autopilot-submodule-prs:end -->\n"
        "Operator text below."
    )
    exit_code, _, _, _, bodies = _sides(
        "rebuild", verdict=verdict_json(sub("private/renet")), console_body=stale
    )
    assert exit_code == 0
    body = bodies["body-new.md"].decode("utf-8")
    assert "private/elite" not in body, "the previous round's links survived the rebuild"
    assert body.count("autopilot-submodule-prs:begin") == 1
    assert "Operator text above." in body
    assert "Operator text below." in body
    assert "- `private/renet` -> https://github.com/acme/renet/pull/77" in body


def test_an_unterminated_block_swallows_the_rest() -> None:
    """PRESERVED DEFECT. A BEGIN marker with no END makes the strip drop everything after it, so the operator's text below is lost on the next write. If this is ever fixed, this test is where it shows up."""
    broken = (
        "Keep me.\n"
        "<!-- autopilot-submodule-prs:begin -->\n"
        "- `private/elite` -> https://github.com/acme/elite/pull/1\n"
        "Operator text that is about to disappear."
    )
    exit_code, _, _, _, bodies = _sides(
        "unterminated", verdict=verdict_json(sub("private/renet")), console_body=broken
    )
    assert exit_code == 0
    body = bodies["body-new.md"].decode("utf-8")
    assert "Keep me." in body
    assert "about to disappear" not in body, (
        "the unterminated-block defect is fixed; the port must be updated to match"
    )


def test_several_submodules_in_one_round() -> None:
    """Order is the verdict's order, and each submodule gets its own lookup."""
    exit_code, _, _, calls, bodies = _sides(
        "several",
        verdict=verdict_json(
            sub("private/renet", "fix(renet): a"),
            sub("private/account", "fix(account): b"),
            sub("private/homebrew-tap", "chore(tap): c"),
        ),
        env={
            "FAKE_GH_EXISTING": json.dumps(
                {"acme/account": "https://github.com/acme/account/pull/12"}
            )
        },
    )
    assert exit_code == 0
    creates = [c for c in calls if c.startswith("pr\tcreate")]
    assert len(creates) == 2, "the existing PR was re-created"
    body = bodies["body-new.md"].decode("utf-8")
    assert (
        body.index("private/renet")
        < body.index("private/account")
        < body.index("private/homebrew-tap")
    )
    assert "https://github.com/acme/account/pull/12" in body


def test_only_the_first_line_of_the_message_becomes_the_title() -> None:
    exit_code, _, _, calls, _ = _sides(
        "title",
        verdict=verdict_json(sub("private/renet", "fix(renet): headline\n\nbody paragraph")),
    )
    assert exit_code == 0
    create = next(c for c in calls if c.startswith("pr\tcreate"))
    assert "--title\tfix(renet): headline\t" in create
    assert "body paragraph" not in create


def test_an_unmapped_path_refuses_to_guess() -> None:
    exit_code, _, stderr, calls, _ = _sides(
        "unmapped", verdict=verdict_json(sub("private/unknown"))
    )
    assert exit_code == 1
    assert b"submodule-unmapped: 'private/unknown' has no repository in the map" in stderr
    assert calls == [], "a gh call was made for an unmapped path"


def test_a_dry_run_rebuilds_onto_an_empty_body() -> None:
    """PRESERVED DEFECT, and the reason a dry run is not a preview: it never reads the live PR body, so the block it prints sits on nothing. The TWO blank lines at the top are real output and both are accounted for: an empty body still gives awk one (empty) line, and the block's own `printf '\\n%s\\n'` adds the second."""
    exit_code, stdout, stderr, calls, _ = _sides(
        "dry-run",
        [*BASE_ARGV, "--dry-run"],
        verdict=verdict_json(sub("private/renet")),
        console_body="Operator text that a dry run will not show.",
        env={"AUTOPILOT_ALLOW_PUSH": ""},
    )
    assert exit_code == 0
    assert calls == [], "a dry run called gh"
    assert stdout == (
        b"\n\n<!-- autopilot-submodule-prs:begin -->\n"
        b"**Submodule PRs**\n\n"
        b"- `private/renet` -> https://github.com/acme/renet/pull/DRY-RUN\n"
        b"<!-- autopilot-submodule-prs:end -->\n"
    ), stdout
    assert b"Operator text" not in stdout
    assert b"dry-run: would link 1 submodule PR(s) in acme/widget#31" in stderr


def test_the_stage_flag_fails_closed() -> None:
    for name, value in (("empty", ""), ("false", "false"), ("uppercase", "TRUE")):
        exit_code, _, stderr, calls, _ = _sides(
            "flag-%s" % name,
            verdict=verdict_json(sub("private/renet")),
            env={"AUTOPILOT_ALLOW_PUSH": value},
        )
        assert exit_code == 1, name
        assert b"stage-flag-disabled" in stderr
        assert calls == [], "a PR was opened with the stage flag off"


def test_usage_and_missing_verdict() -> None:
    for drop in ("--verdict", "--repo", "--pr", "--branch"):
        argv: list[str] = []
        skip = False
        for token in BASE_ARGV:
            if skip:
                skip = False
                continue
            if token == drop:
                skip = True
                continue
            argv.append(token)
        exit_code, _, stderr, calls, _ = _sides(
            "missing%s" % drop, argv, verdict=verdict_json(sub("private/renet"))
        )
        assert exit_code == 2, drop
        assert b"usage: submodule-prs.sh" in stderr
        assert calls == []

    exit_code, _, stderr, _, _ = _sides(
        "verdict-absent", ["--verdict", "nope.json", "--repo", REPO, "--pr", PR, "--branch", BRANCH]
    )
    assert exit_code == 1
    assert b"Required file" in stderr


def test_a_malformed_verdict_fails_with_jqs_own_words() -> None:
    exit_code, _, stderr, calls, _ = _sides("malformed", verdict=b"{truncated")
    assert exit_code == 5
    assert stderr.startswith(b"jq: parse error:")
    assert calls == []


def test_a_failing_pr_list_never_becomes_an_empty_answer() -> None:
    """The most expensive failure this script could have: if a rate-limited `pr list` looked empty, every round would open ANOTHER pull request.

    SLOW ON PURPOSE (9 seconds per side): the retry sleeps are real.
    """
    exit_code, _, stderr, calls, _ = _sides(
        "pr-list-fails",
        verdict=verdict_json(sub("private/renet")),
        env={"FAKE_GH_FAIL": "pr list"},
    )
    assert exit_code == 1
    assert [c for c in calls if c.startswith("pr\tcreate")] == [], (
        "a failed lookup was read as 'no PR exists' and a duplicate was opened"
    )
    assert len([c for c in calls if c.startswith("pr\tlist")]) == 3, "not three attempts"
    assert stderr.count(b"retrying...") == 2
    assert b"    gh: fake pr list failure" in stderr


def test_a_non_integer_count_wipes_the_block_and_exits_0() -> None:
    """DEFECT FOUND IN THE TWIN, reproduced here rather than repaired.

    jq's `length` on a NUMBER is its absolute value, so `"submodules": 3.5`
    produces the count `3.5`. Bash's `for ((i = 0; i < 3.5; i++))` is an
    arithmetic syntax error that `set -e` does NOT catch: the diagnostic prints, the loop body never runs, and the script CONTINUES. It then PATCHes the console PR body with an EMPTY `**Submodule PRs**` block -- destroying any links a previous round put there, which reds the required Submodule Branches gate on a complaint no later round can fix by editing code -- and exits 0 saying
    "linked 3.5 submodule PR(s)".

    Driven against the twin directly before this test was written; the port matches it deliberately. Exit code, gh calls and the posted body are compared exactly, the bash diagnostic by shape (it carries the twin's path and line).
    """
    exit_code, _, stderr, calls, bodies = _sides(
        "float-count",
        verdict=b'{"submodules": 3.5}',
        console_body=(
            "Operator text.\n"
            "<!-- autopilot-submodule-prs:begin -->\n"
            "**Submodule PRs**\n\n"
            "- `private/renet` -> https://github.com/acme/renet/pull/5\n"
            "<!-- autopilot-submodule-prs:end -->"
        ),
        exact_stderr=False,
    )
    assert exit_code == 0, "the twin no longer walks past the arithmetic error"
    assert b"3.5" in stderr
    assert b"linked 3.5 submodule PR(s)" in stderr
    assert [c.split("\t")[1] for c in calls] == ["view", "edit"]
    body = bodies["body-new.md"].decode("utf-8")
    assert "pull/5" not in body, "the wipe did not happen; the defect is fixed, update the port"
    assert "**Submodule PRs**\n\n<!-- autopilot-submodule-prs:end -->" in body


def test_the_fake_gh_is_the_gh() -> None:
    """CONTROL for the whole file: if the stub stops winning the PATH lookup, every case above is opening real pull requests."""
    with tempfile.TemporaryDirectory() as td:
        base = pathlib.Path(td)
        resolved = shutil.which("gh", path=_stub_bin(base))
        assert resolved == str(base / "bin" / "gh"), (
            "the fake gh does not win the PATH lookup: %r" % resolved
        )


def test_pure_helpers_are_exercised_directly() -> None:
    assert sp.submodule_repo("private/renet") == "renet"
    assert sp.submodule_repo("private/nope") is None
    # An EMPTY body still yields one line, which is where the leading blank line in a fresh block comes from.
    assert sp.strip_block("") == "\n"
    assert sp.strip_block("a\nb") == "a\nb\n"
    assert sp.strip_block("a\n%s\nx\n%s\nb" % (sp.BEGIN, sp.END)) == "a\nb\n"
    assert sp.strip_block("a\n%s\nx" % sp.BEGIN) == "a\n", "the unterminated hazard changed"
    assert sp.link_line("private/renet", "u") == "- `private/renet` -> u\n"
    assert sp.rebuild_body("a\n", ["- x\n"]) == (
        "a\n\n%s\n**Submodule PRs**\n\n- x\n%s\n" % (sp.BEGIN, sp.END)
    )

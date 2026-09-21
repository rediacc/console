"""`rediacc_ci.autopilot.submodule_prs`, driven against the bytes its bash twin produced.

WHILE BOTH COPIES EXISTED this file ran `.ci/scripts/autopilot/submodule-prs.sh` and the port over one stubbed `gh` and compared FIVE things per case: exit code, stdout, stderr, the recorded `gh` argv, and the body files the run would have posted. The K=5 ledger `.ci/shadow/w7p6-submodule-prs.observations.jsonl` recorded that comparison over five distinct trees.

THE TWIN HAS NOW BEEN DELETED, and every case compares against `goldens/submodule-prs/`, which holds the twin's OWN recorded bytes, captured on its last day in the tree. Each provenance header carries the twin's blob sha, so `git cat-file -p <sha>` still yields the program that produced them.

THE FAKE `gh` IS A SAFETY CONTROL, NOT A CONVENIENCE, and for this subject that sentence is literal: its success path is `gh pr create`, which OPENS A PULL REQUEST, and `gh pr edit --body-file`, which REPLACES a pull request's body. GitHub restores neither, and `--repo` comes straight off the command line.

Four things stop a case reaching the real binary, and the first is asserted rather than assumed.

The stub directory is FIRST on PATH and `test_the_fake_gh_is_the_gh` resolves `gh` through that PATH; every fixture names `acme/...`, which does not exist; `GH_TOKEN` is a fixture string with `GH_CONFIG_DIR` in the temp tree, so a leaked real `gh` fails auth rather than writing; and the fake RECORDS every argv, so a case that produced no call log fails rather than passing quietly.

THE CALL LOG AND THE BODY FILES ARE THE ARTIFACT, which is why the recorded shape carries `--- gh calls ---` and `--- gh bodies ---`.

Everything this script does is a `gh` call: which repository, which head branch, what title, and the part that matters most, the exact body bytes it would put on the console PR. A port that logged the right sentences and posted the wrong body would sail through a stdout-only recording.

TWO PRESERVED DEFECTS ARE PINNED BY NAME. `an-unterminated-block` records a BEGIN marker with no END making the strip drop everything after it, losing operator text, and `a-dry-run` records a dry run never reading the live body, so what it prints is not what the round would post.

Both are defect reports in recorded form; if either twin behaviour is ever repaired, the recording goes red and the repair gets noticed here.

WHAT IS NORMALISED, and none of it is new. The fake already rewrote the two volatile `--body-file` paths to `<work>/<name>`, because both sides pointed them into their own `mktemp -d`; that substitution predates the freezing.

The recording adds the run directory as `<work>` and the checkout root as `<repo>`, since the one divergent case carries the twin's own path and line, and decodes every stream with `backslashreplace` so a golden stays a UTF-8 text file whatever a fixture holds.
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
from rediacc_ci.autopilot import submodule_prs as sp
from rediacc_ci.tests import frozen

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
PORT = ROOT / ".ci" / "rediacc_ci" / "autopilot" / "submodule_prs.py"
SLUG = "submodule-prs"

CALLS_MARKER = "--- gh calls ---\n"
BODIES_MARKER = "--- gh bodies ---\n"

REPO = "acme/widget"
PR = "31"
BRANCH = "0906-1"

BASE_ARGV = ["--verdict", "verdict.json", "--repo", REPO, "--pr", PR, "--branch", BRANCH]


def verdict_json(*submodules: dict[str, typing.Any]) -> bytes:
    return json.dumps({"submodules": list(submodules)}).encode("utf-8")


def sub(path: str, message: str = "fix(renet): the thing") -> dict[str, typing.Any]:
    return {"path": path, "message": message}


def without(flag: str) -> list[str]:
    """`BASE_ARGV` with one flag and its value removed."""
    argv: list[str] = []
    skip = False
    for token in BASE_ARGV:
        if skip:
            skip = False
            continue
        if token == flag:
            skip = True
            continue
        argv.append(token)
    return argv


STALE_BODY = (
    "Operator text above.\n"
    "<!-- autopilot-submodule-prs:begin -->\n"
    "**Submodule PRs**\n\n"
    "- `private/elite` -> https://github.com/acme/elite/pull/1\n"
    "<!-- autopilot-submodule-prs:end -->\n"
    "Operator text below."
)

BROKEN_BODY = (
    "Keep me.\n"
    "<!-- autopilot-submodule-prs:begin -->\n"
    "- `private/elite` -> https://github.com/acme/elite/pull/1\n"
    "Operator text that is about to disappear."
)

FLOAT_BODY = (
    "Operator text.\n"
    "<!-- autopilot-submodule-prs:begin -->\n"
    "**Submodule PRs**\n\n"
    "- `private/renet` -> https://github.com/acme/renet/pull/5\n"
    "<!-- autopilot-submodule-prs:end -->"
)

# name -> argv, the verdict fixture, the console PR body the fake serves, and the environment
CASE_KW: dict[str, dict[str, typing.Any]] = {
    "no-submodules": {"verdict": verdict_json()},
    # Exit 0 even with the stage flag OFF, because nothing would be written either way. That ordering is the twin's, and it is deliberate.
    "no-submodules-with-the-flag-off": {
        "verdict": verdict_json(),
        "env": {"AUTOPILOT_ALLOW_PUSH": ""},
    },
    "a-new-pr-is-opened-and-linked": {
        "verdict": verdict_json(sub("private/renet")),
        "console_body": "Existing body.",
    },
    "an-existing-pr-is-reused": {
        "verdict": verdict_json(sub("private/renet")),
        "env": {
            "FAKE_GH_EXISTING": json.dumps({"acme/renet": "https://github.com/acme/renet/pull/5"})
        },
    },
    "the-block-is-rebuilt-not-appended": {
        "verdict": verdict_json(sub("private/renet")),
        "console_body": STALE_BODY,
    },
    "an-unterminated-block": {
        "verdict": verdict_json(sub("private/renet")),
        "console_body": BROKEN_BODY,
    },
    "several-submodules-in-one-round": {
        "verdict": verdict_json(
            sub("private/renet", "fix(renet): a"),
            sub("private/account", "fix(account): b"),
            sub("private/homebrew-tap", "chore(tap): c"),
        ),
        "env": {
            "FAKE_GH_EXISTING": json.dumps(
                {"acme/account": "https://github.com/acme/account/pull/12"}
            )
        },
    },
    "only-the-first-line-becomes-the-title": {
        "verdict": verdict_json(sub("private/renet", "fix(renet): headline\n\nbody paragraph"))
    },
    "an-unmapped-path": {"verdict": verdict_json(sub("private/unknown"))},
    "a-dry-run": {
        "argv": [*BASE_ARGV, "--dry-run"],
        "verdict": verdict_json(sub("private/renet")),
        "console_body": "Operator text that a dry run will not show.",
        "env": {"AUTOPILOT_ALLOW_PUSH": ""},
    },
    "the-stage-flag-empty": {
        "verdict": verdict_json(sub("private/renet")),
        "env": {"AUTOPILOT_ALLOW_PUSH": ""},
    },
    "the-stage-flag-false": {
        "verdict": verdict_json(sub("private/renet")),
        "env": {"AUTOPILOT_ALLOW_PUSH": "false"},
    },
    "the-stage-flag-uppercase": {
        "verdict": verdict_json(sub("private/renet")),
        "env": {"AUTOPILOT_ALLOW_PUSH": "TRUE"},
    },
    "an-absent-verdict-file": {
        "argv": ["--verdict", "nope.json", "--repo", REPO, "--pr", PR, "--branch", BRANCH]
    },
    "a-malformed-verdict": {"verdict": b"{truncated"},
    "a-failing-pr-list": {
        "verdict": verdict_json(sub("private/renet")),
        "env": {"FAKE_GH_FAIL": "pr list"},
    },
    "a-non-integer-count": {"verdict": b'{"submodules": 3.5}', "console_body": FLOAT_BODY},
}

REQUIRED_FLAGS = ("--verdict", "--repo", "--pr", "--branch")
for _flag in REQUIRED_FLAGS:
    CASE_KW["missing%s" % _flag] = {
        "argv": without(_flag),
        "verdict": verdict_json(sub("private/renet")),
    }

CASES = tuple(CASE_KW)

# The one case whose diagnostic is bash naming its own path and line. Compared by shape, in its own test.
DIVERGENT = ("a-non-integer-count",)

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


def stub_bin(base: pathlib.Path) -> str:
    """The fake `gh` first on PATH. See `test_the_fake_gh_is_the_gh`."""
    stub = base / "bin"
    stub.mkdir(exist_ok=True)
    fake = stub / "gh"
    fake.write_text(FAKE_GH, encoding="utf-8")
    fake.chmod(0o755)
    return "%s:%s" % (stub, os.environ.get("PATH", "/usr/bin:/bin"))


def decode(raw: bytes) -> str:
    return raw.decode("utf-8", errors="backslashreplace")


def run(subject: pathlib.Path, base: pathlib.Path, name: str) -> tuple[int, str, str, str, str]:
    """One subject, once, over this case's own tree."""
    kw = CASE_KW[name]
    base.mkdir(parents=True, exist_ok=True)
    if "verdict" in kw:
        (base / "verdict.json").write_bytes(kw["verdict"])
    console_body = base / "console-body.txt"
    console_body.write_text(kw.get("console_body", ""), encoding="utf-8")
    call_log = base / "gh-calls.log"
    call_log.write_text("", encoding="utf-8")
    bodies = base / "gh-bodies"
    bodies.mkdir(exist_ok=True)
    env = {
        "PATH": stub_bin(base),
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
        "AUTOPILOT_ALLOW_PUSH": "true",
    }
    env.update(kw.get("env") or {})
    runner = shutil.which("bash") or "/bin/bash" if subject.suffix == ".sh" else sys.executable
    proc = subprocess.run(
        [runner, str(subject), *kw.get("argv", BASE_ARGV)],
        capture_output=True,
        env=env,
        check=False,
        cwd=str(base),
        timeout=120,
    )
    written = {path.name: decode(path.read_bytes()) for path in sorted(bodies.iterdir())}

    def mask(text: str) -> str:
        return text.replace(str(base), "<work>").replace(str(ROOT), "<repo>")

    return (
        proc.returncode,
        mask(decode(proc.stdout)),
        mask(decode(proc.stderr)),
        mask(decode(call_log.read_bytes())),
        mask(json.dumps(written, indent=2, sort_keys=True)),
    )


def render(code: int, stdout: str, stderr: str, calls: str, bodies: str) -> str:
    return "%s%s%s%s%s\n" % (
        frozen.render(code, stdout, stderr),
        CALLS_MARKER,
        calls,
        BODIES_MARKER,
        bodies,
    )


def recorded(name: str) -> tuple[int, str, str, str, str]:
    text = frozen.read(SLUG, name)
    exit_line, rest = text.split("\n", 1)
    stdout, rest = rest.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)
    stderr, rest = rest.split(CALLS_MARKER, 1)
    calls, bodies = rest.split(BODIES_MARKER, 1)
    return (
        int(exit_line.removeprefix("exit: ")),
        stdout,
        stderr,
        calls,
        bodies.removesuffix("\n"),
    )


def lines(calls: str) -> list[str]:
    return [line for line in calls.splitlines() if line]


def files(bodies: str) -> dict[str, str]:
    return json.loads(bodies)


def compare(tmp_path: pathlib.Path, name: str) -> tuple[int, str, str, str, str]:
    want = recorded(name)
    got = run(PORT, tmp_path / "port", name)
    labels = ("exit", "stdout", "stderr", "gh calls", "gh body files")
    for label, a, b in zip(labels, want, got, strict=True):
        assert a == b, "%s: %s diverged:\n--- recorded ---\n%r\n--- port ---\n%r" % (
            name,
            label,
            a,
            b,
        )
    return got


@pytest.mark.parametrize("name", [c for c in CASES if c not in DIVERGENT])
def test_port_matches_the_twins_recorded_output(tmp_path: pathlib.Path, name: str) -> None:
    compare(tmp_path, name)


def test_every_case_has_a_golden_and_no_golden_is_orphaned() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, set(CASES))


# --------------------------------------------------------------------------- What the recordings say ---------------------------------------------------------------------------


def test_no_submodules_is_a_quiet_zero() -> None:
    """A round that named no submodules exits 0 and touches nothing, flag on or off."""
    code, _, stderr, calls, _ = recorded("no-submodules")
    assert code == 0
    assert lines(calls) == []
    assert "the round named no submodules; nothing to open or link" in stderr
    code, _, _, calls, _ = recorded("no-submodules-with-the-flag-off")
    assert code == 0
    assert lines(calls) == []


def test_a_new_submodule_pr_is_opened_and_linked() -> None:
    """The full path: look, create, read the console body, write it back."""
    code, _, stderr, calls, bodies = recorded("a-new-pr-is-opened-and-linked")
    assert code == 0
    call = lines(calls)
    assert call[0].startswith("pr\tlist\t--repo\tacme/renet\t--head\t0906-1\t--state\topen")
    assert call[1] == (
        "pr\tcreate\t--repo\tacme/renet\t--head\t0906-1\t--base\tmain\t--title\t"
        "fix(renet): the thing\t--body-file\t<work>/body.txt"
    ), call[1]
    assert call[2] == 'pr\tview\t31\t--repo\tacme/widget\t--json\tbody\t--jq\t.body // ""'
    assert call[3] == "pr\tedit\t31\t--repo\tacme/widget\t--body-file\t<work>/body-new.md"
    written = files(bodies)
    assert written["body.txt"] == (
        "Submodule change for acme/widget#31.\n\nOpened by the autopilot harness "
        "alongside the console PR; review there.\n"
    )
    assert written["body-new.md"] == (
        "Existing body.\n"
        "\n<!-- autopilot-submodule-prs:begin -->\n"
        "**Submodule PRs**\n\n"
        "- `private/renet` -> https://github.com/acme/renet/pull/77\n"
        "<!-- autopilot-submodule-prs:end -->\n"
    ), written["body-new.md"]
    assert "opened acme/renet PR for branch 0906-1" in stderr
    assert "linked 1 submodule PR(s)" in stderr


def test_an_existing_pr_is_reused() -> None:
    """Idempotence half 1: a second round on the same branch opens nothing."""
    code, _, stderr, calls, bodies = recorded("an-existing-pr-is-reused")
    assert code == 0
    assert not any(call.startswith("pr\tcreate") for call in lines(calls)), (
        "a duplicate PR was opened"
    )
    assert "reusing existing acme/renet PR for branch 0906-1" in stderr
    assert "/pull/5" in files(bodies)["body-new.md"]


def test_the_block_is_rebuilt_not_appended() -> None:
    """Idempotence half 2: last round's links are replaced, not accumulated."""
    code, _, _, _, bodies = recorded("the-block-is-rebuilt-not-appended")
    assert code == 0
    body = files(bodies)["body-new.md"]
    assert "private/elite" not in body, "the previous round's links survived the rebuild"
    assert body.count("autopilot-submodule-prs:begin") == 1
    assert "Operator text above." in body
    assert "Operator text below." in body
    assert "- `private/renet` -> https://github.com/acme/renet/pull/77" in body


def test_an_unterminated_block_swallows_the_rest() -> None:
    """PRESERVED DEFECT. A BEGIN marker with no END makes the strip drop everything after it, so the operator's text below is lost on the next write. If this is ever fixed, this recording is where it shows up."""
    code, _, _, _, bodies = recorded("an-unterminated-block")
    assert code == 0
    body = files(bodies)["body-new.md"]
    assert "Keep me." in body
    assert "about to disappear" not in body, (
        "the unterminated-block defect is fixed; the port must be updated to match"
    )


def test_several_submodules_in_one_round() -> None:
    """Order is the verdict's order, and each submodule gets its own lookup."""
    code, _, _, calls, bodies = recorded("several-submodules-in-one-round")
    assert code == 0
    creates = [c for c in lines(calls) if c.startswith("pr\tcreate")]
    assert len(creates) == 2, "the existing PR was re-created"
    body = files(bodies)["body-new.md"]
    assert (
        body.index("private/renet")
        < body.index("private/account")
        < body.index("private/homebrew-tap")
    )
    assert "https://github.com/acme/account/pull/12" in body


def test_only_the_first_line_of_the_message_becomes_the_title() -> None:
    code, _, _, calls, _ = recorded("only-the-first-line-becomes-the-title")
    assert code == 0
    create = next(c for c in lines(calls) if c.startswith("pr\tcreate"))
    assert "--title\tfix(renet): headline\t" in create
    assert "body paragraph" not in create


def test_an_unmapped_path_refuses_to_guess() -> None:
    code, _, stderr, calls, _ = recorded("an-unmapped-path")
    assert code == 1
    assert "submodule-unmapped: 'private/unknown' has no repository in the map" in stderr
    assert lines(calls) == [], "a gh call was made for an unmapped path"


def test_a_dry_run_rebuilds_onto_an_empty_body() -> None:
    """PRESERVED DEFECT, and the reason a dry run is not a preview: it never reads the live PR body, so the block it prints sits on nothing.

    The TWO blank lines at the top are real output and both are accounted for: an empty body still gives awk one (empty) line, and the block's own `printf '\\n%s\\n'` adds the second.
    """
    code, stdout, stderr, calls, _ = recorded("a-dry-run")
    assert code == 0
    assert lines(calls) == [], "a dry run called gh"
    assert stdout == (
        "\n\n<!-- autopilot-submodule-prs:begin -->\n"
        "**Submodule PRs**\n\n"
        "- `private/renet` -> https://github.com/acme/renet/pull/DRY-RUN\n"
        "<!-- autopilot-submodule-prs:end -->\n"
    ), stdout
    assert "Operator text" not in stdout
    assert "dry-run: would link 1 submodule PR(s) in acme/widget#31" in stderr


def test_the_stage_flag_fails_closed() -> None:
    for name in ("the-stage-flag-empty", "the-stage-flag-false", "the-stage-flag-uppercase"):
        code, _, stderr, calls, _ = recorded(name)
        assert code == 1, name
        assert "stage-flag-disabled" in stderr
        assert lines(calls) == [], "a PR was opened with the stage flag off"


def test_usage_and_missing_verdict() -> None:
    for flag in REQUIRED_FLAGS:
        code, _, stderr, calls, _ = recorded("missing%s" % flag)
        assert code == 2, flag
        assert "usage: submodule-prs.sh" in stderr
        assert lines(calls) == []
    code, _, stderr, _, _ = recorded("an-absent-verdict-file")
    assert code == 1
    assert "Required file" in stderr


def test_a_malformed_verdict_fails_with_jqs_own_words() -> None:
    code, _, stderr, calls, _ = recorded("a-malformed-verdict")
    assert code == 5
    assert stderr.startswith("jq: parse error:")
    assert lines(calls) == []


def test_a_failing_pr_list_never_becomes_an_empty_answer() -> None:
    """The most expensive failure this script could have: if a rate-limited `pr list` looked empty, every round would open ANOTHER pull request.

    SLOW ON PURPOSE (9 seconds): the retry sleeps are real.
    """
    code, _, stderr, calls, _ = recorded("a-failing-pr-list")
    assert code == 1
    assert [c for c in lines(calls) if c.startswith("pr\tcreate")] == [], (
        "a failed lookup was read as 'no PR exists' and a duplicate was opened"
    )
    assert len([c for c in lines(calls) if c.startswith("pr\tlist")]) == 3, "not three attempts"
    assert stderr.count("retrying...") == 2
    assert "    gh: fake pr list failure" in stderr


def test_the_fake_gh_is_the_gh(tmp_path: pathlib.Path) -> None:
    """CONTROL for the whole file: if the stub stops winning the PATH lookup, every case above is opening real pull requests."""
    resolved = shutil.which("gh", path=stub_bin(tmp_path))
    assert resolved == str(tmp_path / "bin" / "gh"), (
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


# --------------------------------------------------------------------------- The one divergence, pinned rather than papered over ---------------------------------------------------------------------------


def test_divergence_a_non_integer_count_wipes_the_block_and_exits_0(
    tmp_path: pathlib.Path,
) -> None:
    """DEFECT FOUND IN THE TWIN, reproduced rather than repaired.

    jq's `length` on a NUMBER is its absolute value, so `"submodules": 3.5` produced the count `3.5`. Bash's `for ((i = 0; i < 3.5; i++))` is an arithmetic syntax error that `set -e` does NOT catch: the diagnostic printed, the loop body never ran, and the script CONTINUED.

    It then PATCHed the console PR body with an EMPTY `**Submodule PRs**` block, destroying any links a previous round had put there, and exited 0 saying "linked 3.5 submodule PR(s)". Exit code, gh calls and the posted body are compared exactly; the bash diagnostic is compared by shape, because it carries the twin's path and line.
    """
    name = "a-non-integer-count"
    want = recorded(name)
    got = run(PORT, tmp_path / "port", name)
    assert want[0] == got[0] == 0, "the twin no longer walks past the arithmetic error"
    assert want[1] == got[1]
    assert "3.5" in want[2]
    assert "3.5" in got[2]
    assert "linked 3.5 submodule PR(s)" in want[2]
    assert "linked 3.5 submodule PR(s)" in got[2]
    assert want[3] == got[3]
    assert [c.split("\t")[1] for c in lines(want[3])] == ["view", "edit"]
    body = files(want[4])["body-new.md"]
    assert "pull/5" not in body, "the wipe did not happen; the defect is fixed, update the port"
    assert "**Submodule PRs**\n\n<!-- autopilot-submodule-prs:end -->" in body
    assert want[4] == got[4]


# --------------------------------------------------------------------------- The control: these goldens can actually fail ---------------------------------------------------------------------------


def test_a_planted_append_instead_of_rebuild_is_caught(tmp_path: pathlib.Path) -> None:
    """THE CONTROL ON THE GOLDENS. Stop stripping the previous round's block before writing the new one.

    Idempotence is the product here: a round that appends rather than rebuilds leaves last round's links beside this round's, and the console PR body grows a duplicate block every round. Nothing on either stream says so and the `gh` argv is unchanged, so only the `--- gh bodies ---` section sees it. The mutant is a throwaway copy, and the tracked port is never touched.
    """
    original = PORT.read_text(encoding="utf-8")
    anchor = "def strip_block(body: str) -> str:\n"
    assert original.count(anchor) == 1, "the plant's anchor moved"
    mutated = original.replace(
        anchor, anchor + '    return body if body.endswith("\\n") else body + "\\n"\n'
    )

    mutant = tmp_path / "plant" / "mutant.py"
    mutant.parent.mkdir(parents=True)
    mutant.write_text(mutated, encoding="utf-8")

    name = "the-block-is-rebuilt-not-appended"
    planted = run(mutant, tmp_path / "planted", name)
    want = recorded(name)
    assert "private/elite" not in files(want[4])["body-new.md"], "the recorded corpus moved"
    assert "private/elite" in files(planted[4])["body-new.md"], (
        "the plant did not leave the previous round's links behind"
    )
    assert planted[3] == want[3], "the plant was supposed to leave the gh calls alone"

    compare(tmp_path, name)
    assert PORT.read_text(encoding="utf-8") == original

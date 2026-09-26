"""`rediacc_ci.ci.dispatch_watchdog`, driven against the bytes its bash twin printed.

WHILE BOTH COPIES EXISTED this file ran `.ci/scripts/ci/dispatch-watchdog.sh` and the port through the same recording fake `gh` and compared exit code, stdout and stderr. The K=5 ledger `.ci/shadow/w7p6-dispatch-watchdog.observations.jsonl` recorded that comparison over five distinct trees. The twin has now been deleted and every case that executed it compares against
`goldens/dispatch-watchdog/`, which holds the twin's OWN recorded bytes, captured from the tracked script on its last day in the tree. Each golden's provenance header carries the blob sha, so `git cat-file -p <sha>` still yields the program that printed them.

THE FAKE `gh` IS NOT A CONVENIENCE: every path of this script either reads the GitHub API or DISPATCHES A WORKFLOW RUN, so there is no invocation a recording could safely let reach GitHub. The fake logs its own argv as `call: gh ...` on stderr -- which is why no separate call-log section is needed here, the calls ARE in the recorded stderr -- and answers from five environment
variables:

    FAKE_GH_API_STDOUT   the `gh api` body, on stdout
    FAKE_GH_API_STDERR   a `gh api` diagnostic, on stderr
    FAKE_GH_API_RC       the `gh api` exit status
    FAKE_GH_RUN_STDERR   a `gh workflow run` diagnostic
    FAKE_GH_RUN_RC       the `gh workflow run` exit status

THE TWO SUBCOMMANDS ANSWER SEPARATELY because the twin treated their streams differently: `gh api`'s stderr passed straight through to the script's own,
while `try_dispatch` captured `gh workflow run`'s two streams MERGED and hid
them entirely on success. A single-answer fake would make those two facts indistinguishable.

The `call:` line is also what made a shadow-gate ledger possible for this pair. `shadow-gate.ts` classifies `→ ` and `✓ ` as CHATTER before any `--finding-re` is consulted, and a successful dispatch reported ONLY through `log_info`, so no message-text regex could ever produce a finding on the happy path. The ledger was recorded with `--finding-re '^call: '`.

TWO KINDS OF CASE ARE NOT COMPARED BYTE FOR BYTE, and both say so in `DIVERGENT`. bash's `${VAR:?}` and `$2: unbound variable` name a LINE OF THE TWIN, which the port cannot and must not reproduce; those cases compare the status, the empty stdout and the reason instead. Defect C's octal abort makes bash print `((: 08: value too great for base (error token is "08")`;
`strip_bash_arith` removes exactly that line and nothing else, and the case that uses it asserts the removed line was really in the recording.

THE THREE STALENESS ALARMS THAT READ THE TWIN'S SOURCE ARE GONE, and the recordings replace them. They pinned the cap, the 404 pattern, the `-f` field order and the option list against the file CI ran. A deleted file does not drift; every one of those is now pinned by bytes the twin really printed -- the cap in two boundary recordings, the 404 pattern by four recordings either
side of it, and the full `-f` list inside the recorded `call: gh workflow run` line.
"""

from __future__ import annotations

import os
import shlex
import shutil
import stat
import sys
from typing import TYPE_CHECKING

import pytest

from rediacc_ci.ci import dispatch_watchdog as port
from rediacc_ci.tests import differential as diff
from rediacc_ci.tests import frozen

if TYPE_CHECKING:
    import pathlib

SLUG = "dispatch-watchdog"
MODULE = "rediacc_ci.ci.dispatch_watchdog"

FAKE_GH = """#!/bin/bash
printf 'call: gh' >&2
for a in "$@"; do printf ' %s' "$a" >&2; done
printf '\\n' >&2
if [[ "$1" == "api" ]]; then
  [[ -n "${FAKE_GH_API_STDERR:-}" ]] && printf '%s\\n' "$FAKE_GH_API_STDERR" >&2
  [[ -n "${FAKE_GH_API_STDOUT:-}" ]] && printf '%s\\n' "$FAKE_GH_API_STDOUT"
  exit "${FAKE_GH_API_RC:-0}"
fi
[[ -n "${FAKE_GH_RUN_STDERR:-}" ]] && printf '%s\\n' "$FAKE_GH_RUN_STDERR" >&2
exit "${FAKE_GH_RUN_RC:-0}"
"""

# Everything the twin, common.sh and python3 reached for through PATH, so a gh-free PATH can be built without also removing bash. `gh` is the ONE name deliberately absent.
TOOLS_WITHOUT_GH = (
    "bash",
    "cat",
    "cut",
    "date",
    "dirname",
    "env",
    "grep",
    "head",
    "id",
    "mktemp",
    "python3",
    "sed",
    "sort",
    "tr",
    "uname",
)

BASE = {"GITHUB_REPOSITORY": "rediacc/console"}

BOOTSTRAP_TEXTS = (
    "workflow watchdog-monitor.yml not found on the default branch",
    "could not create workflow dispatch event: HTTP 404: Not Found (watchdog-monitor.yml)",
)


@pytest.fixture(scope="module")
def bindir(tmp_path_factory) -> pathlib.Path:
    """The recording fake, once per module."""
    root = tmp_path_factory.mktemp("dispatch-watchdog-bin")
    return write_fake_gh(root)


def write_fake_gh(root: pathlib.Path) -> pathlib.Path:
    script = root / "gh"
    script.write_text(FAKE_GH, encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return root


@pytest.fixture(scope="module")
def nogh(tmp_path_factory) -> pathlib.Path:
    """A PATH that has every tool BUT `gh`, for the require_cmd refusal."""
    return write_nogh(tmp_path_factory.mktemp("dispatch-watchdog-nogh"))


def write_nogh(root: pathlib.Path) -> pathlib.Path:
    """Built by symlink rather than by pruning `/usr/bin` off PATH, because that would also remove bash and turn a refusal into a 127 from the harness."""
    for tool in TOOLS_WITHOUT_GH:
        found = shutil.which(tool)
        if found is not None and not (root / tool).exists():
            (root / tool).symlink_to(found)
    assert shutil.which("gh", path=str(root)) is None, "the control did not fire"
    return root


def strip_bash_arith(stderr: str) -> str:
    """Drop bash's own `((: ...: value too great for base` line. Nothing else."""
    kept = [line for line in stderr.split("\n") if "value too great for base" not in line]
    return "\n".join(kept)


BASE_ARGS = ("--run-id", "1", "--generation", "1", "--head-ref", "m", "--pr-number", "3")

CASE_KW: dict[str, tuple[tuple[str, ...], dict[str, object]]] = {
    "an-explicit-head-ref": (
        ("--run-id", "123", "--generation", "2", "--pr-number", "7", "--head-ref", "feat/x"),
        {},
    ),
    "both-lookups-are-made": (
        ("--run-id", "123", "--generation", "1"),
        {"env_extra": {"FAKE_GH_API_STDOUT": "mybranch"}},
    ),
    "an-explicit-pr-number-skips-one-lookup": (
        ("--run-id", "5", "--generation", "1", "--pr-number", "9"),
        {"env_extra": {"FAKE_GH_API_STDOUT": "topic"}},
    ),
    "an-empty-head-ref-from-the-api": (
        ("--run-id", "5", "--generation", "1", "--pr-number", "9"),
        {"env_extra": {"FAKE_GH_API_STDOUT": ""}},
    ),
    "a-head-ref-dispatch-that-succeeds": (
        ("--run-id", "5", "--generation", "1", "--pr-number", "9", "--head-ref", "gone"),
        {"env_extra": {"FAKE_GH_API_STDOUT": "main", "FAKE_GH_RUN_RC": "0"}},
    ),
    "a-failed-default-branch-lookup": (
        BASE_ARGS,
        {
            "env_extra": {
                "FAKE_GH_API_RC": "1",
                "FAKE_GH_RUN_RC": "1",
                "FAKE_GH_RUN_STDERR": "boom",
            }
        },
    ),
    "a-bootstrap-404-by-name": (
        BASE_ARGS,
        {"env_extra": {"FAKE_GH_RUN_RC": "1", "FAKE_GH_RUN_STDERR": BOOTSTRAP_TEXTS[0]}},
    ),
    "a-bootstrap-404-by-http-status": (
        BASE_ARGS,
        {"env_extra": {"FAKE_GH_RUN_RC": "1", "FAKE_GH_RUN_STDERR": BOOTSTRAP_TEXTS[1]}},
    ),
    "a-404-for-another-workflow": (
        BASE_ARGS,
        {
            "env_extra": {
                "FAKE_GH_RUN_RC": "1",
                "FAKE_GH_RUN_STDERR": "HTTP 404: Not Found (ci.yml)",
            }
        },
    ),
    "a-404-split-across-two-lines": (
        BASE_ARGS,
        {
            "env_extra": {
                "FAKE_GH_RUN_RC": "1",
                "FAKE_GH_RUN_STDERR": "HTTP 404: Not Found\nsomething about watchdog-monitor",
            }
        },
    ),
    "generation-23-exceeds-the-cap": (("--run-id", "1", "--generation", "23"), {}),
    "generation-22-is-inside-the-cap": (
        ("--run-id", "1", "--generation", "22", "--head-ref", "m", "--pr-number", "3"),
        {},
    ),
    "an-octal-invalid-generation": (
        ("--run-id", "1", "--generation", "08", "--head-ref", "m", "--pr-number", "3"),
        {},
    ),
    "an-octal-generation-below-the-cap": (
        ("--run-id", "1", "--generation", "025", "--head-ref", "m", "--pr-number", "3"),
        {},
    ),
    "an-octal-generation-above-the-cap": (("--run-id", "1", "--generation", "030"), {}),
    "a-missing-gh": (("--run-id", "1", "--generation", "1"), {"nogh": True}),
    "a-missing-gh-with-a-bad-option": (("--nope",), {"nogh": True}),
    "an-unknown-option": (("--nope",), {}),
    "no-arguments-at-all": ((), {}),
    "only-a-generation": (("--generation", "1"), {}),
    "only-a-run-id": (("--run-id", "1"), {}),
    "a-missing-github-repository": (
        ("--run-id", "1", "--generation", "1"),
        {"env_extra": {"GITHUB_REPOSITORY": ""}},
    ),
    "a-trailing-newline-run-id": (("--run-id", "1\n", "--generation", "1"), {}),
    "an-empty-pending-rerun": (
        (*BASE_ARGS, "--pending-rerun", ""),
        {"env_extra": {"FAKE_GH_RUN_RC": "1"}},
    ),
    "pending-rerun-true": (
        (*BASE_ARGS, "--pending-rerun", "true"),
        {"env_extra": {"FAKE_GH_RUN_RC": "1"}},
    ),
    "pending-rerun-as-the-last-token": (
        ("--run-id", "1", "--generation", "1", "--head-ref", "m", "--pending-rerun"),
        {},
    ),
    "a-failed-head-ref-lookup": (
        ("--run-id", "1", "--generation", "1", "--pr-number", "3"),
        {"env_extra": {"FAKE_GH_API_RC": "4", "FAKE_GH_API_STDERR": "api boom"}},
    ),
    "colour-on-a-terminal": (("--nope",), {"tty": "stderr"}),
    "the-warn-glyph-on-a-terminal": (
        ("--run-id", "1", "--generation", "99"),
        {"tty": "stderr"},
    ),
    "no-color-on-a-terminal": (
        ("--nope",),
        {"tty": "stderr", "env_extra": {"NO_COLOR": "1"}},
    ),
}

# The seven `--run-id` shapes the numeric anchor refuses, and the three `--generation` ones.
BAD_RUN_IDS = ("x", "1a", "", " 1", "1 ", "1.0", "-1")
BAD_GENERATIONS = ("x", "1a", "2.5")
BAD_PENDING = ("maybe", "TRUE", "1", "yes")
LAST_TOKEN_OPTIONS = ("--run-id", "--generation", "--pr-number", "--head-ref")


def _slug(text: str) -> str:
    """A golden name for an argument value, including the awkward ones."""
    table = {"": "empty", " 1": "leading-space", "1 ": "trailing-space"}
    if text in table:
        return table[text]
    return text.replace(".", "-dot-").replace("-", "minus-") if text[0] == "-" else text


for _bad in BAD_RUN_IDS:
    CASE_KW["a-bad-run-id-%s" % _slug(_bad)] = (("--run-id", _bad, "--generation", "1"), {})
for _bad in BAD_GENERATIONS:
    CASE_KW["a-bad-generation-%s" % _slug(_bad)] = (
        ("--run-id", "1", "--generation", _bad),
        {},
    )
for _bad in BAD_PENDING:
    CASE_KW["a-bad-pending-rerun-%s" % _slug(_bad)] = (
        ("--run-id", "1", "--generation", "1", "--pending-rerun", _bad),
        {},
    )
for _opt in LAST_TOKEN_OPTIONS:
    CASE_KW["%s-as-the-last-token" % _opt.lstrip("-")] = ((_opt,), {})

CASES = tuple(CASE_KW)

# Cases the port does not reproduce byte for byte: bash's own `${VAR:?}` and `$2: unbound variable` diagnostics name a line of the twin, and defect C's octal abort adds an arithmetic line the port has no reason to print. Each is compared by status and reason in its own test below.
DIVERGENT = frozenset(
    {
        "no-arguments-at-all",
        "only-a-generation",
        "only-a-run-id",
        "a-missing-github-repository",
        "a-bad-run-id-empty",
        "an-octal-invalid-generation",
        *("%s-as-the-last-token" % opt.lstrip("-") for opt in LAST_TOKEN_OPTIONS),
    }
)


def run(
    command: str,
    name: str,
    bindir: pathlib.Path,
    nogh_dir: pathlib.Path,
) -> tuple[int, str, str]:
    """One side, once, over the named case."""
    args, kw = CASE_KW[name]
    quoted = " ".join(shlex.quote(a) for a in args)
    extra = dict(BASE)
    extra.update(kw.get("env_extra") or {})  # type: ignore[arg-type]
    root = nogh_dir if kw.get("nogh") else bindir
    resolved = (
        str(root) if kw.get("nogh") else "%s:%s" % (root, os.environ.get("PATH", "/usr/bin:/bin"))
    )
    env = dict(extra, PATH=resolved)
    if command.startswith("python3"):
        env["PYTHONPATH"] = ".ci"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
    return diff.bash_streams(
        "%s %s" % (command, quoted),
        env=diff.env_for(**env),
        tty=kw.get("tty"),  # type: ignore[arg-type]
        timeout=30,
    )


def recorded(name: str) -> tuple[int, str, str]:
    text = frozen.read(SLUG, name)
    exit_line, rest = text.split("\n", 1)
    stdout, stderr = rest.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)
    return int(exit_line.removeprefix("exit: ")), stdout, stderr


def drive(name: str, bindir: pathlib.Path, nogh: pathlib.Path) -> tuple[int, str, str]:
    return run("python3 -m %s" % MODULE, name, bindir, nogh)


def compare(name: str, bindir: pathlib.Path, nogh: pathlib.Path) -> tuple[int, str, str]:
    want = recorded(name)
    got = drive(name, bindir, nogh)
    assert got[0] == want[0], "%s: the twin exited %d, the port %d" % (name, want[0], got[0])
    assert got[1] == want[1], "%s: stdout diverged from the recorded bytes" % name
    assert got[2] == want[2], "%s: stderr diverged from the recorded bytes" % name
    return got


@pytest.mark.parametrize("name", [c for c in CASES if c not in DIVERGENT])
def test_port_matches_the_twins_recorded_output(
    name: str, bindir: pathlib.Path, nogh: pathlib.Path
) -> None:
    compare(name, bindir, nogh)


def test_every_case_has_a_golden_and_no_golden_is_orphaned() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, set(CASES))


# --------------------------------------------------------------------------- The dispatch path ---------------------------------------------------------------------------


def test_an_explicit_head_ref_needs_no_lookup_at_all() -> None:
    """Both `--pr-number` and `--head-ref` given: zero `gh api` calls.

    A successful dispatch was SILENT about the call it made, because `try_dispatch` captured both of its streams. The absence of `gh api` in the recording is therefore the assertion.
    """
    returncode, stdout, stderr = recorded("an-explicit-head-ref")
    assert returncode == 0
    assert stdout == ""
    assert stderr == "✓ Dispatched watchdog generation 2 for run 123 on ref feat/x\n"
    assert "gh api" not in stderr


def test_a_missing_head_ref_and_pr_number_are_resolved_from_the_run() -> None:
    assert recorded("both-lookups-are-made")[2] == (
        'call: gh api repos/rediacc/console/actions/runs/123 --jq .head_branch // ""\n'
        "call: gh api repos/rediacc/console/actions/runs/123 --jq "
        '.pull_requests[0].number // ""\n'
        "✓ Dispatched watchdog generation 1 for run 123 on ref mybranch\n"
    )


def test_an_explicit_pr_number_skips_only_its_own_lookup() -> None:
    """The two lookups were independent `if [[ -z ... ]]` guards, not one."""
    stderr = recorded("an-explicit-pr-number-skips-one-lookup")[2]
    assert stderr.count("call: gh api") == 1
    assert ".head_branch" in stderr
    assert ".pull_requests" not in stderr


def test_an_empty_head_ref_from_the_api_falls_through_to_the_default_branch() -> None:
    """`.head_branch // ""` could legitimately answer empty; then arm two ran."""
    stderr = recorded("an-empty-head-ref-from-the-api")[2]
    assert "call: gh api repos/rediacc/console --jq .default_branch\n" in stderr
    assert "on the default branch (head-ref copy unavailable)" in stderr


def test_a_head_ref_dispatch_that_succeeds_is_the_control_for_the_retry() -> None:
    # The head-ref attempt succeeds with FAKE_GH_RUN_RC=0, so this is the
    # control for the case below rather than the retry itself.
    assert "on ref gone" in recorded("a-head-ref-dispatch-that-succeeds")[2]


def test_defect_d_a_failed_default_branch_lookup_becomes_an_empty_ref() -> None:
    """`--ref ` with nothing after it was the whole receipt.

    The recorded `call: gh workflow run` line is also what now pins the `-f` field list and its ORDER, which used to be re-read out of the twin: a reordered list would still dispatch, and still be a different call.
    """
    returncode, _, stderr = recorded("a-failed-default-branch-lookup")
    assert returncode == 1
    assert "--ref  -f target_run_id=1" in stderr, "the empty ref did not reach gh"
    assert stderr.startswith("call: gh api repos/rediacc/console --jq .default_branch\n")
    assert "✗ Failed to dispatch watchdog generation 1 for run 1:" in stderr
    dispatch = next(line for line in stderr.split("\n") if "workflow run" in line)
    fields = [tok for tok in dispatch.split(" -f ") if "=" in tok]
    assert [f.split("=", 1)[0] for f in fields] == [
        "target_run_id",
        "generation",
        "pr_number",
        "head_ref",
        "pending_rerun",
    ], dispatch


@pytest.mark.parametrize("name", ["a-bootstrap-404-by-name", "a-bootstrap-404-by-http-status"])
def test_the_pre_merge_bootstrap_404_fails_open(name: str) -> None:
    returncode, _, stderr = recorded(name)
    assert returncode == 0
    assert (
        "⚠ watchdog-monitor.yml is not registered on the default branch yet "
        "(pre-merge bootstrap) - run 1 continues UNWATCHED\n" in stderr
    )


def test_a_404_for_some_other_workflow_is_not_the_bootstrap_case() -> None:
    """`HTTP 404.*watchdog-monitor` was ANCHORED on the workflow name."""
    returncode, _, stderr = recorded("a-404-for-another-workflow")
    assert returncode == 1
    assert "✗ Failed to dispatch" in stderr


def test_the_404_pattern_is_matched_per_line_as_grep_matches_it() -> None:
    """`.` never crosses a newline in grep, and must not here either."""
    assert port.is_bootstrap_404("HTTP 404: x\nwatchdog-monitor is elsewhere") is False
    assert port.is_bootstrap_404("nope\nHTTP 404 for watchdog-monitor.yml\nnope") is True
    returncode, _, stderr = recorded("a-404-split-across-two-lines")
    assert returncode == 1
    assert "✗ Failed to dispatch" in stderr


# --------------------------------------------------------------------------- The generation cap ---------------------------------------------------------------------------


def test_the_cap_ends_the_chain_at_23() -> None:
    """The cap value, pinned by the sentence the twin printed rather than by re-reading a file that no longer exists."""
    returncode, _, stderr = recorded("generation-23-exceeds-the-cap")
    assert returncode == 0
    assert stderr == (
        "⚠ Generation 23 exceeds cap 22 (~3h of coverage) - ending the watchdog chain\n"
    )
    assert port.MAX_GENERATIONS == 22
    assert "cap %d " % port.MAX_GENERATIONS in stderr


def test_generation_22_is_still_inside_the_cap() -> None:
    """The boundary in both directions, so the comparison cannot be `>=`."""
    assert "Dispatched watchdog generation 22" in recorded("generation-22-is-inside-the-cap")[2]


def test_defect_c_a_zero_padded_generation_skips_the_cap_entirely(
    bindir: pathlib.Path, nogh: pathlib.Path
) -> None:
    """`08` is invalid octal, the arithmetic aborted, and the run PROCEEDED."""
    assert port.OCTAL_CAP is True
    want_exit, _, want_err = recorded("an-octal-invalid-generation")
    returncode, _, stderr = drive("an-octal-invalid-generation", bindir, nogh)
    assert want_exit == returncode == 0
    assert 'value too great for base (error token is "08")' in want_err, (
        "the recording no longer holds the arithmetic error; the normalisation is now a lie"
    )
    assert strip_bash_arith(want_err) == stderr
    assert "✓ Dispatched watchdog generation 08 for run 1 on ref m\n" in stderr


def test_defect_c_a_zero_padded_generation_is_read_in_octal() -> None:
    """`025` is 21 and dispatches; `030` is 24 and ends the chain."""
    assert "Dispatched watchdog generation 025" in recorded("an-octal-generation-below-the-cap")[2]
    assert "Generation 030 exceeds cap 22" in recorded("an-octal-generation-above-the-cap")[2]


def test_the_octal_helper_answers_both_directions() -> None:
    assert port.octal_gt("23", 22) is True
    assert port.octal_gt("22", 22) is False
    assert port.octal_gt("0", 22) is False
    assert port.octal_gt("00", 22) is False
    assert port.octal_gt("025", 22) is False
    assert port.octal_gt("030", 22) is True
    assert port.octal_gt("08", 22) is None
    assert port.octal_gt("019", 22) is None


# --------------------------------------------------------------------------- Refusals ---------------------------------------------------------------------------


def test_gh_missing_is_refused_before_anything_else() -> None:
    returncode, stdout, stderr = recorded("a-missing-gh")
    assert returncode == 1
    assert stderr == "✗ Required command 'gh' is not available\n"
    assert stdout == ""


def test_gh_is_required_even_for_an_argument_error() -> None:
    """`require_cmd gh` ran BEFORE the parser, so a typo reports the tool."""
    assert recorded("a-missing-gh-with-a-bad-option")[2] == (
        "✗ Required command 'gh' is not available\n"
    )


def test_an_unknown_option_exits_1() -> None:
    returncode, stdout, stderr = recorded("an-unknown-option")
    assert returncode == 1
    assert stdout == ""
    assert stderr == "✗ Unknown option: --nope\n"


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("no-arguments-at-all", port.MISSING_RUN_ID),
        ("only-a-generation", port.MISSING_RUN_ID),
        ("only-a-run-id", port.MISSING_GENERATION),
    ],
)
def test_a_missing_required_value_exits_1(
    name: str, expected: str, bindir: pathlib.Path, nogh: pathlib.Path
) -> None:
    """Divergence 2: bash's `${VAR:?}` named a line of the twin; this names the variable."""
    want_exit, want_out, want_err = recorded(name)
    returncode, stdout, stderr = drive(name, bindir, nogh)
    assert want_exit == returncode == 1
    assert want_out == stdout == ""
    assert expected.split(": ", 1)[1] in want_err
    assert stderr == expected + "\n"


def test_a_missing_github_repository_exits_1(bindir: pathlib.Path, nogh: pathlib.Path) -> None:
    want_exit, _, want_err = recorded("a-missing-github-repository")
    returncode, _, stderr = drive("a-missing-github-repository", bindir, nogh)
    assert want_exit == returncode == 1
    assert "GITHUB_REPOSITORY is required" in want_err
    assert stderr == port.MISSING_REPOSITORY + "\n"


@pytest.mark.parametrize("bad", [b for b in BAD_RUN_IDS if b != ""])
def test_a_non_numeric_run_id_is_refused(bad: str) -> None:
    returncode, _, stderr = recorded("a-bad-run-id-%s" % _slug(bad))
    assert returncode == 1
    assert stderr == "✗ --run-id must be numeric, got: %s\n" % bad


def test_an_empty_run_id_hits_the_required_guard_before_the_regex() -> None:
    """The `:?` guard fired first for an empty value, before the regex."""
    returncode, _, stderr = recorded("a-bad-run-id-empty")
    assert returncode == 1
    assert "--run-id is required" in stderr


@pytest.mark.parametrize("bad", BAD_GENERATIONS)
def test_a_non_numeric_generation_is_refused(bad: str) -> None:
    returncode, _, stderr = recorded("a-bad-generation-%s" % _slug(bad))
    assert returncode == 1
    assert stderr == "✗ --generation must be numeric, got: %s\n" % bad


def test_a_trailing_newline_does_not_satisfy_the_numeric_anchor() -> None:
    """bash's `=~ ^[0-9]+$` rejected `1\\n`; a Python `$` would accept it."""
    returncode, _, stderr = recorded("a-trailing-newline-run-id")
    assert returncode == 1
    assert "must be numeric" in stderr


@pytest.mark.parametrize("bad", BAD_PENDING)
def test_a_bad_pending_rerun_is_refused(bad: str) -> None:
    returncode, _, stderr = recorded("a-bad-pending-rerun-%s" % _slug(bad))
    assert returncode == 1
    assert stderr == "✗ --pending-rerun must be true or false, got: %s\n" % bad


def test_an_empty_pending_rerun_is_accepted_as_false() -> None:
    """`${2:-false}` defaulted on UNSET **or empty**, so `''` is not a refusal.

    The one-character difference between `:-` and `-` decides this, and a port that read `argv[i + 1]` straight would refuse an input the twin accepted.
    """
    assert "-f pending_rerun=false" in recorded("an-empty-pending-rerun")[2]


def test_pending_rerun_true_reaches_the_dispatch() -> None:
    assert "-f pending_rerun=true" in recorded("pending-rerun-true")[2]


def test_defect_e_pending_rerun_as_the_last_token_exits_1_in_total_silence() -> None:
    """Zero bytes on BOTH streams. `shift 2` with one argument left, under set -e."""
    returncode, stdout, stderr = recorded("pending-rerun-as-the-last-token")
    assert returncode == 1
    assert stdout == ""
    assert stderr == ""


@pytest.mark.parametrize("opt", LAST_TOKEN_OPTIONS)
def test_defect_e_a_value_option_as_the_last_token_dies_as_bash(
    opt: str, bindir: pathlib.Path, nogh: pathlib.Path
) -> None:
    """Divergence 3: `$2: unbound variable` versus MISSING_VALUE."""
    name = "%s-as-the-last-token" % opt.lstrip("-")
    want_exit, want_out, want_err = recorded(name)
    returncode, stdout, stderr = drive(name, bindir, nogh)
    assert want_exit == returncode == 1
    assert want_out == stdout == ""
    assert "$2: unbound variable" in want_err
    assert stderr == (port.MISSING_VALUE % opt) + "\n"


def test_defect_f_a_failed_head_ref_lookup_ends_the_run_with_no_message() -> None:
    """Only gh's own stderr explained it, while the NEXT lookup failed open."""
    returncode, stdout, stderr = recorded("a-failed-head-ref-lookup")
    assert returncode == 4
    assert stdout == ""
    assert stderr == (
        'call: gh api repos/rediacc/console/actions/runs/1 --jq .head_branch // ""\napi boom\n'
    )
    assert "✗" not in stderr
    assert "⚠" not in stderr


# --------------------------------------------------------------------------- Colour, and the option list ---------------------------------------------------------------------------


def test_colour_on_a_terminal_is_byte_identical() -> None:
    returncode, _, stderr = recorded("colour-on-a-terminal")
    assert returncode == 1
    assert diff.escape_bytes(stderr) > 0, "the twin printed no colour on a tty"


def test_the_warn_glyph_is_byte_identical_on_a_terminal() -> None:
    returncode, _, stderr = recorded("the-warn-glyph-on-a-terminal")
    assert returncode == 0
    assert diff.escape_bytes(stderr) > 0


def test_no_color_suppresses_colour() -> None:
    assert diff.escape_bytes(recorded("no-color-on-a-terminal")[2]) == 0


def test_the_parser_accepts_every_option_the_twin_accepted() -> None:
    """Each value option has a recording of its own, and `--pending-rerun` has three.

    The alarm this replaces re-read the twin's `case` arms. A recording per option is the same claim made against bytes: an option the parser stopped accepting would report `Unknown option` instead of the refusal its golden holds.
    """
    for opt in port.VALUE_OPTIONS:
        name = "%s-as-the-last-token" % opt.lstrip("-")
        assert name in CASE_KW, opt
        assert "Unknown option" not in recorded(name)[2], opt
    assert "Unknown option" not in recorded("an-empty-pending-rerun")[2]


def test_the_module_runs_as_python_m(bindir: pathlib.Path) -> None:
    """The invocation the ledger records, proven to exist."""
    env = diff.env_for(
        **BASE,
        PATH="%s:%s" % (bindir, os.environ.get("PATH", "/usr/bin:/bin")),
        PYTHONPATH=".ci",
        PYTHONDONTWRITEBYTECODE="1",
        FAKE_GH_API_STDOUT="main",
    )
    code, out, err = diff.bash_streams(
        "%s -m %s --run-id 9 --generation 3" % (sys.executable, MODULE), env=env, timeout=30
    )
    assert code == 0
    assert out == ""
    assert "Traceback" not in err
    assert "✓ Dispatched watchdog generation 3 for run 9 on ref main\n" in err


# --------------------------------------------------------------------------- The control: these goldens can actually fail ---------------------------------------------------------------------------


def test_a_planted_widening_of_the_bootstrap_404_is_caught(
    tmp_path: pathlib.Path, bindir: pathlib.Path, nogh: pathlib.Path
) -> None:
    """THE CONTROL ON THE GOLDENS, planted on the pattern that decides whether a failed dispatch is fatal.

    Dropping the workflow name from `HTTP 404.*watchdog-monitor` reads as a simplification -- a 404 from this script is about this script's workflow, surely -- and it is not: a 404 naming SOME OTHER workflow then fails open too, and the run continues believing it is watched when nothing is watching it. The recording for `a-404-for-another-workflow` exits 1 and says "Failed to
    dispatch"; the mutant exits 0 and warns about a pre-merge bootstrap. The mutation runs from a throwaway copy of the module; the tracked port is never touched.
    """
    source = port.__file__
    with open(source, encoding="utf-8") as fh:
        original = fh.read()
    anchor = (
        'BOOTSTRAP_404 = re.compile(r"not found on the default branch|'
        'HTTP 404.*watchdog-monitor")\n'
    )
    assert original.count(anchor) == 1, "the plant's anchor moved"
    mutated = original.replace(
        anchor,
        'BOOTSTRAP_404 = re.compile(r"not found on the default branch|HTTP 404")\n',
    )
    assert mutated != original

    mutant_dir = tmp_path / "mutant"
    mutant_dir.mkdir(parents=True, exist_ok=True)
    mutant = mutant_dir / "dispatch_watchdog.py"
    mutant.write_text(mutated, encoding="utf-8")

    name = "a-404-for-another-workflow"
    returncode, _, stderr = run("python3 %s" % mutant, name, bindir, nogh)
    assert returncode == 0, "the plant did not change the verdict"
    assert "pre-merge bootstrap" in stderr, "the mutant did not fail open"
    assert recorded(name)[0] == 1, "the recorded verdict moved"

    compare(name, bindir, nogh)
    with open(source, encoding="utf-8") as fh:
        assert fh.read() == original

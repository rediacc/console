"""`rediacc_ci.ci.dispatch_watchdog` against its bash twin.

BOTH SIDES ARE DRIVEN THROUGH ONE RECORDING FAKE `gh` on a scratch PATH, and the fake is not a convenience: every path of this script either reads the GitHub API or DISPATCHES A WORKFLOW RUN, so there is no invocation a test could safely let reach GitHub. The fake logs its own argv as `call: gh ...` on stderr and answers from five environment variables:

    FAKE_GH_API_STDOUT   the `gh api` body, on stdout
    FAKE_GH_API_STDERR   a `gh api` diagnostic, on stderr
    FAKE_GH_API_RC       the `gh api` exit status
    FAKE_GH_RUN_STDERR   a `gh workflow run` diagnostic
    FAKE_GH_RUN_RC       the `gh workflow run` exit status

THE TWO SUBCOMMANDS ANSWER SEPARATELY because the twin treats their streams differently: `gh api`'s stderr passes straight through to the script's own,
while `try_dispatch` captures `gh workflow run`'s two streams MERGED and hides
them entirely on success. A single-answer fake would make those two facts indistinguishable.

The `call:` line is also what makes a shadow-gate ledger possible for this pair. `shadow-gate.ts` classifies `→ ` and `✓ ` as CHATTER before any `--finding-re` is consulted, and a successful dispatch reports ONLY through `log_info`, so no message-text regex could ever produce a finding on the happy path. The ledger is recorded with `--finding-re '^call: '`.

ONE NORMALISATION, AND ONLY ONE. Defect C's octal abort makes bash print `((: 08: value too great for base (error token is "08")` naming a line of the twin. `strip_bash_arith` removes exactly that line and nothing else; the case that uses it asserts the removed line was really there.

The K=5 ledger is `.ci/shadow/w7p6-dispatch-watchdog.observations.jsonl`
(`npx tsx scripts/lib/shadow-gate.ts --pair w7p6-dispatch-watchdog --assert --k 5`).
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

if TYPE_CHECKING:
    import pathlib

TWIN = ".ci/scripts/ci/dispatch-watchdog.sh"
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

# Everything the twin, common.sh and python3 reach for through PATH, so a gh-free PATH can be built without also removing bash. `gh` is the ONE name deliberately absent.
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


@pytest.fixture(scope="module")
def bindir(tmp_path_factory) -> pathlib.Path:
    """The recording fake, once per module."""
    root = tmp_path_factory.mktemp("dispatch-watchdog-bin")
    script = root / "gh"
    script.write_text(FAKE_GH, encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return root


@pytest.fixture(scope="module")
def nogh(tmp_path_factory) -> pathlib.Path:
    """A PATH that has every tool BUT `gh`, for the require_cmd refusal.

    Built by symlink rather than by pruning `/usr/bin` off PATH, because that would also remove bash and turn a refusal into a 127 from the harness.
    """
    root = tmp_path_factory.mktemp("dispatch-watchdog-nogh")
    for tool in TOOLS_WITHOUT_GH:
        found = shutil.which(tool)
        if found is not None:
            (root / tool).symlink_to(found)
    assert shutil.which("gh", path=str(root)) is None, "the control did not fire"
    return root


def run_both(
    bindir: pathlib.Path,
    *args: str,
    env_extra: dict[str, str] | None = None,
    tty: str | None = None,
    path: str | None = None,
) -> tuple[tuple[int, str, str], tuple[int, str, str]]:
    quoted = " ".join(shlex.quote(a) for a in args)
    extra = dict(BASE)
    extra.update(env_extra or {})
    resolved = path or "%s:%s" % (bindir, os.environ.get("PATH", "/usr/bin:/bin"))
    old_env = diff.env_for(**extra, PATH=resolved)
    new_env = diff.env_for(**extra, PATH=resolved, PYTHONPATH=".ci", PYTHONDONTWRITEBYTECODE="1")
    old = diff.bash_streams("bash %s %s" % (TWIN, quoted), env=old_env, tty=tty, timeout=30)
    new = diff.bash_streams("python3 -m %s %s" % (MODULE, quoted), env=new_env, tty=tty, timeout=30)
    return old, new


def assert_identical(
    bindir: pathlib.Path,
    *args: str,
    expect_exit: int,
    env_extra: dict[str, str] | None = None,
) -> tuple[int, str, str]:
    old, new = run_both(bindir, *args, env_extra=env_extra)
    assert old[0] == expect_exit, "twin exit changed: %r" % (old,)
    assert new[0] == old[0], "exit: %r vs %r" % (new, old)
    assert new[1] == old[1], "stdout"
    assert new[2] == old[2], "stderr"
    return old


def strip_bash_arith(stderr: str) -> str:
    """Drop bash's own `((: ...: value too great for base` line. Nothing else."""
    kept = [line for line in stderr.split("\n") if "value too great for base" not in line]
    return "\n".join(kept)


# --------------------------------------------------------------------------- The dispatch path ---------------------------------------------------------------------------


def test_an_explicit_head_ref_needs_no_lookup_at_all(bindir: pathlib.Path) -> None:
    """Both `--pr-number` and `--head-ref` given: zero `gh api` calls.

    A successful dispatch is SILENT about the call it made, because `try_dispatch` captures both of its streams. The absence of `gh api` in the output is therefore the assertion.
    """
    old = assert_identical(
        bindir,
        "--run-id",
        "123",
        "--generation",
        "2",
        "--pr-number",
        "7",
        "--head-ref",
        "feat/x",
        expect_exit=0,
    )
    assert old[1] == ""
    assert old[2] == "✓ Dispatched watchdog generation 2 for run 123 on ref feat/x\n"
    assert "gh api" not in old[2]


def test_a_missing_head_ref_and_pr_number_are_resolved_from_the_run(
    bindir: pathlib.Path,
) -> None:
    old = assert_identical(
        bindir,
        "--run-id",
        "123",
        "--generation",
        "1",
        expect_exit=0,
        env_extra={"FAKE_GH_API_STDOUT": "mybranch"},
    )
    assert old[2] == (
        'call: gh api repos/rediacc/console/actions/runs/123 --jq .head_branch // ""\n'
        "call: gh api repos/rediacc/console/actions/runs/123 --jq "
        '.pull_requests[0].number // ""\n'
        "✓ Dispatched watchdog generation 1 for run 123 on ref mybranch\n"
    )


def test_an_explicit_pr_number_skips_only_its_own_lookup(bindir: pathlib.Path) -> None:
    """The two lookups are independent `if [[ -z ... ]]` guards, not one."""
    old = assert_identical(
        bindir,
        "--run-id",
        "5",
        "--generation",
        "1",
        "--pr-number",
        "9",
        expect_exit=0,
        env_extra={"FAKE_GH_API_STDOUT": "topic"},
    )
    assert old[2].count("call: gh api") == 1
    assert ".head_branch" in old[2]
    assert ".pull_requests" not in old[2]


def test_an_empty_head_ref_from_the_api_falls_through_to_the_default_branch(
    bindir: pathlib.Path,
) -> None:
    """`.head_branch // ""` can legitimately answer empty; then arm two runs."""
    old = assert_identical(
        bindir,
        "--run-id",
        "5",
        "--generation",
        "1",
        "--pr-number",
        "9",
        expect_exit=0,
        env_extra={"FAKE_GH_API_STDOUT": ""},
    )
    assert "call: gh api repos/rediacc/console --jq .default_branch\n" in old[2]
    assert "on the default branch (head-ref copy unavailable)" in old[2]


def test_a_failed_head_ref_dispatch_retries_on_the_default_branch(
    bindir: pathlib.Path,
) -> None:
    old = assert_identical(
        bindir,
        "--run-id",
        "5",
        "--generation",
        "1",
        "--pr-number",
        "9",
        "--head-ref",
        "gone",
        expect_exit=0,
        env_extra={"FAKE_GH_API_STDOUT": "main", "FAKE_GH_RUN_RC": "0"},
    )
    # The head-ref attempt succeeds with FAKE_GH_RUN_RC=0, so this is the
    # control for the case below rather than the retry itself.
    assert "on ref gone" in old[2]


def test_defect_d_a_failed_default_branch_lookup_becomes_an_empty_ref(
    bindir: pathlib.Path,
) -> None:
    """`--ref ` with nothing after it is the whole receipt."""
    old = assert_identical(
        bindir,
        "--run-id",
        "1",
        "--generation",
        "1",
        "--head-ref",
        "m",
        "--pr-number",
        "3",
        expect_exit=1,
        env_extra={"FAKE_GH_API_RC": "1", "FAKE_GH_RUN_RC": "1", "FAKE_GH_RUN_STDERR": "boom"},
    )
    assert "--ref  -f target_run_id=1" in old[2], "the empty ref did not reach gh"
    assert old[2].startswith("call: gh api repos/rediacc/console --jq .default_branch\n")
    assert "✗ Failed to dispatch watchdog generation 1 for run 1:" in old[2]


@pytest.mark.parametrize(
    "text",
    [
        "workflow watchdog-monitor.yml not found on the default branch",
        "could not create workflow dispatch event: HTTP 404: Not Found (watchdog-monitor.yml)",
    ],
)
def test_the_pre_merge_bootstrap_404_fails_open(bindir: pathlib.Path, text: str) -> None:
    old = assert_identical(
        bindir,
        "--run-id",
        "1",
        "--generation",
        "1",
        "--head-ref",
        "m",
        "--pr-number",
        "3",
        expect_exit=0,
        env_extra={"FAKE_GH_RUN_RC": "1", "FAKE_GH_RUN_STDERR": text},
    )
    assert (
        "⚠ watchdog-monitor.yml is not registered on the default branch yet "
        "(pre-merge bootstrap) - run 1 continues UNWATCHED\n" in old[2]
    )


def test_a_404_for_some_other_workflow_is_not_the_bootstrap_case(
    bindir: pathlib.Path,
) -> None:
    """`HTTP 404.*watchdog-monitor` is ANCHORED on the workflow name."""
    old = assert_identical(
        bindir,
        "--run-id",
        "1",
        "--generation",
        "1",
        "--head-ref",
        "m",
        "--pr-number",
        "3",
        expect_exit=1,
        env_extra={"FAKE_GH_RUN_RC": "1", "FAKE_GH_RUN_STDERR": "HTTP 404: Not Found (ci.yml)"},
    )
    assert "✗ Failed to dispatch" in old[2]


def test_the_404_pattern_is_matched_per_line_as_grep_matches_it(
    bindir: pathlib.Path,
) -> None:
    """`.` never crosses a newline in grep, and must not here either."""
    assert port.is_bootstrap_404("HTTP 404: x\nwatchdog-monitor is elsewhere") is False
    assert port.is_bootstrap_404("nope\nHTTP 404 for watchdog-monitor.yml\nnope") is True
    old = assert_identical(
        bindir,
        "--run-id",
        "1",
        "--generation",
        "1",
        "--head-ref",
        "m",
        "--pr-number",
        "3",
        expect_exit=1,
        env_extra={
            "FAKE_GH_RUN_RC": "1",
            "FAKE_GH_RUN_STDERR": "HTTP 404: Not Found\nsomething about watchdog-monitor",
        },
    )
    assert "✗ Failed to dispatch" in old[2]


# --------------------------------------------------------------------------- The generation cap ---------------------------------------------------------------------------


def test_the_cap_ends_the_chain_at_23(bindir: pathlib.Path) -> None:
    old = assert_identical(bindir, "--run-id", "1", "--generation", "23", expect_exit=0)
    assert old[2] == (
        "⚠ Generation 23 exceeds cap 22 (~3h of coverage) - ending the watchdog chain\n"
    )
    assert port.MAX_GENERATIONS == 22


def test_generation_22_is_still_inside_the_cap(bindir: pathlib.Path) -> None:
    """The boundary in both directions, so the comparison cannot be `>=`."""
    old = assert_identical(
        bindir,
        "--run-id",
        "1",
        "--generation",
        "22",
        "--head-ref",
        "m",
        "--pr-number",
        "3",
        expect_exit=0,
    )
    assert "Dispatched watchdog generation 22" in old[2]


def test_defect_c_a_zero_padded_generation_skips_the_cap_entirely(
    bindir: pathlib.Path,
) -> None:
    """`08` is invalid octal, the arithmetic aborts, and the run PROCEEDS."""
    assert port.OCTAL_CAP is True
    old, new = run_both(
        bindir, "--run-id", "1", "--generation", "08", "--head-ref", "m", "--pr-number", "3"
    )
    assert old[0] == new[0] == 0
    assert 'value too great for base (error token is "08")' in old[2], (
        "the twin no longer emits the arithmetic error; the normalisation is now a lie"
    )
    assert strip_bash_arith(old[2]) == new[2]
    assert "✓ Dispatched watchdog generation 08 for run 1 on ref m\n" in new[2]


def test_defect_c_a_zero_padded_generation_is_read_in_octal(
    bindir: pathlib.Path,
) -> None:
    """`025` is 21 and dispatches; `030` is 24 and ends the chain."""
    old = assert_identical(
        bindir,
        "--run-id",
        "1",
        "--generation",
        "025",
        "--head-ref",
        "m",
        "--pr-number",
        "3",
        expect_exit=0,
    )
    assert "Dispatched watchdog generation 025" in old[2]
    old = assert_identical(bindir, "--run-id", "1", "--generation", "030", expect_exit=0)
    assert "Generation 030 exceeds cap 22" in old[2]


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


def test_gh_missing_is_refused_before_anything_else(
    bindir: pathlib.Path, nogh: pathlib.Path
) -> None:
    old, new = run_both(bindir, "--run-id", "1", "--generation", "1", path=str(nogh))
    assert old[0] == new[0] == 1
    assert old[2] == "✗ Required command 'gh' is not available\n"
    assert new[2] == old[2]
    assert new[1] == old[1] == ""


def test_gh_is_required_even_for_an_argument_error(
    bindir: pathlib.Path, nogh: pathlib.Path
) -> None:
    """`require_cmd gh` runs BEFORE the parser, so a typo reports the tool."""
    old, new = run_both(bindir, "--nope", path=str(nogh))
    assert old[2] == new[2] == "✗ Required command 'gh' is not available\n"


def test_an_unknown_option_exits_1(bindir: pathlib.Path) -> None:
    old = assert_identical(bindir, "--nope", expect_exit=1)
    assert old[1] == ""
    assert old[2] == "✗ Unknown option: --nope\n"


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        ((), port.MISSING_RUN_ID),
        (("--generation", "1"), port.MISSING_RUN_ID),
        (("--run-id", "1"), port.MISSING_GENERATION),
    ],
)
def test_a_missing_required_value_exits_1(
    bindir: pathlib.Path, args: tuple[str, ...], expected: str
) -> None:
    """Divergence 2: bash's `${VAR:?}` names a line of the twin; this names it."""
    old, new = run_both(bindir, *args)
    assert old[0] == new[0] == 1
    assert old[1] == new[1] == ""
    assert expected.split(": ", 1)[1] in old[2]
    assert new[2] == expected + "\n"


def test_a_missing_github_repository_exits_1(bindir: pathlib.Path) -> None:
    old, new = run_both(
        bindir, "--run-id", "1", "--generation", "1", env_extra={"GITHUB_REPOSITORY": ""}
    )
    assert old[0] == new[0] == 1
    assert "GITHUB_REPOSITORY is required" in old[2]
    assert new[2] == port.MISSING_REPOSITORY + "\n"


@pytest.mark.parametrize("bad", ["x", "1a", "", " 1", "1 ", "1.0", "-1"])
def test_a_non_numeric_run_id_is_refused(bindir: pathlib.Path, bad: str) -> None:
    old, new = run_both(bindir, "--run-id", bad, "--generation", "1")
    assert old[0] == new[0] == 1
    if bad == "":
        # The `:?` guard fires first for an empty value, before the regex.
        assert "--run-id is required" in old[2]
    else:
        assert old[2] == "✗ --run-id must be numeric, got: %s\n" % bad
        assert new[2] == old[2]


@pytest.mark.parametrize("bad", ["x", "1a", "2.5"])
def test_a_non_numeric_generation_is_refused(bindir: pathlib.Path, bad: str) -> None:
    old = assert_identical(bindir, "--run-id", "1", "--generation", bad, expect_exit=1)
    assert old[2] == "✗ --generation must be numeric, got: %s\n" % bad


def test_a_trailing_newline_does_not_satisfy_the_numeric_anchor(
    bindir: pathlib.Path,
) -> None:
    """bash's `=~ ^[0-9]+$` rejects `1\\n`; a Python `$` would accept it."""
    old = assert_identical(bindir, "--run-id", "1\n", "--generation", "1", expect_exit=1)
    assert "must be numeric" in old[2]


@pytest.mark.parametrize("bad", ["maybe", "TRUE", "1", "yes"])
def test_a_bad_pending_rerun_is_refused(bindir: pathlib.Path, bad: str) -> None:
    old = assert_identical(
        bindir, "--run-id", "1", "--generation", "1", "--pending-rerun", bad, expect_exit=1
    )
    assert old[2] == "✗ --pending-rerun must be true or false, got: %s\n" % bad


def test_an_empty_pending_rerun_is_accepted_as_false(bindir: pathlib.Path) -> None:
    """`${2:-false}` defaults on UNSET **or empty**, so `''` is not a refusal.

    The one-character difference between `:-` and `-` decides this, and a port that read `argv[i + 1]` straight would refuse an input the twin accepts.
    """
    old = assert_identical(
        bindir,
        "--run-id",
        "1",
        "--generation",
        "1",
        "--head-ref",
        "m",
        "--pr-number",
        "3",
        "--pending-rerun",
        "",
        expect_exit=1,
        env_extra={"FAKE_GH_RUN_RC": "1"},
    )
    assert "-f pending_rerun=false" in old[2]


def test_pending_rerun_true_reaches_the_dispatch(bindir: pathlib.Path) -> None:
    old = assert_identical(
        bindir,
        "--run-id",
        "1",
        "--generation",
        "1",
        "--head-ref",
        "m",
        "--pr-number",
        "3",
        "--pending-rerun",
        "true",
        expect_exit=1,
        env_extra={"FAKE_GH_RUN_RC": "1"},
    )
    assert "-f pending_rerun=true" in old[2]


def test_defect_e_pending_rerun_as_the_last_token_exits_1_in_total_silence(
    bindir: pathlib.Path,
) -> None:
    """Zero bytes on BOTH streams. `shift 2` with one argument left, under set -e."""
    old = assert_identical(
        bindir,
        "--run-id",
        "1",
        "--generation",
        "1",
        "--head-ref",
        "m",
        "--pending-rerun",
        expect_exit=1,
    )
    assert old[1] == ""
    assert old[2] == ""


@pytest.mark.parametrize("opt", ["--run-id", "--generation", "--pr-number", "--head-ref"])
def test_defect_e_a_value_option_as_the_last_token_dies_as_bash(
    bindir: pathlib.Path, opt: str
) -> None:
    """Divergence 3: `$2: unbound variable` versus MISSING_VALUE."""
    old, new = run_both(bindir, opt)
    assert old[0] == new[0] == 1
    assert old[1] == new[1] == ""
    assert "$2: unbound variable" in old[2]
    assert new[2] == (port.MISSING_VALUE % opt) + "\n"


def test_defect_f_a_failed_head_ref_lookup_ends_the_run_with_no_message(
    bindir: pathlib.Path,
) -> None:
    """Only gh's own stderr explains it, while the NEXT lookup fails open."""
    old = assert_identical(
        bindir,
        "--run-id",
        "1",
        "--generation",
        "1",
        "--pr-number",
        "3",
        expect_exit=4,
        env_extra={"FAKE_GH_API_RC": "4", "FAKE_GH_API_STDERR": "api boom"},
    )
    assert old[1] == ""
    assert old[2] == (
        'call: gh api repos/rediacc/console/actions/runs/1 --jq .head_branch // ""\napi boom\n'
    )
    assert "✗" not in old[2]
    assert "⚠" not in old[2]


# --------------------------------------------------------------------------- Colour, and the pinned constants ---------------------------------------------------------------------------


def test_colour_on_a_terminal_is_byte_identical(bindir: pathlib.Path) -> None:
    old, new = run_both(bindir, "--nope", tty="stderr")
    assert old[0] == new[0] == 1
    assert diff.escape_bytes(old[2]) > 0, "the twin printed no colour on a tty"
    assert new[2] == old[2]


def test_the_warn_glyph_is_byte_identical_on_a_terminal(bindir: pathlib.Path) -> None:
    old, new = run_both(bindir, "--run-id", "1", "--generation", "99", tty="stderr")
    assert old[0] == new[0] == 0
    assert diff.escape_bytes(old[2]) > 0
    assert new[2] == old[2]


def test_no_color_suppresses_colour_on_both_sides(bindir: pathlib.Path) -> None:
    old, new = run_both(bindir, "--nope", tty="stderr", env_extra={"NO_COLOR": "1"})
    assert diff.escape_bytes(old[2]) == 0
    assert new[2] == old[2]


def test_the_cap_and_the_404_pattern_are_the_twins() -> None:
    with open("%s/%s" % (diff.repo(), TWIN), encoding="utf-8") as fh:
        text = fh.read()
    assert "MAX_GENERATIONS=%d" % port.MAX_GENERATIONS in text
    assert 'grep -qE "%s"' % port.BOOTSTRAP_404.pattern in text


def test_the_dispatch_arguments_are_the_twins_in_order() -> None:
    """A reordered `-f` list would still dispatch, and still be a different call."""
    with open("%s/%s" % (diff.repo(), TWIN), encoding="utf-8") as fh:
        text = fh.read()
    for field in (
        "target_run_id=${RUN_ID}",
        "generation=${GENERATION}",
        "pr_number=${PR_NUMBER}",
        "head_ref=${HEAD_REF}",
        "pending_rerun=${PENDING_RERUN}",
    ):
        assert '-f "%s"' % field in text


def test_the_parser_accepts_every_option_the_twin_accepts() -> None:
    with open("%s/%s" % (diff.repo(), TWIN), encoding="utf-8") as fh:
        text = fh.read()
    for opt in (*port.VALUE_OPTIONS, "--pending-rerun"):
        assert "        %s)" % opt in text


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

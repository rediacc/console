"""`rediacc_ci.security.autopilot_workflow_invariants`, driven against the bytes its bash twin printed.

THE TWIN HAS BEEN DELETED. While both copies existed this file ran `.ci/scripts/security/check-autopilot-workflow-invariants.sh` and the port over the same workflow and compared exit code, stdout and stderr byte for byte, with exactly one exemption. The ledger `.ci/shadow/w7p6-check-autopilot-workflow-invariants.observations.jsonl` holds 5 rows of that comparison.

Every fixture case now compares against `goldens/autopilot-workflow-invariants/`, which holds the twin's OWN recorded bytes, captured on its last day in the tree, and each golden's provenance header carries the blob sha, so `git cat-file -p <sha>` still yields the program that printed them.

WHICH CASES ARE RECORDED, AND WHICH ARE DELIBERATELY NOT. Every case driving a SYNTHETIC fixture has a golden, because its input is a constant in this file and its output is reproducible for as long as that constant is. THREE CASES DRIVE THE REAL `.github/workflows/autopilot.yml` and have none, and must not: those bytes are a function of a live tracked file that legitimately
changes, so freezing them would bake today's workflow into a golden and red this suite on the next unrelated workflow edit. All three survive as port-only assertions about the real tree, which is what they were really claiming: the live file is green and its job count is in the verdict, an empty `WORKFLOW_FILE` falls back to it, and a seeded mutation sweep over it produces both
reds and greens without the subject ever crashing.

TWO STREAMS AND NOTHING ELSE, which is the whole observable surface. The subject reads one file and writes a verdict; it creates nothing and touches no remote.

NO FAKES, AND THAT WAS MEASURED. The twin shelled out to `awk` (three separate programs) and `grep`, and to nothing else:

    $ grep -nE '(^|[^a-z-])(yq|jq|gh|curl|wget|docker|git) ' \\
        .ci/scripts/security/check-autopilot-workflow-invariants.sh
    (no output)

Both are transcribed into the port, so there was nothing to record and no scratch PATH to build.

THE INVARIANTS ARE ABOUT TEXT, NOT ABOUT A PARSE TREE, which is why the port walks lines instead of loading YAML: `wall4-comment-missing` is a claim about a COMMENT, `trusted-checkout-not-first` is a claim about the ORDER of two steps, and `model-round-file-tools` is a claim about the contents of a block SCALAR. None of the three survives `yaml.safe_load`.

WHY A BASELINE-GREEN FIXTURE EXISTS. Without it a case asserting exit 1 proves nothing, because the fixture might have been red for a reason the case did not plant. `the-baseline-fixture` is the recording every other fixture case leans on, and it doubles as the NEGATIVE direction of the selftest.

ONE CASE IS COMPARED BY SHAPE, and it pins a real non-determinism rather than pretending it away. `for (j in first_token)` IS UNORDERED IN AWK: gawk answers in internal hash order, which is reproducible only from inside gawk, while the port emits in insertion order. The two therefore print the SAME SET of findings in a different sequence, and only when two or more jobs violate the
same invariant. Every real violation is a single job and the real workflow has none, so the divergence is unreachable in practice and recorded rather than smoothed over.

WHAT IS MASKED, and it is two paths. The case's temporary directory holds the fixture whose name the subject quotes in its messages, and it is rebuilt under a different name every run, so it becomes `<work>`; the checkout root becomes `<repo>`, so a golden cannot quietly acquire this worktree's spelling. Nothing else is touched.

THE CONTROL IS A WRAPPER PLANT that imports the tracked module and replaces one exported function in its own process, rather than editing a copy of the file. The mutation is the removal of one finding KIND, which is a change to a return value rather than to a line of text, and the file on disk is never written to at all.
"""

from __future__ import annotations

import random
import subprocess
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.security import autopilot_workflow_invariants as awi
from rediacc_ci.tests import differential, frozen

if typing.TYPE_CHECKING:  # pragma: no cover - annotations only
    import pathlib

ROOT = paths.repo_root()
PORT = ROOT / ".ci/rediacc_ci/security/autopilot_workflow_invariants.py"
REAL = ROOT / ".github/workflows/autopilot.yml"
SLUG = "autopilot-workflow-invariants"

BASH = "/bin/bash"
PYTHON = "python3"

# A workflow that satisfies every invariant. Every red case below is this file
# with ONE thing broken, so the diff between a case and this constant is exactly
# the defect under test.
BASELINE = """name: autopilot
concurrency:
  group: autopilot
  cancel-in-progress: false
on:
  workflow_run:
    workflows: [ci]
jobs:
  gate:
    runs-on: ubuntu-latest
    steps:
      # WALL 4: on workflow_run the action's .claude/ restore never fires while
      # .claude/hooks/** still execute, so the FIRST checkout must be trusted.
      - uses: actions/checkout@v4
        with:
          repository: rediacc/console
          ref: main
          persist-credentials: false
      - name: Decide
        run: |
          echo deciding
  model:
    needs: gate
    if: >-
      needs.gate.outputs.mode == 'run'
      && env.AUTOPILOT_ALLOW_STATE == 'true'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          repository: rediacc/console
          ref: main
          persist-credentials: false
          submodules: false
      - name: Model round
        uses: anthropics/claude-code-action@v1
        with:
          track_progress: false
          settings: |
            {
              "permissions": {
                "allow": ["Edit", "Write", "Read", "Bash"]
              }
            }
      - uses: ./.github/actions/app-token
        id: token
      - name: Push
        run: |
          echo pushing
"""

# Three jobs, two of which violate the same token invariant, which is the only shape that reaches the awk ordering divergence.
MULTI_JOB_FIXTURE = """name: multi
on: push
jobs:
  zeta:
    steps:
      - uses: ./.github/actions/app-token
      - uses: anthropics/claude-code-action@v1
  alpha:
    steps:
      - uses: ./.github/actions/app-token
      - uses: anthropics/claude-code-action@v1
  gate:
    steps:
      - uses: ./.github/actions/app-token
"""


def mutate(original: str, before: str, after: str, count: int = 1) -> str:
    """`str.replace` that REFUSES to be a no-op.

    A red case whose substitution silently missed still runs, still compares two identical outputs, and still passes, while asserting nothing. This is the control for the control.
    """
    out = original.replace(before, after, count)
    assert out != original, "the substitution %r -> %r matched nothing" % (before, after)
    return out


def broken(before: str, after: str, count: int = 1) -> str:
    return mutate(BASELINE, before, after, count)


# name -> the fixture body (None means the file is never written), plus the flags for the cases that need bytes or a terminal
CASE_KW: dict[str, dict[str, typing.Any]] = {
    "the-baseline-fixture": {"body": BASELINE},
    "a-missing-workflow-file": {"body": None},
    "a-file-with-no-jobs-at-all": {"body": "name: nothing\non: push\n"},
    "a-checkout-without-persist-credentials": {
        "body": broken(
            "          persist-credentials: false\n          submodules: false\n",
            "          submodules: false\n",
        )
    },
    "a-first-checkout-that-is-not-trusted": {
        "body": broken("          repository: rediacc/console\n          ref: main\n", "")
    },
    "a-trusted-checkout-on-the-wrong-ref": {
        "body": broken("          ref: main\n", "          ref: main-next\n")
    },
    "event-payload-in-a-run-block": {
        "body": broken(
            "          echo deciding\n", "          echo ${{ github.event.comment.body }}\n"
        )
    },
    "event-payload-outside-a-run-block": {
        "body": broken(
            "      - name: Decide\n",
            "      - name: Decide\n        env:\n          BODY: ${{ github.event.comment.body }}\n",
        )
    },
    "a-commented-out-violation": {
        "body": broken(
            "          echo deciding\n",
            "          echo deciding\n          # ${{ github.event.comment.body }}\n",
        )
    },
    "an-app-token-in-the-gate-job": {
        "body": broken(
            "      - name: Decide\n",
            "      - uses: ./.github/actions/app-token\n      - name: Decide\n",
        )
    },
    "an-app-token-before-the-model-step": {
        "body": broken(
            "      - name: Model round\n",
            "      - uses: ./.github/actions/app-token\n      - name: Model round\n",
        )
    },
    "track-progress-armed": {"body": broken("track_progress: false", "track_progress: true")},
    "a-quoted-track-progress-false": {
        "body": broken("track_progress: false", "track_progress: 'false'")
    },
    "cancel-in-progress-armed": {
        "body": broken("cancel-in-progress: false", "cancel-in-progress: true")
    },
    "a-pre-model-checkout-with-submodules": {
        "body": broken("          submodules: false\n", "          submodules: recursive\n")
    },
    "the-wall4-comment-removed": {"body": broken("WALL 4", "WALL FOUR")},
    "a-model-if-without-the-state-flag": {
        "body": broken("&& env.AUTOPILOT_ALLOW_STATE == 'true'", "&& env.OTHER == 'true'")
    },
    "a-model-job-with-no-job-level-if": {
        "body": broken(
            "    if: >-\n      needs.gate.outputs.mode == 'run'\n"
            "      && env.AUTOPILOT_ALLOW_STATE == 'true'\n",
            "",
        )
    },
    "the-state-flag-only-in-a-step": {
        "body": mutate(
            broken(
                "    if: >-\n      needs.gate.outputs.mode == 'run'\n"
                "      && env.AUTOPILOT_ALLOW_STATE == 'true'\n",
                "    if: needs.gate.outputs.mode == 'run'\n",
            ),
            "      - name: Push\n",
            "      - name: Push\n        if: env.AUTOPILOT_ALLOW_STATE == 'true'\n",
        )
    },
    "an-allowlist-missing-a-tool": {"body": broken('"Edit", ', "")},
    "a-tool-named-outside-the-settings-block": {
        "body": mutate(
            broken('"Edit", ', ""),
            "      - name: Push\n",
            '      # "Edit" is mentioned here\n      - name: Push\n',
        )
    },
    "an-unlocatable-settings-block": {
        "body": broken("      - name: Model round\n", "      - name: Model turn\n")
    },
    "crlf-line-endings": {"raw": BASELINE.replace("\n", "\r\n").encode("utf-8")},
    "no-trailing-newline": {"body": BASELINE.rstrip("\n")},
    "colour-on-a-terminal": {
        "body": broken("track_progress: false", "track_progress: true"),
        "tty": True,
    },
    "two-jobs-that-take-a-token": {"body": MULTI_JOB_FIXTURE},
}

CASES = tuple(CASE_KW)

# The one case that reaches awk's unordered iteration. Compared by shape, in its own test.
DIVERGENT = ("two-jobs-that-take-a-token",)


def env_for(**extra: str) -> dict[str, str]:
    """REPLACES the caller's environment; see `differential.BASE_ENV`.

    `REDIACC_CI_ROOT` is deliberately absent: it is the one seam the port has and the twin did not.
    """
    env = differential.env_for(PYTHONPATH=str(ROOT / ".ci"), PYTHONDONTWRITEBYTECODE="1")
    env.update(extra)
    return env


def run(subject: pathlib.Path, tmp_path: pathlib.Path, name: str) -> tuple[int, str, str]:
    """One subject, once, over this case's own fixture."""
    kw = CASE_KW[name]
    tmp_path.mkdir(parents=True, exist_ok=True)
    workflow = tmp_path / "wf.yml"
    if kw.get("raw") is not None:
        workflow.write_bytes(kw["raw"])
    elif kw.get("body") is not None:
        workflow.write_text(kw["body"], encoding="utf-8")
    env = env_for(WORKFLOW_FILE=str(workflow))

    def mask(text: str) -> str:
        return text.replace(str(tmp_path), "<work>").replace(str(ROOT), "<repo>")

    if kw.get("tty"):
        # `[[ -t 2 ]] && [[ -z "${NO_COLOR:-}" ]]` (common.sh:18), the branch a human sees. Off a tty every other case proves only the uncoloured half. `CI` is left UNSET: `rediacc_ci.log` also disables colour on `CI=true` and common.sh did not, which is `log.py`'s documented deliberate divergence and is not this gate's subject.
        code, out, err = differential.bash_streams(
            "%s %s" % ("bash" if subject.suffix == ".sh" else PYTHON, subject),
            env=env,
            cwd=str(ROOT),
            tty="stderr",
        )
        return code, mask(out), mask(err)

    proc = subprocess.run(
        [BASH if subject.suffix == ".sh" else PYTHON, str(subject)],
        env=env,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
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


def assert_red(result: tuple[int, str, str], token: str) -> None:
    """Anti-vacuity for one recording: the twin really did fail, for the reason meant."""
    assert result[0] == 1, "expected the twin to fail, got exit %s\n%s" % (result[0], result[2])
    assert token in result[2], "expected %r in the recorded stderr, got:\n%s" % (token, result[2])


@pytest.mark.parametrize("name", [c for c in CASES if c not in DIVERGENT])
def test_port_matches_the_twins_recorded_output(tmp_path: pathlib.Path, name: str) -> None:
    compare(tmp_path, name)


def test_every_case_has_a_golden_and_no_golden_is_orphaned() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, set(CASES))


# --------------------------------------------------------------------------- The real repository, deliberately NOT recorded ---------------------------------------------------------------------------


def drive_real(**extra: str) -> tuple[int, str, str]:
    proc = subprocess.run(
        [PYTHON, str(PORT)],
        env=env_for(**extra),
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    return proc.returncode, proc.stdout, proc.stderr


def test_the_real_workflow_is_green_under_the_port() -> None:
    """The clean-tree case, over the real `.github/workflows/autopilot.yml`.

    NOT A GOLDEN, and that is the point: the real file legitimately changes, so freezing its bytes would red this suite on the next unrelated workflow edit. The job COUNT is asserted from the verdict line rather than the whole line, so a scan that collapsed to zero jobs is still visible here while a new job is not a failure.
    """
    code, _, stderr = drive_real()
    assert code == 0, "the real autopilot.yml is not green:\n%s" % stderr
    assert "autopilot workflow invariants hold:" in stderr
    scanned = stderr.split("autopilot workflow invariants hold:", 1)[1].split("jobs scanned", 1)[0]
    assert int(scanned.strip()) >= 5, "the scan collapsed to %r jobs" % scanned.strip()


def test_an_empty_workflow_file_variable_falls_back_to_the_real_default() -> None:
    """`${WORKFLOW_FILE:-...}` is an empty-OR-unset default.

    `os.environ.get(name, default)` would resolve an exported-empty value to `""` and then report a missing workflow; this is the case that holds that trap shut. Not recorded for the same reason as the case above: the fallback IS the real workflow.
    """
    code, _, stderr = drive_real(WORKFLOW_FILE="")
    assert code == 0, stderr
    assert "autopilot workflow invariants hold:" in stderr


def test_a_deterministic_mutation_sweep_of_the_real_workflow(tmp_path: pathlib.Path) -> None:
    """Twenty seeded mutations of the real file, driven through the port.

    The hand-written cases each aim at ONE rule and therefore only ever exercise the shapes their author thought of. This sweep is the part that catches an interaction, a dedent that ends a pending checkout at the same line a run block closes, or a step marker inside a with-block, and it is seeded so a failure is reproducible rather than a flake.

    NOT RECORDED, because its input is the live workflow. What survives is the anti-vacuity that was always the point: the sweep must produce at least one red and at least one green, and the subject must never crash, which is any exit other than 0 or 1.
    """
    source = REAL.read_text(encoding="utf-8").split("\n")
    rng = random.Random(20260914)  # noqa: S311 - fixture generation, not a security draw
    injections = [
        "      - uses: actions/checkout@v4",
        "        with:",
        "          submodules: recursive",
        "      - uses: ./.github/actions/app-token",
        "      - uses: anthropics/claude-code-action@v1",
        "          track_progress: true",
        "  cancel-in-progress: true",
        "  extra-job:",
        "        run: |",
        "          echo ${{ github.event.comment.body }}",
        "    if: env.AUTOPILOT_ALLOW_STATE == 'yes'",
    ]
    reds = greens = 0
    for index in range(20):
        lines = list(source)
        for _ in range(rng.randint(1, 3)):
            operation = rng.choice(["delete", "duplicate", "blank", "insert", "dedent"])
            at = rng.randrange(len(lines))
            if operation == "delete":
                del lines[at]
            elif operation == "duplicate":
                lines.insert(at, lines[at])
            elif operation == "blank":
                lines[at] = ""
            elif operation == "dedent":
                lines[at] = lines[at].lstrip(" ")
            else:
                lines.insert(at, rng.choice(injections))
        path = tmp_path / ("sweep_%02d.yml" % index)
        path.write_text("\n".join(lines), encoding="utf-8")
        proc = subprocess.run(
            [PYTHON, str(PORT)],
            env=env_for(WORKFLOW_FILE=str(path)),
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        assert proc.returncode in (0, 1), "mutation %d crashed the subject:\n%s" % (
            index,
            proc.stderr,
        )
        if proc.returncode == 0:
            greens += 1
        else:
            reds += 1
    assert reds > 0, "the sweep produced no failing workflow; it proved only the green branch"
    assert greens > 0, "the sweep produced no passing workflow; it proved only the red branch"


# --------------------------------------------------------------------------- What the recordings say ---------------------------------------------------------------------------


def test_the_baseline_fixture_is_green() -> None:
    """THE CONTROL FOR EVERY OTHER FIXTURE CASE, and the NEGATIVE selftest direction."""
    code, _, stderr = recorded("the-baseline-fixture")
    assert code == 0, "the baseline fixture is not green:\n%s" % stderr
    assert "2 jobs scanned" in stderr


def test_a_missing_workflow_file_is_never_green() -> None:
    assert_red(recorded("a-missing-workflow-file"), "workflow-missing: no file at")


def test_a_file_with_no_jobs_at_all_is_a_blind_scan() -> None:
    """`length(seen_checkout) == 0`, the vacuity refusal."""
    assert_red(recorded("a-file-with-no-jobs-at-all"), "workflow-missing: no jobs parsed from")


def test_the_checkout_family() -> None:
    """Three claims about the FIRST checkout, each planted on its own: it keeps no credentials, it names the trusted repository and ref, and `main-next` is not main. The regex is anchored at end of line, which is what the wrong-ref case proves."""
    assert_red(recorded("a-checkout-without-persist-credentials"), "persist-credentials:")
    assert_red(recorded("a-first-checkout-that-is-not-trusted"), "trusted-checkout-not-first:")
    assert_red(recorded("a-trusted-checkout-on-the-wrong-ref"), "trusted-checkout-not-first:")


def test_event_payload_interpolated_into_a_run_block() -> None:
    assert_red(recorded("event-payload-in-a-run-block"), "event-interpolation-in-run:")


def test_event_payload_outside_a_run_block_is_not_a_finding() -> None:
    """The POSITIVE control's twin: `in_run` really is scoped.

    `github.event.` in an `env:` value is the SUPPORTED way to carry untrusted payload text, so a port that dropped the `in_run` condition would flag the correct pattern. Nothing else in this file exercises that.
    """
    code, _, stderr = recorded("event-payload-outside-a-run-block")
    assert code == 0, "an env: interpolation should be allowed:\n%s" % stderr


def test_a_commented_out_violation_is_not_a_finding() -> None:
    """`is_comment` gates almost every rule; without it a comment is a violation."""
    code, _, stderr = recorded("a-commented-out-violation")
    assert code == 0, "a commented line should not be a finding:\n%s" % stderr


def test_the_app_token_family() -> None:
    """The token must reach neither the gate job nor any step before the model step, which is what keeps a write credential out of the blast radius of untrusted input."""
    assert_red(recorded("an-app-token-in-the-gate-job"), "token-in-gate:")
    assert_red(recorded("an-app-token-before-the-model-step"), "token-before-model:")


def test_track_progress_and_cancel_in_progress() -> None:
    """Both armed switches, plus the quoted spelling the twin tolerated."""
    assert_red(recorded("track-progress-armed"), "track-progress-armed:")
    assert_red(recorded("cancel-in-progress-armed"), "cancel-in-progress-armed:")
    code, _, stderr = recorded("a-quoted-track-progress-false")
    assert code == 0, "a quoted false should be accepted:\n%s" % stderr


def test_a_pre_model_checkout_asking_for_submodules() -> None:
    assert_red(recorded("a-pre-model-checkout-with-submodules"), "submodule-checkout-pre-model:")


def test_the_wall4_comment_removed() -> None:
    assert_red(recorded("the-wall4-comment-removed"), "wall4-comment-missing:")


def test_the_model_job_guard() -> None:
    """Three shapes of the same claim: the flag missing from the job's `if:`, no job-level `if:` at all (the anti-vacuity arm, since an unfindable guard must not read as green), and the flag present only in a STEP.

    The last one is the substitute the twin's header says it must not accept: a whole-file grep for AUTOPILOT_ALLOW_STATE would pass on the state-write step that already mentions the flag, and the extraction is scoped to the model job's own `if:` precisely so it does not.
    """
    assert_red(
        recorded("a-model-if-without-the-state-flag"),
        "the model job's if: does not require AUTOPILOT_ALLOW_STATE",
    )
    assert_red(
        recorded("a-model-job-with-no-job-level-if"), "no job-level 'if:' found for the model job"
    )
    assert_red(
        recorded("the-state-flag-only-in-a-step"),
        "the model job's if: does not require AUTOPILOT_ALLOW_STATE",
    )


def test_the_settings_block_family() -> None:
    """The allowlist is read from the Model round step's own block scalar, not from the file: a mention three steps away must not satisfy it, and a step whose name moved makes the block unlocatable rather than empty."""
    assert_red(recorded("an-allowlist-missing-a-tool"), 'permission allowlist omits "Edit"')
    assert_red(
        recorded("a-tool-named-outside-the-settings-block"), 'permission allowlist omits "Edit"'
    )
    assert_red(
        recorded("an-unlocatable-settings-block"), "could not locate the Model round settings block"
    )


def test_line_ending_and_terminator_handling() -> None:
    """A CRLF file must produce the same verdict as an LF one, or a Windows-edited workflow silently changes what the gate sees. And awk yields N records for N lines whether or not the last one is terminated, while `text.split("\\n")` yields N+1 when it IS terminated; getting that wrong shifts every line NUMBER in every finding."""
    assert recorded("crlf-line-endings")[0] == 0
    assert recorded("no-trailing-newline")[0] == 0


def test_colour_is_emitted_when_stderr_is_a_terminal() -> None:
    stderr = recorded("colour-on-a-terminal")[2]
    assert differential.escape_bytes(stderr) > 0, "the twin printed no colour on a tty"
    assert "track-progress-armed" in stderr


# --------------------------------------------------------------------------- The one divergence, pinned rather than papered over ---------------------------------------------------------------------------


def test_two_token_jobs_disagree_only_on_order(tmp_path: pathlib.Path) -> None:
    """`for (j in first_token)` IS UNORDERED IN AWK. Pinned, not papered over.

    This asserts three things at once: the sets match, the exit codes match, and the twin's recorded order really is neither insertion nor sorted, the last one so that a port whose iteration became insertion-ordered by accident cannot quietly agree for the wrong reason.
    """
    name = "two-jobs-that-take-a-token"
    want = recorded(name)
    got = port(tmp_path, name)
    assert want[0] == got[0] == 1
    assert want[1] == got[1] == ""

    # Scoped to `INVARIANT-FAIL: token`, not to `token`: the settings-block and state-guard failures this synthetic file also raises mention the word, and the first version of this case counted six findings where it meant three.
    def token_findings(text: str) -> list[str]:
        return [line for line in text.split("\n") if "INVARIANT-FAIL: token" in line]

    want_lines = token_findings(want[2])
    got_lines = token_findings(got[2])
    assert len(want_lines) == 3, "expected three token findings, got:\n%s" % want[2]
    assert sorted(want_lines) == sorted(got_lines)
    assert sorted(want[2].split("\n")) == sorted(got[2].split("\n"))
    # The divergence itself, stated as an assertion so it cannot rot silently.
    assert want_lines != got_lines, (
        "the recorded order and the port's now agree; the documented divergence "
        "is obsolete and this test, the module docstring and the port's own note "
        "should all be removed together"
    )


# --------------------------------------------------------------------------- The exported helpers, driven directly (the selftest half) ---------------------------------------------------------------------------


def test_walk_reports_nothing_but_the_scan_count_on_a_conformant_file() -> None:
    """The NEGATIVE direction. A gate with only positive controls flags the tree."""
    assert awi.walk(BASELINE) == [("scanned-jobs", "0", "2")]


def test_walk_fires_on_a_planted_violation() -> None:
    """The POSITIVE direction, in-process, with the line number asserted."""
    body = BASELINE.replace("track_progress: false", "track_progress: true")
    kinds = [(kind, where) for kind, _line, where in awi.walk(body) if kind != "scanned-jobs"]
    assert kinds == [("track-progress-armed", "model/- name: Model round")]


def test_records_drops_only_the_terminating_newline() -> None:
    assert awi.records("a\nb\n") == ["a", "b"]
    assert awi.records("a\nb") == ["a", "b"]
    assert awi.records("") == []
    assert awi.records("\n") == [""]
    # NOT splitlines: a form feed is not a record separator for awk.
    assert awi.records("a\x0cb\n") == ["a\x0cb"]


def test_model_if_block_stops_at_the_next_job() -> None:
    block = awi.model_if_block(BASELINE)
    assert block == [
        "    if: >-",
        "      needs.gate.outputs.mode == 'run'",
        "      && env.AUTOPILOT_ALLOW_STATE == 'true'",
    ]


def test_model_settings_block_is_scoped_to_the_model_round_step() -> None:
    block = awi.model_settings_block(BASELINE)
    assert block
    assert all(line.startswith("          ") for line in block)
    assert any('"Edit"' in line for line in block)
    assert not any("app-token" in line for line in block)


def test_required_tools_is_the_real_list() -> None:
    """The constant is load-bearing, so it is asserted rather than trusted."""
    assert awi.REQUIRED_TOOLS == ('"Edit"', '"Write"', '"Read"')


# --------------------------------------------------------------------------- The control: these goldens can actually fail ---------------------------------------------------------------------------


# A throwaway entry point that loads the real module, drops one finding KIND from `walk`, and runs `main`. See the control below.
PLANT = """import sys

from rediacc_ci.security import autopilot_workflow_invariants as subject

_real = subject.walk


def _blind_to_the_token_in_the_gate(text):
    return [finding for finding in _real(text) if finding[0] != "token-in-gate"]


subject.walk = _blind_to_the_token_in_the_gate
raise SystemExit(subject.main(sys.argv[1:]))
"""


def test_a_planted_blind_spot_is_caught(tmp_path: pathlib.Path) -> None:
    """THE CONTROL ON THE GOLDENS, aimed at the worst thing a security gate can do quietly.

    `token-in-gate` is the finding that says the app token is minted in the job that reads untrusted event payload, which is the blast radius wall this whole workflow is shaped around. A subject blind to it reports nothing and EXITS 0 on a workflow the recording says is red, so the comparison fails on the exit code and on stderr at once.

    THE PLANT IS A WRAPPER, NOT A COPY OF THE FILE. It imports the tracked module and replaces one exported function in its own process, which mutates a return value rather than a line of text and keeps the file on disk untouched.
    """
    original = PORT.read_text(encoding="utf-8")
    assert '"token-in-gate"' in original, "the plant's target moved"

    mutant = tmp_path / "plant" / "mutant.py"
    mutant.parent.mkdir(parents=True)
    mutant.write_text(PLANT, encoding="utf-8")

    name = "an-app-token-in-the-gate-job"
    want = recorded(name)
    assert want[0] == 1, "the recorded corpus moved"
    planted = run(mutant, tmp_path / "planted", name)
    assert planted[0] == 0, "the plant did not blind the subject"
    assert "token-in-gate" not in planted[2], "the finding survived the plant"
    assert planted != want

    compare(tmp_path / "good", name)
    assert PORT.read_text(encoding="utf-8") == original

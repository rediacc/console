"""Differential: `rediacc_ci.security.autopilot_workflow_invariants` against its
twin `.ci/scripts/security/check-autopilot-workflow-invariants.sh`.

THE COMPARISON IS BYTE FOR BYTE ON BOTH STREAMS, with exactly one exemption:
`test_two_token_jobs_disagree_only_on_order`, which pins the twin's `for (j in
array)` non-determinism rather than pretending it away. Every other case, the
real workflow included, is compared with nothing elided.

NO FAKES, AND THAT IS MEASURED. The twin shells out to `awk` (three separate
programs) and `grep`, and to nothing else:

    $ grep -nE '(^|[^a-z-])(yq|jq|gh|curl|wget|docker|git) ' \\
        .ci/scripts/security/check-autopilot-workflow-invariants.sh
    (no output)

Both of those are transcribed into the port, so there is nothing left to record
and no scratch PATH to build. Every case drives both sides over a FIXTURE
workflow through `$WORKFLOW_FILE` -- the seam the twin already exposes for its
own gate test -- and two cases drive both over the real
`.github/workflows/autopilot.yml`.

THE INVARIANTS ARE ABOUT TEXT, NOT ABOUT A PARSE TREE, which is why the port
walks lines instead of loading YAML: `wall4-comment-missing` is a claim about a
COMMENT, `trusted-checkout-not-first` is a claim about the ORDER of two steps,
and `model-round-file-tools` is a claim about the contents of a block SCALAR.
None of the three survives `yaml.safe_load`.

WHY A BASELINE-GREEN FIXTURE EXISTS. Without it a case asserting exit 1 proves
nothing, because the fixture might have been red for a reason the case did not
plant. `test_the_baseline_fixture_is_green` is the control every other fixture
case leans on, and it doubles as the NEGATIVE direction of the selftest.

K=5 LEDGER:
`.ci/shadow/w7p6-check-autopilot-workflow-invariants.observations.jsonl`.
"""

from __future__ import annotations

import random
import subprocess
import typing

from rediacc_ci import paths
from rediacc_ci.security import autopilot_workflow_invariants as port
from rediacc_ci.tests import differential

if typing.TYPE_CHECKING:  # pragma: no cover - annotations only
    import pathlib

ROOT = paths.repo_root()
TWIN = ROOT / ".ci/scripts/security/check-autopilot-workflow-invariants.sh"
PORT = ROOT / ".ci/rediacc_ci/security/autopilot_workflow_invariants.py"
REAL = ROOT / ".github/workflows/autopilot.yml"

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


def write(tmp_path: pathlib.Path, body: str, name: str = "wf.yml") -> pathlib.Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def _env(**extra: str) -> dict[str, str]:
    """REPLACES the caller's environment; see `differential.BASE_ENV`.

    `PYTHONPATH` is set for BOTH sides even though only the port needs it, so
    the two children differ in nothing but which program they run.
    `REDIACC_CI_ROOT` is deliberately absent: it is the one seam the port has
    and the twin does not.
    """
    env = differential.env_for(PYTHONPATH=str(ROOT / ".ci"), PYTHONDONTWRITEBYTECODE="1")
    env.update(extra)
    return env


def run_both(workflow: pathlib.Path | str | None = None) -> tuple[tuple, tuple]:
    extra = {} if workflow is None else {"WORKFLOW_FILE": str(workflow)}
    results = []
    for argv in (["bash", str(TWIN)], ["python3", str(PORT)]):
        proc = subprocess.run(
            argv,
            env=_env(**extra),
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        results.append((proc.returncode, proc.stdout, proc.stderr))
    return results[0], results[1]


def assert_same(old: tuple, new: tuple) -> None:
    assert new[0] == old[0], "exit: twin %s, port %s" % (old[0], new[0])
    assert new[1] == old[1], "stdout:\n--- twin\n%s--- port\n%s" % (old[1], new[1])
    assert new[2] == old[2], "stderr:\n--- twin\n%s--- port\n%s" % (old[2], new[2])


def assert_red(old: tuple, token: str) -> None:
    """Anti-vacuity for one case: the twin really did fail, for the reason meant."""
    assert old[0] == 1, "expected the twin to fail, got exit %s\n%s" % (old[0], old[2])
    assert token in old[2], "expected %r in the twin's stderr, got:\n%s" % (token, old[2])


def mutate(original: str, before: str, after: str, count: int = 1) -> str:
    """`str.replace` that REFUSES to be a no-op.

    A red case whose substitution silently missed still runs, still compares two
    identical outputs, and still passes -- while asserting nothing. This is the
    control for the control.
    """
    out = original.replace(before, after, count)
    assert out != original, "the substitution %r -> %r matched nothing" % (before, after)
    return out


# ---------------------------------------------------------------------------
# The real repository
# ---------------------------------------------------------------------------


def test_the_real_repository_agrees() -> None:
    """The clean-tree case, over the real `.github/workflows/autopilot.yml`.

    No fixture reproduces 5 jobs, their real checkout ordering and the real
    `settings: |` block at once, and a fixture cannot notice a rename landing in
    the real file.
    """
    old, new = run_both()
    assert_same(old, new)
    assert old[0] == 0, "the real autopilot.yml is not green:\n%s" % old[2]
    # SEEN the verdict, not matched two empty strings. The count is in the line,
    # so a scan that collapsed to zero jobs would be visible here.
    assert "autopilot workflow invariants hold: 5 jobs scanned" in old[2]


def test_an_empty_workflow_file_variable_falls_back_to_the_real_default() -> None:
    """`${WORKFLOW_FILE:-...}` is an empty-OR-unset default.

    `os.environ.get(name, default)` would resolve an exported-empty value to
    `""` and then report a missing workflow; this is the case that holds that
    trap shut.
    """
    results = []
    for argv in (["bash", str(TWIN)], ["python3", str(PORT)]):
        proc = subprocess.run(
            argv,
            env=_env(WORKFLOW_FILE=""),
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        results.append((proc.returncode, proc.stdout, proc.stderr))
    assert_same(results[0], results[1])
    assert results[0][0] == 0


# ---------------------------------------------------------------------------
# Fixtures, one invariant each
# ---------------------------------------------------------------------------


def test_the_baseline_fixture_is_green(tmp_path: pathlib.Path) -> None:
    """THE CONTROL FOR EVERY OTHER FIXTURE CASE, and the NEGATIVE selftest direction."""
    old, new = run_both(write(tmp_path, BASELINE))
    assert old[0] == 0, "the baseline fixture is not green:\n%s" % old[2]
    assert "2 jobs scanned" in old[2]
    assert_same(old, new)


def test_a_missing_workflow_file_is_never_green(tmp_path: pathlib.Path) -> None:
    old, new = run_both(tmp_path / "absent.yml")
    assert_red(old, "workflow-missing: no file at")
    assert_same(old, new)


def test_a_file_with_no_jobs_at_all_is_a_blind_scan(tmp_path: pathlib.Path) -> None:
    """`length(seen_checkout) == 0`, the vacuity refusal, plus its three companions."""
    old, new = run_both(write(tmp_path, "name: nothing\non: push\n"))
    assert_red(old, "workflow-missing: no jobs parsed from")
    assert_same(old, new)


def test_a_checkout_without_persist_credentials(tmp_path: pathlib.Path) -> None:
    body = mutate(
        BASELINE,
        "          persist-credentials: false\n          submodules: false\n",
        "          submodules: false\n",
    )
    old, new = run_both(write(tmp_path, body))
    assert_red(old, "persist-credentials:")
    assert_same(old, new)


def test_a_first_checkout_that_is_not_the_trusted_ref(tmp_path: pathlib.Path) -> None:
    body = mutate(BASELINE, "          repository: rediacc/console\n          ref: main\n", "", 1)
    old, new = run_both(write(tmp_path, body))
    assert_red(old, "trusted-checkout-not-first:")
    assert_same(old, new)


def test_a_trusted_checkout_on_the_wrong_ref(tmp_path: pathlib.Path) -> None:
    """`ref: main` must be the WHOLE value: `main-next` is not main.

    The regex is `ref:[[:space:]]*main[[:space:]]*$`, anchored at end of line,
    and this is the case that proves the anchor is carried.
    """
    body = mutate(BASELINE, "          ref: main\n", "          ref: main-next\n", 1)
    old, new = run_both(write(tmp_path, body))
    assert_red(old, "trusted-checkout-not-first:")
    assert_same(old, new)


def test_event_payload_interpolated_into_a_run_block(tmp_path: pathlib.Path) -> None:
    body = mutate(
        BASELINE, "          echo deciding\n", "          echo ${{ github.event.comment.body }}\n"
    )
    old, new = run_both(write(tmp_path, body))
    assert_red(old, "event-interpolation-in-run:")
    assert_same(old, new)


def test_event_payload_outside_a_run_block_is_not_a_finding(tmp_path: pathlib.Path) -> None:
    """The POSITIVE control's twin: `in_run` really is scoped.

    `github.event.` in an `env:` value is the SUPPORTED way to carry untrusted
    payload text, so a port that dropped the `in_run` condition would flag the
    correct pattern. Nothing else in this file exercises that.
    """
    body = mutate(
        BASELINE,
        "      - name: Decide\n",
        "      - name: Decide\n        env:\n          BODY: ${{ github.event.comment.body }}\n",
    )
    old, new = run_both(write(tmp_path, body))
    assert old[0] == 0, "an env: interpolation should be allowed:\n%s" % old[2]
    assert_same(old, new)


def test_a_commented_out_violation_is_not_a_finding(tmp_path: pathlib.Path) -> None:
    """`is_comment` gates almost every rule; without it a comment is a violation."""
    body = mutate(
        BASELINE,
        "          echo deciding\n",
        "          echo deciding\n          # ${{ github.event.comment.body }}\n",
    )
    old, new = run_both(write(tmp_path, body))
    assert old[0] == 0, "a commented line should not be a finding:\n%s" % old[2]
    assert_same(old, new)


def test_an_app_token_in_the_gate_job(tmp_path: pathlib.Path) -> None:
    body = mutate(
        BASELINE,
        "      - name: Decide\n",
        "      - uses: ./.github/actions/app-token\n      - name: Decide\n",
    )
    old, new = run_both(write(tmp_path, body))
    assert_red(old, "token-in-gate:")
    assert_same(old, new)


def test_an_app_token_before_the_model_step(tmp_path: pathlib.Path) -> None:
    body = mutate(
        BASELINE,
        "      - name: Model round\n",
        "      - uses: ./.github/actions/app-token\n      - name: Model round\n",
    )
    old, new = run_both(write(tmp_path, body))
    assert_red(old, "token-before-model:")
    assert_same(old, new)


def test_track_progress_armed(tmp_path: pathlib.Path) -> None:
    body = mutate(BASELINE, "track_progress: false", "track_progress: true")
    old, new = run_both(write(tmp_path, body))
    assert_red(old, "track-progress-armed:")
    assert_same(old, new)


def test_a_quoted_track_progress_false_is_accepted(tmp_path: pathlib.Path) -> None:
    """`.false.` -- the twin tolerates the quoted literal as well as the bare one."""
    body = mutate(BASELINE, "track_progress: false", "track_progress: 'false'")
    old, new = run_both(write(tmp_path, body))
    assert old[0] == 0, "a quoted false should be accepted:\n%s" % old[2]
    assert_same(old, new)


def test_cancel_in_progress_armed(tmp_path: pathlib.Path) -> None:
    body = mutate(BASELINE, "cancel-in-progress: false", "cancel-in-progress: true")
    old, new = run_both(write(tmp_path, body))
    assert_red(old, "cancel-in-progress-armed:")
    assert_same(old, new)


def test_a_pre_model_checkout_asking_for_submodules(tmp_path: pathlib.Path) -> None:
    body = mutate(BASELINE, "          submodules: false\n", "          submodules: recursive\n")
    old, new = run_both(write(tmp_path, body))
    assert_red(old, "submodule-checkout-pre-model:")
    assert_same(old, new)


def test_the_wall4_comment_removed(tmp_path: pathlib.Path) -> None:
    body = mutate(BASELINE, "WALL 4", "WALL FOUR")
    old, new = run_both(write(tmp_path, body))
    assert_red(old, "wall4-comment-missing:")
    assert_same(old, new)


def test_the_model_job_if_without_the_state_flag(tmp_path: pathlib.Path) -> None:
    body = mutate(BASELINE, "&& env.AUTOPILOT_ALLOW_STATE == 'true'", "&& env.OTHER == 'true'")
    old, new = run_both(write(tmp_path, body))
    assert_red(old, "the model job's if: does not require AUTOPILOT_ALLOW_STATE")
    assert_same(old, new)


def test_the_model_job_with_no_job_level_if_at_all(tmp_path: pathlib.Path) -> None:
    """The anti-vacuity arm: an unfindable guard must not read as green."""
    body = mutate(
        BASELINE,
        "    if: >-\n      needs.gate.outputs.mode == 'run'\n"
        "      && env.AUTOPILOT_ALLOW_STATE == 'true'\n",
        "",
    )
    old, new = run_both(write(tmp_path, body))
    assert_red(old, "no job-level 'if:' found for the model job")
    assert_same(old, new)


def test_the_state_flag_only_in_a_step_does_not_satisfy_the_job_guard(
    tmp_path: pathlib.Path,
) -> None:
    """THE SUBSTITUTE THE TWIN'S HEADER SAYS IT MUST NOT ACCEPT.

    A whole-file grep for AUTOPILOT_ALLOW_STATE would pass on the state-write
    step that already mentions the flag. The extraction is scoped to the model
    job's own `if:` precisely so it does not, and this is the only case that
    distinguishes the two implementations of that idea.
    """
    body = mutate(
        BASELINE,
        "    if: >-\n      needs.gate.outputs.mode == 'run'\n"
        "      && env.AUTOPILOT_ALLOW_STATE == 'true'\n",
        "    if: needs.gate.outputs.mode == 'run'\n",
    )
    body = mutate(
        body,
        "      - name: Push\n",
        "      - name: Push\n        if: env.AUTOPILOT_ALLOW_STATE == 'true'\n",
    )
    old, new = run_both(write(tmp_path, body))
    assert_red(old, "the model job's if: does not require AUTOPILOT_ALLOW_STATE")
    assert_same(old, new)


def test_the_model_round_allowlist_missing_a_tool(tmp_path: pathlib.Path) -> None:
    body = mutate(BASELINE, '"Edit", ', "")
    old, new = run_both(write(tmp_path, body))
    assert_red(old, 'permission allowlist omits "Edit"')
    assert_same(old, new)


def test_a_tool_named_outside_the_settings_block_does_not_count(
    tmp_path: pathlib.Path,
) -> None:
    """Scoped to the block, not the file: `grep -qF '"Edit"'` over the whole file
    would be satisfied by a mention in a comment three steps away."""
    body = mutate(BASELINE, '"Edit", ', "")
    body = mutate(
        body, "      - name: Push\n", '      # "Edit" is mentioned here\n      - name: Push\n'
    )
    old, new = run_both(write(tmp_path, body))
    assert_red(old, 'permission allowlist omits "Edit"')
    assert_same(old, new)


def test_an_unlocatable_settings_block(tmp_path: pathlib.Path) -> None:
    body = mutate(BASELINE, "      - name: Model round\n", "      - name: Model turn\n")
    old, new = run_both(write(tmp_path, body))
    assert_red(old, "could not locate the Model round settings block")
    assert_same(old, new)


def test_a_workflow_with_crlf_line_endings(tmp_path: pathlib.Path) -> None:
    """`sub(/\\r$/, "", line)` in the twin, `re.sub(r"\\r$", ...)` in the port.

    A CRLF file must produce the same verdict as an LF one, or a Windows-edited
    workflow silently changes what the gate sees.
    """
    path = tmp_path / "crlf.yml"
    path.write_bytes(BASELINE.replace("\n", "\r\n").encode("utf-8"))
    old, new = run_both(path)
    assert old[0] == 0, "a CRLF baseline should still be green:\n%s" % old[2]
    assert_same(old, new)


def test_a_file_with_no_trailing_newline(tmp_path: pathlib.Path) -> None:
    """awk yields N records for N lines whether or not the last one is terminated.

    `text.split("\\n")` yields N+1 with a trailing empty string when it IS
    terminated, and the port's `records()` drops exactly that one. Getting it
    wrong shifts every line NUMBER in every finding.
    """
    path = tmp_path / "nonl.yml"
    path.write_text(BASELINE.rstrip("\n"), encoding="utf-8")
    old, new = run_both(path)
    assert old[0] == 0
    assert_same(old, new)


def test_colour_is_emitted_when_stderr_is_a_terminal(tmp_path: pathlib.Path) -> None:
    """`[[ -t 2 ]] && [[ -z "${NO_COLOR:-}" ]]` (common.sh:18), the branch a human sees.

    `CI` is left UNSET: `rediacc_ci.log` also disables colour on `CI=true` and
    common.sh does not, which is `log.py`'s documented deliberate divergence and
    is not this gate's subject.
    """
    body = mutate(BASELINE, "track_progress: false", "track_progress: true")
    workflow = write(tmp_path, body)
    env = _env(WORKFLOW_FILE=str(workflow))
    old = differential.bash_streams("bash %s" % TWIN, env=env, cwd=str(ROOT), tty="stderr")
    new = differential.bash_streams("python3 %s" % PORT, env=env, cwd=str(ROOT), tty="stderr")
    assert differential.escape_bytes(old[2]) > 0, "the twin printed no colour on a tty"
    assert_same(old, new)


# ---------------------------------------------------------------------------
# The one exempted case
# ---------------------------------------------------------------------------


def test_two_token_jobs_disagree_only_on_order(tmp_path: pathlib.Path) -> None:
    """`for (j in first_token)` IS UNORDERED IN AWK. Pinned, not papered over.

    gawk 5.3.2 answers in internal hash order, which is stable run to run and
    reproducible only from inside gawk; the port emits in insertion order. The
    two therefore print the SAME SET of findings in a different sequence, and
    only when two or more jobs violate the same invariant. Every real violation
    is a single job, and the real workflow has none at all.

    This case asserts three things at once: the sets match, the exit codes
    match, and the twin's order really is neither insertion nor sorted -- the
    last one so that a future gawk whose iteration became insertion-ordered
    turns this test RED rather than letting the port's divergence note go quietly
    stale.
    """
    body = """name: multi
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
    old, new = run_both(write(tmp_path, body))
    assert old[0] == 1
    assert new[0] == 1
    assert old[1] == new[1] == ""

    # Scoped to `INVARIANT-FAIL: token`, not to `token`: the settings-block and
    # state-guard failures this synthetic file also raises mention the word, and
    # the first version of this case counted six findings where it meant three.
    def token_findings(text: str) -> list[str]:
        return [line for line in text.split("\n") if "INVARIANT-FAIL: token" in line]

    old_lines = token_findings(old[2])
    new_lines = token_findings(new[2])
    assert len(old_lines) == 3, "expected three token findings, got:\n%s" % old[2]
    assert sorted(old_lines) == sorted(new_lines)
    assert sorted(old[2].split("\n")) == sorted(new[2].split("\n"))
    # The divergence itself, stated as an assertion so it cannot rot silently.
    assert old_lines != new_lines, (
        "gawk now iterates in insertion order; the port's documented divergence "
        "is obsolete and this test, the module docstring and the exemption in "
        "this file's header should all be removed together"
    )


# ---------------------------------------------------------------------------
# A mutation sweep over the REAL workflow
# ---------------------------------------------------------------------------


def test_a_deterministic_mutation_sweep_of_the_real_workflow(tmp_path: pathlib.Path) -> None:
    """Twenty seeded mutations of the real file, compared byte for byte.

    The hand-written cases above each aim at ONE rule and therefore only ever
    exercise the shapes their author thought of. This sweep is the part that
    catches an interaction -- a dedent that ends a pending checkout at the same
    line a run block closes, a step marker inside a with-block -- and it is
    seeded so a failure is reproducible rather than a flake.

    Anti-vacuity is enforced INSIDE the loop: the sweep must produce at least
    one red and at least one green, or it has proved nothing about either
    branch and fails on that ground alone.
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
        path = write(tmp_path, "\n".join(lines), "sweep_%02d.yml" % index)
        old, new = run_both(path)
        assert_same(old, new)
        if old[0] == 0:
            greens += 1
        else:
            reds += 1
    assert reds > 0, "the sweep produced no failing workflow; it proved only the green branch"
    assert greens > 0, "the sweep produced no passing workflow; it proved only the red branch"


# ---------------------------------------------------------------------------
# The exported helpers, driven directly (the selftest half)
# ---------------------------------------------------------------------------


def test_walk_reports_nothing_but_the_scan_count_on_a_conformant_file() -> None:
    """The NEGATIVE direction. A gate with only positive controls flags the tree."""
    assert port.walk(BASELINE) == [("scanned-jobs", "0", "2")]


def test_walk_fires_on_a_planted_violation() -> None:
    """The POSITIVE direction, in-process, with the line number asserted."""
    body = BASELINE.replace("track_progress: false", "track_progress: true")
    kinds = [(kind, where) for kind, _line, where in port.walk(body) if kind != "scanned-jobs"]
    assert kinds == [("track-progress-armed", "model/- name: Model round")]


def test_records_drops_only_the_terminating_newline() -> None:
    assert port.records("a\nb\n") == ["a", "b"]
    assert port.records("a\nb") == ["a", "b"]
    assert port.records("") == []
    assert port.records("\n") == [""]
    # NOT splitlines: a form feed is not a record separator for awk.
    assert port.records("a\x0cb\n") == ["a\x0cb"]


def test_model_if_block_stops_at_the_next_job() -> None:
    block = port.model_if_block(BASELINE)
    assert block == [
        "    if: >-",
        "      needs.gate.outputs.mode == 'run'",
        "      && env.AUTOPILOT_ALLOW_STATE == 'true'",
    ]


def test_model_settings_block_is_scoped_to_the_model_round_step() -> None:
    block = port.model_settings_block(BASELINE)
    assert block
    assert all(line.startswith("          ") for line in block)
    assert any('"Edit"' in line for line in block)
    assert not any("app-token" in line for line in block)


def test_required_tools_is_the_real_list() -> None:
    """The constant is load-bearing, so it is asserted rather than trusted."""
    assert port.REQUIRED_TOOLS == ('"Edit"', '"Write"', '"Read"')

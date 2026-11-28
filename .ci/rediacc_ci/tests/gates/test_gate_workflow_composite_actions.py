"""Both-ways test for the composite-action scan in `.ci/rediacc_ci/quality/workflows.py`.

THE GAP IT GUARDS. The step rules (the 8-line `run:` cap, env shell syntax, `sudo -E`, `sudo env` drops) read only `.github/workflows`, so a composite action's `runs.steps[*].run` escaped all of them: a 17-line step passed, and five actions carried 8 over-cap blocks (up to 56 logic lines) until the scan was extended. The scan root of the actions is the `WORKFLOW_ACTIONS_DIR` seam, so these cases point it at a fixture and judge ONLY the fixture.

Three claims, each with its control:

  * An over-cap action step is refused, naming the action file, line and step; the same action at the cap is admitted.
  * Workflow-only rules stay off actions: a `pr-` environment line in an action does not fire, the same line in a workflow does.
  * A mutant that drops the actions scan goes red here: with the scan neutralised the planted over-cap step is no longer reported, which is the property the real gate must never lose.

The banned-construct pass (`continue-on-error`) reads `github_yamls`, which already walks `.github/actions`; the case below plants it in a fixture ROOT so that claim is a test and not a reading of the source.
"""

import pathlib

from rediacc_ci.quality import workflows
from rediacc_ci.tests.gates import harness, workflow_rule


def write_action(path: pathlib.Path, lines: int, extra: tuple[str, ...] = ()) -> None:
    """A composite action with one `run:` step of `lines` logic lines, plus a thin one."""
    body = [
        "name: fixture action",
        "description: fixture",
        "runs:",
        "  using: composite",
        "  steps:",
        "    - name: Fat step",
        "      shell: bash",
        "      run: |",
    ]
    body += ["        echo line%d" % i for i in range(1, lines + 1)]
    body += ["    - name: Thin", "      shell: bash", "      run: echo hi"]
    body += list(extra)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(body) + "\n", encoding="utf-8")


def write_clean_workflow(directory: pathlib.Path) -> None:
    (directory / "ok.yml").write_text(
        "name: fixture\non: push\njobs:\n  j:\n    runs-on: ubuntu-latest\n"
        "    steps:\n      - run: ./script.sh\n",
        encoding="utf-8",
    )


def run_with_actions(gate, workflow_dir, actions_dir, **extra):
    env = {"WORKFLOW_ACTIONS_DIR": str(actions_dir)}
    env.update(extra.pop("extra_env", {}))
    return workflow_rule.run_check(gate, workflow_dir, ci=False, extra_env=env, **extra)


def test_over_cap_action_step_is_refused(gate):
    gate.log_test("a composite action step over the cap fails, with file, line and step")
    with harness.temp_dir() as root:
        wf, actions = root / "wf", root / "actions"
        wf.mkdir()
        write_clean_workflow(wf)
        write_action(actions / "fat" / "action.yml", 17)
        result = run_with_actions(gate, wf, actions)
        gate.assert_exit(1, result, "a 17-line action step must fail")
        gate.assert_contains(result.combined, "fat/action.yml:8", "cites the action file and line")
        gate.assert_contains(result.combined, "step: Fat step", "names the offending step")
        gate.assert_contains(result.combined, "has 17 logic lines", "reports the count")
        gate.assert_contains(result.combined, "1 inline run: block(s) exceed 8", "reports the cap")
    gate.log_pass("an over-cap composite action step is refused and located")


def test_compliant_action_is_admitted(gate):
    gate.log_test("CONTROL: an action at the cap, and a nested one, pass")
    with harness.temp_dir() as root:
        wf, actions = root / "wf", root / "actions"
        wf.mkdir()
        write_clean_workflow(wf)
        write_action(actions / "ok" / "action.yml", workflows.DEFAULT_INLINE_MAX_LOGIC)
        write_action(actions / "outer" / "inner" / "action.yml", 3)
        result = run_with_actions(gate, wf, actions)
        gate.assert_exit(0, result, "actions at or under the cap must pass")
    gate.log_pass("compliant actions, nested ones included, are admitted")


def test_nested_action_is_scanned(gate):
    gate.log_test("an action two directories deep is read, as profiler/nest-probe is")
    with harness.temp_dir() as root:
        wf, actions = root / "wf", root / "actions"
        wf.mkdir()
        write_clean_workflow(wf)
        write_action(actions / "outer" / "inner" / "action.yml", 9)
        result = run_with_actions(gate, wf, actions)
        gate.assert_exit(1, result, "a nested over-cap action step must fail")
        gate.assert_contains(result.combined, "outer/inner/action.yml", "names the nested path")
    gate.log_pass("nested composite actions are scanned")


def test_step_rule_beyond_the_cap_applies_to_actions(gate):
    gate.log_test("`sudo -E` in an action step fails, like in a workflow")
    with harness.temp_dir() as root:
        wf, actions = root / "wf", root / "actions"
        wf.mkdir()
        write_clean_workflow(wf)
        write_action(actions / "sudo" / "action.yml", 1)
        text = (actions / "sudo" / "action.yml").read_text(encoding="utf-8")
        (actions / "sudo" / "action.yml").write_text(
            text.replace("echo line1", "sudo -E make install"), encoding="utf-8"
        )
        result = run_with_actions(gate, wf, actions)
        gate.assert_exit(1, result, "sudo -E in an action must fail")
        gate.assert_contains(result.combined, "sudo/action.yml:9", "cites the action line")
    gate.log_pass("per-step rules beyond the cap reach composite actions")


def test_workflow_only_rules_stay_off_actions(gate):
    gate.log_test("a `pr-` environment is a JOB rule: refused in a workflow, ignored in an action")
    block = ("environment: pr-${{ github.event.number }}",)
    with harness.temp_dir() as root:
        wf, actions = root / "wf", root / "actions"
        wf.mkdir()
        write_clean_workflow(wf)
        write_action(actions / "a" / "action.yml", 2, extra=tuple("    " + b for b in block))
        result = run_with_actions(gate, wf, actions)
        gate.assert_exit(0, result, "the job-level rule must not read action files")
        workflow_rule.write_job(wf / "job.yml", *block)
        result = run_with_actions(gate, wf, actions)
        gate.assert_exit(1, result, "CONTROL: the same line in a workflow job fails")
    gate.log_pass("workflow-only rules do not apply to actions, and still apply to workflows")


def test_actions_alone_do_not_satisfy_anti_vacuity(gate):
    gate.log_test("an empty workflow dir stays blind even when actions exist")
    with harness.temp_dir() as root:
        wf, actions = root / "wf", root / "actions"
        wf.mkdir()
        write_action(actions / "a" / "action.yml", 2)
        result = run_with_actions(gate, wf, actions)
        gate.assert_exit(1, result, "no workflows must fail")
        gate.assert_contains(result.combined, "this check is blind", "says why")
    gate.log_pass("the workflow directory must still be seen")


def test_mutant_without_the_actions_scan_goes_red(gate, monkeypatch):
    gate.log_test("MUTANT: drop the actions scan and the planted over-cap step is not reported")
    with harness.temp_dir() as root:
        wf, actions = root / "wf", root / "actions"
        wf.mkdir()
        write_clean_workflow(wf)
        write_action(actions / "fat" / "action.yml", 17)
        monkeypatch.setenv(workflows.ACTIONS_DIR_ENV, str(actions))

        real = workflows.Errors()
        workflows.check_inline_run_blocks(real, pathlib.Path("/"), str(wf), 8)
        gate.assert_eq(1, real.count, "the real scan reports the planted action step")

        original = workflows.step_targets
        monkeypatch.setattr(
            workflows,
            "step_targets",
            lambda r, d, _with_actions=True: original(r, d, with_actions=False),
        )
        mutant = workflows.Errors()
        workflows.check_inline_run_blocks(mutant, pathlib.Path("/"), str(wf), 8)
        gate.assert_eq(0, mutant.count, "the mutant misses it, so this test is what catches it")
    gate.log_pass("a gate that stops reading actions turns the planted step invisible")


def test_banned_construct_in_an_action_is_refused(gate):
    gate.log_test("continue-on-error inside an action step is a banned pattern")
    with harness.temp_dir() as root:
        write_action(
            root / ".github" / "actions" / "c" / "action.yml",
            2,
            extra=("      continue-on-error: true",),
        )
        files = workflows.github_yamls(root)
        gate.assert_eq(1, len(files), "the fixture root's one action is collected")
        errors = workflows.Errors()
        for pattern, label, hint in workflows.BANNED:
            workflows.check_pattern(errors, root, files, pattern, label, hint)
        gate.assert_eq(1, errors.count, "continue-on-error in an action is reported once")
        clean = harness.temp_dir()
        with clean as clean_root:
            write_action(clean_root / ".github" / "actions" / "c" / "action.yml", 2)
            errors = workflows.Errors()
            for pattern, label, hint in workflows.BANNED:
                workflows.check_pattern(
                    errors, clean_root, workflows.github_yamls(clean_root), pattern, label, hint
                )
            gate.assert_eq(0, errors.count, "CONTROL: the same action without it is clean")
    gate.log_pass("banned constructs are read inside actions")

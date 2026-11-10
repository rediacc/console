"""Both-ways test for the `sudo -E` rule in `.ci/scripts/quality/check_workflows.py`.

THE BUG IT GUARDS. ubuntu-26.04 ships sudo-rs, where `sudo -E` prints "preserving the entire environment is not supported, '-E' is ignored" and drops CI, RUNNER_TEMP, HOME and VM_NET_BASE. renet then wrote its keys under /root/.renet and OPS Provision failed at the SSH step (nightly run 42779243944). The portable form is `sudo env "NAME=value" cmd`.
"""

import pathlib

from rediacc_ci.tests.gates import harness, workflow_rule


def _write_run(path: pathlib.Path, command: str) -> None:
    body = [
        "name: fixture",
        "on: push",
        "jobs:",
        "  j:",
        "    runs-on: ubuntu-latest",
        "    steps:",
        "      - run: |",
        "          %s" % command,
    ]
    path.write_text("\n".join(body) + "\n", encoding="utf-8")


def test_flags_sudo_e(gate):
    gate.log_test("a run step using `sudo -E` must fail")
    for command in (
        "sudo -E node cli.cjs ops up",
        "STATUS=$(sudo -E node cli.cjs ops status -o json)",
        "sudo --preserve-env node cli.cjs ops up",
    ):
        with harness.temp_dir() as d:
            _write_run(d / "bad.yml", command)
            result = workflow_rule.run_check(gate, d, ci=True)
            gate.assert_exit(1, result, "`%s` must fail" % command)
            gate.assert_contains(result.combined, "bad.yml:8", "cites file:line")
            gate.assert_contains(result.combined, "sudo env", "names the remedy")
    gate.log_pass("flags sudo -E and --preserve-env, with file:line and the remedy")


def test_sudo_env_and_comments_pass(gate):
    gate.log_test("CONTROL: `sudo env NAME=value` and a commented mention pass")
    for command in (
        'sudo env "RENET_DATA_DIR=$RUNNER_TEMP/renet" node cli.cjs ops up',
        "# sudo -E is a no-op on sudo-rs",
        "sudo -n true",
    ):
        with harness.temp_dir() as d:
            _write_run(d / "ok.yml", command)
            result = workflow_rule.run_check(gate, d, ci=True)
            gate.assert_exit(0, result, "`%s` must pass" % command)
    gate.log_pass("sudo env, a comment, and other sudo flags stay silent")

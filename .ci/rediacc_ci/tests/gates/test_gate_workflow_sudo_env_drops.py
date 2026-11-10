"""Both-ways test for the `sudo env` drop rule in `.ci/scripts/quality/check_workflows.py`.

THE BUG IT GUARDS. `sudo env NAME=value cmd` passes the command ONLY the names it lists. After `sudo -E` was replaced by `sudo env` (4026249886), the Provision VM step kept its own `env:` block (VM_WORKERS, VM_CEPH_NODES, VM_BRIDGE) while the `sudo env` line named none of them, so `ops up` ran with renet defaults (fixed in fdefb2939e). The rule refuses a step whose `sudo env` run text leaves out any name of the same step's `env:` block.
"""

import pathlib

from rediacc_ci.tests.gates import harness, workflow_rule


def _write_step(path: pathlib.Path, run: str, env: tuple[str, ...]) -> None:
    body = [
        "name: fixture",
        "on: push",
        "jobs:",
        "  j:",
        "    runs-on: ubuntu-latest",
        "    steps:",
        "      - name: Provision",
        "        run: %s" % run,
    ]
    if env:
        body.append("        env:")
        body += ["          %s" % entry for entry in env]
    path.write_text("\n".join(body) + "\n", encoding="utf-8")


def test_flags_sudo_env_dropping_step_env(gate):
    gate.log_test("a `sudo env` line that omits a step env name must fail")
    with harness.temp_dir() as d:
        _write_step(
            d / "bad.yml",
            'sudo env "PATH=$PATH" "VM_WORKERS=$VM_WORKERS" renet ops up',
            ("VM_WORKERS: '11'", "VM_BRIDGE: '1'", "VM_CEPH_NODES: ''"),
        )
        result = workflow_rule.run_check(gate, d, ci=True)
        gate.assert_exit(1, result, "dropped step env must fail")
        gate.assert_contains(result.combined, "bad.yml:8", "cites file:line")
        gate.assert_contains(
            result.combined, "VM_BRIDGE, VM_CEPH_NODES", "names the missing variables"
        )
    gate.log_pass("missing names reported with file:line")


def test_flags_block_scalar_run(gate):
    gate.log_test("a `sudo env` inside a run block scalar is read too")
    with harness.temp_dir() as d:
        (d / "bad.yml").write_text(
            "name: fixture\non: push\njobs:\n  j:\n    runs-on: ubuntu-latest\n    steps:\n      - run: |\n          echo start\n          sudo env PATH=$PATH renet ops up\n        env:\n          VM_BRIDGE: '1'"
            "\n",
            encoding="utf-8",
        )
        result = workflow_rule.run_check(gate, d, ci=True)
        gate.assert_exit(1, result, "block-scalar run must fail")
        gate.assert_contains(result.combined, "bad.yml:9", "cites the sudo line")
    gate.log_pass("block scalar covered")


def test_silent_controls(gate):
    gate.log_test("CONTROL: every name passed, no env block, and no sudo env all stay silent")
    cases = (
        (
            'sudo env "VM_WORKERS=$VM_WORKERS" "VM_BRIDGE=$VM_BRIDGE" renet ops up',
            ("VM_WORKERS: '11'", "VM_BRIDGE: '1'"),
        ),
        ('sudo env "PATH=$PATH" renet ops up', ()),
        ("sudo renet ops up", ("VM_WORKERS: '11'",)),
    )
    for run, env in cases:
        with harness.temp_dir() as d:
            _write_step(d / "ok.yml", run, env)
            result = workflow_rule.run_check(gate, d, ci=True)
            gate.assert_exit(0, result, "`%s` with env %s must pass" % (run, env))
    gate.log_pass("controls stay silent")


def test_sibling_step_env_not_blamed(gate):
    gate.log_test("CONTROL: an env block on a different step does not count against the sudo step")
    with harness.temp_dir() as d:
        (d / "ok.yml").write_text(
            "name: fixture\non: push\njobs:\n  j:\n    runs-on: ubuntu-latest\n    steps:\n      - run: sudo env PATH=$PATH renet ops up\n      - run: ./other.sh\n        env:\n          OTHER: x"
            "\n",
            encoding="utf-8",
        )
        result = workflow_rule.run_check(gate, d, ci=True)
        gate.assert_exit(0, result, "sibling step env must not be blamed")
    gate.log_pass("env stays scoped to its own step")


def _write_raw(path: pathlib.Path, step_lines: list[str]) -> None:
    head = [
        "name: fixture",
        "on: push",
        "jobs:",
        "  j:",
        "    runs-on: ubuntu-latest",
        "    steps:",
    ]
    path.write_text("\n".join(head + step_lines) + "\n", encoding="utf-8")


def test_name_elsewhere_in_step_does_not_count(gate):
    gate.log_test(
        "an `export NAME=` or prefix assignment outside the sudo env line must not hide a drop"
    )
    cases = (
        ["          export VM_BRIDGE=1", "          sudo env PATH=$PATH renet ops up"],
        ["          VM_BRIDGE=1 sudo env PATH=$PATH renet ops up"],
    )
    for body in cases:
        with harness.temp_dir() as d:
            _write_raw(
                d / "bad.yml",
                ["      - run: |", *body, "        env:", "          VM_BRIDGE: '1'"],
            )
            result = workflow_rule.run_check(gate, d, ci=True)
            gate.assert_exit(1, result, "name outside the sudo line must still fail: %s" % body)
            gate.assert_contains(result.combined, "VM_BRIDGE", "names the dropped variable")
    gate.log_pass("only the sudo env line counts")


def test_continuation_line_names_count(gate):
    gate.log_test("CONTROL: a name on a backslash continuation of the sudo env line stays silent")
    with harness.temp_dir() as d:
        _write_raw(
            d / "ok.yml",
            [
                "      - run: |",
                "          sudo env PATH=$PATH \\",
                '            "VM_BRIDGE=$VM_BRIDGE" renet ops up',
                "        env:",
                "          VM_BRIDGE: '1'",
            ],
        )
        result = workflow_rule.run_check(gate, d, ci=True)
        gate.assert_exit(0, result, "continued sudo env line naming the variable must pass")
    gate.log_pass("continuations are part of the line")


def test_flow_style_env_mapping(gate):
    gate.log_test("a flow-style step `env: {..}` is read; naming every key stays silent")
    with harness.temp_dir() as d:
        _write_raw(
            d / "bad.yml",
            [
                "      - run: sudo env PATH=$PATH renet ops up",
                "        env: {VM_BRIDGE: '1', \"VM_WORKERS\": 11}",
            ],
        )
        result = workflow_rule.run_check(gate, d, ci=True)
        gate.assert_exit(1, result, "flow-style env drop must fail")
        gate.assert_contains(result.combined, "VM_BRIDGE, VM_WORKERS", "names both flow keys")
    with harness.temp_dir() as d:
        _write_raw(
            d / "ok.yml",
            [
                "      - run: sudo env VM_BRIDGE=$VM_BRIDGE VM_WORKERS=$VM_WORKERS renet ops up",
                "        env: {VM_BRIDGE: '1', \"VM_WORKERS\": 11}",
            ],
        )
        result = workflow_rule.run_check(gate, d, ci=True)
        gate.assert_exit(0, result, "flow-style env fully named must pass")
    gate.log_pass("flow-style env covered both ways")

"""`rediacc_ci.drills.lifecycle_privilege`: the CLI-free helpers of the L1 step (boxes P1 and T1 of PLAN-rediaccfile-unprivileged), pinned without a machine. The live `run(ctx)` is exercised by `npm run vm:check` (its L1 rows); here the probe text, the root scripts and the parsers and verdicts of probe output and grant files are checked against outputs shaped like the real ones, with a control for every verdict that must be able to fail."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile

from rediacc_ci.drills import lifecycle_privilege as lp
from rediacc_ci.drills import vm_check
from rediacc_ci.well_known import DATASTORE_PATH

GOOD_UP = """uid=7111
capeff=0000000000000000
kcore=denied
shadow=denied
block=denied
grants=denied
cred_env=absent
cred_parent=denied
sudo_rc=1
sudo_msg=sudo: The "no new privileges" flag is set, which prevents sudo from running as root.
created_owner=7111
env_owner=7111
cdi_open=Permission denied
"""

ROOT_UP = GOOD_UP.replace("uid=7111", "uid=0").replace("created_owner=7111", "created_owner=0")


# --------------------------------------------------------------------------- registration


def test_step_registration_tuple() -> None:
    assert ("L1", ("P5",), lp.run) == lp.STEP
    assert lp.STEP in vm_check.EXTRA_RENET_STEPS
    assert "L1" in vm_check.PHASE_STEPS[vm_check.SIDE_RENET]


def test_l1_only_drags_in_p5() -> None:
    assert vm_check.VmCheck._ONLY_DEPS["L1"] == ("P5",)


def test_fork_tag_is_swept_as_a_stale_vmc_fork() -> None:
    tags = vm_check.fork_tags("10251200", "abc123")
    tag = lp.fork_tag(tags)
    assert tag == "vmc-10251200-abc123-f"
    assert vm_check.FORK_TAG.match(tag)
    assert tag not in tags


# --------------------------------------------------------------------------- the probe


def test_probe_rediaccfile_is_valid_bash_and_reports_every_key() -> None:
    text = lp.probe_rediaccfile()
    proc = subprocess.run(["bash", "-n"], input=text, text=True, capture_output=True, check=False)
    assert proc.returncode == 0, proc.stderr
    for key in (
        "uid=",
        "capeff=",
        "kcore=",
        "shadow=",
        "block=",
        "grants=",
        "cred_env=",
        "cred_parent=",
        "sudo_rc=",
        "sudo_msg=",
        "created_owner=",
        "env_owner=",
        "cdi_open=",
    ):
        assert key in text, key
    assert "up()" in text
    assert "down()" in text
    # The credential's value is never written by the probe, only its presence.
    assert lp.CREDENTIAL_VALUE not in text


def test_probe_runs_for_real_and_reports_this_process() -> None:
    """Run the probe's `up()` here (renet and sudo stubbed out): the keys come back parseable and the uid is this process's."""
    with tempfile.TemporaryDirectory() as work:
        script = lp.probe_rediaccfile()
        runner = (
            "source /dev/stdin <<'EOF'\n%sEOF\nsudo() { echo 'stub: no new privileges' >&2; return 1; }\nup\n"
            % script
        )
        env = {
            **os.environ,
            "REDIACC_WORKING_DIR": work,
            "LC_ALL": "C",
            lp.CREDENTIAL_VAR: lp.CREDENTIAL_VALUE,
        }
        proc = subprocess.run(
            ["bash", "-c", runner], env=env, capture_output=True, text=True, check=False
        )
        assert proc.returncode == 0, proc.stderr
        with open(os.path.join(work, lp.UP_FILE)) as handle:
            probe = lp.parse_probe(handle.read())
    assert lp.uid_of(probe) == os.getuid()
    assert (
        probe["cred_env"] == "present"
    )  # the control: the probe can see a credential that is there
    assert probe["sudo_rc"] == "1"
    assert probe["created_owner"] == str(os.getuid())
    assert probe["env_owner"] == str(os.getuid())
    assert probe["cdi_open"] != ""  # an absent node answers "No such file", never an empty line


def test_probe_files_carry_the_rediaccfile_and_the_failing_compose() -> None:
    files = lp.probe_files()
    assert files["Rediaccfile"] == lp.probe_rediaccfile()
    assert files[lp.BAD_COMPOSE] == lp.bad_compose()
    assert ">" not in lp.clear_probe_state_command()


def test_bad_compose_names_an_image_that_cannot_exist() -> None:
    assert "rediacc.invalid/" in lp.bad_compose()


def test_fail_marker_command_toggles() -> None:
    assert lp.fail_marker_command(True) == "touch " + lp.FAIL_MARKER
    assert lp.fail_marker_command(False) == "rm -f " + lp.FAIL_MARKER


# --------------------------------------------------------------------------- parsers and verdicts


def test_parse_probe_reads_key_value_lines_and_ignores_noise() -> None:
    probe = lp.parse_probe("noise\n" + GOOD_UP + "also noise without equals\nuid=9\n")
    assert probe["kcore"] == "denied"
    assert probe["uid"] == "9"  # the last value of a key wins
    assert "noise" not in probe


def test_dropped_verdict_control_and_failures() -> None:
    assert lp.dropped_verdict(lp.parse_probe(GOOD_UP))[0]
    assert not lp.dropped_verdict(lp.parse_probe(ROOT_UP))[0]
    full_caps = GOOD_UP.replace("0000000000000000", "000001ffffffffff")
    assert not lp.dropped_verdict(lp.parse_probe(full_caps))[0]
    assert not lp.dropped_verdict({})[0]


def test_denied_verdict_control_and_each_open_key() -> None:
    assert lp.denied_verdict(lp.parse_probe(GOOD_UP))[0]
    for key in ("kcore", "shadow", "block", "grants"):
        opened = GOOD_UP.replace("%s=denied" % key, "%s=readable" % key)
        ok, why = lp.denied_verdict(lp.parse_probe(opened))
        assert not ok
        assert key in why
    leaked = GOOD_UP.replace("cred_env=absent", "cred_env=present")
    assert not lp.denied_verdict(lp.parse_probe(leaked))[0]
    parent = GOOD_UP.replace("cred_parent=denied", "cred_parent=readable")
    assert not lp.denied_verdict(lp.parse_probe(parent))[0]
    assert not lp.denied_verdict({})[0]


def test_denied_verdict_refuses_a_probe_that_had_nothing_to_probe() -> None:
    """`none` is what the probe prints for a missing block device or grants directory: nothing was denied, so the row is not a pass."""
    for key in ("block", "grants"):
        ok, why = lp.denied_verdict(
            lp.parse_probe(GOOD_UP.replace("%s=denied" % key, "%s=none" % key))
        )
        assert not ok
        assert key in why


def test_sudo_verdict_needs_a_failure_that_names_no_new_privs() -> None:
    assert lp.sudo_verdict(lp.parse_probe(GOOD_UP))[0]
    worked = GOOD_UP.replace("sudo_rc=1", "sudo_rc=0")
    assert not lp.sudo_verdict(lp.parse_probe(worked))[0]
    other_failure = GOOD_UP.replace('The "no new privileges" flag is set', "a password is required")
    assert not lp.sudo_verdict(lp.parse_probe(other_failure))[0]


def test_owner_verdict() -> None:
    assert lp.owner_verdict(lp.parse_probe(GOOD_UP))[0]
    assert not lp.owner_verdict(lp.parse_probe(ROOT_UP))[0]
    mismatch = GOOD_UP.replace("created_owner=7111", "created_owner=0")
    assert not lp.owner_verdict(lp.parse_probe(mismatch))[0]


def test_root_verdict_is_the_positive_control() -> None:
    assert lp.root_verdict(lp.parse_probe(ROOT_UP))[0]
    assert not lp.root_verdict(lp.parse_probe(GOOD_UP))[0]
    assert not lp.root_verdict({})[0]


def test_up_failed_verdict() -> None:
    failure = "Error response from daemon: pull access denied for %s/%s" % (
        lp.BAD_IMAGE_HOST,
        lp.BAD_IMAGE_NAME,
    )
    assert lp.up_failed_verdict(1, failure)[0]
    assert not lp.up_failed_verdict(0, failure)[0]
    assert not lp.up_failed_verdict(0, "")[0]
    # An unrelated failure (a broken install) exits nonzero without naming the compose file's image.
    assert not lp.up_failed_verdict(1, "renet: command not found")[0]


def test_probe_prints_none_for_a_missing_block_device_and_grants_directory() -> None:
    """Run the probe's `_report` with no `/sys/block` entry and no grants directory: both keys say `none`, never `denied`."""
    with tempfile.TemporaryDirectory() as work:
        script = lp.probe_rediaccfile().replace(lp.ETC_DIR + "/grants", work + "/no-grants")
        script = script.replace("ls /sys/block", "ls " + work + "/no-block")
        runner = "source /dev/stdin <<'EOF'\n%sEOF\nsudo() { return 1; }\nup\n" % script
        env = {**os.environ, "REDIACC_WORKING_DIR": work, "LC_ALL": "C"}
        proc = subprocess.run(
            ["bash", "-c", runner], env=env, capture_output=True, text=True, check=False
        )
        assert proc.returncode == 0, proc.stderr
        with open(os.path.join(work, lp.UP_FILE)) as handle:
            probe = lp.parse_probe(handle.read())
    assert probe["block"] == "none"
    assert probe["grants"] == "none"


# --------------------------------------------------------------------------- grants


def test_scripts_name_the_network() -> None:
    assert lp.grant_show_script(2816) == "renet daemon grant --network-id 2816 --show"
    assert lp.root_grant_script(2816, True) == (
        "renet daemon grant --network-id 2816 --lifecycle-root=true --show"
    )
    assert "--lifecycle-root=false" in lp.root_grant_script("2816", False)


def test_parse_lifecycle_and_no_grant_verdict() -> None:
    empty = 'level=info msg="x"\n{"version": 1, "repo_mount_path": "/mnt/x"}\n'
    parsed = lp.parse_lifecycle(empty)
    assert parsed == (False, [])
    assert lp.no_grant_verdict(parsed)[0]

    held = '{"version": 1, "lifecycle": {"root": true, "paths": [{"path": "/srv/a"}]}}'
    parsed = lp.parse_lifecycle(held)
    assert parsed == (True, ["/srv/a"])
    assert not lp.no_grant_verdict(parsed)[0]

    only_path = '{"version": 1, "lifecycle": {"paths": [{"path": "/srv/a"}]}}'
    assert not lp.no_grant_verdict(lp.parse_lifecycle(only_path))[0]

    assert lp.parse_lifecycle("no json here") is None
    assert not lp.no_grant_verdict(None)[0]


# --------------------------------------------------------------------------- L1.4 .env and L1.9 device grant


def test_env_verdict_control_and_failures() -> None:
    assert lp.env_verdict(lp.parse_probe(GOOD_UP))[0]
    root_owned = GOOD_UP.replace("env_owner=7111", "env_owner=0")
    assert not lp.env_verdict(lp.parse_probe(root_owned))[0]
    assert not lp.env_verdict(lp.parse_probe(ROOT_UP))[0]
    assert not lp.env_verdict({})[0]


def test_cdi_verdict_both_directions_and_the_silent_probe() -> None:
    denied = lp.parse_probe(GOOD_UP)
    reached = lp.parse_probe(GOOD_UP.replace("Permission denied", "No such device or address"))
    assert lp.cdi_verdict(denied, False)[0]
    assert lp.cdi_verdict(reached, True)[0]
    assert not lp.cdi_verdict(reached, False)[0]
    assert not lp.cdi_verdict(denied, True)[0]
    assert not lp.cdi_verdict({}, False)[0]
    assert not lp.cdi_verdict({}, True)[0]


def test_probe_cdi_open_reports_what_an_open_of_the_node_says() -> None:
    """Run the probe's `up()` here with the node pointing at a missing path: the open's error text reaches `cdi_open`."""
    with tempfile.TemporaryDirectory() as work:
        script = lp.probe_rediaccfile().replace(lp.CDI_NODE, work + "/absent-node")
        runner = "source /dev/stdin <<'EOF'\n%sEOF\nsudo() { return 1; }\nup\n" % script
        env = {**os.environ, "REDIACC_WORKING_DIR": work, "LC_ALL": "C"}
        proc = subprocess.run(
            ["bash", "-c", runner], env=env, capture_output=True, text=True, check=False
        )
        assert proc.returncode == 0, proc.stderr
        with open(os.path.join(work, lp.UP_FILE)) as handle:
            probe = lp.parse_probe(handle.read())
    assert probe["cdi_open"] == "No such file or directory"


# --------------------------------------------------------------------------- T1 rows: cold barrier, stopped daemon, reboot shape


def _run_probe_down(docker_ok: bool, marker: bool) -> subprocess.CompletedProcess[str]:
    """Run the probe's `down()` here with `docker` stubbed to answer or fail."""
    with tempfile.TemporaryDirectory() as work:
        if marker:
            open(os.path.join(work, lp.DOWN_MARKER), "w").close()
        runner = (
            "source /dev/stdin <<'EOF'\n%sEOF\nsudo() { return 1; }\ndocker() { return %d; }\ndown\n"
            % (lp.probe_rediaccfile(), 0 if docker_ok else 1)
        )
        env = {**os.environ, "REDIACC_WORKING_DIR": work, "LC_ALL": "C"}
        return subprocess.run(
            ["bash", "-c", runner], env=env, capture_output=True, text=True, check=False
        )


def test_down_asks_the_daemon_only_under_the_marker() -> None:
    unreachable = _run_probe_down(docker_ok=False, marker=True)
    assert unreachable.returncode != 0
    assert lp.DOWN_FAIL_MARK in unreachable.stderr
    # controls: a reachable daemon, or no marker, leaves down() succeeding
    assert _run_probe_down(docker_ok=True, marker=True).returncode == 0
    assert _run_probe_down(docker_ok=False, marker=False).returncode == 0


def test_clear_probe_state_clears_the_down_marker() -> None:
    assert lp.DOWN_MARKER in lp.clear_probe_state_command()


def test_down_marker_and_removal_commands() -> None:
    assert lp.down_marker_command(True) == "touch " + lp.DOWN_MARKER
    assert lp.down_marker_command(False) == "rm -f " + lp.DOWN_MARKER
    assert lp.remove_probe_output_command(lp.UP_FILE) == "rm -f " + lp.UP_FILE


def test_down_honest_verdict_control_and_failures() -> None:
    assert lp.down_honest_verdict(1, "x " + lp.DOWN_FAIL_MARK)[0]
    assert not lp.down_honest_verdict(0, lp.DOWN_FAIL_MARK)[0]  # reported success
    assert not lp.down_honest_verdict(1, "unrelated failure")[0]  # failed for another reason


def test_down_permission_denied_on_the_socket_is_not_an_unreachable_daemon() -> None:
    """`docker info` refused for the dropped uid is not the stopped-daemon complaint, so L1.11 cannot pass on it."""
    with tempfile.TemporaryDirectory() as work:
        open(os.path.join(work, lp.DOWN_MARKER), "w").close()
        runner = (
            "source /dev/stdin <<'EOF'\n%sEOF\nsudo() { return 1; }\n"
            "docker() { echo 'permission denied while trying to connect to the docker API' >&2; return 1; }\n"
            "down\n" % lp.probe_rediaccfile()
        )
        env = {**os.environ, "REDIACC_WORKING_DIR": work, "LC_ALL": "C"}
        res = subprocess.run(
            ["bash", "-c", runner], env=env, capture_output=True, text=True, check=False
        )
    assert res.returncode != 0
    assert lp.DOWN_FAIL_MARK not in res.stderr
    assert not lp.down_honest_verdict(res.returncode, res.stdout + res.stderr)[0]


class _Reply:
    def __init__(self, rc: int) -> None:
        self.rc, self.out, self.err = rc, "", ""


class _StopProbe(lp._LiveL1):
    """An L1 whose root scripts are canned: the daemon stop exits 1 after stopping the unit, the start fails too."""

    def __init__(self) -> None:
        self.nid = 7
        self.ref = "r"
        self.root_granted = False
        self.autostart_enabled = False
        self.daemon_stopped = False
        self.reboot_grand = ""
        self.device_granted = False
        self.fake_written = False
        self.scripts: list[str] = []

    def up(self, _extra_env=None):
        return _Reply(0)

    def shell(self, _command: str, _ref: str = ""):
        return _Reply(0)

    def check(self, _desc: str, ok: bool, _res=None, _evidence: str = "") -> bool:
        return ok

    def root(self, command: str, _timeout: float = 60.0):
        self.scripts.append(command)
        return _Reply(1)


def test_a_failed_stop_still_leaves_the_daemon_for_teardown_to_start() -> None:
    probe = _StopProbe()
    probe.l1_11_down_stopped_daemon()
    assert probe.daemon_stopped is True  # stop rc=1 and start rc=1: teardown must retry the start
    probe.scripts.clear()
    probe.ctx = type("Ctx", (), {"sweep_leftovers": [], "scrub": staticmethod(str)})()
    probe.cleanup()
    assert lp.daemon_stop_script(7, False) in probe.scripts


def test_cold_barrier_verdict_control_and_failures() -> None:
    good = lp.parse_probe(GOOD_UP)
    assert lp.cold_barrier_verdict(good)[0]
    assert not lp.cold_barrier_verdict({})[0]  # the barrier never ran up()
    leaked = lp.parse_probe(GOOD_UP.replace("cred_env=absent", "cred_env=present"))
    assert not lp.cold_barrier_verdict(leaked)[0]
    readable = lp.parse_probe(GOOD_UP.replace("cred_parent=denied", "cred_parent=readable"))
    assert not lp.cold_barrier_verdict(readable)[0]
    assert not lp.cold_barrier_verdict(lp.parse_probe(ROOT_UP))[0]


def test_reboot_verdict_control_and_failures() -> None:
    good = lp.parse_probe(GOOD_UP)
    assert lp.reboot_verdict(good, 0)[0]
    assert not lp.reboot_verdict(good, 1)[0]
    assert not lp.reboot_verdict({}, 0)[0]  # the tick recovered nothing
    assert not lp.reboot_verdict(lp.parse_probe(ROOT_UP), 0)[0]


def test_barrier_daemon_and_reconcile_scripts() -> None:
    script = lp.cold_barrier_script(DATASTORE_PATH, "abc-123")
    assert script.startswith("env %s=" % lp.CREDENTIAL_VAR)
    assert f"renet backup snapshot --datastore {DATASTORE_PATH} --repo abc-123 --cold" in script
    assert lp.daemon_stop_script(2816, True) == "systemctl stop rediacc-docker-2816"
    assert lp.daemon_stop_script(2816, False) == "systemctl start rediacc-docker-2816"
    assert (
        lp.reconcile_script(DATASTORE_PATH)
        == f"renet repository reconcile --datastore {DATASTORE_PATH}"
    )


def test_remote_evidence_of_a_cli_refusal_names_the_refusal_not_the_metrics_tail() -> None:
    envelope = json.dumps(
        {
            "success": False,
            "errors": [{"code": "VALIDATION_ERROR", "message": "Repository x is not\ndeployed"}],
            "metrics": {"duration_ms": 1660},
        },
        indent=2,
    )

    assert vm_check.envelope_errors(envelope) == "Repository x is not deployed"
    assert vm_check.envelope_errors("plain text\n") == ""
    assert vm_check.envelope_errors('{"errors": []}') == ""
    assert vm_check.envelope_errors('{"errors": 7}') == ""


def _evidence(err: str, out: str = "") -> str:
    return vm_check.remote_evidence(vm_check.Result(1, out, err))


def test_remote_evidence_drops_the_cli_startup_lines_ahead_of_the_remote_stderr() -> None:
    evidence = _evidence("\u2192 Starting CLI\n\u2713 Renet available\nchmod: not permitted\n")
    assert "chmod: not permitted" in evidence
    assert "Starting CLI" not in evidence


def test_remote_evidence_keeps_the_startup_lines_when_nothing_else_is_on_stderr() -> None:
    assert "Starting CLI" in _evidence("\u2192 Starting CLI\n")

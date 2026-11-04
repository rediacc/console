"""`rediacc_ci.drills.lifecycle_privilege`: the CLI-free helpers of the L1 step (boxes P1 and T1 of PLAN-rediaccfile-unprivileged), pinned without a machine. The live `run(ctx)` is exercised by `npm run vm:check` (its L1 rows); here the probe text, the root scripts and the parsers and verdicts of probe output and grant files are checked against outputs shaped like the real ones, with a control for every verdict that must be able to fail."""

from __future__ import annotations

import base64
import os
import re
import subprocess
import tempfile

from rediacc_ci.drills import lifecycle_privilege as lp
from rediacc_ci.drills import vm_check

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
        env = {**os.environ, "REDIACC_WORKING_DIR": work, lp.CREDENTIAL_VAR: lp.CREDENTIAL_VALUE}
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


def test_install_command_writes_both_files_through_base64() -> None:
    cmd = lp.install_command()
    blobs = re.findall(r"printf %s ([A-Za-z0-9+/=]+) \| base64 -d", cmd)
    assert len(blobs) == 2
    assert base64.b64decode(blobs[0]).decode() == lp.probe_rediaccfile()
    assert base64.b64decode(blobs[1]).decode() == lp.bad_compose()
    assert lp.BAD_COMPOSE in cmd


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
    assert lp.up_failed_verdict(1, "compose: pull access denied")[0]
    assert not lp.up_failed_verdict(0, "")[0]


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
        env = {**os.environ, "REDIACC_WORKING_DIR": work}
        proc = subprocess.run(
            ["bash", "-c", runner], env=env, capture_output=True, text=True, check=False
        )
        assert proc.returncode == 0, proc.stderr
        with open(os.path.join(work, lp.UP_FILE)) as handle:
            probe = lp.parse_probe(handle.read())
    assert probe["cdi_open"] == "No such file or directory"

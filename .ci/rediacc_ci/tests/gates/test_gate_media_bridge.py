"""Port of `.ci/scripts/test/gates/test-media-bridge.sh`, retired in W7 P5.

Tests for `.ci/media/bridge.sh` -- VM provisioning and the host->bridge SSH helpers.

THE PART THAT CAN BE TESTED WITHOUT A CLUSTER is bigger than it looks. Four of these nine functions are pure address arithmetic over `.provision-state` and two shell variables, and they are exactly the ones that go wrong quietly: a worker index that is off by one, or a default that stops matching `VM_NET_BASE`, sends a recording at a machine that is not there and reports it as an
SSH problem. Those are staged with fixture files and asserted here.

The remaining five drive a real libvirt cluster or a real SSH endpoint. What is asserted about them is what a test legitimately can: the SHAPE of the command they build. `ssh` and `rsync` are fakes that record their argv, so the `-F` config path, the BatchMode and StrictHostKeyChecking settings and the rsync `-e` wrapper are all pinned without a VM existing.

Nothing here reaches a network. ssh, rsync, rdc.sh, go and node are all absent or faked.

WHERE THIS REIMPLEMENTS grep AND sed, AND WHY THE ANSWERS AGREE.

  `grep '^_BRIDGE_SSH_CONFIG=' bridge.sh` becomes a line scan for a line STARTING
  with that literal. `^` in a POSIX BRE anchors at the start of a line and grep is
  line-oriented, so `str.startswith` over `splitlines()` is the same predicate on
  the same input. The twin then asserts the result is non-empty; this asserts a
  match was found, which is the same claim without the empty-string round trip.

  The off-by-one plant is `sed 's/cut -d, -f"\\$idx"/cut -d, -f"$((idx + 1))"/'`,
  a fixed-string substitution (the only regex metacharacter in it, `$`, is
  backslash-escaped). `str.replace` on the same literal is identical, and the twin's
  follow-up `grep -q 'f"$((idx + 1))"'` refusal is kept as an explicit count check
  BEFORE the write, so an anchor that has moved is a red naming the anchor rather
  than a control that passes for the wrong reason.

WHY THE OFF-BY-ONE IS PLANTED IN THE STATE-FILE BRANCH AND NOT THE FALLBACK. The fixture cases stage a `.provision-state`, so the `VM_WORKERS` fallback line is never reached; planting there would leave the control green while proving nothing. The twin's comment records that this mistake was made once while writing it, and the same trap applies verbatim to this file.

ONE PLACE THIS PORT IS STRICTLY STRONGER THAN ITS TWIN, measured 2026-09-07 while plant-verifying. With the off-by-one planted in the REAL `bridge.sh`, the twin's `test_a_planted_mutation_is_visible_to_the_behaviour_cases` PASSES VACUOUSLY: its `sed` finds nothing to substitute and exits 0, its follow-up `grep -q 'f"$((idx + 1))"'` is satisfied by the plant that is already there,
and the mutant it builds is byte-identical to the module, so "the original is gone, the plant is present" holds for the wrong reason. This port counts the anchor BEFORE writing and refuses when it is not present exactly once, so the same tree turns that case red as well. The VERDICT is unchanged either way -- both sides went red on
`test_address_resolution_reads_state_then_falls_back` -- which is what the parity driver compares; the difference is in composition, and it is in the direction of noticing more.

NO `xdist_group`. Every fixture is under pytest's own `tmp_path`, the chain sandbox is built there too, and the only shared mutable state is `os.environ["PATH"]`, which `harness.fake_bin` saves and restores per process. pytest never runs two tests at once inside one worker, so no case can observe another's PATH. The one thing that WOULD need a group -- writing into the real
`.ci/media` -- is exactly what `media_chain_sandbox` exists to avoid, and `media_assert_ownership_control` refuses to proceed if that sandbox ever went back to symlinking `.ci/legacy`.
"""

import pathlib

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness, media_verify, media_verify_ext

ROOT = paths.repo_root()
MODULE = ROOT / ".ci" / "media" / "bridge.sh"

# The nine functions the split moved into this module.
MOVED = (
    "provision_start",
    "provision_stop",
    "provision_status",
    "_bridge_ip",
    "_worker_ip",
    "_bridge_ssh",
    "_bridge_rsync",
    "_build_cli_sea_cached",
    "_ensure_bridge_recording_tooling",
)

STATE = "bridge_ip=10.9.8.1\nworker_ips=10.9.8.21,10.9.8.22\n"

# The single line the off-by-one plant rewrites, and what it becomes.
IDX_ORIGINAL = 'cut -d, -f"$idx"'
IDX_PLANTED = 'cut -d, -f"$((idx + 1))"'


def run_bridge(root, code, *, module_dir=None):
    return media_verify.media_run_module(root, "bridge.sh", code, module_dir=module_dir)


def stage(directory: pathlib.Path) -> pathlib.Path:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / ".provision-state").write_text(STATE, encoding="utf-8")
    return directory


def test_every_moved_function_is_solely_owned_by_this_module(gate):
    # WHAT THIS REPLACED. Until the cutover run.sh carried its own copy of all nine, and this asserted the bodies were byte-identical. run.sh has no copies now, so the equivalent question is ownership: exactly one file defines each name, it is this module, run.sh and media.sh define none of them, and media-entry.sh resolves every name to this file's body.
    media_verify.media_assert_module_owns(gate, "bridge.sh", *MOVED)


def test_the_ssh_config_constant_lives_here_and_only_here(gate):
    # _BRIDGE_SSH_CONFIG is not a function, so the ownership assertion cannot see it, and it is the single value every other helper in this module depends on.
    lines = MODULE.read_text(encoding="utf-8").splitlines()
    if not [line for line in lines if line.startswith("_BRIDGE_SSH_CONFIG=")]:
        gate.log_fail(
            "_BRIDGE_SSH_CONFIG is not defined in bridge.sh -- this assertion has nothing to check"
        )
    media_verify_ext.assert_absent_from_origins(
        gate,
        r"^_BRIDGE_SSH_CONFIG=",
        ROOT,
        "an origin still assigns _BRIDGE_SSH_CONFIG -- the cutover left a second copy of the value",
    )
    expected = "%s/.renet/staging/.ssh/config" % pathlib.Path.home()
    in_scope = harness.run(
        [
            media_verify._BASH,
            "-c",
            "source '%s/.ci/media/media-entry.sh' >/dev/null 2>&1; "
            'printf "%%s" "${_BRIDGE_SSH_CONFIG:-}"' % ROOT,
        ]
    )
    gate.assert_eq(
        in_scope.out,
        expected,
        "media-entry.sh must put the module's _BRIDGE_SSH_CONFIG in scope",
    )
    gate.log_pass(
        "_BRIDGE_SSH_CONFIG is defined only in bridge.sh and reaches the entry point "
        "with its value intact"
    )


def test_the_ownership_assertion_can_fail(gate, tmp_path):
    # A worker index off by one is the exact defect this module invites, but a mutated BODY is no longer detectable by comparison -- there is nothing left to compare it against. What IS detectable, and what the cutover made an invariant, is a SECOND definition, so _worker_ip is the name the shared control re-plants into each origin.
    media_verify.media_assert_ownership_control(gate, tmp_path, "bridge.sh", "_worker_ip")


def test_a_planted_mutation_is_visible_to_the_behaviour_cases(gate, tmp_path):
    # The off-by-one the fidelity assertion used to guard is still guarded, by the fixture cases further down (`_worker_ip 1` must be the FIRST entry of worker_ips). This control proves those cases are reading this module: it rewrites the index in a COPY and requires the addresses they assert to change.
    staged = stage(tmp_path / "staged")
    mutant = tmp_path / "mutant"
    mutant.mkdir(parents=True, exist_ok=True)
    original = MODULE.read_text(encoding="utf-8")
    if original.count(IDX_ORIGINAL) != 1:
        gate.log_fail(
            "the off-by-one anchor %r appears %d time(s) in bridge.sh, not once, so this "
            "control would pass for the wrong reason" % (IDX_ORIGINAL, original.count(IDX_ORIGINAL))
        )
    (mutant / "bridge.sh").write_text(original.replace(IDX_ORIGINAL, IDX_PLANTED), encoding="utf-8")
    if IDX_PLANTED not in (mutant / "bridge.sh").read_text(encoding="utf-8"):
        gate.log_fail(
            "the off-by-one did not apply, so this control would pass for the wrong reason"
        )
    with harness.fake_bin("+grep +cut +uname"):
        result = run_bridge(staged, 'echo "w1=$(_worker_ip 1)"', module_dir=mutant)
    if result.rc != 0:
        gate.log_fail("the mutated copy did not run at all (output: %s)" % result.combined)
    media_verify.media_assert_mutation_swapped(
        gate, result.combined, "w1=10.9.8.21", "w1=10.9.8.22", "worker address"
    )
    gate.log_pass("an off-by-one worker index in bridge.sh changes what the fixture cases observe")


def test_run_sh_still_reaches_this_module(gate, tmp_path):
    # THE DELEGATION ITSELF, driven end to end in a sandbox repo: ./run.sh, its exec, media-entry.sh's case tree, bridge.sh, with a marker planted inside the
    # function body so nothing downstream of it runs.
    repo = media_verify_ext.media_chain_sandbox(tmp_path)
    media_verify_ext.probe(repo, "bridge.sh", "provision_start")
    with harness.fake_bin("+uname +dirname"):
        result = media_verify_ext.run(repo, "run.sh", "provision", "start", "--basic")
    if result.rc != 0:
        gate.log_fail(
            "./run.sh provision start failed in the sandbox: %s" % result.combined.strip()
        )
    gate.assert_eq(
        result.combined.strip(),
        "MEDIA_CHAIN_REACHED:provision_start:--basic",
        "run.sh must reach bridge.sh's provision_start with its arguments intact",
    )

    # CONTROL: rename the function the delegation is looking for. Nothing else changes.
    media_verify_ext.mutate(
        repo,
        ".ci/media/bridge.sh",
        r"^provision_start\(\) \{",
        "provision_start_RENAMED() {",
    )
    with harness.fake_bin("+uname +dirname"):
        broken = media_verify_ext.run(repo, "run.sh", "provision", "start", "--basic")
    if broken.rc == 0:
        gate.log_fail(
            "the chain still succeeded after provision_start was renamed in bridge.sh, "
            "so the probe proves nothing"
        )
    gate.assert_not_contains(
        broken.combined,
        "MEDIA_CHAIN_REACHED",
        "no marker may be reported once the module no longer defines the name",
    )
    gate.assert_contains(
        broken.combined,
        "provision_start",
        "the failure names the function the delegation could not find",
    )
    gate.log_pass(
        "./run.sh provision start reaches bridge.sh's provision_start, and stops reaching "
        "it when the module renames it"
    )


def test_address_resolution_reads_state_then_falls_back(gate, tmp_path):
    staged = stage(tmp_path / "staged")
    bare = tmp_path / "bare"
    bare.mkdir(parents=True, exist_ok=True)

    probe = 'echo "bridge=$(_bridge_ip) w1=$(_worker_ip 1) w2=$(_worker_ip 2)"'
    with harness.fake_bin("+grep +cut +uname"):
        staged_run = run_bridge(staged, probe)
    if staged_run.rc != 0:
        gate.log_fail("IP resolution failed (output: %s)" % staged_run.combined)
    gate.assert_contains(
        staged_run.combined, "bridge=10.9.8.1", "the bridge IP comes from .provision-state"
    )
    gate.assert_contains(
        staged_run.combined, "w1=10.9.8.21", "worker 1 is the FIRST entry of worker_ips"
    )
    gate.assert_contains(
        staged_run.combined, "w2=10.9.8.22", "worker 2 is the second, so the index is 1-based"
    )

    with harness.fake_bin("+grep +cut +uname"):
        bare_run = run_bridge(bare, probe)
    if bare_run.rc != 0:
        gate.log_fail("IP resolution failed (output: %s)" % bare_run.combined)
    gate.assert_contains(
        bare_run.combined,
        "bridge=192.168.111.1",
        "with no state file the documented default applies",
    )
    gate.assert_contains(
        bare_run.combined, "w1=192.168.111.11", "the default worker list starts at .11"
    )
    gate.assert_contains(bare_run.combined, "w2=192.168.111.12", "and its second entry is .12")
    gate.log_pass(
        "_bridge_ip and _worker_ip read .provision-state and fall back to the documented defaults"
    )


def test_the_ssh_and_rsync_wrappers_build_the_right_command(gate, tmp_path):
    # Its own fixture, for the reason the twin records: assuming the previous
    # case's state file is still there made this assert against the FALLBACK IP
    # while claiming to assert against the staged one.
    staged = stage(tmp_path / "staged")
    config = "%s/.renet/staging/.ssh/config" % pathlib.Path.home()

    with harness.fake_bin("ssh +grep +cut +uname") as fake:
        result = run_bridge(staged, "_bridge_ssh whoami")
        if result.rc != 0:
            gate.log_fail("the ssh call failed (output: %s)" % result.combined)
        call = fake.record("ssh")
    gate.assert_contains(
        call,
        "-F %s" % config,
        "the generated ops SSH config is used, never a hardcoded user or key",
    )
    gate.assert_contains(
        call, "-o BatchMode=yes", "BatchMode keeps a missing key from hanging on a prompt"
    )
    gate.assert_contains(
        call,
        "-o StrictHostKeyChecking=no",
        "a freshly provisioned VM has no known_hosts entry yet",
    )
    gate.assert_contains(call, "-o ConnectTimeout=15", "the connect timeout is pinned")
    gate.assert_contains(
        call, "10.9.8.1 whoami", "it targets the resolved bridge IP and forwards the command"
    )

    with harness.fake_bin("rsync ssh +grep +cut +uname") as fake:
        result = run_bridge(staged, "_bridge_rsync /src/ host:/dst/")
        if result.rc != 0:
            gate.log_fail("the rsync call failed (output: %s)" % result.combined)
        call = fake.record("rsync")
    gate.assert_contains(
        call, "-e ssh -F %s" % config, "rsync tunnels over the SAME generated config"
    )
    gate.assert_contains(call, "/src/ host:/dst/", "the paths are forwarded verbatim")
    gate.log_pass(
        "_bridge_ssh and _bridge_rsync pin the config path and the four connection options"
    )


def test_provisioning_is_a_thin_wrapper_over_rdc_ops(gate, tmp_path):
    # These three had NO definition anywhere in the repo once, and every caller died with "provision_start: command not found". A fake rdc.sh at the fixture root proves they exist, that they delegate, and that start still forwards "$@" -- without libvirt.
    root = tmp_path / "ops"
    root.mkdir(parents=True, exist_ok=True)
    calls = root / "rdc-calls"
    (root / "rdc.sh").write_text(
        '#!/bin/bash\nprintf "%%s\\n" "$*" >>"%s"\n' % calls, encoding="utf-8"
    )
    (root / "rdc.sh").chmod(0o755)
    calls.write_text("", encoding="utf-8")

    with harness.fake_bin("+cat +uname"):
        for code in ("provision_start --basic", "provision_stop", "provision_status"):
            result = run_bridge(root, code)
            if result.rc != 0:
                gate.log_fail("%s failed (output: %s)" % (code, result.combined))
    recorded = calls.read_text(encoding="utf-8")
    gate.assert_contains(recorded, "ops up --basic", "start forwards its arguments to rdc ops up")
    gate.assert_contains(recorded, "ops down", "stop is rdc ops down")
    gate.assert_contains(recorded, "ops status", "status is rdc ops status")
    gate.log_pass(
        "provision start/stop/status delegate to rdc ops, and start forwards its arguments"
    )

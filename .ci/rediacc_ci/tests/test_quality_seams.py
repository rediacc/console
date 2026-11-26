"""The shared seam reader (`rediacc_ci.quality.seams`) and its adoption by the quality gates.

Two halves. The unit half drives `scratch_root` and `floor` directly, both directions: a path inside the temp directory is honoured, one outside is ignored with a note, a lowered floor needs a scratch root and a zero floor is refused whatever it says. The adoption half imports each gate module in a fresh interpreter with its seam pointed OUTSIDE the temp directory and requires the module to still scan the repository, which is the claim a unit test of the helper cannot make: a module that kept its own `os.environ.get(...) or default` would pass the unit half and fail here.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import tempfile

import pytest

from rediacc_ci import paths
from rediacc_ci.quality import seams
from rediacc_ci.quality import tmpfs_health as th
from rediacc_ci.quality import trap_registry as TR

REPO = paths.repo_root()
PKG = pathlib.Path(__file__).resolve().parents[1]  # .ci/rediacc_ci


def _outside_temp() -> pathlib.Path:
    """A real directory outside the temp directory: the repository's own `.ci/config`."""
    candidate = REPO / ".ci" / "config"
    if seams.inside_temp(candidate):
        pytest.skip("the repository itself lives inside the temp directory")
    return candidate


# --------------------------------------------------------------------------- the helper


def test_scratch_root_honours_a_path_inside_temp(tmp_path, capsys):
    assert seams.scratch_root("X_ROOT", str(tmp_path)) == tmp_path.resolve()
    assert capsys.readouterr().err == "", "an honoured seam needs no note"


def test_scratch_root_ignores_a_path_outside_temp_and_says_so(capsys):
    outside = _outside_temp()
    assert seams.scratch_root("X_ROOT", str(outside)) is None
    err = capsys.readouterr().err
    assert "X_ROOT" in err
    assert "not a private scratch path in the temp directory" in err


@pytest.mark.parametrize("raw", [None, ""])
def test_scratch_root_unset_is_silent(raw, capsys):
    assert seams.scratch_root("X_ROOT", raw) is None
    assert capsys.readouterr().err == ""


def test_scratch_root_refuses_a_symlink_that_escapes_temp(tmp_path):
    link = tmp_path / "link"
    link.symlink_to(_outside_temp())
    assert seams.scratch_root("X_ROOT", str(link)) is None


def _repo_tmpdir() -> pathlib.Path:
    """A directory inside the repository to point TMPDIR at: the move findings a66ada74.1 and a66ada74.2 name."""
    fake = REPO / ".ci" / "cache" / "seams-fake-tmpdir"
    (fake / "scan").mkdir(parents=True, exist_ok=True)
    return fake


def test_scratch_root_ignores_tmpdir_moved_onto_the_repository(monkeypatch, capsys):
    """TMPDIR names a directory in the repository and the seam points inside it: `tempfile.gettempdir()` would call that temp, the system base does not."""
    fake = _repo_tmpdir()
    monkeypatch.setenv("TMPDIR", os.fspath(fake))
    # tempfile caches its answer; drop it so TMPDIR is read.
    monkeypatch.setattr(tempfile, "tempdir", None)
    assert pathlib.Path(tempfile.gettempdir()).resolve() == fake.resolve(), (
        "the plant did not move tempfile's temp"
    )
    assert seams.scratch_root("X_ROOT", os.fspath(fake / "scan")) is None
    assert "X_ROOT" in capsys.readouterr().err


def test_scratch_root_ignores_a_world_writable_directory_under_temp(tmp_path, capsys):
    """/tmp is world-writable, so a tree another user could plant is refused: the seam itself, and a seam below such a directory."""
    shared = tmp_path / "shared"
    (shared / "below").mkdir(parents=True)
    shared.chmod(0o777)
    try:
        assert seams.scratch_root("X_ROOT", os.fspath(shared)) is None
        assert seams.scratch_root("X_ROOT", os.fspath(shared / "below")) is None
        err = capsys.readouterr().err
        assert "group- or other-writable" in err
    finally:
        shared.chmod(0o700)


def test_scratch_root_ignores_a_directory_owned_by_another_uid(tmp_path, monkeypatch, capsys):
    """A directory under temp whose owner is not the current uid is refused; the other owner is simulated by an `os.stat` that reports uid + 1 for it."""
    planted = tmp_path / "planted"
    planted.mkdir()
    real_stat = os.stat
    target = planted.resolve()

    def fake_stat(path, *args, **kwargs):
        info = real_stat(path, *args, **kwargs)
        if pathlib.Path(path) == target:
            fields = list(info)
            fields[4] = os.getuid() + 1  # st_uid
            return os.stat_result(fields)
        return info

    monkeypatch.setattr(os, "stat", fake_stat)
    assert seams.scratch_root("X_ROOT", os.fspath(planted)) is None
    assert "owned by uid" in capsys.readouterr().err


def test_scratch_root_honours_a_private_mkdtemp_directory(capsys):
    """CONTROL: a 0700 `mkdtemp` directory under the system temp base, the shape every fixture has, is honoured, and so are a file and a not-yet-created path inside it."""
    made = pathlib.Path(tempfile.mkdtemp(dir=seams.system_temp_base()))
    try:
        assert (made.stat().st_mode & 0o777) == 0o700
        assert seams.scratch_root("X_ROOT", os.fspath(made)) == made.resolve()
        (made / "baseline.txt").write_text("x\n", encoding="utf-8")
        assert seams.scratch_root("X_ROOT", os.fspath(made / "baseline.txt")) is not None
        assert seams.scratch_root("X_ROOT", os.fspath(made / "not" / "yet")) is not None
        assert capsys.readouterr().err == ""
    finally:
        (made / "baseline.txt").unlink(missing_ok=True)
        made.rmdir()


def test_scratch_root_ignores_the_temp_base_itself(capsys):
    """The system temp base itself is shared, never a private scratch root."""
    base = seams.system_temp_base()
    assert base is not None
    assert seams.scratch_root("X_ROOT", os.fspath(base)) is None
    assert "X_ROOT" in capsys.readouterr().err


@pytest.mark.parametrize("literal", seams.SYSTEM_TEMP_CANDIDATES)
def test_scratch_root_ignores_every_literal_temp_candidate(literal, capsys):
    """Whichever candidate the host picks as the base, none of /tmp, /var/tmp or /usr/tmp is a private scratch root, so the /tmp refusal holds on a tmpfs /tmp host too."""
    assert seams.scratch_root("X_ROOT", literal) is None
    assert "X_ROOT" in capsys.readouterr().err


def test_scratch_root_says_so_when_no_temp_directory_is_usable(monkeypatch, tmp_path, capsys):
    """CONTROL for the above: with no usable candidate there is no base, and the refusal says so rather than raising a TypeError."""
    monkeypatch.setattr(seams, "SYSTEM_TEMP_CANDIDATES", (str(tmp_path / "absent"),))
    assert seams.system_temp_base() is None
    assert seams.scratch_root("X_ROOT", os.fspath(tmp_path)) is None
    assert "no system temp directory" in capsys.readouterr().err


def test_floor_default_without_override():
    assert seams.floor("X_MIN", None, 8, honoured=True) == 8
    assert seams.floor("X_MIN", "", 8, honoured=False) == 8


def test_floor_lowered_needs_a_scratch_root(capsys):
    assert seams.floor("X_MIN", "1", 8, honoured=False) == 8
    assert "X_MIN" in capsys.readouterr().err
    assert seams.floor("X_MIN", "1", 8, honoured=True) == 1


def test_floor_raised_is_kept_without_permission():
    assert seams.floor("X_MIN", "50", 8, honoured=False) == 50


def test_floor_zero_is_refused_whatever_it_says():
    assert seams.floor("X_MIN", "0", 8, honoured=True) == 1
    with pytest.raises(ValueError, match="at least 1"):
        seams.floor("X_MIN", None, 0, honoured=True)


def test_floor_rejects_a_non_integer():
    with pytest.raises(ValueError, match="invalid literal"):
        seams.floor("X_MIN", "many", 8, honoured=True)


# --------------------------------------------------------------------------- the gates

# (module, attribute holding the scan root, the seam naming it)
ROOT_SEAMS = [
    ("actions_allowlist", "ROOT", "ACTIONS_ALLOWLIST_ROOT"),
    ("bws_map", "ROOT", "BWS_MAP_ROOT"),
    ("docker_npm_pins", "ROOT", "DOCKER_NPM_PINS_ROOT"),
    ("format_scope", "ROOT", "FORMAT_SCOPE_ROOT"),
    ("language_policy", "ROOT", "LANGUAGE_POLICY_ROOT"),
    ("syncpack_sources", "ROOT", "SYNCPACK_SOURCES_ROOT"),
    ("plan_boxes", "ROOT", "PLAN_BOXES_ROOT"),
    ("plan_citations", "ROOT", "PLAN_CITATIONS_ROOT"),
    ("decision_ids", "ROOT", "DECISION_IDS_ROOT"),
    ("resprofile", "ROOT", "RESPROFILE_ROOT"),
]

# (module, attribute holding the floor, the floor's seam, the root seam that licenses it, the default)
FLOOR_SEAMS = [
    ("actions_allowlist", "MIN_ACTIONS", "ACTIONS_ALLOWLIST_MIN", "ACTIONS_ALLOWLIST_ROOT", 8),
    ("docker_npm_pins", "MIN_DOCKERFILES", "DOCKER_NPM_PINS_MIN", "DOCKER_NPM_PINS_ROOT", 6),
    ("bws_map", "MIN_MAP_ENTRIES", "BWS_MIN_MAP_ENTRIES", "BWS_MAP_ROOT", 30),
    ("syncpack_sources", "MIN_MANIFESTS", "SYNCPACK_SOURCES_MIN", "SYNCPACK_SOURCES_ROOT", 8),
    ("plan_lifecycle", "MIN_PLAN_FILES", "PLAN_FOLDERS_MIN_PLANS", "PLAN_FOLDERS_ROOT", 20),
    ("tree_shape", "MIN_ROOT_FILES", "TREE_SHAPE_MIN_ROOT", "TREE_SHAPE_ROOT", 10),
]


def _attr(module: str, attr: str, env: dict[str, str]) -> tuple[str, str]:
    """`<module>.<attr>` read in a fresh interpreter under `env`, as (stdout, stderr)."""
    code = "import rediacc_ci.quality.%s as m; print(m.%s)" % (module, attr)
    full = {
        k: v for k, v in os.environ.items() if k.isupper() and not k.endswith(("_ROOT", "_MIN"))
    }
    full.update(env)
    full["PYTHONPATH"] = os.fspath(PKG.parent)
    run = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env=full, check=False
    )
    assert run.returncode == 0, "importing %s failed:\n%s" % (module, run.stderr)
    return run.stdout.strip(), run.stderr


@pytest.mark.parametrize(("module", "attr", "seam"), ROOT_SEAMS)
def test_a_root_seam_outside_temp_is_ignored_on_a_plain_run(module, attr, seam):
    value, err = _attr(module, attr, {seam: os.fspath(_outside_temp())})
    assert value == str(REPO), "%s still scans %s" % (module, value)
    assert seam in err
    assert "not a private scratch path in the temp directory" in err


@pytest.mark.parametrize(("module", "attr", "seam"), ROOT_SEAMS)
def test_a_root_seam_under_a_moved_tmpdir_is_ignored_on_a_plain_run(module, attr, seam):
    """TMPDIR set to a repository directory does not make a seam inside it honoured (finding 321c4189.1, the a66ada74 class)."""
    fake = _repo_tmpdir()
    value, err = _attr(module, attr, {"TMPDIR": os.fspath(fake), seam: os.fspath(fake / "scan")})
    assert value == str(REPO), "%s still scans %s" % (module, value)
    assert seam in err


@pytest.mark.parametrize(
    ("module", "attr", "seam"),
    [row for row in ROOT_SEAMS if row[0] in {"actions_allowlist", "bws_map", "syncpack_sources"}],
)
def test_a_root_seam_inside_temp_is_honoured(module, attr, seam, tmp_path):
    value, err = _attr(module, attr, {seam: os.fspath(tmp_path)})
    assert value == str(tmp_path.resolve())
    assert err == ""


# (module, expression the module answers its root with, the seam naming it, the answer without the seam). 321c4189.3: the adopters whose root is a function or a private table, not a module attribute.
ROOT_EXPR_SEAMS = [
    ("gate_argv", "scan_root()", "GATE_ARGV_SCAN_ROOT", str(REPO)),
    ("plan_lifecycle", "resolve_root()[0]", "PLAN_FOLDERS_ROOT", str(REPO)),
    ("tree_shape", "repo_root()", "TREE_SHAPE_ROOT", str(REPO)),
    (
        "hook_exec_baseline",
        "_HOOK_PKG['parent']",
        "HOOK_EXEC_COUNTER_DIR",
        str(REPO / ".claude"),
    ),
]
_EXPR_ROWS = ROOT_EXPR_SEAMS


@pytest.mark.parametrize(("module", "expr", "seam", "default"), _EXPR_ROWS)
def test_an_expression_root_seam_outside_temp_is_ignored(module, expr, seam, default):
    value, err = _attr(module, expr, {seam: os.fspath(_outside_temp())})
    assert value == default, "%s still answers %s" % (module, value)
    assert seam in err


@pytest.mark.parametrize(("module", "expr", "seam"), [row[:3] for row in _EXPR_ROWS])
def test_an_expression_root_seam_inside_temp_is_honoured(module, expr, seam, tmp_path):
    value, err = _attr(module, expr, {seam: os.fspath(tmp_path)})
    assert value == str(tmp_path.resolve()), "%s ignored its scratch seam" % module
    assert err == ""


@pytest.mark.parametrize("row", FLOOR_SEAMS, ids=[row[0] for row in FLOOR_SEAMS])
def test_a_lowered_floor_without_a_scratch_root_is_ignored(row):
    module, attr, seam, _root_seam, default = row
    value, err = _attr(module, attr, {seam: "1"})
    assert value == str(default)
    assert seam in err


@pytest.mark.parametrize("row", FLOOR_SEAMS, ids=[row[0] for row in FLOOR_SEAMS])
def test_a_lowered_floor_with_a_scratch_root_is_honoured(row, tmp_path):
    module, attr, seam, root_seam, _default = row
    value, _ = _attr(module, attr, {seam: "1", root_seam: os.fspath(tmp_path)})
    assert value == "1"


@pytest.mark.parametrize("row", FLOOR_SEAMS, ids=[row[0] for row in FLOOR_SEAMS])
def test_a_zero_floor_is_never_zero(row, tmp_path):
    module, attr, seam, root_seam, _default = row
    value, _ = _attr(module, attr, {seam: "0", root_seam: os.fspath(tmp_path)})
    assert value == "1"


def test_trap_registry_process_seam_outside_temp_is_ignored(capsys):
    outside = _outside_temp()
    saved = os.environ.get("TRAP_CORPUS")
    os.environ["TRAP_CORPUS"] = os.fspath(outside / "TRAPS.md")
    try:
        resolved = TR.resolve_seams(REPO)
    finally:
        if saved is None:
            os.environ.pop("TRAP_CORPUS", None)
        else:
            os.environ["TRAP_CORPUS"] = saved
    assert resolved["TRAP_CORPUS"] == REPO.joinpath(*TR.SEAMS["TRAP_CORPUS"])
    assert "TRAP_CORPUS" in capsys.readouterr().err


def _fake_candidates(monkeypatch, tmp_path, mounts_text):
    """Three real directories standing in for /tmp, /var/tmp and /usr/tmp, and a mounts file naming their filesystems."""
    names = ("tmp", "vartmp", "usrtmp")
    dirs = [tmp_path / name for name in names]
    for directory in dirs:
        directory.mkdir()
    mounts = tmp_path / "mounts"
    mounts.write_text(mounts_text.format(*[d.resolve() for d in dirs]))
    monkeypatch.setattr(seams, "SYSTEM_TEMP_CANDIDATES", tuple(str(d) for d in dirs))
    monkeypatch.setattr(seams, "PROC_MOUNTS", str(mounts))
    return [d.resolve() for d in dirs]


def test_system_temp_base_prefers_var_tmp_when_tmp_is_a_tmpfs(monkeypatch, tmp_path):
    dirs = _fake_candidates(
        monkeypatch, tmp_path, "tmpfs {0} tmpfs rw 0 0\n/dev/sda1 {1} ext4 rw 0 0\n"
    )
    assert seams.system_temp_base() == dirs[1]


def test_system_temp_base_keeps_tmp_when_it_is_on_disk(monkeypatch, tmp_path):
    dirs = _fake_candidates(
        monkeypatch, tmp_path, "/dev/sda1 {0} ext4 rw 0 0\n/dev/sda1 {1} ext4 rw 0 0\n"
    )
    assert seams.system_temp_base() == dirs[0]


def test_system_temp_base_keeps_the_old_order_when_mounts_are_unreadable(monkeypatch, tmp_path):
    dirs = _fake_candidates(monkeypatch, tmp_path, "tmpfs {0} tmpfs rw 0 0\n")
    monkeypatch.setattr(seams, "PROC_MOUNTS", str(tmp_path / "no-such-mounts"))
    assert seams.system_temp_base() == dirs[0]


def test_system_temp_base_keeps_tmpfs_tmp_when_nothing_else_is_on_disk(monkeypatch, tmp_path):
    dirs = _fake_candidates(
        monkeypatch,
        tmp_path,
        "tmpfs {0} tmpfs rw 0 0\ntmpfs {1} tmpfs rw 0 0\ntmpfs {2} tmpfs rw 0 0\n",
    )
    assert seams.system_temp_base() == dirs[0]


def test_system_temp_base_uses_the_longest_mount_point_not_the_first_or_last(monkeypatch, tmp_path):
    """A real mount table lists `/` first, and a parent mount may also come after the candidate: only the longest match decides."""
    dirs = _fake_candidates(monkeypatch, tmp_path, "tmpfs {0} tmpfs rw 0 0\n")
    root_first = "/dev/sda1 / ext4 rw 0 0\ntmpfs {0} tmpfs rw 0 0\n"
    (tmp_path / "mounts").write_text(root_first.format(*dirs))
    assert seams.system_temp_base() == dirs[1]
    root_last = "tmpfs {0} tmpfs rw 0 0\n/dev/sda1 / ext4 rw 0 0\n"
    (tmp_path / "mounts").write_text(root_last.format(*dirs))
    assert seams.system_temp_base() == dirs[1]


def test_system_temp_base_reads_a_mount_point_with_a_tab_or_backslash(monkeypatch, tmp_path):
    """/proc/mounts escapes space, tab and backslash as octal; all of them are undone before the lookup."""
    dirs = _fake_candidates(monkeypatch, tmp_path, "")
    odd = tmp_path / "odd\t name\\x"
    odd.mkdir()
    odd = odd.resolve()
    escaped = os.fspath(odd).replace("\\", "\\134").replace("\t", "\\011").replace(" ", "\\040")
    assert escaped != os.fspath(odd)
    monkeypatch.setattr(seams, "SYSTEM_TEMP_CANDIDATES", (os.fspath(odd), os.fspath(dirs[1])))
    (tmp_path / "mounts").write_text("tmpfs %s tmpfs rw 0 0\n" % escaped)
    assert seams.system_temp_base() == dirs[1]


def test_tmpfs_health_cli_runs_selftest_or_the_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    """db09591e.1: `cli` is the gate's entry point; `--selftest` runs only the controls, a plain run checks the paths and returns 1 on a red one."""
    ran: list[str] = []
    monkeypatch.setattr(th, "controls", lambda: ran.append("controls"))
    monkeypatch.setattr(th, "main", lambda: ran.append("main") or 7)
    assert th.cli(["--selftest"]) == 0
    assert ran == ["controls"]
    assert th.cli([]) == 7
    assert ran == ["controls", "main"]


def test_tmpfs_health_main_is_red_on_an_exhausted_path_and_green_on_a_healthy_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """db09591e.1: the plain-run path of `cli` reaches `main`, which exits 1 when a checked path has too few inodes."""
    monkeypatch.setattr(th, "controls", lambda: None)
    monkeypatch.setattr(th, "CHECK_PATHS", ["/p"])
    monkeypatch.setattr(
        th.os, "statvfs", lambda _p: os.statvfs_result((0, 0, 0, 0, 0, 1000, 2, 2, 0, 255))
    )
    assert th.cli([]) == 1
    monkeypatch.setattr(
        th.os, "statvfs", lambda _p: os.statvfs_result((0, 0, 0, 0, 0, 1000, 900, 900, 0, 255))
    )
    assert th.cli([]) == 0

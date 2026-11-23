"""The shared seam reader (`rediacc_ci.quality.seams`) and its adoption by the quality gates.

Two halves. The unit half drives `scratch_root` and `floor` directly, both directions: a path inside the temp directory is honoured, one outside is ignored with a note, a lowered floor needs a scratch root and a zero floor is refused whatever it says. The adoption half imports each gate module in a fresh interpreter with its seam pointed OUTSIDE the temp directory and requires the module to still scan the repository, which is the claim a unit test of the helper cannot make: a module that kept its own `os.environ.get(...) or default` would pass the unit half and fail here.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

import pytest

from rediacc_ci import paths
from rediacc_ci.quality import seams
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
    assert "outside the temp directory" in err


@pytest.mark.parametrize("raw", [None, ""])
def test_scratch_root_unset_is_silent(raw, capsys):
    assert seams.scratch_root("X_ROOT", raw) is None
    assert capsys.readouterr().err == ""


def test_scratch_root_refuses_a_symlink_that_escapes_temp(tmp_path):
    link = tmp_path / "link"
    link.symlink_to(_outside_temp())
    assert seams.scratch_root("X_ROOT", str(link)) is None


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
    assert "outside the temp directory" in err


@pytest.mark.parametrize(
    ("module", "attr", "seam"),
    [row for row in ROOT_SEAMS if row[0] in {"actions_allowlist", "bws_map", "syncpack_sources"}],
)
def test_a_root_seam_inside_temp_is_honoured(module, attr, seam, tmp_path):
    value, err = _attr(module, attr, {seam: os.fspath(tmp_path)})
    assert value == str(tmp_path.resolve())
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

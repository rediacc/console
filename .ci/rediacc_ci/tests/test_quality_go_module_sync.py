"""`rediacc_ci.quality.go_module_sync` against the discovery it replaces.

WHAT IS WORTH TESTING HERE, and it is not the `go mod tidy -diff` call. That part is one subprocess whose verdict is Go's, and the shadow ledger `.ci/shadow/w7p2-go-module-sync.observations.jsonl` drives it end to end over five distinct trees with real untidy modules. What the ledger cannot isolate is
the DISCOVERY -- a `grep -rln --include=go.mod` pipeline whose four properties
(basename matching, the `./` prefix, symlinks not followed, `node_modules` as a SUBSTRING) each decide which modules the gate is even aware of. A discovery that quietly narrows turns this gate green while the coupling it guards rots.

So every case below compares the Python against the REAL pipeline under bash.
"""

import os
import pathlib

from rediacc_ci import paths
from rediacc_ci.quality import go_module_sync as gms
from rediacc_ci.tests import differential as diff

# The twin's discovery, verbatim from check-go-module-sync.sh:61-62.
DISCOVERY = (
    'grep -rln "replace github.com/rediacc/renet" --include=go.mod . 2>/dev/null | '
    "grep -v node_modules | sort"
)

REPLACING = "module example.com/x\n\ngo 1.21\n\nreplace github.com/rediacc/renet => ./renet\n"
PLAIN = "module example.com/y\n\ngo 1.21\n"


def _bash_discovery(root: pathlib.Path) -> list[str]:
    code, out, err = diff.bash_streams(DISCOVERY, cwd=str(root))
    # `grep -v` exits 1 on no match and `sort` then succeeds; the twin runs the
    # pipeline inside a process substitution where the status is ignored, so a non-zero code here is not a failure of the test.
    assert err == "", err
    assert code in (0, 1), code
    return [line for line in out.split("\n") if line]


def test_discovery_matches_bash_on_a_populated_tree(tmp_path: pathlib.Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "go.mod").write_text(REPLACING, encoding="utf-8")
    (tmp_path / "b" / "c").mkdir(parents=True)
    (tmp_path / "b" / "c" / "go.mod").write_text(REPLACING, encoding="utf-8")
    # A module that does NOT replace renet is not a subject. Without this the comparison would agree on a discovery that matched every go.mod.
    (tmp_path / "d").mkdir()
    (tmp_path / "d" / "go.mod").write_text(PLAIN, encoding="utf-8")
    found = gms.find_modules(tmp_path)
    assert found == _bash_discovery(tmp_path)
    assert found == ["./a/go.mod", "./b/c/go.mod"]


def test_discovery_matches_bash_on_an_empty_tree(tmp_path: pathlib.Path) -> None:
    """The refusal's input. Both must answer with nothing, and the gate must
    then refuse rather than report a clean tree."""
    assert gms.find_modules(tmp_path) == []
    assert _bash_discovery(tmp_path) == []


def test_node_modules_is_a_substring_not_a_component(tmp_path: pathlib.Path) -> None:
    """`grep -v node_modules` excludes `my_node_modules_backup` too, and the
    port must be exactly as blunt or the two disagree on a real tree."""
    for name in ("node_modules", "my_node_modules_backup", "keep"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "go.mod").write_text(REPLACING, encoding="utf-8")
    assert gms.find_modules(tmp_path) == _bash_discovery(tmp_path) == ["./keep/go.mod"]


def test_include_matches_the_basename_only(tmp_path: pathlib.Path) -> None:
    """`--include=go.mod` is a basename glob: `vendor.go.mod` is not a go.mod."""
    (tmp_path / "go.mod").write_text(REPLACING, encoding="utf-8")
    (tmp_path / "vendor.go.mod").write_text(REPLACING, encoding="utf-8")
    assert gms.find_modules(tmp_path) == _bash_discovery(tmp_path) == ["./go.mod"]


def test_directory_symlinks_are_not_followed(tmp_path: pathlib.Path) -> None:
    """`grep -r` does not follow directory symlinks; `-R` would. `os.walk`
    agrees by default, and the default is asserted rather than trusted."""
    real = tmp_path / "real"
    real.mkdir()
    (real / "go.mod").write_text(REPLACING, encoding="utf-8")
    (tmp_path / "link").symlink_to(real, target_is_directory=True)
    assert gms.find_modules(tmp_path) == _bash_discovery(tmp_path) == ["./real/go.mod"]


def test_zero_modules_is_a_refusal(tmp_path: pathlib.Path, monkeypatch) -> None:
    """ZERO INPUTS IS A FAILURE. This is the whole reason the gate is written as
    a discovery rather than as a hardcoded path."""
    monkeypatch.setenv(paths.ROOT_ENV, str(tmp_path))
    assert gms.main([]) == 1


def test_an_absent_go_is_a_setup_error_not_a_verdict(tmp_path: pathlib.Path, monkeypatch) -> None:
    """Exit 2, and 2 is not 1. A gate that could not run must not be counted as
    a gate that found nothing."""
    monkeypatch.setenv(paths.ROOT_ENV, str(tmp_path))
    monkeypatch.setenv("PATH", str(tmp_path / "no-such-bin"))
    assert gms.main([]) == gms.EXIT_SETUP_ERROR == 2


def test_selftest_is_green() -> None:
    """Drives the tidy/untidy plants, which need a real Go toolchain.

    NOT SKIPPED WHEN go IS ABSENT. `selftest` records the missing toolchain as a FAILED control naming the fix, so this assertion goes red with a message that sends the reader to `https://go.dev/dl/` rather than quietly reporting a green suite that exercised only the discovery.
    """
    assert gms.selftest() == 0, (
        "go_module_sync selftest failed. If this host has no Go toolchain the "
        "selftest says so by name; install Go and re-run rather than skipping."
    )


def test_the_real_tree_is_in_sync() -> None:
    """The gate against the actual repository, which is where the coupling it
    guards actually lives."""
    assert os.path.isdir(paths.repo_root() / ".ci/scripts/private/license-mint"), (
        "the license-mint module moved; retarget this test and the gate together"
    )
    assert gms.main([]) == 0

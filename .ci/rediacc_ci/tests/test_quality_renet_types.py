"""`rediacc_ci.quality.renet_types` against the shell it replaces.

WHY A DIFFERENTIAL AND NOT A TABLE OF EXPECTED STRINGS. The whole verdict of this gate rests on one four-token shell function:

    diff -q <(grep -v '_VERSION = ' "$1") <(grep -v '_VERSION = ' "$2") >/dev/null 2>&1

and every interesting property of it is an accident of how those tools compose. `grep -v` on a MISSING file writes to the script's stderr even though the diff is redirected, and returns nothing, so the comparison says "differ" and the file lands on the stale list. `diff` ignores a missing trailing newline in the sense that matters here only because the greps have already re-emitted
the content.
The marker `_VERSION = ` is a SUBSTRING with a mandatory space on each side of
the equals sign, not an anchor, so `A_VERSION=1` is compared and
`  const X_VERSION = 1` is not. None of that is inferable; it is measured below.

They are NOT the whole gate: the whole gate is what the committed shadow ledger `.ci/shadow/w7p2-renet-types.observations.jsonl` compares over five distinct trees, against a minimal Go stand-in for `renet functions generate-types`. This file covers the seams that ledger cannot isolate.
"""

import pathlib
import tempfile

import pytest

from rediacc_ci import paths
from rediacc_ci.quality import renet_types as rt
from rediacc_ci.tests import differential as diff

# The twin's helper, verbatim, with its two arguments substituted.
_COMPARE = (
    """compare() { diff -q <(grep -v '_VERSION = ' "$1") <(grep -v '_VERSION = ' "$2") """
    """>/dev/null 2>&1; }; compare "$1" "$2" && echo same || echo differ"""
)

# Every shape the comparison has to survive, as (left, right, why). `None` means the file is not created at all.
COMPARE_CASES = [
    ("x\ny\n", "x\ny\n", "identical"),
    ("x\ny\n", "x\nz\n", "a changed line"),
    ("x\n", "x\ny\n", "an added line"),
    ("x\ny\n", "x\n", "a removed line"),
    ('A_VERSION = "v1";\nx\n', 'A_VERSION = "v2";\nx\n', "the version line is excluded"),
    ('A_VERSION = "v1";\nx\n', 'A_VERSION = "v2";\nz\n', "a real change beside a version line"),
    ("  const X_VERSION = 1;\ny\n", "  const X_VERSION = 2;\ny\n", "the marker is a SUBSTRING"),
    ("const A_VERSION=1;\n", "const A_VERSION=2;\n", "no spaces means NOT excluded"),
    ("x\ny\n", "x\ny", "a missing trailing newline"),
    ("", "", "two empty files"),
    ("", "x\n", "empty against non-empty"),
    (None, "x\n", "the LEFT file does not exist"),
    ("x\n", None, "the RIGHT file does not exist"),
    (None, None, "NEITHER file exists"),
]


@pytest.mark.parametrize(("left", "right", "why"), COMPARE_CASES)
def test_compare_matches_the_shell_helper(
    tmp_path: pathlib.Path, left: str | None, right: str | None, why: str
) -> None:
    """The verdict, run for real on both sides."""
    a, b = tmp_path / "a.ts", tmp_path / "b.ts"
    if left is not None:
        a.write_text(left, encoding="utf-8")
    if right is not None:
        b.write_text(right, encoding="utf-8")
    # `bash_streams` takes no positional arguments, so `set --` supplies the helper's `$1` and `$2` inside the script rather than beside it.
    code, out, _err = diff.bash_streams(
        "set -- a.ts b.ts\n%s" % _COMPARE, cwd=str(tmp_path), timeout=30
    )
    assert code == 0
    assert rt.compare_ignoring_version(a, b) is (out.strip() == "same"), why


def test_the_compare_table_exercises_both_directions() -> None:
    verdicts = set()
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        for left, right, _why in COMPARE_CASES:
            a, b = root / "a.ts", root / "b.ts"
            for path, content in ((a, left), (b, right)):
                if content is None:
                    path.unlink(missing_ok=True)
                else:
                    path.write_text(content, encoding="utf-8")
            verdicts.add(rt.compare_ignoring_version(a, b))
    assert verdicts == {True, False}, "the table must contain both verdicts"


def test_the_missing_file_error_matches_greps_wording(tmp_path: pathlib.Path) -> None:
    """The leak, byte for byte, because it is the port's job to leak the same.

    `2>/dev/null` on the enclosing `diff` does NOT cover a process substitution, which is easy to assume and wrong. Measured here rather than reasoned.
    """
    missing = tmp_path / "gone.ts"
    (tmp_path / "b.ts").write_text("x\n", encoding="utf-8")
    _code, _out, err = diff.bash_streams(
        "set -- gone.ts b.ts\n%s" % _COMPARE, cwd=str(tmp_path), timeout=30
    )
    assert err.strip() == "grep: gone.ts: No such file or directory"

    _lines, port_err = rt.strip_version_lines(missing)
    assert port_err == "grep: %s: No such file or directory" % missing


def test_require_submodule_skips_locally_and_fails_under_ci(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """All three rungs, against the real bash function sourced from common.sh.

    The CI rung is the one that must not be lost: common.sh's own comment says a gate that silently skips is worse than no gate at all, and names the three scanners that would report success while checking nothing.
    """
    marker = tmp_path / "go.mod"

    script = """
        source .ci/scripts/lib/common.sh
        require_submodule "%s" "Renet submodule" || echo SKIPPED
        echo "rc=$?"
    """

    # Present: the function returns 0 and prints nothing.
    marker.write_text("module x\n", encoding="utf-8")
    code, out, err = diff.bash_streams(script % marker, env=diff.env_for(CI=None))
    assert code == 0
    assert "SKIPPED" not in out
    assert err.strip() == ""
    monkeypatch.delenv("CI", raising=False)
    assert rt._require_submodule(marker, "Renet submodule") is True

    # Absent, locally: warn and return 1, which the caller turns into a skip.
    marker.unlink()
    code, out, err = diff.bash_streams(script % marker, env=diff.env_for(CI=None))
    assert code == 0
    assert "SKIPPED" in out
    assert "Renet submodule not available, skipping" in err
    assert rt._require_submodule(marker, "Renet submodule") is False

    # Absent, under CI: a HARD failure, exit 1, three lines naming the fix.
    code, out, err = diff.bash_streams(script % marker, env=diff.env_for(CI="true"))
    assert code == 1
    assert "required in CI but missing" in err
    assert "A gate skipped here would report success while checking nothing." in err
    assert "git submodule update --init" in err
    monkeypatch.setenv("CI", "true")
    with pytest.raises(SystemExit) as excinfo:
        rt._require_submodule(marker, "Renet submodule")
    assert excinfo.value.code == 1


def test_the_compared_file_list_is_the_gate() -> None:
    """Six entries, and license-tiers is one of them.

    The list is asserted rather than trusted because the twin's own comment records what its absence cost: license-tiers.generated.ts was generated into TEMP_DIR and silently ignored until it was added, which would have let it go stale forever while the gate reported "up-to-date".
    """
    assert len(rt.FILES) == 6
    assert "license-tiers.generated.ts" in rt.FILES
    assert len(set(rt.FILES)) == 6, "a duplicated entry would be compared twice"


def test_the_list_still_matches_the_bash_twins_array() -> None:
    """Drift between the two copies is invisible until a file goes stale.

    Read out of the twin rather than transcribed, so the assertion cannot be satisfied by editing this file.
    """
    twin = paths.repo_root() / ".ci/scripts/quality/check-renet-types.sh"
    text = twin.read_text(encoding="utf-8")
    body = text.split("FILES=(", 1)[1].split(")", 1)[0]
    names = [line.strip().strip('"') for line in body.split("\n") if line.strip().startswith('"')]
    assert names == list(rt.FILES)


def test_selftest_passes() -> None:
    assert rt.selftest() == 0

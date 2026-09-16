"""`rediacc_ci.quality.editorconfig` against the shell and the awk it replaces.

WHAT IS WORTH TESTING HERE, and it is not "does it see a CRLF". The shadow
ledger `.ci/shadow/w7p2-editorconfig.observations.jsonl` drives the whole gate
over five distinct trees carrying all four violation classes. What a ledger row
cannot isolate is the two pieces that decide WHICH FILES ARE EVEN LOOKED AT:

  * the awk binary classifier, whose bug the twin's own header documents (a
    path containing the substring "binary" used to exempt a us-ascii file from
    three of the four checks)
  * `file --mime-encoding`, the single binary oracle, whose verdict on a SHORT
    text file is "binary" and therefore quietly removes it from checks 1 to 3

Both are compared against the real programs below, because a classifier that
narrows turns this gate green over a corpus it stopped looking at.
"""

import pathlib
import subprocess

from rediacc_ci import paths
from rediacc_ci.quality import editorconfig as ec
from rediacc_ci.tests import differential as diff

# The classifier, verbatim from check-editorconfig.sh:56 and :94 (the same
# program appears twice in the twin, once in its control and once in the scan).
AWK_CLASSIFY = "awk -F': ' '$NF ~ /binary/ { sub(/: [^:]*$/, \"\", $0); print }'"


def _bash_classify(lines: list[str]) -> list[str]:
    """Run the twin's awk over `lines`.

    `printf '%s\\n' a b c` and NOT `printf '%s' 'a\\nb'`: `%s` does not interpret
    a backslash escape, so the second form hands awk ONE line containing the
    two characters backslash and n. The first version of this helper did that
    and the comparison failed against a single-line input, which looks like the
    classifier disagreeing when it is the harness feeding it the wrong thing.
    """
    quoted = " ".join("'%s'" % line.replace("'", "'\\''") for line in lines)
    code, out, err = diff.bash_streams("printf '%%s\\n' %s | %s" % (quoted, AWK_CLASSIFY))
    assert err == "", err
    assert code in (0, 1), code
    return [line for line in out.split("\n") if line]


def test_classifier_matches_the_twins_awk_on_the_two_control_inputs() -> None:
    """The exact two strings the twin's own control feeds it."""
    for line in ("some-binary-name.sh: us-ascii", "assets/logo.png: binary"):
        assert ec.classify_binary([line]) == _bash_classify([line]), line


def test_classifier_matches_on_padded_output() -> None:
    """`file` pads the filename column when given more than one path, so the
    real input to awk is not `a: b` but `a:       b`. A classifier that split on
    ':' rather than ': ' would still pass the control above and fail here."""
    lines = ["a.sh:       us-ascii", "b.png:      binary", "c.woff:     binary"]
    assert ec.classify_binary(lines) == _bash_classify(lines) == ["b.png", "c.woff"]


def test_classifier_matches_on_a_path_containing_a_colon_space() -> None:
    """`sub(/: [^:]*$/)` strips only the LAST field, so a path holding ': '
    survives intact. Python's `re.sub` and awk's `sub` agree here and the
    agreement is asserted rather than assumed."""
    lines = ["odd: name.png: binary", "plain.txt: us-ascii"]
    assert ec.classify_binary(lines) == _bash_classify(lines) == ["odd: name.png"]


def test_classifier_treats_a_line_with_no_separator_as_its_own_last_field() -> None:
    """awk's $NF on a line with no ': ' is the whole line. Not a real `file`
    output shape, and asserted anyway because it is the branch a defensive
    rewrite would get wrong in silence."""
    lines = ["binary", "notbinary-word"]
    assert ec.classify_binary(lines) == _bash_classify(lines)


def test_file_calls_a_short_text_file_binary(tmp_path: pathlib.Path) -> None:
    """A REPORTED TWIN BLIND SPOT, pinned so it cannot change unnoticed.

    `file --mime-encoding` answers "binary" for a one-byte text file, so such a
    file is exempted from the final-newline, BOM and CRLF checks entirely. The
    gate cannot see a missing newline on it. Both implementations share the
    oracle, so both share the hole; this asserts the hole is where it is
    believed to be rather than somewhere worse.
    """
    (tmp_path / "tiny.ts").write_bytes(b"x")
    (tmp_path / "longer.ts").write_bytes(b"const x = 1;")
    out = ec.mime_encodings(tmp_path, ["tiny.ts", "longer.ts"])
    binary = ec.classify_binary(out)
    assert "tiny.ts" in binary, out
    assert "longer.ts" not in binary, out


def test_the_nul_control_fires(tmp_path: pathlib.Path) -> None:
    """The twin refuses to report anything if this control does not fire, and
    so does the port. Driven directly rather than through main()."""
    assert ec.nul_control(tmp_path) is True


def test_the_classifier_control_passes() -> None:
    assert ec.classifier_control() is None


def test_tracked_files_matches_git_ls_files(tmp_path: pathlib.Path) -> None:
    """The enumeration, against the real git. THE `--recurse-submodules` FLAG IS
    CARRIED FROM THE TWIN AND IS A REPORTED DEFECT: the manifest lane checks out
    without submodules, so the flag buys nothing there. Compared as-is, because
    the port's job is to keep the corpus, not to widen it."""
    (tmp_path / "a.ts").write_bytes(b"const a = 1;\n")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.md").write_bytes(b"# b\n")
    subprocess.run(["git", "init", "-q", "-b", "main", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    code, out, err = diff.bash_streams(
        "git ls-files -z --recurse-submodules | tr '\\0' '\\n'", cwd=str(tmp_path)
    )
    assert (code, err) == (0, ""), err
    assert ec.tracked_files(tmp_path) == [line for line in out.split("\n") if line]


def test_every_violation_class_is_found_and_every_exemption_holds(tmp_path: pathlib.Path) -> None:
    """One pass over one fixture set, asserting BOTH directions at once."""
    files = {
        "ok.ts": b"const x = 1;\n",
        "nonewline.ts": b"const x = 1;",
        "bom.ts": b"\xef\xbb\xbfconst x = 1;\n",
        "crlf.ts": b"const x = 1;\r\n",
        "empty.ts": b"",
        "pinned.hash": b"deadbeef",
        "corrupt.ts": b"const x = 1;\x00\n",
        "logo.png": b"\x89PNG\r\n\x1a\n\x00\x00",
    }
    for name, data in files.items():
        (tmp_path / name).write_bytes(data)
    binary = {"corrupt.ts", "logo.png"}
    found = ec.scan(tmp_path, sorted(files), binary)
    assert ("NEWLINE", "nonewline.ts") in found
    assert ("BOM", "bom.ts") in found
    assert ("CRLF", "crlf.ts") in found
    assert ("NUL", "corrupt.ts") in found
    for quiet in ("ok.ts", "empty.ts", "pinned.hash", "logo.png"):
        assert [f for f in found if f[1] == quiet] == [], quiet


def test_a_symlink_is_skipped_and_its_target_is_not(tmp_path: pathlib.Path) -> None:
    (tmp_path / "real.ts").write_bytes(b"const x = 1;")
    (tmp_path / "link.ts").symlink_to(tmp_path / "real.ts")
    assert ec.scan(tmp_path, ["link.ts"], set()) == []
    assert ec.scan(tmp_path, ["real.ts"], set()) == [("NEWLINE", "real.ts")]


def test_selftest_is_green() -> None:
    assert ec.selftest() == 0


def test_the_real_tree_complies() -> None:
    """The gate against the actual repository. A red here is real editorconfig
    debt, not a broken port."""
    assert ec.main([]) == 0, "run `bash .ci/scripts/quality/check-editorconfig.sh` for the list"
    assert paths.repo_root().is_dir()

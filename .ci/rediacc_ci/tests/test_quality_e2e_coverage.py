"""`rediacc_ci.quality.e2e_coverage` against the grep and sed pipelines it replaces.

WHAT THE SHADOW LEDGER ALREADY PROVES, so that this file does not repeat it:
`.ci/shadow/w7p2-e2e-coverage.observations.jsonl` drives both implementations
end to end over five distinct committed trees, with a dead method dispatch, a
dead raw dispatch, both at once, and a contract whose oracle array is gone.
Exit codes and finding sets agree on all five.

WHAT THE LEDGER CANNOT ISOLATE is the EXTRACTION, and that is what is here. The
reverse half is three text pipelines: a bash `=~` state machine over the
generated contract, and two `grep -rn | sed -E` pairs over the harness. Each one
decides what the gate is even aware of, and each one narrows silently: a state
machine that stops matching yields an empty oracle (loud), but a sed that
extracts the wrong token yields a verdict about a verb nobody dispatched
(quiet), and a comment filter that widens skips a live line (quiet, and green).

So the cases below run the REAL bash against the Python, on the same input.
"""

import pathlib
import subprocess

from rediacc_ci.quality import e2e_coverage as e2e
from rediacc_ci.tests import differential as diff

# The twin's two sweeps, verbatim from check-e2e-coverage.sh, with the directory
# taken from $1 so a fixture can be pointed at them.
METHOD_SWEEP = (
    "grep -rn --include='*.ts' -E \"function:[[:space:]]*'[a-z0-9_]+'\" \"$1\" 2>/dev/null || true"
)
RAW_SWEEP = (
    'grep -rn --include=\'*.ts\' -E -- "--function[[:space:]]+[a-z0-9_]+" "$1" 2>/dev/null || true'
)

# The twin's verb extraction, applied to the `<line>:<code>` tail of a grep hit.
METHOD_SED = "sed -E \"s/.*function:[[:space:]]*'([a-z0-9_]+)'.*/\\1/\""
RAW_SED = 'sed -E "s/.*--function[[:space:]]+([a-z0-9_]+).*/\\1/"'

CONTRACT = """\
export const RENET_FUNCTIONS = [
  'public_only',
] as const;

export const RENET_BRIDGE_FUNCTIONS = [
  'repo_up',
  'machine_check_disk',
] as const;

export const AFTER = ['never_seen'] as const;
"""


def _bash_hits(script: str, directory: pathlib.Path) -> list[str]:
    code, out, err = diff.bash_streams("%s\n" % script, cwd=str(directory.parent))
    assert err == "", err
    assert code == 0, code
    return [line for line in out.split("\n") if line]


def _sweep(script: str, directory: pathlib.Path) -> list[str]:
    """`grep -rn <dir>` under bash, returned as `<abs-path>:<line>` pairs.

    The match text is dropped: it is the part the two implementations are
    ALLOWED to render differently, and keeping it here would make this file a
    byte comparison of grep's output rather than a comparison of what the two
    sweeps FIND.
    """
    proc = subprocess.run(
        ["bash", "-c", "set -e\n%s" % script, "_", str(directory)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.stderr == "", proc.stderr
    out: list[str] = []
    for line in proc.stdout.split("\n"):
        if not line:
            continue
        path, _, rest = line.partition(":")
        number, _, _code = rest.partition(":")
        out.append("%s:%s" % (path, number))
    return out


def _python_sweep(pairs: list[tuple[str, str, int]]) -> list[str]:
    return sorted("%s:%d" % (path, number) for _verb, path, number in pairs)


def _harness(root: pathlib.Path) -> pathlib.Path:
    src = root / "src"
    src.mkdir(parents=True, exist_ok=True)
    (src / "methods.ts").write_text(
        "const a = { function: 'repo_up' };\n"
        "const b = { function: 'datastore_init' };\n"
        "const c = { functionish: 'not_a_match' };\n",
        encoding="utf-8",
    )
    (src / "raw.ts").write_text(
        "// functions once --function datastore_unmount is the old path\n"
        "sh('renet functions once --function kube_csi_template');\n"
        "  * --function in_a_block_comment\n",
        encoding="utf-8",
    )
    (src / "notes.md").write_text("function: 'wrong_extension'\n", encoding="utf-8")
    return src


# ---------------------------------------------------------------------------
# The oracle state machine
# ---------------------------------------------------------------------------


def test_oracle_reads_only_the_bridge_array() -> None:
    assert e2e.bridge_functions(CONTRACT) == ["repo_up", "machine_check_disk"]


def test_oracle_mirror_ignores_the_arrays_on_either_side() -> None:
    """The half a reviewer waves through: it must NOT read the neighbours.

    `RENET_FUNCTIONS` is the PUBLIC surface and omits the internal verbs this
    gate exists to check, so a state machine that opened on the wrong assignment
    would report every internal dispatch as dead.
    """
    names = e2e.bridge_functions(CONTRACT)
    assert "public_only" not in names
    assert "never_seen" not in names


def test_oracle_stops_at_as_const() -> None:
    text = "RENET_BRIDGE_FUNCTIONS = [\n  'a',\n] as const\n  'b'\n"
    assert e2e.bridge_functions(text) == ["a"]


def test_oracle_takes_the_first_name_per_line_like_bash_regex_match() -> None:
    """bash `=~` fills BASH_REMATCH from the FIRST match in the subject."""
    text = "RENET_BRIDGE_FUNCTIONS = [\n  'a', 'b',\n] as const\n"
    assert e2e.bridge_functions(text) == ["a"]


def test_oracle_empty_is_reported_as_empty_not_guessed() -> None:
    assert e2e.bridge_functions("export const X = ['a'] as const;\n") == []


# ---------------------------------------------------------------------------
# The two sweeps, against the real greps
# ---------------------------------------------------------------------------


def test_method_sweep_matches_bash_grep(tmp_path: pathlib.Path) -> None:
    src = _harness(tmp_path)
    assert _python_sweep(e2e.method_dispatches(e2e.ts_files(src))) == sorted(
        _sweep(METHOD_SWEEP, src)
    )


def test_raw_sweep_finds_the_same_lines_as_bash_grep(tmp_path: pathlib.Path) -> None:
    """The GREP halves must agree; the comment filter is applied afterward.

    Compared before the filter on purpose. If the two disagreed about which
    lines grep matches, a later agreement about which of them are comments would
    be an agreement about a different set.
    """
    src = _harness(tmp_path)
    hits = sorted(
        "%s:%d" % (path, number)
        for path in e2e.ts_files(src)
        for number, _line in e2e._hits(path, e2e.RAW_GREP_RE)
    )
    assert hits == sorted(_sweep(RAW_SWEEP, src))


def test_raw_sweep_skips_comment_lines_and_keeps_the_live_one(tmp_path: pathlib.Path) -> None:
    src = _harness(tmp_path)
    verbs = sorted(v for v, _f, _n in e2e.raw_dispatches(e2e.ts_files(src)))
    assert verbs == ["kube_csi_template"]


def test_only_ts_files_are_subjects(tmp_path: pathlib.Path) -> None:
    """`--include='*.ts'` is a BASENAME match, so the .md is invisible."""
    src = _harness(tmp_path)
    assert all(p.endswith(".ts") for p in e2e.ts_files(src))
    assert "wrong_extension" not in [v for v, _f, _n in e2e.method_dispatches(e2e.ts_files(src))]


def test_symlinked_directories_are_not_followed(tmp_path: pathlib.Path) -> None:
    """`grep -r` does not follow directory symlinks; `-R` would."""
    src = _harness(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "hidden.ts").write_text("const z = { function: 'ghost' };\n", encoding="utf-8")
    (src / "link").symlink_to(outside, target_is_directory=True)
    verbs = [v for v, _f, _n in e2e.method_dispatches(e2e.ts_files(src))]
    assert "ghost" not in verbs
    assert sorted(_sweep(METHOD_SWEEP, src)) == _python_sweep(
        e2e.method_dispatches(e2e.ts_files(src))
    )


# ---------------------------------------------------------------------------
# The verb extraction, against the real seds
# ---------------------------------------------------------------------------


def _bash_extract(sed: str, subject: str) -> str:
    proc = subprocess.run(
        ["bash", "-c", "printf '%s' \"$1\" | " + sed, "_", subject],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def test_method_verb_extraction_is_greedy_exactly_as_sed_is() -> None:
    """TWO LITERALS ON ONE LINE: sed's leading `.*` is greedy, so the LAST wins.

    This is a defect in the twin, reported and deliberately NOT fixed in the
    port: a port that corrects a bug changes the verdict, and the differential
    would rule MISMATCH on the very tree that would prove the fix right.
    """
    subject = "7:send({ function: 'first' }); send({ function: 'second' });"
    assert e2e.METHOD_VERB_RE.match(subject).group(1) == "second"
    assert _bash_extract(METHOD_SED, subject) == "second"


def test_raw_verb_extraction_is_greedy_exactly_as_sed_is() -> None:
    subject = "2:sh('a --function alpha; b --function beta');"
    assert e2e.RAW_VERB_RE.match(subject).group(1) == "beta"
    assert _bash_extract(RAW_SED, subject) == "beta"


def test_horizontal_space_class_does_not_widen_to_unicode() -> None:
    """`[[:space:]]` under LC_ALL=C is ASCII. `\\s` on a str pattern is not.

    A non-breaking space between `function:` and the verb would be a dispatch to
    a `\\s`-based port and not to the twin, which is a difference invisible in
    every ASCII fixture.
    """
    assert e2e.METHOD_GREP_RE.search("function: 'x'") is None
    assert e2e.METHOD_GREP_RE.search("function:\t'x'") is not None


# ---------------------------------------------------------------------------
# The prefix strip, which is not a relpath computation
# ---------------------------------------------------------------------------


def test_relative_is_a_prefix_strip_not_a_path_walk(tmp_path: pathlib.Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    assert e2e._relative(root, str(root / "a" / "b.ts")) == "a/b.ts"
    # Outside the root, bash leaves the string untouched rather than inventing
    # a `../..` chain, and so does this.
    other = str(tmp_path / "elsewhere" / "c.ts")
    assert e2e._relative(root, other) == other


def test_selftest_passes() -> None:
    """The gate's own both-direction controls, driven as a test.

    A `--selftest` that nothing runs is a control nobody proved, and the
    anti-vacuity contract makes the selftest the thing that must run BEFORE any
    real scan. Running it here means a regression in the controls themselves is
    a red test rather than a green gate.
    """
    assert e2e.selftest() == 0

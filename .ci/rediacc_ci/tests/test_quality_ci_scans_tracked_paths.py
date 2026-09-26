"""`rediacc_ci.quality.ci_scans_tracked_paths` against the bash it replaces.

WHAT IS WORTH TESTING HERE. The shadow ledger `.ci/shadow/w7p2-ci-scans-tracked-paths.observations.jsonl` drives the whole gate over five distinct trees: an offender in a workflow, one in a CI script, one in both, an `npx tsx` form, and a two-level ignored root. What a ledger row cannot isolate is the piece the twin spends most of its comments on: the pair of tests that decide
whether a line is EXECUTING an ignored path or merely NAMING one.

That pair is a bash `case` statement with eleven patterns and a second `case` that strips the command keyword. It is re-run here as real bash, over the same inputs, and compared token for token. A port that widened it by one pattern would turn every artifact path list into a finding, and a gate that cries wolf is one the next session learns to route around.

Also compared: the sed escaping (a seven-character class whose spelling looks like a typo and is not), and the fact that `git check-ignore` SKIPS TRACKED PATHS. That last one is not academic. Force-adding the fixture's ignored directory made all five differential trees report VACUOUS_BOTH_EMPTY: the plant had silently stopped being a plant, and nothing about the gate was wrong.
"""

import pathlib
import subprocess

from rediacc_ci.quality import ci_scans_tracked_paths as st
from rediacc_ci.tests import differential as diff

# The twin's two case statements, lines 57-78, lifted verbatim into a driver that
# prints the executable token (or nothing). Only the `stripped=` assignment and
# the final `printf` are added, so what runs here is the gate's own logic.
TWIN_CASE = r"""
stripped="$1"
case "$stripped" in
    run:* | -\ run:* | bash\ * | sh\ * | ./* | source\ * | .\ * | \
        npm\ * | npx\ * | node\ * | python3\ * | tsx\ *) ;;
    *) exit 0 ;;
esac
exe="$stripped"
exe="${exe#- }"
exe="${exe#run: }"
case "$exe" in
    bash\ * | sh\ * | source\ * | node\ * | python3\ * | tsx\ *) exe="${exe#* }" ;;
    npx\ *)
        exe="${exe#npx }"
        exe="${exe#* }"
        ;;
    npm\ *) exit 0 ;;
esac
exe="${exe%% *}"
printf '%s' "$exe"
"""

CASES = (
    "- run: bash x/y.sh",
    "run: bash x/y.sh",
    "bash x/y.sh",
    "sh x/y.sh",
    "./x/y.sh --flag",
    "source x/y.sh",
    ". x/y.sh",
    "npm run build",
    "npx tsx x/y.ts",
    "node x/y.js",
    "python3 x/y.py",
    "tsx x/y.ts",
    "path: private/bin/renet-linux-*",
    "see private/growth/.ci/checks for why",
    "OUT=private/bin",
    "- run: echo hello",
    "run: npm ci",
    "bash",
)


def _twin_token(line: str) -> str | None:
    """What the twin's two case statements make of one line. None means skipped."""
    proc = subprocess.run(
        ["bash", "-c", TWIN_CASE, "driver", line],
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr.decode("utf-8")
    out = proc.stdout.decode("utf-8")
    return out if out != "" else None


def test_executable_token_agrees_with_the_twins_case_statements() -> None:
    """Eighteen lines, both directions, compared against real bash.

    The `None` answers are as load-bearing as the tokens: they are the lines the gate must NOT flag, and they are the reason this gate is still switched on.
    """
    for line in CASES:
        assert st.executable_token(line) == _twin_token(line), line


def test_escaping_matches_the_twins_sed() -> None:
    """`sed 's/[].[^$*\\/]/\\\\&/g'`, run for real, on every character it names."""
    for name in ("private/bin", "node_modules", "a.b", "we[ird]", "d^ollar$", "st*ar"):
        code, out, _err = diff.bash_streams(
            "printf '%%s' '%s' | sed 's/[].[^$*\\/]/\\\\&/g'" % name
        )
        assert code == 0
        assert st.escape_for_ere(name) == out, name


def test_alternation_matches_paste() -> None:
    """`paste -sd'|'` joins the escaped names with a single pipe."""
    names = ["private/bin", "node_modules", "a.b"]
    code, out, _err = diff.bash_streams(
        "printf '%%s\\n' %s | sed 's/[].[^$*\\/]/\\\\&/g' | paste -sd'|'"
        % " ".join("'%s'" % n for n in names)
    )
    assert code == 0
    # `paste` ends its output with a newline; the twin captures it in a `$( )`, which strips it. Compared against the value the twin actually holds.
    assert st.roots_pattern(names) == out.rstrip("\n")


def test_check_ignore_skips_tracked_paths(tmp_path: pathlib.Path) -> None:
    """The reason a force-added fixture silently stops being a plant.

    Both directions: untracked, the directory reads as ignored and the gate finds the offender; tracked, `git check-ignore` says nothing and the same tree is reported clean. Pinned because the failure looks exactly like a gate that cannot fail.
    """
    root = st.build_control_tree(tmp_path)
    assert st.ignored_roots(root) == ["ignoredir"]
    assert st.scan(root) != []
    subprocess.run(
        ["git", "-C", str(root), "add", "-f", "--", "ignoredir/thing.sh"],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    assert st.ignored_roots(root) == []
    assert st.scan(root) == []


def test_ignored_roots_skips_dotted_directories(tmp_path: pathlib.Path) -> None:
    """Bash's `*` does not match a leading dot, which is what keeps `.git` out."""
    (tmp_path / ".hidden").mkdir()
    (tmp_path / "shown").mkdir()
    subprocess.run(
        ["git", "-C", str(tmp_path), "init", "-q"],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    (tmp_path / ".gitignore").write_text(".hidden/\nshown/\n", encoding="utf-8")
    assert st.ignored_roots(tmp_path) == ["shown"]


def test_grep_lines_are_sorted_bytewise(tmp_path: pathlib.Path) -> None:
    """`| sort` under LC_ALL=C sorts the WHOLE `path:line:text` string, bytewise.

    The consequence is worth pinning: `:10:` sorts BEFORE `:1:` because `0` is 0x30 and `:` is 0x3A, so the report for a file with twelve hits comes out 10, 11, 12, 1, 2, ... A port that sorted the parsed tuples would order them numerically and disagree with the twin on every such file.
    """
    root = tmp_path
    (root / ".ci" / "scripts").mkdir(parents=True)
    (root / ".github" / "workflows").mkdir(parents=True)
    body = "\n".join("bash vendorbin/x%d.sh" % i for i in range(1, 13))
    (root / ".ci" / "scripts" / "a.sh").write_text(body + "\n", encoding="utf-8")
    lines = st.grep_lines(root, "vendorbin")
    assert lines == sorted(lines, key=lambda s: s.encode("utf-8"))
    numbers = [int(line.split(":")[1]) for line in lines]
    assert numbers == [10, 11, 12, 1, 2, 3, 4, 5, 6, 7, 8, 9]


def test_selftest_runs_and_meets_its_floor() -> None:
    """The gate's own both-direction controls, over trees built by construction."""
    assert st.selftest() == 0

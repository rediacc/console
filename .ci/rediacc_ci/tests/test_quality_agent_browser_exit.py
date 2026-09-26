r"""`rediacc_ci.quality.agent_browser_exit` against the shell it replaces.

WHY A DIFFERENTIAL AND NOT A TABLE OF EXPECTED STRINGS. Almost every decision in this gate is made by a shell construct whose exact behaviour is not inferable
from reading it: an ERE with a POSIX character class (`-[a-z]*e`), five `case`
patterns matched against the RAW line, a `while IFS= read -r` loop that silently
drops a file's last line when it has no trailing newline, and a two-line `printf` whose second line is post-processed by `sed`. A table of expected strings would be a table of what the PORT does, asserted against itself.

These are the seams the committed ledger cannot isolate. `.ci/shadow/w7p2-agent-browser-exit.observations.jsonl` compares the WHOLE gate over five distinct trees; it cannot say which of the five `case` arms rejected a line, because both sides simply printed nothing for it. This file takes each arm on its own.

THE FRAGMENTS BELOW ARE LIFTED FROM `.ci/scripts/quality/check-agent-browser-exit.sh` lines 31-49 with the variables substituted and nothing else changed. Where a fragment is a `case`, it is reproduced as a `case` rather than as an equivalent `if`, because the equivalence is the thing under test.
"""

import pathlib

import pytest

from rediacc_ci.quality import agent_browser_exit as abe
from rediacc_ci.tests import differential as diff

# --------------------------------------------------------------------------- The `set -e` eligibility test: grep -qE '^[[:space:]]*set[[:space:]]+-[a-z]*e' ---------------------------------------------------------------------------

# Every shape of `set` this repo actually contains, plus the two that look like they should qualify and do not. The comment on each line is the property it is there for; a case with no property is a case that will be deleted the first time someone tidies this file.
SET_E_CASES = [
    "set -e",  # the bare form
    "set -eu",  # e first
    "set -euo pipefail",  # the repo's overwhelmingly common form
    "set -ex",  # e then a non-e letter
    "set -xe",  # e last in the cluster
    "  set -e",  # indented
    "\tset -e",  # tab-indented
    "set  -e",  # extra space between the word and the dash
    "set -uo pipefail",  # NOT errexit: must NOT match
    "set -o errexit",  # long form: must NOT match, and that is a blind spot
    "set -u",  # no e at all
    "unset -e",  # `set` not at the start: must NOT match
    "# set -e",  # a comment: must NOT match
    "set -e ",  # trailing space
    "setup -e",  # a longer word: must NOT match
]


@pytest.mark.parametrize("line", SET_E_CASES)
def test_set_e_eligibility_matches_grep(tmp_path: pathlib.Path, line: str) -> None:
    """`SET_E_RE` and grep must agree, including on the two blind spots."""
    target = tmp_path / "f.sh"
    target.write_text(line + "\n", encoding="utf-8")
    code, _out, err = diff.bash_streams(
        "grep -qE '^[[:space:]]*set[[:space:]]+-[a-z]*e' f.sh; echo $?",
        cwd=str(tmp_path),
    )
    assert code == 0, err
    grep_found = _out.strip() == "0"
    assert bool(abe.SET_E_RE.search(line)) == grep_found


def test_set_o_errexit_is_a_carried_blind_spot() -> None:
    """Pinned as a DECISION, not left to be inferred from the table above.

    `set -o errexit` kills a script exactly as `set -e` does, and this gate does not look at such a file at all. The assertion exists so that a later "improvement" to the regex has to delete a named control rather than quietly widen the corpus, which would change the verdict on the real tree.
    """
    assert abe.SET_E_RE.search("set -o errexit") is None
    assert abe.SET_E_RE.search("set -e") is not None


# --------------------------------------------------------------------------- The line skip-list: five `case` arms, all matched against the RAW line ---------------------------------------------------------------------------

# The exact `case` from the twin, lines 35-46, with `$line` bound by the caller. Prints SKIP when the line is rejected and HIT when it survives to be reported.
_CASE = r"""
line="$1"
case "$line" in
    *'agent-browser'*'open'*) ;;
    *) echo SKIP; exit 0 ;;
esac
case "${line#"${line%%[![:space:]]*}"}" in '#'*) echo SKIP; exit 0 ;; esac
case "$line" in
    *'|| true'* | *'|| :'* | *'||true'*) echo SKIP; exit 0 ;;
    *'if '*'agent-browser'* | *'&&'* | *'! agent-browser'*) echo SKIP; exit 0 ;;
    *'$('*) echo SKIP; exit 0 ;;
esac
echo HIT
"""

# Both directions, deliberately. A table of only-HIT cases would pass against a scanner that reports every line, and a table of only-SKIP cases would pass against one that reports none.
LINE_CASES = [
    'agent-browser open "$URL" >/dev/null 2>&1',  # the defect itself
    '  agent-browser open "$u"',  # indented, still a call
    'agent-browser open "$u" >/dev/null || true',  # neutralised
    'agent-browser open "$u" || :',  # neutralised, colon form
    'agent-browser open "$u" ||true',  # neutralised, no space
    'if agent-browser open "$u"; then :; fi',  # consumed by a conditional
    '! agent-browser open "$u"',  # consumed by negation
    'out=$(agent-browser open "$u")',  # captured
    'cd "$d" && agent-browser open "$u"',  # `&&` anywhere skips: a FALSE NEGATIVE
    'agent-browser open "$u" && echo ok',  # `&&` again
    '# agent-browser open "$u"',  # a comment
    '   # agent-browser open "$u"',  # an indented comment
    'agent-browser close "$u"',  # no `open`
    "agent-browser --help",  # not `open`
    'echo "open agent-browser"',  # wrong order: `open` before the needle
    'curl "$u"',  # not this gate's business
    'if true; then agent-browser open "$u"; fi',  # `if ` before the needle
    'agent-browser open "$u" # if we cared',  # `if ` AFTER the needle: still a HIT
    'agent-browser open "$a"; agent-browser open "$b"',  # two on one line, one finding
]


@pytest.mark.parametrize("line", LINE_CASES)
def test_line_skip_list_matches_case(tmp_path: pathlib.Path, line: str) -> None:
    """Drive the twin's `case` block and the port's arms over the same line."""
    script = tmp_path / "c.sh"
    script.write_text(_CASE, encoding="utf-8")
    # THE LINE ARRIVES THROUGH THE ENVIRONMENT, not through the command string. Every case in the table contains `$`, quotes, or both, and interpolating them into `bash -c` would have the OUTER shell expand them before the fragment ever saw them -- so the fragment would be judging a different line than the port is, and the two would agree for the wrong reason.
    code, out, err = diff.bash_streams(
        'bash c.sh "$LINE"', cwd=str(tmp_path), env=diff.env_for(LINE=line)
    )
    assert code == 0, err
    bash_hit = out.strip() == "HIT"

    # The port's answer for the SAME line, obtained by scanning a one-line file that is eligible. `set -e` is prepended, so the file qualifies and the only question left is the skip-list.
    box = tmp_path / "box"
    box.mkdir(exist_ok=True)
    (box / "x.sh").write_text("set -e\n" + line + "\n", encoding="utf-8")
    port_hit = len(abe.scan(str(box))) > 0
    assert port_hit == bash_hit, "disagreement on %r" % line


# ---------------------------------------------------------------------------
# The `while IFS= read -r` last-line behaviour
# ---------------------------------------------------------------------------


def test_unterminated_last_line_is_dropped_by_both(tmp_path: pathlib.Path) -> None:
    """The defect this port preserves, proven against bash rather than asserted.

    `read` returns non-zero at EOF even though it has already assigned the partial line, so the loop body never runs for it. Any "fix" in the port would make it report a finding the twin does not, which is the NEW_SIDE_NOISY
    class the shadow comparator names.
    """
    target = tmp_path / "f.sh"
    target.write_text('set -e\nagent-browser open "$U"', encoding="utf-8")
    code, out, err = diff.bash_streams(
        'n=0; while IFS= read -r l; do n=$((n+1)); done < f.sh; echo "$n"',
        cwd=str(tmp_path),
    )
    assert code == 0, err
    assert out.strip() == "1"
    assert len(abe._read_lines(target.read_text(encoding="utf-8"))) == 1
    assert abe.scan(str(tmp_path)) == []

    # And its MIRROR: the same content WITH the newline is seen by both.
    target.write_text('set -e\nagent-browser open "$U"\n', encoding="utf-8")
    code, out, err = diff.bash_streams(
        'n=0; while IFS= read -r l; do n=$((n+1)); done < f.sh; echo "$n"',
        cwd=str(tmp_path),
    )
    assert code == 0, err
    assert out.strip() == "2"
    assert len(abe.scan(str(tmp_path))) == 1


# --------------------------------------------------------------------------- The finding's printed shape ---------------------------------------------------------------------------

REPORT_CASES = [
    'agent-browser open "$u"',
    '    agent-browser open "$u"',  # the indent is stripped by sed
    '\t\tagent-browser open "$u"',  # tabs too
    'agent-browser open "$u"   ',  # TRAILING space is NOT stripped
    'agent-browser open "a  b"',  # inner runs survive
]


@pytest.mark.parametrize("line", REPORT_CASES)
def test_report_shape_matches_printf_and_sed(tmp_path: pathlib.Path, line: str) -> None:
    """`printf ' %s:%d\\n %s\\n' "$rel" "$n" "$(echo "$line" | sed ...)"`.

    The `sed 's/^[[:space:]]*//'` strips the LEADING indent only, and the whole thing sits inside a command substitution, which strips trailing NEWLINES but not trailing spaces. Both halves of that are in the table.
    """
    code, out, err = diff.bash_streams(
        """printf '  %s:%d\n    %s\n' "sub/x.sh" 7 "$(echo "$LINE" | sed 's/^[[:space:]]*//')" """,
        cwd=str(tmp_path),
        env=diff.env_for(LINE=line),
    )
    assert code == 0, err
    assert abe._report(str(tmp_path), str(tmp_path / "sub" / "x.sh"), 7, line) == out.rstrip("\n")


# --------------------------------------------------------------------------- The corpora ---------------------------------------------------------------------------


def test_shell_corpus_matches_grep_rl(tmp_path: pathlib.Path) -> None:
    """`grep -rl --include='*.sh' | grep -v ... | sort`, file set and order.

    Sorted comparison, because the ORDER decides the order findings are printed in and a reordered report is a reordered diff for every future reviewer.
    """
    (tmp_path / "a.sh").write_text('agent-browser open "$u"\n', encoding="utf-8")
    (tmp_path / "b.sh").write_text("nothing here\n", encoding="utf-8")
    (tmp_path / "c.bash").write_text('agent-browser open "$u"\n', encoding="utf-8")
    nm = tmp_path / "node_modules" / "pkg"
    nm.mkdir(parents=True)
    (nm / "d.sh").write_text('agent-browser open "$u"\n', encoding="utf-8")
    deep = tmp_path / "x" / "y"
    deep.mkdir(parents=True)
    (deep / "e.sh").write_text('agent-browser open "$u"\n', encoding="utf-8")

    code, out, err = diff.bash_streams(
        "grep -rl --include='*.sh' 'agent-browser' . 2>/dev/null | "
        "grep -v '/node_modules/' | grep -v '/\\.git/' | "
        "grep -vF 'check-agent-browser-exit.sh' | sort",
        cwd=str(tmp_path),
    )
    assert code == 0, err
    from_bash = sorted(line[2:] for line in out.strip().split("\n"))
    from_port = sorted(
        p[len(str(tmp_path)) + 1 :]
        for p in abe._corpus(str(tmp_path), abe.SH_SUFFIXES, abe.SH_PRUNE)
    )
    assert from_port == from_bash


def test_js_corpus_prunes_dist_and_the_shell_one_does_not(tmp_path: pathlib.Path) -> None:
    """The two prune lists genuinely differ, and that difference is the twin's.

    `dist` is excluded from the JS corpus and NOT from the shell corpus. Asserted rather than commented, because it reads like a copy-paste slip and is not: built JS is a copy of source that would double every finding, while a `.sh` under a `dist` directory is an ordinary script.
    """
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "b.js").write_text("execSync('agent-browser open x');\n", encoding="utf-8")
    (dist / "b.sh").write_text('agent-browser open "$u"\n', encoding="utf-8")
    assert abe._corpus(str(tmp_path), abe.JS_SUFFIXES, abe.JS_PRUNE) == []
    assert len(abe._corpus(str(tmp_path), abe.SH_SUFFIXES, abe.SH_PRUNE)) == 1


# --------------------------------------------------------------------------- The gate as a whole ---------------------------------------------------------------------------


def test_js_half_runs_first_and_hides_the_shell_half(tmp_path: pathlib.Path) -> None:
    """A tree with BOTH defects reports only the JavaScript one.

    This is control flow, not a finding rule, and it is the property most likely to be lost by someone merging the two reports into one pass. The ledger's `abe-4` row is the whole-gate version of this same claim.
    """
    (tmp_path / "a.ts").write_text("execSync('agent-browser open ' + u);\n", encoding="utf-8")
    (tmp_path / "b.sh").write_text('set -e\nagent-browser open "$u"\n', encoding="utf-8")
    assert len(abe.scan_js(str(tmp_path))) == 1
    assert len(abe.scan(str(tmp_path))) == 1
    # Both fire independently; main() prints only the first. That ordering is asserted by the ledger row rather than re-driven here, because main() resolves its root from the environment.


def test_selftest_is_green() -> None:
    """The port's own plants and mirrors, driven from pytest.

    Not redundant with running `--selftest` from the shell: this is the call that fails the pytest suite if a control is deleted, which is the failure mode the flag on its own cannot catch (nobody runs it).
    """
    assert abe.selftest() == 0


def test_inline_controls_are_green() -> None:
    """The controls the TWIN has, which main() runs before every real scan."""
    assert abe.inline_controls() == 0

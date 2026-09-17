"""`rediacc_ci.core.advisory` against the live `emit-advisory.sh`.

THE TWIN IS LIVE, not frozen: `.ci/scripts/lib/emit-advisory.sh` still carries
its implementation and is still reached by `blocker-validator.sh:80`, by
`age-check.sh` and by `.ci/scripts/security/audit.sh`. Every case below sources
that file.

THE TWIN IS DRIVEN STANDALONE, WITH NO `common.sh`, AND THAT IS THE WHOLE
DIFFERENTIAL'S SCOPE. `emit-advisory.sh` defines its loggers only when nothing
has defined them already (`declare -F`), so sourcing `common.sh` first replaces
four of the functions under test with common.sh's. A differential that did that
would be measuring `common.sh` while appearing to measure this file. The
transitive branch belongs to whichever box ports `common.sh`; it is named here
so its absence reads as a boundary rather than as an oversight.

WHY BOTH STREAMS ARE COMPARED SEPARATELY AND NEVER MERGED. One advisory
STRADDLES them: off CI the header goes to stderr through `log_error` while every
continuation line -- Affected, Summary, Fix, Action, Details -- is a plain
`echo` on stdout. `2>&1` would make a stream swap invisible, and a stream swap
in this exact file is the 2026-09-06 incident `rediacc_ci.log` is shaped by.
`differential.bash_streams` has no option to merge them.
"""

import textwrap

import pytest

from rediacc_ci.core import advisory as adv
from rediacc_ci.tests import differential as diff

TWIN = ".ci/scripts/lib/emit-advisory.sh"
US = "\x1f"

# US and not tab, for the reason recorded at `rediacc_ci.core.advisory`'s SEP:
# `IFS=$'\t' read` collapses consecutive tabs and eats an empty field, which on
# this differential's first run shifted `fix` into `name` on the bash side only and looked exactly like a port defect.
BASH_DRIVER = textwrap.dedent(
    """
    _drive() {
      source %s
      declare -A _TBL=([severity]=ADV_SEVERITY [title]=ADV_TITLE [ghsa]=ADV_GHSA \\
                       [url]=ADV_URL [range]=ADV_VULN_RANGE \\
                       [patched]=ADV_PATCHED_VERSION [desc]=ADV_DESC_PREVIEW)
      local emitted=0
      while IFS=$'\\x1f' read -r verb a b c d e; do
        [[ -n "$verb" ]] || continue
        case "$verb" in
          meta) arr="${_TBL[$a]:-}"
                [[ -n "$arr" ]] || exit 2
                eval "$arr[\\$b]=\\$c" ;;
          emit) emit_advisory "$a" "$b" "$c" "$d" "$e"; emitted=$((emitted+1)) ;;
          *) exit 2 ;;
        esac
      done
      [[ $emitted -gt 0 ]] || exit 2
      exit 0
    }
    """
    % TWIN
)

PY_DRIVER = "PYTHONPATH=.ci python3 -m rediacc_ci.core.advisory"

FULL = [
    ("meta", "severity", "1234", "critical"),
    ("meta", "title", "1234", "Prototype pollution"),
    ("meta", "ghsa", "1234", "GHSA-xxxx-yyyy-zzzz"),
    ("meta", "url", "1234", "https://github.com/advisories/GHSA-xxxx"),
    ("meta", "range", "1234", "<= 1.15.11"),
    ("meta", "patched", "1234", "1.16.0"),
    ("meta", "desc", "1234", "A short description already truncated by the caller"),
    ("emit", "error", "1234", "lodash", "npm audit fix", "upgrade before release"),
]

# (id, env-overrides, program rows).
CASES = [
    ("bare-error", {}, [("emit", "error", "1234", "lodash", "npm audit fix")]),
    ("full-metadata", {}, FULL),
    ("ci-annotations", {"CI": "true"}, FULL),
    # `CI=1` IS NOT `CI=true`. The twin compares against the literal string, so
    # a machine exporting CI=1 for some other tool must still get the human form.
    ("ci-is-one-not-true", {"CI": "1"}, FULL),
    # An empty `name` with a patched version: exercises `${parens:+$parens, }`,
    # the idiom most likely to leave a stray leading comma in a naive port.
    (
        "empty-name-patched-only",
        {},
        [("meta", "patched", "lodash", "4.17.21"), ("emit", "warn", "lodash", "", "upgrade")],
    ),
    # A PACKAGE-NAME id, which is the case the twin's bash-4 guard exists for.
    (
        "package-name-id",
        {},
        [
            ("meta", "ghsa", "lodash", "GHSA-abcd-efgh-ijkl"),
            ("emit", "error", "lodash", "", "", ""),
        ],
    ),
    # BACKSLASHES. `log_error` is `echo -e`, so these are INTERPRETED, and a port that formatted them as data would silently disagree on any Windows path or regex an advisory happens to name.
    (
        "backslash-escapes",
        {},
        [("emit", "error", "id1", "C:\\tmp\\new", "sed -e 's/\\t/ /g'")],
    ),
    # A range with no patched version, and a patched version with no range: the
    # two halves of the `${vuln_range:-unknown}` default.
    (
        "range-without-patched",
        {},
        [("meta", "range", "x", ">= 2.0.0 < 2.4.1"), ("emit", "warn", "x", "pkg", "")],
    ),
    # `\c` SUPPRESSES THE REST OF THE LINE INCLUDING ITS NEWLINE. Measured on the real builtin: `echo -e 'a\cb'` writes `a` with no trailing `$`. A port that always appended a newline would differ by one byte here and nowhere
    # else, which is the hardest kind of difference to find later.
    (
        "backslash-c-eats-the-newline",
        {},
        [("emit", "error", "id2", "head\\ctail", "fix")],
    ),
    (
        "two-advisories",
        {},
        [
            ("meta", "severity", "a", "low"),
            ("meta", "severity", "b", "high"),
            ("emit", "warn", "a", "pkg-a", "fix a"),
            ("emit", "error", "b", "pkg-b", "fix b"),
        ],
    ),
]


def program(rows) -> str:
    return "".join(US.join(row) + "\n" for row in rows)


def _shquote(text: str) -> str:
    return "'" + text.replace("'", "'\\''") + "'"


def run_both(text: str, overrides: dict):
    env = diff.env_for(**overrides)
    quoted = "printf '%%s' %s" % _shquote(text)
    old = diff.bash_streams("%s\n%s | _drive" % (BASH_DRIVER, quoted), env=env)
    new = diff.bash_streams("%s | %s" % (quoted, PY_DRIVER), env=env)
    return old, new


@pytest.mark.parametrize(("case_id", "overrides", "rows"), CASES, ids=[c[0] for c in CASES])
def test_port_matches_the_live_twin(case_id, overrides, rows) -> None:
    old, new = run_both(program(rows), overrides)
    assert old == new, "case %s: bash %r vs python %r" % (case_id, old, new)


def test_the_corpus_is_not_empty() -> None:
    assert len(CASES) >= 5, "the differential corpus collapsed to %d case(s)" % len(CASES)


def test_the_differential_can_fail() -> None:
    """A single space removed from `  Fix: ` must turn the comparison red."""
    old, new = run_both(program(FULL), {})
    assert old == new
    assert old != (new[0], new[1].replace("  Fix: ", "  Fix:"), new[2]), (
        "the comparison did not notice a change to a continuation line on stdout"
    )
    assert old != (new[0], new[1], new[2].replace("✗", "x")), (
        "the comparison did not notice a change to the header on stderr"
    )


def test_the_two_streams_are_really_separate() -> None:
    """The header is on stderr and the body on stdout, off CI. Both non-empty.

    A CONTROL ON THE CONTROL. If `bash_streams` ever merged the two, every case
    above would still pass -- both sides would be merged identically -- while the
    stream swap this file exists to catch became invisible.
    """
    _rc, out, err = diff.bash_streams(
        "%s\nprintf '%%s' %s | _drive" % (BASH_DRIVER, _shquote(program(FULL))),
        env=diff.env_for(),
    )
    assert "✗ 1234" in err
    assert "Affected:" not in err
    assert "  Affected: <= 1.15.11  →  Patched in: 1.16.0" in out
    assert "✗" not in out


def test_under_ci_the_annotation_moves_to_stdout() -> None:
    """The other half of the stream story, and the reason CI is a case at all."""
    _rc, out, err = diff.bash_streams(
        "%s\nprintf '%%s' %s | _drive" % (BASH_DRIVER, _shquote(program(FULL))),
        env=diff.env_for(CI="true"),
    )
    assert out.startswith("::error::1234 (lodash, critical, GHSA")
    assert err == ""  # the whole advisory moved to stdout


# -- the helpers, exercised directly -----------------------------------------


@pytest.mark.parametrize(
    ("name", "severity", "ghsa", "title", "expected"),
    [
        ("lodash", "critical", "GHSA-x", "T", "1234 (lodash, critical, GHSA-x): T"),
        ("", "critical", "", "", "1234 (critical)"),
        ("", "", "", "", "1234"),
        ("", "", "", "T", "1234: T"),
        ("lodash", "", "GHSA-x", "", "1234 (lodash, GHSA-x)"),
    ],
    ids=["all", "severity-only", "nothing", "title-only", "name-and-ghsa"],
)
def test_header_composition(name, severity, ghsa, title, expected) -> None:
    """No stray leading comma, no empty parens. Both directions of the idiom."""
    assert adv.header_for("1234", name, severity, ghsa, title) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("plain", "plain"),
        ("a\\tb", "a\tb"),
        ("a\\nb", "a\nb"),
        ("C:\\tmp", "C:\tmp"),
        ("\\\\literal", "\\literal"),
        ("\\q unrecognised", "\\q unrecognised"),
        ("\\x41", "A"),
        ("\\101", "\\101"),
        ("keep\\cdropped", "keep"),
        ("arrow → stays", "arrow → stays"),
    ],
    ids=[
        "plain",
        "tab",
        "newline",
        "windows-path",
        "escaped-backslash",
        "unrecognised-passes-through",
        "hex",
        "bare-octal-is-literal",
        "backslash-c-truncates",
        "non-ascii-survives",
    ],
)
def test_echo_e_matches_bash(raw: str, expected: str) -> None:
    """`_echo_e` against a table, and then against bash itself below."""
    assert adv._echo_e(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "plain",
        "a\\tb",
        "C:\\tmp\\new",
        "\\\\literal",
        "\\q",
        "\\x41",
        "\\101",
        "\\0101",
        "\\08",
        "arrow → stays",
    ],
)
def test_echo_e_matches_bash_for_real(raw: str) -> None:
    """The same question asked of the real builtin, which is the actual authority."""
    _rc, out, _err = diff.bash_streams("echo -e %s" % _shquote(raw))
    assert out == adv._echo_e(raw) + "\n"


def test_ci_is_the_literal_string_true() -> None:
    assert adv.in_ci({"CI": "true"}) is True
    for value in ("1", "TRUE", "yes", "", "false"):
        assert adv.in_ci({"CI": value}) is False, "CI=%r must not read as CI" % value


def test_an_unknown_level_refuses_rather_than_inventing_an_emitter() -> None:
    """Bash dies with `ci_notice: command not found`; this raises. Neither guesses."""
    with pytest.raises(ValueError, match="must be 'error' or 'warn'"):
        adv.emit_advisory("notice", "1", "n", "f")


def test_an_unknown_table_refuses() -> None:
    table = adv.Advisories()
    with pytest.raises(KeyError):
        table.set("cvss", "1", "9.8")
    table.set("severity", "1", "high")
    assert table.get("severity", "1") == "high"


def test_zero_emits_is_a_refusal_not_a_pass() -> None:
    """Anti-vacuity. Metadata with no advisory produces no bytes on either side."""
    assert adv.run_program([US.join(("meta", "severity", "1", "high"))]) == 2
    assert adv.run_program([]) == 2


def test_a_real_program_is_not_refused() -> None:
    """The negative control for the two refusals above."""
    assert adv.run_program([US.join(("emit", "error", "1", "pkg", "fix"))]) == 0

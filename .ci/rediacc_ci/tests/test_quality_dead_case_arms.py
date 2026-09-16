r"""`rediacc_ci.quality.dead_case_arms` against the grep pipelines it replaces.

WHAT IS WORTH TESTING HERE. The shadow ledger
`.ci/shadow/w7p2-dead-case-arms.observations.jsonl` drives the whole gate over
five distinct trees carrying a dead arm in each scan root, a live mirror, and
the vacuity floor. What a ledger row cannot isolate is the two greps that decide
the verdict for every arm:

    grep -rnE '^[[:space:]]*\*[^)]*"[^"]*"[^)]*\)'   is this line an ASSERTION
    grep -rhE --exclude-dir=test "${key}=" $CODE_DIRS | grep -qvE '^\s*(#|//|\*)'
                                                     is this key ALIVE

The second is the gate. Drop its comment filter and every documented pattern
vaccinates the tree against detection, which is the 2026-08-05 defect the twin's
header records. Widen the first and the gate reports assignments as assertions.
Both are compared against the real grep below.

A FALSE POSITIVE COSTS MORE THAN A MISS HERE, and the tests are written that
way round: `key_is_live` counting a key as alive on the flimsiest evidence is
the SAFE direction, because a dead-arm finding tells an author to rewrite an
assertion that may in fact be working.
"""

import pathlib

from rediacc_ci import paths
from rediacc_ci.quality import dead_case_arms as dca
from rediacc_ci.tests import differential as diff


def _joined(*rows: str) -> str:
    """`"\n".join(rows)` behind a call. The rows stay one per line.

    A helper rather than a literal join because ruff's FLY002 rewrites a join
    over a LITERAL list into an f-string, and a ten-line shell fixture written
    as one f-string is unreadable. Passing the rows as arguments keeps the
    fixture legible and gives the linter nothing static to fold.
    """
    return "\n".join(rows)


# The two pipelines, verbatim from check-dead-case-arms.sh:77-78 and :101-102.
EXTRACT = (
    'grep -rnE \'^[[:space:]]*\\*[^)]*"[^"]*"[^)]*\\)\' "$D" 2>/dev/null | '
    "grep -vE '^[^:]+:[0-9]+:[[:space:]]*#' || true"
)
LIVE = 'grep -rhE --exclude-dir=test "$K=" "$C" 2>/dev/null | grep -qvE \'^[[:space:]]*(#|//|\\*)\''


def _bash_extract(directory: pathlib.Path) -> list[str]:
    code, out, err = diff.bash_streams('D="%s"; %s' % (directory, EXTRACT))
    assert err == "", err
    assert code == 0, code
    return [line for line in out.split("\n") if line]


def _bash_live(key: str, code_dir: pathlib.Path) -> bool:
    # `out` is deliberately not read: `grep -q` prints nothing and the EXIT
    # CODE is the whole answer.
    code, _out, err = diff.bash_streams('K="%s"; C="%s"; %s' % (key, code_dir, LIVE))
    assert err == "", err
    assert code in (0, 1), code
    return code == 0


def test_extraction_matches_the_twins_grep(tmp_path: pathlib.Path) -> None:
    """Every shape the recogniser must and must not match, in one fixture."""
    (tmp_path / "arms.sh").write_text(
        _joined(
            'case "$out" in',
            '    *"cores=20"* | *"cores=1[0-9]"*)',
            '        log_fail "the sampler sized itself from the HOST" ;;',
            '    *"mem_kb=1"*) exit 1 ;;',
            "    *plain*)",
            '# *"commented=1"*)',
            '    # *"indented_comment=1"*)',
            'FOO="assigned=1"',
            "esac",
            "",
        ),
        encoding="utf-8",
    )
    got = dca.extract_case_keys([str(tmp_path)], tmp_path)
    want = _bash_extract(tmp_path)
    assert sorted(got) == sorted(want), (got, want)
    joined = "\n".join(got)
    assert "cores=20" in joined
    assert "mem_kb=1" in joined
    assert "commented" not in joined, "a commented-out arm is not an assertion"
    assert "assigned" not in joined, "an assignment is not an arm"


def test_extraction_matches_on_the_real_test_tree() -> None:
    """The corpus the gate actually judges. A recogniser that narrowed would
    still pass a hand-built fixture and go quiet here."""
    root = paths.repo_root() / ".ci" / "scripts" / "test"
    assert root.is_dir(), "the test scan root moved; retarget the gate deliberately"
    got = sorted(dca.extract_case_keys([str(root)], paths.repo_root()))
    want = sorted(_bash_extract(root))
    assert got == want, [x for x in got if x not in want][:5] + [x for x in want if x not in got][
        :5
    ]
    assert len(want) >= 1, "ZERO arms found; every comparison here would be vacuous"


def test_key_liveness_matches_the_twins_pipeline(tmp_path: pathlib.Path) -> None:
    """The comment filter, in both directions, against the real grep."""
    code = tmp_path / "code"
    code.mkdir()
    (code / "emit.sh").write_text('printf "livekey=%s\\n" "$x"\n', encoding="utf-8")
    (code / "doc.sh").write_text("# the sampler never emits deadkey=20\n", encoding="utf-8")
    (code / "c.ts").write_text("// commentkey=1\n", encoding="utf-8")
    (code / "block.js").write_text(" * blockkey=1\n", encoding="utf-8")
    for key, expected in (
        ("livekey", True),
        ("deadkey", False),
        ("commentkey", False),
        ("blockkey", False),
        ("absentkey", False),
    ):
        assert dca.key_is_live(key, [str(code)], tmp_path) is expected, key
        assert _bash_live(key, code) is expected, key


def test_exclude_dir_test_matches_the_twin(tmp_path: pathlib.Path) -> None:
    """`--exclude-dir=test` is an exact directory-NAME match, so `testdata`
    still counts. A port that treated it as a substring would silently shrink
    the set of code that can vouch for a key."""
    code = tmp_path / "code"
    (code / "test").mkdir(parents=True)
    (code / "testdata").mkdir()
    (code / "test" / "e.sh").write_text("excludedkey=20\n", encoding="utf-8")
    assert dca.key_is_live("excludedkey", [str(code)], tmp_path) is False
    assert _bash_live("excludedkey", code) is False
    (code / "testdata" / "e.sh").write_text("keptkey=20\n", encoding="utf-8")
    assert dca.key_is_live("keptkey", [str(code)], tmp_path) is True
    assert _bash_live("keptkey", code) is True


def test_ugrep_skips_a_binary_file_and_so_does_the_port(tmp_path: pathlib.Path) -> None:
    """MEASURED, NOT ASSUMED. `grep` on this host is ugrep, which reports
    nothing at all for a file containing a NUL byte; GNU grep would print
    `Binary file X matches`. The port follows the grep the differential
    actually runs, and this pins which one that is."""
    (tmp_path / "bin.sh").write_bytes(b'case "$1" in\n    *"binprobe=1"*) exit 1 ;;\nesac\n\x00\n')
    assert _bash_extract(tmp_path) == []
    assert dca.extract_case_keys([str(tmp_path)], tmp_path) == []


def test_key_tokens_need_three_characters() -> None:
    """`[A-Za-z_][A-Za-z0-9_]{2,}=` is the twin's token, and the `{2,}` is what
    keeps a two-character shell variable out of the finding set."""
    assert dca.keys_in('f.sh:1: *"ab=1"*)') == []
    assert dca.keys_in('f.sh:1: *"abc=1"*)') == ["abc"]
    assert dca.keys_in('f.sh:1: *"z_9=1"* | *"abc=2"*)') == ["abc", "z_9"]


def test_media_count_is_top_level_only(tmp_path: pathlib.Path) -> None:
    """`for _f in "$_d"/*.sh` does not recurse, and the count is the vacuity
    floor: a recursive count would keep the floor satisfied by files the scan
    root's own glob no longer reaches."""
    (tmp_path / "a.sh").write_text("x\n", encoding="utf-8")
    (tmp_path / "deep").mkdir()
    (tmp_path / "deep" / "b.sh").write_text("x\n", encoding="utf-8")
    assert dca.media_shell_files([str(tmp_path)], tmp_path) == 1


def test_the_real_media_root_is_not_empty() -> None:
    """THE VACUITY FLOOR, checked against the live tree. If this ever reds the
    gate is scanning nothing and its green would mean nothing."""
    root = paths.repo_root()
    assert dca.media_shell_files([dca.DEFAULT_MEDIA_DIRS], root) > 0


def test_selftest_is_green() -> None:
    assert dca.selftest() == 0


def test_the_real_tree_has_no_dead_arms() -> None:
    """The gate against the actual repository, controls and all."""
    assert dca.main([]) == 0

"""`rediacc_ci.quality.pipefail_grep_q`, driven directly.

WHILE BOTH COPIES EXISTED a bash child ran the REAL `.ci/scripts/quality/check-pipefail-grep-q.sh` over a git fixture with stdout and stderr captured SEPARATELY, and its bytes were compared against the port's. The twin had no environment seam -- it resolved its root from its OWN location and enumerated through `git -C "$ROOT" ls-files` -- so the fixture was a real git
repository holding BOTH implementations. Same recipe as the committed ledger, `.ci/shadow/w7p2-pipefail-grepq.observations.jsonl`, which licensed the port at K=5. The twin was retired in W7 P5 and the whole-gate cases went with it.

THE MECHANISM CONTROL STILL RUNS FOR REAL, below: a 300 KB producer piped into `grep -q` under pipefail, asserted to report MISSED. It is the one control that cannot be a pure assertion, because the claim is about what the kernel does to a writer whose reader has exited. If the host ever stops reproducing the race, the gate is guarding a myth and these cases say so rather than
quietly agreeing about one.

THE RACING SHAPE IS ASSEMBLED AT RUNTIME in this file, exactly as the twin assembled its own fixture, so that this file's TEXT never carries it contiguously. The twin flagged itself the first time it became a tracked file for precisely that reason.
"""

import pathlib

import pytest

from rediacc_ci import paths
from rediacc_ci.quality import pipefail_grep_q as gate

# Assembled, never written out. See the module docstring.
GQ = "grep -q"


# --------------------------------------------------------------------------- The decision functions, driven directly. Both directions for every rule. ---------------------------------------------------------------------------

_SEED = 'set -o pipefail\nbody() { cat "$1"; }\n'


@pytest.mark.parametrize(
    ("text", "hits"),
    [
        pytest.param(_SEED + 'if body "$1" | %s x; then :; fi\n' % GQ, 1, id="the-racing-shape"),
        pytest.param(
            _SEED + 'if [ -n "$(body "$1" | grep x)" ]; then :; fi\n',
            0,
            id="the-sanctioned-fix",
        ),
        # INVERTED 2026-09-16. This case asserted 0 while it was called "a-bounded-builtin-producer", which was the gate's rule until `printf` and `echo` joined SCALING_PRODUCERS. Both builtins report MISSED 40/40 on a 300 KB payload on this host, so the bounded exemption was not a safety claim that survived measurement.
        pytest.param(
            'set -o pipefail\nif printf "%%s" "$x" | %s y; then :; fi\n' % GQ,
            1,
            id="a-builtin-printf-producer-is-flagged",
        ),
        pytest.param(
            'set -o pipefail\nif [ -n "$(printf "%s" "$x" | grep y)" ]; then :; fi\n',
            0,
            id="the-sanctioned-fix-for-printf",
        ),
        pytest.param(
            'set -o pipefail\nif echo "$x" | %s y; then :; fi\n' % GQ,
            1,
            id="a-builtin-echo-producer-is-flagged",
        ),
        pytest.param(
            'set -o pipefail\nif [ -n "$(echo "$x" | grep y)" ]; then :; fi\n',
            0,
            id="the-sanctioned-fix-for-echo",
        ),
        pytest.param(
            'body() { cat "$1"; }\nif body "$1" | %s x; then :; fi\n' % GQ,
            0,
            id="no-pipefail-no-race",
        ),
        pytest.param(
            _SEED + '# never write: body "$1" | %s x\n' % GQ, 0, id="a-comment-is-not-code"
        ),
        pytest.param(
            'set -o pipefail\npass() { echo "$*"; }\necho "no racing pass | %s here"\n' % GQ,
            0,
            id="a-string-literal-is-not-code",
        ),
        pytest.param(
            "set -o pipefail\nif x | %s y; then :; fi\n" % GQ, 0, id="not-a-local-function"
        ),
        pytest.param("", 0, id="empty"),
    ],
)
def test_offenders_in(text: str, hits: int) -> None:
    assert len(gate.offenders_in(text)) == hits


def test_a_line_naming_two_local_functions_is_reported_twice() -> None:
    """One `grep -n` per function name, so a line matching two is two hits.

    Pinned because it looks like a missing de-duplication and is the twin's shape; a port that collapsed it would disagree on the count.
    """
    text = "set -o pipefail\nabe() { :; }\nzed() { :; }\nif abe zed | %s x; then :; fi\n" % GQ
    assert len(gate.offenders_in(text)) == 2


@pytest.mark.parametrize(
    ("line", "stripped"),
    [
        pytest.param("code # tail", "code ", id="comment"),
        pytest.param("a 'b c' d", "a '' d", id="single-quoted"),
        pytest.param('a "b c" d', 'a "" d', id="double-quoted"),
        pytest.param("body | grep x", "body | grep x", id="plain-code-survives"),
    ],
)
def test_strip_code(line: str, stripped: str) -> None:
    assert gate.strip_code(line) == stripped


@pytest.mark.parametrize(
    ("text", "names"),
    [
        pytest.param("body() {\n", ["body"], id="column-one"),
        pytest.param("  body() {\n", [], id="indented-is-not-a-definition"),
        pytest.param("body () {\n", [], id="a-space-before-the-parens"),
        pytest.param("zed() {\nabe() {\nzed() {\n", ["abe", "zed"], id="sorted-and-unique"),
    ],
)
def test_local_functions(text: str, names: list[str]) -> None:
    assert gate.local_functions(text) == names


def test_the_mechanism_control_reproduces_on_this_host(tmp_path: pathlib.Path) -> None:
    """The OS half of the gate, asserted here as well as inside the gate.

    If this ever stops saying MISSED, the gate is guarding a myth on this host and every green it prints is worthless. That is worth a failing test, not a skip.
    """
    assert gate.mechanism_output(tmp_path) == "MISSED"


def test_the_builtin_mechanism_control_reproduces_on_this_host(tmp_path: pathlib.Path) -> None:
    """The OTHER half of the OS claim, and a different kernel path from the above.

    bash traps SIGPIPE for its own builtins, so `printf` does not die -- it takes EPIPE from write(2) and returns non-zero, which pipefail promotes. The gate flags eleven `printf`/`echo` sites on the strength of that; if it ever stops reproducing, those flags are guarding a myth and this must go red rather than skip.
    """
    assert gate.mechanism_builtin_output(tmp_path) == "MISSED"


@pytest.mark.parametrize(
    ("rel", "hits"),
    [
        pytest.param(".ci/lib/devbox.sh", 1, id="under-an-inheriting-prefix"),
        pytest.param("scripts/dev/thing.sh", 0, id="anywhere-else"),
        pytest.param(None, 0, id="a-fixture-has-no-path"),
    ],
)
def test_inherited_pipefail_is_decided_by_path(rel: str | None, hits: int) -> None:
    """Identical bytes, classified by PATH alone.

    `.ci/lib/devbox.sh:1082` sets no pipefail of its own and inherits it from every sourcer (scripts/dev/worktree.sh:12, .ci/lib/local-common.sh:937,983 via rdc.sh:11), which is why the gate could not see the sweep's strongest finding.
    """
    text = (
        'lib_detect() { git -C "$1" status --porcelain; }\n'
        'if printf "%%s" "$out" | %s dubious; then :; fi\n' % GQ
    )
    assert len(gate.offenders_in(text, rel)) == hits


def test_the_live_corpus_is_not_empty() -> None:
    """`git ls-files` over the real tree must return files, or the gate is blind."""
    files = [f for f in gate.scan_files(paths.repo_root()) if f]
    assert len(files) > 100


def test_selftest_passes_and_is_not_vacuous(capsys) -> None:
    assert gate.selftest() == 0
    out = capsys.readouterr().out
    assert "control(s) passed" in out
    # RATCHETED 26 -> 28 on 2026-09-16 when `tee` and `docker` joined SCALING_PRODUCERS and each got its own selftest control. A floor that is not raised with the controls it counts stops pinning the ones added after it.
    assert int(out.strip().split("\n")[-1].split()[0]) >= 28

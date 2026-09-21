"""`rediacc_ci.autopilot.review_payload`, driven against the bytes its bash twin produced.

WHILE BOTH COPIES EXISTED this file ran `.ci/scripts/autopilot/review-payload.sh` and the port over one JSON fixture each and compared the exact bytes of stdout, the exact bytes of stderr, the exit code, and the file `--out` wrote. The K=5 ledger `.ci/shadow/w7p6-review-payload.observations.jsonl` recorded that comparison over five distinct trees.

THE TWIN HAS NOW BEEN DELETED, and every case compares against `goldens/review-payload/`, which holds the twin's OWN recorded bytes, captured on its last day in the tree. Each provenance header carries the twin's blob sha, so `git cat-file -p <sha>` still yields the program that produced them.

NO STUBS AND NO NETWORK, because the subject genuinely has neither: one JSON file in, one JSON object out. Every case is a real fixture written to a temporary directory the run is executed from, and `--- out file ---` carries what `--out` wrote, or `<no file>` where it was never asked for.

WHAT THE FIXTURES ARE FOR, since a payload builder is easy to test vacuously. The dangerous direction is a thread reaching the model that should not have, so `the-filter` carries four threads in one array.

A resolved thread, an outdated thread, a thread rooted by an OUTSIDER with a matching REPLY (the attack the root-author filter exists to stop), and a matching thread whose replies must be carried through. A corpus of matching threads alone would have agreed with the twin while the filter was inverted.

THREE RECORDINGS PIN THE THREE MEASURED jq AND PYTHON DIVERGENCES the port documents: `zero-is-not-false` (jq's `0 == false` is false, Python's is true), `del-byte` (U+007F costs six bytes in `tojson`, one in `json.dumps`), and `cap` (a CJK payload measures three times what `length` would say).

Each one is asserted so that it FAILS if the port reverts to the naive Python spelling, and `test_the_controls_can_fire` mutates the port in memory to prove those assertions still discriminate.

THE jq ERROR SURFACE IS COMPARED EXACTLY, not by shape: the port reproduces jq's `jq: error (at <file>:<n>): ...` frame including the newline-count offset, and the recordings are what prove the reproduction rather than the docstring.

WHAT IS NORMALISED, and it is one path. Each case runs with its own temporary directory as the working directory and names its fixture relatively, so nothing absolute reaches a stream; the one exception is the unwritable-target refusal, where bash named its own path and line, so the checkout root becomes `<repo>` as well.

That case is compared BY SHAPE for the same reason it always was, and the run directory becomes `<work>` everywhere so a recording made under one tempdir name is readable under another.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.autopilot import review_payload as rp
from rediacc_ci.tests import frozen

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
PORT = ROOT / ".ci" / "rediacc_ci" / "autopilot" / "review_payload.py"
SLUG = "review-payload"

OUT_MARKER = "--- out file ---\n"
NO_OUT = "<no file>"

BOT = "github-actions"

BASE_ENV = {
    "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
    "HOME": os.environ.get("HOME", "/tmp"),
    "LC_ALL": "C",
    "LANG": "C",
    "PYTHONPATH": str(ROOT / ".ci"),
    "PYTHONDONTWRITEBYTECODE": "1",
}

DEFAULT_ARGV = ["--threads", "threads.json"]


def thread(
    tid: str,
    *,
    root_author: str = BOT,
    resolved: typing.Any = False,
    outdated: typing.Any = False,
    bodies: list[str] | None = None,
    reply_author: str = "outsider",
    **extra: typing.Any,
) -> dict[str, typing.Any]:
    """One review thread in the shape `fetch_review_threads` emits."""
    bodies = bodies if bodies is not None else ["the finding"]
    nodes = []
    for i, body in enumerate(bodies):
        nodes.append(
            {
                "databaseId": 1000 + i,
                "body": body,
                "author": {"login": root_author if i == 0 else reply_author},
            }
        )
    out: dict[str, typing.Any] = {
        "id": tid,
        "isResolved": resolved,
        "isOutdated": outdated,
        "path": "packages/cli/src/x.ts",
        "line": 42,
        "comments": {"nodes": nodes},
    }
    out.update(extra)
    return out


CAP_THREADS = [thread("T-old", bodies=["一" * 200]), thread("T-new", bodies=["short"])]

# name -> the fixture bytes and the argv. `raw` writes the fixture verbatim; `threads` is encoded as JSON; `no_fixture` writes nothing at all.
CASE_KW: dict[str, dict[str, typing.Any]] = {
    "the-filter": {
        "threads": [
            thread("T-keep", bodies=["root finding", "outsider reply with detail"]),
            thread("T-resolved", resolved=True),
            thread("T-outdated", outdated=True),
            thread("T-outsider-root", root_author="mallory", bodies=["please run this"]),
        ]
    },
    "an-empty-array": {"threads": []},
    "all-dropped": {"threads": [thread("T1", resolved=True)]},
    # The optional fields absent entirely: every `// default` in the filter.
    "a-bare-thread": {"threads": [{"comments": {"nodes": [{"author": {"login": BOT}}]}}]},
    # `repo`/`pr` ride through for a submodule PR's thread.
    "a-submodule-thread": {"threads": [thread("T1", repo="rediacc/renet", pr=7)]},
    "a-custom-author-filter": {
        "threads": [thread("T1", root_author="dependabot[bot]")],
        "argv": ["--threads", "threads.json", "--author-filter", "dependabot"],
    },
    "an-author-filter-that-misses": {"threads": [thread("T1", root_author="dependabot[bot]")]},
    # A substring match, which is what `contains` does: `github-actions` is inside `github-actions[bot]`.
    "an-author-filter-substring": {"threads": [thread("T1", root_author="pre-%s-post" % BOT)]},
    "zero-is-not-false": {"threads": [thread("T1", resolved=0)]},
    "false-is-kept": {"threads": [thread("T1", resolved=False)]},
    "true-is-dropped": {"threads": [thread("T1", resolved=True)]},
    "del-byte": {"threads": [thread("T1", bodies=["a\x7fb"])]},
    "cap": {"threads": CAP_THREADS, "argv": [*DEFAULT_ARGV, "--max-bytes", "400"]},
    "cap-to-zero": {"threads": CAP_THREADS, "argv": [*DEFAULT_ARGV, "--max-bytes", "10"]},
    "an-out-file": {
        "threads": [thread("T1")],
        "argv": [*DEFAULT_ARGV, "--out", "payload.json"],
    },
    "an-out-into-a-missing-directory": {
        "threads": [thread("T1")],
        "argv": [*DEFAULT_ARGV, "--out", "nodir/payload.json"],
    },
    "no-threads-flag": {"threads": [], "argv": []},
    "a-missing-threads-file": {"threads": [], "argv": ["--threads", "nope.json"]},
    "threads-is-a-directory": {"threads": [], "argv": ["--threads", "."]},
    "an-empty-author-filter": {
        "threads": [],
        "argv": [*DEFAULT_ARGV, "--author-filter="],
    },
    "invalid-utf8": {
        "raw": b'[{"id":"T1","comments":{"nodes":[{"body":"bad \xff byte","author":{"login":"github-actions"}}]}}]'
    },
}

MAX_BYTES_SHAPES = (
    ("abc", "abc"),
    ("-1", "minus-one"),
    ("123456789", "too-long"),
    ("12.5", "decimal"),
    ("", "empty"),
)
for _value, _label in MAX_BYTES_SHAPES:
    CASE_KW["max-bytes-%s" % _label] = {
        "threads": [],
        "argv": [*DEFAULT_ARGV, "--max-bytes=%s" % _value],
    }

NOT_AN_ARRAY = (
    ("object", b"{}"),
    ("scalar", b"42"),
    ("string", b'"hello"'),
    ("null", b"null"),
    ("truncated", b'[{"id"'),
    ("empty", b""),
    ("whitespace", b"   \n"),
)
for _label, _body in NOT_AN_ARRAY:
    CASE_KW["not-an-array-%s" % _label] = {"raw": _body}

JQ_ERRORS = (
    ("element-is-a-number", b"[1]", None),
    ("element-is-a-string", b'["x"]', None),
    ("a-multiline-fixture", b"[\n  1,\n  2\n]\n", None),
    ("containment-truncated", b'[{"comments":{"nodes":[{"author":{"login":5}}]}}]', None),
    (
        "containment-untruncated",
        b'[{"comments":{"nodes":[{"author":{"login":5}}]}}]',
        [*DEFAULT_ARGV, "--author-filter", "gh"],
    ),
    ("iterate-a-long-string", b'[{"comments":{"nodes":"abcdefghijklmnop"}}]', None),
    ("nodes-root-is-a-string", b'[{"comments":{"nodes":["hi"]}}]', None),
    ("login-is-a-number", b'[{"comments":{"nodes":[{"author":{"login":5}}]}}]', None),
    ("nodes-is-a-string", b'[{"comments":{"nodes":"hi"}}]', None),
    ("element-is-an-array", b"[[]]", None),
    # A null ELEMENT is not an error in jq: it indexes to null all the way down and is dropped by the author filter.
    ("element-is-null", b"[null]", None),
)
for _label, _body, _argv in JQ_ERRORS:
    CASE_KW[_label] = {"raw": _body}
    if _argv is not None:
        CASE_KW[_label]["argv"] = _argv

CASES = tuple(CASE_KW)

# The one case whose refusal text is bash naming its own path and line. Compared by shape, in its own test.
DIVERGENT = ("an-out-into-a-missing-directory",)


def decode(raw: bytes) -> str:
    """Bytes as a golden can hold them. The corpus carries a stray byte on purpose, and the same decode runs on both sides of every comparison."""
    return raw.decode("utf-8", errors="backslashreplace")


def run(subject: pathlib.Path, base: pathlib.Path, name: str) -> tuple[int, str, str, str]:
    """One subject, once, from its own working directory."""
    kw = CASE_KW[name]
    argv = list(kw.get("argv", DEFAULT_ARGV))
    base.mkdir(parents=True, exist_ok=True)
    if "raw" in kw:
        (base / "threads.json").write_bytes(kw["raw"])
    elif "threads" in kw:
        (base / "threads.json").write_bytes(json.dumps(kw["threads"]).encode("utf-8"))
    runner = "bash" if subject.suffix == ".sh" else sys.executable
    proc = subprocess.run(
        [runner, str(subject), *argv],
        capture_output=True,
        env=dict(BASE_ENV),
        check=False,
        cwd=str(base),
        timeout=60,
    )
    written = NO_OUT
    for i, flag in enumerate(argv):
        if flag == "--out" and i + 1 < len(argv):
            target = base / argv[i + 1]
            if target.exists():
                written = decode(target.read_bytes())

    def mask(text: str) -> str:
        return text.replace(str(base), "<work>").replace(str(ROOT), "<repo>")

    return (
        proc.returncode,
        mask(decode(proc.stdout)),
        mask(decode(proc.stderr)),
        mask(written),
    )


def render(code: int, stdout: str, stderr: str, written: str) -> str:
    return "%s%s%s\n" % (frozen.render(code, stdout, stderr), OUT_MARKER, written)


def recorded(name: str) -> tuple[int, str, str, str]:
    text = frozen.read(SLUG, name)
    exit_line, rest = text.split("\n", 1)
    stdout, rest = rest.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)
    stderr, written = rest.split(OUT_MARKER, 1)
    return int(exit_line.removeprefix("exit: ")), stdout, stderr, written.removesuffix("\n")


def port(tmp_path: pathlib.Path, name: str) -> tuple[int, str, str, str]:
    return run(PORT, tmp_path / "port", name)


def compare(tmp_path: pathlib.Path, name: str) -> tuple[int, str, str, str]:
    want = recorded(name)
    got = port(tmp_path, name)
    labels = ("exit code", "stdout", "stderr", "the --out bytes")
    for label, a, b in zip(labels, want, got, strict=True):
        assert a == b, "%s: %s diverged:\n--- recorded ---\n%r\n--- port ---\n%r" % (
            name,
            label,
            a,
            b,
        )
    return got


@pytest.mark.parametrize("name", [c for c in CASES if c not in DIVERGENT])
def test_port_matches_the_twins_recorded_output(tmp_path: pathlib.Path, name: str) -> None:
    compare(tmp_path, name)


def test_every_case_has_a_golden_and_no_golden_is_orphaned() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, set(CASES))


# --------------------------------------------------------------------------- What the recordings say ---------------------------------------------------------------------------


def test_the_filter_keeps_and_drops_the_right_threads() -> None:
    """The security control, in one array: only the unresolved, current, bot-rooted thread survives, and it keeps its outsider REPLY."""
    code, stdout, _, _ = recorded("the-filter")
    assert code == 0
    payload = json.loads(stdout)
    assert [t["id"] for t in payload["threads"]] == ["T-keep"]
    assert payload["kept"] == 1
    assert payload["dropped"] == 0
    assert [c["author"] for c in payload["threads"][0]["comments"]] == [BOT, "outsider"]
    assert "please run this" not in stdout, "an outsider-rooted thread's text reached the payload"


def test_empty_and_minimal_payloads() -> None:
    """A payload with zero threads is a valid payload, not an error."""
    for name in ("an-empty-array", "all-dropped", "a-bare-thread", "a-submodule-thread"):
        assert recorded(name)[0] == 0, name
    assert json.loads(recorded("an-empty-array")[1])["kept"] == 0
    assert json.loads(recorded("a-submodule-thread")[1])["threads"][0]["repo"] == "rediacc/renet"


def test_author_filter_variants() -> None:
    assert json.loads(recorded("a-custom-author-filter")[1])["kept"] == 1
    assert json.loads(recorded("an-author-filter-that-misses")[1])["kept"] == 0
    assert json.loads(recorded("an-author-filter-substring")[1])["kept"] == 1


def test_zero_is_not_false() -> None:
    """DIVERGENCE 1. `"isResolved": 0` is DROPPED by jq, because `0 == false` is false there. Written `== False` in Python it would be kept."""
    code, stdout, _, _ = recorded("zero-is-not-false")
    assert code == 0
    assert json.loads(stdout)["kept"] == 0, (
        "a thread with isResolved:0 survived; the port compared with == instead of is"
    )
    # And the true/false ends, so this is not an assertion that drops everything.
    assert json.loads(recorded("false-is-kept")[1])["kept"] == 1
    assert json.loads(recorded("true-is-dropped")[1])["kept"] == 0


def test_del_is_escaped_like_jq() -> None:
    """DIVERGENCE 2: U+007F is six bytes in the payload, not one."""
    code, stdout, _, _ = recorded("del-byte")
    assert code == 0
    assert "\\u007f" in stdout, "DEL was emitted raw; the port is not matching tojson"
    assert "\x7f" not in stdout


def test_byte_cap_counts_bytes_not_codepoints() -> None:
    """DIVERGENCE 3, plus the shedding order.

    The CJK body is three bytes per codepoint, so a cap measured in codepoints would keep a thread the twin sheds.
    """
    code, stdout, stderr, _ = recorded("cap")
    assert code == 0
    payload = json.loads(stdout)
    assert payload["dropped"] == 1
    assert [t["id"] for t in payload["threads"]] == ["T-new"], "the cap shed the NEWEST thread"
    assert "1 oldest thread(s) dropped" in stderr
    # A cap smaller than one thread ends with an EMPTY payload, dropped == n.
    assert json.loads(recorded("cap-to-zero")[1]) == {
        "threads": [],
        "kept": 0,
        "dropped": 2,
        "bytes": 2,
    }


def test_out_file() -> None:
    """`--out` writes the payload and stdout stays empty."""
    code, stdout, _, written = recorded("an-out-file")
    assert code == 0
    assert stdout == ""
    assert written != NO_OUT
    assert json.loads(written)["kept"] == 1
    assert written.endswith("\n")


def test_usage_refusals() -> None:
    """Every exit-2 path the twin had, and the two that are not exit 2."""
    code, _, stderr, _ = recorded("no-threads-flag")
    assert code == 2
    assert "usage: review-payload.sh" in stderr

    # `require_file` exits 1, NOT 2: it is common.sh's refusal, not this script's usage message, and the two carry different codes.
    code, _, stderr, _ = recorded("a-missing-threads-file")
    assert code == 1
    assert "does not exist" in stderr

    # A DIRECTORY where a file is expected: `-f` is false for both.
    assert recorded("threads-is-a-directory")[0] == 1

    for _value, label in MAX_BYTES_SHAPES:
        code, _, stderr, _ = recorded("max-bytes-%s" % label)
        if label == "empty":
            # `${ARG_MAX_BYTES:-49152}`: an EMPTY value takes the default, so this one is a success, not a refusal. Pinned because the `-`/`:-` distinction is exactly what the author-filter guard turns on.
            assert code == 0, "an empty --max-bytes should fall back to the default"
        else:
            assert code == 2, "--max-bytes=%r was accepted" % label
            assert "--max-bytes must be a number" in stderr

    code, _, stderr, _ = recorded("an-empty-author-filter")
    assert code == 2
    assert "--author-filter must not be empty" in stderr


def test_not_a_json_array() -> None:
    """Everything the twin reported as "not a JSON array", including the empty file (`jq -e` exits 4 there) and a bare scalar."""
    for label, _body in NOT_AN_ARRAY:
        code, _, stderr, _ = recorded("not-an-array-%s" % label)
        assert code == 2, "%s was accepted as an array" % label
        assert "threads fixture is not a JSON array" in stderr


def test_jq_runtime_errors_are_reproduced_exactly() -> None:
    """The type errors inside the filter: jq's frame, jq's text, jq's exit 5.

    Both a single-line and a multi-line fixture, because the `(at file:N)` offset is the input's newline count and one case alone would pass with the offset hard-coded to zero.
    """
    code, _, stderr, _ = recorded("element-is-a-number")
    assert code == 5
    assert stderr == 'jq: error (at threads.json:0): Cannot index number with string "isResolved"\n'

    code, _, stderr, _ = recorded("element-is-a-string")
    assert code == 5
    assert "Cannot index string" in stderr

    code, _, stderr, _ = recorded("a-multiline-fixture")
    assert code == 5
    assert "threads.json:4" in stderr, "the (at file:N) offset is not the newline count"

    # BOTH SIDES OF jq's ERROR-MESSAGE TRUNCATION. jq quotes values into a 15-byte buffer, so `"github-actions"` (16 bytes) comes out cut and `"gh"` does not. A port that skipped the truncation agrees on the short one and diverges on the default filter, which is the case that actually ships.
    assert 'string ("github-act...)' in recorded("containment-truncated")[2]
    assert 'string ("gh")' in recorded("containment-untruncated")[2]

    # A null ELEMENT is not an error in jq: it indexes to null all the way down and is dropped by the author filter.
    assert recorded("element-is-null")[0] == 0


def test_invalid_utf8_is_carried_not_refused() -> None:
    """jq substitutes U+FFFD for a stray byte rather than refusing the file, so the port decodes with errors="replace" and the payload still builds."""
    code, stdout, _, _ = recorded("invalid-utf8")
    assert code == 0
    assert json.loads(stdout)["kept"] == 1


def test_pure_helpers_are_exercised_directly() -> None:
    """The exported helpers, without a subprocess."""
    threads = [thread("A"), thread("B", resolved=True)]
    kept = rp.select_threads(threads, BOT)
    assert [t["id"] for t in kept] == ["A"]
    assert list(kept[0]) == ["id", "repo", "pr", "path", "line", "comments"], (
        "key order changed; the payload is compared as bytes downstream"
    )
    remaining, dropped = rp.shed(kept, 10)
    assert (remaining, dropped) == ([], 1)
    assert rp.shed(kept, 100000) == (kept, 0)
    assert rp.compact({"a": "\x7f"}) == '{"a":"\\u007f"}'
    assert rp.utf8_len("一") == 3
    assert rp.jq_error_line(b"a\nb\n") == 2


def test_the_controls_can_fire() -> None:
    """A recording whose assertions have never fired is a claim, not a control.

    Each mutation below is the naive Python spelling the port documents as wrong; every one must change the answer.
    """
    # Divergence 1: `== False` instead of `is False` keeps an `isResolved: 0`.
    naive_zero = [t for t in [thread("T1", resolved=0)] if (t.get("isResolved") or False) == False]  # noqa: E712
    assert naive_zero, "the mutation did not reproduce the naive spelling"
    assert rp.select_threads([thread("T1", resolved=0)], BOT) == [], (
        "the port kept a thread the naive spelling keeps; divergence 1 is not implemented"
    )
    # Divergence 2: plain json.dumps leaves DEL raw and measures one byte.
    naive = json.dumps({"a": "\x7f"}, separators=(",", ":"), ensure_ascii=False)
    assert len(naive.encode()) != len(rp.compact({"a": "\x7f"}).encode())
    # Divergence 3: codepoints against bytes.
    assert len("一" * 10) == 10
    assert rp.utf8_len("一" * 10) == 30


# --------------------------------------------------------------------------- The one divergence, pinned rather than papered over ---------------------------------------------------------------------------


def test_divergence_an_out_into_a_missing_directory(tmp_path: pathlib.Path) -> None:
    """Exit 1 on both. The text diverges: bash named its own path and line, and both sides name the target they could not write."""
    name = "an-out-into-a-missing-directory"
    want = recorded(name)
    got = port(tmp_path, name)
    assert want[0] == got[0] == 1
    assert want[1] == got[1] == ""
    assert "nodir/payload.json" in want[2], "the twin's refusal did not name the target"
    assert "nodir/payload.json" in got[2], "the port's refusal did not name the target"
    assert want[3] == got[3] == NO_OUT


# --------------------------------------------------------------------------- The control: these goldens can actually fail ---------------------------------------------------------------------------


def test_a_planted_inversion_of_the_root_author_filter_is_caught(tmp_path: pathlib.Path) -> None:
    """THE CONTROL ON THE GOLDENS. Accept a thread whose ROOT comment is not the bot's.

    That filter is the security product of this script: a thread an outsider opened carries text the outsider chose, and letting it through puts that text in front of an autonomous model.

    `the-filter` records one kept thread and no trace of `please run this`; a mutant that drops the check keeps two and carries the sentence. The mutant is a throwaway copy, and the tracked port is never touched.
    """
    original = PORT.read_text(encoding="utf-8")
    anchor = "        if not _contains(root_login, author_filter):\n            continue\n"
    assert original.count(anchor) == 1, "the plant's anchor moved"
    mutated = original.replace(anchor, "        if False:\n            continue\n")

    mutant = tmp_path / "plant" / "mutant.py"
    mutant.parent.mkdir(parents=True)
    mutant.write_text(mutated, encoding="utf-8")

    name = "the-filter"
    planted = run(mutant, tmp_path / "planted", name)
    want = recorded(name)
    assert "please run this" not in want[1], "the recorded corpus moved"
    assert "please run this" in planted[1], "the plant did not let the outsider thread through"
    assert json.loads(planted[1])["kept"] == 2

    compare(tmp_path, name)
    assert PORT.read_text(encoding="utf-8") == original

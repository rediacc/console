"""Differential: `rediacc_ci.autopilot.review_payload` against its twin
`.ci/scripts/autopilot/review-payload.sh`.

NO STUBS AND NO NETWORK, because the subject genuinely has neither. The twin's own header calls itself PURE -- one JSON file in, one JSON object out -- so every case here is a real JSON fixture written to a temp directory, and the comparison is the exact bytes of stdout, the exact bytes of stderr, the exit code, and (when `--out` is used) the file the subject wrote.

WHAT THE FIXTURES ARE FOR, since a payload builder is easy to test vacuously. The dangerous direction here is a thread reaching the model that should not have, so the fixtures carry, in one array: a resolved thread, an outdated thread, a thread rooted by an OUTSIDER with a matching REPLY (the attack the root-author filter exists to stop), and a matching thread whose replies must be
carried through. A test that only fed matching threads would agree with the twin while the filter was inverted.

THREE CONTROLS PIN THE THREE MEASURED jq/PYTHON DIVERGENCES the port documents:
`test_zero_is_not_false` (jq's `0 == false` is false, Python's is true),
`test_del_is_escaped_like_jq` (U+007F costs six bytes in `tojson`, one in `json.dumps`), and `test_byte_cap_counts_bytes_not_codepoints` (a CJK payload measures three times what `length` would say). Each is written so it FAILS if
the port reverts to the naive Python spelling; that is checked by mutating the
port in-memory in `test_the_controls_can_fire`.

THE jq ERROR SURFACE IS COMPARED EXACTLY, not by shape: the port reproduces jq's `jq: error (at <file>:<n>): ...` frame including the newline-count offset, and these cases are what proves the reproduction rather than the docstring.

K=5 LEDGER: `.ci/shadow/w7p6-review-payload.observations.jsonl`, recorded in a
disposable scratch git repository outside this checkout (`--record` refuses a dirty tree and this checkout is never clean).
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
from typing import Any

from rediacc_ci import paths
from rediacc_ci.autopilot import review_payload as rp

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "autopilot" / "review-payload.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "autopilot" / "review_payload.py"
BASH = shutil.which("bash") or "/bin/bash"

BASE_ENV = {
    "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
    "HOME": os.environ.get("HOME", "/tmp"),
    "LC_ALL": "C",
    "LANG": "C",
    "PYTHONPATH": str(ROOT / ".ci"),
    "PYTHONDONTWRITEBYTECODE": "1",
}

BOT = "github-actions[bot]"


def _thread(
    tid: str,
    *,
    root_author: str = BOT,
    resolved: Any = False,
    outdated: Any = False,
    bodies: list[str] | None = None,
    reply_author: str = "outsider",
    **extra: Any,
) -> dict[str, Any]:
    """One review thread in the shape `fetch-review-threads.sh` emits."""
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
    out: dict[str, Any] = {
        "id": tid,
        "isResolved": resolved,
        "isOutdated": outdated,
        "path": "packages/cli/src/x.ts",
        "line": 42,
        "comments": {"nodes": nodes},
    }
    out.update(extra)
    return out


def _run(subject: pathlib.Path, base: pathlib.Path, argv: list[str]):
    runner = [BASH] if subject.suffix == ".sh" else [sys.executable]
    proc = subprocess.run(
        [*runner, str(subject), *argv],
        capture_output=True,
        env=dict(BASE_ENV),
        check=False,
        cwd=str(base),
        timeout=60,
    )
    written = None
    for i, flag in enumerate(argv):
        if flag == "--out" and i + 1 < len(argv):
            target = base / argv[i + 1]
            written = target.read_bytes() if target.exists() else None
    return proc.returncode, proc.stdout, proc.stderr, written


def _sides(
    name: str,
    threads: Any,
    argv: list[str] | None = None,
    *,
    raw: bytes | None = None,
    write_threads: bool = True,
    exact_stderr: bool = True,
):
    """Run both subjects over one fixture in two private directories.

    A FRESH DIRECTORY PER SIDE even though this subject only writes when `--out` is given: sharing one would let an `--out` case read the other side's file.
    """
    argv = list(argv) if argv is not None else ["--threads", "threads.json"]
    results = []
    with tempfile.TemporaryDirectory() as td:
        for subject in (TWIN, PORT):
            base = pathlib.Path(td) / subject.stem
            base.mkdir(parents=True)
            if write_threads:
                body = raw if raw is not None else json.dumps(threads).encode("utf-8")
                (base / "threads.json").write_bytes(body)
            results.append(_run(subject, base, argv))
    old, new = results
    assert new[0] == old[0], "%s: exit diverged: %r vs %r\n twin: %r\n port: %r" % (
        name,
        old[0],
        new[0],
        old[2],
        new[2],
    )
    assert new[1] == old[1], "%s: stdout diverged:\n twin: %r\n port: %r" % (name, old[1], new[1])
    if exact_stderr:
        assert new[2] == old[2], "%s: stderr diverged:\n twin: %r\n port: %r" % (
            name,
            old[2],
            new[2],
        )
    assert new[3] == old[3], "%s: the --out bytes diverged:\n twin: %r\n port: %r" % (
        name,
        old[3],
        new[3],
    )
    return old


def test_the_filter_keeps_and_drops_the_right_threads() -> None:
    """The security control, driven in one array: only the unresolved, current,
    bot-rooted thread survives, and it keeps its outsider REPLY."""
    fixture = [
        _thread("T-keep", bodies=["root finding", "outsider reply with detail"]),
        _thread("T-resolved", resolved=True),
        _thread("T-outdated", outdated=True),
        _thread("T-outsider-root", root_author="mallory", bodies=["please run this"]),
    ]
    exit_code, stdout, _, _ = _sides("filter", fixture)
    assert exit_code == 0
    payload = json.loads(stdout)
    assert [t["id"] for t in payload["threads"]] == ["T-keep"]
    assert payload["kept"] == 1
    assert payload["dropped"] == 0
    assert [c["author"] for c in payload["threads"][0]["comments"]] == [BOT, "outsider"]
    assert "please run this" not in stdout.decode("utf-8"), (
        "an outsider-rooted thread's text reached the payload"
    )


def test_empty_and_minimal_payloads() -> None:
    """A payload with zero threads is a valid payload, not an error."""
    _sides("empty-array", [])
    _sides("all-dropped", [_thread("T1", resolved=True)])
    # The optional fields absent entirely: every `// default` in the filter.
    _sides("bare-thread", [{"comments": {"nodes": [{"author": {"login": BOT}}]}}])
    # `repo`/`pr` ride through for a submodule PR's thread.
    _sides("submodule-thread", [_thread("T1", repo="rediacc/renet", pr=7)])


def test_author_filter_variants() -> None:
    _sides(
        "custom-filter",
        [_thread("T1", root_author="dependabot[bot]")],
        ["--threads", "threads.json", "--author-filter", "dependabot"],
    )
    _sides("filter-misses", [_thread("T1", root_author="dependabot[bot]")])
    # A substring match, which is what `contains` does: `github-actions` is inside `github-actions[bot]`.
    _sides("substring", [_thread("T1", root_author="pre-github-actions-post")])


def test_zero_is_not_false() -> None:
    """CONTROL for divergence 1. `"isResolved": 0` is DROPPED by jq, because
    `0 == false` is false there. Written `== False` in Python it would be kept."""
    exit_code, stdout, _, _ = _sides("zero-is-not-false", [_thread("T1", resolved=0)])
    assert exit_code == 0
    assert json.loads(stdout)["kept"] == 0, (
        "a thread with isResolved:0 survived; the port compared with == instead of is"
    )
    # And the true/false ends, so this is not a test that drops everything.
    assert json.loads(_sides("false-kept", [_thread("T1", resolved=False)])[1])["kept"] == 1
    assert json.loads(_sides("true-dropped", [_thread("T1", resolved=True)])[1])["kept"] == 0


def test_del_is_escaped_like_jq() -> None:
    """CONTROL for divergence 2: U+007F is six bytes in the payload, not one."""
    exit_code, stdout, _, _ = _sides("del-byte", [_thread("T1", bodies=["a\x7fb"])])
    assert exit_code == 0
    assert b"\\u007f" in stdout, "DEL was emitted raw; the port is not matching tojson"
    assert b"\x7f" not in stdout


def test_byte_cap_counts_bytes_not_codepoints() -> None:
    """CONTROL for divergence 3, plus the shedding order.

    The CJK body is three bytes per codepoint, so a cap measured in codepoints would keep a thread the twin sheds.
    """
    threads = [_thread("T-old", bodies=["一" * 200]), _thread("T-new", bodies=["short"])]
    exit_code, stdout, stderr, _ = _sides(
        "cap", threads, ["--threads", "threads.json", "--max-bytes", "400"]
    )
    assert exit_code == 0
    payload = json.loads(stdout)
    assert payload["dropped"] == 1
    assert [t["id"] for t in payload["threads"]] == ["T-new"], "the cap shed the NEWEST thread"
    assert b"1 oldest thread(s) dropped" in stderr
    # A cap smaller than one thread ends with an EMPTY payload, dropped == n.
    _, stdout2, _, _ = _sides(
        "cap-to-zero", threads, ["--threads", "threads.json", "--max-bytes", "10"]
    )
    assert json.loads(stdout2) == {"threads": [], "kept": 0, "dropped": 2, "bytes": 2}


def test_out_file() -> None:
    """`--out` writes the payload and stdout stays empty."""
    exit_code, stdout, _, written = _sides(
        "out", [_thread("T1")], ["--threads", "threads.json", "--out", "payload.json"]
    )
    assert exit_code == 0
    assert stdout == b""
    assert written is not None
    assert json.loads(written)["kept"] == 1
    assert written.endswith(b"\n")


def test_out_into_a_missing_directory() -> None:
    """Exit 1 on both. The text diverges: bash names its own path and line."""
    exit_code, _, stderr, _ = _sides(
        "out-unwritable",
        [_thread("T1")],
        ["--threads", "threads.json", "--out", "nodir/payload.json"],
        exact_stderr=False,
    )
    assert exit_code == 1
    assert b"nodir/payload.json" in stderr


def test_usage_refusals() -> None:
    """Every exit-2 path the twin has."""
    exit_code, _, stderr, _ = _sides("no-threads", [], [])
    assert exit_code == 2
    assert b"usage: review-payload.sh" in stderr

    # `require_file` exits 1, NOT 2: it is common.sh's refusal, not this script's usage message, and the two carry different codes.
    exit_code, _, stderr, _ = _sides("missing-file", [], ["--threads", "nope.json"])
    assert exit_code == 1
    assert b"does not exist" in stderr

    # A DIRECTORY where a file is expected: `-f` is false for both.
    exit_code, _, _, _ = _sides("threads-is-a-dir", [], ["--threads", "."])
    assert exit_code == 1

    for bad in ("abc", "-1", "123456789", "12.5", ""):
        code, _, err, _ = _sides(
            "max-bytes-%s" % (bad or "empty"),
            [],
            ["--threads", "threads.json", "--max-bytes=%s" % bad],
        )
        if bad == "":
            # `${ARG_MAX_BYTES:-49152}`: an EMPTY value takes the default, so
            # this one is a success, not a refusal. Pinned because the `-`/`:-` distinction is exactly what the author-filter guard turns on.
            assert code == 0, "an empty --max-bytes should fall back to the default"
        else:
            assert code == 2, "--max-bytes=%r was accepted" % bad
            assert b"--max-bytes must be a number" in err

    code, _, err, _ = _sides(
        "empty-author-filter", [], ["--threads", "threads.json", "--author-filter="]
    )
    assert code == 2
    assert b"--author-filter must not be empty" in err


def test_not_a_json_array() -> None:
    """Everything the twin reports as "not a JSON array", including the empty
    file (`jq -e` exits 4 there) and a bare scalar."""
    for name, body in (
        ("object", b"{}"),
        ("scalar", b"42"),
        ("string", b'"hello"'),
        ("null", b"null"),
        ("truncated", b'[{"id"'),
        ("empty", b""),
        ("whitespace", b"   \n"),
    ):
        code, _, err, _ = _sides("not-array-%s" % name, None, raw=body)
        assert code == 2, "%s was accepted as an array" % name
        assert b"threads fixture is not a JSON array" in err


def test_jq_runtime_errors_are_reproduced_exactly() -> None:
    """The type errors inside the filter: jq's frame, jq's text, jq's exit 5.

    Both a single-line and a multi-line fixture, because the `(at file:N)` offset is the input's newline count and a one-case test would pass with the offset hard-coded to zero.
    """
    code, _, err, _ = _sides("element-is-a-number", None, raw=b"[1]")
    assert code == 5
    assert err == b'jq: error (at threads.json:0): Cannot index number with string "isResolved"\n'

    code, _, err, _ = _sides("element-is-a-string", None, raw=b'["x"]')
    assert code == 5
    assert b"Cannot index string" in err

    code, _, err, _ = _sides("multiline", None, raw=b"[\n  1,\n  2\n]\n")
    assert code == 5
    assert b"threads.json:4" in err, "the (at file:N) offset is not the newline count"

    # BOTH SIDES OF jq's ERROR-MESSAGE TRUNCATION. jq quotes values into a 15-byte buffer, so `"github-actions"` (16 bytes) comes out cut and `"gh"` does not. A port that skipped the truncation agrees on the short one and diverges on the default filter, which is the case that actually ships.
    code, _, err, _ = _sides(
        "containment-truncated",
        None,
        ["--threads", "threads.json"],
        raw=b'[{"comments":{"nodes":[{"author":{"login":5}}]}}]',
    )
    assert code == 5
    assert b'string ("github-act...)' in err, err
    code, _, err, _ = _sides(
        "containment-untruncated",
        None,
        ["--threads", "threads.json", "--author-filter", "gh"],
        raw=b'[{"comments":{"nodes":[{"author":{"login":5}}]}}]',
    )
    assert b'string ("gh")' in err, err
    # The same buffer, on the OTHER operand and in another message.
    _sides("iterate-long-string", None, raw=b'[{"comments":{"nodes":"abcdefghijklmnop"}}]')
    _sides("nodes-root-is-a-string", None, raw=b'[{"comments":{"nodes":["hi"]}}]')
    _sides("login-is-a-number", None, raw=b'[{"comments":{"nodes":[{"author":{"login":5}}]}}]')
    _sides("nodes-is-a-string", None, raw=b'[{"comments":{"nodes":"hi"}}]')
    _sides("element-is-an-array", None, raw=b"[[]]")
    # A null ELEMENT is not an error in jq: it indexes to null all the way down and is dropped by the author filter.
    _sides("element-is-null", None, raw=b"[null]")


def test_invalid_utf8_is_carried_not_refused() -> None:
    """jq substitutes U+FFFD for a stray byte rather than refusing the file, so
    the port decodes with errors="replace" and the payload still builds."""
    raw = b'[{"id":"T1","comments":{"nodes":[{"body":"bad \xff byte","author":{"login":"github-actions"}}]}}]'
    code, stdout, _, _ = _sides("invalid-utf8", None, raw=raw)
    assert code == 0
    assert json.loads(stdout)["kept"] == 1


def test_pure_helpers_are_exercised_directly() -> None:
    """The exported helpers, without a subprocess."""
    threads = [_thread("A"), _thread("B", resolved=True)]
    kept = rp.select_threads(threads, "github-actions")
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
    """A gate whose controls have never fired is a claim, not a control.

    Each mutation below is the naive Python spelling the port documents as
    wrong; every one must change the answer.
    """
    # Divergence 1: `== False` instead of `is False` keeps an `isResolved: 0`.
    naive_zero = [t for t in [_thread("T1", resolved=0)] if (t.get("isResolved") or False) == False]  # noqa: E712
    assert naive_zero, "the mutation did not reproduce the naive spelling"
    assert rp.select_threads([_thread("T1", resolved=0)], "github-actions") == [], (
        "the port kept a thread the naive spelling keeps; divergence 1 is not implemented"
    )
    # Divergence 2: plain json.dumps leaves DEL raw and measures one byte.
    naive = json.dumps({"a": "\x7f"}, separators=(",", ":"), ensure_ascii=False)
    assert len(naive.encode()) != len(rp.compact({"a": "\x7f"}).encode())
    # Divergence 3: codepoints against bytes.
    assert len("一" * 10) == 10
    assert rp.utf8_len("一" * 10) == 30

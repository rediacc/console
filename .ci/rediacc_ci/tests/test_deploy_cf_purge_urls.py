"""Differential: `rediacc_ci.deploy.cf_purge_urls` against its twin
`.ci/scripts/deploy/cf-purge-urls.sh`.

A RECORDING FAKE `curl` ON A SCRATCH PATH. Nothing here reaches Cloudflare: the
fake logs its exact argv, answers from the environment, and every case pins a
fixture zone id and a fixture credential, so even a bypassed fake would not name
a real zone. `.ci/shadow/w7p5a-status.json` records this path as blocked only for
the "one real run" clause and says in as many words that the mocked parity ledger
is a separate, achievable piece of work. This is that piece.

THE REQUEST LOG IS COMPARED, NOT JUST THE STREAMS. The observable effect of this
script is a set of POST bodies against a live CDN, and two implementations can
print the same tally while purging different URLs, batching differently, or
sending the credential in the wrong header.
`test_the_request_shape_is_asserted_in_full` pins the literal argv of a purge --
method, URL, both headers, and the `--data` payload -- and then checks the port's
own builders produce the same thing.

BOTH DEFECT PATHS ARE DRIVEN, because the twin's header promises "always exits 0
even on credential/auth/API failures" and two paths break that promise: a curl
transport failure exits 6 and a non-JSON body exits 5. Reproduced, because
agreement with the live twin is the deliverable.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import typing

from rediacc_ci import paths
from rediacc_ci.deploy import cf_purge_urls as port

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "deploy" / "cf-purge-urls.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "deploy" / "cf_purge_urls.py"
BASH = shutil.which("bash") or "/bin/bash"

ZONE = "zone-fixture"
# Named BEARER rather than TOKEN because ruff's S105 keys on the NAME: a constant called TOKEN is "a hardcoded password" to the linter even when its value is visibly a fixture.
BEARER = "tok-fixture"

FAKE_CURL = """#!/usr/bin/python3
import json
import os
import sys

argv = sys.argv[1:]
log = os.environ["FAKE_CALL_LOG"]
with open(log, "a") as fh:
    fh.write("curl\\t" + "\\t".join(argv) + "\\n")
with open(log) as fh:
    call_index = len([line for line in fh if line.strip()])

if os.environ.get("FAKE_CURL_RC"):
    sys.stderr.write("curl: (6) Could not resolve host: api.cloudflare.com\\n")
    sys.exit(int(os.environ["FAKE_CURL_RC"]))

if os.environ.get("FAKE_CURL_BODY") is not None:
    sys.stdout.write(os.environ["FAKE_CURL_BODY"])
    sys.exit(0)

fail_on = os.environ.get("FAKE_FAIL_ON_CALL")
if fail_on and call_index == int(fail_on):
    sys.stdout.write(
        json.dumps({"success": False, "errors": [{"code": 1012, "message": "Invalid zone"}]})
        + "\\n"
    )
    sys.exit(0)

sys.stdout.write(json.dumps({"success": True, "errors": [], "result": {"id": "purge"}}) + "\\n")
"""

# `jq` is a real prerequisite of BOTH sides (the port shells out to the same binary, for the reasons in its docstring) and `sed` is what the twin's --help is made of. Nothing else is on the scratch PATH, so a tool leaking in would be visible as a behaviour change rather than as a silent convenience.
PATH_MINIMUM = ("jq", "sed")


def _bin(tmp_path: pathlib.Path, name: str, *, drop: str = "") -> str:
    stub = tmp_path / name
    stub.mkdir(parents=True, exist_ok=True)
    for real_name in PATH_MINIMUM:
        if real_name == drop:
            continue
        real = shutil.which(real_name)
        assert real is not None, f"{real_name} is missing from this machine"
        link = stub / real_name
        if not link.exists():
            link.symlink_to(real)
    if drop != "curl":
        curl = stub / "curl"
        curl.write_text(FAKE_CURL, encoding="utf-8")
        curl.chmod(0o755)
    else:
        assert shutil.which("curl", path=str(stub)) is None, "curl leaked into the stub PATH"
    return str(stub)


def _run(
    subject: pathlib.Path,
    tmp_path: pathlib.Path,
    args: list[str],
    *,
    stdin: str | None = None,
    drop: str = "",
    drop_env: tuple[str, ...] = (),
    **extra: str,
):
    side = "old" if subject.suffix == ".sh" else "new"
    call_log = tmp_path / f"{side}-calls.log"
    call_log.write_text("", encoding="utf-8")
    env = {
        "PATH": _bin(tmp_path, f"{side}-bin", drop=drop),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LC_ALL": "C",
        "LANG": "C",
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "FAKE_CALL_LOG": str(call_log),
        "CLOUDFLARE_API_TOKEN": BEARER,
    }
    env.update(extra)
    for name in drop_env:
        env.pop(name, None)
    runner = [BASH] if subject.suffix == ".sh" else [sys.executable]
    proc = subprocess.run(
        [*runner, str(subject), *args],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=120,
        input="" if stdin is None else stdin,
    )
    calls = [line for line in call_log.read_text(encoding="utf-8").splitlines() if line]
    return proc, calls


def run_both(tmp_path: pathlib.Path, args: list[str], **kw):
    old, old_calls = _run(TWIN, tmp_path, args, **kw)
    new, new_calls = _run(PORT, tmp_path, args, **kw)
    return old, new, old_calls, new_calls


def _assert_agree(old, new, label: str, old_calls=None, new_calls=None) -> None:
    assert new.returncode == old.returncode, (
        f"{label}: exit diverged: {old.returncode!r} vs {new.returncode!r}"
    )
    assert new.stdout == old.stdout, (
        f"{label}: stdout diverged:\nold: {old.stdout!r}\nnew: {new.stdout!r}"
    )
    assert new.stderr == old.stderr, (
        f"{label}: stderr diverged:\nold: {old.stderr!r}\nnew: {new.stderr!r}"
    )
    if old_calls is not None:
        assert new_calls == old_calls, (
            f"{label}: request sequence diverged:\nold: {old_calls}\nnew: {new_calls}"
        )


def purge_call(urls: list[str], headers: list[str] | None = None) -> str:
    """The recorded line for one purge, built from the port's own helpers."""
    auth = ["-H", "Authorization: Bearer %s" % BEARER] if headers is None else headers
    argv = port.curl_argv(ZONE, auth, port.payload_for(urls))
    return "curl\t" + "\t".join(argv[1:])


def test_the_request_shape_is_asserted_in_full(tmp_path: pathlib.Path) -> None:
    """THE REQUEST, PINNED AGAINST LITERAL BYTES rather than against the port's
    own helpers, so a change in both would still be caught. Method, URL, both
    headers, and the JSON body jq builds."""
    old, new, old_calls, new_calls = run_both(tmp_path, ["--zone", ZONE, "https://a", "https://b"])
    assert old.returncode == 0
    assert old_calls == [
        (
            "curl\t-sS\t-X\tPOST\t"
            "https://api.cloudflare.com/client/v4/zones/zone-fixture/purge_cache\t"
            "-H\tAuthorization: Bearer tok-fixture\t"
            "-H\tContent-Type: application/json\t"
            '--data\t{"files":["https://a","https://b"]}'
        )
    ]
    assert old_calls == [purge_call(["https://a", "https://b"])]
    assert old.stdout == (
        "cf-purge-urls.sh: purging 2 URL(s) from CF zone zone-fixture\n"
        "cf-purge-urls.sh: purged 2 URL(s) successfully\n"
    )
    assert old.stderr == "", "this script's happy path must say nothing on stderr"
    _assert_agree(old, new, "request-shape", old_calls, new_calls)


def test_help_is_byte_identical(tmp_path: pathlib.Path) -> None:
    """`--help` is a program printing its own source through two `sed` passes on
    one side and a string constant on the other. The bytes must agree."""
    old, new, old_calls, new_calls = run_both(tmp_path, ["--help"])
    assert old.returncode == 0
    assert old.stdout.startswith("Purge a list of URLs from Cloudflare cache.\n")
    assert old.stdout.endswith("there.\n\n"), "the trailing blank line the sed range includes"
    assert old_calls == []
    _assert_agree(old, new, "help", old_calls, new_calls)

    short_old, short_new, _oc, _nc = run_both(tmp_path, ["-h"])
    _assert_agree(short_old, short_new, "help-short", None, None)
    assert short_old.stdout == old.stdout

    # `--help` AFTER other arguments still wins, because the loop acts the moment it reaches the token.
    late_old, late_new, _loc, _lnc = run_both(tmp_path, ["https://a", "--help"])
    assert late_old.stdout == old.stdout
    _assert_agree(late_old, late_new, "help-late", None, None)


def test_help_matches_the_twins_header_extraction() -> None:
    """THE STALENESS ALARM for divergence 2 in the port's docstring. `HELP` is a
    literal, so this recomputes `sed -n '2,/^$/p' | sed 's/^# \\{0,1\\}//'` from
    the twin's source and fails if the two ever drift apart."""
    lines = TWIN.read_text(encoding="utf-8").split("\n")
    picked: list[str] = []
    for line in lines[1:]:
        picked.append(line)
        if line == "":
            break
    stripped = []
    for line in picked:
        if line.startswith("# "):
            stripped.append(line[2:])
        elif line.startswith("#"):
            stripped.append(line[1:])
        else:
            stripped.append(line)
    extracted = "".join(line + "\n" for line in stripped)
    assert extracted == port.HELP


def test_a_missing_zone_is_refused(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, [])
    assert old.returncode == 1
    assert old.stderr == "::error::cf-purge-urls.sh: --zone <ZONE_ID> is required\n"
    assert old.stdout == ""
    assert old_calls == []
    _assert_agree(old, new, "no-zone", old_calls, new_calls)


def test_no_urls_is_a_clean_no_op(tmp_path: pathlib.Path) -> None:
    """THE ZERO-INPUT CASE, and note it is a PASS in this script rather than a
    refusal: nothing to purge is a legitimate state after an upload that changed
    no files. Pinned so a port cannot turn it into a request against `{files:[]}`."""
    old, new, old_calls, new_calls = run_both(tmp_path, ["--zone", ZONE])
    assert old.returncode == 0
    assert old.stdout == "cf-purge-urls.sh: no URLs to purge\n"
    assert old_calls == [], "a run with no URLs made a request"
    _assert_agree(old, new, "no-urls", old_calls, new_calls)


def test_the_zero_check_runs_before_the_credential_check(tmp_path: pathlib.Path) -> None:
    """ORDER IS OBSERVABLE: no URLs and no credentials says "no URLs to purge",
    not "no Cloudflare credentials"."""
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["--zone", ZONE], drop_env=("CLOUDFLARE_API_TOKEN",)
    )
    assert old.stdout == "cf-purge-urls.sh: no URLs to purge\n"
    assert old.stderr == ""
    _assert_agree(old, new, "zero-before-creds", old_calls, new_calls)


def test_no_credentials_skips_the_purge_and_still_exits_zero(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["--zone", ZONE, "https://a"], drop_env=("CLOUDFLARE_API_TOKEN",)
    )
    assert old.returncode == 0
    assert old.stderr == (
        "::warning::cf-purge-urls.sh: no Cloudflare credentials in env "
        "(set CLOUDFLARE_API_TOKEN, or CF_GLOBAL_API_KEY+CF_EMAIL); skipping purge\n"
    )
    assert old.stdout == "", "the purging line must not print when nothing is purged"
    assert old_calls == []
    _assert_agree(old, new, "no-creds", old_calls, new_calls)


def test_half_a_global_key_is_not_a_credential(tmp_path: pathlib.Path) -> None:
    """`CF_GLOBAL_API_KEY` without `CF_EMAIL` is the no-credential branch, not a
    request with a missing header."""
    old, new, old_calls, new_calls = run_both(
        tmp_path,
        ["--zone", ZONE, "https://a"],
        drop_env=("CLOUDFLARE_API_TOKEN",),
        CF_GLOBAL_API_KEY="gk-fixture",
    )
    assert old.returncode == 0
    assert "no Cloudflare credentials in env" in old.stderr
    assert old_calls == []
    _assert_agree(old, new, "half-global-key", old_calls, new_calls)


def test_the_global_key_pair_sends_two_headers_in_the_twins_order(
    tmp_path: pathlib.Path,
) -> None:
    old, new, old_calls, new_calls = run_both(
        tmp_path,
        ["--zone", ZONE, "https://a"],
        drop_env=("CLOUDFLARE_API_TOKEN",),
        CF_GLOBAL_API_KEY="gk-fixture",
        CF_EMAIL="ci@example.invalid",
    )
    assert old.returncode == 0
    assert old_calls == [
        purge_call(
            ["https://a"],
            headers=["-H", "X-Auth-Email: ci@example.invalid", "-H", "X-Auth-Key: gk-fixture"],
        )
    ]
    assert "X-Auth-Email: ci@example.invalid\t-H\tX-Auth-Key: gk-fixture" in old_calls[0]
    _assert_agree(old, new, "global-key", old_calls, new_calls)


def test_a_token_wins_over_a_global_key(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(
        tmp_path,
        ["--zone", ZONE, "https://a"],
        CF_GLOBAL_API_KEY="gk-fixture",
        CF_EMAIL="ci@example.invalid",
    )
    assert "Authorization: Bearer tok-fixture" in old_calls[0]
    assert "X-Auth-Key" not in old_calls[0]
    _assert_agree(old, new, "token-wins", old_calls, new_calls)


def test_stdin_urls_are_appended_to_the_positional_ones(tmp_path: pathlib.Path) -> None:
    """POSITIONAL FIRST, THEN STDIN, and an EMPTY LINE is skipped rather than
    purged as the empty string."""
    old, new, old_calls, new_calls = run_both(
        tmp_path,
        ["--zone", ZONE, "https://pos"],
        stdin="https://one\n\nhttps://two\n",
    )
    assert old.returncode == 0
    assert old_calls == [purge_call(["https://pos", "https://one", "https://two"])]
    assert '{"files":["https://pos","https://one","https://two"]}' in old_calls[0]
    _assert_agree(old, new, "stdin", old_calls, new_calls)


def test_a_final_line_without_a_newline_is_dropped(tmp_path: pathlib.Path) -> None:
    """THE BASH FACT A `for line in sys.stdin` PORT GETS WRONG. `read` stores the
    partial last line and then returns non-zero at EOF, so the loop body never
    runs for it: the twin purges ONE url here, not two. A port that kept it
    would purge a URL the twin does not."""
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["--zone", ZONE], stdin="https://kept\nhttps://dropped"
    )
    assert old.returncode == 0
    assert old.stdout.startswith("cf-purge-urls.sh: purging 1 URL(s) ")
    assert '{"files":["https://kept"]}' in old_calls[0]
    assert "dropped" not in old_calls[0]
    _assert_agree(old, new, "partial-line", old_calls, new_calls)


def test_thirty_one_urls_are_two_batches_of_thirty_and_one(tmp_path: pathlib.Path) -> None:
    urls = ["https://x/%d" % n for n in range(1, 32)]
    old, new, old_calls, new_calls = run_both(tmp_path, ["--zone", ZONE, *urls])
    assert old.returncode == 0
    assert len(old_calls) == 2, "the 30-URL chunk boundary moved"
    assert old_calls == [purge_call(urls[:30]), purge_call(urls[30:])]
    assert old.stdout == (
        "cf-purge-urls.sh: purging 31 URL(s) from CF zone zone-fixture\n"
        "cf-purge-urls.sh: purged 31 URL(s) successfully\n"
    )
    _assert_agree(old, new, "chunking", old_calls, new_calls)


def test_a_failed_second_batch_reports_index_thirty_and_stops(tmp_path: pathlib.Path) -> None:
    """THE INDEX IN THE WARNING IS THE URL OFFSET, not the batch number, and the
    loop STOPS at the first failure rather than trying the rest."""
    urls = ["https://x/%d" % n for n in range(1, 70)]
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["--zone", ZONE, *urls], FAKE_FAIL_ON_CALL="2"
    )
    assert old.returncode == 0, "a failed batch is best-effort, so still exit 0"
    assert old.stderr == (
        "::warning::CF purge failed for batch starting at index 30 "
        "(best-effort; Cache Rule makes this non-critical):\n"
        '[{"code":1012,"message":"Invalid zone"}]\n'
    )
    assert len(old_calls) == 2, "the sweep continued past a failed batch"
    assert "purged 69 URL(s) successfully" not in old.stdout
    _assert_agree(old, new, "batch-failure", old_calls, new_calls)


def test_an_unsuccessful_body_prints_the_errors_array_on_stderr(
    tmp_path: pathlib.Path,
) -> None:
    old, new, old_calls, new_calls = run_both(
        tmp_path,
        ["--zone", ZONE, "https://a"],
        FAKE_CURL_BODY='{"success":false,"errors":[{"code":1012,"message":"Invalid zone"}]}\n',
    )
    assert old.returncode == 0
    assert old.stdout == "cf-purge-urls.sh: purging 1 URL(s) from CF zone zone-fixture\n"
    assert old.stderr.endswith('[{"code":1012,"message":"Invalid zone"}]\n')
    _assert_agree(old, new, "unsuccessful-body", old_calls, new_calls)


def test_a_body_with_no_errors_key_prints_null(tmp_path: pathlib.Path) -> None:
    """`jq -c '.errors'` over a body without the key emits `null` rather than
    failing, so the warning is followed by the word null. Pinned because a port
    guarding the lookup would print an empty line instead."""
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["--zone", ZONE, "https://a"], FAKE_CURL_BODY='{"success":false}\n'
    )
    assert old.returncode == 0
    assert old.stderr.endswith("null\n")
    _assert_agree(old, new, "no-errors-key", old_calls, new_calls)


def test_an_empty_body_warns_and_prints_nothing_after_it(tmp_path: pathlib.Path) -> None:
    """The third jq shape: EMPTY input makes both `jq -r '.success // false'` and
    `jq -c '.errors'` emit nothing at all and exit 0, so the run warns and ends
    green with no errors line. Not a parse error, and not a pass."""
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["--zone", ZONE, "https://a"], FAKE_CURL_BODY=""
    )
    assert old.returncode == 0
    assert old.stderr == (
        "::warning::CF purge failed for batch starting at index 0 "
        "(best-effort; Cache Rule makes this non-critical):\n"
    )
    assert "jq:" not in old.stderr
    _assert_agree(old, new, "empty-body", old_calls, new_calls)


def test_defect_a_non_json_body_exits_five_despite_the_always_zero_promise(
    tmp_path: pathlib.Path,
) -> None:
    """DEFECT 1, PINNED. The header (twin lines 21-28) promises the script
    "always exits 0 even on credential/auth/API failures". An HTML error page
    reaches an unguarded `jq` inside an ASSIGNMENT, so jq's parse error goes to
    stderr and `set -e` ends the run with jq's status 5.

    Reproduced because agreement with the live twin is the deliverable;
    repaired, this test goes red and names the port that must follow.
    """
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["--zone", ZONE, "https://a"], FAKE_CURL_BODY="<html>504 Gateway Timeout</html>\n"
    )
    assert old.returncode == 5, f"the twin's jq status changed: {old.returncode}"
    assert "jq: parse error" in old.stderr
    assert "purged 1 URL(s) successfully" not in old.stdout
    assert port.ALWAYS_EXITS_ZERO_IS_FALSE
    _assert_agree(old, new, "non-json", old_calls, new_calls)


def test_defect_a_transport_failure_exits_six_despite_the_always_zero_promise(
    tmp_path: pathlib.Path,
) -> None:
    """DEFECT 2, PINNED. `RESPONSE=$(curl -sS ...)` is an assignment, so a curl
    that cannot resolve the host ends the run with CURL's status. The "purging N
    URL(s)" line has already printed, so the caller sees a started purge, curl's
    own message, and a non-zero exit the header says cannot happen."""
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["--zone", ZONE, "https://a"], FAKE_CURL_RC="6"
    )
    assert old.returncode == 6
    assert old.stdout == "cf-purge-urls.sh: purging 1 URL(s) from CF zone zone-fixture\n"
    assert old.stderr == "curl: (6) Could not resolve host: api.cloudflare.com\n"
    assert len(old_calls) == 1
    _assert_agree(old, new, "curl-fails", old_calls, new_calls)


def test_an_unknown_flag_is_purged_as_a_url(tmp_path: pathlib.Path) -> None:
    """There is no unknown-flag refusal: the `*)` arm takes anything. Driven so a
    port cannot "improve" the parser into rejecting it."""
    old, new, old_calls, new_calls = run_both(tmp_path, ["--zone", ZONE, "--dry-run"])
    assert old.returncode == 0
    assert '{"files":["--dry-run"]}' in old_calls[0]
    _assert_agree(old, new, "unknown-flag", old_calls, new_calls)


def test_a_repeated_zone_flag_keeps_the_last_one(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["--zone", "first", "--zone", ZONE, "https://a"]
    )
    assert "zones/zone-fixture/purge_cache" in old_calls[0]
    assert "zones/first/" not in old_calls[0]
    _assert_agree(old, new, "repeated-zone", old_calls, new_calls)


def test_divergence_a_trailing_zone_flag_is_bashs_own_unbound_variable(
    tmp_path: pathlib.Path,
) -> None:
    """THE ONE DIVERGENCE, ASSERTED IN BOTH DIRECTIONS SO IT CANNOT BE "FIXED"
    BY ACCIDENT. `--zone` as the last token reads `"$2"` under `set -u`, and the
    twin dies with bash's own message naming the bash FILE and a bash LINE. The
    port cannot honestly print that; it prints its own sentence. Same stream,
    same exit status, no request from either."""
    old, new, old_calls, new_calls = run_both(tmp_path, ["--zone"])
    assert old.returncode == new.returncode == 1
    assert old.stderr.endswith("line 38: $2: unbound variable\n")
    assert new.stderr == "cf-purge-urls.sh: --zone requires a value\n"
    assert old.stderr != new.stderr
    assert old.stdout == new.stdout == ""
    assert old_calls == new_calls == []


def test_pure_helpers() -> None:
    assert port.BATCH_SIZE == 30
    assert port.SELF == "cf-purge-urls.sh"
    assert port.CF_API_BASE == "https://api.cloudflare.com/client/v4"

    assert port.parse_argv(["--zone", "Z", "a", "-x"]) == ("Z", ["a", "-x"])
    assert port.parse_argv([]) == ("", [])

    # `read` semantics, both halves.
    assert port.stdin_urls("a\n\nb\n") == ["a", "b"]
    assert port.stdin_urls("a\nb") == ["a"]
    assert port.stdin_urls("") == []
    assert port.stdin_urls("\n") == []

    assert port.auth_headers({"CLOUDFLARE_API_TOKEN": "T"}) == ["-H", "Authorization: Bearer T"]
    assert port.auth_headers({"CF_GLOBAL_API_KEY": "K", "CF_EMAIL": "E"}) == [
        "-H",
        "X-Auth-Email: E",
        "-H",
        "X-Auth-Key: K",
    ]
    assert port.auth_headers({"CF_GLOBAL_API_KEY": "K"}) is None
    assert port.auth_headers({}) is None

    assert port.batches(["a", "b"], 1) == [["a"], ["b"]]
    assert len(port.batches(["u"] * 61)) == 3
    assert port.batches([]) == []

    assert port.payload_for(["https://a", "https://b"]) == '{"files":["https://a","https://b"]}'
    assert port.curl_argv("Z", ["-H", "h"], "{}") == [
        "curl",
        "-sS",
        "-X",
        "POST",
        "https://api.cloudflare.com/client/v4/zones/Z/purge_cache",
        "-H",
        "h",
        "-H",
        "Content-Type: application/json",
        "--data",
        "{}",
    ]


def test_planted_defect_is_caught(tmp_path: pathlib.Path) -> None:
    """ANTI-VACUITY, planted on the batch size -- the one number whose loss is
    invisible in the exit code and in every printed line, and which in production
    means Cloudflare rejecting an oversized purge while the script reports
    success. Driven red, then the source is confirmed byte-identical and green.
    """
    original = PORT.read_text(encoding="utf-8")
    mutated = original.replace("BATCH_SIZE = 30", "BATCH_SIZE = 60", 1)
    assert mutated != original, "the line this plant targets is no longer present verbatim"
    mutant = tmp_path / "mutant.py"
    mutant.write_text(mutated, encoding="utf-8")

    urls = ["https://x/%d" % n for n in range(1, 32)]
    args = ["--zone", ZONE, *urls]
    old, old_calls = _run(TWIN, tmp_path, args)
    bad, bad_calls = _run(mutant, tmp_path, args)
    assert len(old_calls) == 2, "the TWIN stopped batching; the plant is untested"
    assert len(bad_calls) == 1, "the mutant still batched at 30"
    assert bad.returncode == old.returncode, (
        "the plant is invisible in the exit code, which is why the call log is compared"
    )
    assert bad.stdout == old.stdout, (
        "the plant is invisible on stdout too: both say 'purged 31 URL(s) successfully'"
    )

    good, good_calls = _run(PORT, tmp_path, args)
    assert good_calls == old_calls, "restored port no longer agrees with the twin"
    assert good.stdout == old.stdout
    assert PORT.read_text(encoding="utf-8") == original, (
        "port source must be restored byte-identical"
    )

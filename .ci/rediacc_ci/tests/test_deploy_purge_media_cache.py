"""Differential: `rediacc_ci.deploy.purge_media_cache` against its twin
`.ci/scripts/deploy/purge-media-cache.sh`.

A RECORDING FAKE `curl` ON A SCRATCH PATH. Nothing here reaches Cloudflare: the
fake logs its exact argv and answers from the environment, and the only real
credential name in the file is an environment KEY, never a value.
`.ci/shadow/w7p5a-status.json` records this path as blocked only for the "one
real run" clause and says in as many words that the mocked parity ledger is a
separate, achievable piece of work. This is that piece.

THE REQUEST IS THE WHOLE CONTRACT, so the log is compared as well as the two
streams. The zone id and the hostname are hard-coded in the twin and take no
argument, which means the ONLY thing this program does is send one exact POST;
a port that sent it to a different zone would print identical output and exit 0.
`test_planted_defect_is_caught` plants exactly that.

TWO jq CALL SITES WITH DIFFERENT `set -e` EXPOSURE are driven, because that is
the pair a `json.loads` port gets wrong: a non-JSON body prints jq's parse error
TWICE and still exits 1 through the script's own branch, while a curl that cannot
reach the host ends the run with curl's status and NO diagnostic at all.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import typing

from rediacc_ci import paths
from rediacc_ci.deploy import purge_media_cache as port

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "deploy" / "purge-media-cache.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "deploy" / "purge_media_cache.py"
BASH = shutil.which("bash") or "/bin/bash"

# Named BEARER rather than TOKEN because ruff's S105 keys on the NAME: a
# constant called TOKEN is "a hardcoded password" to the linter even when its
# value is visibly a fixture.
BEARER = "tok-fixture"

FAKE_CURL = """#!/usr/bin/python3
import json
import os
import sys

argv = sys.argv[1:]
with open(os.environ["FAKE_CALL_LOG"], "a") as fh:
    fh.write("curl\\t" + "\\t".join(argv) + "\\n")

if os.environ.get("FAKE_CURL_RC"):
    sys.exit(int(os.environ["FAKE_CURL_RC"]))

if os.environ.get("FAKE_CURL_BODY") is not None:
    sys.stdout.write(os.environ["FAKE_CURL_BODY"])
    sys.exit(0)

sys.stdout.write(json.dumps({"success": True, "errors": [], "result": {"id": "purge"}}) + "\\n")
"""

# common.sh needs `dirname` at source time and `uname`/`tr` in its detection
# helpers; `jq` is a REQUIRED command of the subject and is therefore the real
# binary on both sides -- the port shells out to the same one.
PATH_MINIMUM = ("dirname", "uname", "tr", "jq")


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
    if drop:
        assert shutil.which(drop, path=str(stub)) is None, f"{drop} leaked into the stub PATH"
    return str(stub)


def _run(
    subject: pathlib.Path,
    tmp_path: pathlib.Path,
    args: list[str],
    *,
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
        input="",
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


def purge_call(headers: list[str] | None = None) -> str:
    auth = ["-H", "Authorization: Bearer %s" % BEARER] if headers is None else headers
    return "curl\t" + "\t".join(port.curl_argv(auth)[1:])


def test_the_request_shape_is_asserted_in_full(tmp_path: pathlib.Path) -> None:
    """THE ONE REQUEST, PINNED AGAINST LITERAL BYTES rather than against the
    port's own helpers, so a change in both would still be caught. Zone id,
    hostname, both headers and the exact body, SPACE AFTER THE COLON included."""
    old, new, old_calls, new_calls = run_both(tmp_path, [])
    assert old.returncode == 0
    assert old_calls == [
        (
            "curl\t-s\t-X\tPOST\t"
            "https://api.cloudflare.com/client/v4/zones/"
            "9e802649c143c9cefd811d8fd671d31c/purge_cache\t"
            "-H\tAuthorization: Bearer tok-fixture\t"
            "-H\tContent-Type: application/json\t"
            '--data\t{"hosts": ["media.rediacc.com"]}'
        )
    ]
    assert old_calls == [purge_call()]
    assert old.stdout == "", "this script must never put anything on stdout"
    assert old.stderr == (
        "→ Purging Cloudflare cache for media.rediacc.com...\n"
        "✓ Purge complete. Cache repopulates on next request "
        "(cf-cache-status: MISS then HIT).\n"
    )
    _assert_agree(old, new, "request-shape", old_calls, new_calls)


def test_no_credentials_is_a_refusal_not_a_skip(tmp_path: pathlib.Path) -> None:
    """CONTRAST WITH THE SIBLING `cf-purge-urls.sh`, which treats a missing
    credential as a best-effort skip and exits 0. This one exits 1, and the
    difference is deliberate on both sides."""
    old, new, old_calls, new_calls = run_both(tmp_path, [], drop_env=("CLOUDFLARE_API_TOKEN",))
    assert old.returncode == 1
    assert old.stderr == "✗ Set CLOUDFLARE_API_TOKEN, or CF_GLOBAL_API_KEY + CF_EMAIL\n"
    assert old_calls == []
    _assert_agree(old, new, "no-creds", old_calls, new_calls)


def test_half_a_global_key_is_not_a_credential(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(
        tmp_path, [], drop_env=("CLOUDFLARE_API_TOKEN",), CF_EMAIL="ci@example.invalid"
    )
    assert old.returncode == 1
    assert old_calls == []
    _assert_agree(old, new, "half-global-key", old_calls, new_calls)


def test_the_global_key_pair_sends_key_before_email(tmp_path: pathlib.Path) -> None:
    """THE HEADER ORDER IS THE OPPOSITE OF THE SIBLING SCRIPT'S. Neither order
    matters to Cloudflare and both matter to a recorded argv, which is why each
    port carries its own twin's order instead of sharing a helper."""
    old, new, old_calls, new_calls = run_both(
        tmp_path,
        [],
        drop_env=("CLOUDFLARE_API_TOKEN",),
        CF_GLOBAL_API_KEY="gk-fixture",
        CF_EMAIL="ci@example.invalid",
    )
    assert old.returncode == 0
    assert "X-Auth-Key: gk-fixture\t-H\tX-Auth-Email: ci@example.invalid" in old_calls[0]
    assert old_calls == [
        purge_call(["-H", "X-Auth-Key: gk-fixture", "-H", "X-Auth-Email: ci@example.invalid"])
    ]
    _assert_agree(old, new, "global-key", old_calls, new_calls)


def test_a_token_wins_over_a_global_key(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(
        tmp_path, [], CF_GLOBAL_API_KEY="gk-fixture", CF_EMAIL="ci@example.invalid"
    )
    assert "Authorization: Bearer tok-fixture" in old_calls[0]
    assert "X-Auth-Key" not in old_calls[0]
    _assert_agree(old, new, "token-wins", old_calls, new_calls)


def test_missing_curl_is_refused_before_missing_jq(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, [], drop="curl")
    assert old.returncode == 1
    assert old.stderr == "✗ Required command 'curl' is not available\n"
    _assert_agree(old, new, "missing-curl", old_calls, new_calls)


def test_missing_jq_is_refused(tmp_path: pathlib.Path) -> None:
    """The port shells out to jq for the same reason the twin does, so `jq` is a
    real prerequisite of BOTH and this refusal has to agree."""
    old, new, old_calls, new_calls = run_both(tmp_path, [], drop="jq")
    assert old.returncode == 1
    assert old.stderr == "✗ Required command 'jq' is not available\n"
    assert old_calls == []
    _assert_agree(old, new, "missing-jq", old_calls, new_calls)


def test_an_unsuccessful_body_prints_the_errors_array(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(
        tmp_path,
        [],
        FAKE_CURL_BODY='{"success":false,"errors":[{"code":10000,"message":"Authentication error"}]}\n',
    )
    assert old.returncode == 1
    assert old.stderr == (
        "→ Purging Cloudflare cache for media.rediacc.com...\n"
        '✗ Purge failed: [{"code":10000,"message":"Authentication error"}]\n'
    )
    _assert_agree(old, new, "unsuccessful-body", old_calls, new_calls)


def test_an_empty_object_is_the_string_null_not_false(tmp_path: pathlib.Path) -> None:
    """`.success` HAS NO `// false` DEFAULT here, unlike the housekeeping
    sibling, so a body of `{}` yields the STRING `null`. Both are `!= "true"` so
    the branch is the same; the point is that a port must not tidy the filter,
    because `.errors` then reports `null` as well."""
    old, new, old_calls, new_calls = run_both(tmp_path, [], FAKE_CURL_BODY="{}\n")
    assert old.returncode == 1
    assert old.stderr.endswith("✗ Purge failed: null\n")
    _assert_agree(old, new, "empty-object", old_calls, new_calls)


def test_an_empty_body_fails_with_an_empty_tail_and_no_jq_error(
    tmp_path: pathlib.Path,
) -> None:
    """jq over EMPTY input emits nothing and exits 0, so this is the failure
    branch with a message that just stops. Not a parse error, and not a pass."""
    old, new, old_calls, new_calls = run_both(tmp_path, [], FAKE_CURL_BODY="")
    assert old.returncode == 1
    assert old.stderr.endswith("✗ Purge failed: \n")
    assert "jq:" not in old.stderr
    _assert_agree(old, new, "empty-body", old_calls, new_calls)


def test_a_non_json_body_prints_jqs_parse_error_twice(tmp_path: pathlib.Path) -> None:
    """THE CASE A `json.loads` PORT WOULD GET WRONG, and the reason both jq call
    sites are shelled out. Neither substitution is in a position `set -e` can
    act on, so jq dies TWICE -- once for `.success`, once for `.errors` inside
    the `log_error` argument -- and the script still reaches its own exit 1."""
    old, new, old_calls, new_calls = run_both(
        tmp_path, [], FAKE_CURL_BODY="<html>504 Gateway Timeout</html>\n"
    )
    assert old.returncode == 1, f"the twin's status changed: {old.returncode}"
    assert old.stderr.count("jq: parse error") == 2
    assert old.stderr.endswith("✗ Purge failed: \n")
    _assert_agree(old, new, "non-json", old_calls, new_calls)


def test_defect_a_transport_failure_is_a_silent_non_zero(tmp_path: pathlib.Path) -> None:
    """THE DEFECT, PINNED. `curl -s` (no `-S`) says nothing on a network error and
    the assignment feeds `set -e`, so the caller gets the step line, NO
    diagnostic whatsoever, and exit 6. A workflow step fails with no reason in
    the log.

    Reproduced because agreement with the live twin is the deliverable;
    repaired, this test goes red and names the port that must follow.
    """
    old, new, old_calls, new_calls = run_both(tmp_path, [], FAKE_CURL_RC="6")
    assert old.returncode == 6
    assert old.stderr == "→ Purging Cloudflare cache for media.rediacc.com...\n"
    assert old.stdout == ""
    assert len(old_calls) == 1
    assert port.A_TRANSPORT_FAILURE_IS_SILENT
    _assert_agree(old, new, "curl-fails", old_calls, new_calls)


def test_extra_arguments_are_ignored_by_both(tmp_path: pathlib.Path) -> None:
    """The twin parses nothing, so `--dry-run` is NOT a dry run: the purge
    happens. Driven so a port cannot invent a flag the callers do not have."""
    old, new, old_calls, new_calls = run_both(tmp_path, ["--dry-run"])
    assert old.returncode == 0
    assert len(old_calls) == 1, "an ignored flag became a dry run"
    _assert_agree(old, new, "extra-args", old_calls, new_calls)


def test_divergence_common_sh_interprets_backslash_escapes_in_the_cf_error(
    tmp_path: pathlib.Path,
) -> None:
    """A DELIBERATE DIVERGENCE, ASSERTED IN BOTH DIRECTIONS SO IT CANNOT BE
    "FIXED" BY ACCIDENT. `Purge failed: <errors>` is the one message that
    interpolates remote text, and common.sh logs through `echo -e`, which
    interprets backslash escapes IN THE MESSAGE. `rediacc_ci.log` formats the
    message as data (see its module docstring), so a Cloudflare error carrying a
    literal backslash-n renders as a newline through the twin and as two
    characters here.

    THE FIXTURE HAS TO CARRY A REAL NEWLINE, not a literal backslash-n: jq
    re-escapes what it prints, so a message holding two characters comes out of
    `jq -c` as `\\\\n` and `echo -e` renders THAT as a literal backslash-n on
    both sides. Only a genuine newline in the JSON string reaches `echo -e` as
    the single escape that distinguishes the two implementations. Driven the
    wrong way round first, which is how the distinction was found.
    """
    body = '{"success":false,"errors":[{"message":"boom\\nline two"}]}\n'
    old, new, _oc, _nc = run_both(tmp_path, [], FAKE_CURL_BODY=body)
    assert old.returncode == new.returncode == 1
    assert "boom\nline two" in old.stderr, "the twin no longer interprets escapes"
    assert "boom\\nline two" in new.stderr, "the port started interpreting escapes"
    assert old.stderr != new.stderr


def test_pure_helpers() -> None:
    assert port.ZONE_ID == "9e802649c143c9cefd811d8fd671d31c"
    assert port.PURGE_HOSTNAME == "media.rediacc.com"
    assert port.PURGE_BODY == '{"hosts": ["media.rediacc.com"]}'

    assert port.auth_headers({"CLOUDFLARE_API_TOKEN": "T"}) == ["-H", "Authorization: Bearer T"]
    assert port.auth_headers({"CF_GLOBAL_API_KEY": "K", "CF_EMAIL": "E"}) == [
        "-H",
        "X-Auth-Key: K",
        "-H",
        "X-Auth-Email: E",
    ]
    assert port.auth_headers({"CF_EMAIL": "E"}) is None
    assert port.auth_headers({}) is None

    assert port.curl_argv(["-H", "h"]) == [
        "curl",
        "-s",
        "-X",
        "POST",
        ("https://api.cloudflare.com/client/v4/zones/9e802649c143c9cefd811d8fd671d31c/purge_cache"),
        "-H",
        "h",
        "-H",
        "Content-Type: application/json",
        "--data",
        '{"hosts": ["media.rediacc.com"]}',
    ]


def test_planted_defect_is_caught(tmp_path: pathlib.Path) -> None:
    """ANTI-VACUITY, planted on the zone id -- the one value that decides WHICH
    cache is purged, and whose corruption leaves both streams and the exit code
    completely unchanged while media.rediacc.com keeps serving the stale
    response the script exists to evict. Driven red, then the source is confirmed
    byte-identical and green.
    """
    original = PORT.read_text(encoding="utf-8")
    mutated = original.replace(
        'ZONE_ID = "9e802649c143c9cefd811d8fd671d31c"',
        'ZONE_ID = "0000000000000000000000000000000f"',
        1,
    )
    assert mutated != original, "the line this plant targets is no longer present verbatim"
    mutant = tmp_path / "mutant.py"
    mutant.write_text(mutated, encoding="utf-8")

    old, old_calls = _run(TWIN, tmp_path, [])
    bad, bad_calls = _run(mutant, tmp_path, [])
    assert bad.returncode == old.returncode == 0, "the plant is invisible in the exit code"
    assert bad.stderr == old.stderr, "the plant is invisible on stderr"
    assert bad.stdout == old.stdout == "", "the plant is invisible on stdout"
    assert len(bad_calls) == len(old_calls) == 1, "the plant even keeps the call COUNT"
    assert bad_calls != old_calls, "the mutant still purged the real zone"
    assert "zones/0000000000000000000000000000000f/" in bad_calls[0]

    good, good_calls = _run(PORT, tmp_path, [])
    assert good_calls == old_calls, "restored port no longer agrees with the twin"
    assert good.stderr == old.stderr
    assert PORT.read_text(encoding="utf-8") == original, (
        "port source must be restored byte-identical"
    )

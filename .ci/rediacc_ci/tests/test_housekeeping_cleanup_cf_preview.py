"""Differential: `rediacc_ci.housekeeping.cleanup_cf_preview` against its twin
`.ci/scripts/housekeeping/cleanup-cf-preview.sh`.

A RECORDING FAKE `curl` ON A SCRATCH PATH, answering from the REQUEST SHAPE.
Nothing here reaches Cloudflare. The fake routes on the URL -- a `/deployments/`
segment is a delete, anything else is a listing -- and every case pins a fixture
account id and token, so even a bypassed fake would not name a real account.

THE REQUEST LOG IS COMPARED, NOT JUST THE STREAMS, and for this script it is the
main evidence. The observable effect is a set of DELETE calls against a live CDN;
two implementations can print the same tally while deleting different
deployments, or while paginating differently, or while sending the token in the
wrong header. `test_the_request_shape_is_asserted_in_full` pins the exact argv of
both endpoints -- method, URL, and both headers -- against the port's own
`curl_argv`, so the shape is checked against the code as well as against the twin.

THE THREE jq FAILURE MODES ARE DRIVEN, because the port shells out to jq rather
than parsing JSON in Python precisely so that they agree: a non-JSON body and a
`result`-less body both kill the run with jq's own message and exit 5, while an
EMPTY body does not and takes the ordinary warning branch. A port using
`json.loads` would pass every happy-path test here and differ on all three.

THE VACUITY DEFECT IS PINNED. `test_defect_a_failed_listing_reads_as_nothing_to_do`
drives a curl that cannot reach the host and asserts the twin exits 0 saying
"No preview deployments to clean up". Reproduced because agreement with the live
twin is the deliverable; repaired, the test goes red and names the port that
must follow.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import typing

from rediacc_ci import paths
from rediacc_ci.housekeeping import cleanup_cf_preview as port

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "housekeeping" / "cleanup-cf-preview.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "housekeeping" / "cleanup_cf_preview.py"
BASH = shutil.which("bash") or "/bin/bash"

ACCOUNT = "acct-fixture"
# Named BEARER rather than TOKEN because ruff's S105 keys on the NAME: a
# constant called TOKEN is "a hardcoded password" to the linter even when its
# value is visibly a fixture.
BEARER = "tok-fixture"

FAKE_CURL = """#!/usr/bin/python3
import json
import os
import re
import sys

argv = sys.argv[1:]
with open(os.environ["FAKE_CALL_LOG"], "a") as fh:
    fh.write("curl\\t" + "\\t".join(argv) + "\\n")

urls = [a for a in argv if a.startswith("https://")]
url = urls[0] if urls else ""

if os.environ.get("FAKE_CURL_RC"):
    sys.stderr.write("curl: (6) Could not resolve host\\n")
    sys.exit(int(os.environ["FAKE_CURL_RC"]))

if os.environ.get("FAKE_CURL_BODY") is not None:
    sys.stdout.write(os.environ["FAKE_CURL_BODY"])
    sys.exit(0)

if "/deployments/" in url:
    if os.environ.get("FAKE_DELETE_OK", "true") == "true":
        sys.stdout.write(json.dumps({"success": True, "result": None}) + "\\n")
    else:
        sys.stdout.write(
            json.dumps(
                {
                    "success": False,
                    "errors": [
                        {"message": os.environ.get("FAKE_DELETE_ERR", "latest deployment")}
                    ],
                }
            )
            + "\\n"
        )
    sys.exit(0)

if os.environ.get("FAKE_LIST_UNSUCCESSFUL") == "1":
    sys.stdout.write(json.dumps({"success": False, "errors": [{"message": "auth"}]}) + "\\n")
    sys.exit(0)

page = int(re.search(r"[?&]page=(\\d+)", url).group(1))
per_page = int(os.environ.get("FAKE_PER_PAGE", "2"))
last_page = int(os.environ.get("FAKE_LAST_PAGE", "1"))
if page > last_page:
    sys.stdout.write(json.dumps({"success": True, "result": []}) + "\\n")
    sys.exit(0)
result = []
for i in range(per_page):
    branch = "feature-x" if i % 2 == 0 else "other-branch"
    result.append(
        {
            "id": "dep-%d-%d" % (page, i),
            "created_on": "2026-01-%02d" % (i + 1),
            "deployment_trigger": {"metadata": {"branch": branch}},
        }
    )
sys.stdout.write(json.dumps({"success": True, "result": result}) + "\\n")
sys.exit(0)
"""

# common.sh needs `dirname` and `uname` at source time and `tr` in parse_args;
# the twin itself needs `jq`, which is a REQUIRED command of the subject and is
# therefore the real binary on both sides -- the port shells out to the same one.
PATH_MINIMUM = ("dirname", "uname", "tr", "jq")


def _bin(tmp_path: pathlib.Path, name: str, *, tools: bool = True, drop: str = "") -> str:
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
    curl = stub / "curl"
    if tools and drop != "curl":
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
    tools: bool = True,
    drop: str = "",
    drop_env: tuple[str, ...] = (),
    **extra: str,
):
    side = "old" if subject.suffix == ".sh" else "new"
    call_log = tmp_path / f"{side}-calls.log"
    call_log.write_text("", encoding="utf-8")
    env = {
        "PATH": _bin(tmp_path, f"{side}-bin", tools=tools, drop=drop),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LC_ALL": "C",
        "LANG": "C",
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "FAKE_CALL_LOG": str(call_log),
        "CLOUDFLARE_API_TOKEN": BEARER,
        "CLOUDFLARE_ACCOUNT_ID": ACCOUNT,
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


def list_call(page: int) -> str:
    """The recorded line for one listing request. `[1:]` drops the argv[0]
    `curl`, which the fake writes itself as the log's own first field."""
    return "curl\t" + "\t".join(
        port.curl_argv("GET", port.deployments_path(ACCOUNT, page), BEARER)[1:]
    )


def delete_call(dep_id: str) -> str:
    return "curl\t" + "\t".join(
        port.curl_argv("DELETE", port.delete_path(ACCOUNT, dep_id), BEARER)[1:]
    )


def test_the_request_shape_is_asserted_in_full(tmp_path: pathlib.Path) -> None:
    """THE REQUESTS, PINNED AGAINST THE LITERAL BYTES rather than against the
    port's own helpers, so that a change in both would still be caught. Method,
    URL, and BOTH headers, for both endpoints."""
    old, new, old_calls, new_calls = run_both(tmp_path, ["--branch", "feature-x"])
    assert old.returncode == 0
    assert old_calls == [
        (
            "curl\t-s\t-X\tGET\t"
            "https://api.cloudflare.com/client/v4/accounts/acct-fixture/pages/projects/"
            "rediacc/deployments?env=preview&per_page=25&page=1\t"
            "-H\tAuthorization: Bearer tok-fixture\t-H\tContent-Type: application/json"
        ),
        (
            "curl\t-s\t-X\tDELETE\t"
            "https://api.cloudflare.com/client/v4/accounts/acct-fixture/pages/projects/"
            "rediacc/deployments/dep-1-0?force=true\t"
            "-H\tAuthorization: Bearer tok-fixture\t-H\tContent-Type: application/json"
        ),
    ]
    # And the port's own builders agree with those literals.
    assert old_calls == [list_call(1), delete_call("dep-1-0")]
    _assert_agree(old, new, "request-shape", old_calls, new_calls)


def test_only_the_named_branch_is_deleted(tmp_path: pathlib.Path) -> None:
    """THE ONE REFUSAL. The listing carries deployments from OTHER branches and
    they must never be touched; the filter is
    `.deployment_trigger.metadata.branch == $branch`."""
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["--branch", "feature-x"], FAKE_PER_PAGE="6"
    )
    assert old.returncode == 0
    assert "Found 3 preview deployments for branch 'feature-x'" in old.stderr
    deleted = [c for c in old_calls if "DELETE" in c]
    assert len(deleted) == 3
    assert all("dep-1-0" in c or "dep-1-2" in c or "dep-1-4" in c for c in deleted), deleted
    _assert_agree(old, new, "branch-filter", old_calls, new_calls)


def test_a_branch_with_no_deployments_is_a_clean_no_op(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, ["--branch", "nothing-here"])
    assert old.returncode == 0
    assert old.stderr == (
        "→ Cleaning up CF Pages preview deployments for branch: nothing-here\n"
        "→ Found 0 preview deployments for branch 'nothing-here'\n"
        "✓ No preview deployments to clean up\n"
    )
    assert old.stdout == "", "this script must never put anything on stdout"
    assert not any("DELETE" in c for c in old_calls)
    _assert_agree(old, new, "no-match", old_calls, new_calls)


def test_dry_run_makes_no_delete_request_at_all(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, ["--branch", "feature-x", "--dry-run"])
    assert old.returncode == 0
    assert old.stderr == (
        "→ Cleaning up CF Pages preview deployments for branch: feature-x\n"
        "⚠ DRY-RUN mode: no deletions will be performed\n"
        "→ Found 1 preview deployments for branch 'feature-x'\n"
        "⚠ [DRY-RUN] Would delete: dep-1-0 (created: 2026-01-01)\n"
        "✓ Would delete 1 of 1 deployments for branch 'feature-x'\n"
    )
    assert not any("DELETE" in c for c in old_calls), "a dry run issued a DELETE"
    _assert_agree(old, new, "dry-run", old_calls, new_calls)


def test_dry_run_false_is_not_a_dry_run(tmp_path: pathlib.Path) -> None:
    """parse_args quirk 2: `--dry-run false` stores the STRING `false`, and the
    comparison is against the literal `true`. So this really deletes."""
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["--branch", "feature-x", "--dry-run", "false"]
    )
    assert old.returncode == 0
    assert "DRY-RUN" not in old.stderr
    assert any("DELETE" in c for c in old_calls)
    _assert_agree(old, new, "dry-run-false", old_calls, new_calls)


def test_pagination_follows_until_a_short_page(tmp_path: pathlib.Path) -> None:
    """`per_page=25` and `[[ "$all_results" -lt 25 ]]`. A full page means there
    may be more; a short one ends the sweep. Three listings here: two full, one
    short."""
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["--branch", "feature-x"], FAKE_PER_PAGE="25", FAKE_LAST_PAGE="2"
    )
    assert old.returncode == 0
    lists = [c for c in old_calls if "\tGET\t" in c]
    assert lists == [list_call(1), list_call(2), list_call(3)]
    assert "Found 26 preview deployments" in old.stderr
    _assert_agree(old, new, "pagination", old_calls, new_calls)


def test_a_refused_delete_is_reported_and_the_sweep_continues(
    tmp_path: pathlib.Path,
) -> None:
    """Cloudflare refuses to delete the LATEST deployment of a branch. That is
    expected, not fatal: refusing over it would leave every older preview
    behind."""
    old, new, old_calls, new_calls = run_both(
        tmp_path,
        ["--branch", "feature-x"],
        FAKE_PER_PAGE="6",
        FAKE_DELETE_OK="false",
        FAKE_DELETE_ERR="latest deployment cannot be deleted",
    )
    assert old.returncode == 0
    assert old.stderr.count("⚠ Could not delete ") == 3
    assert "latest deployment cannot be deleted" in old.stderr
    assert "✓ Deleted 0 of 3 deployments for branch 'feature-x'\n" in old.stderr
    assert len([c for c in old_calls if "DELETE" in c]) == 3, "the sweep stopped early"
    _assert_agree(old, new, "delete-refused", old_calls, new_calls)


def test_a_delete_error_with_no_errors_array_says_unknown_error(
    tmp_path: pathlib.Path,
) -> None:
    """`.errors[0].message // "unknown error"`. Indexing a missing key yields
    null in jq rather than raising, so this is a message and not a crash."""
    old, new, old_calls, new_calls = run_both(
        tmp_path,
        ["--branch", "feature-x"],
        FAKE_CURL_BODY='{"success":true,"result":[{"id":"dep-a","created_on":"x",'
        '"deployment_trigger":{"metadata":{"branch":"feature-x"}}}]}\n',
        FAKE_DELETE_OK="false",
    )
    # The body override answers BOTH endpoints, so the delete "succeeds" here;
    # the point of the case is the shared-body path agreeing at all.
    assert old.returncode == 0
    _assert_agree(old, new, "unknown-error", old_calls, new_calls)


def test_a_successful_delete_is_silent_unless_debug_is_true(
    tmp_path: pathlib.Path,
) -> None:
    """`log_debug` is gated on `DEBUG=true` EXACTLY -- not on any truthy value.
    Both directions are driven, because a port that logged unconditionally would
    look fine to a reader and change the workflow log."""
    quiet_old, quiet_new, qoc, qnc = run_both(tmp_path, ["--branch", "feature-x"])
    assert "Deleted: dep-1-0" not in quiet_old.stderr
    _assert_agree(quiet_old, quiet_new, "debug-off", qoc, qnc)

    loud_old, loud_new, loc, lnc = run_both(tmp_path, ["--branch", "feature-x"], DEBUG="true")
    assert "[DEBUG] Deleted: dep-1-0" in loud_old.stderr
    _assert_agree(loud_old, loud_new, "debug-on", loc, lnc)

    one_old, one_new, ooc, onc = run_both(tmp_path, ["--branch", "feature-x"], DEBUG="1")
    assert "Deleted: dep-1-0" not in one_old.stderr, "DEBUG=1 is not DEBUG=true"
    _assert_agree(one_old, one_new, "debug-1", ooc, onc)


def test_no_branch_is_refused_after_the_prerequisites(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, [])
    assert old.returncode == 1
    assert old.stderr == ("✗ Usage: cleanup-cf-preview.sh --branch <branch_name> [--dry-run]\n")
    assert old_calls == []
    _assert_agree(old, new, "no-branch", old_calls, new_calls)


def test_a_missing_token_is_refused_before_the_missing_branch(
    tmp_path: pathlib.Path,
) -> None:
    """ORDER IS OBSERVABLE. `require_var` runs BEFORE the branch check, so a run
    with neither says which variable is missing rather than printing usage."""
    old, new, old_calls, new_calls = run_both(tmp_path, [], drop_env=("CLOUDFLARE_API_TOKEN",))
    assert old.returncode == 1
    assert old.stderr == ("✗ Required environment variable 'CLOUDFLARE_API_TOKEN' is not set\n")
    _assert_agree(old, new, "missing-token", old_calls, new_calls)


def test_a_missing_account_id_is_refused(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["--branch", "b"], drop_env=("CLOUDFLARE_ACCOUNT_ID",)
    )
    assert old.returncode == 1
    assert "CLOUDFLARE_ACCOUNT_ID" in old.stderr
    _assert_agree(old, new, "missing-account", old_calls, new_calls)


def test_missing_curl_is_refused_before_missing_jq(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, ["--branch", "b"], drop="curl")
    assert old.returncode == 1
    assert old.stderr == "✗ Required command 'curl' is not available\n"
    _assert_agree(old, new, "missing-curl", old_calls, new_calls)


def test_missing_jq_is_refused(tmp_path: pathlib.Path) -> None:
    """The port shells out to jq for the same reason the twin does, so `jq` is a
    real prerequisite of BOTH and this refusal has to agree."""
    old, new, old_calls, new_calls = run_both(tmp_path, ["--branch", "b"], drop="jq")
    assert old.returncode == 1
    assert old.stderr == "✗ Required command 'jq' is not available\n"
    _assert_agree(old, new, "missing-jq", old_calls, new_calls)


def test_defect_a_failed_listing_reads_as_nothing_to_do(tmp_path: pathlib.Path) -> None:
    """THE VACUITY DEFECT, PINNED. curl cannot reach the host, the `|| echo
    '{"result":[]}'` fallback fires, `.success // false` is false, and the run
    ends GREEN with "No preview deployments to clean up". The one warning line
    sits in the middle of a successful run, so a branch whose previews were never
    enumerated is indistinguishable from a branch that had none.

    Reproduced because agreement with the live twin is the deliverable;
    repaired, this test goes red and names the port that must follow.
    """
    old, new, old_calls, new_calls = run_both(tmp_path, ["--branch", "feature-x"], FAKE_CURL_RC="6")
    assert old.returncode == 0, "the twin now fails on an unreachable API"
    assert old.stderr == (
        "→ Cleaning up CF Pages preview deployments for branch: feature-x\n"
        "⚠ CF API request failed on page 1\n"
        "→ Found 0 preview deployments for branch 'feature-x'\n"
        "✓ No preview deployments to clean up\n"
    )
    assert port.API_FAILURE_READS_AS_NOTHING_TO_DO
    _assert_agree(old, new, "curl-fails", old_calls, new_calls)


def test_an_unsuccessful_listing_body_is_the_same_green(tmp_path: pathlib.Path) -> None:
    """A 200 whose body says `success: false` -- an auth failure, say -- takes
    the identical path. Driven separately from the transport failure because the
    two reach the branch by different routes."""
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["--branch", "feature-x"], FAKE_LIST_UNSUCCESSFUL="1"
    )
    assert old.returncode == 0
    assert "CF API request failed on page 1" in old.stderr
    assert "No preview deployments to clean up" in old.stderr
    _assert_agree(old, new, "unsuccessful-body", old_calls, new_calls)


def test_a_non_json_body_kills_the_run_with_jqs_own_message(
    tmp_path: pathlib.Path,
) -> None:
    """THE CASE A `json.loads` PORT WOULD GET WRONG. An HTML error page reaches
    an unguarded `jq`, whose parse error goes to stderr and whose exit status
    passes through `set -e`. Both the message and the status must agree, which is
    why the port runs jq rather than parsing in Python."""
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["--branch", "feature-x"], FAKE_CURL_BODY="<html>504 Gateway Timeout</html>\n"
    )
    assert old.returncode == 5, f"jq's status changed: {old.returncode}"
    assert "jq: parse error" in old.stderr
    assert "Found" not in old.stderr, "the run continued past the parse error"
    _assert_agree(old, new, "non-json", old_calls, new_calls)


def test_a_result_less_body_dies_on_the_filter_not_on_the_length(
    tmp_path: pathlib.Path,
) -> None:
    """`[.result[] | ...]` is evaluated BEFORE `.result | length`, so a body with
    `success: true` and no `result` key dies with "Cannot iterate over null"
    rather than reporting zero. Order matters and is asserted."""
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["--branch", "feature-x"], FAKE_CURL_BODY='{"success":true}\n'
    )
    assert old.returncode == 5
    assert "Cannot iterate over null" in old.stderr
    _assert_agree(old, new, "no-result-key", old_calls, new_calls)


def test_an_empty_body_does_not_die(tmp_path: pathlib.Path) -> None:
    """The third jq shape: EMPTY input makes `jq -r '.success // false'` emit
    nothing at all and exit 0, so `success` is the empty string and the ordinary
    warning branch runs. Not a parse error, and not a pass."""
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["--branch", "feature-x"], FAKE_CURL_BODY=""
    )
    assert old.returncode == 0
    assert "CF API request failed on page 1" in old.stderr
    assert "jq:" not in old.stderr
    _assert_agree(old, new, "empty-body", old_calls, new_calls)


def test_a_branch_name_with_a_space_is_carried_through_the_filter(
    tmp_path: pathlib.Path,
) -> None:
    """`--arg branch "$BRANCH"` passes the name as DATA to jq, so a branch name
    is never a jq program fragment. Driven with a space because parse_args
    consumes the next token whole."""
    body = (
        '{"success":true,"result":[{"id":"dep-space","created_on":"2026-02-02",'
        '"deployment_trigger":{"metadata":{"branch":"odd name"}}}]}\n'
    )
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["--branch", "odd name"], FAKE_CURL_BODY=body
    )
    assert old.returncode == 0
    assert "Found 1 preview deployments for branch 'odd name'" in old.stderr
    _assert_agree(old, new, "branch-with-space", old_calls, new_calls)


def test_divergence_common_sh_interprets_backslash_escapes_in_the_cf_error(
    tmp_path: pathlib.Path,
) -> None:
    """A DELIBERATE DIVERGENCE, ASSERTED IN BOTH DIRECTIONS SO IT CANNOT BE
    "FIXED" BY ACCIDENT. `Could not delete <id>: <error_msg>` is the one message
    that interpolates remote text, and common.sh logs through `echo -e`.
    `rediacc_ci.log` formats the message as data (see its module docstring)."""
    old, new, _oc, _nc = run_both(
        tmp_path,
        ["--branch", "feature-x"],
        FAKE_DELETE_OK="false",
        FAKE_DELETE_ERR="boom\\nline two",
    )
    assert old.returncode == new.returncode == 0
    assert "boom\nline two" in old.stderr, "the twin no longer interprets escapes"
    assert "boom\\nline two" in new.stderr, "the port started interpreting escapes"
    assert old.stderr != new.stderr


def test_pure_helpers() -> None:
    assert port.CF_PAGES_PROJECT == "rediacc"
    assert port.PAGE_SIZE == 25
    assert port.deployments_path("A", 3) == (
        "/accounts/A/pages/projects/rediacc/deployments?env=preview&per_page=25&page=3"
    )
    assert port.delete_path("A", "D") == (
        "/accounts/A/pages/projects/rediacc/deployments/D?force=true"
    )
    assert port.curl_argv("GET", "/x", "T") == [
        "curl",
        "-s",
        "-X",
        "GET",
        "https://api.cloudflare.com/client/v4/x",
        "-H",
        "Authorization: Bearer T",
        "-H",
        "Content-Type: application/json",
    ]
    # The two `|| echo` fallbacks are DIFFERENT shapes, and both must be false
    # under `.success // false`.
    assert port.LIST_FALLBACK == '{"result":[]}'
    assert port.DELETE_FALLBACK == '{"success":false}'


def test_planted_defect_is_caught(tmp_path: pathlib.Path) -> None:
    """ANTI-VACUITY, planted on the branch filter -- the one refusal in the
    script, and the one whose omission deletes other branches' live previews
    while printing a bigger, entirely plausible tally. Driven red, then the
    source is confirmed byte-identical and green.
    """
    original = PORT.read_text(encoding="utf-8")
    # The target is the SELECT CLAUSE ALONE, not the whole statement. The first
    # version of this plant matched two source lines including their indentation,
    # and `ruff format` re-wrapped them minutes later -- the guard below caught
    # it, which is the reason the guard is an assertion rather than a comment.
    # `select(true)` keeps the jq program valid and `$branch` still bound, so the
    # ONLY thing the mutant loses is the refusal.
    mutated = original.replace(
        "select(.deployment_trigger.metadata.branch == $branch) ",
        "select(true) ",
    )
    assert mutated != original, "the line this plant targets is no longer present verbatim"
    mutant = tmp_path / "mutant.py"
    mutant.write_text(mutated, encoding="utf-8")

    kw = {"FAKE_PER_PAGE": "6"}
    old, old_calls = _run(TWIN, tmp_path, ["--branch", "feature-x"], **kw)
    bad, bad_calls = _run(mutant, tmp_path, ["--branch", "feature-x"], **kw)
    assert "Found 3 preview deployments" in old.stderr, "the TWIN filtered nothing; plant untested"
    assert "Found 6 preview deployments" in bad.stderr, "the mutant still filtered by branch"
    other = [c for c in bad_calls if "dep-1-1" in c]
    assert other, "the mutant did not reach another branch's deployment"
    assert not any("dep-1-1" in c for c in old_calls), "the TWIN deleted another branch's preview"
    assert bad.returncode == old.returncode, (
        "the plant is invisible in the exit code, which is why the call log is compared"
    )

    good, good_calls = _run(PORT, tmp_path, ["--branch", "feature-x"], **kw)
    assert good_calls == old_calls, "restored port no longer agrees with the twin"
    assert good.stderr == old.stderr
    assert PORT.read_text(encoding="utf-8") == original, (
        "port source must be restored byte-identical"
    )

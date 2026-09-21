"""`rediacc_ci.housekeeping.cleanup_cf_preview`, driven against the bytes its bash twin printed.

WHILE BOTH COPIES EXISTED this file ran `.ci/scripts/housekeeping/cleanup-cf-preview.sh` and the port over the same fixture, one after the other, and compared exit code, stdout, stderr and the HTTP request log. The K=5 ledger `.ci/shadow/w7p6-cleanup-cf-preview.observations.jsonl` recorded that comparison over five distinct trees. The twin has now been deleted and every
case that executed it compares against `goldens/cleanup-cf-preview/`, which holds the twin's OWN recorded bytes, captured from the tracked script on its last day in the tree. Each golden's provenance header carries the blob sha, so `git cat-file -p <sha>` still yields the program that printed them.

A RECORDING FAKE `curl` ON A SCRATCH PATH, answering from the REQUEST SHAPE. Nothing here reaches Cloudflare. The fake routes on the URL -- a `/deployments/` segment is a delete, anything else is a listing -- and every case pins a fixture account id and token, so even a bypassed fake would not name a real account.

THE REQUEST LOG IS RECORDED, NOT JUST THE STREAMS, and for this script it is the main evidence. The observable effect is a set of DELETE calls against a live CDN; two implementations can print the same tally while deleting different deployments, or while paginating differently, or while sending the token in the wrong header. `test_the_request_shape_is_asserted_in_full` pins the
exact argv of both endpoints -- method, URL, and both headers -- against the port's own `curl_argv` as well as against the recorded literals, so the shape is checked against the code and against the twin.

THE THREE jq FAILURE MODES ARE DRIVEN, because the port shells out to jq rather than parsing JSON in Python precisely so that they agree: a non-JSON body and a `result`-less body both kill the run with jq's own message and exit 5, while an EMPTY body does not and takes the ordinary warning branch. A port using `json.loads` would pass every happy-path case here and differ on all
three.

THE VACUITY DEFECT IS PINNED. `test_defect_a_failed_listing_reads_as_nothing_to_do` reads the recording of a curl that could not reach the host and asserts the twin exited 0 saying "No preview deployments to clean up". Reproduced because agreement with the twin was the deliverable; repaired, the test goes red and names the port that must follow.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.housekeeping import cleanup_cf_preview as port
from rediacc_ci.tests import frozen

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
PORT = ROOT / ".ci" / "rediacc_ci" / "housekeeping" / "cleanup_cf_preview.py"
BASH = shutil.which("bash") or "/bin/bash"

SLUG = "cleanup-cf-preview"

ACCOUNT = "acct-fixture"
# Named BEARER rather than TOKEN because ruff's S105 keys on the NAME: a constant called TOKEN is "a hardcoded password" to the linter even when its value is visibly a fixture.
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

# The twin's `common.sh` needed `dirname` and `uname` at source time and `tr` in parse_args; `jq` is a REQUIRED command of the subject and is therefore the real binary on both sides -- the port shells out to the same one.
PATH_MINIMUM = ("dirname", "uname", "tr", "jq")

CALLS_MARKER = "--- calls ---\n"


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
    side: str = "new",
    tools: bool = True,
    drop: str = "",
    drop_env: tuple[str, ...] = (),
    **extra: str,
):
    tmp_path.mkdir(parents=True, exist_ok=True)
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


SPACE_BODY = (
    '{"success":true,"result":[{"id":"dep-space","created_on":"2026-02-02",'
    '"deployment_trigger":{"metadata":{"branch":"odd name"}}}]}\n'
)
UNKNOWN_ERROR_BODY = (
    '{"success":true,"result":[{"id":"dep-a","created_on":"x",'
    '"deployment_trigger":{"metadata":{"branch":"feature-x"}}}]}\n'
)

# Every recorded case: the argv the subject is given, and the fake's knobs.
CASE_KW: dict[str, tuple[list[str], dict[str, object]]] = {
    "the-request-shape": (["--branch", "feature-x"], {}),
    "only-the-named-branch": (["--branch", "feature-x"], {"FAKE_PER_PAGE": "6"}),
    "a-branch-with-no-deployments": (["--branch", "nothing-here"], {}),
    "a-dry-run": (["--branch", "feature-x", "--dry-run"], {}),
    "dry-run-false-is-not-a-dry-run": (["--branch", "feature-x", "--dry-run", "false"], {}),
    "pagination-to-a-short-page": (
        ["--branch", "feature-x"],
        {"FAKE_PER_PAGE": "25", "FAKE_LAST_PAGE": "2"},
    ),
    "a-refused-delete": (
        ["--branch", "feature-x"],
        {
            "FAKE_PER_PAGE": "6",
            "FAKE_DELETE_OK": "false",
            "FAKE_DELETE_ERR": "latest deployment cannot be deleted",
        },
    ),
    "a-delete-error-with-no-errors-array": (
        ["--branch", "feature-x"],
        {"FAKE_CURL_BODY": UNKNOWN_ERROR_BODY, "FAKE_DELETE_OK": "false"},
    ),
    "debug-is-exactly-true": (["--branch", "feature-x"], {"DEBUG": "true"}),
    "debug-is-one": (["--branch", "feature-x"], {"DEBUG": "1"}),
    "no-branch-at-all": ([], {}),
    "a-missing-token": ([], {"drop_env": ("CLOUDFLARE_API_TOKEN",)}),
    "a-missing-account-id": (["--branch", "b"], {"drop_env": ("CLOUDFLARE_ACCOUNT_ID",)}),
    "a-missing-curl": (["--branch", "b"], {"drop": "curl"}),
    "a-missing-jq": (["--branch", "b"], {"drop": "jq"}),
    "an-unreachable-api": (["--branch", "feature-x"], {"FAKE_CURL_RC": "6"}),
    "an-unsuccessful-listing-body": (["--branch", "feature-x"], {"FAKE_LIST_UNSUCCESSFUL": "1"}),
    "a-non-json-body": (
        ["--branch", "feature-x"],
        {"FAKE_CURL_BODY": "<html>504 Gateway Timeout</html>\n"},
    ),
    "a-result-less-body": (["--branch", "feature-x"], {"FAKE_CURL_BODY": '{"success":true}\n'}),
    "an-empty-body": (["--branch", "feature-x"], {"FAKE_CURL_BODY": ""}),
    "a-branch-name-with-a-space": (["--branch", "odd name"], {"FAKE_CURL_BODY": SPACE_BODY}),
    "a-cf-error-carrying-a-backslash-n": (
        ["--branch", "feature-x"],
        {"FAKE_DELETE_OK": "false", "FAKE_DELETE_ERR": "boom\\nline two"},
    ),
}

CASES = tuple(CASE_KW)

# The one case whose recorded stderr the port deliberately does NOT reproduce: `common.sh` logged through `echo -e`, and `rediacc_ci.log` formats the message as data.
DIVERGENT = "a-cf-error-carrying-a-backslash-n"


def render(proc, calls: list[str]) -> str:
    body = frozen.render(proc.returncode, proc.stdout, proc.stderr)
    return body + CALLS_MARKER + "".join("%s\n" % line for line in calls)


def recorded(name: str) -> tuple[int, str, str, list[str]]:
    """One golden, back into the four observables `_run` produces."""
    text = frozen.read(SLUG, name)
    exit_line, rest = text.split("\n", 1)
    streams, calls_text = rest.split(CALLS_MARKER, 1)
    stdout, stderr = streams.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)
    return (
        int(exit_line.removeprefix("exit: ")),
        stdout,
        stderr,
        [line for line in calls_text.splitlines() if line],
    )


def drive(tmp_path: pathlib.Path, name: str, *, subject: pathlib.Path | None = None):
    args, kw = CASE_KW[name]
    return _run(subject or PORT, tmp_path, args, **kw)  # type: ignore[arg-type]


def compare(tmp_path: pathlib.Path, name: str, *, subject: pathlib.Path | None = None):
    want_exit, want_out, want_err, want_calls = recorded(name)
    proc, calls = drive(tmp_path, name, subject=subject)
    assert proc.returncode == want_exit, (
        f"{name}: the twin exited {want_exit}, the port {proc.returncode}"
    )
    assert proc.stdout == want_out, f"{name}: stdout diverged from the recorded bytes"
    assert proc.stderr == want_err, f"{name}: stderr diverged from the recorded bytes"
    assert calls == want_calls, f"{name}: the request sequence diverged:\n{want_calls}\n{calls}"
    return proc, calls


def list_call(page: int) -> str:
    """The recorded line for one listing request. `[1:]` drops the argv[0] `curl`, which the fake writes itself as the log's own first field."""
    return "curl\t" + "\t".join(
        port.curl_argv("GET", port.deployments_path(ACCOUNT, page), BEARER)[1:]
    )


def delete_call(dep_id: str) -> str:
    return "curl\t" + "\t".join(
        port.curl_argv("DELETE", port.delete_path(ACCOUNT, dep_id), BEARER)[1:]
    )


@pytest.mark.parametrize("name", [c for c in CASES if c != DIVERGENT])
def test_port_matches_the_twins_recorded_output(tmp_path: pathlib.Path, name: str) -> None:
    compare(tmp_path, name)


def test_every_case_has_a_golden_and_no_golden_is_orphaned() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, set(CASES))


def test_the_request_shape_is_asserted_in_full(tmp_path: pathlib.Path) -> None:
    """THE REQUESTS, PINNED AGAINST THE LITERAL BYTES rather than against the port's own helpers, so that a change in both would still be caught. Method, URL, and BOTH headers, for both endpoints."""
    want_exit, _, _, want_calls = recorded("the-request-shape")
    assert want_exit == 0
    assert want_calls == [
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
    assert want_calls == [list_call(1), delete_call("dep-1-0")]
    compare(tmp_path, "the-request-shape")


def test_only_the_named_branch_is_deleted(tmp_path: pathlib.Path) -> None:
    """THE ONE REFUSAL. The listing carries deployments from OTHER branches and they must never be touched; the filter is
    `.deployment_trigger.metadata.branch == $branch`."""
    _, _, stderr, calls = recorded("only-the-named-branch")
    assert "Found 3 preview deployments for branch 'feature-x'" in stderr
    deleted = [c for c in calls if "DELETE" in c]
    assert len(deleted) == 3
    assert all("dep-1-0" in c or "dep-1-2" in c or "dep-1-4" in c for c in deleted), deleted
    compare(tmp_path, "only-the-named-branch")


def test_a_branch_with_no_deployments_is_a_clean_no_op(tmp_path: pathlib.Path) -> None:
    returncode, stdout, stderr, calls = recorded("a-branch-with-no-deployments")
    assert returncode == 0
    assert stderr == (
        "→ Cleaning up CF Pages preview deployments for branch: nothing-here\n"
        "→ Found 0 preview deployments for branch 'nothing-here'\n"
        "✓ No preview deployments to clean up\n"
    )
    assert stdout == "", "this script must never put anything on stdout"
    assert not any("DELETE" in c for c in calls)
    compare(tmp_path, "a-branch-with-no-deployments")


def test_dry_run_makes_no_delete_request_at_all(tmp_path: pathlib.Path) -> None:
    returncode, _, stderr, calls = recorded("a-dry-run")
    assert returncode == 0
    assert stderr == (
        "→ Cleaning up CF Pages preview deployments for branch: feature-x\n"
        "⚠ DRY-RUN mode: no deletions will be performed\n"
        "→ Found 1 preview deployments for branch 'feature-x'\n"
        "⚠ [DRY-RUN] Would delete: dep-1-0 (created: 2026-01-01)\n"
        "✓ Would delete 1 of 1 deployments for branch 'feature-x'\n"
    )
    assert not any("DELETE" in c for c in calls), "a dry run issued a DELETE"
    compare(tmp_path, "a-dry-run")


def test_dry_run_false_is_not_a_dry_run(tmp_path: pathlib.Path) -> None:
    """parse_args quirk 2: `--dry-run false` stored the STRING `false`, and the comparison was against the literal `true`. So this really deletes."""
    returncode, _, stderr, calls = recorded("dry-run-false-is-not-a-dry-run")
    assert returncode == 0
    assert "DRY-RUN" not in stderr
    assert any("DELETE" in c for c in calls)
    compare(tmp_path, "dry-run-false-is-not-a-dry-run")


def test_pagination_follows_until_a_short_page(tmp_path: pathlib.Path) -> None:
    """`per_page=25` and `[[ "$all_results" -lt 25 ]]`. A full page means there
    may be more; a short one ends the sweep. Three listings here: two full, one short."""
    returncode, _, stderr, calls = recorded("pagination-to-a-short-page")
    assert returncode == 0
    lists = [c for c in calls if "\tGET\t" in c]
    assert lists == [list_call(1), list_call(2), list_call(3)]
    assert "Found 26 preview deployments" in stderr
    compare(tmp_path, "pagination-to-a-short-page")


def test_a_refused_delete_is_reported_and_the_sweep_continues(tmp_path: pathlib.Path) -> None:
    """Cloudflare refuses to delete the LATEST deployment of a branch. That is expected, not fatal: refusing over it would leave every older preview behind."""
    returncode, _, stderr, calls = recorded("a-refused-delete")
    assert returncode == 0
    assert stderr.count("⚠ Could not delete ") == 3
    assert "latest deployment cannot be deleted" in stderr
    assert "✓ Deleted 0 of 3 deployments for branch 'feature-x'\n" in stderr
    assert len([c for c in calls if "DELETE" in c]) == 3, "the sweep stopped early"
    compare(tmp_path, "a-refused-delete")


def test_a_successful_delete_is_silent_unless_debug_is_true(tmp_path: pathlib.Path) -> None:
    """`log_debug` was gated on `DEBUG=true` EXACTLY -- not on any truthy value.
    All three states are recorded, because a port that logged unconditionally would look fine to a reader and change the workflow log."""
    assert "Deleted: dep-1-0" not in recorded("the-request-shape")[2]
    assert "[DEBUG] Deleted: dep-1-0" in recorded("debug-is-exactly-true")[2]
    assert "Deleted: dep-1-0" not in recorded("debug-is-one")[2], "DEBUG=1 is not DEBUG=true"
    for name in ("the-request-shape", "debug-is-exactly-true", "debug-is-one"):
        compare(tmp_path / name, name)


def test_no_branch_is_refused_after_the_prerequisites(tmp_path: pathlib.Path) -> None:
    returncode, _, stderr, calls = recorded("no-branch-at-all")
    assert returncode == 1
    assert stderr == ("✗ Usage: cleanup-cf-preview.sh --branch <branch_name> [--dry-run]\n")
    assert calls == []
    compare(tmp_path, "no-branch-at-all")


def test_a_missing_token_is_refused_before_the_missing_branch(tmp_path: pathlib.Path) -> None:
    """ORDER IS OBSERVABLE. `require_var` ran BEFORE the branch check, so a run
    with neither says which variable is missing rather than printing usage."""
    returncode, _, stderr, _ = recorded("a-missing-token")
    assert returncode == 1
    assert stderr == ("✗ Required environment variable 'CLOUDFLARE_API_TOKEN' is not set\n")
    compare(tmp_path, "a-missing-token")


def test_a_missing_account_id_is_refused(tmp_path: pathlib.Path) -> None:
    returncode, _, stderr, _ = recorded("a-missing-account-id")
    assert returncode == 1
    assert "CLOUDFLARE_ACCOUNT_ID" in stderr
    compare(tmp_path, "a-missing-account-id")


def test_missing_curl_is_refused_before_missing_jq(tmp_path: pathlib.Path) -> None:
    returncode, _, stderr, _ = recorded("a-missing-curl")
    assert returncode == 1
    assert stderr == "✗ Required command 'curl' is not available\n"
    compare(tmp_path, "a-missing-curl")


def test_missing_jq_is_refused(tmp_path: pathlib.Path) -> None:
    """The port shells out to jq for the same reason the twin did, so `jq` is a real prerequisite of BOTH and this refusal has to agree."""
    returncode, _, stderr, _ = recorded("a-missing-jq")
    assert returncode == 1
    assert stderr == "✗ Required command 'jq' is not available\n"
    compare(tmp_path, "a-missing-jq")


def test_defect_a_failed_listing_reads_as_nothing_to_do(tmp_path: pathlib.Path) -> None:
    """THE VACUITY DEFECT, PINNED. curl could not reach the host, the `|| echo
    '{"result":[]}'` fallback fired, `.success // false` was false, and the run
    ended GREEN with "No preview deployments to clean up". The one warning line sits in the middle of a successful run, so a branch whose previews were never enumerated is indistinguishable from a branch that had none.

    Reproduced because agreement with the twin was the deliverable;
    repaired, this test goes red and names the port that must follow.
    """
    returncode, _, stderr, _ = recorded("an-unreachable-api")
    assert returncode == 0, "the twin failed on an unreachable API"
    assert stderr == (
        "→ Cleaning up CF Pages preview deployments for branch: feature-x\n"
        "⚠ CF API request failed on page 1\n"
        "→ Found 0 preview deployments for branch 'feature-x'\n"
        "✓ No preview deployments to clean up\n"
    )
    assert port.API_FAILURE_READS_AS_NOTHING_TO_DO
    compare(tmp_path, "an-unreachable-api")


def test_an_unsuccessful_listing_body_is_the_same_green(tmp_path: pathlib.Path) -> None:
    """A 200 whose body says `success: false` -- an auth failure, say -- took the identical path. Recorded separately from the transport failure because the two reach the branch by different routes."""
    returncode, _, stderr, _ = recorded("an-unsuccessful-listing-body")
    assert returncode == 0
    assert "CF API request failed on page 1" in stderr
    assert "No preview deployments to clean up" in stderr
    compare(tmp_path, "an-unsuccessful-listing-body")


def test_a_non_json_body_kills_the_run_with_jqs_own_message(tmp_path: pathlib.Path) -> None:
    """THE CASE A `json.loads` PORT WOULD GET WRONG. An HTML error page reached an unguarded `jq`, whose parse error went to stderr and whose exit status passed through `set -e`. Both the message and the status must agree, which is why the port runs jq rather than parsing in Python."""
    returncode, _, stderr, _ = recorded("a-non-json-body")
    assert returncode == 5, f"jq's status changed: {returncode}"
    assert "jq: parse error" in stderr
    assert "Found" not in stderr, "the run continued past the parse error"
    compare(tmp_path, "a-non-json-body")


def test_a_result_less_body_dies_on_the_filter_not_on_the_length(tmp_path: pathlib.Path) -> None:
    """`[.result[] | ...]` was evaluated BEFORE `.result | length`, so a body with `success: true` and no `result` key dies with "Cannot iterate over null" rather than reporting zero. Order matters and is asserted."""
    returncode, _, stderr, _ = recorded("a-result-less-body")
    assert returncode == 5
    assert "Cannot iterate over null" in stderr
    compare(tmp_path, "a-result-less-body")


def test_an_empty_body_does_not_die(tmp_path: pathlib.Path) -> None:
    """The third jq shape: EMPTY input made `jq -r '.success // false'` emit nothing at all and exit 0, so `success` was the empty string and the ordinary warning branch ran. Not a parse error, and not a pass."""
    returncode, _, stderr, _ = recorded("an-empty-body")
    assert returncode == 0
    assert "CF API request failed on page 1" in stderr
    assert "jq:" not in stderr
    compare(tmp_path, "an-empty-body")


def test_a_branch_name_with_a_space_is_carried_through_the_filter(tmp_path: pathlib.Path) -> None:
    """`--arg branch "$BRANCH"` passed the name as DATA to jq, so a branch name is never a jq program fragment. Driven with a space because parse_args consumes the next token whole."""
    returncode, _, stderr, _ = recorded("a-branch-name-with-a-space")
    assert returncode == 0
    assert "Found 1 preview deployments for branch 'odd name'" in stderr
    compare(tmp_path, "a-branch-name-with-a-space")


def test_divergence_common_sh_interprets_backslash_escapes_in_the_cf_error(
    tmp_path: pathlib.Path,
) -> None:
    """A DELIBERATE DIVERGENCE, ASSERTED IN BOTH DIRECTIONS SO IT CANNOT BE
    "FIXED" BY ACCIDENT. `Could not delete <id>: <error_msg>` is the one message that interpolates remote text, and common.sh logged through `echo -e`. `rediacc_ci.log` formats the message as data (see its module docstring)."""
    want_exit, _, want_err, _ = recorded(DIVERGENT)
    proc, _ = drive(tmp_path, DIVERGENT)
    assert want_exit == proc.returncode == 0
    assert "boom\nline two" in want_err, (
        "the recording no longer shows the twin interpreting escapes"
    )
    assert "boom\\nline two" in proc.stderr, "the port started interpreting escapes"
    assert want_err != proc.stderr


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
    # The two `|| echo` fallbacks are DIFFERENT shapes, and both must be false under `.success // false`.
    assert port.LIST_FALLBACK == '{"result":[]}'
    assert port.DELETE_FALLBACK == '{"success":false}'


def test_planted_branch_filter_defect_is_caught(tmp_path: pathlib.Path) -> None:
    """ANTI-VACUITY, planted on the branch filter -- the one refusal in the script, and the one whose omission deletes other branches' live previews
    while printing a bigger, entirely plausible tally. Driven red against the recording, then the source is confirmed byte-identical and green.
    """
    original = PORT.read_text(encoding="utf-8")
    # The target is the SELECT CLAUSE ALONE, not the whole statement. The first version of this plant matched two source lines including their indentation, and `ruff format` re-wrapped them minutes later -- the guard below caught it, which is the reason the guard is an assertion rather than a comment. `select(true)` keeps the jq program valid and `$branch` still bound, so the ONLY
    # thing the mutant loses is the refusal.
    mutated = original.replace(
        "select(.deployment_trigger.metadata.branch == $branch) ",
        "select(true) ",
    )
    assert mutated != original, "the line this plant targets is no longer present verbatim"
    mutant = tmp_path / "mutant.py"
    mutant.write_text(mutated, encoding="utf-8")

    _, _, want_err, want_calls = recorded("only-the-named-branch")
    assert "Found 3 preview deployments" in want_err, "the TWIN filtered nothing; plant untested"
    assert not any("dep-1-1" in c for c in want_calls), "the TWIN deleted another branch's preview"

    bad, bad_calls = drive(tmp_path / "bad", "only-the-named-branch", subject=mutant)
    assert "Found 6 preview deployments" in bad.stderr, "the mutant still filtered by branch"
    assert [c for c in bad_calls if "dep-1-1" in c], "the mutant did not reach another branch"
    with pytest.raises(AssertionError):
        compare(tmp_path / "bad2", "only-the-named-branch", subject=mutant)

    compare(tmp_path / "good", "only-the-named-branch")
    assert PORT.read_text(encoding="utf-8") == original, (
        "port source must be restored byte-identical"
    )


def test_planted_page_size_defect_is_caught(tmp_path: pathlib.Path) -> None:
    """THE NEW CONTROL ON THE GOLDENS. Shrink the page size by one.

    `per_page=25` appears in every listing URL and in the `-lt 25` short-page test, so a port that paginated in twenties would still sweep correctly and still print a plausible tally: the only witness is the recorded request log, where page 3 was requested because page 2 came back full at 25. The mutant is written to a throwaway file; the tracked port is never touched.
    """
    original = PORT.read_text(encoding="utf-8")
    anchor = "PAGE_SIZE = 25\n"
    assert original.count(anchor) == 1, "the plant's anchor moved"
    mutant = tmp_path / "mutant.py"
    mutant.write_text(original.replace(anchor, "PAGE_SIZE = 24\n"), encoding="utf-8")

    with pytest.raises(AssertionError):
        compare(tmp_path / "bad", "pagination-to-a-short-page", subject=mutant)
    compare(tmp_path / "good", "pagination-to-a-short-page")
    assert PORT.read_text(encoding="utf-8") == original

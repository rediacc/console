"""Fake-gh tests for `rediacc_ci.review.review_status`, the advisory Review Complete reporter.

THE REPORTER WRITES TO GITHUB, so the fake `gh` is load-bearing. Three things keep the real binary out of reach: the stub directory is the only `gh` on PATH (`test_the_fake_gh_is_the_gh`), every case names a repository that does not exist (`acme/widget`), and `GH_TOKEN` is a fixture string with `GH_CONFIG_DIR` inside the temp tree, so a leaked real `gh` fails auth instead of writing.

THE FAKE ROUTES BY ENDPOINT and answers each `--jq` call with the value that expression would produce from the fixture, so no `jq` binary is involved. Every write is captured with its argv and stdin body; the tests assert on the captured payload, because a reporter that logged the right sentence and posted the wrong conclusion would pass a stdout-only check.

ONE CASE PER TITLE TOKEN, both budget arms, the outage excuse with a matched and an unmatched class, the `workflow_run` artifact path, a failing hygiene script giving `failure`, and `test_each_scenario_posts_the_ruled_conclusion`, the control that sweeps every token and asserts `failure` exactly for `stale`, `failed-run` and `hygiene`, `neutral` for `draft`, and `success` for the rest (operator ruling 2026-10-03: Review Complete is required again, and only an LLM outage excuses a failed review).
"""

from __future__ import annotations

import io
import json
import os
import shutil
import sys
import zipfile
from typing import TYPE_CHECKING

import pytest

from rediacc_ci import paths
from rediacc_ci.review import claude_review_gate
from rediacc_ci.review import review_status as rs

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Callable

ROOT = paths.repo_root()

REPO = "acme/widget"
OLD_SHA = "1" * 40
NEW_SHA = "2" * 40
PR = "42"

FAKE_GH = (
    r'''#!%s
"""Routing fake for `gh`: fixture answers per endpoint, writes captured, never served."""
import io
import json
import os
import sys
import zipfile

argv = sys.argv[1:]
fixtures = os.environ["FAKE_GH_DIR"]


def fixture(name, default=None):
    path = os.path.join(fixtures, name + ".json")
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


method = "GET"
explicit = False
has_field = False
read_stdin = False
path = ""
i = 1 if argv and argv[0] == "api" else 0
while i < len(argv):
    arg = argv[i]
    if arg in ("-X", "--method"):
        i += 1
        method = argv[i]
        explicit = True
    elif arg in ("--jq", "--repo", "--json"):
        i += 1
    elif arg in ("--input", "-f", "-F", "--field", "--raw-field"):
        i += 1
        has_field = True
        read_stdin = read_stdin or arg == "--input"
    elif arg.startswith("-"):
        pass
    elif not path:
        path = arg
    i += 1
if not explicit and has_field:
    method = "POST"

body = sys.stdin.read() if read_stdin else ""
with open(os.environ["FAKE_GH_LOG"], "a", encoding="utf-8") as handle:
    handle.write(json.dumps({"argv": argv, "method": method, "path": path, "body": body}) + "\n")

if method not in ("GET",):
    print('{"id": 999}')
    sys.exit(0)

if argv[:2] == ["pr", "view"]:
    size = fixture("pr-size")
    print(size["additions"] + size["deletions"])
elif path.endswith("/check-runs"):
    existing = fixture("existing-check")
    if existing:
        print(existing)
elif "/actions/runs/" in path and path.endswith("/artifacts"):
    for art in fixture("run-artifacts", []):
        print(art)
elif "/actions/artifacts/" in path and path.endswith("/zip"):
    member = fixture("review-target")
    if member is None:
        sys.exit(1)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr("review-target.txt", member)
    sys.stdout.buffer.write(buf.getvalue())
elif "/compare/" in path:
    names = fixture("compare")
    if names is None:
        sys.exit(1)
    print(json.dumps(names))
elif path.endswith("/comments"):
    print(json.dumps(fixture("comments", [])))
elif "/pulls/" in path:
    print(json.dumps(fixture("pull")))
else:
    sys.stderr.write("fake gh: unrouted %%r\n" %% (argv,))
    sys.exit(3)
'''
    % sys.executable
)

HYGIENE_STUB = """#!/bin/sh
echo "stub %s for PR ${PR_NUMBER:-?} on ${GITHUB_REPOSITORY:-?}"
exit %d
"""

GITMODULES = """[submodule "private/renet"]
\tpath = private/renet
\turl = git@example.invalid:acme/renet.git
"""


def _marker(sha: str) -> dict:
    return {
        "id": 1,
        "user": {"login": "github-actions[bot]"},
        "body": "%s %s -->\nAutomated Claude review completed." % (rs.MARKER_PREFIX, sha),
    }


def _report(index: int) -> dict:
    return {
        "id": 100 + index,
        "user": {"login": "github-actions[bot]"},
        "body": "**Claude finished the automated review of 1111111**\nlooks fine",
    }


def _attempt(sha: str, attempts: int, cls: str) -> dict:
    return {
        "id": 200 + attempts,
        "user": {"login": "github-actions[bot]"},
        "body": "%s %s -->\nattempts: %d\nclass: %s" % (rs.ATTEMPT_PREFIX, sha, attempts, cls),
    }


class World:
    """One fixture tree: a fake `gh`, its answers, hygiene stubs and a log of every call."""

    def __init__(self, base: pathlib.Path) -> None:
        self.base = base
        self.fixtures = base / "fixtures"
        self.fixtures.mkdir()
        self.bin = base / "bin"
        self.bin.mkdir()
        fake = self.bin / "gh"
        fake.write_text(FAKE_GH, encoding="utf-8")
        fake.chmod(0o755)
        self.log = base / "gh.log"
        self.log.write_text("", encoding="utf-8")
        self.hygiene_dir = base / "hygiene"
        (base / ".gitmodules").write_text(GITMODULES, encoding="utf-8")
        self.write("pull", {"state": "open", "draft": False, "head": NEW_SHA})
        self.write("comments", [_marker(NEW_SHA)])
        self.write("pr-size", {"additions": 100, "deletions": 40})
        self.hygiene(0, 0)

    def write(self, key: str, value: object) -> None:
        (self.fixtures / ("%s.json" % key)).write_text(json.dumps(value), encoding="utf-8")

    def remove(self, key: str) -> None:
        (self.fixtures / ("%s.json" % key)).unlink(missing_ok=True)

    def hygiene(self, *codes: int) -> None:
        self.hygiene_dir.mkdir(exist_ok=True)
        for name, code in zip(rs.HYGIENE_SCRIPTS, codes, strict=True):
            script = self.hygiene_dir / name
            script.write_text(HYGIENE_STUB % (name, code), encoding="utf-8")
            script.chmod(0o755)

    def calls(self) -> list[dict]:
        lines = self.log.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines if line]

    def writes(self) -> list[dict]:
        return [call for call in self.calls() if call["method"] != "GET"]

    def payload(self) -> dict:
        writes = self.writes()
        assert len(writes) == 1, writes
        return json.loads(writes[0]["body"])


@pytest.fixture
def world(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> World:
    w = World(tmp_path)
    for key in list(os.environ):
        if key.startswith(("WR_", "GITHUB_", "GH_")) or key in (
            "PR_NUMBER",
            "EVENT_NAME",
            "CHECK_NAME",
        ):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("PATH", "%s:/usr/bin:/bin" % w.bin)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("GH_TOKEN", "not-a-real-token")
    monkeypatch.setenv("GH_CONFIG_DIR", str(tmp_path / "gh-config"))
    monkeypatch.setenv("FAKE_GH_DIR", str(w.fixtures))
    monkeypatch.setenv("FAKE_GH_LOG", str(w.log))
    monkeypatch.setenv("GITHUB_REPOSITORY", REPO)
    monkeypatch.setenv("EVENT_NAME", "issue_comment")
    monkeypatch.setenv("PR_NUMBER", PR)
    monkeypatch.chdir(tmp_path)
    return w


def _run(world: World) -> int:
    try:
        return rs.run(hygiene_dir=world.hygiene_dir)
    except rs.ReporterError as broken:
        return broken.code


def _token(payload: dict) -> str:
    return payload["output"]["title"].split(":", 1)[0]


# --------------------------------------------------------------------------- controls


def test_the_fake_gh_is_the_gh(world: World) -> None:
    assert shutil.which("gh") == str(world.bin / "gh")


def test_the_prefixes_are_the_gates_own_objects() -> None:
    assert rs.MARKER_PREFIX is claude_review_gate.MARKER_PREFIX
    assert rs.ATTEMPT_PREFIX is claude_review_gate.ATTEMPT_PREFIX
    assert not hasattr(rs, "parse_prefix")


def test_the_title_tokens_are_frozen() -> None:
    assert rs.TITLE_TOKENS == (
        "draft",
        "failed-run",
        "stale",
        "hygiene",
        "capped",
        "exhausted",
        "outage",
        "current",
    )
    for token in rs.TITLE_TOKENS:
        title = rs.title_for(token)
        assert title.startswith(token + ": "), title
        assert title.split(":", 1)[0] == token
    assert rs.TOKEN_CONCLUSION == {
        "draft": "neutral",
        "failed-run": "failure",
        "stale": "failure",
        "hygiene": "failure",
        "capped": "success",
        "exhausted": "success",
        "outage": "success",
        "current": "success",
    }


def test_the_default_hygiene_dir_holds_both_real_scripts() -> None:
    """ANTI-VACUITY: the tests point at stubs, so the shipped default must name real executables."""
    assert rs.DEFAULT_HYGIENE_DIR == ROOT / ".ci" / "scripts" / "quality"
    for name in rs.HYGIENE_SCRIPTS:
        path = rs.DEFAULT_HYGIENE_DIR / name
        assert path.is_file(), path
        assert os.access(path, os.X_OK), path
    assert rs.HYGIENE_SCRIPTS == ("check_resolved_threads.py", "check_review_comments.py")


def test_check_payload_refuses_an_unknown_conclusion() -> None:
    with pytest.raises(rs.ReporterError):
        rs.check_payload("Review Complete", NEW_SHA, "cancelled", "stale: x", "body")
    assert rs.check_payload("Review Complete", NEW_SHA, "failure", "stale: x", "b")[
        "conclusion"
    ] == ("failure")


def test_the_outage_classes_are_exact_and_conservative() -> None:
    assert rs.OUTAGE_CLASSES == (
        "api_error_429",
        "api_error_500",
        "api_error_502",
        "api_error_503",
        "api_error_504",
        "api_error_529",
    )
    for cls in rs.OUTAGE_CLASSES:
        assert rs.is_outage_class(cls)
    for cls in (
        "api_error_401",
        "api_error_403",
        "api_error_400",
        "error_max_turns",
        "error_during_execution",
        "error_max_budget_usd",
        "error_max_structured_output_retries",
        "review step did not succeed",
        "",
        "API_ERROR_529",
        "api_error_529 ",
        "x api_error_503",
    ):
        assert not rs.is_outage_class(cls), cls


# --------------------------------------------------------------------------- one case per token


def test_current(world: World) -> None:
    assert _run(world) == 0
    payload = world.payload()
    assert payload["conclusion"] == "success"
    assert _token(payload) == "current"
    assert payload["head_sha"] == NEW_SHA
    assert payload["name"] == "Review Complete"
    assert payload["status"] == "completed"


def test_stale_without_any_marker(world: World) -> None:
    world.write("comments", [])
    assert _run(world) == 0
    payload = world.payload()
    assert payload["conclusion"] == "failure"
    assert _token(payload) == "stale"
    assert "has not been reviewed" in payload["output"]["summary"]


def test_stale_when_real_files_changed_since_the_marker(world: World) -> None:
    world.write("comments", [_marker(OLD_SHA)])
    world.write("compare", ["private/renet", "packages/cli/src/index.ts"])
    assert _run(world) == 0
    payload = world.payload()
    assert _token(payload) == "stale"
    assert "1 non-submodule file(s) changed" in payload["output"]["summary"]


def test_a_failed_compare_fails_closed(world: World) -> None:
    world.write("comments", [_marker(OLD_SHA)])
    assert _run(world) == 0
    assert _token(world.payload()) == "stale"


def test_gitlink_only_delta_is_current(world: World) -> None:
    world.write("comments", [_marker(OLD_SHA)])
    world.write("compare", ["private/renet"])
    assert _run(world) == 0
    payload = world.payload()
    assert _token(payload) == "current"
    assert "only submodule pointer bumps" in payload["output"]["summary"]


def test_hygiene_failure_gives_failure(world: World) -> None:
    world.hygiene(0, 1)
    assert _run(world) == 0
    payload = world.payload()
    assert payload["conclusion"] == "failure"
    assert _token(payload) == "hygiene"
    summary = payload["output"]["summary"]
    assert "`check_review_comments.py` failed (exit 1)" in summary
    assert "stub check_review_comments.py for PR 42 on acme/widget" in summary


def test_capped_passes_with_a_warning(world: World) -> None:
    world.write("comments", [_marker(OLD_SHA), _report(1), _report(2), _report(3)])
    assert _run(world) == 0
    payload = world.payload()
    assert payload["conclusion"] == "success"
    assert _token(payload) == "capped"
    assert "**REVIEW CAP REACHED** (3/3)" in payload["output"]["summary"]


def test_capped_with_failing_hygiene_is_hygiene(world: World) -> None:
    world.write("comments", [_marker(OLD_SHA), _report(1), _report(2), _report(3)])
    world.hygiene(1, 0)
    assert _run(world) == 0
    payload = world.payload()
    assert payload["conclusion"] == "failure"
    assert _token(payload) == "hygiene"


def test_exhausted_passes_with_a_warning(world: World) -> None:
    world.write("comments", [_marker(OLD_SHA), _attempt(NEW_SHA, 3, "error_max_turns")])
    assert _run(world) == 0
    payload = world.payload()
    assert payload["conclusion"] == "success"
    assert _token(payload) == "exhausted"
    assert "**HEAD REVIEW ATTEMPTS EXHAUSTED**" in payload["output"]["summary"]


def test_a_non_infra_attempt_never_exhausts_the_head(world: World) -> None:
    world.write("comments", [_marker(OLD_SHA), _attempt(NEW_SHA, 1, "")])
    assert _run(world) == 0
    assert _token(world.payload()) == "stale"


def test_draft(world: World) -> None:
    world.write("pull", {"state": "open", "draft": True, "head": NEW_SHA})
    shutil.rmtree(world.hygiene_dir)
    assert _run(world) == 0
    payload = world.payload()
    assert payload["conclusion"] == "neutral"
    assert _token(payload) == "draft"


def _workflow_run(monkeypatch: pytest.MonkeyPatch, conclusion: str) -> None:
    monkeypatch.setenv("EVENT_NAME", "workflow_run")
    monkeypatch.delenv("PR_NUMBER")
    monkeypatch.setenv("WR_RUN_ID", "777")
    monkeypatch.setenv("WR_CONCLUSION", conclusion)
    monkeypatch.setenv("WR_HTML_URL", "https://example.invalid/run/777")


def test_failed_run(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    _workflow_run(monkeypatch, "failure")
    world.write("run-artifacts", [9001])
    world.write("review-target", "42\n")
    world.write("comments", [_marker(OLD_SHA), _attempt(NEW_SHA, 1, "error_during_execution")])
    assert _run(world) == 0
    payload = world.payload()
    assert payload["conclusion"] == "failure"
    assert _token(payload) == "failed-run"
    summary = payload["output"]["summary"]
    assert "investigate and fix: the Claude Review run concluded `failure`" in summary
    assert "(last attempt class `error_during_execution`)" in summary
    assert "https://example.invalid/run/777" in summary


def test_a_failed_run_on_an_already_reviewed_head_is_current(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    _workflow_run(monkeypatch, "timed_out")
    world.write("run-artifacts", [9001])
    world.write("review-target", "42\n")
    assert _run(world) == 0
    assert _token(world.payload()) == "current"


def test_outage_matched_class_passes_with_a_warning(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    _workflow_run(monkeypatch, "failure")
    world.write("run-artifacts", [9001])
    world.write("review-target", "42\n")
    world.write("comments", [_marker(OLD_SHA), _attempt(NEW_SHA, 1, "api_error_529")])
    assert _run(world) == 0
    payload = world.payload()
    assert payload["conclusion"] == "success"
    assert _token(payload) == "outage"
    summary = payload["output"]["summary"]
    assert "**LLM OUTAGE**" in summary
    assert "`api_error_529`" in summary
    assert "investigate and fix:" not in summary


def test_outage_unmatched_class_is_not_excused(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    _workflow_run(monkeypatch, "failure")
    world.write("run-artifacts", [9001])
    world.write("review-target", "42\n")
    world.write("comments", [_marker(OLD_SHA), _attempt(NEW_SHA, 1, "api_error_401")])
    assert _run(world) == 0
    payload = world.payload()
    assert payload["conclusion"] == "failure"
    assert _token(payload) == "failed-run"
    assert "**LLM OUTAGE**" not in payload["output"]["summary"]


def test_outage_reads_only_the_current_heads_class(world: World) -> None:
    world.write("comments", [_marker(OLD_SHA), _attempt(OLD_SHA, 1, "api_error_503")])
    assert _run(world) == 0
    payload = world.payload()
    assert payload["conclusion"] == "failure"
    assert _token(payload) == "stale"


def test_outage_with_failing_hygiene_is_hygiene(world: World) -> None:
    world.write("comments", [_marker(OLD_SHA), _attempt(NEW_SHA, 1, "api_error_503")])
    world.hygiene(0, 1)
    assert _run(world) == 0
    payload = world.payload()
    assert payload["conclusion"] == "failure"
    assert _token(payload) == "hygiene"


def test_workflow_run_resolves_the_pr_from_the_artifact(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    _workflow_run(monkeypatch, "success")
    world.write("run-artifacts", [9001])
    world.write("review-target", "PR 42\n")
    assert _run(world) == 0
    payload = world.payload()
    assert _token(payload) == "current"
    paths_hit = [call["path"] for call in world.calls()]
    assert "repos/acme/widget/actions/runs/777/artifacts" in paths_hit
    assert "repos/acme/widget/actions/artifacts/9001/zip" in paths_hit
    assert "repos/acme/widget/pulls/42" in paths_hit


def test_workflow_run_with_no_artifact_posts_nothing(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    _workflow_run(monkeypatch, "success")
    assert _run(world) == 0
    assert world.writes() == []


def test_an_artifact_that_cannot_be_downloaded_breaks_the_reporter(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    _workflow_run(monkeypatch, "success")
    world.write("run-artifacts", [9001])
    assert _run(world) == 1
    assert world.writes() == []


def test_an_artifact_with_no_number_breaks_the_reporter(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    _workflow_run(monkeypatch, "success")
    world.write("run-artifacts", [9001])
    world.write("review-target", "no digits here\n")
    assert _run(world) == 1
    assert world.writes() == []


# --------------------------------------------------------------------------- write shape and reporter failures


def test_an_existing_check_run_is_patched_without_head_sha(world: World) -> None:
    world.write("existing-check", 555)
    assert _run(world) == 0
    (write,) = world.writes()
    assert write["method"] == "PATCH"
    assert write["path"] == "repos/acme/widget/check-runs/555"
    body = json.loads(write["body"])
    assert "head_sha" not in body
    assert body["conclusion"] == "success"


def test_check_name_is_configurable(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHECK_NAME", "Review Status")
    assert _run(world) == 0
    assert world.payload()["name"] == "Review Status"


def test_a_missing_hygiene_script_breaks_the_reporter(world: World) -> None:
    (world.hygiene_dir / rs.HYGIENE_SCRIPTS[1]).unlink()
    assert _run(world) == 1
    assert world.writes() == []


def test_a_closed_pr_posts_nothing(world: World) -> None:
    world.write("pull", {"state": "closed", "draft": False, "head": NEW_SHA})
    assert _run(world) == 0
    assert world.writes() == []


def test_a_non_numeric_pr_number_is_refused_before_any_api_call(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PR_NUMBER", "42/../../x")
    assert _run(world) == 1
    assert world.calls() == []


def test_a_non_ascii_digit_pr_number_is_refused_before_any_api_call(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `str.isdigit()` accepts these; a REST path must not.
    monkeypatch.setenv("PR_NUMBER", "\uff14\uff12")
    assert _run(world) == 1
    assert world.calls() == []


def test_a_non_numeric_run_id_is_refused_before_any_api_call(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    _workflow_run(monkeypatch, "success")
    monkeypatch.setenv("WR_RUN_ID", "777/../../pulls/1")
    world.write("run-artifacts", [9001])
    world.write("review-target", "42\n")
    assert _run(world) == 1
    assert world.calls() == []


def test_a_malformed_head_sha_is_refused_before_any_write(world: World) -> None:
    world.write("pull", {"state": "open", "draft": False, "head": 'a" or true or "'})
    assert _run(world) == 1
    assert world.writes() == []
    # Control: the well-formed head posts.
    world.write("pull", {"state": "open", "draft": False, "head": NEW_SHA})
    assert _run(world) == 0
    assert len(world.writes()) == 1


def test_an_unsupported_event_breaks_the_reporter(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EVENT_NAME", "push")
    assert _run(world) == 1
    assert world.calls() == []


def test_main_maps_a_missing_variable_to_a_nonzero_exit(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GITHUB_REPOSITORY")
    assert rs.main() != 0
    assert world.calls() == []


# --------------------------------------------------------------------------- the advisory control


def _scenarios() -> list[tuple[str, str, Callable[[World, pytest.MonkeyPatch], None]]]:
    """(expected token, expected conclusion, setup) for every token."""

    def current(w: World, _mp: pytest.MonkeyPatch) -> None:
        pass

    def stale(w: World, _mp: pytest.MonkeyPatch) -> None:
        w.write("comments", [])

    def stale_diff(w: World, _mp: pytest.MonkeyPatch) -> None:
        w.write("comments", [_marker(OLD_SHA)])
        w.write("compare", ["a.txt"])

    def hygiene_both(w: World, _mp: pytest.MonkeyPatch) -> None:
        w.hygiene(1, 1)

    def capped(w: World, _mp: pytest.MonkeyPatch) -> None:
        w.write("comments", [_marker(OLD_SHA), _report(1), _report(2), _report(3)])

    def exhausted(w: World, _mp: pytest.MonkeyPatch) -> None:
        w.write("comments", [_marker(OLD_SHA), _attempt(NEW_SHA, 3, "error_during_execution")])

    def outage(w: World, _mp: pytest.MonkeyPatch) -> None:
        w.write("comments", [_marker(OLD_SHA), _attempt(NEW_SHA, 1, "api_error_429")])

    def draft(w: World, _mp: pytest.MonkeyPatch) -> None:
        w.write("pull", {"state": "open", "draft": True, "head": NEW_SHA})

    def timed_out(w: World, mp: pytest.MonkeyPatch) -> None:
        _workflow_run(mp, "timed_out")
        w.write("run-artifacts", [1])
        w.write("review-target", "42")
        w.write("comments", [])

    def failed_run_with_hygiene(w: World, mp: pytest.MonkeyPatch) -> None:
        timed_out(w, mp)
        w.hygiene(1, 1)

    def stale_with_hygiene(w: World, _mp: pytest.MonkeyPatch) -> None:
        w.write("comments", [])
        w.hygiene(1, 1)

    return [
        ("current", "success", current),
        ("stale", "failure", stale),
        ("stale", "failure", stale_diff),
        ("hygiene", "failure", hygiene_both),
        ("capped", "success", capped),
        ("exhausted", "success", exhausted),
        ("outage", "success", outage),
        ("draft", "neutral", draft),
        ("failed-run", "failure", timed_out),
        # An unreviewed head outranks a hygiene failure: the token names the missing review, not the unanswered findings.
        ("failed-run", "failure", failed_run_with_hygiene),
        ("stale", "failure", stale_with_hygiene),
    ]


def test_the_scenarios_cover_every_token() -> None:
    assert {token for token, _c, _s in _scenarios()} == set(rs.TITLE_TOKENS)


@pytest.mark.parametrize("case", _scenarios(), ids=lambda c: c[2].__name__)
def test_each_scenario_posts_the_ruled_conclusion(
    world: World, monkeypatch: pytest.MonkeyPatch, case
) -> None:
    token, conclusion, setup = case
    setup(world, monkeypatch)
    assert _run(world) == 0
    payload = world.payload()
    assert _token(payload) == token
    assert payload["conclusion"] == conclusion
    assert (payload["conclusion"] == "failure") == (token in ("stale", "failed-run", "hygiene"))


@pytest.mark.parametrize("failed_run", [False, True])
@pytest.mark.parametrize("currency_ok", [False, True])
@pytest.mark.parametrize("excuse", ["", "capped", "exhausted", "outage"])
@pytest.mark.parametrize("hygiene_failed", [False, True])
def test_select_token_follows_the_docstring_decision(
    failed_run: bool, currency_ok: bool, excuse: str, hygiene_failed: bool
) -> None:
    token = rs.select_token(
        failed_run=failed_run, currency_ok=currency_ok, excuse=excuse, hygiene_failed=hygiene_failed
    )
    if not currency_ok and not excuse:
        expected = "failed-run" if failed_run else "stale"
    elif hygiene_failed:
        expected = "hygiene"
    elif not currency_ok:
        expected = excuse
    else:
        expected = "current"
    assert token == expected


def test_the_zip_reader_takes_only_ascii_digits() -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr(rs.ARTIFACT_MEMBER, "pr=\u0664 42\n")
    assert rs._read_member_digits(buf.getvalue()) == "42"
    assert rs._read_member_digits(b"not a zip") == ""


# --------------------------------------------------------------------------- transient read retry (PLAN-gh-retry G12) ---------------------------------------------------------------------------


def _script_gh(monkeypatch: pytest.MonkeyPatch, answers: list[tuple[int, bytes, bytes]]):
    calls: list[list[str]] = []
    slept: list[float] = []

    def once(args: list[str]) -> tuple[int, bytes, bytes]:
        calls.append(list(args))
        return answers[min(len(calls), len(answers)) - 1]

    monkeypatch.setattr(rs, "_gh_once", once)
    monkeypatch.setattr(rs, "_sleep", slept.append)
    return calls, slept


def test_a_502_read_is_retried_then_answers(monkeypatch: pytest.MonkeyPatch) -> None:
    calls, slept = _script_gh(
        monkeypatch, [(1, b"", b"gh: Server Error (HTTP 502)\n"), (0, b"[]", b"")]
    )
    assert rs._gh(["api", "x"], quiet=True) == (0, b"[]")
    assert len(calls) == 2
    assert slept == [5.0]


def test_a_persistent_5xx_read_fails_after_the_ladder_and_last_marker_is_unreviewed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls, slept = _script_gh(monkeypatch, [(1, b"", b"gh: Server Error (HTTP 503)\n")])
    assert rs.last_marker_sha(REPO, PR, claude_review_gate.MARKER_PREFIX) == ""
    assert len(calls) == 3
    assert slept == [5.0, 15.0]


def test_a_404_read_is_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    calls, slept = _script_gh(monkeypatch, [(1, b"", b"gh: Not Found (HTTP 404)\n")])
    assert rs._gh(["api", "x"], quiet=True)[0] == 1
    assert len(calls) == 1
    assert slept == []


def test_a_pr_read_that_still_5xxs_is_a_reporter_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    _calls, slept = _script_gh(monkeypatch, [(1, b"", b"gh: Server Error (HTTP 502)\n")])
    with pytest.raises(rs.ReporterError):
        rs._read_pr(REPO, PR)
    assert slept == [5.0, 15.0]

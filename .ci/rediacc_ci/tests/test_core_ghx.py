"""`rediacc_ci.core.ghx` against fake `gh` binaries, in both directions.

WHY FAKES AND NOT THE REAL `gh`. The module's whole subject is what happens when a call does NOT succeed, and the failures worth testing -- an expired token, a rate limit, a binary that is not installed -- cannot be produced on demand against the real service, and must never be produced by WRITING to it. So every
case here puts a `gh` of this file's own making first on PATH and drives the
module against it. The one thing that costs is fidelity, and the answer to that is the frozen block below: every stderr string a case asserts on was captured
from the real `gh` 2.98.0 on 2026-09-06, and the capture command is written
beside it so the next reader can re-take the measurement rather than trust it.

EVERY CASE FIRES IN BOTH DIRECTIONS. It is not enough to show that `pr_head_refs()` raises when `gh` fails. Each load-bearing assertion is factored into a `_assert_*` helper that two tests call: one with the module as written, and one with a DEFECT PLANTED into the module -- `pr_list` replaced by the `|| echo "[]"` behaviour the module exists to refuse -- which must make the same
assertion fail. A test that cannot fail is the thing this repository refuses most consistently, and the planted-defect controls are how that is shown here rather than asserted in a comment.
"""

import json
import os
import pathlib
import re
import subprocess
import sys

import pytest

from rediacc_ci import paths, proc
from rediacc_ci.core import ghx
from rediacc_ci.tests import differential as diff

# --------------------------------------------------------------------------- THE FROZEN MEASUREMENTS
#
# Captured on this host 2026-09-06, gh 2.98.0. Each capture command is exact, so a reader who doubts the string re-runs it rather than reasoning about it. ---------------------------------------------------------------------------

# GH_CONFIG_DIR=$(mktemp -d) env -u GH_TOKEN -u GITHUB_TOKEN \
# gh pr list --repo rediacc/console --state open --json number -> exit 4, empty stdout
MEASURED_UNAUTH_RC = 4
MEASURED_UNAUTH_STDERR = (
    "To get started with GitHub CLI, please run:  gh auth login\n"
    "Alternatively, populate the GH_TOKEN environment variable with a GitHub API "
    "authentication token.\n"
)

# GH_CONFIG_DIR=$(mktemp -d) env -u GH_TOKEN -u GITHUB_TOKEN gh auth status
# -> exit 1, empty stdout
MEASURED_AUTH_STATUS_RC = 1
MEASURED_AUTH_STATUS_STDERR = (
    "You are not logged into any GitHub hosts. To log in, run: gh auth login\n"
)

# gh frobnicate -> exit 1
MEASURED_UNKNOWN_VERB_RC = 1
MEASURED_UNKNOWN_VERB_STDERR = 'unknown command "frobnicate" for "gh"\n'

# What GitHub answers when the token is present and the budget is not. Not captured from a live 403 here (that would mean spending the budget to prove the
# string); it is the documented body, and the case that matters is the ORDERING
# it exercises, not the exact wording.
RATE_LIMIT_STDERR = (
    "HTTP 403: API rate limit exceeded for user ID 1. If you reach out to GitHub "
    "Support for help, please include the request ID. (https://api.github.com/...)\n"
    "To get started with GitHub CLI, please run:  gh auth login\n"
)

# A 404 body from `gh api`, which is a JSON OBJECT and not the array a caller of a list endpoint is expecting. This is the shape `json_list` refuses.
NOT_FOUND_BODY = '{"message":"Not Found","documentation_url":"https://docs.github.com/rest"}'

# What a proxy or a captive portal answers instead of an API. The direct analogue of the 404 whose HTML body became a signing key (docs/dev-environments.md:102-110).
HTML_BODY = "<!DOCTYPE html>\n<html><head><title>404 Not Found</title></head></html>\n"


# --------------------------------------------------------------------------- The fake binary ---------------------------------------------------------------------------


@pytest.fixture
def fake_bin(tmp_path, monkeypatch):
    """A factory that puts an executable of our own making on PATH, alone.

    PATH IS REPLACED, NOT PREPENDED. Prepending leaves the real `gh` reachable, and a case that meant to test "gh is absent" would then quietly test the real binary instead -- which is the ambient-dependency failure `differential`'s own docstring warns about. Replacing also makes the absent case a one-liner: a directory with no `gh` in it.
    """
    bindir = tmp_path / "bin"
    bindir.mkdir()
    monkeypatch.setenv("PATH", str(bindir))

    def make(name: str, *, stdout: str = "", stderr: str = "", rc: int = 0) -> pathlib.Path:
        """A fake that prints fixed bytes and exits with a fixed code.

        WRITTEN IN PYTHON, NOT SH, AND THE REASON IS THE FIXTURE ITSELF. PATH is replaced by a directory holding only this fake, so a `#!/bin/sh` script whose body says `cat` cannot find `cat` -- and the failure is silent in the worst possible way: the fake exits 0 having printed NOTHING, which is exactly the empty-answer symptom every case here is trying to tell apart
        from a real one. Measured while writing this file: the sh version printed
        "cat: not found" on stderr and the suite read it as a successful empty list. The shebang here is an absolute interpreter path, so the fake needs nothing from PATH at all.

        The payloads go through FILES rather than through the script text, so a payload containing a quote cannot silently change the script.
        """
        out_file = tmp_path / ("%s.out" % name)
        err_file = tmp_path / ("%s.err" % name)
        out_file.write_text(stdout, encoding="utf-8")
        err_file.write_text(stderr, encoding="utf-8")
        path = bindir / name
        path.write_text(
            "#!" + sys.executable + "\n"
            "import sys\n"
            "sys.stdout.write(open(" + repr(str(out_file)) + ", encoding='utf-8').read())\n"
            "sys.stderr.write(open(" + repr(str(err_file)) + ", encoding='utf-8').read())\n"
            "sys.exit(" + str(rc) + ")\n",
            encoding="utf-8",
        )
        path.chmod(0o755)
        return path

    make.bindir = bindir
    make.tmp = tmp_path
    return make


@pytest.fixture
def argv_recorder(tmp_path, monkeypatch):
    """A fake `gh` that records its argv and its environment, then succeeds."""
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    monkeypatch.setenv("PATH", str(bindir))
    log = tmp_path / "argv.log"
    env_log = tmp_path / "env.log"
    path = bindir / "gh"
    path.write_text(
        "#!" + sys.executable + "\n"
        "import os, sys\n"
        "open(" + repr(str(log)) + ", 'w', encoding='utf-8')"
        ".write('\\n'.join(sys.argv[1:]))\n"
        "open(" + repr(str(env_log)) + ", 'w', encoding='utf-8')"
        ".write('\\n'.join('%s=%s' % kv for kv in os.environ.items()))\n"
        "sys.stdout.write('[]')\n",
        encoding="utf-8",
    )
    path.chmod(0o755)
    return log, env_log


def _rows(*refs: str) -> str:
    """A `gh pr list --json headRefName` body for the given head refs."""
    return json.dumps([{"headRefName": ref} for ref in refs])


# --------------------------------------------------------------------------- ANTI-VACUITY: prove the fake is what runs ---------------------------------------------------------------------------


def test_the_fake_gh_is_the_one_that_runs(fake_bin):
    """Without this, every case below could be driving the developer's real gh
    and passing for reasons that have nothing to do with the fixture."""
    fake_bin("gh", stdout="gh version 0.0.0-fake (1999-01-01)\n")
    resolved = ghx.which_gh()
    assert resolved is not None
    assert resolved.startswith(str(fake_bin.bindir))
    assert ghx.version() == "gh version 0.0.0-fake (1999-01-01)"


@pytest.mark.usefixtures("fake_bin")
def test_an_empty_path_really_does_hide_the_binary():
    """The ABSENT case is produced by a directory with no gh in it, so this
    asserts that the mechanism works before any case relies on it."""
    assert ghx.which_gh() is None
    result = ghx.gh(["--version"])
    assert result.returncode == ghx.NOT_INSTALLED_RC
    assert result.failure == ghx.FAILURE_NOT_INSTALLED


def test_the_measured_constants_match_the_module():
    """The exit code the module branches on is the one that was measured.

    Pinned as its own case because AUTH_FAILED_RC is the single fact in this module that cannot be derived from anything in the repository: it came from running the real binary, and if it is wrong the misclassification is silent.
    """
    assert ghx.AUTH_FAILED_RC == MEASURED_UNAUTH_RC
    assert ghx.NOT_INSTALLED_RC == proc.SPAWN_FAILED_RC


# --------------------------------------------------------------------------- THE FOUNDING CASE: a failed call is not an empty answer ---------------------------------------------------------------------------


def _assert_failure_is_not_an_empty_answer():
    """A `gh` that could not answer must RAISE, not return an empty list."""
    with pytest.raises(ghx.GhUnauthenticatedError):
        ghx.pr_head_refs(repo="rediacc/console")


def _assert_empty_is_an_empty_answer():
    """A `gh` that answered "nothing here" must return the empty list."""
    assert ghx.pr_head_refs(repo="rediacc/console") == []


def test_a_failed_call_raises_rather_than_answering_empty(fake_bin):
    fake_bin("gh", rc=MEASURED_UNAUTH_RC, stderr=MEASURED_UNAUTH_STDERR)
    _assert_failure_is_not_an_empty_answer()


def test_a_genuinely_empty_list_is_an_empty_list(fake_bin):
    fake_bin("gh", stdout="[]")
    _assert_empty_is_an_empty_answer()


def test_control_planting_the_or_echo_defect_makes_the_failure_case_fail(fake_bin, monkeypatch):
    """THE PLANTED DEFECT. `pr_list` is replaced by exactly the behaviour the
    module refuses -- `gh api ... || echo "[]"` -- and the assertion above must stop holding. Without this control the raise-assertion could be passing for
    some unrelated reason and nobody would know."""
    fake_bin("gh", rc=MEASURED_UNAUTH_RC, stderr=MEASURED_UNAUTH_STDERR)
    monkeypatch.setattr(ghx, "pr_list", lambda **_kwargs: [])
    # `pytest.raises` that sees nothing raised fails with `Failed`, so catching that IS the statement "the assertion above no longer holds".
    with pytest.raises(pytest.fail.Exception):
        _assert_failure_is_not_an_empty_answer()


def test_control_the_empty_case_still_passes_under_the_planted_defect(fake_bin, monkeypatch):
    """The other half of the control, and the reason the defect is dangerous:
    with `|| echo "[]"` planted, the EMPTY case is still green. A suite that only
    tested the empty direction would ship the bug."""
    fake_bin("gh", stdout="[]")
    monkeypatch.setattr(ghx, "pr_list", lambda **_kwargs: [])
    _assert_empty_is_an_empty_answer()


def test_the_stderr_survives_and_names_the_cause(fake_bin):
    """28 call sites send this to /dev/null. It is the only useful thing a
    failed call produces, so it must reach the exception's message."""
    fake_bin("gh", rc=MEASURED_UNAUTH_RC, stderr=MEASURED_UNAUTH_STDERR)
    with pytest.raises(ghx.GhUnauthenticatedError) as caught:
        ghx.pr_head_refs(repo="rediacc/console")
    assert "gh auth login" in str(caught.value)
    assert caught.value.stderr == MEASURED_UNAUTH_STDERR
    assert caught.value.returncode == MEASURED_UNAUTH_RC


# --------------------------------------------------------------------------- TRAP 2, IN BASH: the pipeline that cannot tell the two apart ---------------------------------------------------------------------------

# The advice printed by .claude/rediacc_hooks/guards/block_nonstandard_branch_name.py:230-233, frozen verbatim. This is the thing `branch_indexes` replaces, and the case below runs it rather than describing it.
GUARD_PIPELINE = (
    'gh pr list --state all --limit 100 --json headRefName --jq ".[].headRefName" '
    '| grep "^${d}-" | sed "s/^${d}-//" | sort -n | tail -1'
)


@pytest.fixture
def dual_fake_gh(tmp_path, monkeypatch):
    """A `gh` that answers JSON normally and one-ref-per-line under `--jq`.

    Needed because the guard's pipeline and this module ask the same question
    with different output shapes, and the point of the case is that ONE fake
    answers both -- so the comparison is between the two CONSUMERS, not between two differently-rigged binaries.
    """
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    monkeypatch.setenv("PATH", str(bindir))

    def make(refs: list[str], *, rc: int = 0, stderr: str = "") -> None:
        (tmp_path / "json.out").write_text(_rows(*refs), encoding="utf-8")
        (tmp_path / "jq.out").write_text("".join(r + "\n" for r in refs), encoding="utf-8")
        (tmp_path / "gh.err").write_text(stderr, encoding="utf-8")
        path = bindir / "gh"
        path.write_text(
            "#!" + sys.executable + "\n"
            "import sys\n"
            "which = "
            + repr(str(tmp_path / "jq.out"))
            + " if '--jq' in sys.argv[1:] else "
            + repr(str(tmp_path / "json.out"))
            + "\n"
            "sys.stdout.write(open(which, encoding='utf-8').read())\n"
            "sys.stderr.write(open("
            + repr(str(tmp_path / "gh.err"))
            + ", encoding='utf-8').read())\n"
            "sys.exit(" + str(rc) + ")\n",
            encoding="utf-8",
        )
        path.chmod(0o755)

    make.bindir = bindir
    return make


def _run_guard_pipeline(bindir: pathlib.Path, day: str) -> tuple[int, str, str]:
    return diff.bash_streams(
        "d=%s\n%s\n" % (day, GUARD_PIPELINE),
        env=diff.env_for(PATH="%s:%s" % (bindir, diff.BASE_ENV["PATH"])),
    )


def test_the_guard_pipeline_cannot_tell_an_outage_from_an_empty_day(dual_fake_gh):
    """THE CONTROL FOR THE WHOLE MODULE, and the 2026-08-26 duplicate reproduced.

    The same pipeline is run twice: once against a `gh` that succeeded and had nothing to report, once against a `gh` that failed to authenticate. Both must produce byte-identical output and exit 0, which is why the caller adding one to nothing picked a name that was already taken.
    """
    dual_fake_gh([])
    empty_rc, empty_out, _ = _run_guard_pipeline(dual_fake_gh.bindir, "0826")

    dual_fake_gh([], rc=MEASURED_UNAUTH_RC, stderr=MEASURED_UNAUTH_STDERR)
    failed_rc, failed_out, _ = _run_guard_pipeline(dual_fake_gh.bindir, "0826")

    assert empty_out == failed_out == ""
    assert empty_rc == failed_rc == 0


def test_the_module_tells_them_apart_on_the_same_fake(dual_fake_gh):
    """The other direction, on the same binary the pipeline could not read."""
    dual_fake_gh([])
    assert ghx.branch_indexes("0826", repo="rediacc/console") == set()
    assert ghx.next_branch_name("0826", repo="rediacc/console") == "0826-1"

    dual_fake_gh([], rc=MEASURED_UNAUTH_RC, stderr=MEASURED_UNAUTH_STDERR)
    with pytest.raises(ghx.GhUnauthenticatedError):
        ghx.branch_indexes("0826", repo="rediacc/console")
    with pytest.raises(ghx.GhUnauthenticatedError):
        ghx.next_branch_name("0826", repo="rediacc/console")


def test_the_next_branch_name_is_one_past_the_highest_used(fake_bin):
    fake_bin("gh", stdout=_rows("0826-1", "0826-2", "0825-9", "main"))
    assert ghx.branch_indexes("0826", repo="r/c") == {1, 2}
    assert ghx.next_branch_name("0826", repo="r/c") == "0826-3"
    assert ghx.branch_indexes("0825", repo="r/c") == {9}


def test_a_suffixed_ref_is_not_read_as_an_index(fake_bin):
    """`0826-1-fixup` is somebody else's mistake and must not collapse onto 1.

    A prefix match would report {1} for a day whose only ref is the suffixed one,
    and `next_branch_name` would then hand back 0826-2 while 0826-1 is free -- which is the same class of wrong answer, in the harmless direction today and the harmful one as soon as the numbers line up differently.
    """
    fake_bin("gh", stdout=_rows("0826-1-fixup", "0826-2x", "0826-03"))
    # "0826-03" IS all digits and is index 3; the two non-numeric tails are not.
    assert ghx.branch_indexes("0826", repo="r/c") == {3}


def test_the_day_argument_is_validated(fake_bin):
    """Passing a BRANCH where a DAY belongs must not answer "nothing today"."""
    fake_bin("gh", stdout=_rows("0826-1"))
    for bad in ("0826-1", "826", "08261", "", "abcd"):
        with pytest.raises(ValueError, match="MMDD"):
            ghx.branch_indexes(bad, repo="r/c")


# --------------------------------------------------------------------------- .stdout is the check that cannot be skipped ---------------------------------------------------------------------------


def test_stdout_raises_on_a_failed_call_and_stdout_raw_does_not():
    result = ghx.GhResult(["gh", "x"], 1, "partial output", "boom")
    with pytest.raises(ghx.GhError):
        _ = result.stdout
    assert result.stdout_raw == "partial output"
    assert result.stderr == "boom"
    assert bool(result) is False


def test_every_accessor_routes_through_the_raising_property():
    """A second path to the bytes would be a second place to forget the check.

    Set-based rather than a list of method names typed by hand: every public zero-argument accessor on GhResult is called, and each one must refuse.
    """
    result = ghx.GhResult(["gh", "x"], 1, "[]", "boom")
    # Derived, not typed: everything public that is neither a stored field nor one of the three deliberate non-output accessors. A new output accessor added later joins this set automatically and must obey the same rule.
    accessors = {
        name
        for name in dir(ghx.GhResult)
        if not name.startswith("_")
        and name not in set(ghx.GhResult.__slots__)
        and name not in {"ok", "failure", "error"}
    }
    assert accessors == {"stdout", "lines", "value", "json", "json_list"}
    for name in sorted(accessors):
        attribute = getattr(ghx.GhResult, name)
        with pytest.raises(ghx.GhError):
            _ = getattr(result, name)() if callable(attribute) else getattr(result, name)


def test_error_refuses_to_describe_a_success():
    result = ghx.GhResult(["gh", "x"], 0, "fine", "")
    assert result.failure is None
    with pytest.raises(ValueError, match="successful"):
        result.error()


# --------------------------------------------------------------------------- Classification ---------------------------------------------------------------------------


def _classify_case(rc: int, stderr: str) -> str | None:
    return ghx.GhResult(["gh", "x"], rc, "", stderr).failure


def test_the_classification_table():
    cases = {
        (0, ""): None,
        (MEASURED_UNAUTH_RC, MEASURED_UNAUTH_STDERR): ghx.FAILURE_UNAUTHENTICATED,
        (MEASURED_AUTH_STATUS_RC, MEASURED_AUTH_STATUS_STDERR): ghx.FAILURE_UNAUTHENTICATED,
        (1, "HTTP 401: Bad credentials\n"): ghx.FAILURE_UNAUTHENTICATED,
        (1, RATE_LIMIT_STDERR): ghx.FAILURE_RATE_LIMITED,
        (MEASURED_UNKNOWN_VERB_RC, MEASURED_UNKNOWN_VERB_STDERR): ghx.FAILURE_FAILED,
        (proc.SPAWN_FAILED_RC, "no such file"): ghx.FAILURE_NOT_INSTALLED,
    }
    got = {key: _classify_case(*key) for key in cases}
    assert got == cases


def _assert_rate_limit_wins_over_auth():
    """A 403 body that ALSO says "gh auth login" is a rate limit, not a token problem."""
    assert _classify_case(1, RATE_LIMIT_STDERR) == ghx.FAILURE_RATE_LIMITED


def test_rate_limit_is_classified_before_authentication():
    _assert_rate_limit_wins_over_auth()


def test_control_removing_the_rate_limit_markers_breaks_the_ordering(monkeypatch):
    """PLANTED DEFECT: with the rate-limit markers gone, the same body is read as
    an authentication failure, and the assertion above must fail. This is what
    makes the ordering comment in `_classify` load bearing rather than decorative."""
    monkeypatch.setattr(ghx, "_RATE_LIMIT_MARKERS", ())
    with pytest.raises(AssertionError):
        _assert_rate_limit_wins_over_auth()
    assert _classify_case(1, RATE_LIMIT_STDERR) == ghx.FAILURE_UNAUTHENTICATED


def test_a_timeout_is_its_own_classification():
    result = ghx.GhResult(["gh", "x"], proc.TIMEOUT_RC, "", "", timed_out=True)
    assert result.failure == ghx.FAILURE_TIMED_OUT


def test_every_classification_has_an_error_class():
    """Set-based: no failure string may fall through to a bare GhError silently.

    FAILURE_FAILED and FAILURE_TIMED_OUT deliberately map to the base class, and naming them here is what makes that a decision rather than an omission.
    """
    all_failures = {
        ghx.FAILURE_NOT_INSTALLED,
        ghx.FAILURE_UNAUTHENTICATED,
        ghx.FAILURE_RATE_LIMITED,
        ghx.FAILURE_TIMED_OUT,
        ghx.FAILURE_FAILED,
    }
    assert set(ghx._ERROR_CLASSES) < all_failures
    assert all_failures - set(ghx._ERROR_CLASSES) == {ghx.FAILURE_TIMED_OUT, ghx.FAILURE_FAILED}
    for failure, cls in ghx._ERROR_CLASSES.items():
        assert issubclass(cls, ghx.GhError), failure


def test_auth_state_is_tri_state(fake_bin):
    fake_bin("gh", stdout="Logged in to github.com as someone\n")
    assert ghx.auth_state() == ghx.AUTH_AUTHENTICATED

    fake_bin("gh", rc=MEASURED_AUTH_STATUS_RC, stderr=MEASURED_AUTH_STATUS_STDERR)
    assert ghx.auth_state() == ghx.AUTH_UNAUTHENTICATED

    fake_bin("gh", rc=1, stderr="something nobody has seen before\n")
    assert ghx.auth_state() == ghx.AUTH_UNKNOWN


@pytest.mark.usefixtures("fake_bin")
def test_auth_state_says_unknown_rather_than_unauthenticated_when_gh_is_absent():
    """The distinction that stops a message telling a human to log in when the
    real problem is that gh was never installed."""
    assert ghx.which_gh() is None
    assert ghx.auth_state() == ghx.AUTH_UNKNOWN


# --------------------------------------------------------------------------- TRAP 3: exit 0 is not a promise about the body ---------------------------------------------------------------------------


def test_an_html_body_is_refused_rather_than_parsed(fake_bin):
    """The invalid_signature shape: a 404's HTML arriving where a value belongs."""
    fake_bin("gh", stdout=HTML_BODY)
    with pytest.raises(ghx.GhBadOutputError, match="not JSON"):
        ghx.api_json("repos/x/y")


def test_control_the_naive_spelling_accepts_the_html_body(fake_bin):
    """The other direction: `result.stdout_raw` is exactly what an unchecked
    caller would have used, and it hands back the HTML without complaint. The
    module's refusal is only meaningful because this is what it refuses."""
    fake_bin("gh", stdout=HTML_BODY)
    result = ghx.gh(["api", "repos/x/y"])
    assert result.stdout_raw == HTML_BODY
    assert result.ok is True


def test_an_error_object_is_not_iterated_as_a_list(fake_bin):
    fake_bin("gh", stdout=NOT_FOUND_BODY)
    with pytest.raises(ghx.GhBadOutputError, match="expected a JSON array"):
        ghx.pr_list(repo="r/c")


def test_control_the_naive_spelling_iterates_the_error_objects_keys(fake_bin):
    """What `for row in result.json()` would have produced: one "finding" named
    after the error message. Asserted so the refusal above is anchored to a real
    wrong answer rather than to a hypothetical one."""
    fake_bin("gh", stdout=NOT_FOUND_BODY)
    parsed = ghx.gh(["api", "x"]).json()
    assert list(parsed) == ["message", "documentation_url"]


def test_an_empty_value_is_refused_where_a_scalar_is_required(fake_bin):
    fake_bin("gh", stdout="   \n")
    result = ghx.gh(["api", "x", "--jq", ".sha"])
    assert result.ok is True
    with pytest.raises(ghx.GhBadOutputError, match="ACCOUNT_ED25519_PUBLIC_KEY"):
        result.value("commit sha")


def test_control_the_naive_strip_yields_the_empty_string(fake_bin):
    """The exact assignment that put an empty signing key into a production
    build. `curl -f` on the dead endpoint did this; so does `.strip()` here."""
    fake_bin("gh", stdout="   \n")
    assert ghx.gh(["api", "x"]).stdout_raw.strip() == ""


def test_lines_distinguishes_nothing_from_could_not_ask(fake_bin):
    fake_bin("gh", stdout="\n\n")
    assert ghx.gh(["x"]).lines() == []
    fake_bin("gh", rc=1, stderr="boom\n")
    with pytest.raises(ghx.GhError):
        ghx.gh(["x"]).lines()


# --------------------------------------------------------------------------- Secrets are write-only ---------------------------------------------------------------------------


def test_secret_value_always_raises_and_says_why():
    """A corpus of names rather than one, so the refusal cannot be name-specific."""
    for name in ("ACCOUNT_ED25519_PUBLIC_KEY", "CLOUDFLARE_R2_ACCESS_KEY_ID", "X", ""):
        with pytest.raises(ghx.SecretValueUnavailableError) as caught:
            ghx.secret_value(name)
        message = str(caught.value)
        assert "WRITE-ONLY" in message
        assert "invalid_signature" in message


def test_there_is_no_other_way_to_ask_for_a_secret_value():
    """Set-based: the module's public surface offers names, and no getter.

    Derived from `__all__` rather than typed out, so a future function called `read_secret` or `get_secret_value` fails this the day it is added.
    """
    # Exception CLASSES are excluded by shape, not by name: SecretValueUnavailableError is part of the refusal, not a way around it. Anything else callable whose name mentions a secret is a getter until proven otherwise.
    getters = set()
    for name in ghx.__all__:
        if "secret" not in name.lower() or name in {"secret_names", "secret_value"}:
            continue
        obj = getattr(ghx, name)
        if isinstance(obj, type) and issubclass(obj, BaseException):
            continue
        getters.add(name)
    assert getters == set()
    assert "secret_names" in ghx.__all__


def test_secret_names_parses_the_listing_and_sorts_it(fake_bin):
    fake_bin(
        "gh",
        stdout=("ZULU_TOKEN\t2026-01-02T00:00:00Z\tall\nALPHA_KEY\t2026-01-01T00:00:00Z\tall\n\n"),
    )
    assert ghx.secret_names(org="rediacc") == ["ALPHA_KEY", "ZULU_TOKEN"]


def test_secret_names_raises_when_the_listing_could_not_be_read(fake_bin):
    fake_bin("gh", rc=MEASURED_UNAUTH_RC, stderr=MEASURED_UNAUTH_STDERR)
    with pytest.raises(ghx.GhUnauthenticatedError):
        ghx.secret_names(org="rediacc")


def test_secret_names_needs_exactly_one_scope():
    for kwargs in ({}, {"org": "a", "repo": "b"}):
        with pytest.raises(ValueError, match="exactly one"):
            ghx.secret_names(**kwargs)


# --------------------------------------------------------------------------- The call itself ---------------------------------------------------------------------------


def test_the_noninteractive_environment_reaches_the_child(argv_recorder):
    _log, env_log = argv_recorder
    ghx.gh(["pr", "list"])
    seen = dict(
        line.split("=", 1)
        for line in env_log.read_text(encoding="utf-8").splitlines()
        if "=" in line
    )
    assert {k: seen.get(k) for k in ghx.NONINTERACTIVE} == ghx.NONINTERACTIVE


def test_the_repo_flag_is_appended_rather_than_inferred(argv_recorder):
    log, _env = argv_recorder
    ghx.gh(["pr", "list"], repo="rediacc/console")
    assert log.read_text(encoding="utf-8").split() == [
        "pr",
        "list",
        "--repo",
        "rediacc/console",
    ]


def test_api_json_refuses_paginate_with_jq():
    with pytest.raises(ValueError, match="value stream"):
        ghx.api_json("repos/x/y/labels", paginate=True, jq=".[].name")


def test_pr_list_refuses_an_empty_field_set():
    with pytest.raises(ValueError, match="at least one"):
        ghx.pr_list(repo="r/c", fields=())


def test_retries_follow_the_documented_backoff_and_keep_the_last_failure(fake_bin):
    """`attempts=3` reproduces common.sh:_gh_probe, and the schedule is asserted
    against `proc.backoff_delays` rather than against numbers typed here."""
    fake_bin("gh", rc=MEASURED_UNAUTH_RC, stderr=MEASURED_UNAUTH_STDERR)
    slept: list[float] = []
    result = ghx.gh(["pr", "list"], attempts=3, sleep=slept.append)
    assert slept == proc.backoff_delays(3)
    assert result.failure == ghx.FAILURE_UNAUTHENTICATED


def test_one_attempt_is_the_default(fake_bin):
    fake_bin("gh", rc=1, stderr="boom\n")
    slept: list[float] = []
    ghx.gh(["pr", "list"], sleep=slept.append)
    assert slept == []


# --------------------------------------------------------------------------- The argv dispatcher, driven as a real process with the streams kept apart ---------------------------------------------------------------------------


def _module_run(bindir: pathlib.Path, args: list[str]) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    # ONLY the fake directory, so nothing can reach the real gh through the tail of a PATH. The interpreter is an absolute path and `paths.repo_root()` is derived from the package location, so the child needs nothing else.
    env["PATH"] = str(bindir)
    env["PYTHONPATH"] = str(paths.repo_root() / ".ci")
    return subprocess.run(
        [sys.executable, "-m", "rediacc_ci.core.ghx", *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(paths.repo_root()),
        env=env,
        timeout=60,
    )


def test_the_dispatcher_prints_a_name_on_stdout_and_exits_zero(fake_bin):
    fake_bin("gh", stdout=_rows("0826-1", "0826-2"))
    done = _module_run(fake_bin.bindir, ["next-branch-name", "0826", "rediacc/console"])
    assert done.returncode == 0
    assert done.stdout == "0826-3\n"
    assert done.stderr == ""


def test_the_dispatcher_puts_the_reason_on_stderr_and_nothing_on_stdout(fake_bin):
    """THE CONTRACT `name="$(...)" || handle-it` DEPENDS ON. A failure must not
    put a plausible name on stdout, and must not exit 0."""
    fake_bin("gh", rc=MEASURED_UNAUTH_RC, stderr=MEASURED_UNAUTH_STDERR)
    done = _module_run(fake_bin.bindir, ["next-branch-name", "0826", "rediacc/console"])
    assert done.returncode != 0
    assert done.stdout == ""
    assert "gh auth login" in done.stderr


def test_the_dispatcher_rejects_an_unknown_verb_with_usage_not_failure(fake_bin):
    fake_bin("gh", stdout="[]")
    done = _module_run(fake_bin.bindir, ["frobnicate"])
    assert done.returncode == 2
    assert done.stdout == ""
    assert "unknown verb" in done.stderr


def test_the_dispatcher_reports_a_bad_day_as_usage(fake_bin):
    fake_bin("gh", stdout="[]")
    done = _module_run(fake_bin.bindir, ["next-branch-name", "0826-1"])
    assert done.returncode == 2
    assert done.stdout == ""
    assert "MMDD" in done.stderr


# --------------------------------------------------------------------------- The module's own hygiene ---------------------------------------------------------------------------


def test_all_names_in_dunder_all_exist():
    missing = {name for name in ghx.__all__ if not hasattr(ghx, name)}
    assert missing == set()


def test_no_em_dashes_in_the_module_or_this_file():
    """House rule for this workstream, checked on the artefacts rather than
    trusted to the author."""
    # chr(8212) rather than the literal character, or this file would fail its own check the moment it was written.
    em_dash = chr(8212)
    for path in (
        paths.repo_root() / ".ci/rediacc_ci/core/ghx.py",
        pathlib.Path(__file__),
    ):
        text = path.read_text(encoding="utf-8")
        assert em_dash not in text, path


def test_the_module_documents_every_incident_it_claims_to_close():
    """Corpus-derived: the file:line references in the docstring must resolve.

    A docstring that cites `common.sh:392-397` is making a checkable claim, and an unchecked citation rots into a confident lie the moment a file moves. Only the path is verified here, not the line contents: pinning contents would make an unrelated edit to those files red this suite.
    """
    text = (paths.repo_root() / ".ci/rediacc_ci/core/ghx.py").read_text(encoding="utf-8")
    cited = {
        match.group(1)
        for match in re.finditer(
            r"`?((?:\.ci|scripts|docs|\.claude)/[\w./-]+\.(?:sh|py|ts|md))", text
        )
    }
    assert cited, "the docstring cites no files at all, so this check is vacuous"
    missing = {rel for rel in cited if not (paths.repo_root() / rel).exists()}
    assert missing == set()

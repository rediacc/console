"""Differential: `rediacc_ci.review.review_status` against its twin
`.ci/scripts/review/review-status.sh`.

THIS SCRIPT WRITES TO GITHUB, so the fake `gh` is not a convenience. Its
success path POSTs or PATCHes a check-run against whatever repository and SHA
the environment names, and a required check-run posted on a real head is a
merge decision. Three independent things keep the real binary out of reach:

  1. the stub directory is FIRST on PATH and `shutil.which("gh", path=...)` is
     asserted to resolve to the fake, in `test_the_fake_gh_is_the_gh`;
  2. every case names a repository that does not exist (`acme/widget`);
  3. `GH_TOKEN` is a fixture string and `GH_CONFIG_DIR` points into the temp
     tree, so a leaked real `gh` would fail auth instead of writing.

THE ROUTING FAKE APPLIES THE CALLER'S OWN `--jq`, which is the design the bash
gate test `.ci/scripts/test/gates/test-review-status.sh:57` already uses and the
reason this file can compare two implementations that ask for the same data
DIFFERENTLY. The twin filters server-side (`gh api ... --jq '.[] | select(...)'`)
while `core.review_budget` fetches the page and filters in Python; the fake
serves the same fixture to both and runs real jq when asked, so the ANSWERS are
comparable even though the command lines are not.

WHAT IS COMPARED, ON EVERY CASE:
  * exit code, stdout and stderr, byte for byte;
  * the NORMALISED call log -- `<method>\\t<path>`, in order -- which catches a
    dropped read, a reordered one, or a write that never happened;
  * the RAW argv of every call this file makes itself. The two budget endpoints
    (`*/issues/*/comments` and `pr view`) are excluded from the raw comparison
    and ONLY from it, because that difference is the documented one above;
  * the check-run PAYLOAD BYTES, which are the product. A stdout-only
    comparison would be satisfied by a port that logged the right sentence and
    posted the wrong conclusion.

BOTH DEADLOCK ARMS ARE DRIVEN, and they are the reason this file is long:
`test_a_capped_pr_passes_with_a_warning_rather_than_becoming_unmergeable` and
`test_an_exhausted_head_passes_with_a_warning_too`. `common.sh:623-632` records
what the missing guard cost on PR #553.

K=5 LEDGER: `.ci/shadow/w7p6-review-status.observations.jsonl`, recorded in a
disposable scratch git repository outside this checkout.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

from rediacc_ci import paths
from rediacc_ci.review import review_status as rs

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "review" / "review-status.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "review" / "review_status.py"
REAL_GATE = ROOT / ".ci" / "scripts" / "review" / "claude-review-gate.sh"
BASH = shutil.which("bash") or "/bin/bash"

REPO = "acme/widget"
OLD_SHA = "1" * 40
NEW_SHA = "2" * 40

FAKE_GH = r'''#!/usr/bin/python3
"""Routing fake for `gh`. Serves fixture JSON per endpoint and applies the
caller's own --jq to it with the real jq. Non-GET calls are captured, never
served."""
import io
import os
import subprocess
import sys
import zipfile

argv = sys.argv[1:]
method = "GET"
explicit = False
has_field = False
path = ""
jqexpr = None
read_stdin = False

i = 0
while i < len(argv):
    a = argv[i]
    if a == "api":
        pass
    elif a in ("-X", "--method"):
        i += 1
        method = argv[i]
        explicit = True
    elif a == "--jq":
        i += 1
        jqexpr = argv[i]
    elif a in ("--input", "-f", "-F", "--field", "--raw-field"):
        i += 1
        has_field = True
        if a == "--input":
            read_stdin = True
    elif a in ("--paginate", "--silent"):
        pass
    elif a.startswith("-"):
        pass
    elif not path:
        path = a
    i += 1

if not explicit and has_field:
    method = "POST"

with open(os.environ["RAW_LOG"], "a") as fh:
    fh.write("\t".join(argv).replace("\n", "\\n") + "\n")
with open(os.environ["FAKE_LOG"], "a") as fh:
    fh.write("%s\t%s\n" % (method, path))

if method != "GET":
    body = sys.stdin.buffer.read() if read_stdin else b""
    with open(os.environ["GH_CAPTURE"], "ab") as fh:
        fh.write(("METHOD=%s PATH=%s\n" % (method, path)).encode())
        fh.write(body)
        fh.write(b"\n")
    sys.stdout.write('{"id": 999}\n')
    sys.exit(0)

fixtures = os.environ["GH_FIXTURES"]
parts = path.split("/")
if path == "pr":
    key = "pr-size"
elif "/actions/runs/" in path and path.endswith("/artifacts"):
    key = "run-artifacts"
elif "/actions/artifacts/" in path and path.endswith("/zip"):
    target = os.path.join(fixtures, "review-target.txt")
    if not os.path.exists(target):
        sys.exit(1)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.write(target, "review-target.txt")
    sys.stdout.buffer.write(buf.getvalue())
    sys.exit(0)
elif path.endswith("/check-runs"):
    key = "check-runs"
elif path.endswith("/comments"):
    key = "comments"
elif "/compare/" in path:
    key = "compare"
elif "/pulls/" in path:
    key = "pull"
else:
    sys.stderr.write("fake gh: unrouted path: %s\n" % path)
    sys.exit(3)

fixture = os.path.join(fixtures, key + ".json")
if not os.path.exists(fixture):
    sys.stderr.write("fake gh: missing fixture %s\n" % fixture)
    sys.exit(4)
if os.environ.get("FAKE_GH_FAIL_ON", "") and os.environ["FAKE_GH_FAIL_ON"] in path:
    sys.stderr.write("fake gh: fixture refuses %s\n" % path)
    sys.exit(1)
if jqexpr:
    sys.exit(subprocess.run(["jq", "-r", jqexpr, fixture], check=False).returncode)
with open(fixture, "rb") as fh:
    sys.stdout.buffer.write(fh.read())
'''

HYGIENE_STUB = """#!/bin/bash
echo "stub %s for PR ${PR_NUMBER:-?}"
exit %d
"""

GITMODULES = """[submodule "private/renet"]
\tpath = private/renet
\turl = git@github.com:rediacc/renet.git
[submodule "private/account"]
\tpath = private/account
\turl = git@github.com:rediacc/account.git
"""

# The endpoints the two sides legitimately ask for differently. See the module
# docstring; this list is the ONLY place the raw-argv comparison is relaxed.
BUDGET_ENDPOINTS = ("/issues/", "pr")


def _marker(sha: str) -> dict:
    return {
        "id": 1,
        "user": {"login": "github-actions[bot]"},
        "body": "<!-- claude-reviewed: %s -->\nAutomated Claude review completed." % sha,
    }


def _report(index: int) -> dict:
    return {
        "id": 100 + index,
        "user": {"login": "github-actions[bot]"},
        "body": "**Claude finished** the review.\n### Review\nlooks fine",
    }


def _attempt(sha: str, attempts: int = 1, cls: str = "") -> dict:
    body = "<!-- claude-review-attempt: %s -->" % sha
    if attempts:
        body += "\nattempts: %d" % attempts
    if cls:
        body += "\nclass: %s" % cls
    return {"id": 200 + attempts, "user": {"login": "github-actions[bot]"}, "body": body}


class World:
    """The fixture set, as the bash gate test's `setup` builds it."""

    def __init__(self, base: pathlib.Path) -> None:
        self.base = base
        self.fixtures = base / "fixtures"
        self.fixtures.mkdir(parents=True, exist_ok=True)
        (base / ".gitmodules").write_text(GITMODULES, encoding="utf-8")
        self.write("pull", {"state": "open", "draft": False, "head": {"sha": NEW_SHA}})
        self.write("comments", [_marker(NEW_SHA)])
        self.compare()
        self.write("check-runs", {"check_runs": []})
        self.write("pr-size", {"additions": 100, "deletions": 40})
        self.write("run-artifacts", {"artifacts": []})
        self.hygiene(0, 0, 0)

    def write(self, key: str, value) -> None:
        (self.fixtures / ("%s.json" % key)).write_text(json.dumps(value), encoding="utf-8")

    def compare(self, *filenames: str) -> None:
        """The compare fixture in the API's own shape.

        `--jq '[.files[]?.filename]'` is applied to it by the fake, so a
        fixture shaped as a bare list makes jq fail and every case silently
        exercises the compare-failed arm instead of the one it names. That
        happened once while this file was being written, which is why this
        helper exists rather than a raw `write("compare", [...])`.
        """
        self.write("compare", {"files": [{"filename": name} for name in filenames]})

    def hygiene(self, *codes: int) -> None:
        directory = self.base / "hygiene"
        directory.mkdir(exist_ok=True)
        for name, code in zip(rs.HYGIENE_SCRIPTS, codes, strict=True):
            script = directory / name
            script.write_text(HYGIENE_STUB % (name, code), encoding="utf-8")
            script.chmod(0o755)


def _stub_bin(base: pathlib.Path) -> str:
    stub = base / "bin"
    stub.mkdir(exist_ok=True)
    fake = stub / "gh"
    fake.write_text(FAKE_GH, encoding="utf-8")
    fake.chmod(0o755)
    return "%s:%s" % (stub, os.environ.get("PATH", "/usr/bin:/bin"))


class Side:
    __slots__ = ("calls", "capture", "exit", "raw", "stderr", "stdout")

    def __init__(self, code, stdout, stderr, calls, raw, capture) -> None:
        self.exit = code
        self.stdout = stdout
        self.stderr = stderr
        self.calls = calls
        self.raw = raw
        self.capture = capture

    def payload(self) -> dict | None:
        """The last captured write's JSON body."""
        if not self.capture:
            return None
        chunk = self.capture.decode("utf-8", "replace").split("METHOD=")[-1]
        body = chunk.split("\n", 1)[1].strip()
        return json.loads(body) if body else None

    def methods(self) -> list[str]:
        return [line.split("\t")[0] for line in self.calls]


def _run(world: World, which: str, env_extra: dict[str, str], *, path: str | None = None) -> Side:
    base = world.base
    log = base / ("calls-%s.log" % which)
    raw = base / ("raw-%s.log" % which)
    capture = base / ("capture-%s.txt" % which)
    for artefact in (log, raw, capture):
        artefact.write_bytes(b"")

    env = {
        "PATH": path if path is not None else _stub_bin(base),
        "HOME": str(base),
        "LC_ALL": "C",
        "LANG": "C",
        "NO_COLOR": "1",
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "GH_FIXTURES": str(world.fixtures),
        "GH_CAPTURE": str(capture),
        "FAKE_LOG": str(log),
        "RAW_LOG": str(raw),
        # A leaked real gh would fail auth rather than write anything.
        "GH_TOKEN": "not-a-real-token",
        "GH_CONFIG_DIR": str(base / "gh-config"),
        "GITHUB_REPOSITORY": REPO,
        "REVIEW_STATUS_HYGIENE_DIR": str(base / "hygiene"),
        "REVIEW_STATUS_GATE_SCRIPT": str(REAL_GATE),
    }
    env.update(env_extra)
    for key in [k for k, v in env.items() if v is None]:
        del env[key]
    # `{base}` in a fixture value is the case directory, which is only known
    # here: `_sides` builds the world after the caller has written its env.
    env = {k: v.replace("{base}", str(base)) for k, v in env.items()}

    argv = [BASH, str(TWIN)] if which == "old" else [sys.executable, str(PORT)]
    proc = subprocess.run(
        argv, capture_output=True, env=env, check=False, cwd=str(base), timeout=180
    )
    return Side(
        proc.returncode,
        proc.stdout,
        proc.stderr,
        log.read_text(encoding="utf-8").splitlines(),
        raw.read_text(encoding="utf-8").splitlines(),
        capture.read_bytes(),
    )


def _raw_own(lines: list[str]) -> list[str]:
    """The raw argv of the calls this file makes ITSELF, budget reads dropped."""
    kept = []
    for line in lines:
        fields = line.split("\t")
        if fields and fields[0] == "pr":
            continue
        if any("/issues/" in f for f in fields):
            continue
        kept.append(line)
    return kept


def _sides(name: str, env_extra: dict[str, str] | None = None, *, build=None, path=None):
    """Both implementations over one fixture world, in sequence."""
    with tempfile.TemporaryDirectory() as td:
        world = World(pathlib.Path(td))
        if build is not None:
            build(world)
        results = [_run(world, which, dict(env_extra or {}), path=path) for which in ("old", "new")]
    old, new = results
    for label, left, right in (
        ("exit", old.exit, new.exit),
        ("stdout", old.stdout, new.stdout),
        ("stderr", old.stderr, new.stderr),
        ("call log", old.calls, new.calls),
        ("own argv", _raw_own(old.raw), _raw_own(new.raw)),
        ("write capture", old.capture, new.capture),
    ):
        assert right == left, "%s: %s diverged:\n twin: %r\n port: %r" % (name, label, left, right)
    return old


BASE_ENV = {"EVENT_NAME": "issue_comment", "PR_NUMBER": "42"}


# --------------------------------------------------------------------------- Controls. ---------------------------------------------------------------------------


def test_all_three_files_exist_where_this_file_says_they_do() -> None:
    for path in (TWIN, PORT, REAL_GATE):
        assert path.is_file(), path


def test_the_twin_parses_under_bash() -> None:
    proc = subprocess.run([BASH, "-n", str(TWIN)], capture_output=True, check=False)
    assert proc.returncode == 0, proc.stderr


def test_the_fake_gh_is_the_gh() -> None:
    with tempfile.TemporaryDirectory() as td:
        base = pathlib.Path(td)
        path = _stub_bin(base)
        assert shutil.which("gh", path=path) == str(base / "bin" / "gh")


def test_the_real_gate_still_carries_both_prefixes() -> None:
    """ANTI-VACUITY. Every case below points `REVIEW_STATUS_GATE_SCRIPT` at the
    REAL gate script, so if either assignment is ever reworded this suite would
    exercise the parse-failure arm and nothing else."""
    text = REAL_GATE.read_text(encoding="utf-8")
    assert rs.parse_prefix(text, "MARKER_PREFIX") == "<!-- claude-reviewed:"
    assert rs.parse_prefix(text, "ATTEMPT_PREFIX") == "<!-- claude-review-attempt:"


# --------------------------------------------------------------------------- The two extraction helpers, driven against the programs they replace. ---------------------------------------------------------------------------


def _sed_prefix(text: str, name: str) -> str:
    with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as handle:
        handle.write(text)
        temp = handle.name
    try:
        out = subprocess.run(
            [
                BASH,
                "-c",
                'v="$(sed -n "s/^%s=\'\\(.*\\)\'[[:space:]]*$/\\1/p" "$1")"; '
                "printf '%%s' \"${v%%%%$'\\n'*}\"" % name,
                "bash",
                temp,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    finally:
        os.unlink(temp)
    return out.stdout


def test_parse_prefix_agrees_with_the_twins_sed() -> None:
    for text in (
        "MARKER_PREFIX='<!-- claude-reviewed:'\n",
        "MARKER_PREFIX='<!-- claude-reviewed:'   \n",
        "  MARKER_PREFIX='indented'\n",
        "MARKER_PREFIX='first'\nMARKER_PREFIX='second'\n",
        "MARKER_PREFIX='a' 'b'\n",
        "MARKER_PREFIX=unquoted\n",
        "# MARKER_PREFIX='commented'\n",
        "",
    ):
        assert rs.parse_prefix(text, "MARKER_PREFIX") == _sed_prefix(text, "MARKER_PREFIX"), text


def _jq_non_gitlink(files: list[str], subs: list[str]) -> int:
    """The twin's own two-stage jq, run by the real jq."""
    subs_json = subprocess.run(
        [
            BASH,
            "-c",
            'printf "%s\\n" "$1" | jq -R . | jq -s "[.[] | select(length > 0)]"',
            "bash",
            "\n".join(subs),
        ],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    out = subprocess.run(
        [
            "jq",
            "-r",
            "--argjson",
            "subs",
            subs_json,
            "[.[] | select(. as $f | $subs | index($f) | not)] | length",
        ],
        input=json.dumps(files),
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    return int(out.strip())


def test_non_gitlink_count_agrees_with_the_twins_jq() -> None:
    subs = ["private/renet", "private/account"]
    for files in (
        ["private/renet"],
        ["private/account"],
        ["private/renet", "private/account"],
        ["src/main.ts"],
        ["private/renet", "src/main.ts"],
        [],
        ["private/renet/inner.txt"],
    ):
        assert rs.non_gitlink_count(files, subs) == _jq_non_gitlink(files, subs), files


def test_the_first_submodule_is_not_special_cased_away() -> None:
    """jq's `index` answers 0 for the FIRST element and `0 | not` is FALSE, so
    the first submodule counts as a gitlink like every other. A hand-rolled
    truthiness test is where a reimplementation of this filter goes wrong."""
    assert rs.non_gitlink_count(["private/renet"], ["private/renet", "private/account"]) == 0


# --------------------------------------------------------------------------- Refusals, before any network. ---------------------------------------------------------------------------


def test_a_missing_jq_is_refused_by_name() -> None:
    with tempfile.TemporaryDirectory() as td:
        base = pathlib.Path(td)
        world = World(base)
        stub = base / "bin"
        _stub_bin(base)
        for name in ("dirname", "uname", "python3", "git", "sed"):
            real = shutil.which(name)
            assert real is not None, name
            (stub / name).symlink_to(real)
        results = [_run(world, which, dict(BASE_ENV), path=str(stub)) for which in ("old", "new")]
    old, new = results
    assert old.exit == new.exit == 1
    assert old.stderr == new.stderr
    assert b"Required command 'jq' is not available" in old.stderr
    assert old.calls == new.calls == []


def test_a_missing_repository_variable_is_refused() -> None:
    old = _sides("no-repo", {**BASE_ENV, "GITHUB_REPOSITORY": None})
    assert old.exit == 1
    assert b"Required environment variable 'GITHUB_REPOSITORY' is not set" in old.stderr
    assert old.calls == []


def test_an_unsupported_event_is_refused_by_name() -> None:
    old = _sides("bad-event", {"EVENT_NAME": "push", "PR_NUMBER": "42"})
    assert old.exit == 1
    assert b"Unsupported EVENT_NAME: push" in old.stderr
    assert old.calls == []


def test_no_event_at_all_is_reported_as_unset() -> None:
    old = _sides("no-event", {"EVENT_NAME": None, "PR_NUMBER": "42"})
    assert old.exit == 1
    assert b"Unsupported EVENT_NAME: unset" in old.stderr


def test_a_missing_gate_script_is_fatal() -> None:
    old = _sides(
        "no-gate", {**BASE_ENV, "REVIEW_STATUS_GATE_SCRIPT": "/nonexistent/claude-review-gate.sh"}
    )
    assert old.exit == 1
    assert b"cannot read review constants: /nonexistent/claude-review-gate.sh does not exist" in (
        old.stderr
    )
    assert old.calls == []


def test_an_unparseable_marker_prefix_names_the_fix() -> None:
    def build(world: World) -> None:
        (world.base / "gate.sh").write_text(
            "ATTEMPT_PREFIX='<!-- claude-review-attempt:'\n", encoding="utf-8"
        )

    old = _sides(
        "no-marker",
        {**BASE_ENV, "REVIEW_STATUS_GATE_SCRIPT": "{base}/gate.sh"},
        build=build,
    )
    assert old.exit == 1
    assert b"could not parse MARKER_PREFIX out of" in old.stderr
    assert b"keep it as a plain top-level assignment there" in old.stderr
    assert old.stderr.count(b"\n") == 2, old.stderr
    assert old.calls == []


def test_an_unparseable_attempt_prefix_names_the_553_failure_mode() -> None:
    """FOUR lines, and the last two are the point: without the attempt prefix
    the cap reads LOWER here than in the gate, and the deadlock guard cannot
    fire on a capped PR."""

    def build(world: World) -> None:
        (world.base / "gate.sh").write_text(
            "MARKER_PREFIX='<!-- claude-reviewed:'\n", encoding="utf-8"
        )

    old = _sides(
        "no-attempt",
        {**BASE_ENV, "REVIEW_STATUS_GATE_SCRIPT": "{base}/gate.sh"},
        build=build,
    )
    assert old.exit == 1
    assert b"could not parse ATTEMPT_PREFIX out of" in old.stderr
    assert b"the #553 failure mode" in old.stderr
    assert old.stderr.count(b"\n") == 4, old.stderr


# --------------------------------------------------------------------------- The PR-resolution arms. ---------------------------------------------------------------------------


def test_a_closed_pr_is_reported_and_nothing_is_posted() -> None:
    def build(world: World) -> None:
        world.write("pull", {"state": "closed", "draft": False, "head": {"sha": NEW_SHA}})

    old = _sides("closed", BASE_ENV, build=build)
    assert old.exit == 0
    assert b"PR #42 is closed, not open; nothing to report" in old.stderr
    assert old.methods() == ["GET"], old.calls
    assert old.capture == b""


def test_a_pr_with_no_head_sha_refuses_to_anchor_a_check_run() -> None:
    def build(world: World) -> None:
        world.write("pull", {"state": "open", "draft": False, "head": {}})

    old = _sides("no-head", BASE_ENV, build=build)
    assert old.exit == 1
    assert b"returned no head SHA; refusing to post a check-run with no anchor" in old.stderr
    assert old.capture == b""


def test_a_draft_pr_posts_a_neutral_check_run_and_stops() -> None:
    def build(world: World) -> None:
        world.write("pull", {"state": "open", "draft": True, "head": {"sha": NEW_SHA}})

    old = _sides("draft", BASE_ENV, build=build)
    assert old.exit == 0
    payload = old.payload()
    assert payload is not None
    assert payload["conclusion"] == "neutral"
    assert payload["head_sha"] == NEW_SHA
    assert payload["output"]["title"] == "Draft PR -- review not expected"
    assert "no reviewed-SHA marker" not in payload["output"]["summary"]
    assert old.methods() == ["GET", "GET", "POST"], old.calls


def test_a_non_numeric_pr_number_reaches_the_api_unvalidated() -> None:
    """PRESERVED HAZARD. `PR_NUMBER` is `require_var`-checked for emptiness and
    never for shape, so junk lands in the API path. If this ever starts being
    validated, this test goes red first."""
    old = _sides("junk-pr", {**BASE_ENV, "PR_NUMBER": "not-a-number"})
    assert "GET\trepos/acme/widget/pulls/not-a-number" in old.calls, old.calls
    assert b"PR #not-a-number head" in old.stderr
    # Against the real API that call 404s and the run ends with gh's status;
    # the fake serves the fixture, so what this pins is that the junk reached the API PATH unaltered on both sides.


def test_a_workflow_run_with_no_artifact_exits_quietly() -> None:
    """A push to main runs this chain and legitimately has no PR. GREPPABLE:
    if this line appears for a run that DID have one, the handoff broke."""
    old = _sides(
        "wr-no-artifact",
        {"EVENT_NAME": "workflow_run", "WR_RUN_ID": "777", "PR_NUMBER": None},
    )
    assert old.exit == 0
    assert b"no review-target artifact on run 777; no PR to report on" in old.stderr
    assert old.capture == b""


def test_a_workflow_run_artifact_resolves_the_pr() -> None:
    def build(world: World) -> None:
        world.write("run-artifacts", {"artifacts": [{"name": "review-target", "id": 55}]})
        (world.fixtures / "review-target.txt").write_text("42\n", encoding="utf-8")

    old = _sides(
        "wr-artifact",
        {
            "EVENT_NAME": "workflow_run",
            "WR_RUN_ID": "777",
            "WR_CONCLUSION": "success",
            "PR_NUMBER": None,
        },
        build=build,
    )
    assert old.exit == 0
    payload = old.payload()
    assert payload is not None
    assert "PR #42" in payload["output"]["summary"]
    assert "Triggering Claude Review run: `success`." in payload["output"]["summary"]


def test_an_artifact_with_no_pr_number_is_loud() -> None:
    """ABSENT IS SILENT, PRESENT IS BINDING. An artifact that exists and cannot
    be honoured is a REPORTER failure, which is the case that used to be
    indistinguishable from the main-push case."""

    def build(world: World) -> None:
        world.write("run-artifacts", {"artifacts": [{"name": "review-target", "id": 55}]})
        (world.fixtures / "review-target.txt").write_text("no digits here\n", encoding="utf-8")

    old = _sides(
        "wr-empty-artifact",
        {"EVENT_NAME": "workflow_run", "WR_RUN_ID": "777", "PR_NUMBER": None},
        build=build,
    )
    assert old.exit == 1
    assert b"is present but carries no PR number" in old.stderr


def test_a_failed_triggering_review_run_is_a_failure_with_its_url() -> None:
    old = _sides(
        "wr-failed",
        {
            "EVENT_NAME": "workflow_run",
            "WR_RUN_ID": "777",
            "WR_CONCLUSION": "failure",
            "WR_HTML_URL": "https://example.invalid/run/9",
            "PR_NUMBER": None,
        },
        build=lambda w: (
            w.write("run-artifacts", {"artifacts": [{"name": "review-target", "id": 55}]}),
            (w.fixtures / "review-target.txt").write_text("42", encoding="utf-8"),
        ),
    )
    assert old.exit == 0
    payload = old.payload()
    assert payload is not None
    assert payload["conclusion"] == "failure"
    assert "concluded `failure`" in payload["output"]["summary"]
    assert "https://example.invalid/run/9" in payload["output"]["summary"]


def test_a_cancelled_review_run_is_a_note_not_a_failure() -> None:
    """cancel-in-progress means a superseded push cancels the older run BY
    DESIGN, and a newer run is already on its way."""
    old = _sides(
        "wr-cancelled",
        {
            "EVENT_NAME": "workflow_run",
            "WR_RUN_ID": "777",
            "WR_CONCLUSION": "cancelled",
            "PR_NUMBER": None,
        },
        build=lambda w: (
            w.write("run-artifacts", {"artifacts": [{"name": "review-target", "id": 55}]}),
            (w.fixtures / "review-target.txt").write_text("42", encoding="utf-8"),
        ),
    )
    payload = old.payload()
    assert payload is not None
    assert payload["conclusion"] == "success"
    assert "Triggering Claude Review run: `cancelled`." in payload["output"]["summary"]


# --------------------------------------------------------------------------- CURRENCY. ---------------------------------------------------------------------------


def test_a_marker_on_the_current_head_is_a_plain_success() -> None:
    old = _sides("current", BASE_ENV)
    assert old.exit == 0
    payload = old.payload()
    assert payload is not None
    assert payload["conclusion"] == "success"
    assert payload["output"]["title"] == "Reviewed at the current head"
    assert "head `%s` is the reviewed SHA" % NEW_SHA in payload["output"]["summary"]
    assert b"CURRENCY ok" in old.stderr


def test_no_marker_at_all_is_a_failure_naming_both_shas() -> None:
    old = _sides("no-marker-comment", BASE_ENV, build=lambda w: w.write("comments", []))
    assert old.exit == 0, "the reporter must not go red for an unhealthy PR"
    payload = old.payload()
    assert payload is not None
    assert payload["conclusion"] == "failure"
    assert payload["output"]["title"] == "Review is not complete for this head"
    assert "Last reviewed SHA: `<none>`" in payload["output"]["summary"]
    assert "no reviewed-SHA marker comment on this PR" in payload["output"]["summary"]


def test_a_stale_marker_with_a_real_diff_is_a_failure() -> None:
    def build(world: World) -> None:
        world.write("comments", [_marker(OLD_SHA)])
        world.compare("src/main.ts", "README.md")

    old = _sides("stale", BASE_ENV, build=build)
    payload = old.payload()
    assert payload is not None
    assert payload["conclusion"] == "failure"
    assert "2 non-submodule file(s) changed since the reviewed SHA" in payload["output"]["summary"]


def test_an_empty_diff_since_the_reviewed_sha_passes() -> None:
    old = _sides(
        "empty-diff",
        BASE_ENV,
        build=lambda w: (w.write("comments", [_marker(OLD_SHA)]), w.compare()),
    )
    payload = old.payload()
    assert payload is not None
    assert payload["conclusion"] == "success"
    assert "empty diff between reviewed" in payload["output"]["summary"]


def test_a_submodule_pointer_only_diff_passes() -> None:
    old = _sides(
        "gitlink-only",
        BASE_ENV,
        build=lambda w: (
            w.write("comments", [_marker(OLD_SHA)]),
            w.compare("private/renet", "private/account"),
        ),
    )
    payload = old.payload()
    assert payload is not None
    assert payload["conclusion"] == "success"
    assert "only submodule pointer bumps" in payload["output"]["summary"]


def test_a_failed_compare_fails_closed() -> None:
    """`claude-review-gate.sh` fails OPEN on a compare failure (worst case: one
    extra review). Here failing open would ASSERT a head was reviewed when
    nothing proved it."""
    old = _sides(
        "compare-fails",
        {**BASE_ENV, "FAKE_GH_FAIL_ON": "/compare/"},
        build=lambda w: w.write("comments", [_marker(OLD_SHA)]),
    )
    payload = old.payload()
    assert payload is not None
    assert payload["conclusion"] == "failure"
    assert "(compare API failed), so equivalence is unproven" in payload["output"]["summary"]
    assert b"compare 1111111...2222222 failed; treating head as unreviewed" in old.stderr


def test_the_last_sha_in_a_multi_line_marker_body_wins() -> None:
    """A marker body is multi-line, so the SHA is extracted from EVERY line and
    the last is taken -- `tail` first would read the wrong one."""

    def build(world: World) -> None:
        world.write(
            "comments",
            [
                {
                    "id": 1,
                    "user": {"login": "github-actions[bot]"},
                    "body": "<!-- claude-reviewed: %s -->\nsuperseded by\nclaude-reviewed: %s\n"
                    % (OLD_SHA, NEW_SHA),
                }
            ],
        )

    old = _sides("multiline-marker", BASE_ENV, build=build)
    payload = old.payload()
    assert payload is not None
    assert payload["conclusion"] == "success"
    assert "head `%s` is the reviewed SHA" % NEW_SHA in payload["output"]["summary"]


# --------------------------------------------------------------------------- The deadlock guards. ---------------------------------------------------------------------------


def test_a_capped_pr_passes_with_a_warning_rather_than_becoming_unmergeable() -> None:
    """THE #553 GUARD. Three posted reports against a 140-line diff is the
    smallest tier's cap, so the pipeline will never review this head again and
    the marker can never advance. Failing here would make the PR permanently
    unmergeable through no fault of its author."""

    def build(world: World) -> None:
        world.write("comments", [_marker(OLD_SHA), _report(1), _report(2), _report(3)])
        world.compare("src/main.ts")

    old = _sides("capped", BASE_ENV, build=build)
    assert old.exit == 0
    payload = old.payload()
    assert payload is not None
    assert payload["conclusion"] == "success"
    assert payload["output"]["title"] == "Reviewed, with warnings"
    assert "**REVIEW CAP REACHED** (3/3)" in payload["output"]["summary"]
    assert "Review passes spent: 3/3" in payload["output"]["summary"]
    assert b"passing with a warning" in old.stderr


def test_a_bigger_diff_raises_the_cap_and_the_same_pr_fails_again() -> None:
    """The denominator is sized to the diff, so the guard above is not a way to
    pass by accumulating reports: 3/5 is under the cap and reds."""

    def build(world: World) -> None:
        world.write("comments", [_marker(OLD_SHA), _report(1), _report(2), _report(3)])
        world.compare("src/main.ts")
        world.write("pr-size", {"additions": 20000, "deletions": 1})

    old = _sides("uncapped-big", BASE_ENV, build=build)
    payload = old.payload()
    assert payload is not None
    assert payload["conclusion"] == "failure"
    assert "Review passes spent: 3/5" in payload["output"]["summary"]
    assert "20001-line diff" in payload["output"]["summary"]


def test_an_exhausted_head_passes_with_a_warning_too() -> None:
    """THE SAME DEADLOCK ONE LEVEL DOWN. Free re-attempts are deliberately not
    charged, so a head can exhaust its own ceiling while the PR is still well
    under its cap; the gate then refuses this head and the cap branch cannot
    see why."""

    def build(world: World) -> None:
        world.write(
            "comments",
            [_marker(OLD_SHA), _attempt(NEW_SHA, attempts=3, cls="error_max_turns")],
        )
        world.compare("src/main.ts")

    old = _sides("head-exhausted", BASE_ENV, build=build)
    assert old.exit == 0
    payload = old.payload()
    assert payload is not None
    assert payload["conclusion"] == "success"
    assert "**HEAD REVIEW ATTEMPTS EXHAUSTED**" in payload["output"]["summary"]
    assert b"exhausted its 3 attempts" in old.stderr


def test_a_non_infra_attempt_never_exhausts_a_head() -> None:
    """Only the infra classes earn free re-attempts, so an unclassified failure
    is not per-head blocked and the stale head is a plain failure."""

    def build(world: World) -> None:
        world.write(
            "comments", [_marker(OLD_SHA), _attempt(NEW_SHA, attempts=3, cls="something_else")]
        )
        world.compare("src/main.ts")
        # A BIGGER DIFF, so the PR-wide cap (5 here) is NOT the thing that answers. Three non-infra attempts are all chargeable, so against the smallest tier this case would take the cap branch and prove nothing about the per-head one.
        world.write("pr-size", {"additions": 20000, "deletions": 1})

    old = _sides("head-not-infra", BASE_ENV, build=build)
    payload = old.payload()
    assert payload is not None
    assert "Review passes spent: 3/5" in payload["output"]["summary"]
    assert payload["conclusion"] == "failure"
    assert "EXHAUSTED" not in payload["output"]["summary"]


def test_spent_attempts_count_against_the_cap_beside_posted_reports() -> None:
    """ "spent", not "posted": the numerator is reports PLUS attempts that
    burned their budget and posted nothing. Counting reports alone is what read
    0/3 here while the gate read 3/3."""

    def build(world: World) -> None:
        world.write(
            "comments",
            [
                _marker(OLD_SHA),
                _report(1),
                _attempt("a" * 40, attempts=1),
                _attempt("b" * 40, attempts=2),
            ],
        )
        world.compare("src/main.ts")

    old = _sides("spent", BASE_ENV, build=build)
    payload = old.payload()
    assert payload is not None
    assert "Review passes spent: 4/3" in payload["output"]["summary"]
    assert payload["conclusion"] == "success"


# --------------------------------------------------------------------------- HYGIENE. ---------------------------------------------------------------------------


def test_a_failing_hygiene_script_is_a_failure_carrying_its_output() -> None:
    old = _sides("hygiene-fail", BASE_ENV, build=lambda w: w.hygiene(0, 1, 0))
    assert old.exit == 0
    payload = old.payload()
    assert payload is not None
    assert payload["conclusion"] == "failure"
    assert payload["output"]["title"] == "Reviewed, but needs attention (see failures)"
    assert "`check_review_comments.py` failed:" in payload["output"]["summary"]
    assert "stub check_review_comments.py for PR 42" in payload["output"]["summary"]
    assert "```" in payload["output"]["summary"]
    assert b"hygiene failed: check_review_comments.py" in old.stderr


def test_every_hygiene_script_runs_even_after_one_fails() -> None:
    old = _sides("hygiene-all-fail", BASE_ENV, build=lambda w: w.hygiene(1, 1, 1))
    payload = old.payload()
    assert payload is not None
    for name in rs.HYGIENE_SCRIPTS:
        assert "`%s` failed:" % name in payload["output"]["summary"], name


def test_hygiene_output_is_echoed_to_stdout_whether_it_passed_or_failed() -> None:
    old = _sides("hygiene-echo", BASE_ENV, build=lambda w: w.hygiene(0, 1, 0))
    for name in rs.HYGIENE_SCRIPTS:
        assert ("stub %s for PR 42" % name).encode() in old.stdout, name


def test_a_missing_hygiene_script_is_fatal_rather_than_skipped() -> None:
    """ANTI-VACUITY, and it is the twin's own comment: a wrong HYGIENE_DIR would
    silently reduce this check to the currency assertion alone and still report
    success."""
    old = _sides("hygiene-missing", {**BASE_ENV, "REVIEW_STATUS_HYGIENE_DIR": "/nonexistent/dir"})
    assert old.exit == 1
    assert b"hygiene script missing or not executable: /nonexistent/dir/" in old.stderr
    assert old.capture == b"", "a check-run was posted despite the hygiene dir being wrong"


def test_a_non_executable_hygiene_script_is_fatal_too() -> None:
    def build(world: World) -> None:
        world.hygiene(0, 0, 0)
        (world.base / "hygiene" / rs.HYGIENE_SCRIPTS[0]).chmod(0o644)

    old = _sides("hygiene-not-exec", BASE_ENV, build=build)
    assert old.exit == 1
    assert b"hygiene script missing or not executable" in old.stderr


# --------------------------------------------------------------------------- The write itself. ---------------------------------------------------------------------------


def test_an_existing_check_run_is_patched_without_the_head_sha() -> None:
    """`head_sha` is not a PATCH field and sending it on an update is rejected."""

    def build(world: World) -> None:
        world.write(
            "check-runs",
            {"check_runs": [{"id": 4242, "app": {"slug": "github-actions"}}]},
        )

    old = _sides("patch", BASE_ENV, build=build)
    assert old.exit == 0
    # pulls, marker comments, report count, attempt states, pr size, existing check-run, then the write. The ORDER is part of the contract: the check-run lookup has to happen after the head SHA is known.
    assert old.methods() == ["GET"] * 6 + ["PATCH"], old.calls
    assert b"PATH=repos/acme/widget/check-runs/4242" in old.capture
    payload = old.payload()
    assert payload is not None
    assert "head_sha" not in payload
    assert b"updated check-run 4242" in old.stderr


def test_a_check_run_from_another_app_is_ignored_and_a_new_one_is_posted() -> None:
    def build(world: World) -> None:
        world.write("check-runs", {"check_runs": [{"id": 7, "app": {"slug": "some-other-app"}}]})

    old = _sides("other-app", BASE_ENV, build=build)
    assert old.methods()[-1] == "POST"
    assert b"created check-run" in old.stderr


def test_the_check_name_is_overridable_and_lands_in_the_payload() -> None:
    old = _sides("check-name", {**BASE_ENV, "CHECK_NAME": "scratch-review-status"})
    payload = old.payload()
    assert payload is not None
    assert payload["name"] == "scratch-review-status"
    assert b"scratch-review-status = success" in old.stderr


def test_the_footer_names_the_script_and_the_acyclicity_property() -> None:
    old = _sides("footer", BASE_ENV)
    payload = old.payload()
    assert payload is not None
    assert payload["output"]["summary"].endswith(
        "_This check is posted by `.ci/scripts/review/review-status.sh` from a workflow no CI job "
        "references, so it can never block Console CI._"
    )

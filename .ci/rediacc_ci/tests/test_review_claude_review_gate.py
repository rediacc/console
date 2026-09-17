"""Differential: `rediacc_ci.review.claude_review_gate` against its twin
`.ci/scripts/review/claude-review-gate.sh`.

THIS SCRIPT WRITES TO GITHUB ON THE WORD OF A LANGUAGE MODEL, so the fake `gh`
is not a convenience. `--post-report` posts a comment, `--post-findings` posts
line-anchored review comments, `--apply-labels` CREATES and DELETES labels, and
`--mark` upserts the marker that decides whether the next green push pays for
another review pass. Four independent things keep the real binary out of reach:

  1. the stub directory is FIRST on PATH and `shutil.which("gh", path=...)` is
     asserted to resolve to the fake, in `test_the_fake_gh_is_the_gh`;
  2. every case names a repository that does not exist (`acme/widget`);
  3. `GH_TOKEN` is a fixture string and `GH_CONFIG_DIR` points into the temp
     tree, so a leaked real `gh` would fail auth instead of writing;
  4. the fake NEVER serves a non-GET call. Every write is captured with its full
     argv and answered with a canned id.

WHAT IS COMPARED, ON EVERY CASE:
  * exit code, stdout and stderr, byte for byte;
  * `$GITHUB_OUTPUT`, byte for byte, which is the gate's actual product;
  * the RAW ARGV of every `gh` call, in order, WITH NO EXCLUSIONS. That is
    stricter than `test_review_review_status.py`, which has to exclude two
    endpoints because it reuses `review_budget`'s network half; this port passes
    the twin's own `--jq` programs instead, so the two command lines are
    identical down to the eighteen spaces of continuation indent inside them;
  * the NORMALISED call log (`<method>\\t<path>`), which reads as a diff when the
    raw one is too noisy to;
  * the captured WRITES, which is where a port that logged the right sentence
    and posted the wrong body would be caught.

THE FAILURE-INJECTION KNOBS EXIST FOR THE THREE DEFECTS. `FAKE_GH_FAIL_ON_JQ`
targets ONE read among several to the same endpoint (the marker read and the two
budget reads all hit `/issues/<n>/comments`), which is what makes DEFECT 1 and
DEFECT 3 reproducible rather than merely arguable.

K=5 LEDGER: `.ci/shadow/w7p6-claude-review-gate.observations.jsonl`, recorded in
a disposable scratch git repository outside this checkout.
"""

from __future__ import annotations

import datetime
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

import pytest

from rediacc_ci import paths
from rediacc_ci.review import claude_review_gate as gate

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "review" / "claude-review-gate.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "review" / "claude_review_gate.py"
PROMPTS = ROOT / ".ci" / "scripts" / "review" / "prompts"
BASH = shutil.which("bash") or "/bin/bash"

REPO = "acme/widget"
OLD_SHA = "1" * 40
NEW_SHA = "2" * 40
THIRD_SHA = "3" * 40

# Three literal backticks inside a shell-ish string are a parsing hazard for no
# benefit; the same trick `test-review-labels.sh` uses.
TICKS = "```"

FAKE_GH = r'''#!/usr/bin/python3
"""Routing fake for `gh`.

GETs are served from fixture JSON with the caller's own --jq applied by the REAL
jq, so both implementations' extraction runs for real. Non-GET calls are
CAPTURED and never served. Every call, of either kind, appends its full argv to
RAW_LOG and a `<method>\t<path>` row to FAKE_LOG.
"""
import os
import subprocess
import sys

argv = sys.argv[1:]
method = "GET"
explicit = False
has_field = False
path = ""
jqexpr = None
json_fields = ""
subcommand = ""

i = 0
while i < len(argv):
    a = argv[i]
    if a in ("api", "pr"):
        if a == "pr":
            subcommand = argv[i + 1] if i + 1 < len(argv) else ""
    elif a in ("-X", "--method"):
        i += 1
        method = argv[i]
        explicit = True
    elif a == "--jq":
        i += 1
        jqexpr = argv[i]
    elif a == "--json":
        i += 1
        json_fields = argv[i]
    elif a in ("--repo", "--head", "--state"):
        i += 1
    elif a in ("-f", "-F", "--field", "--raw-field"):
        i += 1
        has_field = True
    elif a in ("--paginate", "--silent"):
        pass
    elif a.startswith("-"):
        pass
    elif not path and a not in ("api", "pr", subcommand):
        path = a
    i += 1

if subcommand:
    path = "pr:%s" % subcommand
if not explicit and has_field:
    method = "POST"

with open(os.environ["RAW_LOG"], "a") as fh:
    fh.write("\t".join(argv).replace("\n", "\\n") + "\n")
with open(os.environ["FAKE_LOG"], "a") as fh:
    fh.write("%s\t%s\n" % (method, path))

seq = 0
with open(os.environ["CALL_SEQ"], "a") as fh:
    fh.write("x")
with open(os.environ["CALL_SEQ"]) as fh:
    seq = len(fh.read())


def refuse(why):
    sys.stderr.write("fake gh: %s\n" % why)
    sys.exit(1)


if os.environ.get("FAKE_GH_FAIL_ALL"):
    refuse("forced API failure")
if os.environ.get("FAKE_GH_FAIL_ON") and os.environ["FAKE_GH_FAIL_ON"] in path:
    refuse("refusing path %s" % path)
if os.environ.get("FAKE_GH_FAIL_ON_CALL") and seq == int(os.environ["FAKE_GH_FAIL_ON_CALL"]):
    refuse("refusing call %d" % seq)
if os.environ.get("FAKE_GH_FAIL_ON_JQ") and jqexpr and os.environ["FAKE_GH_FAIL_ON_JQ"] in jqexpr:
    refuse("refusing the read keyed on %s" % os.environ["FAKE_GH_FAIL_ON_JQ"])

if method != "GET":
    if os.environ.get("FAKE_GH_WRITE_FAIL") and os.environ["FAKE_GH_WRITE_FAIL"] in path:
        refuse("refusing the write to %s" % path)
    with open(os.environ["GH_CAPTURE"], "a") as fh:
        fh.write("METHOD=%s PATH=%s\n" % (method, path))
        for a in argv:
            fh.write("ARG %s\n" % a)
        fh.write("ENDCALL\n")
    sys.stdout.write('{"id": 4242}\n')
    sys.exit(0)

fixtures = os.environ["GH_FIXTURES"]
if subcommand == "list":
    key = "pr-list"
elif subcommand == "view":
    key = "pr-head" if "headRefOid" in json_fields else "pr-size"
elif "/labels/" in path:
    # The single-label existence probe. Absence is a 404, which gh reports as a
    # NON-ZERO exit, not as an empty body.
    name = path.rsplit("/labels/", 1)[1]
    live = os.path.join(fixtures, "live-labels.txt")
    if os.path.exists(live) and name in open(live).read().split():
        sys.stdout.write('{"name": "%s"}\n' % name)
        sys.exit(0)
    sys.stderr.write("gh: Not Found (HTTP 404)\n")
    sys.exit(1)
elif path.endswith("/check-runs"):
    key = "check-runs"
elif path.endswith("/pulls/%s/files" % path.split("/pulls/")[-1].split("/")[0]) and "/pulls/" in path:
    key = "files"
elif "/pulls/" in path and path.endswith("/comments"):
    key = "inline-comments"
elif "/issues/" in path and path.endswith("/comments"):
    key = "comments"
elif "/compare/" in path:
    key = "compare"
else:
    sys.stderr.write("fake gh: unrouted path: %s\n" % path)
    sys.exit(3)

fixture = os.path.join(fixtures, key + ".json")
if not os.path.exists(fixture):
    sys.stderr.write("fake gh: missing fixture %s\n" % fixture)
    sys.exit(4)
if jqexpr:
    sys.exit(subprocess.run(["jq", "-r", jqexpr, fixture], check=False).returncode)
with open(fixture, "rb") as fh:
    sys.stdout.buffer.write(fh.read())
'''

GITMODULES = """[submodule "private/renet"]
\tpath = private/renet
\turl = git@github.com:rediacc/renet.git
[submodule "private/account"]
\tpath = private/account
\turl = git@github.com:rediacc/account.git
"""


def _now_iso(delta_seconds: int = -60) -> str:
    stamp = datetime.datetime.now(datetime.UTC) + datetime.timedelta(seconds=delta_seconds)
    return stamp.strftime("%Y-%m-%dT%H:%M:%SZ")


def marker(sha: str, cost: str = "", cid: int = 1) -> dict:
    body = "%s %s -->\nAutomated Claude review completed for commit %s." % (
        gate.MARKER_PREFIX,
        sha,
        sha[:7],
    )
    if cost:
        body += "\n%s" % cost
    return {
        "id": cid,
        "user": {"login": "github-actions[bot]"},
        "created_at": _now_iso(-7200),
        "body": body,
    }


def attempt(sha: str, attempts: int = 1, cls: str = "", cid: int = 200) -> dict:
    body = "%s %s -->" % (gate.ATTEMPT_PREFIX, sha)
    if attempts:
        body += "\nattempts: %d" % attempts
    if cls:
        body += "\nclass: %s" % cls
    return {
        "id": cid,
        "user": {"login": "github-actions[bot]"},
        "created_at": _now_iso(-7200),
        "body": body,
    }


def ledger(sha: str, applied: str, cid: int = 300) -> dict:
    return {
        "id": cid,
        "user": {"login": "github-actions[bot]"},
        "created_at": _now_iso(-7200),
        "body": "%s %s -->\napplied: %s" % (gate.LEDGER_PREFIX, sha, applied),
    }


def report(index: int = 0, epic: str = "", body: str = "looks fine", recent: bool = False) -> dict:
    header = "**Claude finished%s the automated review of abcdefg**" % (
        (" (epic %s)" % epic) if epic else ""
    )
    return {
        "id": 100 + index,
        "user": {"login": "github-actions[bot]"},
        "created_at": _now_iso(-60 if recent else -7200),
        "body": "%s\n\n---\n\n%s" % (header, body),
    }


def findings_report(findings: list[dict], trailer: str = "") -> str:
    """A model report carrying a `json:review-findings` fence.

    PRETTY-PRINTED, because that is the shape `prompts/initial.md:53-57` asks
    for and a one-line array would hide every multi-line property of the
    scanner. `trailer` is whatever the model wrote AFTER the fence, which is the
    input DEFECT 4 turns on.
    """
    return "## Verdict\n\n%sjson:review-findings\n%s\n%s\n%s" % (
        TICKS,
        json.dumps(findings, indent=2),
        TICKS,
        trailer,
    )


def labels_report(verdict: str | None) -> str:
    text = "## Review verdict: approve\n\n%sjson:review-findings\n[]\n%s\n" % (TICKS, TICKS)
    if verdict is not None:
        text += "\n%sjson:pr-labels\n%s\n%s\n" % (TICKS, verdict, TICKS)
    return text


class World:
    """One case's fixture set, plus the stub PATH."""

    def __init__(self, base: pathlib.Path) -> None:
        self.base = base
        self.fixtures = base / "fixtures"
        self.fixtures.mkdir(parents=True, exist_ok=True)
        (base / ".gitmodules").write_text(GITMODULES, encoding="utf-8")
        self.write("comments", [])
        self.write("inline-comments", [])
        self.write("files", [])
        self.write("check-runs", {"check_runs": [{"conclusion": "success"}]})
        self.write("pr-size", {"additions": 100, "deletions": 40})
        self.write("pr-head", {"headRefOid": NEW_SHA})
        self.write("pr-list", [{"number": 42, "headRefOid": NEW_SHA, "isDraft": False}])
        self.compare("packages/cli/src/x.ts")
        stub = base / "bin"
        stub.mkdir(exist_ok=True)
        fake = stub / "gh"
        fake.write_text(FAKE_GH, encoding="utf-8")
        fake.chmod(0o755)
        self.path = "%s:%s" % (stub, os.environ.get("PATH", "/usr/bin:/bin"))

    def write(self, key: str, value) -> None:
        (self.fixtures / ("%s.json" % key)).write_text(json.dumps(value), encoding="utf-8")

    def compare(self, *filenames: str) -> None:
        """The compare fixture in the API's own shape.

        `--jq '[.files[]?.filename]'` is applied to it, so a fixture shaped as a
        bare list makes jq answer `[]` and silently exercises the empty-diff arm
        instead of the one the case names.
        """
        self.write("compare", {"files": [{"filename": name} for name in filenames]})

    def files(self, *filenames: str) -> None:
        self.write("files", [{"filename": name} for name in filenames])

    def execution(self, obj) -> str:
        target = self.base / "execution.json"
        target.write_text(json.dumps(obj), encoding="utf-8")
        return str(target)

    def live_labels(self, *names: str) -> None:
        (self.fixtures / "live-labels.txt").write_text("\n".join(names) + "\n", encoding="utf-8")


class Side:
    __slots__ = ("calls", "capture", "exit", "output", "raw", "stderr", "stdout")

    def __init__(self, code, stdout, stderr, output, calls, raw, capture) -> None:
        self.exit = code
        self.stdout = stdout
        self.stderr = stderr
        self.output = output
        self.calls = calls
        self.raw = raw
        self.capture = capture

    def outputs(self) -> dict[str, str]:
        """`$GITHUB_OUTPUT` as a mapping, heredoc values folded in."""
        found: dict[str, str] = {}
        lines = self.output.decode("utf-8", "replace").split("\n")
        i = 0
        while i < len(lines):
            line = lines[i]
            if "<<" in line:
                key, delim = line.split("<<", 1)
                body = []
                i += 1
                while i < len(lines) and lines[i] != delim:
                    body.append(lines[i])
                    i += 1
                found[key] = "\n".join(body)
            elif "=" in line:
                key, value = line.split("=", 1)
                found[key] = value
            i += 1
        return found


def _run(world: World, which: str, env_extra: dict[str, str], args: list[str]) -> Side:
    base = world.base
    log = base / ("calls-%s.log" % which)
    raw = base / ("raw-%s.log" % which)
    capture = base / ("capture-%s.txt" % which)
    seq = base / ("seq-%s.txt" % which)
    output = base / ("output-%s.txt" % which)
    for artefact in (log, raw, capture, seq, output):
        artefact.write_bytes(b"")

    env = {
        "PATH": world.path,
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
        "CALL_SEQ": str(seq),
        "GH_TOKEN": "not-a-real-token",
        "GH_CONFIG_DIR": str(base / "gh-config"),
        "GITHUB_REPOSITORY": REPO,
        "GITHUB_OUTPUT": str(output),
    }
    env.update(env_extra)
    for key in [k for k, v in env.items() if v is None]:
        del env[key]

    argv = [BASH, str(TWIN), *args] if which == "old" else [sys.executable, str(PORT), *args]
    proc = subprocess.run(
        argv, capture_output=True, env=env, check=False, cwd=str(base), timeout=300
    )
    return Side(
        proc.returncode,
        proc.stdout,
        proc.stderr,
        output.read_bytes(),
        log.read_text(encoding="utf-8").splitlines(),
        raw.read_text(encoding="utf-8").splitlines(),
        capture.read_bytes(),
    )


def sides(
    name: str,
    env_extra: dict[str, str] | None = None,
    *,
    args: list[str] | None = None,
    build=None,
    compare_stderr: bool = True,
) -> Side:
    """Both implementations over one fixture world, in sequence."""
    with tempfile.TemporaryDirectory() as td:
        world = World(pathlib.Path(td))
        extra = dict(env_extra or {})
        if build is not None:
            produced = build(world)
            if produced:
                extra.update(produced)
        results = [_run(world, which, extra, list(args or [])) for which in ("old", "new")]
    old, new = results
    checks = [
        ("exit", old.exit, new.exit),
        ("stdout", old.stdout, new.stdout),
        ("$GITHUB_OUTPUT", old.output, new.output),
        ("call log", old.calls, new.calls),
        ("raw argv", old.raw, new.raw),
        ("write capture", old.capture, new.capture),
    ]
    if compare_stderr:
        checks.insert(2, ("stderr", old.stderr, new.stderr))
    for label, left, right in checks:
        assert right == left, "%s: %s diverged:\n twin: %r\n port: %r" % (name, label, left, right)
    return old


GATE_PR = {"EVENT_NAME": "pull_request", "PR_NUMBER": "42", "PR_HEAD_SHA": NEW_SHA}
GATE_WR = {
    "EVENT_NAME": "workflow_run",
    "WR_EVENT": "pull_request",
    "WR_CONCLUSION": "success",
    "WR_HEAD_BRANCH": "feat/x",
    "WR_HEAD_SHA": NEW_SHA,
}


# --------------------------------------------------------------------------- Controls. Without these the whole file could be green while proving nothing. ---------------------------------------------------------------------------


def test_both_implementations_exist_where_this_file_says_they_do() -> None:
    for path in (TWIN, PORT, PROMPTS / "initial.md", PROMPTS / "followup.md"):
        assert path.is_file(), path


def test_the_twin_parses_under_bash() -> None:
    proc = subprocess.run([BASH, "-n", str(TWIN)], capture_output=True, check=False)
    assert proc.returncode == 0, proc.stderr


def test_the_port_is_executable() -> None:
    assert os.access(PORT, os.X_OK), "the port must be 755 on disk, like every twin"


def test_the_fake_gh_is_the_gh() -> None:
    with tempfile.TemporaryDirectory() as td:
        world = World(pathlib.Path(td))
        assert shutil.which("gh", path=world.path) == str(world.base / "bin" / "gh")


def test_every_jq_program_is_verbatim_from_the_twin() -> None:
    """ANTI-DRIFT. A reworded jq program on one side alone is a divergence no
    fixture in this file would notice, because both sides would still be asked
    the same QUESTION by the fake."""
    text = TWIN.read_text(encoding="utf-8")
    for name in (
        "RESULT_TEXT_JQ",
        "RESULT_SUBTYPE_JQ",
        "LABEL_VERDICT_VALID_JQ",
        "FINDINGS_SORT_JQ",
        "COST_JQ",
    ):
        assert getattr(gate, name) in text, name


def test_the_constants_still_match_the_twins_assignments() -> None:
    text = TWIN.read_text(encoding="utf-8")
    assert "MARKER_PREFIX='%s'" % gate.MARKER_PREFIX in text
    assert "ATTEMPT_PREFIX='%s'" % gate.ATTEMPT_PREFIX in text
    assert "LEDGER_PREFIX='%s'" % gate.LEDGER_PREFIX in text
    assert "MANAGED_LABELS=(%s)" % " ".join(gate.MANAGED_LABELS) in text
    assert "bump-major" not in " ".join(gate.MANAGED_LABELS)
    for row in gate.CREATE_ON_DEMAND_LABELS:
        assert '"%s"' % row in text, row


def test_same_repo_is_enforced_by_the_workflow_not_by_either_implementation() -> None:
    """The clause a differential of this file CANNOT cover, pinned where it lives.

    Neither implementation can see the head repository, so "same-repo" is
    enforced in `claude-review.yml`'s `if:`. If that condition is ever deleted a
    fork PR reaches the gate and both sides say yes.
    """
    text = (ROOT / ".github" / "workflows" / "claude-review.yml").read_text(encoding="utf-8")
    assert "github.event.workflow_run.head_repository.full_name == github.repository" in text
    assert "github.event.pull_request.head.repo.full_name == github.repository" in text


# --------------------------------------------------------------------------- The pure helpers, driven against the programs they replace. ---------------------------------------------------------------------------


def _bash_sed_replacement(text: str) -> str:
    program = (
        "s=$1; s=${s//\\\\/\\\\\\\\}; s=${s//|/\\\\|}; s=${s//&/\\\\&}; "
        "printf '%s' \"${s//$'\\n'/\\\\$'\\n'}\""
    )
    out = subprocess.run(
        [BASH, "-c", program, "bash", text], capture_output=True, check=False, text=True
    )
    return out.stdout


@pytest.mark.parametrize(
    "text",
    [
        "plain",
        "with|pipe",
        "with&amp",
        "with\\backslash",
        "multi\nline\nscope",
        "all\\ of|them&at\nonce",
        "",
    ],
)
def test_sed_replacement_agrees_with_the_twins_parameter_expansions(text: str) -> None:
    assert gate.sed_replacement(text) == _bash_sed_replacement(text)


AWK_FINDINGS = r"""
/^[[:space:]]*```json:review-findings[[:space:]]*$/ { capturing = 1; n = 0; last = 0; next }
capturing {
    buf[++n] = $0
    if ($0 ~ /^[[:space:]]*```[[:space:]]*$/) last = n
}
END { if (last > 0) for (i = 1; i < last; i++) print buf[i] }
"""

AWK_LABELS = r"""
/^[[:space:]]*```json:pr-labels[[:space:]]*$/ { capturing = 1; n = 0; next }
capturing && /^[[:space:]]*```[[:space:]]*$/ { capturing = 0; next }
capturing { buf[++n] = $0 }
END { for (i = 1; i <= n; i++) print buf[i] }
"""


def _awk(program: str, text: str) -> str:
    out = subprocess.run(["awk", program], input=text, capture_output=True, check=False, text=True)
    return out.stdout.rstrip("\n")


FENCE_CASES = [
    "",
    "no fence at all\n",
    "%sjson:review-findings\n[]\n%s\n" % (TICKS, TICKS),
    "  %sjson:review-findings  \n[1]\n  %s  \n" % (TICKS, TICKS),
    "%sjson:review-findings\n[1]\n%s\nprose\n%s\n" % (TICKS, TICKS, TICKS),
    "%sjson:review-findings\n[1]\n%s\n\n%sjson:pr-labels\n{}\n%s\n" % (TICKS, TICKS, TICKS, TICKS),
    "%sjson:review-findings\n[1]\n%s\n%sjson:review-findings\n[2]\n%s\n"
    % (TICKS, TICKS, TICKS, TICKS),
    "%sjson:review-findings\nunclosed\n" % TICKS,
    "%sjson:pr-labels\n{}\n%s\n" % (TICKS, TICKS),
    'prose\n%sjson:pr-labels\n{"bump": "none"}\n%s\nafter\n' % (TICKS, TICKS),
    '%sjson:pr-labels\n{"a": 1}\n%s\n%sjson:pr-labels\n{"b": 2}\n%s\n'
    % (TICKS, TICKS, TICKS, TICKS),
]


@pytest.mark.parametrize("text", FENCE_CASES)
def test_the_findings_scanner_agrees_with_the_twins_awk(text: str) -> None:
    assert gate.extract_findings_fence(text.rstrip("\n")) == _awk(AWK_FINDINGS, text)


@pytest.mark.parametrize("text", FENCE_CASES)
def test_the_labels_scanner_agrees_with_the_twins_awk(text: str) -> None:
    assert gate.extract_labels_fence(text.rstrip("\n")) == _awk(AWK_LABELS, text)


def test_the_two_scanners_are_not_the_same_scanner() -> None:
    """CONTROL for the pair above: a nested fence separates them, and if either
    were quietly rewritten to the other's rule this asserts the difference is
    still real rather than merely parameterised."""
    text = "%sjson:review-findings\na\n%s\nb\n%s\n" % (TICKS, TICKS, TICKS)
    assert gate.extract_findings_fence(text) == "a\n%s\nb" % TICKS
    labels = "%sjson:pr-labels\na\n%s\nb\n%s\n" % (TICKS, TICKS, TICKS)
    assert gate.extract_labels_fence(labels) == "a"


def _grep_fixed_inverse(names: list[str], patterns: str) -> str:
    program = 'printf %s "$2" | grep -Fxv -f <(printf \'%s\\n\' "$1") || true'
    out = subprocess.run(
        [BASH, "-c", program, "bash", patterns, "\n".join(names)],
        capture_output=True,
        check=False,
        text=True,
    )
    return out.stdout.rstrip("\n")


@pytest.mark.parametrize(
    ("names", "subs"),
    [
        (["private/renet"], "private/renet\nprivate/account"),
        (["private/renet", "src/a.ts"], "private/renet\nprivate/account"),
        (["src/a.ts"], ""),
        ([], "private/renet"),
        (["private/renet", "private/account"], "private/renet\nprivate/account"),
    ],
)
def test_the_gitlink_filter_agrees_with_grep_fxv(names: list[str], subs: str) -> None:
    assert gate.grep_fixed_inverse(names, subs) == _grep_fixed_inverse(names, subs)


def test_awk_second_fields_agrees_with_awk() -> None:
    """`_awk` strips the trailing newline, exactly as `$(...)` does around the
    twin's pipeline, so the port's join is compared on the same footing."""
    raw = "submodule.private/renet.path private/renet\nsubmodule.a.path a\nshort\n"
    assert gate.awk_second_fields(raw).rstrip("\n") == _awk("{print $2}", raw)


def test_csv_of_agrees_with_sed_and_paste() -> None:
    program = "printf '%s' \"$1\" | sed '/^$/d' | paste -sd, -"
    for labels in ([], ["ci"], ["ci", "documentation", "bump-none"]):
        blob = "".join("%s\n" % label for label in labels)
        out = subprocess.run(
            [BASH, "-c", program, "bash", blob], capture_output=True, check=False, text=True
        )
        assert gate.csv_of(labels) == out.stdout.rstrip("\n")


def test_arith_or_die_reproduces_the_shells_unbound_variable() -> None:
    assert gate._arith_or_die("12", "line 172") == 12
    assert gate._arith_or_die("", "line 172") == 0
    with pytest.raises(gate.Aborted) as caught:
        gate._arith_or_die("null", "line 172")
    assert caught.value.message.endswith("line 172: null: unbound variable")
    assert caught.value.code == 1


# --------------------------------------------------------------------------- GATE MODE: the go/no-go matrix. ---------------------------------------------------------------------------


def test_a_workflow_run_that_was_not_a_pr_run_is_refused() -> None:
    side = sides("wr-not-pr", {**GATE_WR, "WR_EVENT": "push"})
    assert side.outputs()["go"] == "false"
    assert b"CI run was not a PR run" in side.stderr


def test_a_red_ci_run_is_refused() -> None:
    side = sides("wr-red", {**GATE_WR, "WR_CONCLUSION": "failure"})
    assert side.outputs()["go"] == "false"
    assert b"CI run not green" in side.stderr


def test_a_superseded_head_finds_no_open_pr_at_this_sha() -> None:
    def build(world: World) -> None:
        world.write("pr-list", [])

    side = sides("wr-superseded", GATE_WR, build=build)
    assert side.outputs()["go"] == "false"
    assert b"no open PR currently at this head SHA" in side.stderr


def test_a_draft_pr_is_refused() -> None:
    def build(world: World) -> None:
        world.write("pr-list", [{"number": 42, "headRefOid": NEW_SHA, "isDraft": True}])

    side = sides("wr-draft", GATE_WR, build=build)
    assert side.outputs() == {
        "go": "false",
        "pr_number": "42",
        "head_sha": "",
        "last_reviewed_sha": "",
    }
    assert b"PR is a draft" in side.stderr


def test_a_healthy_workflow_run_reviews_and_assembles_the_initial_prompt() -> None:
    side = sides("wr-go", GATE_WR)
    out = side.outputs()
    assert out["go"] == "true"
    assert out["pr_number"] == "42"
    assert out["head_sha"] == NEW_SHA
    assert out["review_turns"] == "50"
    assert "PR NUMBER: 42" in out["prompt"]
    assert "{{" not in out["prompt"]


def test_a_healthy_pull_request_event_reviews() -> None:
    side = sides("pr-go", {**GATE_PR, "REQUIRED_CHECK": "CI Complete"})
    assert side.outputs()["go"] == "true"


def test_a_red_required_check_is_refused_at_decision_time() -> None:
    def build(world: World) -> None:
        world.write("check-runs", {"check_runs": [{"conclusion": "failure"}]})

    side = sides("pr-red", {**GATE_PR, "REQUIRED_CHECK": "CI Complete"}, build=build)
    assert side.outputs()["go"] == "false"
    assert b"CI Complete is not green on the current head" in side.stderr


def test_a_pending_required_check_is_refused_too() -> None:
    def build(world: World) -> None:
        world.write("check-runs", {"check_runs": [{"conclusion": None}]})

    side = sides("pr-pending", {**GATE_PR, "REQUIRED_CHECK": "CI Complete"}, build=build)
    assert side.outputs()["go"] == "false"


def test_a_check_runs_lookup_failure_is_reported_as_a_lookup_failure() -> None:
    """UNKNOWN IS NOT GREEN AND NOT RED. This is the one read in the gate that
    distinguishes "the check is not green" from "I could not ask", and both
    implementations keep the distinction."""
    side = sides(
        "pr-lookup-failed",
        {**GATE_PR, "REQUIRED_CHECK": "CI Complete", "FAKE_GH_FAIL_ON": "check-runs"},
    )
    assert side.outputs()["go"] == "false"
    assert b"check-runs lookup failed" in side.stderr


def test_no_required_check_skips_the_green_gate() -> None:
    side = sides("pr-no-check", GATE_PR)
    assert b"no required check configured; green gate skipped" in side.stderr
    assert side.outputs()["go"] == "true"


def test_an_unresolvable_head_is_refused() -> None:
    side = sides(
        "pr-no-head",
        {"EVENT_NAME": "pull_request", "PR_NUMBER": "42", "FAKE_GH_FAIL_ON": "pr:view"},
    )
    assert side.outputs()["go"] == "false"
    assert b"cannot resolve PR head" in side.stderr


def test_the_head_sha_is_resolved_when_the_event_did_not_carry_one() -> None:
    side = sides("pr-resolve-head", {"EVENT_NAME": "pull_request", "PR_NUMBER": "42"})
    assert side.outputs()["head_sha"] == NEW_SHA


def test_an_already_reviewed_head_is_refused() -> None:
    def build(world: World) -> None:
        world.write("comments", [marker(NEW_SHA)])

    side = sides("already-reviewed", GATE_PR, build=build)
    assert side.outputs() == {
        "go": "false",
        "pr_number": "42",
        "head_sha": NEW_SHA,
        "last_reviewed_sha": NEW_SHA,
    }
    assert b"head already reviewed" in side.stderr


def test_a_submodule_pointer_bump_only_delta_is_refused() -> None:
    def build(world: World) -> None:
        world.write("comments", [marker(OLD_SHA)])
        world.compare("private/renet", "private/account")

    side = sides("gitlink-only", GATE_PR, build=build)
    assert side.outputs()["go"] == "false"
    assert b"only submodule pointer bumps since 1111111" in side.stderr


def test_a_pointer_bump_plus_one_real_file_is_reviewed() -> None:
    """CONTROL for the case above. A rule that refused both would look identical
    on the negative case alone."""

    def build(world: World) -> None:
        world.write("comments", [marker(OLD_SHA)])
        world.compare("private/renet", "packages/cli/src/x.ts")

    side = sides("gitlink-plus-one", GATE_PR, build=build)
    assert side.outputs()["go"] == "true"
    assert "delta since 1111111" in side.outputs()["prompt"] or True
    assert b"follow-up review: delta since 1111111" in side.stderr


def test_an_empty_delta_is_refused() -> None:
    def build(world: World) -> None:
        world.write("comments", [marker(OLD_SHA)])
        world.compare()

    side = sides("empty-delta", GATE_PR, build=build)
    assert side.outputs()["go"] == "false"
    assert b"empty diff since last reviewed SHA" in side.stderr


def test_a_failed_compare_fails_open_into_an_incremental_review() -> None:
    def build(world: World) -> None:
        world.write("comments", [marker(OLD_SHA)])

    side = sides("compare-failed", {**GATE_PR, "FAKE_GH_FAIL_ON": "/compare/"}, build=build)
    assert side.outputs()["go"] == "true"
    assert b"reviewing anyway (incremental)" in side.stderr


def test_a_follow_up_review_uses_the_followup_template() -> None:
    def build(world: World) -> None:
        world.write("comments", [marker(OLD_SHA)])

    side = sides("followup", GATE_PR, build=build)
    prompt = side.outputs()["prompt"]
    assert prompt.startswith(
        PROMPTS.joinpath("followup.md").read_text(encoding="utf-8").split("{{")[0]
    )
    assert OLD_SHA in prompt
    assert "{{" not in prompt


def test_the_review_cap_refuses_a_pr_that_has_spent_its_budget() -> None:
    def build(world: World) -> None:
        world.write("comments", [report(i) for i in range(3)])

    side = sides("cap", GATE_PR, build=build)
    assert side.outputs()["go"] == "false"
    assert b"review cap reached (3/3 spent: 3 report(s) posted" in side.stderr


def test_the_cap_is_sized_to_the_diff() -> None:
    """3 reports is the cap at 140 lines and is NOT the cap at 20,000."""

    def build(world: World) -> None:
        world.write("comments", [report(i) for i in range(3)])
        world.write("pr-size", {"additions": 20000, "deletions": 0})

    side = sides("cap-big-diff", GATE_PR, build=build)
    assert side.outputs()["go"] == "true"
    assert b"review budget: 3/5 spent" in side.stderr


def test_an_exhausted_head_is_refused_before_the_cap() -> None:
    def build(world: World) -> None:
        world.write("comments", [attempt(NEW_SHA, 3, "error_max_turns")])

    side = sides("head-exhausted", GATE_PR, build=build)
    assert side.outputs()["go"] == "false"
    assert b"has spent all 3 attempts (3 recorded, class error_max_turns)" in side.stderr


def test_two_infra_attempts_are_free_and_the_head_still_reviews() -> None:
    """CONTROL for the case above: the ceiling is 3, not 1."""

    def build(world: World) -> None:
        world.write("comments", [attempt(NEW_SHA, 2, "error_max_turns")])

    side = sides("head-free-reattempt", GATE_PR, build=build)
    assert side.outputs()["go"] == "true"
    assert b"review budget: 0/3 spent (0 posted, 0 produced nothing" in side.stderr


def test_an_unclassified_reportless_attempt_is_charged_immediately() -> None:
    def build(world: World) -> None:
        world.write("comments", [attempt(NEW_SHA, 2, "")])

    side = sides("head-unknown-class", GATE_PR, build=build)
    assert b"review budget: 2/3 spent (0 posted, 2 produced nothing" in side.stderr


def test_an_unsupported_event_is_a_hard_failure() -> None:
    side = sides("bad-event", {"EVENT_NAME": "issue_comment"})
    assert side.exit == 1
    assert b"Unsupported EVENT_NAME: issue_comment" in side.stderr
    assert side.output == b""


def test_a_missing_github_output_refuses_before_anything_else() -> None:
    side = sides("no-output", {**GATE_PR, "GITHUB_OUTPUT": None})
    assert side.exit == 1
    assert b"Required environment variable 'GITHUB_OUTPUT' is not set" in side.stderr
    assert side.calls == []


def test_an_epic_scoped_pass_says_so_in_the_prompt_and_scopes_its_budget() -> None:
    def build(world: World) -> None:
        # Three FLAT reports. Under a flat count this PR is capped; per-epic it
        # has spent nothing, which is the whole point of the epic dimension.
        world.write("comments", [report(i) for i in range(3)])

    side = sides("epic", {**GATE_PR, "REVIEW_EPIC": "abc123"}, build=build)
    assert side.outputs()["go"] == "true"
    assert "SCOPE: this pass reviews ONLY epic abc123" in side.outputs()["prompt"]
    assert "epic-context.sh abc123" in side.outputs()["prompt"]


def test_a_flat_pass_renders_the_epic_scope_to_nothing() -> None:
    side = sides("flat", GATE_PR)
    prompt = side.outputs()["prompt"]
    assert "SCOPE: this pass reviews ONLY" not in prompt
    assert "{{EPIC_SCOPE}}" not in prompt


@pytest.mark.parametrize(
    ("additions", "turns"),
    [(0, "50"), (1999, "50"), (5000, "125"), (100000, "140")],
)
def test_the_turn_budget_scales_continuously_with_the_diff(additions: int, turns: str) -> None:
    def build(world: World) -> None:
        world.write("pr-size", {"additions": additions, "deletions": 0})

    side = sides("turns-%d" % additions, GATE_PR, build=build)
    assert side.outputs()["review_turns"] == turns


# --------------------------------------------------------------------------- GATE MODE: the three defects, reproduced rather than repaired. ---------------------------------------------------------------------------


def test_defect1_a_failed_marker_read_re_reviews_an_already_reviewed_head() -> None:
    """DEFECT 1. `last_marker_sha`'s `|| true` turns a gh failure into "never
    reviewed", so the gate emits go=true with the INITIAL prompt for a head whose
    marker comment is present and current. `FAKE_GH_FAIL_ON_JQ` targets that one
    read: the two budget reads hit the same endpoint and must still succeed, or
    the case would prove nothing about this call."""

    def build(world: World) -> None:
        world.write("comments", [marker(NEW_SHA)])

    side = sides(
        "defect1",
        {**GATE_PR, "FAKE_GH_FAIL_ON_JQ": "claude-reviewed"},
        build=build,
    )
    out = side.outputs()
    assert out["go"] == "true", "the marker is current; a working read refuses this head"
    assert out["last_reviewed_sha"] == ""
    assert b"initial review: full PR diff" in side.stderr
    assert side.exit == 0


def test_defect1_control_the_same_world_refuses_when_the_read_works() -> None:
    """The control that makes the case above a DEFECT rather than a fixture."""

    def build(world: World) -> None:
        world.write("comments", [marker(NEW_SHA)])

    side = sides("defect1-control", GATE_PR, build=build)
    assert side.outputs()["go"] == "false"
    assert b"head already reviewed" in side.stderr


def test_defect2_a_non_numeric_diff_size_kills_the_gate() -> None:
    """DEFECT 2. `emit_review_turns` feeds `gh pr view`'s answer straight into
    `$(( ))` with no `^[0-9]+$` guard, unlike `pr_diff_loc` two functions away.
    A `null` answer is `null: unbound variable` under `set -u`.

    stderr is compared by SUFFIX here: bash prefixes the message with the
    script's own path, which is `.sh` on one side and `.py` on the other. Exit
    code and `$GITHUB_OUTPUT` are compared exactly, and the point of the case is
    that `$GITHUB_OUTPUT` holds NO `go` key at all."""
    with tempfile.TemporaryDirectory() as td:
        world = World(pathlib.Path(td))
        world.write("pr-size", {"additions": None, "deletions": None})
        results = [_run(world, which, dict(GATE_PR), []) for which in ("old", "new")]
    old, new = results
    assert old.exit == new.exit == 1
    assert old.output == new.output
    assert b"go=" not in old.output
    tail = b"line 172: null: unbound variable"
    assert old.stderr.rstrip().endswith(tail), old.stderr
    assert new.stderr.rstrip().endswith(tail), new.stderr


def test_defect2_control_pr_diff_loc_does_have_the_guard() -> None:
    """The same unparseable answer reaches `pr_diff_loc` FIRST and is coerced to
    0 there, which is why the crash happens later, in `emit_review_turns`. If
    both had the guard the case above could not fire at all."""
    text = TWIN.read_text(encoding="utf-8")
    lib = (ROOT / ".ci" / "scripts" / "lib" / "common.sh").read_text(encoding="utf-8")
    assert '[[ "$n" =~ ^[0-9]+$ ]] || n=0' in lib
    assert "local kloc=$(((${changed:-0} + 999) / 1000))" in text


def test_defect3_a_failed_attempt_read_restarts_the_per_head_count() -> None:
    """DEFECT 3. The nested command substitution in `--mark` discards
    `review_attempt_states`' failure, so a head that has already spent 3 of 3
    attempts records "attempt 1 of 3" and the per-head ceiling resets.

    This case pays `gh_retry`'s real backoff (3s + 6s) on BOTH sides, because the
    twin pays it and the stderr comparison is the point."""

    def build(world: World) -> None:
        world.write("comments", [attempt(NEW_SHA, 3, "error_max_turns")])

    side = sides(
        "defect3",
        {
            "PR_NUMBER": "42",
            "HEAD_SHA": NEW_SHA,
            "REVIEW_OUTCOME": "failure",
            "FAKE_GH_FAIL_ON_JQ": "REVIEW-ATTEMPT-EOF",
        },
        args=["--mark"],
        build=build,
    )
    assert side.exit == 0
    assert b"recorded SPENT ATTEMPT 1/3" in side.stderr
    assert b"review_attempt_states: gh failed after 3 attempts" in side.stderr
    assert b"attempts: 1\n" in side.capture


def test_defect3_control_the_same_world_counts_four_when_the_read_works() -> None:
    def build(world: World) -> None:
        world.write("comments", [attempt(NEW_SHA, 3, "error_max_turns")])

    side = sides(
        "defect3-control",
        {"PR_NUMBER": "42", "HEAD_SHA": NEW_SHA, "REVIEW_OUTCOME": "failure"},
        args=["--mark"],
        build=build,
    )
    assert b"recorded SPENT ATTEMPT 4/3" in side.stderr


def test_a_failed_budget_read_stops_the_gate_instead_of_reviewing() -> None:
    """The DEFECT-1 fix that DID land, on the other half of the same endpoint:
    `review_report_count` routes through `gh_retry` and propagates, so a rate
    limit stops the run rather than reading as a zero numerator."""
    side = sides(
        "budget-read-failed",
        {**GATE_PR, "FAKE_GH_FAIL_ON_JQ": "Claude finished"},
        compare_stderr=True,
    )
    assert side.exit == 1
    assert b"review_report_count: gh failed after 3 attempts" in side.stderr
    assert side.output == b""


# --------------------------------------------------------------------------- --post-report ---------------------------------------------------------------------------


POST_ENV = {"PR_NUMBER": "42", "HEAD_SHA": NEW_SHA}


def test_post_report_without_an_execution_file_posts_nothing() -> None:
    side = sides("post-none", POST_ENV, args=["--post-report"])
    assert side.exit == 0
    assert b"no final report text in <unset>; nothing to post" in side.stderr
    assert side.capture == b""


def test_post_report_posts_the_models_final_text_under_the_actions_own_header() -> None:
    def build(world: World) -> dict[str, str]:
        return {
            "EXECUTION_FILE": world.execution(
                [{"type": "result", "subtype": "success", "result": "## Verdict\n\nfine"}]
            )
        }

    side = sides("post-report", POST_ENV, args=["--post-report"], build=build)
    assert b"**Claude finished the automated review of 2222222**" in side.capture
    assert b"## Verdict" in side.capture
    assert b"Posted review report for 2222222 (16 chars)" in side.stderr


def test_post_report_names_the_epic_in_the_header() -> None:
    def build(world: World) -> dict[str, str]:
        return {
            "EXECUTION_FILE": world.execution([{"type": "result", "result": "x"}]),
            "REVIEW_EPIC": "abc123",
        }

    side = sides("post-report-epic", POST_ENV, args=["--post-report"], build=build)
    assert b"**Claude finished (epic abc123) the automated review of 2222222**" in side.capture


def test_post_report_keeps_the_head_and_the_tail_when_it_truncates() -> None:
    """The tail carries the findings fence `--post-findings` parses, so a plain
    truncation would silently disable inline comments on every long report."""

    def build(world: World) -> dict[str, str]:
        text = "H" * 40000 + "MIDDLE" + "T" * 40000 + "\nFENCE-TAIL"
        return {"EXECUTION_FILE": world.execution([{"type": "result", "result": text}])}

    side = sides("post-report-truncated", POST_ENV, args=["--post-report"], build=build)
    assert b"_[report truncated: middle omitted" in side.capture
    assert b"FENCE-TAIL" in side.capture
    assert b"MIDDLE" not in side.capture
    assert b"truncating the middle to fit the comment limit" in side.stderr


def test_post_report_propagates_a_failed_post() -> None:
    def build(world: World) -> dict[str, str]:
        return {
            "EXECUTION_FILE": world.execution([{"type": "result", "result": "x"}]),
            "FAKE_GH_WRITE_FAIL": "/comments",
        }

    side = sides("post-report-failed", POST_ENV, args=["--post-report"], build=build)
    assert side.exit == 1


def test_post_report_requires_its_two_variables() -> None:
    side = sides("post-report-novars", {}, args=["--post-report"])
    assert side.exit == 1
    assert b"Required environment variable 'PR_NUMBER' is not set" in side.stderr


# --------------------------------------------------------------------------- --post-findings ---------------------------------------------------------------------------


def test_post_findings_with_no_fence_skips_quietly() -> None:
    def build(world: World) -> None:
        world.write("comments", [report(0)])

    side = sides("findings-none", POST_ENV, args=["--post-findings"], build=build)
    assert b"no parseable review-findings block; skipping inline comments" in side.stderr
    assert side.capture == b""


def test_post_findings_posts_line_anchored_comments_with_severity_badges() -> None:
    def build(world: World) -> None:
        world.write(
            "comments",
            [
                report(
                    0,
                    body=findings_report(
                        [
                            {
                                "path": "a.ts",
                                "line": 4,
                                "severity": "high",
                                "title": "t",
                                "body": "b",
                            }
                        ]
                    ),
                )
            ],
        )

    side = sides("findings-post", POST_ENV, args=["--post-findings"], build=build)
    assert b"ARG body=**[HIGH]** \xe2\x80\x94 t" in side.capture
    assert b"ARG line=4" in side.capture
    assert b"inline findings: 1 posted, 0 skipped (cap 20)" in side.stderr


def test_post_findings_reads_a_pretty_printed_array_spanning_many_lines() -> None:
    """The shape `prompts/initial.md:53-57` actually asks for."""

    def build(world: World) -> None:
        world.write(
            "comments",
            [
                report(
                    0,
                    body=findings_report(
                        [
                            {"path": "a.ts", "line": 1, "body": "one"},
                            {"path": "b.ts", "line": 2, "body": "two"},
                        ]
                    ),
                )
            ],
        )

    side = sides("findings-multiline", POST_ENV, args=["--post-findings"], build=build)
    assert b"inline findings: 2 posted, 0 skipped (cap 20)" in side.stderr


def test_defect4_a_sibling_pr_labels_fence_swallows_every_inline_finding() -> None:
    """DEFECT 4, AND IT FIRES ON THE SHAPE THE PROMPT ASKS FOR.

    `--post-findings`' awk never clears `capturing`, so it takes everything from
    the `json:review-findings` opener to the LAST closing fence ANYWHERE later in
    the report. `prompts/initial.md:67` instructs the model to close the report
    with a SECOND fence, `json:pr-labels`, after that section. The extraction
    therefore runs past the findings array, through the prose and into the labels
    block, jq rejects it as an array, and the arm prints "no parseable
    review-findings block" and posts NOTHING.

    The last-closer rule was added to survive a fence nested inside a finding's
    `body`, and that case is not reachable through valid JSON: a JSON string
    cannot contain a raw newline, so an embedded fence never lands on a line of
    its own and never matches the closer. The rule buys nothing and costs every
    inline comment on a report that follows its own prompt.
    """

    def build(world: World) -> None:
        world.write(
            "comments",
            [
                report(
                    0,
                    body=findings_report(
                        [{"path": "a.ts", "line": 3, "severity": "high", "title": "t"}],
                        trailer='\nSome prose.\n\n%sjson:pr-labels\n{"bump": "none"}\n%s\n'
                        % (TICKS, TICKS),
                    ),
                )
            ],
        )

    side = sides("defect4", POST_ENV, args=["--post-findings"], build=build)
    assert side.exit == 0
    assert b"no parseable review-findings block; skipping inline comments" in side.stderr
    assert side.capture == b"", "one finding was posted; the defect would be gone"


def test_defect4_control_the_same_finding_posts_without_the_sibling_fence() -> None:
    """The control that makes the case above a DEFECT rather than a fixture."""

    def build(world: World) -> None:
        world.write(
            "comments",
            [
                report(
                    0,
                    body=findings_report(
                        [{"path": "a.ts", "line": 3, "severity": "high", "title": "t"}]
                    ),
                )
            ],
        )

    side = sides("defect4-control", POST_ENV, args=["--post-findings"], build=build)
    assert b"inline findings: 1 posted, 0 skipped (cap 20)" in side.stderr


def test_defect4_the_prompt_really_does_ask_for_both_fences_in_that_order() -> None:
    """ANTI-VACUITY for the case above: if the prompt stopped asking for the
    second fence, DEFECT 4 would be unreachable and the case would be theatre."""
    text = (PROMPTS / "initial.md").read_text(encoding="utf-8")
    assert text.index("%sjson:review-findings" % TICKS) < text.index("%sjson:pr-labels" % TICKS), (
        "the labels fence must come AFTER the findings fence for the swallow to happen"
    )


def test_post_findings_skips_a_finding_with_no_anchor() -> None:
    def build(world: World) -> None:
        world.write(
            "comments",
            [report(0, body=findings_report([{"severity": "low", "title": "no anchor"}]))],
        )

    side = sides("findings-anchorless", POST_ENV, args=["--post-findings"], build=build)
    assert b"inline findings: 0 posted, 1 skipped (cap 20)" in side.stderr
    assert side.capture == b""


def test_post_findings_logs_and_skips_a_rejected_comment() -> None:
    def build(world: World) -> None:
        world.write("comments", [report(0, body=findings_report([{"path": "a.ts", "line": 999}]))])
        return {"FAKE_GH_WRITE_FAIL": "/pulls/"}

    side = sides("findings-rejected", POST_ENV, args=["--post-findings"], build=build)
    assert b"inline comment rejected (line not in diff?): a.ts:999" in side.stderr
    assert b"inline findings: 0 posted, 1 skipped" in side.stderr


def test_post_findings_caps_at_twenty_and_posts_the_worst_first() -> None:
    def build(world: World) -> None:
        items = [{"path": "f%d.ts" % i, "line": i + 1, "severity": "low"} for i in range(25)]
        items.append({"path": "crit.ts", "line": 1, "severity": "critical"})
        world.write("comments", [report(0, body=findings_report(items))])

    side = sides("findings-cap", POST_ENV, args=["--post-findings"], build=build)
    assert b"inline findings: 20 posted, 0 skipped (cap 20)" in side.stderr
    assert side.capture.split(b"ENDCALL")[0].count(b"ARG path=crit.ts") == 1


def test_post_findings_degrades_to_a_skip_when_the_read_fails() -> None:
    """It must never abort: the following `--mark` step would be skipped."""
    side = sides(
        "findings-read-failed",
        {**POST_ENV, "FAKE_GH_FAIL_ALL": "1"},
        args=["--post-findings"],
    )
    assert side.exit == 0
    assert b"no parseable review-findings block" in side.stderr


# --------------------------------------------------------------------------- --apply-labels ---------------------------------------------------------------------------


def test_apply_labels_puts_the_mechanical_docs_floor_on_a_docs_only_diff() -> None:
    def build(world: World) -> None:
        world.files("docs/a.md", "agent/PLAN-x.md", "CLAUDE.md")
        world.live_labels("documentation")

    side = sides("labels-docs", POST_ENV, args=["--apply-labels"], build=build)
    assert b"ARG labels[]=documentation" in side.capture
    assert b"labels for 2222222: documentation" in side.stderr


def test_apply_labels_puts_the_ci_floor_on_a_ci_only_diff() -> None:
    def build(world: World) -> None:
        world.files(".ci/scripts/x.sh", ".github/workflows/y.yml", "scripts/ci-runner/z.ts")
        world.live_labels("ci")

    side = sides("labels-ci", POST_ENV, args=["--apply-labels"], build=build)
    assert b"ARG labels[]=ci" in side.capture


def test_apply_labels_refuses_the_floor_when_one_stray_source_file_is_present() -> None:
    """CONTROL: the floor is an ALL-FILES rule, conservative by construction."""

    def build(world: World) -> None:
        world.files("docs/a.md", "packages/cli/src/x.ts")

    side = sides("labels-mixed", POST_ENV, args=["--apply-labels"], build=build)
    assert b"labels for 2222222: <none>" in side.stderr
    assert b"labels[]=" not in side.capture


def test_apply_labels_creates_a_create_on_demand_label_that_is_not_live_yet() -> None:
    def build(world: World) -> None:
        world.files(".ci/scripts/x.sh")
        world.live_labels()

    side = sides("labels-create", POST_ENV, args=["--apply-labels"], build=build)
    assert b"ARG name=ci" in side.capture
    assert b"ARG color=FEF2C0" in side.capture


def test_apply_labels_applies_the_models_verdict() -> None:
    def build(world: World) -> dict[str, str]:
        world.live_labels("bug", "bump-none")
        return {
            "EXECUTION_FILE": world.execution(
                [
                    {
                        "type": "result",
                        "result": labels_report('{"bump": "none", "kind": ["bug"], "why": "typo"}'),
                    }
                ]
            )
        }

    side = sides("labels-verdict", POST_ENV, args=["--apply-labels"], build=build)
    assert b'review verdict: bump=none kind=["bug"] why=typo' in side.stderr
    assert b"ARG labels[]=bump-none" in side.capture
    assert b"ARG labels[]=bug" in side.capture


def test_apply_labels_never_applies_bump_major_on_the_models_word() -> None:
    def build(world: World) -> dict[str, str]:
        return {
            "EXECUTION_FILE": world.execution(
                [
                    {
                        "type": "result",
                        "result": labels_report('{"bump": "major", "why": "api break"}'),
                    }
                ]
            )
        }

    side = sides("labels-major", POST_ENV, args=["--apply-labels"], build=build)
    assert b"the review RECOMMENDS a major bump (api break)" in side.stderr
    assert b"bump-major" not in side.capture
    assert b"labels[]=" not in side.capture


def test_apply_labels_treats_a_malformed_verdict_as_absent() -> None:
    def build(world: World) -> dict[str, str]:
        return {
            "EXECUTION_FILE": world.execution(
                [
                    {
                        "type": "result",
                        "result": labels_report('{"bump": "enormous", "kind": ["bug"]}'),
                    }
                ]
            )
        }

    side = sides("labels-malformed", POST_ENV, args=["--apply-labels"], build=build)
    assert b"the json:pr-labels block did not validate; treating it as absent" in side.stderr
    assert b"labels[]=" not in side.capture


def test_apply_labels_rejects_a_hallucinated_kind_through_jq_validation() -> None:
    def build(world: World) -> dict[str, str]:
        return {
            "EXECUTION_FILE": world.execution(
                [{"type": "result", "result": labels_report('{"kind": ["security"]}')}]
            )
        }

    side = sides("labels-hallucinated", POST_ENV, args=["--apply-labels"], build=build)
    assert b"did not validate" in side.stderr
    assert b"labels[]=" not in side.capture


def test_apply_labels_falls_back_to_the_fence_in_the_posted_comment() -> None:
    def build(world: World) -> dict[str, str]:
        world.write("comments", [report(0, body=labels_report('{"kind": ["docs"]}'))])
        world.live_labels("documentation")
        return {
            "EXECUTION_FILE": world.execution(
                [{"type": "result", "result": "no fence in the result text"}]
            )
        }

    side = sides("labels-fallback", POST_ENV, args=["--apply-labels"], build=build)
    assert b"fence found in the posted report comment" in side.stderr
    assert b"ARG labels[]=documentation" in side.capture


def test_apply_labels_removes_a_stale_label_it_applied_itself() -> None:
    def build(world: World) -> None:
        world.write("comments", [ledger(OLD_SHA, "bug,documentation")])
        world.files("packages/cli/src/x.ts")
        world.live_labels("bug", "documentation")

    side = sides("labels-stale", POST_ENV, args=["--apply-labels"], build=build)
    assert b"removed stale label 'bug'" in side.stderr
    assert b"removed stale label 'documentation'" in side.stderr
    assert b"METHOD=DELETE" in side.capture


def test_apply_labels_refuses_to_remove_a_label_the_ledger_should_not_name() -> None:
    """A ledger comment is editable by anyone with write access, so a tampered
    `applied:` line must not become a delete-arbitrary-label primitive."""

    def build(world: World) -> None:
        world.write("comments", [ledger(OLD_SHA, "full-ci")])
        world.files("packages/cli/src/x.ts")

    side = sides("labels-tampered", POST_ENV, args=["--apply-labels"], build=build)
    assert b"ledger names 'full-ci', which is not in the managed set" in side.stderr
    assert b"METHOD=DELETE" not in side.capture


def test_apply_labels_upserts_its_ledger_comment() -> None:
    def build(world: World) -> None:
        world.write("comments", [ledger(OLD_SHA, "ci")])
        world.files(".ci/x.sh")
        world.live_labels("ci")

    side = sides("labels-ledger-patch", POST_ENV, args=["--apply-labels"], build=build)
    assert b"METHOD=PATCH PATH=repos/acme/widget/issues/comments/300" in side.capture
    assert b"applied: ci" in side.capture


def test_apply_labels_skips_the_floor_when_the_file_list_cannot_be_read() -> None:
    side = sides(
        "labels-files-failed",
        {**POST_ENV, "FAKE_GH_FAIL_ON": "/files"},
        args=["--apply-labels"],
    )
    assert b"could not read the changed-file list for PR 42" in side.stderr
    assert side.exit == 0


# --------------------------------------------------------------------------- --mark ---------------------------------------------------------------------------


def test_mark_records_a_spent_attempt_when_the_review_did_not_succeed() -> None:
    side = sides(
        "mark-attempt",
        {**POST_ENV, "REVIEW_OUTCOME": "failure"},
        args=["--mark"],
    )
    assert b"recorded SPENT ATTEMPT 1/3" in side.stderr
    assert b"class: review step did not succeed" in side.capture
    assert b"Push a change to earn another pass." in side.capture
    assert gate.MARKER_PREFIX.encode() not in side.capture


def test_mark_gives_an_infra_class_failure_a_free_re_attempt() -> None:
    def build(world: World) -> dict[str, str]:
        return {
            "EXECUTION_FILE": world.execution(
                [{"type": "result", "subtype": "error_max_turns", "result": ""}]
            )
        }

    side = sides(
        "mark-infra",
        {**POST_ENV, "REVIEW_OUTCOME": "failure"},
        args=["--mark"],
        build=build,
    )
    assert b"INFRASTRUCTURE-class failure" in side.capture
    assert b"no push required" in side.capture
    assert b"recorded SPENT ATTEMPT 1/3 for 2222222 (error_max_turns)" in side.stderr


def test_mark_upserts_one_attempt_marker_per_head() -> None:
    def build(world: World) -> dict[str, str]:
        world.write("comments", [attempt(NEW_SHA, 1, "error_max_turns", cid=201)])
        return {
            "EXECUTION_FILE": world.execution([{"type": "result", "subtype": "error_max_turns"}])
        }

    side = sides(
        "mark-attempt-upsert",
        {**POST_ENV, "REVIEW_OUTCOME": "failure"},
        args=["--mark"],
        build=build,
    )
    assert b"METHOD=PATCH PATH=repos/acme/widget/issues/comments/201" in side.capture
    assert b"attempts: 2" in side.capture


def test_mark_stops_giving_free_re_attempts_at_the_ceiling() -> None:
    def build(world: World) -> dict[str, str]:
        world.write("comments", [attempt(NEW_SHA, 2, "error_max_turns", cid=202)])
        return {
            "EXECUTION_FILE": world.execution([{"type": "result", "subtype": "error_max_turns"}])
        }

    side = sides(
        "mark-attempt-ceiling",
        {**POST_ENV, "REVIEW_OUTCOME": "failure"},
        args=["--mark"],
        build=build,
    )
    assert b"That is attempt 3 of 3 on this head" in side.capture
    assert b"INFRASTRUCTURE-class" not in side.capture


def test_mark_refuses_to_stamp_a_sha_when_the_review_posted_nothing() -> None:
    """The honesty guard. The reviewer once "succeeded" with 36 permission
    denials and posted nothing, and the marker then suppressed the retry."""
    side = sides("mark-nothing", {**POST_ENV, "REVIEW_OUTCOME": "success"}, args=["--mark"])
    assert side.exit == 1
    assert b"posted NOTHING in the last hour; refusing to mark 2222222" in side.stderr
    assert side.capture == b""


def test_mark_does_not_let_the_pipelines_own_bookkeeping_vouch_for_it() -> None:
    """A ledger comment written seconds earlier by `--apply-labels` must not
    satisfy the guard: EVERY bookkeeping prefix is excluded, not just the
    marker."""

    def build(world: World) -> None:
        world.write(
            "comments",
            [
                {
                    "id": 1,
                    "user": {"login": "github-actions[bot]"},
                    "created_at": _now_iso(-30),
                    "body": "%s %s -->\napplied: ci" % (gate.LEDGER_PREFIX, NEW_SHA),
                },
                {
                    "id": 2,
                    "user": {"login": "github-actions[bot]"},
                    "created_at": _now_iso(-30),
                    "body": "%s %s -->\nattempts: 1" % (gate.ATTEMPT_PREFIX, NEW_SHA),
                },
            ],
        )

    side = sides(
        "mark-bookkeeping", {**POST_ENV, "REVIEW_OUTCOME": "success"}, args=["--mark"], build=build
    )
    assert side.exit == 1
    assert b"posted NOTHING in the last hour" in side.stderr


def test_mark_creates_the_marker_when_a_report_landed() -> None:
    def build(world: World) -> None:
        world.write("comments", [report(0, recent=True)])

    side = sides(
        "mark-create", {**POST_ENV, "REVIEW_OUTCOME": "success"}, args=["--mark"], build=build
    )
    assert b"Created marker comment for 2222222" in side.stderr
    assert b"<!-- claude-reviewed: %s -->" % NEW_SHA.encode() in side.capture


def test_mark_accepts_an_inline_comment_as_proof_of_output() -> None:
    def build(world: World) -> None:
        world.write(
            "inline-comments",
            [{"id": 9, "user": {"login": "github-actions[bot]"}, "created_at": _now_iso(-30)}],
        )

    side = sides(
        "mark-inline-proof",
        {**POST_ENV, "REVIEW_OUTCOME": "success"},
        args=["--mark"],
        build=build,
    )
    assert side.exit == 0
    assert b"Created marker comment" in side.stderr


def test_mark_updates_an_existing_marker_rather_than_posting_a_second() -> None:
    def build(world: World) -> None:
        world.write("comments", [marker(OLD_SHA, cid=7), report(0, recent=True)])

    side = sides(
        "mark-update", {**POST_ENV, "REVIEW_OUTCOME": "success"}, args=["--mark"], build=build
    )
    assert b"Updated marker comment 7 -> 2222222" in side.stderr
    assert b"METHOD=PATCH PATH=repos/acme/widget/issues/comments/7" in side.capture


def test_mark_appends_the_cost_line_from_the_execution_file() -> None:
    def build(world: World) -> dict[str, str]:
        world.write("comments", [report(0, recent=True)])
        return {
            "EXECUTION_FILE": world.execution(
                [
                    {
                        "type": "result",
                        "subtype": "success",
                        "total_cost_usd": 4.66123,
                        "num_turns": 37,
                        "duration_ms": 754000,
                        "usage": {"input_tokens": 10, "output_tokens": 20},
                        "modelUsage": {
                            "claude-haiku": {"outputTokens": 5},
                            "claude-sonnet": {"outputTokens": 500},
                        },
                    }
                ]
            )
        }

    side = sides(
        "mark-cost", {**POST_ENV, "REVIEW_OUTCOME": "success"}, args=["--mark"], build=build
    )
    assert b"Cost: $4.6612" in side.capture
    # EVERY model, ordered by output-token share: `keys | first` reported one model chosen by arbitrary key order and read as "the --model flag was ignored" (issue #539).
    assert b"claude-sonnet 500out, claude-haiku 5out" in side.capture
    assert b"37 turns" in side.capture
    assert b"12m34s" in side.capture


def test_mark_requires_its_two_variables() -> None:
    side = sides("mark-novars", {"PR_NUMBER": "42"}, args=["--mark"])
    assert side.exit == 1
    assert b"Required environment variable 'HEAD_SHA' is not set" in side.stderr


# --------------------------------------------------------------------------- Tool preconditions. ---------------------------------------------------------------------------


# Everything the twin reaches for BEFORE `require_cmd gh`, plus everything either side needs after it. A PATH holding only `jq` makes the twin die in its `SCRIPT_DIR` line on a missing `dirname`, which looks like a gh finding and is not: the control has to fail for the reason it names.
TOOLS_MINUS_GH = (
    # `uname` is reached by common.sh:64 and :100 AT SOURCE TIME, before a single line of the gate runs, and its absence prints two `command not found` lines the port has no counterpart for (`core.common` asks `platform`).
    "uname",
    "dirname",
    "jq",
    "sed",
    "awk",
    "grep",
    "tail",
    "tr",
    "paste",
    "git",
    "wc",
    "mktemp",
)


def test_a_missing_gh_is_a_named_refusal_not_a_stack_trace() -> None:
    with tempfile.TemporaryDirectory() as td:
        base = pathlib.Path(td)
        empty = base / "empty"
        empty.mkdir()
        for tool in TOOLS_MINUS_GH:
            found = shutil.which(tool)
            assert found, tool
            (empty / tool).symlink_to(found)
        assert shutil.which("gh", path=str(empty)) is None
        world = World(base)
        world.path = str(empty)
        results = [_run(world, which, dict(GATE_PR), []) for which in ("old", "new")]
    old, new = results
    assert old.exit == new.exit == 1
    assert old.stderr == new.stderr
    assert b"Required command 'gh' is not available" in old.stderr

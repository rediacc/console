#!/usr/bin/env python3
"""Port of `.ci/scripts/review/review-status.sh`, the "Review Complete" check-run reporter.

THE SHAPE OF THE THING FIRST, because nothing else here makes sense without it. This is not a CI job and must never become one. Console CI's old `Review Gate` ran on `pull_request` -- BEFORE the review it is named after can have happened -- and asserted nothing about WHICH commit was reviewed. The assertion cannot move into CI either, because the review only starts once CI is
green, so a CI job that waits for the review deadlocks the pipeline that produces it. The verdict is therefore posted as an INDEPENDENT check-run from a workflow no CI job references. That acyclicity is the property to preserve: never add a `needs:` or a `wait-for` on `Review Complete` anywhere inside Console CI.

TWO ASSERTIONS, and the second one is three subprocesses:

    CURRENCY  the reviewed-SHA marker comment must name the PR's CURRENT head,
              or the diff marker...head must be empty or submodule-gitlink only.
    HYGIENE   `check_resolved_threads.py`, `check_review_comments.py` and
              `check_review_report_replies.py` must all pass, unchanged.

FOUR CONCLUSIONS. `success` when current and clean; `success` WITH A WARNING when the review budget is exhausted and the marker is stale; `neutral` for a draft; `failure` for a stale head, a failed triggering review run, or a failing hygiene script.

THE EXIT CODE IS NOT THE VERDICT. The script exits 0 after posting a `failure` conclusion, because the verdict lives in the check-run and a red JOB would be a second, confusing signal on the same head. A non-zero exit always means the REPORTER broke.

-----------------------------------------------------------------------------
THE DEADLOCK GUARD IS THE REASON THIS FILE IS DELICATE
-----------------------------------------------------------------------------
Once a PR reaches its review cap the gate script refuses to review again, so the marker can NEVER advance to the current head. Failing here would make the PR permanently unmergeable through no fault of its author. That is not a hypothetical: `common.sh:623-632` records PR #553 (2026-08-07) reading 3/3 in the gate and 0/3 here at the same moment, green, ready, thread-clean and
unmergeable. So there are TWO passing-with-a-warning arms -- the PR-wide cap, and the per-head attempt ceiling one level down -- and both are driven in the differential.

-----------------------------------------------------------------------------
THE BUDGET COMES FROM `core.review_budget`, NOT FROM A SECOND COPY
-----------------------------------------------------------------------------
`review_spend_total`, `review_cap_for`, `review_attempt_states`, `review_head_is_exhausted` and `pr_diff_loc` are the review-budget half of `common.sh`, already ported at `core.review_budget`, whose own docstring names THIS script as one of its two live callers and quotes the reason they live in one place: "the two disagreeing about the cap resurrects exactly the deadlock
review-status.sh was written to prevent. One table, one function, both callers." Re-transliterating them here would be that second copy.

TWO DIFFERENCES THE REUSE BUYS, both named rather than hidden:

  * ARGV SHAPE. The twin's `review_report_count` filters server-side with
    `gh api ... --jq '.[] | select(...) | .id'`; `review_budget.report_count`
    fetches the page and filters in Python. Same endpoint, same page, same
    count -- a different command line. The differential compares the
    NORMALISED call log (method and path, in order) for that reason, and
    compares raw argv for every call this file makes itself.
  * FAILURE SURFACE. `gh_retry` prints its three attempts and replays gh's
    stderr indented four spaces; `core.ghx` raises a typed error. The EXIT CODE
    is the same (1, via `set -e` on the `|| return 1`), the words on stderr are
    not. `pr_diff_loc` is passed `on_error=DIFF_LOC_FAILS_TO_ZERO` explicitly,
    which is the twin's stated decision (`common.sh:764-765`) made visible at
    the call site.

-----------------------------------------------------------------------------
`jq` BUILDS THE CHECK-RUN PAYLOAD, and that is not laziness
-----------------------------------------------------------------------------
`jq -n --arg ...` is what produces the bytes that go up to GitHub, including jq's own two-space indentation and key order, and `jq 'del(.head_sha)'` is what strips the one field a PATCH rejects. Those bytes are the product. They are handed to the same jq here, so a differential can compare the payload byte for byte -- which it does, on every case that writes.

`--arg` ALSO KEEPS MODEL- AND USER-AUTHORED TEXT OUT OF THE SHELL. The summary carries hygiene-script output verbatim; nothing is interpolated into a command line on either side.

-----------------------------------------------------------------------------
THE CONSTANTS ARE READ OUT OF `claude-review-gate.sh`, NOT COPIED
-----------------------------------------------------------------------------
Two files disagreeing about `MARKER_PREFIX` makes this check silently unable to find any marker -- every head then reads as unreviewed. A parse failure is FATAL rather than defaulted, and the `ATTEMPT_PREFIX` failure message spells out the consequence (the cap reads lower here than in the gate and the deadlock guard cannot fire, the #553 mode). `parse_prefix` is the twin's `sed`
program as a regex, driven against real `sed` in the differential rather than assumed equivalent.

-----------------------------------------------------------------------------
WHERE THE DEFAULT PATHS COME FROM, since this file moved
-----------------------------------------------------------------------------
The twin defaults `HYGIENE_DIR` to `$SCRIPT_DIR/../quality` and `GATE_SCRIPT` to `$SCRIPT_DIR/claude-review-gate.sh`, both relative to `.ci/scripts/review/`. This module lives in `.ci/rediacc_ci/review/`, where the same expressions would resolve to `.ci/rediacc_ci/quality` -- the Python package, not the directory of executables the twin runs. `twin_script_dir()` therefore names the
TWIN's directory explicitly, so both sides reach the same two real paths. The two test seams (`REVIEW_STATUS_HYGIENE_DIR`, `REVIEW_STATUS_GATE_SCRIPT`) are unchanged.

THE HYGIENE SCRIPTS ARE THE `.py` PORTS, and the twin says why: W7 P4 cut them over on 2026-09-08, so CI invokes `check_<name>.py` and a pipeline still running the `.sh` would be proving a file CI no longer uses. Each is executed DIRECTLY, not through `bash`, so the shebang picks the interpreter.

-----------------------------------------------------------------------------
ONE HAZARD, REPORTED RATHER THAN REPAIRED
-----------------------------------------------------------------------------
The `workflow_run` arm requires `WR_RUN_ID` but the other four events require only `PR_NUMBER`, and `PR_NUMBER` is used verbatim in an API path. A non-numeric `PR_NUMBER` therefore reaches `gh api repos/<repo>/pulls/<junk>` and dies with gh's own 404 message and gh's exit code, after `require_var` has already passed -- there is no numeric validation anywhere. Nothing is
interpolated into a shell on either side, so this is a bad-input path with a confusing diagnostic rather than a security hole, and tightening it changes a live workflow step's contract. Pinned by `test_a_non_numeric_pr_number_reaches_the_api_unvalidated`.

Exit: 0 whatever the conclusion, including `failure`; non-zero only when the reporter itself could not do its job.

K=5 LEDGER: `.ci/shadow/w7p6-review-status.observations.jsonl`.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

from rediacc_ci import log
from rediacc_ci.core import common, ghx, review_budget

DEFAULT_CHECK_NAME = "Review Complete"

# The three hygiene scripts, in the twin's order. THE PORTS, not the twins.
HYGIENE_SCRIPTS = (
    "check_resolved_threads.py",
    "check_review_comments.py",
    "check_review_report_replies.py",
)

# The five events this reporter answers to. `workflow_run` resolves the PR from an artifact; the other four are handed a number.
EVENT_WORKFLOW_RUN = "workflow_run"
EVENTS_WITH_PR_NUMBER = (
    "pull_request_review",
    "pull_request_review_comment",
    "issue_comment",
    "workflow_dispatch",
)

# `WR_CONCLUSION` values that mean no verdict was produced. `cancelled` is deliberately absent: Claude Review runs with cancel-in-progress, so a superseded push cancels the older run BY DESIGN and a newer run is already on its way.
FAILED_CONCLUSIONS = ("failure", "timed_out")

ARTIFACT_NAME = "review-target"
ARTIFACT_MEMBER = "review-target.txt"

# `sed -n "s/^NAME='\(.*\)'[[:space:]]*$/\1/p"`. GREEDY on purpose, like the
# sed: a line with two quoted runs yields everything between the first and the last quote. `[[:space:]]` inside a line is space, tab, vertical tab, form feed and carriage return -- not the newline, which sed never sees inside a line.
PREFIX_RE = "^%s='(.*)'[ \t\v\f\r]*$"

# `sed -n 's/.*claude-reviewed: \([0-9a-f]\{40\}\).*/\1/p'` over the marker
# bodies. Lowercase hex, exactly 40, and the LAST match across all lines wins (`| tail -n 1`) -- never the first, because a marker body is multi-line.
MARKER_SHA_RE = re.compile(r".*claude-reviewed: ([0-9a-f]{40}).*")

# `git config -f .gitmodules --get-regexp '^submodule\..*\.path$'`.
GITMODULES_PATH_RE = r"^submodule\..*\.path$"

FOOTER = (
    "\n\n_This check is posted by `.ci/scripts/review/review-status.sh` from a "
    "workflow no CI job references, so it can never block Console CI._"
)


class ReporterError(Exception):
    """The reporter itself broke: a message already logged, and an exit code.

    Distinct from a `failure` CONCLUSION, which is a healthy run reporting an unhealthy PR and exits 0.
    """

    def __init__(self, code: int = 1) -> None:
        super().__init__("reporter failed with %d" % code)
        self.code = code


def twin_script_dir(root: pathlib.Path | None = None) -> pathlib.Path:
    """`.ci/scripts/review/`, the TWIN's `SCRIPT_DIR`. See the module docstring."""
    base = pathlib.Path(__file__).resolve().parents[3] if root is None else pathlib.Path(root)
    return base / ".ci" / "scripts" / "review"


def parse_prefix(text: str, name: str) -> str:
    """The twin's `sed` + `${VAR%%$'\\n'*}`: the FIRST matching line's capture.

    sed prints one line per match and the parameter expansion then keeps only
    the first, so a gate script with two `MARKER_PREFIX=` assignments is read as
    its first one. Reproduced, and driven against real `sed` in the tests.
    """
    matches = re.findall(PREFIX_RE % re.escape(name), text, re.MULTILINE)
    return matches[0] if matches else ""


def _gh(args: list[str], *, quiet: bool = False) -> tuple[int, bytes]:
    """One `gh` call, no retry, stdout captured.

    `quiet` is the twin's `2>/dev/null` on the calls that are allowed to fail;
    everywhere else gh's stderr is INHERITED, which is how a caller learns what 404'd on the paths that end the run.
    """
    try:
        proc = subprocess.run(
            ["gh", *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL if quiet else None,
            check=False,
        )
    except OSError:
        return 127, b""
    return proc.returncode, proc.stdout or b""


def _jq(args: list[str], stdin: bytes | None = None) -> tuple[int, bytes]:
    """`jq` with stderr inherited and stdout captured."""
    proc = subprocess.run(
        ["jq", *args],
        input=stdin if stdin is not None else b"",
        stdout=subprocess.PIPE,
        check=False,
    )
    return proc.returncode, proc.stdout or b""


def last_marker_sha(repo: str, pr: str, prefix: str) -> str:
    """The NEWEST reviewed-SHA marker on the PR, or "".

    Same shape as `claude-review-gate.sh`'s reader: the marker BODY is multi-line, so the SHA is extracted from EVERY line and the last is taken -- never `tail` first.

    `2>/dev/null ... || true`: a `gh` failure is indistinguishable from "no marker", and the currency assertion then fails CLOSED, which is the right direction here. That swallow is the twin's and is preserved; note it is the only one in this file, and unlike the budget's (which was fixed on 2026-09-10 because it moved the CAP NUMERATOR) this one can only make the check stricter.
    """
    code, body = _gh(
        ["api", "repos/%s/issues/%s/comments" % (repo, pr), "--paginate"],
        quiet=True,
    )
    if code != 0:
        return ""
    try:
        comments = json.loads(body.decode("utf-8", "replace"))
    except ValueError:
        return ""
    if not isinstance(comments, list):
        return ""
    found = ""
    for comment in comments:
        if not isinstance(comment, dict):
            continue
        text = comment.get("body") or ""
        if not text.startswith(prefix):
            continue
        for line in text.split("\n"):
            match = MARKER_SHA_RE.match(line)
            if match:
                found = match.group(1)
    return found


def submodule_paths(cwd: str | None = None) -> list[str]:
    """`git config -f .gitmodules --get-regexp '^submodule\\..*\\.path$' | awk '{print $2}'`.

    Reads `.gitmodules` in the CURRENT DIRECTORY, which is the twin's behaviour and the reason a run from the wrong cwd sees no submodules and treats a pointer bump as a real change. `|| true`: no `.gitmodules` is not an error.
    """
    try:
        proc = subprocess.run(
            ["git", "config", "-f", ".gitmodules", "--get-regexp", GITMODULES_PATH_RE],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            cwd=cwd,
        )
    except OSError:
        return []
    if proc.returncode != 0:
        return []
    out = []
    for line in (proc.stdout or b"").decode("utf-8", "replace").split("\n"):
        fields = line.split()
        if len(fields) >= 2:
            # `awk '{print $2}'`: the second whitespace-separated field.
            out.append(fields[1])
    return out


def non_gitlink_count(files: list[str], subs: list[str]) -> int:
    """The twin's jq: how many changed files are NOT a submodule path.

    `[.[] | select(. as $f | $subs | index($f) | not)] | length`. `index` answers 0 for the FIRST submodule, and `0 | not` is FALSE in jq (0 is truthy), so the first submodule is treated exactly like the rest. That is the one place a hand-rolled reimplementation of this filter goes wrong, so the equivalence is driven against real jq in the differential rather than argued here.
    """
    wanted = set(subs)
    return sum(1 for name in files if name not in wanted)


def check_payload(check_name: str, head_sha: str, conclusion: str, title: str, summary: str):
    """`jq -n --arg ...`: the bytes that go up to GitHub. Returns (rc, bytes)."""
    return _jq(
        [
            "-n",
            "--arg",
            "name",
            check_name,
            "--arg",
            "sha",
            head_sha,
            "--arg",
            "conclusion",
            conclusion,
            "--arg",
            "title",
            title,
            "--arg",
            "summary",
            summary,
            (
                '{name: $name, head_sha: $sha, status: "completed", conclusion: $conclusion,\n'
                "          output: {title: $title, summary: $summary}}"
            ),
        ]
    )


def post_check(
    repo: str,
    check_name: str,
    head_sha: str,
    conclusion: str,
    title: str,
    summary: str,
) -> None:
    """Upsert the named check-run on the PR's CURRENT head.

    UPSERT rather than always-POST because these events fire on every comment, and a fresh check-run per keystroke buries the PR's checks list.

    `head_sha` is not a PATCH field and sending it on an update is rejected, so the update path pipes the payload through `jq 'del(.head_sha)'` first.
    """
    rc, payload = check_payload(check_name, head_sha, conclusion, title, summary)
    if rc != 0:
        raise ReporterError(rc)

    # `|| existing=""`: a failed lookup means POST a new one, which is the safe
    # direction (a duplicate check-run, never a lost verdict).
    code, found = _gh(
        [
            "api",
            "-X",
            "GET",
            "repos/%s/commits/%s/check-runs" % (repo, head_sha),
            "-f",
            "check_name=%s" % check_name,
            "--jq",
            '[.check_runs[]? | select(.app.slug == "github-actions")] | last | .id // empty',
        ]
    )
    existing = "" if code != 0 else found.decode("utf-8", "replace").strip()

    if existing:
        rc, stripped = _jq(["del(.head_sha)"], stdin=payload)
        if rc != 0:
            raise ReporterError(rc)
        code, _ = _gh_input(
            ["api", "-X", "PATCH", "repos/%s/check-runs/%s" % (repo, existing), "--input", "-"],
            stripped,
        )
        if code != 0:
            raise ReporterError(code)
        log.info("updated check-run %s: %s = %s" % (existing, check_name, conclusion))
        return

    code, _ = _gh_input(
        ["api", "-X", "POST", "repos/%s/check-runs" % repo, "--input", "-"], payload
    )
    if code != 0:
        raise ReporterError(code)
    log.info("created check-run: %s = %s on %s" % (check_name, conclusion, head_sha))


def _gh_input(args: list[str], payload: bytes) -> tuple[int, bytes]:
    """`gh ... --input - <<<payload >/dev/null`. stderr inherited."""
    try:
        proc = subprocess.run(
            ["gh", *args],
            input=payload,
            stdout=subprocess.DEVNULL,
            check=False,
        )
    except OSError:
        return 127, b""
    return proc.returncode, b""


def artifact_pr(repo: str, run_id: str) -> str:
    """The `review-target` artifact's PR number, or "" when there is none.

    ABSENT IS SILENT, PRESENT IS BINDING, and the twin's comment records why at length: a push to main runs this chain and legitimately has no PR, writes no artifact and exits 0. An artifact that EXISTS but cannot be honoured is a REPORTER failure and must be loud -- that is the case that used to be indistinguishable from the main-push case, back when this arm read
    `workflow_run.head_sha` (which GitHub stamps with the DEFAULT BRANCH tip, so it had never resolved a PR since it was written).
    """
    probe_args = [
        "api",
        "repos/%s/actions/runs/%s/artifacts" % (repo, run_id),
        "--jq",
        '.artifacts[] | select(.name == "%s") | .id' % ARTIFACT_NAME,
    ]
    # `... | grep -q .` inside an `if`: a gh failure is a false condition, not a refusal, because `set -e` does not apply to a condition.
    code, listing = _gh(probe_args, quiet=True)
    if code != 0 or not listing.strip():
        return ""

    # The SECOND call is not in a condition, so `set -e` applies to it.
    code, ident = _gh(
        [
            "api",
            "repos/%s/actions/runs/%s/artifacts" % (repo, run_id),
            "--jq",
            '[.artifacts[] | select(.name == "%s")] | first | .id' % ARTIFACT_NAME,
        ]
    )
    if code != 0:
        raise ReporterError(code)
    art_id = ident.decode("utf-8", "replace").strip()

    tmp_dir = tempfile.mkdtemp()
    try:
        tmp_zip = os.path.join(tmp_dir, "review-target.zip")
        try:
            proc = subprocess.run(
                ["gh", "api", "repos/%s/actions/artifacts/%s/zip" % (repo, art_id)],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        except OSError:
            proc = None
        if proc is None or proc.returncode != 0:
            # The redirection has already created (or truncated) the file on the twin's side; the message and the exit code are what matter.
            log.error(
                "review-target artifact %s exists on run %s but could not be downloaded"
                % (art_id, run_id)
            )
            raise ReporterError(1)
        with open(tmp_zip, "wb") as handle:
            handle.write(proc.stdout or b"")
        digits = _read_member_digits(tmp_zip)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    if not digits:
        log.error("review-target artifact on run %s is present but carries no PR number" % run_id)
        raise ReporterError(1)
    return digits


def _read_member_digits(zip_path: str) -> str:
    """The twin's inline `python3 -c` reader, plus its `| tr -dc '0-9'`.

    Every exception is swallowed and yields the empty string, which the caller then reports as "present but carries no PR number" -- so a corrupt zip and an empty member are the same, loud, outcome. This is the one place the port reimplements rather than spawns, because the twin's program IS python3 and this is the identical code in-process.
    """
    try:
        with zipfile.ZipFile(zip_path) as archive:
            raw = archive.read(ARTIFACT_MEMBER).decode("utf-8", "replace")
    except Exception:  # noqa: BLE001 - `except Exception: pass`, the twin's own net
        raw = ""
    return "".join(ch for ch in raw if ch.isdigit() and ch.isascii())


def _resolve_pr(repo: str, event: str) -> str:
    """The `case "${EVENT_NAME:-}"` block. Returns the PR number, or ""."""
    if event == EVENT_WORKFLOW_RUN:
        run_id = common.require_var("WR_RUN_ID")
        return artifact_pr(repo, run_id)
    if event in EVENTS_WITH_PR_NUMBER:
        # NOT VALIDATED AS A NUMBER anywhere. See the module docstring.
        return common.require_var("PR_NUMBER")
    log.error("Unsupported EVENT_NAME: %s" % (event or "unset"))
    raise ReporterError(1)


def _read_gate_constants(gate_script: pathlib.Path) -> tuple[str, str]:
    """MARKER_PREFIX and ATTEMPT_PREFIX, or a fatal refusal naming the fix."""
    if not gate_script.is_file():
        log.error("cannot read review constants: %s does not exist" % gate_script)
        raise ReporterError(1)
    try:
        text = gate_script.read_text(encoding="utf-8", errors="replace")
    except OSError:
        # `sed` on an unreadable file prints its own error and yields nothing, which lands in the parse-failure arm below.
        text = ""
    marker = parse_prefix(text, "MARKER_PREFIX")
    attempt = parse_prefix(text, "ATTEMPT_PREFIX")
    if not marker:
        log.error("could not parse MARKER_PREFIX out of %s" % gate_script)
        log.error("  Fix: keep it as a plain top-level assignment there, or update this parser.")
        raise ReporterError(1)
    if not attempt:
        log.error("could not parse ATTEMPT_PREFIX out of %s" % gate_script)
        log.error("  Fix: keep it as a plain top-level assignment there, or update this parser.")
        log.error("  Without it the cap reads LOWER here than in the gate, and the deadlock")
        log.error("  guard below cannot fire on a capped PR -- the #553 failure mode.")
        raise ReporterError(1)
    # The twin's two `declare -F` guards. STRUCTURAL rather than reachable here -- an import failure would have ended this process at the import -- and kept because the contract they state ("the gate and this script must share ONE numerator") is what the reuse of core.review_budget rests on.
    for attr, message in (
        ("spend_total", "review_spend_total() is missing from ../lib/common.sh"),
        ("cap_for", "review_cap_for() is missing from ../lib/common.sh"),
    ):
        if not callable(getattr(review_budget, attr, None)):
            log.error(message)
            log.error("  Fix: restore it there; the gate and this script must share ONE numerator.")
            raise ReporterError(1)
    return marker, attempt


def _currency(repo: str, head_sha: str, last_sha: str) -> tuple[bool, str]:
    """ASSERTION 1. Returns (ok, detail)."""
    if last_sha and last_sha == head_sha:
        return True, "head `%s` is the reviewed SHA" % head_sha
    if not last_sha:
        return False, (
            "no reviewed-SHA marker comment on this PR, so head `%s` has not been reviewed"
            % head_sha
        )

    # FAIL CLOSED ON A COMPARE FAILURE. `claude-review-gate.sh` fails OPEN there (worst case: one extra review); here failing open would ASSERT a head was reviewed when nothing proved it.
    code, body = _gh(
        [
            "api",
            "repos/%s/compare/%s...%s" % (repo, last_sha, head_sha),
            "--jq",
            "[.files[]?.filename]",
        ],
        quiet=True,
    )
    files_json = b"" if code != 0 else body.strip()
    if not files_json:
        log.warn(
            "compare %s...%s failed; treating head as unreviewed" % (last_sha[:7], head_sha[:7])
        )
        return False, (
            "could not compare `%s` with `%s` (compare API failed), so equivalence is unproven"
            % (last_sha, head_sha)
        )

    try:
        files = json.loads(files_json.decode("utf-8", "replace"))
    except ValueError:
        files = []
    if not isinstance(files, list) or not files:
        # `[[ "$(jq 'length' <<<"$files_json")" -eq 0 ]]`.
        return True, "empty diff between reviewed `%s` and head `%s`" % (last_sha, head_sha)

    names = [name for name in files if isinstance(name, str)]
    count = non_gitlink_count(names, submodule_paths())
    if count == 0:
        return True, (
            "only submodule pointer bumps between reviewed `%s` and head `%s`"
            % (last_sha, head_sha)
        )
    return False, "%d non-submodule file(s) changed since the reviewed SHA" % count


def _hygiene(hygiene_dir: pathlib.Path, pr: str, repo: str, failures: list[str]) -> None:
    """ASSERTION 2, and its anti-vacuity guard.

    A wrong `HYGIENE_DIR` would silently reduce this check to the currency assertion alone and STILL REPORT SUCCESS, so a missing or non-executable script is a fatal reporter failure rather than a skipped check.

    Each script's combined output is captured, its last 20 lines go into the failure text, and the WHOLE of it is echoed to stdout either way -- so a passing hygiene run is still readable in the workflow log.
    """
    for script in HYGIENE_SCRIPTS:
        path = hygiene_dir / script
        if not (path.is_file() and os.access(path, os.X_OK)):
            log.error("hygiene script missing or not executable: %s" % path)
            raise ReporterError(1)
        env = dict(os.environ)
        env["PR_NUMBER"] = pr
        env["GITHUB_REPOSITORY"] = repo
        try:
            proc = subprocess.run(
                [str(path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=env,
                check=False,
            )
            code, out = proc.returncode, proc.stdout or b""
        except OSError:
            code, out = 126, b""
        if code == 0:
            log.info("hygiene ok: %s" % script)
        else:
            text = out.decode("utf-8", "surrogateescape")
            # `$(tail -n 20 "$out_file")`: the last 20 lines, with the trailing newlines the command substitution would have stripped.
            lines = text.split("\n")
            if lines and lines[-1] == "":
                lines.pop()
            tail = "\n".join(lines[-20:]).rstrip("\n")
            failures.append("`%s` failed:\n\n```\n%s\n```" % (script, tail))
            log.error("hygiene failed: %s" % script)
        # `cat "$out_file"`: BYTES, because a hygiene script's output is not this reporter's to re-encode.
        sys.stdout.flush()
        sys.stdout.buffer.write(out)
        sys.stdout.buffer.flush()


def build_summary(
    pr: str,
    head_sha: str,
    last_sha: str,
    failures: list[str],
    warnings: list[str],
    notes: list[str],
) -> str:
    """The check-run body, section by section, in the twin's exact whitespace."""
    summary = "PR #%s -- head `%s`, last reviewed `%s`." % (pr, head_sha, last_sha or "<none>")
    for heading, items in (
        ("Failures", failures),
        ("Warnings", warnings),
        ("Context", notes),
    ):
        if not items:
            continue
        summary += "\n\n## %s\n" % heading
        for item in items:
            summary += "\n- %s" % item
    return summary + FOOTER


def run() -> int:
    # `os.environ.get(...)` SPELLED OUT AT EVERY READ, not through a local alias. `check:ci-python-env-registry` derives a module's environment inputs from the AST and an alias hides every one of them from it, which is the undeclared-input hole that gate exists to close.
    for cmd in ("gh", "jq", "python3"):
        # `python3` is declared because the artifact lookup reads a zip member
        # with it. An UNDECLARED binary is a MUTE DEATH: under `set -euo
        # pipefail` a command-not-found inside a command substitution exits 127 immediately, before any log_error and before post_check, leaving the head with no check-run and no annotation.
        common.require_cmd(cmd)
    repo = common.require_var("GITHUB_REPOSITORY")

    check_name = os.environ.get("CHECK_NAME") or DEFAULT_CHECK_NAME
    hygiene_dir = pathlib.Path(
        os.environ.get("REVIEW_STATUS_HYGIENE_DIR") or (twin_script_dir() / ".." / "quality")
    )
    gate_script = pathlib.Path(
        os.environ.get("REVIEW_STATUS_GATE_SCRIPT") or (twin_script_dir() / "claude-review-gate.sh")
    )
    marker_prefix, attempt_prefix = _read_gate_constants(gate_script)

    event = os.environ.get("EVENT_NAME", "")
    log.step("Review Complete: resolving the PR (event: %s)" % (event or "unset"))
    pr = _resolve_pr(repo, event)

    if not pr:
        # Reachable only when no review-target artifact was written, i.e. the triggering run had no PR at all (a push to main). GREPPABLE ON PURPOSE: if this line ever appears for a run that DID have a PR, the handoff broke and the silence is the bug, not the verdict.
        log.info(
            "no review-target artifact on run %s; no PR to report on"
            % (os.environ.get("WR_RUN_ID") or "?")
        )
        return 0

    code, body = _gh(
        [
            "api",
            "repos/%s/pulls/%s" % (repo, pr),
            "--jq",
            "{state: .state, draft: .draft, head: .head.sha}",
        ]
    )
    if code != 0:
        # `set -e` on a plain assignment: gh's own status, gh's own stderr.
        raise ReporterError(code)
    rc, state_out = _jq(["-r", ".state // empty"], stdin=body)
    if rc != 0:
        raise ReporterError(rc)
    pr_state = state_out.decode("utf-8", "replace").strip()
    rc, draft_out = _jq(["-r", ".draft // false"], stdin=body)
    if rc != 0:
        raise ReporterError(rc)
    pr_draft = draft_out.decode("utf-8", "replace").strip()
    rc, head_out = _jq(["-r", ".head // empty"], stdin=body)
    if rc != 0:
        raise ReporterError(rc)
    head_sha = head_out.decode("utf-8", "replace").strip()

    if pr_state != "open":
        log.info("PR #%s is %s, not open; nothing to report" % (pr, pr_state or "unknown"))
        return 0
    if not head_sha:
        log.error("PR #%s returned no head SHA; refusing to post a check-run with no anchor" % pr)
        raise ReporterError(1)

    log.info("PR #%s head %s" % (pr, head_sha))

    if pr_draft == "true":
        post_check(
            repo,
            check_name,
            head_sha,
            "neutral",
            "Draft PR -- review not expected",
            "PR #%s is a draft. The review pipeline only fires for a non-draft PR whose current "
            "head has green CI, so there is nothing to assert about commit `%s` yet. Flip the PR "
            "ready for review and this check re-evaluates." % (pr, head_sha),
        )
        return 0

    failures: list[str] = []
    warnings: list[str] = []
    notes: list[str] = []

    if event == EVENT_WORKFLOW_RUN:
        conclusion = os.environ.get("WR_CONCLUSION", "")
        if conclusion in FAILED_CONCLUSIONS:
            failures.append(
                "The triggering **Claude Review** run concluded `%s`, so no review verdict was "
                "produced for this head: %s"
                % (conclusion, os.environ.get("WR_HTML_URL") or "<run url unavailable>")
            )
        else:
            notes.append("Triggering Claude Review run: `%s`." % (conclusion or "n/a"))

    log.step("CURRENCY: is the reviewed-SHA marker on the current head?")
    last_sha = last_marker_sha(repo, pr, marker_prefix)
    currency_ok, currency_detail = _currency(repo, head_sha, last_sha)

    try:
        # Posted reports PLUS spent attempts: the same total the gate caps on. Counting posted reports alone made this script read 0/3 while the gate read 3/3 on the SAME PR, which is why the deadlock guard never fired.
        review_count = review_budget.spend_total(
            review_budget.report_count(pr, repo=repo),
            review_budget.spent_attempt_count(pr, attempt_prefix, repo=repo),
        )
    except (ghx.GhError, ValueError) as exc:
        # `|| return 1` in the twin, then `set -e`. The words differ (see the module docstring); the exit code does not.
        log.error("review budget could not be read for PR #%s: %s" % (pr, exc))
        raise ReporterError(1) from None

    # Y in "X/Y" is sized to THIS PR's diff, via the shared table.
    pr_loc = review_budget.diff_loc(pr, repo=repo, on_error=review_budget.DIFF_LOC_FAILS_TO_ZERO)
    max_reviews = review_budget.cap_for(pr_loc)
    notes.append("Currency: %s." % currency_detail)
    # "spent", not "posted": this number is reports PLUS attempts that burned their budget and posted nothing.
    notes.append(
        "Review passes spent: %d/%d (posted reports + spent attempts; cap %d for a %d-line diff)."
        % (review_count, max_reviews, max_reviews, pr_loc)
    )

    if currency_ok:
        log.info("CURRENCY ok: %s" % currency_detail)
    elif review_count >= max_reviews:
        # THE DEADLOCK GUARD. See the module docstring.
        warnings.append(
            "**REVIEW CAP REACHED** (%d/%d) and the marker is stale: %s. The review pipeline will "
            "not run again on this PR, so the marker can never reach `%s`. Passing so the PR stays "
            "mergeable -- review the delta by hand."
            % (review_count, max_reviews, currency_detail, head_sha)
        )
        log.warn(
            "CURRENCY stale but review cap reached (%d/%d); passing with a warning"
            % (review_count, max_reviews)
        )
    elif review_budget.head_is_exhausted(
        review_budget.attempt_states(pr, attempt_prefix, repo=repo), head_sha
    ):
        # THE SAME DEADLOCK, ONE LEVEL DOWN. The free re-attempts are deliberately not charged, so a head can exhaust its own ceiling while the PR is still well under its cap -- at which point the gate refuses this head and the branch above cannot see why.
        warnings.append(
            "**HEAD REVIEW ATTEMPTS EXHAUSTED** for `%s` (%d reportless attempts, %d/%d of the PR "
            "budget spent): %s. The review pipeline will not retry this head, so the marker can "
            "never reach it. Passing so the PR stays mergeable -- push a change to earn another "
            "pass, or review the delta by hand."
            % (
                head_sha,
                review_budget.REVIEW_MAX_ATTEMPTS_PER_HEAD,
                review_count,
                max_reviews,
                currency_detail,
            )
        )
        log.warn(
            "CURRENCY stale but head %s exhausted its %d attempts; passing with a warning"
            % (head_sha, review_budget.REVIEW_MAX_ATTEMPTS_PER_HEAD)
        )
    else:
        failures.append(
            "Head `%s` has not been reviewed. Last reviewed SHA: `%s`. Detail: %s."
            % (head_sha, last_sha or "<none>", currency_detail)
        )
        log.error("CURRENCY failed: %s" % currency_detail)

    log.step("HYGIENE: running the three review-hygiene checks")
    _hygiene(hygiene_dir, pr, repo, failures)

    conclusion = "success"
    title = "Reviewed at the current head"
    if failures:
        conclusion = "failure"
        title = (
            "Reviewed, but needs attention (see failures)"
            if currency_ok
            else "Review is not complete for this head"
        )
    elif warnings:
        conclusion = "success"
        title = "Reviewed, with warnings"

    post_check(
        repo,
        check_name,
        head_sha,
        conclusion,
        title,
        build_summary(pr, head_sha, last_sha, failures, warnings, notes),
    )
    # Exit 0 even on a `failure` conclusion. See the module docstring.
    return 0


def main() -> int:
    """No arguments: the twin parses none and ignores whatever it is given."""
    try:
        return run()
    except common.RefusalError as refusal:
        refusal.report()
        return refusal.code
    except ReporterError as broken:
        return broken.code


if __name__ == "__main__":
    raise SystemExit(main())

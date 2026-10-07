#!/usr/bin/env python3
"""The sanctioned-command registry: ad-hoc shape -> the tool that replaces it.

WHY A TABLE AND NOT ANOTHER GUARD. This repo already carries 21 separate pre-bash `block-*.sh` scripts, each with its own regex and its own hand-written message. That is the same many-copies shape that caused the bug this registry exists to end: on 2026-08-25 the CI-watch recipe was found in NINE places, two of them printing advice their own neighbouring prose contradicted. Adding
a
class here is a ROW, not a new script, so there is one place to be right.

Each row is a work order, not a ban:
    name      short slug, used in messages and by the gate
    pattern   the ad-hoc shape, as a regex over the command TEXT
    example   a command that MUST match `pattern` -- the gate re-runs this, so a
              row whose pattern has rotted cannot keep reading as an active rule
    counter   a legitimately DIFFERENT command that must NOT match, pinning the
              boundary; without it an over-broad pattern reads as a working one.
              It must be a command, not prose: prose that merely names a banned
              shape DOES match, on purpose (see the note below), so using a
              rejection sentence as the counter would assert the opposite of the
              ruling this registry is built on.
    use       the exact replacement to print
    why       the evidence, in one line, so the message argues rather than asserts

READS COMMAND TEXT, DELIBERATELY. Prose that merely DESCRIBES a banned shape is matched too. That false positive was put to the operator on 2026-08-25 with four scored options and the ruling was to keep it: this failure is loud (a blocked command naming its replacement) while every narrowing that would admit the doc edit fails silently. Worklist #6a2c9652. The workaround is to
write the file with the Write tool and pass it by path.
"""

import importlib
import importlib.util
import pathlib
import re
import shlex

CI_TRACE = ".ci/scripts/ci/ci-trace.py"

REGISTRY = [
    {
        "name": "gh-run-watch",
        "pattern": r"gh\s+run\s+watch\b",
        "example": "gh run watch 123 --exit-status --interval 100",
        "counter": "gh run view 123 --json conclusion,jobs",
        "use": "%s --wait" % CI_TRACE,
        "why": (
            "gh run watch dropped 4 times out of 4 in one campaign and has been seen "
            "exiting 1 while the run was still in progress"
        ),
    },
    {
        "name": "hand-rolled-ci-poll",
        "pattern": r"(?:until|while)[^\n]{0,120}gh\s+(?:run|api)[^\n]{0,120}status",
        "example": 'until [ "$(gh run view $R --json status --jq .status)" = "completed" ]; do',
        "counter": "%s --wait" % CI_TRACE,
        "use": "%s --wait" % CI_TRACE,
        "why": (
            "a hand-rolled loop reported a SUPERSEDED attempt's verdict as final "
            "(watchdog rerun bumped run_attempt) and another reported on a run a "
            "later push had already cancelled; ci-trace keys on the PR head, never "
            "a run id, so neither is expressible"
        ),
    },
    {
        "name": "gh-pr-edit-body",
        "pattern": r"gh\s+pr\s+edit\b[^\n]*--body",
        "example": 'gh pr edit 574 --body "new text"',
        "counter": "gh api repos/o/r/pulls/574 -X PATCH -F body=@body.md",
        "use": "gh api repos/<owner>/<repo>/pulls/<n> -X PATCH -F body=@<file>",
        "why": (
            "measured 2026-08-25 against PR #574: it exits 1 with "
            "'GraphQL: Projects (classic) is being deprecated ... "
            "(repository.pullRequest.projectCards)' and the body is UNCHANGED. This "
            "repo's docs called it a SILENT failure for months; it is not silent, it "
            "is loud and ignored, which matters because you debug the two differently "
            "-- read stderr rather than hunting a no-op. The gh api PATCH form works."
        ),
    },
]


def compiled():
    return [(row, re.compile(row["pattern"], re.IGNORECASE)) for row in REGISTRY]


def match(command):
    """The first row whose ad-hoc shape appears in `command`, or None."""
    for row, rx in compiled():
        if rx.search(command or ""):
            return row
    return None


def message(row):
    return (
        "BLOCKED (%s): use the sanctioned command instead.\n"
        "  use:  %s\n"
        "  why:  %s\n"
        "If you are EDITING documentation that describes this shape rather than "
        "running it, write the file with the Write tool and pass it by path."
        % (row["name"], row["use"], row["why"])
    )


# --------------------------------------------------------------------------- CI_READ_VERBS: raw CI reads -> the tracer verb that replaces each ---------------------------------------------------------------------------
#
# WHY A SECOND TABLE, AND WHY IT IS NOT MATCHED LIKE `REGISTRY`. `REGISTRY` bans WATCH shapes and reads the raw command text, prose included, under the 2026-08-25 ruling above: a loop can hide inside a quoted test, and a refused doc edit is loud. A READ is different. `gh pr checks 591` is one argv, never a loop, and the commit message or worklist note that merely names it is
# the common case rather than the rare one, so text matching here would refuse the very messages that record why the read is banned. These rows are therefore judged over the commands bash would RUN (`shellscan._analyse(cmd).runs`, the command-position reading `block_long_sleep` moved to on 2026-10-01, #8e5a6452), by `block_raw_ci_read`, which hands each `gh` run's argv to
# `ci_read_line` and then `ci_read_row` below.
#
# The trigger, 2026-10-02 on PR #591: Console CI run 36953549081 was cancelled by the watchdog's job budget with zero failed jobs, and the lead spent dozens of raw `gh` calls (run views, job lists, whole job logs through sed and grep, watchdog run lists) to find the one job and the 916-second silence that caused it. `ci-trace.py` now answers each of those in one compact read.
#
# Each row:
#     name     slug, printed as `BLOCKED (raw-ci-read/<name>)`
#     match    regex over the NORMALISED read line `ci_read_line` builds: the gh argv after `gh`, joined by single spaces, except that `gh api` becomes
#              `api <METHOD> <endpoint>` (scheme, host, leading slash and query string removed) and a GraphQL call becomes `api graphql <its arguments>`
#     id       optional regex whose group 1 is the run or job id substituted for `<id>` in `use`
#     use      the exact tracer command to run instead
#     why      one line of evidence
#     example  a command that MUST be refused by exactly this row (`check_sanctioned_registry.py` re-runs it)
#     counter  a nearby command that must NOT be refused by any row, pinning the carve-out next to the row
#
# ORDER MATTERS: the first matching row wins, so a narrower shape (`--watch`, `--job`, `--log`) sits above the broader one.
#
# CARVE-OUTS, by construction rather than by row: every write (`gh api -X POST|PATCH|PUT|DELETE`, or a body flag with no `-X`, which gh sends as POST), `gh run rerun|cancel|download|delete`, `gh pr create|edit|ready|merge|comment|view` without rollup fields, `pulls/<n>`, issues, releases, artifacts, and GraphQL without rollup fields. No environment bypass exists: `--job <id> --log` is the
# whole-log route, so nothing a raw read could show is out of reach.
#
# KNOWN GAPS, stated so a green is not read as more: `curl` against api.github.com is not judged, a GraphQL query passed as `-F query=@file` is not opened, and a raw read inside a script the command runs is invisible (only the command line is walked).

# Any prefix ending in a slash: `repos/<owner>/<repo>/`, `repositories/<id>/`, and the `.../` docs abbreviate it to.
_REPO_PREFIX = r"(?:\S*/)?"
# A path segment holding an id. Not `\d+`: a doc writes `<id>` and a command writes `$RUN`, and both are the same read.
_ID = r"[^/\s]+"

CI_READ_VERBS = [
    {
        "name": "gh-pr-checks-watch",
        "match": r"^pr checks\b.*\s--watch\b",
        "use": "%s --wait" % CI_TRACE,
        "why": (
            "`gh pr checks --watch` keys on whatever checks exist when it starts; on 2026-10-02 the head "
            "had only `CI - OBS Mirror` contexts a minute after the push, which is the exact state the "
            "tracer once called GREEN. `--wait` requires `CI Complete` on the PR head"
        ),
        "example": "gh pr checks 591 --watch --interval 30",
        "counter": "gh pr ready 591",
    },
    {
        "name": "gh-pr-checks",
        "match": r"^pr checks\b",
        "use": "%s" % CI_TRACE,
        "why": (
            "`gh pr checks` lists every context flat: the non-blocking `CI Verdict` reads as a job "
            "with a /runs/ URL, a cancelled gate reads as a skip, and nothing says whether `CI Complete` exists "
            "yet. The tracer judges the head (add `--ref <branch>` for another branch, `--why` for a red)"
        ),
        "example": "gh pr checks 591 --repo o/r",
        "counter": "gh pr comment 591 --body-file note.md",
    },
    {
        "name": "gh-pr-view-rollup",
        "match": r"^pr view\b.*statusCheckRollup",
        "use": "%s --json" % CI_TRACE,
        "why": (
            "the raw rollup is the tracer's own input; read without its GREEN rule it is how a head "
            "with only OBS Mirror contexts registered was called green on 2026-10-02"
        ),
        "example": "gh pr view 591 --json headRefOid,statusCheckRollup",
        "counter": "gh pr view 591 --json headRefOid,isDraft,mergeStateStatus",
    },
    {
        "name": "gh-run-list-watchdog",
        "match": r"^run list\b.*watchdog",
        "use": "%s --watchdog" % CI_TRACE,
        "why": (
            "the watchdog's verdict lives on separate Watchdog Monitor runs titled `Watchdog: run <id> (`; "
            "`--watchdog [<run>]` finds them for the PR head's run and prints their budget annotations"
        ),
        "example": 'gh run list --workflow "Watchdog Monitor" --limit 20',
        "counter": "gh run download 36953549081 -n budget-violations",
    },
    {
        "name": "gh-run-list-schedule",
        # Scheduled runs of ANY workflow (the nightly, housekeeping, promote-stable): before 2026-10-04 this read had no sanctioned verb, so the guard refused it and pointed at `--runs`, which lists only Console CI, and a five-night nightly red stayed invisible to every session. First-wins order puts this row before `gh-run-list`.
        "match": r"^run list\b.*\s--event[= ]schedule\b",
        "use": "%s --scheduled" % CI_TRACE,
        "why": (
            "`--scheduled` lists the newest scheduled run of every workflow that has a `schedule:` trigger, "
            "with its verdict and failed jobs (`--workflow <name>` for one workflow's history)"
        ),
        "example": "gh run list --event schedule --branch main",
        "counter": 'gh run list --workflow "Release to Edge" --limit 3',
    },
    {
        "name": "gh-run-list",
        # Console CI only: with no `--workflow`/`-w`, or one naming Console CI. Another workflow's runs (the Release to Edge dispatch `/pr-merge` looks up by id) are outside the tracer's `--runs`, so listing them is not refused.
        "match": (
            r"^run list\b(?:(?!.*\s(?:--workflow|-w)[= ]).*"
            r"|.*\s(?:--workflow|-w)[= ](?:Console CI|ci\.yml)(?:\s.*)?)$"
        ),
        "use": "%s --runs" % CI_TRACE,
        "why": (
            "`gh run list --limit 1` is usually NOT your run: it is recency-sorted and the watchdog's "
            "workflow_dispatch generations interleave every few minutes. `--runs` lists Console CI runs on "
            "the branch only (`--ref main` for main); nightly and other scheduled runs: `--scheduled`"
        ),
        "example": 'gh run list --branch main --workflow "Console CI" --limit 3',
        "counter": 'gh run list --workflow "Release to Edge" --limit 3',
        # `--runs` takes `--ref <branch>` for a branch other than the current one (`--runs --ref main` after a merge).
    },
    {
        "name": "gh-run-view-job",
        "match": r"^run view\b.*\s--job[= ]?\d+",
        "id": r"--job[= ]?(\d+)",
        "use": "%s --job <id> --errors" % CI_TRACE,
        "why": (
            "`--errors` prints the failing step's excerpt, an infra/code category and the longest log "
            "silences; `--steps` gives durations and `--log` the whole ANSI-stripped log, cached"
        ),
        "example": "gh run view --job 104569 --log",
        "counter": "gh run rerun 36953549081 --failed",
    },
    {
        "name": "gh-run-view-log",
        "match": r"^run view\b.*\s--log(?:-failed)?\b",
        "id": r"^run view (\d+)",
        "use": "%s --run <id> --why" % CI_TRACE,
        "why": (
            "`gh run view --log-failed` refuses until the whole run completes and prints every failed "
            "job's log unsliced; `--why` names the cause, the failing step and its category in <= 12 lines"
        ),
        "example": "gh run view 36953549081 --log-failed",
        "counter": "gh run download 36953549081 -n bridge-logs",
    },
    {
        "name": "gh-run-view",
        "match": r"^run view\b",
        "id": r"^run view (\d+)",
        "use": "%s --run <id> --jobs" % CI_TRACE,
        "why": (
            "`--jobs` prints the counts and every job that did not pass with its duration against p90; "
            "`--why` explains a red or a cancel (watchdog budget, superseded, timeout, manual)"
        ),
        "example": "gh run view 36953549081 --json conclusion,jobs",
        "counter": "gh run rerun 36953549081",
    },
    {
        "name": "gh-api-job-log",
        "match": r"^api GET " + _REPO_PREFIX + r"actions/jobs/" + _ID + r"/logs$",
        "id": r"actions/jobs/(\d+)",
        "use": "%s --job <id> --log" % CI_TRACE,
        "why": (
            "the raw log endpoint redirects to an ANSI-coloured blob that every caller then pipes through "
            "sed and grep; `--log` is that log stripped and cached, `--errors` the failing step's slice"
        ),
        "example": "gh api repos/o/r/actions/jobs/104569/logs",
        "counter": "gh api repos/o/r/actions/jobs/104569/rerun -X POST",
    },
    {
        "name": "gh-api-job",
        "match": r"^api GET " + _REPO_PREFIX + r"actions/jobs/" + _ID + r"$",
        "id": r"actions/jobs/(\d+)",
        "use": "%s --job <id> --steps" % CI_TRACE,
        "why": "`--steps` prints every step with its duration and flags the log silences between them",
        "example": "gh api repos/o/r/actions/jobs/104569 --jq .steps",
        "counter": "gh api repos/o/r/actions/runs/36953549081/artifacts",
    },
    {
        "name": "gh-api-run-jobs",
        "match": r"^api GET "
        + _REPO_PREFIX
        + r"actions/runs/"
        + _ID
        + r"(?:/attempts/"
        + _ID
        + r")?/jobs$",
        "id": r"actions/runs/(\d+)",
        "use": "%s --run <id> --jobs" % CI_TRACE,
        "why": (
            "a run has 160+ jobs across pages; `--jobs` paginates, counts, and prints only the ones that "
            "did not pass (add `--attempt N` for one attempt)"
        ),
        "example": "gh api --paginate repos/o/r/actions/runs/36953549081/jobs",
        "counter": "gh api repos/o/r/actions/runs/36953549081/rerun-failed-jobs -X POST",
    },
    {
        "name": "gh-api-run-logs",
        "match": r"^api GET "
        + _REPO_PREFIX
        + r"actions/runs/"
        + _ID
        + r"(?:/attempts/"
        + _ID
        + r")?/logs$",
        "id": r"actions/runs/(\d+)",
        "use": "%s --run <id> --why" % CI_TRACE,
        "why": "the run log archive is every job's log zipped; `--why` finds the one job and step that matter",
        "example": "gh api repos/o/r/actions/runs/36953549081/logs > logs.zip",
        "counter": "gh api repos/o/r/actions/runs/36953549081/cancel -X POST",
    },
    {
        "name": "gh-api-run",
        "match": r"^api GET "
        + _REPO_PREFIX
        + r"actions/runs/"
        + _ID
        + r"(?:/attempts/"
        + _ID
        + r")?$",
        "id": r"actions/runs/(\d+)",
        "use": "%s --run <id> --why" % CI_TRACE,
        "why": (
            "a run object's `conclusion: cancelled` does not say who cancelled it; `--why` attributes it "
            "(watchdog budget, superseded, timeout-kill, manual) from the Watchdog Monitor's evidence"
        ),
        "example": "gh api repos/o/r/actions/runs/36953549081 --jq .conclusion",
        "counter": "gh api repos/o/r/pulls/591 --jq .head.sha",
    },
    {
        "name": "gh-api-runs-list",
        "match": r"^api GET " + _REPO_PREFIX + r"actions/(?:workflows/[^/\s]+/)?runs$",
        "use": "%s --runs" % CI_TRACE,
        "why": (
            "the runs list mixes every workflow and every branch; `--runs` lists the branch's Console CI "
            "runs (and `--watchdog` the watchdog generations); scheduled runs of every workflow: `--scheduled`"
        ),
        "example": "gh api 'repos/o/r/actions/workflows/ci.yml/runs?branch=0930-1'",
        "counter": "gh api repos/o/r/releases/latest",
    },
    {
        "name": "gh-api-annotations",
        "match": r"^api GET " + _REPO_PREFIX + r"check-runs/" + _ID + r"/annotations$",
        "id": r"check-runs/(\d+)",
        "use": "%s --job <id> --errors" % CI_TRACE,
        "why": (
            "an Actions job's check-run id IS its job id; `--errors` prints its failing step, and "
            "`--watchdog` the budget annotations that live on the Watchdog Monitor runs instead"
        ),
        "example": "gh api repos/o/r/check-runs/104569/annotations",
        "counter": "gh api repos/o/r/check-runs/104569 -X PATCH -f status=completed",
    },
    {
        "name": "gh-api-check-runs",
        "match": (
            r"^api GET "
            + _REPO_PREFIX
            + r"(?:commits/[^/\s]+/(?:check-runs|check-suites|status|statuses)"
            r"|statuses/[^/\s]+|check-runs/" + _ID + r"|check-suites/" + _ID + r"(?:/check-runs)?)$"
        ),
        "use": "%s --json" % CI_TRACE,
        "why": (
            "the commit's raw check-runs hold every context, including the non-blocking "
            "`CI Verdict` and `Publish CI Verdict`; the tracer applies the GREEN rule, and its `--json` "
            "carries the published CI Verdict when one matches the run"
        ),
        "example": "gh api repos/o/r/commits/a7f30558/check-runs --jq '.check_runs[].name'",
        "counter": "gh api repos/o/r/issues/591/comments",
    },
    {
        "name": "gh-graphql-rollup",
        "match": r"^api graphql\b.*\b(?:statusCheckRollup|checkSuites|checkRuns)\b",
        "use": "%s --json" % CI_TRACE,
        "why": (
            "a hand-written rollup query reimplements the tracer's read without its GREEN rule (CI Complete "
            "present and SUCCESS, an untruncated read, no blocking live, hard or cancelled context)"
        ),
        "example": (
            'gh api graphql -f query=\'{ repository(owner:"o", name:"r") { pullRequest(number:591) '
            "{ commits(last:1) { nodes { commit { statusCheckRollup { state } } } } } } }'"
        ),
        "counter": (
            "gh api graphql -f query='mutation { resolveReviewThread(input:{threadId:\"T\"}) { thread { id } } }'"
        ),
    },
]

_API_HOST = re.compile(r"^https?://[^/]+/(?:api/v3/)?")


def _shellscan():
    """`rediacc_hooks.shellscan`, the one gh argv parser (#d2d5f89d).

    This module is loaded BY PATH, by the guards, by ci-trace, by the Stop hook and by the registry checker, and not all of them have `.claude` on sys.path; the checker's own test loads a planted COPY from a temp directory. So: the import by name when it already works, else the canonical `.claude` hop (`rediacc_hooks/syspath.py`) beside this file, else the one above the working directory. None found is an ImportError that says so, never a silent fallback reader.
    """
    try:
        return importlib.import_module("rediacc_hooks.shellscan")
    except ImportError:
        pass
    here = pathlib.Path(__file__).resolve()
    anchors = [
        here.parents[2],
        *(d / ".claude" for d in [pathlib.Path.cwd(), *pathlib.Path.cwd().parents]),
    ]
    for claude in anchors:
        hop = claude / "rediacc_hooks" / "syspath.py"
        if not hop.is_file():
            continue
        spec = importlib.util.spec_from_file_location("rediacc_hooks_syspath", hop)
        if spec is None or spec.loader is None:
            continue
        syspath = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(syspath)
        syspath.on_sys_path(syspath.CLAUDE_DIR)
        return importlib.import_module("rediacc_hooks.shellscan")
    raise ImportError(
        "sanctioned.py needs rediacc_hooks.shellscan to read a gh api call, and found no "
        ".claude/rediacc_hooks/syspath.py beside %s or above %s" % (here, pathlib.Path.cwd())
    )


def _api_parts(args):
    """(endpoint, explicit method or "", body present) for `gh api <args>`; args are those after `api`.

    Read by `shellscan.gh_args`, the pflag reader every gh guard shares (#d2d5f89d), so the method and the endpoint are what gh makes of them in every spelling: `-X GET`, `-XGET`, `-X=GET` (GET, not "=GET"), `--method=get`, a bundle ending in it (`-iX GET`, `-iXPATCH`), and a field in any spelling (`-fstatus=x`, `--raw-field=x`). Measured 2026-10-07 through dispatch.py, before this: `gh api -X=GET repos/o/r/actions/jobs/1` and `gh api -iX GET repos/o/r/actions/jobs/1` were admitted by
    block_raw_ci_read where `-X GET` is refused, the first read as a "=GET" write and the second with "GET" taken for the endpoint.
    """
    shellscan = _shellscan()
    parsed = shellscan.gh_args(["api", *args])
    endpoint = parsed.operands[0] if parsed.operands else ""
    method = (parsed.last("method") or "").upper()
    body = bool(parsed.values("field") or parsed.values("raw-field") or parsed.values("input"))
    return endpoint, method, body


def api_method(args):
    """The HTTP method `gh <args>` would send for a `gh api` call: `-X` wins, else a body flag means POST, else GET.

    "" when `args` is not a `gh api` call. `block_raw_ci_read` calls this itself rather than through `ci_read_line`, so its declared DEFECT can turn a write into a read.
    """
    if not args or args[0] != "api":
        return ""
    _endpoint, method, body = _api_parts(args[1:])
    if method:
        return method
    return "POST" if body else "GET"


def ci_read_line(args, method):
    """The normalised read line the `CI_READ_VERBS` rows match, for the argv after `gh`; "" when there is none."""
    if not args:
        return ""
    if args[0] != "api":
        return " ".join(args)
    endpoint, _method, _body = _api_parts(args[1:])
    endpoint = _API_HOST.sub("", endpoint).lstrip("/").split("?", 1)[0].rstrip("/")
    if endpoint == "graphql":
        return "api graphql " + " ".join(args[1:])
    if endpoint == "":
        return ""
    return "api %s %s" % (method or "GET", endpoint)


def ci_read_row(line):
    """(row, id) for the first `CI_READ_VERBS` row matching a normalised line, else (None, "")."""
    for row in CI_READ_VERBS:
        if re.search(row["match"], line or "", re.IGNORECASE):
            ident = ""
            if row.get("id"):
                hit = re.search(row["id"], line, re.IGNORECASE)
                ident = hit.group(1) if hit else ""
            return row, ident
    return None, ""


def ci_read_match(command):
    """(row, id) for a command string whose FIRST `gh` word starts a raw CI read, else (None, "").

    For the registry checker and the doc scan, which hold a single command rather than a walked shell line; the guard walks the shell itself.
    """
    try:
        words = shlex.split(command or "")
    except ValueError:
        words = (command or "").split()
    if "gh" not in words:
        return None, ""
    args = words[words.index("gh") + 1 :]
    return ci_read_row(ci_read_line(args, api_method(args)))


def ci_read_use(row, ident):
    return row["use"].replace("<id>", ident) if ident else row["use"]


def ci_read_message(row, ident):
    return (
        "BLOCKED (raw-ci-read/%s): read CI through the tracer instead.\n"
        "  use:  %s\n"
        "  why:  %s\n"
        "The whole log of any job is `%s --job <id> --log`, so there is no bypass to ask for. "
        "Writes (rerun, cancel, download, -X POST/PATCH), PR edits, pulls/<n>, issues and releases are not refused."
        % (row["name"], ci_read_use(row, ident), row["why"], CI_TRACE)
    )

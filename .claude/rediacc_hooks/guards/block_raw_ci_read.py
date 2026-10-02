"""Refuse a raw CI read through `gh` and name the `ci-trace.py` verb that answers it.

THE TRIGGER, 2026-10-02 on PR #591 (agent/plans/PLAN-ci-verdict.md, box C). Console CI run 36953549081 was cancelled by the watchdog's job budget with zero failed jobs. Diagnosing it took dozens of raw `gh` reads: run views, paginated job lists, whole job logs piped through `sed` and `grep`, watchdog run lists. Every one of them passed every guard, because the guards that existed
(`block_ci_polling`, `block_ci_reverse_poll`, `block_adhoc_sanctioned`) ban WATCH shapes, not reads. `ci-trace.py` now carries a diagnosis verb for each read (`--why`, `--runs`, `--run <id> --jobs`, `--job <id> --errors|--steps|--log`, `--history`, `--watchdog`), and this guard is what makes it the only route.

THE TABLE LIVES IN `.claude/hooks/lib/sanctioned.py` as `CI_READ_VERBS`, beside the watch registry, so `check_sanctioned_registry.py` re-runs every row's example and counter and proves each `use` flag exists in `ci-trace.py --help`, and `rediacc_ci.quality.ci_watch_recipe` check C refuses a doc that hands one of these reads out. This file only finds the `gh` runs and applies the write carve-out.

COMMAND POSITION, NOT TEXT, following `block_long_sleep` (2026-10-01, #8e5a6452). A read is one argv, never a loop hiding in a quoted test, so there is nothing for a text match to find that the walk cannot, and the text match would refuse the commit messages and worklist notes that record why these reads are banned. `shellscan._analyse(cmd).runs` lists the commands bash would run: it descends `$(...)`, `sh -c`
payloads, `eval` and a heredoc fed to a shell, while a quoted argument and a heredoc body read as data stay data. That is why the watch registry's text match is not reused here; its own header records the ruling that keeps it text-matched, and the reason (a loop's banned half lives inside quotes) does not apply to a read.

WRITES ARE NOT READS. The method is computed here (`registry.api_method`), so the declared DEFECT below, which forces every call to GET, turns a `gh api -X PATCH .../check-runs/<id>` write into a refusal and the differential sees it. `gh run rerun|cancel|download|delete`, PR edits, `pulls/<n>`, issues, releases and artifacts never match a row.

NO BYPASS. `ci-trace.py --job <id> --log` prints the whole ANSI-stripped log, so nothing a raw read could show is out of reach and there is no environment variable to ask for.

FAILS OPEN on its own breakage, as `block_adhoc_sanctioned` does: a registry that cannot be imported allows everything rather than bricking the shell.

THIS GUARD HAS NO BASH TWIN (`OWN_SUITE = True`), so it is judged against `test-block_raw_ci_read.py` beside it and against its own DEFECT, never against a golden.
"""

import importlib.util
import types

from rediacc_hooks import hookio, shellscan

CHAIN = "pre-bash"
OWN_SUITE = True
ORDER = 51

# A write read as a GET: `gh api -X PATCH repos/o/r/check-runs/<id>` becomes `api GET .../check-runs/<id>` and is refused.
DEFECT = ("method = registry.api_method(args)", "method = 'GET'")

LIB = hookio.repo_root() / ".claude" / "hooks" / "lib"

_REGISTRY: list[types.ModuleType | None] = []

EDGE_CASES = [
    # --- refused: every CI_READ_VERBS row, plus the shapes the walk must see through ---
    ("pr checks", "gh pr checks 591"),
    ("pr checks --watch", "gh pr checks 591 --watch"),
    ("pr checks inside a substitution", 'echo "$(gh pr checks 591)"'),
    ("pr view with the rollup", "gh pr view 591 --json headRefOid,statusCheckRollup"),
    ("run list", "gh run list --branch 0930-1 --limit 5"),
    ("watchdog run list", 'gh run list --workflow "Watchdog Monitor" --limit 20'),
    ("run view --job --log", "gh run view --job 104569 --log"),
    ("run view --log-failed", "gh run view 36953549081 --log-failed"),
    ("run view json", "gh run view 36953549081 --json conclusion,jobs"),
    (
        "job log piped through sed and grep (the 2026-10-02 shape)",
        (
            "gh api repos/o/r/actions/jobs/104569/logs --allow-escape-sequences "
            "| sed 's/\\x1b\\[[0-9;]*m//g' | grep -n 'Error'"
        ),
    ),
    ("one job object", "gh api repos/o/r/actions/jobs/104569 --jq .steps"),
    ("run jobs, paginated", "gh api --paginate repos/o/r/actions/runs/36953549081/jobs"),
    (
        "attempt jobs, leading slash",
        "gh api /repos/o/r/actions/runs/36953549081/attempts/2/jobs",
    ),
    ("run log archive", "gh api repos/o/r/actions/runs/36953549081/logs > logs.zip"),
    ("run object", "gh api repos/o/r/actions/runs/36953549081 --jq .conclusion"),
    ("explicit GET", "gh api -X GET repos/o/r/actions/runs/36953549081"),
    (
        "workflow runs with a query string",
        "gh api 'repos/o/r/actions/workflows/ci.yml/runs?branch=0930-1'",
    ),
    ("check-run annotations", "gh api repos/o/r/check-runs/104569/annotations"),
    ("commit check-runs", "gh api repos/o/r/commits/a7f30558/check-runs"),
    (
        "graphql rollup",
        (
            'gh api graphql -f query=\'{ repository(owner:"o", name:"r") '
            "{ pullRequest(number:591) { commits(last:1) { nodes { commit "
            "{ statusCheckRollup { state } } } } } } }'"
        ),
    ),
    ("inside sh -c", "sh -c 'gh run view 36953549081'"),
    # --- allowed: writes, carve-outs, and prose that only names a read ---
    ("CONTROL: rerun", "gh run rerun 36953549081 --failed"),
    ("CONTROL: cancel", "gh run cancel 36953549081"),
    ("CONTROL: download an artifact", "gh run download 36953549081 -n bridge-logs"),
    ("CONTROL: pr create", "gh pr create --draft --title t --body-file b.md"),
    ("CONTROL: pr edit", "gh pr edit 591 --add-label ci"),
    ("CONTROL: pr ready", "gh pr ready 591"),
    ("CONTROL: pr merge", "gh pr merge 591 --rebase"),
    ("CONTROL: pr comment", "gh pr comment 591 --body-file note.md"),
    ("CONTROL: pr view without rollup", "gh pr view 591 --json headRefOid,isDraft"),
    ("CONTROL: pulls/<n>", "gh api repos/o/r/pulls/591 --jq .head.sha"),
    ("CONTROL: issues", "gh api repos/o/r/issues/591/comments"),
    ("CONTROL: releases", "gh api repos/o/r/releases/latest"),
    ("CONTROL: artifacts", "gh api repos/o/r/actions/runs/36953549081/artifacts"),
    (
        "CONTROL: a check-run write (the DEFECT's target)",
        "gh api -X PATCH repos/o/r/check-runs/104569 -f status=completed",
    ),
    ("CONTROL: a body flag means POST", "gh api repos/o/r/check-runs -f name=x"),
    (
        "CONTROL: rerun-failed-jobs POST",
        "gh api -X POST repos/o/r/actions/runs/36953549081/rerun-failed-jobs",
    ),
    (
        "CONTROL: graphql without rollup fields",
        (
            'gh api graphql -f query=\'mutation { resolveReviewThread(input:{threadId:"T"}) '
            "{ thread { id } } }'"
        ),
    ),
    (
        "CONTROL: a commit message naming gh pr checks",
        'git commit -m "docs: gh pr checks is refused"',
    ),
    ("CONTROL: a heredoc body is data", "cat > note.md <<'EOF'\ngh run view 36953549081\nEOF"),
    ("CONTROL: the tracer itself", ".ci/scripts/ci/ci-trace.py --run 36953549081 --why"),
]


def _registry():
    """`import sanctioned` by path, once; None on any failure (the guard then fails open)."""
    if _REGISTRY:
        return _REGISTRY[0]
    module: types.ModuleType | None = None
    try:
        spec = importlib.util.spec_from_file_location("sanctioned", str(LIB / "sanctioned.py"))
        if spec is not None and spec.loader is not None:
            loaded = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(loaded)
            if hasattr(loaded, "CI_READ_VERBS"):
                module = loaded
    except Exception:  # noqa: BLE001 -- fail open, as block_adhoc_sanctioned does
        module = None
    _REGISTRY.append(module)
    return module


def _refusal(registry, cmd):
    """The refusal text for the first raw CI read bash would run in `cmd`, or ""."""
    for run_ in shellscan._analyse(cmd).runs:
        if run_.name.rsplit("/", 1)[-1] != "gh":
            continue
        args = list(run_.argv)
        method = registry.api_method(args)
        line = registry.ci_read_line(args, method)
        # GraphQL is always a POST, read or write alike; its rows judge the query, so the method cannot carve it out.
        if method not in ("", "GET") and not line.startswith("api graphql "):
            continue
        row, ident = registry.ci_read_row(line)
        if row is not None:
            return registry.ci_read_message(row, ident)
    return ""


def run(ev):
    cmd = ev.raw("tool_input", "command")
    if cmd == "" or "gh" not in cmd:
        return hookio.ALLOW
    registry = _registry()
    if registry is None:
        return hookio.ALLOW
    try:
        msg = _refusal(registry, cmd)
    except Exception:  # noqa: BLE001 -- a raising registry allows, never bricks the shell
        return hookio.ALLOW
    if msg:
        ev.warn(msg)
        return hookio.DENY
    return hookio.ALLOW

#!/usr/bin/env python3
"""Control harness for block_raw_ci_read.

Both directions, because a one-sided control is satisfiable by a broken hook: one that always refuses passes the refusal cases, one that never refuses passes the allowed ones. A refusal must also NAME the tracer command that replaces the read, with the id filled in where the read carried one, because a refusal without its replacement is a dead end.

    test-block_raw_ci_read.py            run every case through dispatch.py, as settings.json does
    test-block_raw_ci_read.py --defect   run them in-process against the guard with its declared DEFECT
                                         planted; this MUST fail, which is the proof the suite can
"""

import importlib
import importlib.util
import json
import pathlib
import subprocess
import sys
import typing

HERE = pathlib.Path(__file__).resolve()
# The canonical sys.path hop, through rediacc_hooks/syspath.py loaded by file (the pattern test-block_commit_on_main.py uses).
_SYSPATH = importlib.util.spec_from_file_location(
    "rediacc_hooks_syspath", HERE.parent.parent / "syspath.py"
)
if _SYSPATH is None or _SYSPATH.loader is None:
    raise SystemExit("%s: rediacc_hooks/syspath.py is missing" % __file__)
_syspath = importlib.util.module_from_spec(_SYSPATH)
_SYSPATH.loader.exec_module(_syspath)
# Derived from THIS file, never hard-coded: the guard lives beside the harness, and the dispatcher is what actually runs it.
DISPATCH = str(HERE.parents[1] / "dispatch.py")
STEM = "block_raw_ci_read"
GUARD_ARGV = [sys.executable, DISPATCH, STEM]
T = ".ci/scripts/ci/ci-trace.py"
G = "g" + "h"  # assembled so this file is not itself a raw read to a text scan
REPO = "repos/o/r"
# The API base comes from the literal registry (check:ci-literal-sources R1), through the hooks' reader.
_syspath.on_sys_path(str(HERE.parents[2]))
API_BASE = importlib.import_module("rediacc_hooks.wellknown").GH_API_BASE

CASES = [
    # (name, command, expected tracer command in the refusal, or None when allowed)
    # --- one refusal per CI_READ_VERBS row ---
    ("pr checks", G + " pr checks 591", T),
    ("pr checks --watch", G + " pr checks 591 --watch", T + " --wait"),
    ("pr view rollup", G + " pr view 591 --json statusCheckRollup", T + " --json"),
    ("watchdog run list", G + ' run list --workflow "Watchdog Monitor"', T + " --watchdog"),
    ("run list", G + " run list --limit 1", T + " --runs"),
    (
        "run list of Console CI",
        G + ' run list --workflow "Console CI" --branch main',
        T + " --runs",
    ),
    ("run list -w ci.yml", G + " run list -w ci.yml", T + " --runs"),
    # 2026-10-04: scheduled runs point at `--scheduled`, the verb that lists them (before, the refusal named `--runs`, which cannot show a nightly or housekeeping run).
    (
        "run list --event schedule",
        G + " run list --event schedule --branch main",
        T + " --scheduled",
    ),
    (
        "run list --event=schedule of housekeeping",
        G + " run list --workflow housekeeping.yml --event=schedule",
        T + " --scheduled",
    ),
    ("run view --job --log", G + " run view --job 104569 --log", T + " --job 104569 --errors"),
    (
        "run view --log-failed",
        G + " run view 36953549081 --log-failed",
        T + " --run 36953549081 --why",
    ),
    ("run view", G + " run view 36953549081", T + " --run 36953549081 --jobs"),
    ("api job log", G + " api %s/actions/jobs/104569/logs" % REPO, T + " --job 104569 --log"),
    ("api job", G + " api %s/actions/jobs/104569" % REPO, T + " --job 104569 --steps"),
    (
        "api run jobs",
        G + " api %s/actions/runs/36953549081/jobs?per_page=100" % REPO,
        T + " --run 36953549081 --jobs",
    ),
    ("api run logs", G + " api %s/actions/runs/7/logs" % REPO, T + " --run 7 --why"),
    ("api run", G + " api %s/actions/runs/7" % REPO, T + " --run 7 --why"),
    ("api runs list", G + " api %s/actions/runs" % REPO, T + " --runs"),
    ("api annotations", G + " api %s/check-runs/9/annotations" % REPO, T + " --job 9 --errors"),
    ("api commit check-runs", G + " api %s/commits/abc/check-runs" % REPO, T + " --json"),
    ("api combined status", G + " api %s/commits/abc/status" % REPO, T + " --json"),
    (
        "graphql rollup",
        G + " api graphql -f query='{ x { statusCheckRollup { state } } }'",
        T + " --json",
    ),
    # --- the walk sees through the ways a read is RUN ---
    ("in a substitution", 'x="$(' + G + ' pr checks 591)"', T),
    ("after &&", "cd /tmp && " + G + " run list", T + " --runs"),
    ("in sh -c", "sh -c '" + G + " run view 5'", T + " --run 5 --jobs"),
    ("in bash -c, double quotes", 'bash -c "' + G + ' pr checks"', T),
    ("eval", "eval '" + G + " run list'", T + " --runs"),
    ("timeout prefix", "timeout 30 " + G + " run view 5 --log", T + " --run 5 --why"),
    (
        "log piped through sed and grep",
        G + " api %s/actions/jobs/3/logs --allow-escape-sequences | sed s/a/b/ | grep x" % REPO,
        T + " --job 3 --log",
    ),
    (
        "full URL endpoint",
        G + " api %s/%s/actions/jobs/3" % (API_BASE, REPO),
        T + " --job 3 --steps",
    ),
    ("a variable run id", G + ' api "%s/actions/runs/$RUN/jobs"' % REPO, T + " --run <id> --jobs"),
    ("explicit -X GET", G + " api -X GET %s/actions/runs/7" % REPO, T + " --run 7 --why"),
    ("--method=GET", G + " api --method=GET %s/actions/runs/7" % REPO, T + " --run 7 --why"),
    ("heredoc fed to bash", "bash <<'EOF'\n" + G + " run list\nEOF", T + " --runs"),
    # --- carve-outs: writes ---
    ("rerun", G + " run rerun 5 --failed", None),
    ("cancel", G + " run cancel 5", None),
    ("download", G + " run download 5 -n bridge-logs", None),
    ("delete", G + " run delete 5", None),
    ("run list of another workflow", G + ' run list --workflow "Release to Edge" --limit 3', None),
    ("api POST rerun", G + " api -X POST %s/actions/runs/5/rerun" % REPO, None),
    ("api -XPOST glued", G + " api -XPOST %s/actions/jobs/5/rerun" % REPO, None),
    ("api PATCH check-run", G + " api -X PATCH %s/check-runs/9 -f status=completed" % REPO, None),
    ("api body flag means POST", G + " api %s/check-runs -f name=x -f head_sha=abc" % REPO, None),
    ("api --input means POST", G + " api %s/check-runs --input body.json" % REPO, None),
    # --- carve-outs: not CI reads ---
    ("pr create", G + " pr create --draft --title t --body-file b.md", None),
    ("pr edit", G + " pr edit 591 --add-label x", None),
    ("pr ready", G + " pr ready 591", None),
    ("pr merge", G + " pr merge 591 --rebase", None),
    ("pr comment", G + " pr comment 591 --body x", None),
    ("pr view without rollup", G + " pr view 591 --json headRefOid,isDraft", None),
    ("pulls/<n>", G + " api %s/pulls/591 --jq .head.sha" % REPO, None),
    ("pull review comments", G + " api %s/pulls/591/comments" % REPO, None),
    ("issues", G + " api %s/issues/591/comments" % REPO, None),
    ("releases", G + " api %s/releases/latest" % REPO, None),
    ("artifacts", G + " api %s/actions/runs/5/artifacts" % REPO, None),
    (
        "graphql mutation",
        G + " api graphql -f query='mutation { resolveReviewThread { x } }'",
        None,
    ),
    ("workflow run dispatch", G + " workflow run ci-verdict.yml -f run_id=5", None),
    # --- prose and data: the read is NAMED, never run ---
    ("commit -m prose", 'git commit -m "docs: ' + G + ' pr checks is refused"', None),
    ("echo of a quoted read", "echo '" + G + " run view 5'", None),
    ("grep for the pattern", "grep -rn '" + G + " run list' docs/", None),
    (
        "worklist --add text",
        '.claude/hooks/stop/worklist.py --add abc "stop using ' + G + ' run view"',
        None,
    ),
    ("heredoc body written to a file", "cat > n.md <<'EOF'\n" + G + " run view 5\nEOF", None),
    ("the tracer itself", T + " --run 5 --why", None),
]


def _event(cmd):
    return json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}})


def via_dispatch(cmd):
    p = subprocess.run(GUARD_ARGV, input=_event(cmd), capture_output=True, text=True, check=False)
    return p.returncode, p.stdout + p.stderr


def _outside_defect(src: str, *names: str) -> str:
    """`src` with every top-level `DEFECT` (or named) assignment removed, so a needle search cannot be satisfied by the declaration that names it.

    `old in src` alone stays true after the guarded line is deleted, because the declaration itself contains the text it plants (measured 2026-10-05).
    """
    import ast  # noqa: PLC0415 -- only the planted-defect controls need it

    wanted = names or ("DEFECT",)
    cut = [
        n
        for n in ast.parse(src).body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id in wanted for t in n.targets)
    ]
    return "\n".join(
        line
        for i, line in enumerate(src.split("\n"), 1)
        if not any(n.lineno <= i <= (n.end_lineno or n.lineno) for n in cut)
    )


def defect_runner():
    """The guard with its declared DEFECT planted, run in-process."""
    _syspath.on_sys_path(str(HERE.parents[2]))
    hookio = importlib.import_module("rediacc_hooks.hookio")
    good = importlib.import_module("rediacc_hooks.guards." + STEM)

    old, new = good.DEFECT
    path = str(good.__file__)
    src = pathlib.Path(path).read_text(encoding="utf-8")
    if old not in _outside_defect(src):
        raise SystemExit(
            "the DEFECT no longer applies to the guard outside its own declaration: %r" % old
        )
    ns: dict[str, typing.Any] = {"__name__": "broken_" + STEM, "__file__": path}
    exec(compile(src.replace(old, new), path, "exec"), ns)  # noqa: S102

    def run(cmd):
        event = hookio.Event(_event(cmd))
        rc = ns["run"](event)
        _rc, out, err = event.result(rc)
        return rc, out + err

    return run


def main(argv):
    runner = defect_runner() if "--defect" in argv else via_dispatch
    refusals = sum(1 for c in CASES if c[2] is not None)
    allows = len(CASES) - refusals
    fails = 0
    for name, cmd, want in CASES:
        rc, text = runner(cmd)
        blocked = rc != 0
        if want is None:
            ok = not blocked
            detail = (
                "" if ok else "refused: " + text.strip().splitlines()[0] if text.strip() else ""
            )
        else:
            ok = blocked and ("use:  " + want + "\n") in text
            detail = "" if ok else ("allowed" if not blocked else "wrong use line: " + text[:200])
        fails += not ok
        print(
            "%-36s want=%-9s %s %s"
            % (
                name,
                "allowed" if want is None else "BLOCKED",
                "ok" if ok else "*** FAIL ***",
                detail,
            )
        )
    print()
    print("%d refusal case(s), %d allow case(s)" % (refusals, allows))
    if refusals < 10 or allows < 10:
        print("FLOOR: at least 10 of each direction is required")
        fails += 1
    print("FAILURES: %d" % fails)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

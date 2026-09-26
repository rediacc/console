"""Port of `scripts/ops/derive-shadow-pass-list.sh` (124 lines).

Derives the org secrets whose Bitwarden twin has PASSED a value-for-value compare, from real CI run output, and prints the exact `gh secret delete` commands. It prints them; it does not run them. Deleting a secret is irreversible and is the operator's to execute.

WHY THE TOOL EXISTS AT ALL, carried from the twin because it is the reason the derivation may not be done by hand: a fallback may only be destroyed after something has compared it to its replacement VALUE BY VALUE, the only place both values exist at once is the shadow compare step in CI, and its verdict lives in run logs that expire. The "42 agree" figure the migration ran on
came from run 33691632299, which was CANCELLED and whose logs no longer return a single verdict line.

WHO CALLS IT: nobody. It is an operator entry point invoked by hand, surveyed as such at `scripts/data/domains.json:118`.

    PYTHONPATH=.ci python3 -m rediacc_ci.ops.derive_shadow_pass_list [--branch <branch>] [--runs <n>]

PORT NOTES, each driven before it was written down.

THE TWIN WAS ALREADY HALF PYTHON. Its last 35 lines were a `python3 - <<'PY'` heredoc doing the shadow-name to github-name mapping and the two `gh api` calls. That half moves across unchanged in substance, which is why the divergence surface of this port is the bash half above it.

`grep -l ... | xargs -n1 basename` IS RUN AS THE PIPELINE IT IS, not reimplemented. Three behaviours depend on that and all three are recorded cases. An empty glob leaves bash passing the LITERAL pattern to grep, which then reports it as a missing file on stderr. `xargs -n1` over empty input still runs `basename` ONCE, with no operand, which prints its own usage to stderr. And
this repository runs ugrep rather than GNU grep, so a Python reimplementation would answer a question about a different program from the one CI runs.

THE FOUR `sort -u` STAGES BECOME SETS, and the reason that is safe is that nothing downstream reads their ORDER. `pairs.txt` is consumed by two counting passes and by a membership test; the one ordered output, the `gh secret delete` lines, is sorted by the Python half on its own. What the counts must agree on is CARDINALITY, which a set gives exactly.

A JOB'S OWN CONCLUSION IS THE FILTER, NOT THE RUN'S, and the comment the twin carries for it is load-bearing rather than decorative. A run cancelled by the watchdog can still contain jobs that ran their compare step and printed a verdict; run 33718710855 is exactly that shape. The converse still holds and is why this is not a relaxation: a job whose own conclusion is cancelled or
failed did not report, and its absence of a verdict must never read as a pass.

`set -u` WITHOUT `set -e`, reproduced in both halves. A missing value after `--branch` is an unbound `$2`, which is FATAL under `set -u` even with no `set -e`: bash prints `$2: unbound variable` and exits 1 before any work happens. Reproduced with the same sentence and status, without forging bash's line number. Everything else runs to the end regardless of what failed, which
is why a `gh` that cannot answer yields an empty verdict set rather than a crash.

THE TWO `gh api` CALLS RAISE, and that is the twin's behaviour too: the heredoc passed `check=True`, so an unreachable API ends the program with a traceback and a non-zero status rather than with a silently short org list. A shorter org list would silently reclassify a deletable secret as "not an org secret", which is the wrong direction to be wrong in.

Exit: 0 when a deletable list was derived; 1 when no passing compare exists on the branch, or when `--branch` was given no value; 2 on an unknown argument or an absent `gh`.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import subprocess
import sys

WORKFLOW_GLOB = ".github/workflows/*.yml"
WORKFLOW_DIR = ".github/workflows"
COMPARE_NEEDLE = "Compare shadow secrets against GitHub"
VERDICT_RE = "shadow [A-Z0-9_]+ (match|MISMATCH|EMPTY)"
GH_BINDING_RE = re.compile(r"GH_([A-Z0-9_]+):\s*\$\{\{\s*secrets\.([A-Z0-9_]+)\s*\}\}")

ORG_SECRETS_API = "orgs/rediacc/actions/secrets"
REPO_SECRETS_API = "repos/rediacc/console/actions/secrets"

DEFAULT_RUNS = "6"


def _err(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def current_branch() -> str:
    """`git symbolic-ref --quiet --short HEAD 2>/dev/null || echo main`."""
    try:
        proc = subprocess.run(
            ["git", "symbolic-ref", "--quiet", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return "main"
    if proc.returncode != 0:
        return "main"
    return proc.stdout.rstrip("\n")


def shadow_carrying_workflows() -> list[str]:
    """`grep -l <needle> .github/workflows/*.yml | xargs -n1 basename`, run as that pipeline.

    The glob is expanded here the way bash expands it, INCLUDING the arm where it matches nothing and the unexpanded pattern is handed to grep as a filename.
    """
    matches = sorted(str(p) for p in pathlib.Path().glob(WORKFLOW_GLOB.replace("*", "[!.]*")))
    argv = ["grep", "-l", COMPARE_NEEDLE, *(matches or [WORKFLOW_GLOB])]
    grep = subprocess.Popen(argv, stdout=subprocess.PIPE)
    xargs = subprocess.run(
        ["xargs", "-n1", "basename"],
        stdin=grep.stdout,
        stdout=subprocess.PIPE,
        text=True,
        check=False,
    )
    if grep.stdout is not None:
        grep.stdout.close()
    grep.wait()
    return [line for line in xargs.stdout.splitlines() if line]


def _gh(args: list[str]) -> tuple[int, str]:
    """One `gh` call whose stderr the twin sent to /dev/null."""
    proc = subprocess.run(["gh", *args], capture_output=True, text=True, check=False)
    return proc.returncode, proc.stdout


def run_ids(workflow: str, branch: str, runs: str) -> list[str]:
    _, out = _gh(
        [
            "run",
            "list",
            "--workflow=%s" % workflow,
            "--branch",
            branch,
            "--limit",
            runs,
            "--json",
            "databaseId",
            "-q",
            ".[].databaseId",
        ]
    )
    return out.splitlines()


def successful_job_count(run_id: str) -> str:
    """`gh run view --json jobs -q ... || echo 0`, with the substitution's trailing-newline strip."""
    rc, out = _gh(
        [
            "run",
            "view",
            run_id,
            "--json",
            "jobs",
            "-q",
            '[.jobs[]|select(.conclusion=="success")|.name]|length',
        ]
    )
    if rc != 0:
        return "0"
    return out.rstrip("\n")


def verdicts_in_log(run_id: str) -> list[str]:
    """`gh run view <id> --log | grep -oE '<verdict>' || true`, run as that pipeline."""
    _, log = _gh(["run", "view", run_id, "--log"])
    grep = subprocess.run(
        ["grep", "-oE", VERDICT_RE],
        input=log,
        capture_output=True,
        text=True,
        check=False,
    )
    if grep.stderr:
        sys.stderr.write(grep.stderr)
        sys.stderr.flush()
    return grep.stdout.splitlines()


def github_names_by_shadow() -> dict[str, set[str]]:
    """The `GH_<shadow>: ${{ secrets.<github> }}` bindings.

    The two names differ wherever the migration renamed something, and deleting by the shadow name would delete the wrong secret.
    """
    out: dict[str, set[str]] = {}
    for path in pathlib.Path(WORKFLOW_DIR).glob("*.yml"):
        for match in GH_BINDING_RE.finditer(path.read_text(encoding="utf-8")):
            out.setdefault(match.group(1), set()).add(match.group(2))
    return out


def secret_names(endpoint: str) -> set[str]:
    proc = subprocess.run(
        ["gh", "api", endpoint, "--paginate", "-q", "[.secrets[].name]"],
        capture_output=True,
        text=True,
        check=True,
    )
    return set(json.loads(proc.stdout))


def emit_delete_commands(passed: set[str]) -> None:
    """The twin's `python3 - <<'PY'` half, unchanged in substance."""
    gh_of = github_names_by_shadow()
    org = secret_names(ORG_SECRETS_API)
    repo = secret_names(REPO_SECRETS_API)
    _err("# %d org secret(s), %d repo-level" % (len(org), len(repo)))
    out: list[str] = []
    skipped: list[tuple[str, str]] = []
    for shadow in sorted(passed):
        names = gh_of.get(shadow, set())
        if len(names) != 1:
            skipped.append(
                (shadow, "reads %d github name(s): %s" % (len(names), sorted(names) or "none"))
            )
            continue
        name = next(iter(names))
        if name not in org:
            skipped.append((shadow, "%s is not an org secret" % name))
            continue
        if name in repo:
            # A repo-level twin SHADOWS the org one, so the compare tested the repo copy and the org copy has never been compared. This is exactly how CLAUDE_CODE_OAUTH_TOKEN looked, and deleting on that evidence would destroy an unverified value.
            skipped.append(
                (
                    shadow,
                    "%s also exists REPO-level, which shadows the org copy; "
                    "the compare tested the repo one" % name,
                )
            )
            continue
        out.append(name)
    for name in out:
        print("gh secret delete %s --org rediacc" % name, flush=True)
    for shadow, why in skipped:
        _err("# SKIP %s: %s" % (shadow, why))
    _err("# %d deletable, %d skipped" % (len(out), len(skipped)))


def main(argv: list[str]) -> int:
    branch = os.environ.get("BRANCH") or current_branch()
    runs = DEFAULT_RUNS
    rest = list(argv)
    while rest:
        flag = rest.pop(0)
        if flag in ("--branch", "--runs"):
            if not rest:
                # `BRANCH="$2"` with no `$2` is fatal under `set -u`, before any work happens.
                _err("$2: unbound variable")
                return 1
            value = rest.pop(0)
            if flag == "--branch":
                branch = value
            else:
                runs = value
            continue
        _err("unknown arg: %s" % flag)
        return 2

    # `command -v gh` RESOLVES the name, it does not run the program. Spelling this as a `gh --version` probe would put a call in front of every later one.
    if shutil.which("gh") is None:
        _err("gh is required")
        return 2

    _err("# deriving from branch %s, up to %s run(s) per shadow-carrying workflow" % (branch, runs))

    workflows = shadow_carrying_workflows()
    _err("# %d shadow-carrying workflow(s)" % len(workflows))

    # JOB conclusion, not RUN conclusion: see the module docstring.
    verdicts: set[str] = set()
    for workflow in workflows:
        for run_id in run_ids(workflow, branch, runs):
            if not run_id:
                continue
            if successful_job_count(run_id) in ("", "0"):
                continue
            verdicts.update(verdicts_in_log(run_id))

    pairs = {
        (parts[1], parts[2]) for parts in (line.split() for line in verdicts) if len(parts) > 2
    }
    ok = {name for name, verdict in pairs if verdict == "match"}
    bad = {name for name, verdict in pairs if verdict != "match"}
    passed = ok - bad

    _err(
        "# verdicts seen: %d, clean-pass names: %d, names with a non-match: %d"
        % (len(pairs), len(passed), len(bad))
    )
    if not passed:
        _err(
            "REFUSING: no passing compare found on %s. Push and let CI run; "
            "a cancelled run reports nothing." % branch
        )
        return 1

    emit_delete_commands(passed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

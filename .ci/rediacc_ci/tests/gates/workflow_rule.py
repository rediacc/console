"""`.ci/scripts/test/lib/workflow-rule.sh`, ported. The harness for the rules
that live inside `.ci/scripts/quality/check_workflows.py`.

WHY IT IS SHARED, and why between exactly these callers rather than every workflow test. check-workflows.sh hosts several banned-pattern rules, and each gets its own gate test driving it against a fixture tree. The incantation is
exact and easy to get subtly wrong: `WORKFLOW_INLINE_ONLY=1` is what empties
GITHUB_YAMLS (check-workflows.sh:38-40) so the banned-pattern scans become no-ops and the FIXTURE TREE is the only thing judged. Without it a test both trips on and depends on the real `.github` state.

test-workflow-contracts.sh looks like it belongs here and does NOT: it drives `.ci/scripts/security/check-workflow-gates.sh` with `WORKFLOWS_DIR` -- a different script, a different variable, no inline-only switch. The five lines
rhyme; the contract does not. Folding it in would produce a helper with two
meanings.

THE ONE DIFFERENCE FROM THE BASH ORIGINAL, and it is a real one rather than a
translation artefact. `workflow-rule.sh` hard-codes `CI=true`, and
test-workflow-inline.sh does NOT source it: that file defines its own `run_check`
with no `CI` assignment at all. Two callers, two environments, one incantation
otherwise. Rather than hide that difference behind a default, `ci` is an explicit argument here and each caller states which side of it it is on, so a reader can see that inline's fixtures are judged with CI unset exactly as the twin judges them.

STREAMS ARE MERGED, matching `2>&1` in both bash callers. These rules write their findings to stdout and their diagnostics to stderr, and every assertion is about "what the author sees", which is the merged text.
"""

import os
import pathlib

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

CHECK = paths.from_root(".ci", "scripts", "quality", "check-workflows.sh")


def run_check(
    gate, directory: os.PathLike[str] | str, *, ci: bool, extra_env: dict[str, str] | None = None
) -> harness.RunResult:
    """Drive ONLY the workflow rules against `directory`.

    `gate` is taken so a MISSING subject reds as a named refusal here rather than as a `FileNotFoundError` from deep inside subprocess, which would read as flake and name no remedy.
    """
    if not CHECK.is_file():
        gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(CHECK))
    env = {"WORKFLOW_INLINE_ONLY": "1", "WORKFLOW_DIR": str(directory)}
    if ci:
        env["CI"] = "true"
    if extra_env:
        env.update(extra_env)
    return harness.run([str(CHECK)], env=env)


def write_job(path: pathlib.Path, *lines: str) -> None:
    """A one-job workflow whose extra `lines` land at JOB level, under `j:`.

    Byte-for-byte the twin's `write_job`: four bytes of indent on the caller's lines, because job-level keys sit at that depth and the rule under test keys on the indentation.
    """
    body = ["name: fixture", "on: push", "jobs:", "  j:", "    runs-on: ubuntu-latest"]
    body += ["    %s" % line for line in lines]
    body += ["    steps:", "      - run: ./script.sh"]
    path.write_text("\n".join(body) + "\n", encoding="utf-8")


def write_step_env(path: pathlib.Path, *lines: str) -> None:
    """A one-step workflow whose `lines` land inside that step's `env:` mapping.

    Ten bytes of indent, which is what puts them one level inside `env:` at eight. The env-shell-var rule's whole dedent behaviour is keyed on that, so the number is not cosmetic.
    """
    body = [
        "name: fixture",
        "on: push",
        "jobs:",
        "  j:",
        "    runs-on: ubuntu-latest",
        "    steps:",
        "      - run: ./script.sh",
        "        env:",
    ]
    body += ["          %s" % line for line in lines]
    path.write_text("\n".join(body) + "\n", encoding="utf-8")

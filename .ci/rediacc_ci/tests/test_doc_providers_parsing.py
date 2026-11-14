"""Two readers in `scripts/lib/doc-providers.ts`, run under node because neither is exported (`lint:unused` refuses an export nothing imports) and one uses a lookbehind Python's `re` cannot take.

`firstHeading` and `titleCell` build the agent-reference table (reviews de2cd4c9.1, .3, .4), and the hook-path pattern of `wiredHooks` decides which wired commands reach the hook table (reviews 9c563f7f.1 and .2).
"""

import json
import re
import shutil
import subprocess
from typing import Any

import pytest

from rediacc_ci import paths

SOURCE = (paths.repo_root() / "scripts/lib/doc-providers.ts").read_text(encoding="utf-8")
NODE = shutil.which("node")


def _node(script: str) -> Any:
    assert NODE, "node is required"
    done = subprocess.run(
        [NODE, "--input-type=module", "-e", script], capture_output=True, text=True, check=True
    )
    return json.loads(done.stdout)


def _function(name: str) -> str:
    """The `const <name> = ...;` definition, with its parameter types removed."""
    found = re.search(r"^const %s = (?:[^\n]*;$|.*?^\};$)" % name, SOURCE, re.DOTALL | re.MULTILINE)
    assert found, "%s not found in doc-providers.ts" % name
    return re.sub(r"\((\w+): string\): string", r"(\1)", found.group(0))


def _headings(cases: list[str]) -> list[str]:
    script = "%s\nconsole.log(JSON.stringify(%s.map(firstHeading)));" % (
        _function("firstHeading"),
        json.dumps(cases),
    )
    return _node(script)


def test_a_tilde_fence_closed_by_backticks_stays_fenced():
    assert _headings(["~~~\n```\n# not a title\n~~~\n# Real\n"]) == ["Real"]


def test_a_longer_fence_holds_a_shorter_one():
    assert _headings(["````md\n```\n# inside\n```\n````\n# After\n"]) == ["After"]


def test_plain_fence_and_first_heading():
    assert _headings(["intro\n```\n# code\n```\n# Title\n# Second\n"]) == ["Title"]


def test_no_heading_outside_a_fence_is_empty():
    assert _headings(["```\n# only code\n```\n"]) == [""]


def test_title_cell_escapes_a_pipe_and_names_a_missing_title():
    script = "%s\nconsole.log(JSON.stringify([titleCell(''), titleCell('A | B')]));" % _function(
        "titleCell"
    )
    assert _node(script) == ["(no title)", "A \\| B"]


@pytest.mark.parametrize(
    ("command", "hits"),
    [
        ('bash "$CLAUDE_PROJECT_DIR/run.sh" worktree', ["run.sh"]),
        ("${CLAUDE_PROJECT_DIR}/run.sh worktree", ["run.sh"]),
        ("./run.sh worktree", ["run.sh"]),
        ("cd a/run.sh", []),
        (
            'python3 "$CLAUDE_PROJECT_DIR/.claude/rediacc_hooks/dispatch.py"',
            [".claude/rediacc_hooks/dispatch.py"],
        ),
    ],
)
def test_the_wired_hook_pattern_reaches_run_sh_in_each_spelling(command, hits):
    literal = re.search(r"matchAll\(\s*\n\s*(/.+/g)\n", SOURCE)
    assert literal, "the wiredHooks pattern was not found"
    script = (
        "const re = %s;\nconsole.log(JSON.stringify([...%s.matchAll(re)].map((m) => m[0])));"
        % (literal.group(1), json.dumps(command))
    )
    assert _node(script) == hits

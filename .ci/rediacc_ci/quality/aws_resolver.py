r"""check:ci-aws-resolver -- every `aws` call in this repo goes through `rediacc_ci.core.awscli`, so the pinned aws CLI is the one that runs.

WHY. Until 2026-10-19 (agent/plans/PLAN-pin-awscli-toolchain-python-compatible.md) twenty-three modules exec'd a bare `"aws"` argv[0] after their own presence check (`common.require_cmd("aws")`, `shutil.which("aws")`, a local `_require_cmd`), so the CLI that wrote production R2 was whatever the runner image or the developer's host carried, and a dev host with none refused outright. `core.awscli` resolves `AWS_BIN`, then PATH, then the pinned cache install; this gate keeps a new call site from walking around it.

THE RULES, each with a plant in the controls that must turn it red:

  argv-head       no Python list or tuple literal outside `core/awscli.py` and the
                  tests starts with the string `"aws"`: an argv is built with
                  `awscli.AWS` at its head.
  presence        no call named `require_cmd`, `_require_cmd` or `which` takes the
                  literal `"aws"`: presence is `awscli.require()`.
  resolver        a module that names `awscli.AWS` also calls `awscli.run`,
                  `awscli.argv`, `awscli.require` or `awscli.resolve`, so the argv it
                  builds reaches the resolver before it is exec'd.
  shell           no workflow (`.github/workflows/*.yml`) and no `.ci/**/*.sh` runs a
                  bare `aws s3`, `aws s3api` or `aws iam` at command position; the
                  shell spelling is `"${AWS_BIN:-aws}"`. Comment lines are not commands.

A CORPUS FLOOR. Fewer than `MIN_MODULES` Python modules importing `awscli` means the scan is not looking at the tree the rules were written for (a moved package, an emptied glob), and that is a refusal (exit 2), never a pass.

Exit 0 clean, 1 on any finding, 2 on a failed control or a corpus too small to judge.
"""

from __future__ import annotations

import ast
import pathlib
import re
import sys
from dataclasses import dataclass

from rediacc_ci import log, paths
from rediacc_ci.controls import Checker, controls_first, plant

PACKAGE_REL = ".ci/rediacc_ci"
RESOLVER_REL = ".ci/rediacc_ci/core/awscli.py"
TESTS_REL = ".ci/rediacc_ci/tests"
WORKFLOWS_REL = ".github/workflows"
SHELL_ROOT_REL = ".ci"

# The aws call-site modules found on 2026-10-19 number 22; a scan seeing fewer than this many has lost the tree.
MIN_MODULES = 20

PRESENCE_CALLS = ("require_cmd", "_require_cmd", "which")
RESOLVER_CALLS = ("run", "argv", "require", "resolve")
# `aws s3 ...` at command position: line start, a YAML `run:`, or after a pipe, `;`, `&&`, `||`, `(`, `$(` or a backtick, then optional `then`/`do`/`else`/`exec`/`!` keywords and VAR=value prefixes.
SHELL_RE = re.compile(
    r"(?:^|[;&|(`]|\$\(|\brun:)\s*(?:(?:then|do|else|exec|!)\s+)*"
    r"(?:[A-Za-z_][A-Za-z0-9_]*=\S*\s+)*aws\s+(?:s3api|s3|iam)\b"
)


class CannotRunError(RuntimeError):
    """The corpus is missing or too small to judge."""


@dataclass(frozen=True)
class Finding:
    rule: str
    where: str
    detail: str


def _call_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return ""


def _is_aws(node: ast.AST | None) -> bool:
    return isinstance(node, ast.Constant) and node.value == "aws"


def _is_awscli_attr(node: ast.AST, attr: str | tuple[str, ...]) -> bool:
    names = (attr,) if isinstance(attr, str) else attr
    return (
        isinstance(node, ast.Attribute)
        and node.attr in names
        and isinstance(node.value, ast.Name)
        and node.value.id == "awscli"
    )


def python_findings(source: str, rel: str) -> tuple[list[Finding], bool]:
    """(findings, imports awscli) for one module's source."""
    tree = ast.parse(source, filename=rel)
    findings: list[Finding] = []
    names_aws = False
    calls_resolver = False
    imports = False
    for node in ast.walk(tree):
        if isinstance(node, (ast.List, ast.Tuple)) and node.elts and _is_aws(node.elts[0]):
            findings.append(
                Finding(
                    "argv-head", "%s:%d" % (rel, node.lineno), 'a "aws" argv head; write awscli.AWS'
                )
            )
        elif isinstance(node, ast.Call):
            name = _call_name(node)
            if name in PRESENCE_CALLS and node.args and _is_aws(node.args[0]):
                findings.append(
                    Finding(
                        "presence",
                        "%s:%d" % (rel, node.lineno),
                        '%s("aws"); use awscli.require()' % name,
                    )
                )
            if _is_awscli_attr(node.func, RESOLVER_CALLS):
                calls_resolver = True
        elif _is_awscli_attr(node, "AWS"):
            names_aws = True
        elif isinstance(node, ast.ImportFrom) and node.module == "rediacc_ci.core":
            imports = imports or any(alias.name == "awscli" for alias in node.names)
    if names_aws and not calls_resolver:
        findings.append(
            Finding(
                "resolver",
                rel,
                "names awscli.AWS but never calls awscli.run/argv/require/resolve, so its argv is exec'd unresolved",
            )
        )
    return findings, imports


def shell_findings(text: str, rel: str) -> list[Finding]:
    found: list[Finding] = []
    for number, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("#"):
            continue
        if SHELL_RE.search(line):
            found.append(
                Finding(
                    "shell",
                    "%s:%d" % (rel, number),
                    'a bare aws command; write "${AWS_BIN:-aws}"',
                )
            )
    return found


def gather(root: pathlib.Path) -> tuple[list[Finding], int]:
    package = root / PACKAGE_REL
    if not package.is_dir():
        raise CannotRunError("%s is not a directory" % package)
    findings: list[Finding] = []
    importers = 0
    skip = {root / RESOLVER_REL}
    tests = root / TESTS_REL
    for path in sorted(package.rglob("*.py")):
        if path in skip or tests in path.parents or "__pycache__" in path.parts:
            continue
        rel = path.relative_to(root).as_posix()
        got, imports = python_findings(path.read_text(encoding="utf-8"), rel)
        findings.extend(got)
        importers += int(imports)
    if importers < MIN_MODULES:
        raise CannotRunError(
            "only %d module(s) under %s import core.awscli, below the floor of %d"
            % (importers, PACKAGE_REL, MIN_MODULES)
        )
    shell_files = sorted((root / WORKFLOWS_REL).glob("*.yml")) + sorted(
        p
        for p in (root / SHELL_ROOT_REL).rglob("*.sh")
        if "cache" not in p.relative_to(root).parts[:2]
    )
    if not shell_files:
        raise CannotRunError("no workflow or .ci shell file found to scan")
    for path in shell_files:
        findings.extend(
            shell_findings(
                path.read_text(encoding="utf-8", errors="replace"),
                path.relative_to(root).as_posix(),
            )
        )
    return findings, importers


def render(findings: list[Finding], importers: int) -> int:
    if findings:
        for finding in findings:
            log.error("[%s] %s: %s" % (finding.rule, finding.where, finding.detail))
        log.error(
            "aws resolver: %d finding(s) across %d awscli module(s); route aws through rediacc_ci.core.awscli"
            % (len(findings), importers)
        )
        return 1
    log.success("aws resolver: clean, %d module(s) route aws through core.awscli" % importers)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if "--selftest" in args:
        return 1 if selftest() else 0
    rc = controls_first("aws resolver", selftest)
    if rc:
        return rc
    root = pathlib.Path(paths.repo_root())
    if "--root" in args and args.index("--root") + 1 < len(args):
        root = pathlib.Path(args[args.index("--root") + 1]).resolve()
    try:
        findings, importers = gather(root)
    except (CannotRunError, OSError, SyntaxError) as exc:
        log.error("aws resolver: CANNOT RUN: %s" % exc)
        return 2
    return render(findings, importers)


# --------------------------------------------------------------------------- controls

FIX_MODULE = """
import subprocess
from rediacc_ci.core import awscli, common


def list_argv(bucket):
    return [awscli.AWS, "s3api", "list-objects-v2", "--bucket", bucket]


def main():
    awscli.require()
    common.require_cmd("gh")
    return awscli.run(list_argv("b"), capture_output=True).returncode
"""

FIX_SHELL = """#!/usr/bin/env bash
# aws s3 cp in a comment is not a command
AWS="${AWS_BIN:-aws}"
"$AWS" s3 cp a s3://b/a
echo "run aws s3 ls to see it"
"""


def _rules(findings: list[Finding]) -> set[str]:
    return {f.rule for f in findings}


def selftest() -> bool:
    """True when a control failed, which is what `controls_first` expects."""
    check = Checker()
    clean, imports = python_findings(FIX_MODULE, "f.py")
    check("CONTROL: a module routed through awscli is clean", clean == [])
    check("CONTROL: and it counts as an awscli importer", imports)
    check(
        "CONTROL: a resolved shell call and a comment are clean",
        shell_findings(FIX_SHELL, "f.sh") == [],
    )

    planted = plant(FIX_MODULE, "[awscli.AWS, ", '["aws", ')
    check(
        "PLANT argv-head: a literal aws argv head is a finding",
        _rules(python_findings(planted, "f.py")[0]) == {"argv-head"},
    )
    planted = plant(
        FIX_MODULE, "    awscli.require()\n", '    subprocess.run(("aws", "s3", "ls"))\n'
    )
    check(
        "PLANT argv-head: a tuple argv counts too",
        "argv-head" in _rules(python_findings(planted, "f.py")[0]),
    )
    planted = plant(FIX_MODULE, 'common.require_cmd("gh")', 'common.require_cmd("aws")')
    check(
        "PLANT presence: require_cmd of aws is a finding",
        _rules(python_findings(planted, "f.py")[0]) == {"presence"},
    )
    planted = plant(
        FIX_MODULE,
        "import subprocess\n",
        'import shutil, subprocess\nFOUND = shutil.which("aws")\n',
    )
    check(
        "PLANT presence: shutil.which of aws is a finding",
        "presence" in _rules(python_findings(planted, "f.py")[0]),
    )
    planted = plant(FIX_MODULE, "    awscli.require()\n", "")
    planted = plant(planted, "awscli.run(list_argv", "subprocess.run(list_argv")
    check(
        "PLANT resolver: awscli.AWS exec'd without the resolver is a finding",
        _rules(python_findings(planted, "f.py")[0]) == {"resolver"},
    )
    planted = plant(FIX_SHELL, '"$AWS" s3 cp', "aws s3 cp")
    check(
        "PLANT shell: a bare aws s3 at line start is a finding",
        _rules(shell_findings(planted, "f.sh")) == {"shell"},
    )
    planted = plant(
        FIX_SHELL,
        '"$AWS" s3 cp a s3://b/a',
        "for d in a b; do aws s3api head-object --key $d; done",
    )
    check(
        "PLANT shell: a bare aws s3api after `do` is a finding",
        _rules(shell_findings(planted, "f.sh")) == {"shell"},
    )
    planted = plant(FIX_SHELL, '"$AWS" s3 cp a s3://b/a', "KEYS=$(aws iam list-access-keys)")
    check(
        "PLANT shell: a bare aws iam inside $( ) is a finding",
        _rules(shell_findings(planted, "f.sh")) == {"shell"},
    )
    return not check.ok


if __name__ == "__main__":
    raise SystemExit(main())

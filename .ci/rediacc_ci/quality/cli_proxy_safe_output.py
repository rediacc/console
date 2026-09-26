"""The CLI writes output and sets its exit status through the request-aware helpers, never the process streams.

WHY. `rdc serve` runs commands in-process for many callers at once (packages/cli/src/services/serve/command-dispatch.ts), and services/core/request-context.ts binds a per-request context: writeStdout / writeStderr push into the request's buffers, setExitCode sets the request's exit code, and exitProcess unwinds the request. A command that calls `process.stdout.write`, `process.stderr.write` or `console.*` directly, or assigns `process.exitCode`, bypasses all of it: under the proxy its output lands on the EXECUTOR's stdout and the client gets empty output and exit 0. Found 2026-09-24: `repo cat` returned no bytes and exit 0 through the proxy, the JSON error envelope never reached the client (utils/errors.ts), and about forty sibling sites across twenty files had the same shape.

WHAT IT CHECKS. Every non-test TypeScript file under packages/cli/src, line by line, for
  - `process.stdout.write` / `process.stderr.write`   -> writeStdout / writeStderr
  - `process.exitCode =`                              -> setExitCode
  - `console.log|error|warn|info|debug(`              -> outputService, or writeStdout / writeStderr
Comment lines are skipped. A file on ALLOWED may keep EXACTLY its pinned number of sites: one more is a finding (a new bypass in a file that is exempt for an unrelated reason), one fewer is a finding too (lower the pin, so the exemption shrinks with the code), and an entry whose file is gone is dead.

Exit 0 clean, 1 on findings, 2 when the gate's own controls fail (controls_first convention).
"""

from __future__ import annotations

import re
import sys
from typing import TYPE_CHECKING, NamedTuple

from rediacc_ci import paths
from rediacc_ci.controls import controls_first
from rediacc_ci.core import allowlist

if TYPE_CHECKING:
    import pathlib

CLI_SRC = "packages/cli/src"
_SUFFIXES = (".ts", ".tsx", ".mts", ".cts")

_RULES: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "process.stdout.write",
        re.compile(r"\bprocess\.stdout\.write\b"),
        "writeStdout() from services/core/request-context.ts (it takes bytes too)",
    ),
    (
        "process.stderr.write",
        re.compile(r"\bprocess\.stderr\.write\b"),
        "writeStderr() from services/core/request-context.ts",
    ),
    (
        "process.exitCode =",
        re.compile(r"\bprocess\.exitCode\s*=(?!=)"),
        "setExitCode() from services/core/request-context.ts",
    ),
    (
        "console.*",
        re.compile(r"\bconsole\.(?:log|error|warn|info|debug)\s*\("),
        "outputService, or writeStdout()/writeStderr() from services/core/request-context.ts",
    ),
)

_COMMENT = re.compile(r"^\s*(?://|/\*|\*)")


class Allowed(NamedTuple):
    sites: int
    reason: str


# Files that legitimately touch the process streams, each pinned to its exact site count.
ALLOWED: dict[str, Allowed] = {
    "services/core/request-context.ts": Allowed(
        3,
        "BLOCKER: this file IS the sanctioned seam; writeStdout, writeStderr and setExitCode fall"
        " through to the process streams only when no request context is bound",
    ),
    "services/core/output.ts": Allowed(
        3,
        "BLOCKER: outputService's writeOut, writeErr and writeProse push into the request buffers"
        " inside a dispatch and reach console only when no request context is bound",
    ),
    "index.ts": Allowed(
        1,
        "BLOCKER: the process entry point reports an MCP server boot failure before any command"
        " or request context exists, then exits the process",
    ),
    "warmup.ts": Allowed(
        1,
        "BLOCKER: the SEA bundle smoke check runs as its own process mode (index.ts --warmup),"
        " never as a command, so no request context can be bound around it",
    ),
    "utils/debug.ts": Allowed(
        1,
        "BLOCKER: REDIACC_DEBUG lines are the executor operator's own diagnostics; inside a"
        " dispatch they belong in the executor log, not in a tenant's response",
    ),
    "commands/vscode.ts": Allowed(
        2,
        "BLOCKER: vscode connect, list, cleanup and check edit the local SSH config and launch a"
        " local VS Code; the contract marks all four proxyCapable false, so none runs in a dispatch",
    ),
    "templates/embedded.generated.ts": Allowed(
        4,
        "BLOCKER: the matches are inside generated template text (a Node server shipped to"
        " machines by scripts/embed-templates.ts), not CLI code that writes anything",
    ),
}


class Site(NamedTuple):
    line: int
    rule: str
    text: str


def scan_text(text: str) -> list[Site]:
    """Every bypass site in one file's text, comment lines excluded."""
    sites: list[Site] = []
    for number, line in enumerate(text.splitlines(), 1):
        if _COMMENT.match(line):
            continue
        for rule, pattern, _fix in _RULES:
            if pattern.search(line):
                sites.append(Site(number, rule, line.strip()))
    return sites


def is_test(rel: str) -> bool:
    return "/__tests__/" in "/" + rel or rel.endswith((".test.ts", ".spec.ts"))


def _fix_for(rule: str) -> str:
    return next(fix for name, _pattern, fix in _RULES if name == rule)


def verdict(files: dict[str, str], allowed: dict[str, Allowed]) -> list[str]:
    """Findings for `files` (path relative to packages/cli/src -> text) against `allowed`."""
    out: list[str] = []
    for rel, reason in sorted(allowed.items()):
        if not reason.reason.startswith("BLOCKER:"):
            out.append("%s: the allowlist reason must start with 'BLOCKER:'" % rel)
            continue
        rejection = allowlist.validate_reason(rel, reason.reason[len("BLOCKER:") :], "ALLOWED")
        if rejection is not None:
            out.append(rejection.message)
    for rel, text in sorted(files.items()):
        if is_test(rel):
            continue
        sites = scan_text(text)
        pinned = allowed.get(rel)
        if pinned is None:
            out.extend(
                "%s/%s:%d: %s bypasses the request context; use %s. %s"
                % (CLI_SRC, rel, s.line, s.rule, _fix_for(s.rule), s.text)
                for s in sites
            )
        elif len(sites) > pinned.sites:
            out.append(
                "%s/%s: %d process-stream sites, pinned at %d. A NEW bypass in an exempt file is"
                " still a bypass: route it through request-context.ts. Sites:\n      %s"
                % (
                    CLI_SRC,
                    rel,
                    len(sites),
                    pinned.sites,
                    "\n      ".join("%d: %s" % (s.line, s.text) for s in sites),
                )
            )
        elif len(sites) < pinned.sites:
            out.append(
                "%s/%s: %d process-stream sites, pinned at %d. Lower its ALLOWED pin in"
                " .ci/rediacc_ci/quality/cli_proxy_safe_output.py to %d (drop the entry at 0)."
                % (CLI_SRC, rel, len(sites), pinned.sites, len(sites))
            )
    out.extend(
        "%s/%s: on ALLOWED but not in the tree; delete the dead entry" % (CLI_SRC, rel)
        for rel in sorted(set(allowed) - set(files))
    )
    return out


def tree_files(root: pathlib.Path) -> dict[str, str]:
    base = root / CLI_SRC
    return {
        path.relative_to(base).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(base.rglob("*"))
        if path.is_file() and path.suffix in _SUFFIXES and not path.name.endswith(".d.ts")
    }


_OK_ALLOWED = {
    "seam.ts": Allowed(1, "BLOCKER: the planted seam that is allowed exactly one process write"),
}


def selftest() -> bool:
    """True when a control FAILED."""
    failed = False

    def expect(label: str, files: dict[str, str], want_findings: bool) -> None:
        nonlocal failed
        got = verdict(files, _OK_ALLOWED)
        if bool(got) != want_findings:
            print(
                "✗ control: %s (%s)" % (label, got or "no finding"),
                file=sys.stderr,
            )
            failed = True

    seam = {"seam.ts": "process.stdout.write(x);\n"}
    expect("a clean tree read as a finding", {**seam, "a.ts": "writeStdout(x);\n"}, False)
    for plant in (
        "process.stdout.write(buf);",
        "  process.stderr.write(`x`);",
        "process.exitCode = 1;",
        "(options.onStdout ?? process.stdout.write.bind(process.stdout))(t);",
        "console.log(value);",
        "console.warn('x');",
    ):
        expect("the plant %r was not reported" % plant, {**seam, "cmd.ts": plant + "\n"}, True)
    expect(
        "a comparison with process.exitCode read as an assignment",
        {**seam, "cmd.ts": "if (process.exitCode === 1) return;\n"},
        False,
    )
    expect(
        "a comment line read as a site",
        {**seam, "cmd.ts": " * Never process.stdout.write here.\n// process.exitCode = 1\n"},
        False,
    )
    expect(
        "a test file was scanned",
        {**seam, "commands/__tests__/x.test.ts": "process.stdout.write(x);\n"},
        False,
    )
    expect(
        "growth in an exempt file was not reported",
        {"seam.ts": "process.stdout.write(x);\nprocess.exitCode = 2;\n"},
        True,
    )
    expect("a drained exempt file was not reported", {"seam.ts": "writeStdout(x);\n"}, True)
    expect("a dead ALLOWED entry was not reported", {"a.ts": "writeStdout(x);\n"}, True)
    if not verdict(seam, {"seam.ts": Allowed(1, "BLOCKER: tbd")}):
        print("✗ control: a low-effort BLOCKER reason was accepted", file=sys.stderr)
        failed = True
    return failed


def main(argv: list[str]) -> int:
    rc = controls_first("CLI proxy-safe output", selftest)
    if rc or "--selftest" in argv:
        return rc
    files = tree_files(paths.repo_root())
    scanned = sum(1 for rel in files if not is_test(rel))
    if scanned == 0:
        print(
            "✗ no source file found under %s: the gate is not seeing the tree" % CLI_SRC,
            file=sys.stderr,
        )
        return 1
    found = verdict(files, ALLOWED)
    if found:
        print("✗ %d CLI proxy-safe output finding(s):" % len(found), file=sys.stderr)
        for f in found:
            print("    %s" % f, file=sys.stderr)
        return 1
    pinned = sum(a.sites for a in ALLOWED.values())
    print(
        "✓ %d CLI source files write through request-context; %d pinned process-stream"
        " sites in %d exempt files" % (scanned, pinned, len(ALLOWED))
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

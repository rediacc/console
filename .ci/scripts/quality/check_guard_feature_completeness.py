#!/usr/bin/env python3
"""A hook that CALLS a shared-lib function it never sourced fails at runtime, not at
review time -- and the failure looks like success.

WHY THIS EXISTS. check-hook-integrity.sh proves every guard has a case that expects it
to BLOCK/WARN and a case that expects it to stay SILENT. Neither direction tells you
whether the guard actually evaluated its real logic or crashed before reaching it: a
guard that calls an undefined function dies with `bash: <name>: command not found` on
stderr, and the "expect non-empty output" half of a warn/block assertion cannot tell
that crash apart from a real warning -- both are just non-empty text.

PROVEN, not theorised. This session renamed `hook_scan_target` (the function
warn-stale-index.sh:30 calls from its sourced lib/command-scan.sh) to
`hook_scan_target_RENAMED`, ran warn-stale-index.sh's own real "expect a warning"
test input, and got:
    warn-stale-index.sh: line 30: hook_scan_target: command not found
which is non-empty, so the existing "warn" assertion shape (`[ -n "$out" ]`) would have
PASSED that case even though the guard never ran its real logic. Restored immediately;
see agent/e580532b/STATE.md for the session that found this.

WHAT IT CHECKS. Every guard under .claude/hooks/**/*.sh that sources a `lib/*.sh` file
via the repo's one sourcing idiom (`source "$(dirname "${BASH_SOURCE[0]}")/lib/X.sh"`)
must have every identifier it calls as a bare statement -- `name ...` at the start of a
line or after `&&`/`||`/`;`/`$(` -- resolve to a function DEFINED either in the guard
itself or in a lib it actually sources. An identifier that is not locally resolvable
but IS a function name defined SOMEWHERE ELSE in the .claude/hooks tree is flagged: a
coincidental collision with an ordinary shell word is vanishingly unlikely given this
tree's function names (`hook_scan_target`, `_hook_wrapper_payload`, ...), and a real
typo/rename/dropped-source produces exactly that shape.

WHAT IT DOES NOT DO. It does not execute anything, and it follows sourcing ONE level
(the guard's own file plus whatever it directly sources) -- the same honest scoping
disclosure check_python_gate_deps.py makes for Python imports.
"""

import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
HOOKS_DIR = REPO_ROOT / ".claude" / "hooks"

DEF_RE = re.compile(r"^\s*(?:function\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*\(\)\s*\{", re.MULTILINE)
SOURCE_RE = re.compile(
    r'^\s*(?:source|\.)\s+"\$\(dirname\s+"\$\{BASH_SOURCE\[0\]\}"\)/(lib/[A-Za-z0-9_.\-]+\.sh)"',
    re.MULTILINE,
)
# A bare-statement call: identifier at line-start (optional indent) or after a
# statement separator, NOT immediately followed by `=` (that would be an assignment)
# or `(` (that would be a definition, already excluded by not matching DEF_RE's tail).
CALL_RE = re.compile(
    r"(?:^|[;&|]|\$\()\s*([A-Za-z_][A-Za-z0-9_]*)\b(?!\s*\(\)|\s*=[^=])",
    re.MULTILINE,
)

BASH_KEYWORDS = {
    "if",
    "then",
    "else",
    "elif",
    "fi",
    "for",
    "while",
    "until",
    "do",
    "done",
    "case",
    "esac",
    "function",
    "in",
    "select",
    "time",
    "coproc",
    "local",
    "export",
    "readonly",
    "declare",
    "return",
    "exit",
    "break",
    "continue",
    "echo",
    "printf",
    "read",
    "shift",
    "set",
    "unset",
    "trap",
    "eval",
    "exec",
    "source",
    "cd",
    "pwd",
    "test",
    "true",
    "false",
    "let",
    "typeset",
}


HEREDOC_OPEN_RE = re.compile(r"<<-?\s*(['\"]?)(\w+)\1")


def strip_noise(text: str) -> str:
    """Drop heredoc bodies and full-line comments before scanning for calls.

    PROVEN NECESSARY, not precautionary: this gate's own first real run flagged
    warn-remote-drift.sh over the word "fail" inside the comment `# Bounded fetch of
    just this branch; fail open on timeout or any error.` -- the `;` mid-comment read
    as a statement separator. Heredoc bodies are the same risk (human prose, not
    bash), so both are stripped the same way rather than patched as one-off
    exceptions.
    """
    lines = text.split("\n")
    out = []
    in_heredoc = False
    terminator = ""
    for line in lines:
        if in_heredoc:
            if line.strip() == terminator:
                in_heredoc = False
            continue
        m = HEREDOC_OPEN_RE.search(line)
        if m:
            terminator = m.group(2)
            in_heredoc = True
            out.append(line[: m.start()])
            continue
        if line.strip().startswith("#"):
            continue
        out.append(line)
    return "\n".join(out)


def defined_functions(text: str) -> set[str]:
    return set(DEF_RE.findall(strip_noise(text)))


def sourced_libs(hook_path: pathlib.Path, text: str) -> list[pathlib.Path]:
    out = []
    for rel in SOURCE_RE.findall(text):
        lib = hook_path.parent / rel
        if lib.is_file():
            out.append(lib)
    return out


def called_identifiers(text: str) -> set[str]:
    return {m for m in CALL_RE.findall(text) if m not in BASH_KEYWORDS}


def find_offenders() -> list[str]:
    hook_files = sorted(HOOKS_DIR.rglob("*.sh"))
    hook_files = [
        f for f in hook_files if not f.name.startswith("test-") and "worklist-cases" not in f.parts
    ]

    # Global set: every function name defined ANYWHERE in the hook tree, so a call
    # that resolves nowhere locally but matches something elsewhere is a real signal
    # (typo/rename/dropped source), not just an unrecognised shell word.
    global_defined: set[str] = set()
    file_text: dict[pathlib.Path, str] = {}
    for f in hook_files:
        try:
            t = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        file_text[f] = t
        global_defined |= defined_functions(t)

    offenders = []
    for f, text in file_text.items():
        local_defined = defined_functions(text)
        for lib in sourced_libs(f, text):
            local_defined |= defined_functions(
                file_text.get(lib, lib.read_text(encoding="utf-8", errors="replace"))
            )
        for name in sorted(called_identifiers(strip_noise(text))):
            if name in local_defined:
                continue
            if name in global_defined:
                offenders.append(
                    f"{f.relative_to(REPO_ROOT)}: calls '{name}', a function defined "
                    f"elsewhere in the hook tree but not locally defined or sourced here"
                )
    return offenders


def selftest() -> int:
    failures = 0

    def check(name: str, ok: bool) -> None:
        nonlocal failures
        status = "ok  " if ok else "FAIL"
        print(f"{status} control: {name}")
        if not ok:
            failures += 1

    # A locally-defined function called in the same file: never flagged.
    text_local = "my_func() {\n  echo hi\n}\nmy_func\n"
    check(
        "a locally-defined function call is not flagged",
        "my_func"
        not in {
            n for n in called_identifiers(text_local) if n not in defined_functions(text_local)
        },
    )

    # A call to a name that is a real function defined ONLY elsewhere, with no local
    # definition and no source line: this is the shape of the proven live defect.
    caller_text = 'echo start\nhook_scan_target "$CMD"\n'
    lib_text = "hook_scan_target() {\n  echo scanning\n}\n"
    caller_calls = called_identifiers(caller_text)
    caller_defs = defined_functions(caller_text)
    lib_defs = defined_functions(lib_text)
    check(
        "a call resolving only in an UNSOURCED sibling file is detected",
        "hook_scan_target" in caller_calls
        and "hook_scan_target" not in caller_defs
        and "hook_scan_target" in lib_defs,
    )

    # The same call, but the file DOES source the lib: not flagged, because the
    # union of local + sourced definitions covers it.
    check(
        "the same call IS resolved once the lib is sourced",
        "hook_scan_target" in (caller_defs | lib_defs),
    )

    # An ordinary external command (never defined as a function anywhere) must never
    # be flagged just because it appears as a bare statement.
    check(
        "an ordinary external command (git) is not treated as a missing feature",
        "git" not in defined_functions(lib_text) and "git" not in defined_functions(caller_text),
    )

    # REGRESSION: this gate's own first real run flagged warn-remote-drift.sh over
    # the word "fail" inside a comment ("...branch; fail open on timeout..."). The
    # `;` mid-comment read as a statement separator before strip_noise() existed.
    comment_text = "echo start\n# just a fetch; fail open on timeout or any error.\n"
    check(
        "a word following a semicolon INSIDE A COMMENT is not treated as a call",
        "fail" not in called_identifiers(strip_noise(comment_text)),
    )
    heredoc_text = (
        "cat >&2 <<EOF\nPushing now would fail or waste a CI round; align first.\nEOF\nexit 2\n"
    )
    check(
        "a word inside a HEREDOC body is not treated as a call",
        "fail" not in called_identifiers(strip_noise(heredoc_text))
        and "align" not in called_identifiers(strip_noise(heredoc_text)),
    )

    return failures


def main() -> int:
    if "--selftest" in sys.argv:
        print("guard feature completeness selftest")
        bad = selftest()
        print("selftest: all controls passed" if bad == 0 else f"selftest: {bad} FAILED")
        return 0 if bad == 0 else 1

    if selftest() != 0:
        print(
            "x the rule itself is broken, so no verdict it produces means anything.",
            file=sys.stderr,
        )
        return 1

    offenders = find_offenders()
    if offenders:
        print(f"x {len(offenders)} guard(s) call a feature they never sourced:", file=sys.stderr)
        for o in offenders:
            print(f"    {o}", file=sys.stderr)
        return 1

    scanned = len([f for f in HOOKS_DIR.rglob("*.sh") if not f.name.startswith("test-")])
    print(
        f"✓ {scanned} guard script(s) scanned, every called feature resolves locally or via source"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

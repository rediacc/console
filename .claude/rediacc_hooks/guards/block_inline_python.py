"""Block edits that put Python SOURCE inside a JavaScript/TypeScript file.

THE INCIDENT THIS EXISTS FOR. packages/cli/src/remote/vscode/bootstrap.ts held a 130-line Python program inside a template literal, executed on a remote host over SSH. No linter, formatter or type checker in this repo could see it, and it had grown a code-injection hole: four of the six values interpolated into it
went in unescaped, so a universalUser of `'; import os; os.system('id'); x='`
parsed cleanly and executed, under `sudo -u` on the user-switch path. CI now
catches the class (check:ci-no-inline-python), but CI runs after the edit; this
refuses it at the keystroke, which is what the operator asked for by name: "improve .claude/hooks/ to avoid future incidents".

ONE RULE, TWO ENTRY POINTS, on purpose. The decision lives entirely in .ci/scripts/quality/check_inline_python.py, invoked here with --file. A hook
with its own private regex would drift from the gate, and the direction of
drift is always the same: the hook grows lenient, the gate stays strict, and the difference shows up as a CI failure the author could not reproduce.

THE ESCAPE, and why there is one. Set REDIACC_ALLOW_INLINE_PYTHON=1 in the
shell that launches the session. A guard with no way past it is a guard somebody deletes the first time it is wrong, and deleting it removes the protection permanently rather than for one edit. The CI gate is unaffected by this variable, so an override buys a local edit, never a merge.

PORT NOTE ON FINDING THE DETECTOR. The bash computes
`REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"`, three
levels up from `.claude/hooks/pre-edit/`. That arithmetic is exactly what `hookio.repo_root()` refuses to do: it LOOKS for the directory holding both `.claude` and `.ci` instead of counting, so the answer survives this file moving. Same tree, different failure mode -- a miscount here would silently find no detector and the guard would degrade to its warning branch, which is the one
shape of breakage this guard's own header says must not read as clean.

PORT NOTE ON `2>&1`. `FINDINGS=$("$DETECTOR" --file "$TMP" 2>&1)` merges the two
streams into one, and the detector writes its findings to STDERR, so a port that captured only stdout would emit an empty findings block and still exit 2.
`hookio.run_out` deliberately discards stderr, so it is the wrong tool here;
the private helper below spells the merge as `stderr=STDOUT`, which is the same
file-descriptor duplication the shell performs.

PORT NOTE ON THE `case` WITH NO EMPTY ARM. Unlike block-suppressions.sh, this guard's `case` has no `"")` arm, so a payload naming no file exits 0 and the detector is never forked for it. That asymmetry between two neighbouring
pre-edit guards is real and is preserved; it is also why the corpus's
`edit_json` payloads cost this guard nothing.
"""

import contextlib
import os
import subprocess
import tempfile

from rediacc_hooks import hookio

CHAIN = "pre-edit"
TWIN = "pre-edit/block-inline-python.sh"
ORDER = 8

# The documented escape. Removing it does not make the guard stricter in any useful way -- it makes it the guard "somebody deletes the first time it is wrong", which removes the protection permanently rather than for one edit.
DEFECT = ('if ev.env("REDIACC_ALLOW_INLINE_PYTHON") == "1":', "if False:")

# `case "$FILE" in *.ts | *.tsx | *.js | *.jsx | *.cjs | *.mjs) ;; *) exit 0`.
# Narrower than block-suppressions.sh's list on purpose: .vue, .svelte and .astro are not places this incident can take the shape it took.
CODE_SUFFIXES = ("*.ts", "*.tsx", "*.js", "*.jsx", "*.cjs", "*.mjs")

DETECTOR_REL = ".ci/scripts/quality/check_inline_python.py"

# The two sides of the escape hatch. Both are run over the whole case list, so the override is proved to let a real finding through rather than assumed to.
ENVS = [
    ("default", {}, {}),
    ("override", {"REDIACC_ALLOW_INLINE_PYTHON": "1"}, {}),
]

# The detector's own control case, reused rather than reinvented: two distinct statement-shaped signals at the head of a line inside one quoted region.
_PROGRAM = "const s = `\nimport os\nimport pathlib\n\ndef go():\n    print(os.getcwd())\n`;\n"

EDGE_CASES = [
    (
        "a program in a template literal",
        {"tool_input": {"file_path": "packages/cli/src/a.ts", "new_string": _PROGRAM}},
    ),
    (
        "the same program in a .mjs file",
        {"tool_input": {"file_path": "packages/cli/bundle.mjs", "content": _PROGRAM}},
    ),
    # "Mentions Python" is far too wide, and the detector says so at length.
    # Naming the interpreter is not a finding; shipping a program is.
    (
        "naming the interpreter is not shipping a program",
        {
            "tool_input": {
                "file_path": "packages/cli/src/a.ts",
                "new_string": 'const bin = "python3";',
            }
        },
    ),
    (
        "ordinary TypeScript",
        {"tool_input": {"file_path": "packages/cli/src/a.ts", "new_string": "const x = 1;"}},
    ),
    # A .py file is where the program is SUPPOSED to live, so this guard has nothing to say about it.
    ("the program in a real .py file", {"tool_input": {"file_path": "a.py", "content": _PROGRAM}}),
    # No `""` arm in the `case`, so a payload naming no file leaves early.
    ("no file_path at all", {"tool_input": {"new_string": _PROGRAM}}),
    (
        "an empty fragment in a code file",
        {"tool_input": {"file_path": "packages/cli/src/a.ts", "new_string": ""}},
    ),
    (
        "a MultiEdit edits array is collected too",
        {"tool_input": {"file_path": "packages/cli/src/a.ts", "edits": [{"new_string": _PROGRAM}]}},
    ),
]

MISSING_DETECTOR = (
    "⚠️  inline-Python guard cannot run: %s is missing or not executable. Not blocking, but "
    "this edit was NOT checked -- check:ci-no-inline-python still is."
)

WHY_IT_MATTERS = (
    "Python in a JS/TS string is invisible to every tool here: ruff cannot lint or format "
    "it, tsc cannot see it, and no reviewer reads a 100-line template literal closely. "
    "That is not theoretical -- the last one hid a code-injection hole for as long as the "
    "file existed, because values were interpolated into the program's SOURCE."
)

WHAT_TO_DO = (
    "Put the program in a real .py file next to the module that runs it, and import it as "
    "text (packages/cli/bundle.mjs already carries the esbuild loader; "
    "packages/cli/src/types/py-modules.d.ts declares the module). Pass configuration as "
    "data -- JSON in argv or on stdin -- never by interpolating into the source, so a "
    "value cannot become a statement. packages/cli/src/remote/vscode/setup-script.py is "
    "the worked example."
)

THE_ESCAPE = (
    "If this really is the exception, run the session with REDIACC_ALLOW_INLINE_PYTHON=1. "
    "The CI gate check:ci-no-inline-python ignores that variable, so the override buys a "
    "local edit and never a merge."
)


def _detector_output(detector, path):
    """`$("$DETECTOR" --file "$TMP" 2>&1)` -- merged streams, status kept.

    Returns `(ok, text)`. The text has its trailing newlines stripped, which is the command substitution's doing and not the detector's.
    """
    try:
        proc = subprocess.run(
            [detector, "--file", path],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
    except OSError:
        return False, ""
    text = hookio._command_substitution(proc.stdout.decode("utf-8", "surrogateescape"))
    return proc.returncode == 0, text


def run(ev):
    file_path = ev.field("tool_input", "file_path")
    if not hookio.case_glob(file_path, *CODE_SUFFIXES):
        return hookio.ALLOW

    if ev.env("REDIACC_ALLOW_INLINE_PYTHON") == "1":
        return hookio.ALLOW

    content = ev.texts(
        ("tool_input", "content"),
        ("tool_input", "new_string"),
        ("tool_input", "new_source"),
        ("tool_input", "edits", "[]?", "new_string"),
    )
    if content == "":
        return hookio.ALLOW

    detector = "%s/%s" % (hookio.repo_root(), DETECTOR_REL)

    # A missing detector must not read as "clean". It means the hook cannot judge, and a guard that cannot judge should say so rather than wave the edit through.
    if not os.access(detector, os.X_OK):
        ev.warn(MISSING_DETECTOR % detector)
        return hookio.ALLOW

    # Judge the FRAGMENT, not the file on disk: the point is to refuse the content before it lands. The suffix matters because the detector selects rules by file type, so the temp file keeps the real one's extension.
    #
    # `${FILE##*.}` strips the longest `*.` prefix and yields the whole string
    # when there is no dot at all; the `case` above means there always is one,
    # but the fallback is spelled rather than assumed.
    extension = file_path[file_path.rfind(".") + 1 :] if "." in file_path else file_path
    handle, tmp = tempfile.mkstemp(
        prefix="inline-python-",
        suffix="." + extension,
        dir=os.environ.get("TMPDIR") or "/tmp",
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(hookio._printf_line(content))
        ok, findings = _detector_output(detector, tmp)
        if ok:
            return hookio.ALLOW
        # Rewrite the temp path back to the real one so the message names a file the author recognises.
        findings = findings.replace(tmp, file_path)
    finally:
        # `trap 'rm -f "$TMP"' EXIT` -- and `rm -f` never complains about a file that is already gone, which is what `missing_ok` says here.
        with contextlib.suppress(OSError):
            os.unlink(tmp)

    ev.warn("❌ BLOCKED: this edit puts Python source inside %s." % file_path)
    ev.warn(findings)
    ev.warn("")
    ev.warn(WHY_IT_MATTERS)
    ev.warn("")
    ev.warn(WHAT_TO_DO)
    ev.warn("")
    ev.warn(THE_ESCAPE)
    return hookio.DENY

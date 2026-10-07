"""The message catalogue: every constant renders at its call-site arity (117), and a missing catalogue fails closed (118).

Ported from `.claude/hooks/stop/worklist-cases/08-poll-and-waiting.sh`. Cases 101-116 (the poll shape, waiting-cross-session and the silent poll fast path) were removed with cross-session messaging on 2026-09-24.
"""

from __future__ import annotations

import ast
import contextlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys

from rediacc_hooks.tests import wlfix
from rediacc_hooks.tests.wlfix import wl  # noqa: F401


def run_script(script, argv: list[str], env: dict, stdin: str = "") -> wlfix.Result:
    """One invocation of a COPY of the hook, for the missing-catalogue case.

    `wlfix.Fixture.python` always drives the shipped `worklist.py`; case 118 has to drive a copy that was deliberately separated from its own `wl_*` modules, so the path is a parameter here rather than a knob on the shared fixture.
    """
    proc = subprocess.run(
        [sys.executable, str(script), *argv],
        input=stdin,
        capture_output=True,
        text=True,
        env=dict(env),
        check=False,
    )
    return wlfix.Result(proc.stdout, proc.stderr, proc.returncode)


# The keyed fields `wl_schedred.fields(row, me8)` returns, which every scheduled-red message renders from.
SCHED_ROW = {
    "name": "Console CI",
    "stem": "ci",
    "file": "ci.yml",
    "run": 1,
    "attempt": 1,
    "conclusion": "failure",
    "age": "3 h",
    "jobs": "j",
    "blocks": "b",
    "me": "m",
    "add": "a",
    "url": "u",
}
PUSH_ROW = dict(SCHED_ROW, stem="ci-push", sha="e6fc817f", root="Validate Promotion", cause="c")

# .claude/hooks/stop -> .claude/hooks -> .claude -> the repository.
REPO_ROOT = wlfix.STOP_DIR.parents[2]

# ---- DERIVED ARITY. The catalogue strings are the oracle; nothing here is a hand copy of them. ----
#
# This file used to carry a hand table of every constant's call-site arity (267 entries by 2026-10-06). It asserted a shape the call sites were never checked against. Now the shape is DERIVED from each string's own `%` placeholders and rendered, and the call sites are AST-scanned against that derivation, which is the claim the table only made.

# A printf-style placeholder: an optional `(key)`, flags, width, precision, length, conversion.
PLACEHOLDER = re.compile(
    r"%(?:\((?P<key>[^)]*)\))?[#0\- +]*(?P<width>\*|\d+)?(?:\.(?P<prec>\*|\d+))?[hlL]?(?P<conv>.)",
    re.DOTALL,
)

# The sample each conversion letter takes. A placeholder whose letter is not here fails, so a new conversion is a decision rather than a silent `str()`.
CONVERSION_SAMPLES = {
    "s": "x",
    "r": "x",
    "a": "x",
    "d": 1,
    "i": 1,
    "u": 1,
    "x": 1,
    "X": 1,
    "o": 1,
    "c": 1,
    "f": 1.0,
    "F": 1.0,
    "e": 1.0,
    "E": 1.0,
    "g": 1.0,
    "G": 1.0,
}

# Overrides kept ONLY where the sample value is the contract. The scheduled-red and main-push messages render from `wl_schedred.fields(row, me8)`, which no call-site literal shows, so these prove each string uses only keys that row provides (plus what its call site adds).
SAMPLES = {
    "V_SCHEDULED_RED": SCHED_ROW,
    "V_SCHEDULED_RED_TICK": dict(SCHED_ROW, item="i"),
    "N_SCHEDULED_RED_PEER": dict(SCHED_ROW, owner="o"),
    "N_SCHEDULED_GREEN": dict(SCHED_ROW, item="i"),
    "CTX_SCHEDULED_RED_SESSION_START": dict(SCHED_ROW, tracked="untracked", stale=""),
    "V_MAIN_PUSH_RED": PUSH_ROW,
    "V_MAIN_PUSH_RED_TICK": dict(PUSH_ROW, item="i"),
    "N_MAIN_PUSH_RED_PEER": dict(PUSH_ROW, owner="o"),
    "N_MAIN_PUSH_GREEN": dict(PUSH_ROW, item="i"),
    "CTX_MAIN_PUSH_RED_SESSION_START": dict(PUSH_ROW, tracked="untracked", stale=""),
}


class Shape:
    """What one catalogue string takes: nothing, N positionals, or a set of keys."""

    def __init__(self, keys=None, count=0):
        self.keys = keys
        self.count = count

    @property
    def verbatim(self):
        return self.keys is None and self.count == 0

    def sample(self, placeholders):
        if self.keys is not None:
            return {key: CONVERSION_SAMPLES[conv] for key, conv in placeholders}
        return tuple(CONVERSION_SAMPLES[conv] for _key, conv in placeholders)

    def describe(self):
        if self.keys is not None:
            return "keys %s" % sorted(self.keys)
        return "%d positional" % self.count


def placeholders(text):
    """[(key | None, conversion)] for every placeholder, `%%` ignored. Raises ValueError on a shape `%` cannot render."""
    out = []
    for m in PLACEHOLDER.finditer(text):
        conv = m.group("conv")
        if conv == "%":
            continue
        if m.group("width") == "*" or m.group("prec") == "*":
            raise ValueError(
                "a `*` width or precision takes an extra argument this derivation does not model: %r"
                % m.group(0)
            )
        if conv not in CONVERSION_SAMPLES:
            raise ValueError("unknown conversion %r in %r" % (conv, m.group(0)))
        out.append((m.group("key"), conv))
    keyed = [k for k, _ in out if k is not None]
    if keyed and len(keyed) != len(out):
        raise ValueError("mixes keyed and positional placeholders, which `%` refuses to render")
    return out


def shape_of(text):
    found = placeholders(text)
    if found and found[0][0] is not None:
        return Shape(keys=frozenset(k for k, _ in found)), found
    return Shape(count=len(found)), found


def catalogue_strings(catalogue):
    return {
        key: value
        for key, value in vars(catalogue).items()
        if not key.startswith("_") and isinstance(value, str)
    }


def render_findings(strings):
    """Every string derives a shape and renders with it; a SAMPLES override renders with its row."""
    failures = []
    for name, text in sorted(strings.items()):
        try:
            shape, found = shape_of(text)
        except ValueError as exc:
            failures.append("SHAPE %s: %s" % (name, exc))
            continue
        if shape.verbatim:
            continue
        args = SAMPLES.get(name, shape.sample(found))
        try:
            text % args
        except (TypeError, ValueError, KeyError, IndexError) as exc:
            # These four are what a `%` render can raise: a missing key, too few or mistyped arguments, and an unsupported format character. Anything outside them is a defect this test should surface as an error rather than fold into the tally.
            failures.append("RENDER %s with %r: %s" % (name, args, exc))
    stale = sorted(set(SAMPLES) - set(strings))
    if stale:
        failures.append("SAMPLES names constant(s) the catalogue no longer has: %s" % stale)
    return failures


def catalogue_aliases(tree):
    """The names a module binds the catalogue to: `import worklist_messages as M`, and worklist.py's `M = _MODS["worklist_messages"]`."""
    aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            aliases.update(a.asname or a.name for a in node.names if a.name == "worklist_messages")
        elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Subscript):
            key = node.value.slice
            if isinstance(key, ast.Constant) and key.value == "worklist_messages":
                aliases.update(t.id for t in node.targets if isinstance(t, ast.Name))
    return aliases


def callsite_findings(rel, source, shapes):
    """(findings, checked) for every `<alias>.NAME % <literal>` in one module.

    A tuple literal must match the positional count; a dict literal with constant keys must match the key set EXACTLY (a missing key raises at render time, and an extra one is a field the caller computes that the message dropped); any other non-tuple literal (a string, an f-string, a number) is one positional. A right operand that is a name or a call is not a literal and is not judged: its arity is decided at run time.
    """
    tree = ast.parse(source, filename=rel)
    aliases = catalogue_aliases(tree)
    findings = []
    checked = 0
    for node in ast.walk(tree):
        if not (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod)):
            continue
        left = node.left
        if not (
            isinstance(left, ast.Attribute)
            and isinstance(left.value, ast.Name)
            and left.value.id in aliases
        ):
            continue
        name = left.attr
        where = "%s:%d %s" % (rel, node.lineno, name)
        if name not in shapes:
            findings.append("MISSING %s: the catalogue has no such string" % where)
            continue
        shape = shapes[name]
        right = node.right
        if isinstance(right, ast.Tuple):
            if any(isinstance(e, ast.Starred) for e in right.elts):
                continue
            got = Shape(count=len(right.elts))
        elif isinstance(right, ast.Dict):
            keys = [k for k in right.keys if isinstance(k, ast.Constant)]
            if len(keys) != len(right.keys):
                continue  # a `**spread` or a computed key: decided at run time
            got = Shape(keys=frozenset(k.value for k in keys))
        elif isinstance(right, (ast.Constant, ast.JoinedStr)):
            got = Shape(count=1)
        else:
            continue
        checked += 1
        if shape.verbatim:
            findings.append(
                "VERBATIM %s: the string has no placeholder and is rendered with %s"
                % (where, got.describe())
            )
        elif (shape.keys, shape.count) != (got.keys, got.count):
            findings.append(
                "ARITY %s: the string takes %s, the call site passes %s"
                % (where, shape.describe(), got.describe())
            )
    return findings, checked


def hook_modules(root):
    """Every hook module that can render the catalogue: `.claude/hooks/**/*.py`, tests excluded."""
    return sorted(
        p for p in (root / ".claude" / "hooks").rglob("*.py") if "__pycache__" not in p.parts
    )


def scan_callsites(root, shapes):
    findings = []
    checked = 0
    for path in hook_modules(root):
        rel = str(path.relative_to(root))
        got, n = callsite_findings(rel, path.read_text(encoding="utf-8"), shapes)
        findings.extend(got)
        checked += n
    return findings, checked


def load_catalogue():
    """`worklist_messages.py` loaded by path, exactly as the bash probe loaded it."""
    path = wlfix.STOP_DIR / "worklist_messages.py"
    spec = importlib.util.spec_from_file_location("wm", path)
    assert spec is not None, path
    assert spec.loader is not None, path
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_117_the_message_catalogue_renders_at_every_call_site_arity():
    """Every string renders at its DERIVED arity, and every literal call site in the hooks passes exactly that."""
    catalogue = load_catalogue()
    strings = catalogue_strings(catalogue)
    assert len(strings) >= 100, (
        "only %d catalogue strings; the loader is not seeing the catalogue" % len(strings)
    )
    failures = render_findings(strings)
    shapes = {}
    for name, text in strings.items():
        with contextlib.suppress(ValueError):  # already a SHAPE failure above
            shapes[name] = shape_of(text)[0]
    found, checked = scan_callsites(REPO_ROOT, shapes)
    failures.extend(found)
    # Anti-vacuity: an alias the scan stopped resolving would check nothing and pass.
    assert checked >= 100, (
        "only %d literal call site(s) checked; the AST scan has lost the hooks" % checked
    )
    assert not failures, "catalogue-arity failures=%d: %s" % (len(failures), failures)


def test_117b_a_planted_call_site_with_the_wrong_arity_fails(tmp_path):
    """CONTROL: `M.V_IDLE % ("a", "b")` in a tmp copy of a real hook module, against the real catalogue."""
    strings = catalogue_strings(load_catalogue())
    shapes = {name: shape_of(text)[0] for name, text in strings.items()}
    assert shapes["V_IDLE"].count == 1, "the plant assumes V_IDLE takes one positional"
    real = wlfix.STOP_DIR / "wl_checks.py"
    source = real.read_text(encoding="utf-8")
    clean, checked = callsite_findings("wl_checks.py", source, shapes)
    assert checked > 0, "the clean copy checks no call site, so the plant below would prove nothing"
    planted = tmp_path / "wl_checks.py"
    planted.write_text(source + '\n\nPLANT = M.V_IDLE % ("a", "b")\n', encoding="utf-8")
    got, _ = callsite_findings("wl_checks.py", planted.read_text(encoding="utf-8"), shapes)
    new = [f for f in got if f not in clean]
    assert any(
        f.startswith("ARITY wl_checks.py:") and "V_IDLE" in f and "2 positional" in f for f in new
    ), new
    assert real.read_text(encoding="utf-8") == source, "the real module is never written"


def test_117c_call_site_rules_both_directions():
    """Pure cases: the dict rule is exact in both directions, and what is not a literal is not judged."""
    shapes = {
        "ONE": shape_of("a %s")[0],
        "KEYED": shape_of("%(a)s %(b)d")[0],
        "PLAIN": shape_of("no placeholder, 100%% plain")[0],
    }
    src = (
        "import worklist_messages as Q\n"
        "a = Q.ONE % ('x',)\n"
        "b = Q.ONE % 'x'\n"
        "c = Q.KEYED % {'a': 1, 'b': 2}\n"
        "d = Q.ONE % some_tuple\n"
        "e = Q.ONE % make()\n"
    )
    assert callsite_findings("ok.py", src, shapes) == ([], 3), (
        "CONTROL: correct literals and non-literals pass"
    )
    bad = (
        "import worklist_messages as Q\n"
        "a = Q.ONE % ('x', 'y')\n"
        "b = Q.KEYED % {'a': 1}\n"
        "c = Q.KEYED % {'a': 1, 'b': 2, 'extra': 3}\n"
        "d = Q.PLAIN % 'x'\n"
        "e = Q.GONE % 'x'\n"
    )
    found, _ = callsite_findings("bad.py", bad, shapes)
    assert [f.split(":")[0] + ":" + f.split(":")[1].split()[0] for f in found] == [
        "ARITY bad.py:2",
        "ARITY bad.py:3",
        "ARITY bad.py:4",
        "VERBATIM bad.py:5",
        "MISSING bad.py:6",
    ], found
    other = "import something_else as Q\nx = Q.ONE % ('x', 'y')\n"
    assert callsite_findings("other.py", other, shapes) == ([], 0), (
        "only the catalogue's aliases are scanned"
    )
    mods = 'M = _MODS["worklist_messages"]\nx = M.ONE % ("x", "y")\n'
    assert callsite_findings("wl.py", mods, shapes)[1] == 1, (
        "worklist.py's _MODS binding is an alias too"
    )


def test_117d_a_mixed_keyed_and_positional_string_fails():
    """CONTROL: `%` refuses to render a string mixing `%(key)s` and `%s`, so the derivation must refuse it too."""
    failures = render_findings({"MIXED": "%(who)s waited %s minutes", "FINE": "%(who)s waited"})
    assert failures, "a mixed string must fail"
    assert failures[0].startswith("SHAPE MIXED:"), failures
    assert not any("FINE" in f for f in failures), "CONTROL: the well-formed keyed string passes"
    assert render_findings({"STAR": "%*d"})[0].startswith("SHAPE STAR:"), (
        "a `*` width is refused, not guessed"
    )
    assert render_findings({"ODD": "%q"})[0].startswith("SHAPE ODD:"), (
        "an unknown conversion is refused"
    )


def test_118_a_missing_catalogue_fails_closed_and_spares_the_query_modes(wl):  # noqa: F811
    """The import is guarded so a broken worklist_messages.py cannot become the old crash-reads-as-ALLOW hole: message USE raises into the crash handler (block, naming the catalogue), while --path, which uses no messages, keeps working for the scripts that call it."""
    nocat = wl.base / "nocat"
    (nocat / "proj" / ".git").mkdir(parents=True, exist_ok=True)
    (nocat / "tmp").mkdir(parents=True, exist_ok=True)
    hook = nocat / "worklist.py"
    shutil.copy(str(wlfix.HOOK), str(hook))

    env = dict(wl.env)
    env["TMPDIR"] = str(nocat / "tmp")
    env["CLAUDE_PROJECT_DIR"] = str(nocat / "proj")
    got = run_script(hook, ["--path"], env)
    merged = got.out + got.err
    why = "--path broke without the catalogue: rc=%d %r" % (got.rc, merged[:120])
    assert got.rc == 0, why
    assert "claude-worklist" in merged, why

    slug = re.sub(r"[^A-Za-z0-9._-]", "_", str(nocat / "proj")).lstrip("_")
    worklist = nocat / "tmp" / "claude-worklist" / ("%s.md" % slug)
    worklist.parent.mkdir(parents=True, exist_ok=True)
    with worklist.open("a", encoding="utf-8") as handle:
        handle.write("- [ ] (deadbeef) open thing\n")

    stop_env = dict(env)
    stop_env["WORKLIST_TASKS_DIR"] = str(nocat / "tasks")
    stop_env["GITHUB_ACTIONS"] = ""
    payload = json.dumps(
        {
            "session_id": wl.sid,
            "cwd": str(nocat / "proj"),
            "transcript_path": "/none",
            "last_assistant_message": "done",
        }
    )
    blocked = run_script(hook, [], stop_env, stdin=payload)
    assert blocked.decision == "block", "missing catalogue produced decision=%s: %r" % (
        blocked.decision,
        blocked.out[:160],
    )
    assert "worklist_messages" in blocked.out, (
        "the blocking stop did not name the catalogue: %r" % blocked.out[:160]
    )

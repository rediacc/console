"""Refuse `npm run <name>` when the governing package.json has no script called `<name>`.

THE TRAP. docs/agent-reference/TRAPS.md, "manifest-id-is-not-an-npm-script" (cited by Trap-Id, not line: that file is appended to constantly). Most gates are both a `package.json` script and a `scripts/ci-runner/manifest.ts` id, so the two namespaces look interchangeable, and they are not: a manifest id typed after `npm run` is a red for a gate that never ran. `npm run --silent <missing>` exits 1 with ZERO bytes on both streams,
which is byte-for-byte what a gate failing for cause looks like when its output is suppressed. Measured on 2026-09-09: four such reds in one session, every one of them rc=0 when driven by its real invocation.

WHY BLOCKING IS SAFE. The referent is resolvable BEFORE the call, and the call it refuses exits 1 regardless, so a refusal here costs nothing the command itself would not have cost. What the refusal adds is the resolved file and the nearest real names, which turns a silent red into a one-edit fix.

WHICH package.json GOVERNS, in npm's own order:
    --prefix <dir> / -C <dir>   exactly that directory
    -w <ws> / --workspace <ws>  that workspace, by path or by package name
    an earlier `cd`             shellscan's walk carries it into the run's cwd
    else                        the payload's cwd, walking UP to the nearest
                                package.json, which is what npm does itself

IT FAILS OPEN, and every open door is a case below: a name carrying `$`, a backtick or `{` (computed at run time), a directory carrying any of those, a directory that does not exist, no package.json found, an unparseable one, `--if-present` (npm exits 0 on a missing name), `--workspaces` (every workspace, and a name missing from some of them is normal), and a repeated `-w`. A guard that refused a command it could not judge would be a guard sessions learn to route around.
"""

import difflib
import json
import os
import pathlib

from rediacc_hooks import hookio, shellscan

CHAIN = "pre-bash"
OWN_SUITE = True
ORDER = 54

# The mutation the plan names: the lookup always says "present", so the missing-name case must stop being refused.
DEFECT = ("    return name in scripts, scripts", "    return True, scripts")

DYNAMIC = ("$", "`", "{")
# npm options that take a VALUE, so the word after them is not the script name. Any other option is read as a flag on its own (`--silent`, `-s`, `--foreground-scripts`).
VALUE_FLAGS = frozenset(("--prefix", "-C", "-w", "--workspace", "--loglevel", "--script-shell"))
ALL_WORKSPACES = frozenset(("--workspaces", "-ws", "--ws"))

EDGE_CASES = [
    ("a name no package.json defines", "npm run does-not-exist-example"),
    ("run-script is the same verb", "npm run-script does-not-exist-example"),
    ("a manifest id that is not a root script", "npm run gate-test:trap-registry"),
    ("a flag before the name is skipped", "npm run --silent does-not-exist-example"),
    ("a cd carries the package", "cd packages/cli && npm run check:ci-python-lint"),
    ("--prefix names the package", "npm --prefix packages/cli run check:ci-python-lint"),
    # CONTROLS: every one of these must pass.
    ("a real root script", "npm run check:ci-python-lint"),
    ("a real script in the cd'd package", "cd packages/cli && npm run test"),
    ("a real script under --prefix", "npm --prefix packages/cli run test"),
    ("a real script under -w", "npm -w packages/cli run test"),
    ("a real script under -w by package name", "npm -w @rediacc/cli run test"),
    ("a computed name fails open", 'npm run "$GATE"'),
    ("a brace name fails open", "npm run {a,b}"),
    ("a computed directory fails open", 'cd "$D" && npm run does-not-exist-example'),
    ("a missing directory fails open", "cd /nonexistent/dir && npm run does-not-exist-example"),
    ("--if-present exits 0 on a miss", "npm run --if-present does-not-exist-example"),
    ("--workspaces fails open", "npm run --workspaces does-not-exist-example"),
    ("a bare npm run only lists", "npm run"),
    ("prose is not a run", "echo 'npm run does-not-exist-example'"),
    ("a remote operand is not this tree", "ssh host 'npm run does-not-exist-example'"),
]

MESSAGE = """BLOCKED: `npm run %(name)s` names a script that %(file)s does not define.

npm would exit 1 here%(silent)s, which reads exactly like a gate that ran and
failed (TRAPS.md, manifest-id-is-not-an-npm-script). A manifest id is not
always an npm script: some entries in scripts/ci-runner/manifest.ts carry a
bare path in `run:` and are driven by that path.

Nearest real scripts in that file: %(near)s
To drive a manifest-only gate, read its `run:`:
    grep -n "id: '%(name)s'" -A3 scripts/ci-runner/manifest.ts
"""


def _dynamic(word):
    return any(ch in word for ch in DYNAMIC)


def _parse(argv):
    """(script name or "", prefix, workspace, open) from npm's argv, where `open` means "do not judge"."""
    prefix = ""
    workspaces = []
    verb_seen = False
    name = ""
    i = 0
    while i < len(argv):
        word = argv[i]
        flag, eq, value = word.partition("=")
        if word == "--if-present" or flag in ALL_WORKSPACES:
            return "", "", "", True
        if word.startswith("-") and word != "-":
            if word == "--":
                break
            if not eq and flag in VALUE_FLAGS:
                i += 1
                value = argv[i] if i < len(argv) else ""
            if flag in ("--prefix", "-C"):
                prefix = value
            elif flag in ("-w", "--workspace"):
                workspaces.append(value)
            i += 1
            continue
        if not verb_seen:
            if word not in ("run", "run-script"):
                return "", "", "", True
            verb_seen = True
        elif not name:
            name = word
        i += 1
    if not verb_seen or not name or len(workspaces) > 1:
        return "", "", "", True
    return name, prefix, workspaces[0] if workspaces else "", False


def _base_dir(ev):
    cwd = ev.field("cwd")
    return pathlib.Path(cwd or ev.cwd)


def _join(base, rel):
    if rel is None:
        return base
    if _dynamic(rel) or rel == "-":
        return None
    return base / os.path.expanduser(rel)


def _nearest_package(directory):
    for d in (directory, *directory.parents):
        if (d / "package.json").is_file():
            return d / "package.json"
    return None


def _load(path):
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return doc if isinstance(doc, dict) else None


def _workspace(root_pkg, ws):
    """The workspace directory `-w <ws>` names, by path or by package name, or None."""
    root = root_pkg.parent
    if (root / ws / "package.json").is_file():
        return root / ws
    doc = _load(root_pkg) or {}
    for entry in doc.get("workspaces") or []:
        if not isinstance(entry, str) or "*" in entry:
            continue
        pkg = _load(root / entry / "package.json")
        if pkg and pkg.get("name") == ws:
            return root / entry
    return None


def _governing(ev, run, prefix, ws):
    """The package.json npm would read for this run, or None (fail open)."""
    here = _join(_base_dir(ev), run.cwd)
    if here is None or not here.is_dir():
        return None
    if prefix:
        target = _join(here, prefix)
        if target is None or not (target / "package.json").is_file():
            return None
        return target / "package.json"
    pkg = _nearest_package(here)
    if pkg is None or not ws:
        return pkg
    if _dynamic(ws):
        return None
    wsdir = _workspace(pkg, ws)
    return wsdir / "package.json" if wsdir else None


def lookup(pkg, name):
    """(present, scripts) for `name` in `pkg`, or (True, []) when the file cannot be read: failing open."""
    doc = _load(pkg)
    if doc is None or not isinstance(doc.get("scripts"), dict):
        return True, []
    scripts = sorted(doc["scripts"])
    return name in scripts, scripts


def _near(name, scripts):
    close = difflib.get_close_matches(name, scripts, n=5, cutoff=0.5)
    if not close:
        stem = name.split(":", 1)[0]
        close = [s for s in scripts if s.startswith(stem)][:5]
    if close:
        return ", ".join(close)
    return "none close; it defines %s" % ", ".join(scripts[:8]) + (
        ", ..." if len(scripts) > 8 else ""
    )


def _display(pkg, ev):
    root = pathlib.Path(ev.project_dir).resolve()
    try:
        return str(pkg.resolve().relative_to(root))
    except ValueError:
        return str(pkg)


def run(ev):
    cmd = ev.field("tool_input", "command")
    if "npm" not in cmd:
        return hookio.ALLOW
    for item in shellscan._analyse(cmd).runs:
        if shellscan._base(item.name) != "npm":
            continue
        name, prefix, ws, fail_open = _parse(item.argv)
        if fail_open or _dynamic(name):
            continue
        pkg = _governing(ev, item, prefix, ws)
        if pkg is None:
            continue
        present, scripts = lookup(pkg, name)
        if present:
            continue
        silent = " with nothing on stdout" + (
            " or stderr" if any(a in ("-s", "--silent") for a in item.argv) else ""
        )
        ev.warn(
            MESSAGE
            % {
                "name": name,
                "file": _display(pkg, ev),
                "silent": silent,
                "near": _near(name, scripts),
            }
        )
        return hookio.DENY
    return hookio.ALLOW

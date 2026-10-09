"""check:ci-model-invocable-commands: no tracked slash command or skill disables model invocation, except a file the operator's exception list admits.

THE RULING (operator, 2026-10-09), verbatim: "no command or skill in this repo is user-only. Every slash command and skill must be invocable by the AI. This is enforced twice: a hook refuses the flag at write time, and a CI gate fails on it." This is the CI half; the write-time half is the pair of guards `block_user_only_command` (pre-edit) and `block_user_only_command_shell_write` (pre-bash).

THE AMENDMENT (operator, 2026-10-09), verbatim:

    it seems that we need an exceptionlist. I forgot about handoff command. let's include it into the exception list for CI & hook(s)

So there is ONE exception list, `.ci/config/model-invocation-exceptions.json`, and it holds only operator rulings, never a BLOCKER entry: an exception needs a new operator ruling (its date and verbatim quote in the entry), and the hooks refuse any AI edit to the list, so the operator adds one with `!`. This gate refuses an entry with no ruling, a BLOCKER entry, a duplicate, a listed file that is not tracked, and a listed file whose key is no longer exactly what the list says (a stale entry).

ONE PREDICATE, ONE LOADER. What a command or skill file is, what "disables model invocation" means (every spelling of `disable-model-invocation`; an explicit `false` is refused as well as a truthy value, because a present key is one word from a user-only command), how the list is found and parsed, and the per-file decision are all `.claude/rediacc_hooks/model_invocation.py` (`in_scope`, `findings`, `load_exceptions`, `exceptions_for`, `verdict`), imported here through the documented `.claude` hop. The hooks import the same module, so the two halves cannot disagree, and `.ci/rediacc_ci/tests/gates/test_gate_model_invocation_agreement.py` drives the real guards and this gate over one set of planted fixtures (a listed file and unlisted ones) to prove it.

NOT IN SCOPE: `user-invocable:` in `.claude/skills/*/SKILL.md`. That key decides whether a skill is in the USER's slash menu, not whether the model may invoke it.

WHAT IS SCANNED. Every TRACKED `.md` under a `.claude/commands/` or `.claude/skills/` directory, at any depth, in the console and in each of the four submodules (`private/account` tracks `.claude/commands/update-tax-rates.md`; Claude Code discovers nested `.claude` trees). A submodule that is not checked out is a FAILURE, never a skip: its commands would be unchecked, and an unchecked file is not a passing one. Zero files scanned in the console is a failure too, because a scan that sees nothing has lost its file list and its silence would read like a clean tree.
"""

from __future__ import annotations

import argparse
import dataclasses
import importlib
import json
import pathlib
import subprocess
import sys
import tempfile

from rediacc_ci import paths

# The scanned repositories: (label, path from the root). The console is first and must yield files.
SCOPE = (
    ("console", ""),
    ("private/account", "private/account"),
    ("private/elite", "private/elite"),
    ("private/homebrew-tap", "private/homebrew-tap"),
    ("private/renet", "private/renet"),
)
CONSOLE_ONLY = SCOPE[:1]


def predicate():
    """`rediacc_hooks.model_invocation`, the one predicate and loader, through the documented `.claude` hop (the precedent is `hook_exec_baseline._load_counter`). Anchored on THIS file: the predicate is part of the instrument, not of the tree being judged."""
    paths.on_sys_path(pathlib.Path(__file__).resolve().parents[3] / ".claude")
    # `importlib.import_module`, not an `import` statement: the hop has to run first, and a function-level import statement would need a suppression marker, which this tree bans.
    try:
        model_invocation = importlib.import_module("rediacc_hooks.model_invocation")
    except ImportError as exc:
        raise SystemExit(
            "check:ci-model-invocable-commands judges through .claude/rediacc_hooks/model_invocation.py "
            "and could not import it (%s); without it no file can be judged" % exc
        ) from exc
    return model_invocation


@dataclasses.dataclass
class Report:
    """What one run read and found."""

    scanned: dict[str, int] = dataclasses.field(default_factory=dict)
    refusals: list[tuple[str, str]] = dataclasses.field(default_factory=list)
    honoured: list[str] = dataclasses.field(default_factory=list)
    not_checked: list[str] = dataclasses.field(default_factory=list)

    @property
    def total(self) -> int:
        return sum(self.scanned.values())

    def failed(self) -> bool:
        return bool(self.refusals or self.not_checked or self.scanned.get("console", 0) == 0)


def _tracked(repo: pathlib.Path) -> list[str] | None:
    """`git ls-files` of one repository, or None when it is not a checkout."""
    if not (repo / ".git").exists():
        return None
    proc = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "-z"], capture_output=True, check=False
    )
    if proc.returncode != 0:
        return None
    return [p for p in proc.stdout.decode("utf-8", "surrogateescape").split("\0") if p]


def check_tree(root: pathlib.Path, scope=SCOPE) -> Report:
    """Judge every tracked command and skill file under `root` with the shared `verdict`, then the exception list itself."""
    mi = predicate()
    report = Report()
    exceptions = mi.load_exceptions(root)
    for error in exceptions.errors:
        report.refusals.append((mi.EXCEPTIONS_REL, error))
    tracked: set[str] = set()
    for label, prefix in scope:
        repo = root / prefix if prefix else root
        files = _tracked(repo)
        if files is None:
            report.not_checked.append(label)
            continue
        count = 0
        for rel in files:
            key = "%s/%s" % (prefix, rel) if prefix else rel
            if not mi.in_scope(key):
                continue
            path = root / key
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                report.refusals.append((key, "tracked but unreadable (%s)" % exc))
                continue
            count += 1
            tracked.add(key)
            rel_key, file_list = mi.exceptions_for(path)
            for why in mi.verdict(rel_key, text, file_list):
                report.refusals.append((key, why))
            if rel_key in file_list.entries and not mi.verdict(rel_key, text, file_list):
                entry = file_list.entries[rel_key]
                report.honoured.append(
                    "%s keeps `disable-model-invocation: %s` (operator ruling %s)"
                    % (key, entry.value, entry.date)
                )
        report.scanned[label] = count
    for path in exceptions.entries:
        if path not in tracked:
            report.refusals.append(
                (
                    mi.EXCEPTIONS_REL,
                    "stale entry: %s is not a tracked command or skill file; only the operator removes the entry"
                    % path,
                )
            )
    return report


def render(report: Report) -> tuple[list[str], list[str]]:
    """(stdout lines, stderr lines) for a report."""
    shape = ", ".join("%s %d" % (label, n) for label, n in report.scanned.items())
    out = ["exceptions honoured (operator rulings): %d" % len(report.honoured)]
    out += ["  %s" % line for line in report.honoured]
    err = [
        "NOT CHECKED: %s is not checked out, so its commands and skills went unjudged. "
        "Fix: git submodule update --init %s" % (label, label)
        for label in report.not_checked
    ]
    if report.scanned.get("console", 0) == 0 and "console" not in report.not_checked:
        err.append(
            "the console yielded ZERO command or skill files: the gate is not seeing the tree, and its green would mean nothing"
        )
    for path, why in report.refusals:
        err.append("%s: %s" % (path, why))
    if report.failed():
        err.append(
            "FAIL check:ci-model-invocable-commands: %d refusal(s), %d file(s) scanned (%s). "
            "Remove the key from the file. A user-only command is an operator decision: the operator edits it with !, "
            "and an exception exists only as an operator ruling in .ci/config/model-invocation-exceptions.json, never a BLOCKER entry."
            % (len(report.refusals) + len(report.not_checked), report.total, shape)
        )
    else:
        out.append(
            "OK check:ci-model-invocable-commands: %d command/skill file(s) scanned (%s), none user-only beyond %d operator exception(s)"
            % (report.total, shape, len(report.honoured))
        )
    return out, err


# --------------------------------------------------------------------------- selftest ---------------------------------------------------------------------------

_K = "disable-model-invocation"
_CLEAN = "---\ndescription: a command\n---\n\nBody.\n"
_FLAG = "---\ndescription: a command\n%s: %%s\n---\n\nBody.\n" % _K
_RULING = {"date": "2026-10-09", "quote": "a selftest ruling, quoted verbatim for the control"}


def _entry(path, value="true", ruling=_RULING):
    entry = {"path": path, "value": value}
    if ruling is not None:
        entry["ruling"] = ruling
    return entry


def _plant(root: pathlib.Path, files: dict[str, str], entries) -> None:
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    files = dict(files)
    if entries is not None:
        files[".ci/config/model-invocation-exceptions.json"] = json.dumps({"exceptions": entries})
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)


BASE = {".claude/commands/a.md": _CLEAN, ".claude/skills/s/SKILL.md": _CLEAN}

# (name, files over BASE, list entries, fails?)
SELFTEST = [
    ("a clean tree passes", {}, [], False),
    ("a planted truthy key fails", {".claude/commands/b.md": _FLAG % "true"}, [], True),
    ("an explicit false fails", {".claude/commands/b.md": _FLAG % "false"}, [], True),
    (
        "another spelling fails",
        {".claude/skills/s/SKILL.md": _FLAG.replace(_K, "Disable_Model_Invocation") % "yes"},
        [],
        True,
    ),
    ("a nested command tree fails", {"private/x/.claude/commands/t.md": _FLAG % "on"}, [], True),
    (
        "a body that only mentions the key passes",
        {".claude/commands/b.md": _CLEAN + "Never set `%s: true`.\n" % _K},
        [],
        False,
    ),
    ("a sub-agent definition is out of scope", {".claude/agents/b.md": _FLAG % "true"}, [], False),
    (
        "a listed file keeping its key passes",
        {".claude/commands/h.md": _FLAG % "true"},
        [_entry(".claude/commands/h.md")],
        False,
    ),
    (
        "a listed file with another value fails",
        {".claude/commands/h.md": _FLAG % "false"},
        [_entry(".claude/commands/h.md")],
        True,
    ),
    (
        "a stale entry (key gone) fails",
        {".claude/commands/h.md": _CLEAN},
        [_entry(".claude/commands/h.md")],
        True,
    ),
    ("a stale entry (file gone) fails", {}, [_entry(".claude/commands/gone.md")], True),
    (
        "an entry without a ruling fails",
        {".claude/commands/h.md": _FLAG % "true"},
        [_entry(".claude/commands/h.md", ruling=None)],
        True,
    ),
    (
        "a BLOCKER entry fails",
        {".claude/commands/h.md": _FLAG % "true"},
        [
            _entry(
                ".claude/commands/h.md",
                ruling={"date": "2026-10-09", "quote": "BLOCKER: the tool needs it, honestly"},
            )
        ],
        True,
    ),
    (
        "an unlisted flagged file beside a listed one fails",
        {".claude/commands/h.md": _FLAG % "true", ".claude/commands/b.md": _FLAG % "true"},
        [_entry(".claude/commands/h.md")],
        True,
    ),
    ("a missing exception list fails", {}, None, True),
]


def selftest(quiet: bool = False) -> int:
    fails = 0
    with tempfile.TemporaryDirectory(prefix="mi-gate-") as tmp:
        for i, (name, files, entries, want_fail) in enumerate(SELFTEST):
            root = pathlib.Path(tmp) / str(i)
            _plant(root, {**BASE, **files}, entries)
            report = check_tree(root, CONSOLE_ONLY)
            ok = report.failed() == want_fail
            fails += not ok
            if not quiet or not ok:
                print("%s %s" % ("ok  " if ok else "FAIL", name))
        # ZERO FILES: a tree with no command or skill file at all must fail, or a lost file list reads as clean.
        root = pathlib.Path(tmp) / "empty"
        _plant(root, {"README.md": "x\n"}, [])
        ok = check_tree(root, CONSOLE_ONLY).failed()
        fails += not ok
        if not quiet or not ok:
            print("%s zero command files fails" % ("ok  " if ok else "FAIL"))
        # AN ABSENT SUBMODULE is unchecked, never clean.
        root = pathlib.Path(tmp) / "nosub"
        _plant(root, BASE, [])
        ok = check_tree(root, (("console", ""), ("private/x", "private/x"))).failed()
        fails += not ok
        if not quiet or not ok:
            print("%s an absent submodule fails" % ("ok  " if ok else "FAIL"))
    print("selftest: %d control(s), %d failure(s)" % (len(SELFTEST) + 2, fails))
    return 1 if fails else 0


def main(argv: list[str], root: pathlib.Path | None = None) -> int:
    parser = argparse.ArgumentParser(prog="check_model_invocable_commands.py")
    parser.add_argument("--selftest", action="store_true", help="run the planted controls only")
    parser.add_argument(
        "--root", type=pathlib.Path, help="judge this tree instead of the repository"
    )
    parser.add_argument(
        "--console-only", action="store_true", help="skip the submodules (for a fixture tree)"
    )
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    # CONTROLS FIRST, on every run: a verdict from a predicate whose planted controls did not fire is not a verdict.
    if selftest(quiet=True):
        print(
            "FAIL check:ci-model-invocable-commands: its own controls failed, so no verdict on the tree",
            file=sys.stderr,
        )
        return 1
    tree = (args.root or root or pathlib.Path.cwd()).resolve()
    report = check_tree(tree, CONSOLE_ONLY if args.console_only else SCOPE)
    out, err = render(report)
    for line in out:
        print(line)
    for line in err:
        print(line, file=sys.stderr)
    return 1 if report.failed() else 0

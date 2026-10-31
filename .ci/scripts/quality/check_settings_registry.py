#!/usr/bin/env python3
"""check:ci-settings-registry -- every registered tunable holds one value, in range, at every copy.

WHY THIS EXISTS. One operator ruling (the R2 storage ceiling to 5 TB, 2026-10-30) had to be written into three places by hand, and only an unrelated test noticed a missed copy. `.ci/config/settings.json` now registers each tunable with every copy that must hold its value, and `npm run settings -- set` writes them all at once (agent/plans/PLAN-settings-set-verb.md). A hand edit to ONE copy still bypasses the verb, and this gate is what refuses it (Design 5).

THE RULES, per registry entry:

  * the entry is well formed: a unique id, a unit in bytes/count/ms/usd, numeric min <= max, a why, at least one copy;
  * every registered file exists (copies, reason paths, pytest paths), and every listed gate id is in scripts/ci-runner/gates.lock.json;
  * every copy resolves to a number: a `json_path` (an RFC 6901 pointer) into a JSON file, or a `py_dict`/`py_key` entry of a module-level dict literal in a Python file, read with `ast` (an independent reader from the verb's byte-span scanner, so the two cross-check each other);
  * every copy of one id holds the same number;
  * that number sits inside [min, max];
  * every reason path resolves to a string.

ANTI-VACUITY. A registry with zero entries, an unreadable registry, or one that does not parse is exit 2 (no verdict): a gate that judged nothing has not passed. `--selftest` runs planted controls in both directions (a clean tree green; a planted disagreement, a dangling path, an out-of-range value, a missing file, a non-number copy and a Python copy out of agreement each red; an empty registry exit 2) before the real check, and the success line prints how many ids, copies and files it judged.

THE FIX for a finding is `npm run settings -- set <id> <value> --reason '<why>'`, which writes every copy; never a hand edit to one copy.

Exit 0 when every copy agrees and sits in range, 1 on findings, 2 when a control fails or no verdict is possible.

---- gate ----
step: Settings registry
needs: none
lane: quality-static
why: A tunable registered in .ci/config/settings.json lives in several files; a hand edit to one copy
     leaves them disagreeing silently, and only `npm run settings -- set` writes them all.
---- end gate ----
"""

from __future__ import annotations

import argparse
import ast
import json
import pathlib
import sys
import tempfile
from typing import TypeGuard

import _cipath
from rediacc_ci.controls import plant

REGISTRY_REL = ".ci/config/settings.json"
LOCK_REL = "scripts/ci-runner/gates.lock.json"
UNITS = ("bytes", "count", "ms", "usd")
FIX = "change it with `npm run settings -- set <id> <value> --reason '<why>'`, which writes every copy"


class NoVerdictError(Exception):
    """The gate cannot judge the tree (exit 2)."""


class CopyMissError(Exception):
    """One copy does not resolve; the message names why."""


def is_number(value: object) -> TypeGuard[int | float]:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def pointer_tokens(pointer: str) -> list[str]:
    if pointer == "":
        return []
    if not pointer.startswith("/"):
        raise CopyMissError("%r is not a JSON pointer" % pointer)
    return [t.replace("~1", "/").replace("~0", "~") for t in pointer[1:].split("/")]


def resolve_pointer(doc: object, pointer: str) -> object:
    node = doc
    for tok in pointer_tokens(pointer):
        if isinstance(node, dict) and tok in node:
            node = node[tok]
        elif isinstance(node, list) and tok.isdigit() and int(tok) < len(node):
            node = node[int(tok)]
        else:
            raise CopyMissError("%s does not resolve (no %r)" % (pointer, tok))
    return node


def py_dict_value(text: str, name: str, key: str) -> object:
    """The literal value of `name[key]` where `name = {...}` is a module-level dict literal."""
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        raise CopyMissError("does not parse as Python: %s" % exc) from exc
    for node in tree.body:
        target = None
        value: ast.expr | None = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            value = node.value
        elif isinstance(node, ast.AnnAssign):
            target = node.target
            value = node.value
        if not (isinstance(target, ast.Name) and target.id == name):
            continue
        if not isinstance(value, ast.Dict):
            raise CopyMissError("%s is not a dict literal" % name)
        hits = [
            v
            for k, v in zip(value.keys, value.values, strict=True)
            if isinstance(k, ast.Constant) and k.value == key
        ]
        if len(hits) != 1:
            raise CopyMissError(
                "%s[%r] %s" % (name, key, "is absent" if not hits else "appears more than once")
            )
        try:
            return ast.literal_eval(hits[0])
        except ValueError as exc:
            raise CopyMissError("%s[%r] is not a literal" % (name, key)) from exc
    raise CopyMissError("no module-level %s = {...}" % name)


def copy_label(copy: dict) -> str:
    if "json_path" in copy:
        return "%s#%s" % (copy.get("file"), copy["json_path"])
    return "%s#%s[%r]" % (copy.get("file"), copy.get("py_dict"), copy.get("py_key"))


class Tree:
    """Reads files under one root once each; JSON parsed lazily."""

    def __init__(self, root: pathlib.Path) -> None:
        self.root = root
        self._text: dict[str, str | None] = {}
        self._json: dict[str, object] = {}

    def exists(self, rel: str) -> bool:
        return (self.root / rel).is_file()

    def text(self, rel: str) -> str:
        if rel not in self._text:
            try:
                self._text[rel] = (self.root / rel).read_text(encoding="utf-8")
            except OSError:
                self._text[rel] = None
            except UnicodeDecodeError as exc:
                # An unreadable copy is no verdict (exit 2), not a crash: nothing was compared.
                raise NoVerdictError("%s is not valid UTF-8: %s" % (rel, exc)) from exc
        got = self._text[rel]
        if got is None:
            raise CopyMissError("file missing")
        return got

    def json(self, rel: str) -> object:
        if rel not in self._json:
            try:
                self._json[rel] = json.loads(self.text(rel))
            except ValueError as exc:
                raise CopyMissError("not valid JSON: %s" % exc) from exc
        return self._json[rel]


def read_copy(tree: Tree, copy: dict) -> object:
    rel = copy.get("file")
    if not isinstance(rel, str) or not rel:
        raise CopyMissError("needs a file")
    has_json = isinstance(copy.get("json_path"), str)
    has_py = isinstance(copy.get("py_dict"), str) and isinstance(copy.get("py_key"), str)
    if has_json == has_py:
        raise CopyMissError("needs exactly one of json_path, or py_dict with py_key")
    if has_json:
        return resolve_pointer(tree.json(rel), copy["json_path"])
    return py_dict_value(tree.text(rel), copy["py_dict"], copy["py_key"])


def load_registry(root: pathlib.Path) -> list[dict]:
    path = root / REGISTRY_REL
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise NoVerdictError("%s cannot be read: %s" % (REGISTRY_REL, exc)) from exc
    except ValueError as exc:
        raise NoVerdictError("%s is not valid JSON: %s" % (REGISTRY_REL, exc)) from exc
    entries = doc.get("settings") if isinstance(doc, dict) else None
    if not isinstance(entries, list):
        raise NoVerdictError("%s has no settings array" % REGISTRY_REL)
    if not entries:
        raise NoVerdictError(
            "%s registers zero settings; the gate is judging nothing and its green would mean nothing"
            % REGISTRY_REL
        )
    return entries


def gate_ids(root: pathlib.Path) -> set[str] | None:
    try:
        lock = json.loads((root / LOCK_REL).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return {e["id"] for e in lock if isinstance(e, dict) and isinstance(e.get("id"), str)}


def entry_findings(
    tree: Tree, entry: object, n: int, seen: set[str], gates: set[str] | None
) -> tuple[str, list[str], int]:
    """(id, findings, copies judged) for one registry entry."""
    if not isinstance(entry, dict) or not isinstance(entry.get("id"), str) or not entry["id"]:
        return "settings[%d]" % n, ["settings[%d] needs an id" % n], 0
    sid = entry["id"]
    out: list[str] = []
    if sid in seen:
        out.append("%s: registered twice in %s" % (sid, REGISTRY_REL))
    seen.add(sid)
    if entry.get("unit") not in UNITS:
        out.append("%s: unit %r is not one of %s" % (sid, entry.get("unit"), ", ".join(UNITS)))
    lo, hi = entry.get("min"), entry.get("max")
    bounds: tuple[float, float] | None = None
    if (
        isinstance(lo, (int, float))
        and isinstance(hi, (int, float))
        and not isinstance(lo, bool)
        and not isinstance(hi, bool)
        and lo <= hi
    ):
        bounds = (lo, hi)
    else:
        out.append("%s: needs numeric min <= max (got %r, %r)" % (sid, lo, hi))
    if not isinstance(entry.get("why"), str) or not entry["why"]:
        out.append("%s: needs a why" % sid)
    copies = entry.get("copies")
    if not isinstance(copies, list) or not copies:
        out.append("%s: needs at least one copy" % sid)
        copies = []
    values: list[tuple[str, int | float]] = []
    for i, copy in enumerate(copies):
        if not isinstance(copy, dict):
            out.append("%s copies[%d]: not an object" % (sid, i))
            continue
        label = copy_label(copy)
        try:
            value = read_copy(tree, copy)
        except CopyMissError as exc:
            out.append(
                "%s: copy %s: %s; fix the registry path or restore the value" % (sid, label, exc)
            )
            continue
        if not is_number(value):
            out.append("%s: copy %s holds %r, not a number" % (sid, label, value))
            continue
        values.append((label, value))
    if values and len({v for _, v in values}) > 1:
        out.append(
            "%s: copies disagree: %s; %s"
            % (sid, ", ".join("%s=%r" % (label, v) for label, v in values), FIX)
        )
    if values and bounds is not None and len(values) == len(copies):
        source = values[0][1]
        if not bounds[0] <= source <= bounds[1]:
            out.append(
                "%s: %r is outside the registered range [%r, %r]; bring it back in range with `npm run settings -- set`, or widen min/max in %s if the ruling moved"
                % (sid, source, bounds[0], bounds[1], REGISTRY_REL)
            )
    for i, reason in enumerate(entry.get("reason_paths") or []):
        if (
            not isinstance(reason, dict)
            or not isinstance(reason.get("file"), str)
            or not isinstance(reason.get("json_path"), str)
        ):
            out.append("%s reason_paths[%d]: needs a file and a json_path" % (sid, i))
            continue
        try:
            got = resolve_pointer(tree.json(reason["file"]), reason["json_path"])
        except CopyMissError as exc:
            out.append(
                "%s: reason path %s#%s: %s" % (sid, reason["file"], reason["json_path"], exc)
            )
            continue
        if not isinstance(got, str):
            out.append(
                "%s: reason path %s#%s holds %r, not a string"
                % (sid, reason["file"], reason["json_path"], got)
            )
    tests = entry.get("tests")
    if not isinstance(tests, dict):
        out.append("%s: tests is {gates: [...], pytest: [...]}" % sid)
        tests = {}
    out.extend(
        "%s: pytest path %r does not exist; `set` would run nothing" % (sid, rel)
        for rel in tests.get("pytest") or []
        if not isinstance(rel, str) or not tree.exists(rel.split("::", 1)[0])
    )
    for gid in tests.get("gates") or []:
        if gates is None:
            out.append("%s: gate %r cannot be checked, %s is unreadable" % (sid, gid, LOCK_REL))
        elif gid not in gates:
            out.append("%s: gate %r is not in %s" % (sid, gid, LOCK_REL))
    return sid, out, len(values)


def check(root: pathlib.Path) -> tuple[list[str], str]:
    """(findings, the success shape line). Raises NoVerdictError when nothing can be judged."""
    entries = load_registry(root)
    tree = Tree(root)
    gates = gate_ids(root)
    seen: set[str] = set()
    findings: list[str] = []
    judged = 0
    files: set[str] = set()
    for n, entry in enumerate(entries):
        _, out, count = entry_findings(tree, entry, n, seen, gates)
        findings.extend(out)
        judged += count
        if isinstance(entry, dict):
            files.update(
                c["file"]
                for c in entry.get("copies") or []
                if isinstance(c, dict) and isinstance(c.get("file"), str)
            )
    if judged == 0 and not findings:
        raise NoVerdictError("no copy resolved to a number; the gate is not seeing the tree")
    shape = "%d settings, %d copies across %d files, every copy agrees and sits in range" % (
        len(entries),
        judged,
        len(files),
    )
    return findings, shape


# ---- selftest -------------------------------------------------------------------------------

FIXTURE_JSON = {"limits": {"a": 2000, "b": 2000}, "why": {"a": "a reason"}}
FIXTURE_PY = 'CEILINGS: dict[str, float] = {\n    "a": 2_000,\n    "other": 5,\n}\n'


def fixture_entry(**over: object) -> dict:
    entry: dict = {
        "id": "fx.a",
        "unit": "count",
        "min": 1000,
        "max": 3000,
        "why": "fixture",
        "copies": [
            {"file": "conf.json", "json_path": "/limits/a"},
            {"file": "conf.json", "json_path": "/limits/b"},
            {"file": "mod.py", "py_dict": "CEILINGS", "py_key": "a"},
        ],
        "reason_paths": [{"file": "conf.json", "json_path": "/why/a", "mode": "replace"}],
        "tests": {"gates": [], "pytest": ["test_fx.py"]},
    }
    entry.update(over)
    return entry


def build_fixture(
    root: pathlib.Path, entries: list[dict], conf: dict | None = None, py: str = FIXTURE_PY
) -> None:
    (root / ".ci" / "config").mkdir(parents=True, exist_ok=True)
    (root / REGISTRY_REL).write_text(json.dumps({"settings": entries}))
    (root / "conf.json").write_text(json.dumps(conf if conf is not None else FIXTURE_JSON))
    (root / "mod.py").write_text(py)
    (root / "test_fx.py").write_text("def test_x():\n    pass\n")


def run_case(
    entries: list[dict], conf: dict | None = None, py: str = FIXTURE_PY
) -> tuple[int, str]:
    with tempfile.TemporaryDirectory(prefix="settings-registry-selftest-") as tmp:
        root = pathlib.Path(tmp)
        build_fixture(root, entries, conf, py)
        try:
            findings, _ = check(root)
        except NoVerdictError as exc:
            return 2, str(exc)
        return (1 if findings else 0), "\n".join(findings)


def selftest_cases() -> list[tuple[str, int, int, str]]:
    """(label, wanted rc, got rc, detail)."""
    disagree = json.loads(json.dumps(FIXTURE_JSON))
    disagree["limits"]["b"] = 2500
    non_number = json.loads(json.dumps(FIXTURE_JSON))
    non_number["limits"]["b"] = "2000"
    reason_not_str = json.loads(json.dumps(FIXTURE_JSON))
    reason_not_str["why"]["a"] = 7
    out_of_range = json.loads(json.dumps(FIXTURE_JSON))
    out_of_range["limits"] = {"a": 9000, "b": 9000}
    return [
        ("a clean fixture passes", 0, *run_case([fixture_entry()])),
        ("a JSON copy planted out of agreement is red", 1, *run_case([fixture_entry()], disagree)),
        (
            "a Python copy planted out of agreement is red",
            1,
            *run_case([fixture_entry()], py=plant(FIXTURE_PY, "2_000", "2_500")),
        ),
        (
            "a dangling json_path is red",
            1,
            *run_case([fixture_entry(copies=[{"file": "conf.json", "json_path": "/limits/nope"}])]),
        ),
        (
            "a dangling py_key is red",
            1,
            *run_case(
                [
                    fixture_entry(
                        copies=[{"file": "mod.py", "py_dict": "CEILINGS", "py_key": "nope"}]
                    )
                ]
            ),
        ),
        (
            "a registered file that does not exist is red",
            1,
            *run_case([fixture_entry(copies=[{"file": "gone.json", "json_path": "/limits/a"}])]),
        ),
        (
            "a value outside [min, max] at every copy is red",
            1,
            *run_case([fixture_entry()], out_of_range, plant(FIXTURE_PY, "2_000", "9_000")),
        ),
        ("a copy holding a string is red", 1, *run_case([fixture_entry()], non_number)),
        (
            "a reason path holding a non-string is red",
            1,
            *run_case([fixture_entry()], reason_not_str),
        ),
        (
            "a missing pytest path is red",
            1,
            *run_case([fixture_entry(tests={"gates": [], "pytest": ["nope.py"]})]),
        ),
        ("an unknown unit is red", 1, *run_case([fixture_entry(unit="furlongs")])),
        ("a duplicate id is red", 1, *run_case([fixture_entry(), fixture_entry()])),
        ("an empty registry is no verdict (exit 2), never a pass", 2, *run_case([])),
    ]


def selftest(verbose: bool = False) -> bool:
    ok = True
    for label, want, got, detail in selftest_cases():
        if got != want:
            ok = False
            print(
                "selftest control failed: %s (wanted %d, got %d)\n  %s"
                % (label, want, got, detail),
                file=sys.stderr,
            )
        elif verbose:
            print("  PASS  %s (rc %d)" % (label, got))
    return ok


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--selftest", action="store_true", help="run only the planted controls")
    parser.add_argument(
        "--root",
        type=pathlib.Path,
        default=pathlib.Path(__file__).resolve().parents[3],
        help="tree to judge (default: this checkout)",
    )
    args = parser.parse_args(argv)
    if not selftest(verbose=args.selftest):
        print(
            "check_settings_registry: a selftest control failed; the gate's verdict would mean nothing",
            file=sys.stderr,
        )
        return 2
    if args.selftest:
        print("check_settings_registry: selftest ok")
        return 0
    try:
        findings, shape = check(args.root.resolve())
    except NoVerdictError as exc:
        print("check_settings_registry: NO VERDICT: %s" % exc, file=sys.stderr)
        return 2
    if findings:
        for f in findings:
            print("FAIL %s" % f, file=sys.stderr)
        print(
            "check_settings_registry: %d finding(s) in %s" % (len(findings), REGISTRY_REL),
            file=sys.stderr,
        )
        return 1
    print("check_settings_registry: %s." % shape)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

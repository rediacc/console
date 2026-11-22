"""Read every hook guard's declared `DEFECT` and `MUTANTS`, for check:ci-guard-mutations' hook arm.

`python3 -m rediacc_ci.quality.guard_mutants <guards-dir>` prints one JSON document: per guard that declares a top-level `DEFECT = (old, new)` and/or `MUTANTS = {name: (old, new)}`, every plant with the UTF-8 byte spans of `old` OUTSIDE the declarations, and the sibling `test-<stem>.py` suite when one exists. The gate (scripts/gates/check-guard-mutations.ts) plants each one into a scratch copy and loads it through `guard_mutant_site.py`.

The declarations are Python literals, so Python reads them: an escaped quote, a triple-quoted string or an implicit concatenation is exactly where a hand-rolled TypeScript parse would read a different `old` than the suite does. The declaration contains the text it plants, so a plain `old in src` stays true after the guarded line is deleted; counting outside the declarations is what makes a stale pattern visible (the same cut the suites' own MUTANT_RUNNER makes, test-block_unverified_push.py). A declaration that is not a literal of that shape is reported as an error, never skipped.
"""

import ast
import json
import pathlib
import sys

DECLARATIONS = ("DEFECT", "MUTANTS")


def _pair(value: object) -> tuple[str, str] | None:
    """`value` as an (old, new) pair of strings, else None."""
    if (
        isinstance(value, tuple | list)
        and len(value) == 2
        and all(isinstance(v, str) for v in value)
    ):
        return value[0], value[1]
    return None


def _spans(src: str, old: str, cut: list[tuple[int, int]]) -> list[list[int]]:
    """UTF-8 byte spans `[start, end)` of every `old` in `src` that overlaps no declaration line range in `cut`."""
    data = src.encode("utf-8")
    needle = old.encode("utf-8")
    line_starts = [0]
    line_starts.extend(i + 1 for i, byte in enumerate(data) if byte == 0x0A)
    regions = []
    for first, last in cut:
        start = line_starts[first - 1]
        end = line_starts[last] if last < len(line_starts) else len(data)
        regions.append((start, end))
    spans = []
    at = data.find(needle)
    while at != -1:
        end = at + len(needle)
        if not any(at < r_end and end > r_start for r_start, r_end in regions):
            spans.append([at, end])
        at = data.find(needle, end)
    return spans


def read_declarations(src: str) -> dict:
    """The plants `src` declares: {"plants": [{label, old, new, spans}], "errors": [...]}.

    Pure, so it can be driven on strings. `label` is `DEFECT` or `MUTANTS[<name>]`.
    """
    tree = ast.parse(src)
    cut: list[tuple[int, int]] = []
    found: dict = {}
    plants: list[dict] = []
    errors: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets = [node.target]
        else:
            continue
        for target in targets:
            if isinstance(target, ast.Name) and target.id in DECLARATIONS:
                cut.append((node.lineno, node.end_lineno or node.lineno))
                if target.id in found:
                    errors.append(
                        "%s is declared twice (line %d and line %d); only one declaration is read"
                        % (target.id, found[target.id].lineno, node.lineno)
                    )
                    continue
                found[target.id] = node

    def add(label: str, pair: tuple[str, str] | None) -> None:
        if pair is None:
            errors.append("%s is not an (old, new) pair of strings" % label)
        elif not pair[0]:
            errors.append("%s has an empty `old`, which plants nowhere" % label)
        elif pair[0] == pair[1]:
            errors.append("%s has old == new, which changes nothing" % label)
        else:
            plants.append(
                {"label": label, "old": pair[0], "new": pair[1], "spans": _spans(src, pair[0], cut)}
            )

    if "DEFECT" in found:
        try:
            add("DEFECT", _pair(ast.literal_eval(found["DEFECT"].value)))
        except ValueError as exc:
            errors.append("DEFECT is not a literal: %s" % exc)
    if "MUTANTS" in found:
        try:
            mutants = ast.literal_eval(found["MUTANTS"].value)
        except ValueError as exc:
            errors.append("MUTANTS is not a literal: %s" % exc)
        else:
            if not isinstance(mutants, dict) or not mutants:
                errors.append("MUTANTS is not a non-empty dict")
            else:
                for name, pair in mutants.items():
                    add("MUTANTS[%s]" % name, _pair(pair))
    return {"plants": plants, "errors": errors}


def scan(guards_dir: str) -> list[dict]:
    """One row per guard module under `guards_dir` that declares DEFECT or MUTANTS, sorted by stem."""
    rows = []
    for path in sorted(pathlib.Path(guards_dir).glob("*.py")):
        if path.name.startswith("test-"):
            continue
        src = path.read_text(encoding="utf-8")
        if not any(("\n%s = " % d) in ("\n" + src) for d in DECLARATIONS):
            continue
        try:
            decl = read_declarations(src)
        except SyntaxError as exc:
            decl = {"plants": [], "errors": ["the guard does not parse: %s" % exc]}
        if not decl["plants"] and not decl["errors"]:
            continue
        suite = path.parent / ("test-%s.py" % path.stem)
        rows.append(
            {
                "stem": path.stem,
                "file": path.name,
                "suite": suite.name if suite.is_file() else None,
                "plants": decl["plants"],
                "errors": decl["errors"],
            }
        )
    return rows


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        sys.stderr.write(
            "usage: PYTHONPATH=.ci python3 -m rediacc_ci.quality.guard_mutants <guards-dir>\n"
        )
        return 2
    if not pathlib.Path(argv[0]).is_dir():
        sys.stderr.write("guard_mutants: %s is not a directory\n" % argv[0])
        return 2
    json.dump(scan(argv[0]), sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

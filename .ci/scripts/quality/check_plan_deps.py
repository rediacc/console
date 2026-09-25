#!/usr/bin/env python3
"""check:ci-plan-deps -- every live plan says what must finish before it starts.

THE ORDER (operator, 2026-09-24): "we should not start implementing a plan before the required plan completes. It should be a mandatory field and should have at least explicit 'no-dep' if there is really no dependency." The design is agent/plans/PLAN-plan-dependencies.md; this file is its T2.

THE GRAMMAR IS NOT HERE. It lives in `.claude/hooks/stop/wl_plandeps.py`, imported through `paths.hooks_stop_dir` the way check_plan_boxes.py imports the Stop hook's box parser, because the pre-edit guard and the worklist verbs read the same line and a second parser would be a second grammar.

WHICH PLANS MUST CARRY THE FIELD: every non-stub `agent/plans/PLAN-*.md` whose Status is not in `wl_planfile.FINISHED_STATES`. Stubs, finished records (`compacted`) and everything in `_done/` and `_removed/` are exempt (plan section 1).

EIGHT FINDINGS, EACH WITH A PLANTED CONTROL IN `--selftest`:

    D1  a required plan has no `Depends-On:` line
    D2  malformed: a path token, a non-PLAN name, an empty token, `no-dep` without
        a 12+ char reason or with a placeholder one, `no-dep` mixed into a list,
        a duplicate, a second line, a line past the 10-line window, emphasis
    D3  a token resolving to no plan, stub or tombstone
    D4  a withdrawn target (`_removed/`, `Status: removed`, a non-`_done` tombstone)
    D5  a plan that depends on itself
    D6  a cycle among the headers, reported as a path `A -> B -> A`
    D7  an ambiguous basename (two real files share it)
    D8  the vacuity floor: fewer than MIN_REQUIRED required plans parsed, or a
        required plan that produced neither a verdict nor a finding. ZERO parsed
        is CANNOT RUN (exit 77), never green.

D9 (a task edge `PLAN-y.md#<id>` whose box no longer exists) is PLAN-plan-dependencies T12 and is not asserted here yet; a task edge is resolved at plan level.

THE VERBS.

    --check                   (the default) controls first, then the verdict
    --selftest                the planted controls alone
    --draft [<path>]          a proposed value per required plan, with every plan it
                              cites, that plan's Status and completeness, up to two
                              citing lines, and a MUTUAL flag. Never writes.
    --set <path> "<value>"    validate the value (grammar, resolution, self, cycle)
                              and show the one-line change; `--write` applies it.
                              The only door for a record, since the ORDER-11 guard
                              refuses any Edit to a record's header.
    --root <dir>              judge another tree (the plant test's door)

Exit codes: 0 green, 1 findings or a refused `--set`, 2 a control failed or bad usage, 77 cannot run.

---- gate ----
step: Plan dependencies
needs: none
selftest: true
lane: quality-branch
why: a plan must not start before the plans it needs are finished, and a plan
     that never says what it needs cannot be ordered at all. The field is
     mandatory (a list of plans, or `no-dep -- <reason>`), and this gate is the
     merge-time backstop behind the pre-edit guard block_plan_without_depends.
---- end gate ----
"""

from __future__ import annotations

import dataclasses
import pathlib
import sys

import _cipath  # noqa: F401
from rediacc_ci import controls, paths

paths.on_sys_path(paths.hooks_stop_dir())

try:
    import wl_plandeps as D
except ImportError as _exc:  # pragma: no cover -- a tree without .claude/hooks/stop
    print(
        "VACUOUS INPUT: cannot import the plan-header grammar wl_plandeps from %s (%s). "
        "The grammar lives only there, so without it there is nothing to judge."
        % (paths.hooks_stop_dir(), _exc),
        file=sys.stderr,
    )
    sys.exit(77)

#: The floor under how many required plans a run must parse. Measured 2026-09-25: 41. The floor guards against a glob or a Status reader that stopped seeing the corpus, not against ordinary closing of plans.
MIN_REQUIRED = 10
CONTROL_FLOOR = 34


class CannotRunError(RuntimeError):
    """No verdict is possible: exit 77, which is not a pass."""


@dataclasses.dataclass(frozen=True)
class Finding:
    code: str
    rel: str
    message: str


def evaluate(graph: D.Graph) -> tuple[list[Finding], dict[str, int]]:
    """(findings, stats) over every required plan. Raises CannotRunError on zero."""
    required = graph.required()
    if not required:
        raise CannotRunError(
            "zero required plans parsed under %s; a tree with no live plan is not a clean one"
            % D.PLANS_DIR
        )
    findings: list[Finding] = []
    verdicts = 0
    edges = 0
    for rel in required:
        found = graph.check(rel)
        verdicts += 1
        dep = graph.plans[rel].header.depends
        edges += len(dep.edges) if dep else 0
        findings.extend(Finding(code, rel, msg) for code, msg in found)
    if len(required) < MIN_REQUIRED:
        findings.append(
            Finding(
                "D8",
                D.PLANS_DIR,
                "only %d required plan(s) parsed, under the floor of %d; the corpus stopped "
                "loading, or the Status reader stopped matching" % (len(required), MIN_REQUIRED),
            )
        )
    if verdicts != len(required):
        findings.append(
            Finding(
                "D8",
                D.PLANS_DIR,
                "%d of %d required plans produced no verdict"
                % (len(required) - verdicts, len(required)),
            )
        )
    stats = {
        "plans": len(graph.plans),
        "required": len(required),
        "edges": edges,
        "verdicts": verdicts,
    }
    return findings, stats


# --------------------------------------------------------------------------- Controls.

_STUB = "# stub\n\nStatus: moved\nMoved-To: agent/plans/_done/PLAN-fin.md\n"
_INDEX = (
    "## Expired plans\n\n| Plan | Title | First seen | Expired | Full-Text-Blob |\n|---|---|---|---|---|\n"
    "| `agent/plans/_done/PLAN-gone.md` | t | 2026-01-01 | 2026-03-01 | `%s` |\n"
    "| `agent/plans/PLAN-expired-backlog.md` | t | 2026-01-01 | 2026-03-01 | `%s` |\n"
    % ("a" * 40, "b" * 40)
)


def _plan(status: str = "in-progress", dep: str | None = None) -> str:
    text = "# PLAN: sample\n\nStatus: %s\nOwner: cafe0000\n" % status
    if dep is not None:
        text += "Depends-On: %s\n" % dep
    return text + "\n## Tasks\n\n- [ ] T1 a box\n"


def _clean() -> dict[str, str]:
    """A tree that must be green: 10 required plans (the floor) with a chain, a no-dep, a finished target, a stub-shadowed target and a tombstone target, plus exempt files that carry no field."""
    texts = {
        "agent/plans/PLAN-p%02d.md" % i: _plan(
            dep="no-dep -- sample plan number %02d stands alone" % i
        )
        for i in range(6)
    }
    texts.update(
        {
            "agent/plans/PLAN-x.md": _plan(dep="PLAN-y.md"),
            "agent/plans/PLAN-y.md": _plan(dep="PLAN-z.md, PLAN-fin.md"),
            "agent/plans/PLAN-z.md": _plan(
                status="draft", dep="PLAN-gone.md -- expired once it landed"
            ),
            "agent/plans/PLAN-t.md": _plan(dep="PLAN-y.md#T1"),
            "agent/plans/PLAN-rec.md": _plan(status="compacted"),
            "agent/plans/PLAN-fin.md": _STUB,
            "agent/plans/_done/PLAN-fin.md": _plan(status="done"),
            "agent/plans/_done/PLAN-old.md": _plan(status="done"),
            "agent/plans/_removed/PLAN-rm.md": _plan(status="removed"),
        }
    )
    return texts


def _codes(texts: dict[str, str], index: str = _INDEX) -> set[str]:
    findings, _stats = evaluate(D.Graph.from_texts(texts, index))
    return {f.code for f in findings}


def _with(**changes: str) -> dict[str, str]:
    texts = _clean()
    for name, text in changes.items():
        texts["agent/plans/PLAN-%s.md" % name] = text
    return texts


def selftest() -> int:
    """Every finding planted into the clean fixture, and the clean fixture itself green. A detector is only proven by its twin: one that always fires passes every plant."""
    tally = controls.Controls("plan deps", floor=CONTROL_FLOOR)
    tally.check("clean fixture is green", _codes(_clean()), set())
    tally.check(
        "clean fixture parses exactly the floor",
        evaluate(D.Graph.from_texts(_clean(), _INDEX))[1]["required"],
        MIN_REQUIRED,
    )

    # D1: remove the line. Its twin is the same plan exempt by Status.
    tally.check("D1 planted: a live plan without the field", _codes(_with(p00=_plan())), {"D1"})
    tally.check(
        "D1 twin: a compacted record needs none",
        _codes(_with(rec=_plan(status="compacted"))),
        set(),
    )
    tally.check(
        "D1 twin: a _done plan needs none",
        _codes(dict(_clean(), **{"agent/plans/_done/PLAN-old.md": _plan(status="draft")})),
        set(),
    )
    tally.check(
        "D1 planted: a plan with no Status is required",
        _codes(_with(p00="# appendix\n\ntext\n")),
        {"D1"},
    )

    # D2: every malformed sub-shape of the grammar, each against the clean value.
    for label, value in (
        ("a path token", "agent/plans/PLAN-y.md"),
        ("a non-PLAN name", "README.md"),
        ("an empty token", "PLAN-y.md,"),
        ("no-dep without a reason", "no-dep"),
        ("a reason under 12 chars", "no-dep -- too short"),
        ("a placeholder reason", "no-dep -- n/a"),
        ("no-dep mixed into a list", "PLAN-y.md, no-dep -- a real reason here"),
        ("a duplicate token", "PLAN-y.md, PLAN-y.md"),
    ):
        tally.check("D2 planted: %s" % label, _codes(_with(x=_plan(dep=value))), {"D2"})
    two = controls.plant(_plan(dep="PLAN-y.md"), "Owner:", "Depends-On: PLAN-z.md\nOwner:")
    tally.check("D2 planted: a second line", _codes(_with(x=two)), {"D2"})
    late = (
        "# PLAN: x\n\nStatus: draft\n"
        + "".join("Note-%d: x\n" % i for i in range(7))
        + "Depends-On: PLAN-y.md\n\n## Tasks\n"
    )
    tally.check("D2 planted: the field at line 11", _codes(_with(x=late)), {"D2"})
    tally.check(
        "D2 twin: the same field at line 10",
        _codes(_with(x=controls.plant(late, "Note-6: x\n", ""))),
        set(),
    )
    tally.check(
        "D2 planted: an emphasised key",
        _codes(_with(x=controls.plant(_plan(), "Owner:", "**Depends-On:** PLAN-y.md\nOwner:"))),
        {"D2"},
    )

    # D3-D5, D7: resolution.
    tally.check(
        "D3 planted: a dangling token", _codes(_with(x=_plan(dep="PLAN-nowhere.md"))), {"D3"}
    )
    tally.check(
        "D3 twin: a _done tombstone resolves", _codes(_with(x=_plan(dep="PLAN-gone.md"))), set()
    )
    tally.check(
        "D3 twin: a stub-shadowed _done plan resolves",
        _codes(_with(x=_plan(dep="PLAN-fin.md"))),
        set(),
    )
    tally.check("D3 planted: the tombstone section removed", _codes(_clean(), index=""), {"D3"})
    tally.check("D4 planted: a _removed target", _codes(_with(x=_plan(dep="PLAN-rm.md"))), {"D4"})
    tally.check(
        "D4 planted: a backlog tombstone",
        _codes(_with(x=_plan(dep="PLAN-expired-backlog.md"))),
        {"D4"},
    )
    tally.check(
        "D4 planted: Status removed in agent/plans",
        _codes(_with(w=_plan(status="removed"), x=_plan(dep="PLAN-w.md"))),
        {"D4"},
    )
    tally.check("D5 planted: a self edge", _codes(_with(x=_plan(dep="PLAN-x.md"))), {"D5"})
    dup = dict(_clean(), **{"agent/plans/_done/PLAN-z.md": _plan(status="done")})
    tally.check("D7 planted: two real files share the name", _codes(dup), {"D7"})

    # D6: cycles, with the path in the message; a diamond is not one.
    tally.check("D6 planted: a 2-cycle", _codes(_with(z=_plan(dep="PLAN-y.md"))), {"D6"})
    tally.check("D6 planted: a 3-cycle", _codes(_with(z=_plan(dep="PLAN-x.md"))), {"D6"})
    msgs = [
        f.message for f in evaluate(D.Graph.from_texts(_with(z=_plan(dep="PLAN-x.md")), _INDEX))[0]
    ]
    tally.check(
        "D6 names the path",
        any("PLAN-x.md -> PLAN-y.md -> PLAN-z.md -> PLAN-x.md" in m for m in msgs),
        True,
    )
    tally.check("D6 twin: a diamond", _codes(_with(t=_plan(dep="PLAN-y.md, PLAN-z.md"))), set())

    # D8: the floor, and zero as CANNOT RUN.
    short = {k: v for k, v in _clean().items() if k != "agent/plans/PLAN-p00.md"}
    tally.check("D8 planted: one under the floor", _codes(short), {"D8"})
    only_exempt = {
        k: v for k, v in _clean().items() if not D.Graph.from_texts(_clean()).is_required(k)
    }
    tally.raises(
        "D8 planted: zero required plans cannot run",
        CannotRunError,
        evaluate,
        D.Graph.from_texts(only_exempt, _INDEX),
    )

    # --set validation, which is the same verdict run on the would-be text.
    tally.check(
        "--set refuses a dangling value",
        bool(
            _set_problems(
                D.Graph.from_texts(_clean(), _INDEX), "agent/plans/PLAN-p00.md", "PLAN-nowhere.md"
            )
        ),
        True,
    )
    tally.check(
        "--set accepts a valid value",
        _set_problems(D.Graph.from_texts(_clean(), _INDEX), "agent/plans/PLAN-p00.md", "PLAN-x.md"),
        [],
    )
    tally.check(
        "--set refuses a value that closes a cycle",
        {
            c
            for c, _ in _set_problems(
                D.Graph.from_texts(_clean(), _INDEX), "agent/plans/PLAN-z.md", "PLAN-x.md"
            )
        },
        {"D6"},
    )
    return 0 if tally.report() else 1


# --------------------------------------------------------------------------- Verbs.


def _set_problems(graph: D.Graph, rel: str, value: str) -> list[tuple[str, str]]:
    """The D1-D7 verdict on `rel` with its field set to `value`."""
    text = graph.texts.get(rel, "")
    new_text = D.set_header(text, value)
    texts = dict(graph.texts)
    texts[rel] = new_text
    return D.Graph(texts, graph.index_text, graph.root).check(rel)


def check(root: pathlib.Path) -> int:
    graph = D.Graph.load(root)
    findings, stats = evaluate(graph)
    if findings:
        by_rel: dict[str, list[Finding]] = {}
        for f in findings:
            by_rel.setdefault(f.rel, []).append(f)
        for rel in sorted(by_rel):
            print("✗ %s" % rel, file=sys.stderr)
            for f in by_rel[rel]:
                print("    %s  %s" % (f.code, f.message), file=sys.stderr)
        codes: dict[str, int] = {}
        for f in findings:
            codes[f.code] = codes.get(f.code, 0) + 1
        print(
            "✗ plan deps: %d finding(s) across %d plan(s) (%s), %d required plan(s) of %d parsed."
            % (
                len(findings),
                len(by_rel),
                ", ".join("%s=%d" % kv for kv in sorted(codes.items())),
                stats["required"],
                stats["plans"],
            ),
            file=sys.stderr,
        )
        print(
            "  Fix: `check_plan_deps.py --draft <path>` proposes a value; "
            '`check_plan_deps.py --set <path> "<value>" --write` applies it.',
            file=sys.stderr,
        )
        return 1
    print(
        "✓ plan deps: %d required plan(s) carry a valid Depends-On (%d edge(s)), no cycle, of %d plan(s) parsed."
        % (stats["required"], stats["edges"], stats["plans"])
    )
    print(
        "  Blind spot: whether an edge is the RIGHT one (citation is not dependency), and task-edge "
        "boxes (D9, PLAN-plan-dependencies T12)."
    )
    return 0


def _rel(root: pathlib.Path, arg: str) -> str:
    path = pathlib.Path(arg)
    if path.is_absolute():
        try:
            return path.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            return arg
    return path.as_posix()


def draft(root: pathlib.Path, target: str | None) -> int:
    graph = D.Graph.load(root)
    rels = [_rel(root, target)] if target else graph.required()
    for rel in rels:
        if rel not in graph.plans:
            print("✗ %s is not a plan under %s" % (rel, D.PLANS_DIR), file=sys.stderr)
            return 2
    for rel in rels:
        info = graph.plans[rel]
        field = info.header.get(D.FIELD)
        own = info.base
        live: list[str] = []
        done: list[str] = []
        rows = []
        for name, lines in graph.citations(rel):
            t = graph.resolve(name)
            mutual = t.state == D.LIVE and any(n == own for n, _ in graph.citations(t.rel))
            if t.state == D.LIVE:
                live.append(name)
            elif t.state == D.COMPLETE:
                done.append(name)
            rows.append((name, t, mutual, lines))
        if field is not None and not graph.check(rel):
            proposal = "keep: %s" % field.value
        elif live:
            proposal = (
                "%s   <- CANDIDATE EDGE(S): citation is not dependency; decide each"
                % ", ".join(live)
            )
        elif done:
            proposal = "no-dep -- cites only finished plans: %s" % ", ".join(done)
        else:
            proposal = "no-dep -- cites no other plan"
        print("%s  [Status: %s]" % (rel, info.header.status or "none"))
        print("  proposed: Depends-On: %s" % proposal)
        for name, t, mutual, lines in rows:
            print(
                "    cites %s  [%s%s]%s"
                % (
                    name,
                    t.state,
                    (", Status: %s" % t.status) if t.status else "",
                    "  MUTUAL" if mutual else "",
                )
            )
            for line in lines:
                print("        | %s" % line[:160])
        print()
    return 0


def set_value(root: pathlib.Path, target: str, value: str, write: bool) -> int:
    graph = D.Graph.load(root)
    rel = _rel(root, target)
    path = root / rel
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        print("✗ cannot read %s: %s" % (rel, exc), file=sys.stderr)
        return 2
    graph.texts[rel] = text
    try:
        problems = _set_problems(graph, rel, value)
    except ValueError as exc:
        print("✗ %s: %s" % (rel, exc), file=sys.stderr)
        return 1
    if problems:
        print("✗ refused: %s with `Depends-On: %s` would carry:" % (rel, value), file=sys.stderr)
        for code, msg in problems:
            print("    %s  %s" % (code, msg), file=sys.stderr)
        return 1
    new_text = D.set_header(text, value)
    old = graph.plans[rel].header.get(D.FIELD) if rel in graph.plans else None
    print("%s" % rel)
    print("  - %s" % ("Depends-On: %s" % old.value if old else "(no Depends-On line)"))
    print("  + Depends-On: %s" % value.strip())
    if not write:
        print("  (dry run; add --write to apply)")
        return 0
    path.write_text(new_text, encoding="utf-8")
    print("  ✓ written")
    return 0


def _arg_after(argv: list[str], flag: str) -> str | None:
    if flag not in argv:
        return None
    i = argv.index(flag)
    return argv[i + 1] if i + 1 < len(argv) and not argv[i + 1].startswith("--") else None


def main(argv: list[str]) -> int:
    try:
        if "--selftest" in argv:
            return selftest()
        root_arg = _arg_after(argv, "--root")
        if "--root" in argv and root_arg is None:
            print("✗ --root needs a directory", file=sys.stderr)
            return 2
        root = pathlib.Path(root_arg) if root_arg else paths.repo_root()
        if not (root / D.PLANS_DIR).is_dir():
            raise CannotRunError(
                "%s has no %s directory, so there is no plan to judge" % (root, D.PLANS_DIR)
            )
        if "--draft" in argv:
            return draft(root, _arg_after(argv, "--draft"))
        if "--set" in argv:
            i = argv.index("--set")
            if len(argv) < i + 3:
                print('✗ usage: --set <path> "<value>" [--write]', file=sys.stderr)
                return 2
            return set_value(root, argv[i + 1], argv[i + 2], "--write" in argv)
        print("plan deps: controls first, then the verdict")
        if selftest() != 0:
            print(
                "✗ instrument control failed; every verdict below would be meaningless",
                file=sys.stderr,
            )
            return 2
        return check(root)
    except CannotRunError as exc:
        print("⚠ CANNOT RUN (exit 77, which is not a verdict): %s" % exc, file=sys.stderr)
        return 77


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

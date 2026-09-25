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

THE X FINDINGS (agent/plans/PLAN-plan-priority-concurrency.md section 6b), over the `Priority:`, `Concurrency:` and `Owns:` lines whose grammar lives beside Depends-On's in wl_plandeps and whose meaning (the overlap engine) lives in wl_planconc:

    D10 a required plan has no `Priority:`
    D11 `Priority:` malformed, emphasised, or on two lines
    D12 `Concurrency:` missing or malformed; `exclusive` without a 12+ char reason
    D13 `Owns:` missing or malformed; `none` without a reason
    D14 an Owns glob escapes the repo (absolute, `..`, `!`, backslash) or expands past 32
    D15 a `parallel` plan claims a universal glob (`**`, `*`, `**/*`)
    D16 an X field past line 12, or a spine field (Status, Owner, Full-Text*, Record-Sig)
        pushed past line 10
    D17 an `(operator)` Priority at the merge-base that is gone or demoted to an AI value
        now. A level change that keeps the marker is an INFO row, never red: the
        operator's own hand edit looks identical.
    D8  (extended) at least MIN_REQUIRED required plans carry a parsed triple

UNTIL THE MIGRATION. `wl_plandeps.X_FIELDS_REQUIRED` is False until PLAN-plan-priority-concurrency.md T11 writes the three lines into every required plan and flips it in the same commit. While it is False, D10-D16 are PRINTED as a pending-migration block with their counts and do not fail the gate; D17 fails it either way, because the operator freeze does not wait for a migration.

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
    --base-tree <dir>         read the D17 base from a directory instead of git (the plant door)
    --overlaps                every pair of required plans whose Owns overlap, with a witness
                              and up to 5 real shared files. Advisory: overlap only matters when
                              both plans are live at once.
    --set-x <path> "<Key: value>" ...
                              validate and show a Priority/Concurrency/Owns change; `--write`
                              applies it. Refuses any change to an `(operator)` Priority.
    --migrate-x               one seed row per required plan (section 7). Never writes the tree.
      --diff                  the unified diff the seeds would produce
      --save                  write the seeds, with each file's sha256, to PROPOSAL_REL
      --table                 the one approval table, from PROPOSAL_REL
      --apply <json>          validate a reviewed proposal; with `--write`, write exactly the
                              three lines per file and print numstat-shaped proof. Refuses a
                              file whose sha256 changed since `--save`.

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
import difflib
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys

import _cipath  # noqa: F401
from rediacc_ci import controls, paths

paths.on_sys_path(paths.hooks_stop_dir())

try:
    import wl_planconc as X
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
CONTROL_FLOOR = 104
#: Where `--migrate-x --save` writes the reviewed-before-apply proposal. Under the ignored `.ci/cache/`, so nothing tracked changes.
PROPOSAL_REL = ".ci/cache/plan-x-migration/proposal.json"
#: A seed Owns that materialises to more files than this is proposed `exclusive` (section 7).
EXCLUSIVE_FILES = 40


class CannotRunError(RuntimeError):
    """No verdict is possible: exit 77, which is not a pass."""


@dataclasses.dataclass(frozen=True)
class Finding:
    code: str
    rel: str
    message: str
    missing: bool = False


def evaluate(graph: D.Graph, strict_x: bool | None = None) -> tuple[list[Finding], dict[str, int]]:
    """(findings, stats) over every required plan. Raises CannotRunError on zero.

    `strict_x` defaults to `wl_plandeps.X_FIELDS_REQUIRED`. When it is False the D10-D16 X findings land in `stats["pending"]` (a list, printed by `check`) instead of `findings`; when True they are findings like any other and the D8 floor also counts parsed X triples.
    """
    strict_x = D.X_FIELDS_REQUIRED if strict_x is None else strict_x
    required = graph.required()
    if not required:
        raise CannotRunError(
            "zero required plans parsed under %s; a tree with no live plan is not a clean one"
            % D.PLANS_DIR
        )
    findings: list[Finding] = []
    pending: list[Finding] = []
    verdicts = 0
    edges = 0
    triples = 0
    exclusive = 0
    for rel in required:
        found = graph.check(rel)
        verdicts += 1
        header = graph.plans[rel].header
        dep = header.depends
        edges += len(dep.edges) if dep else 0
        findings.extend(Finding(code, rel, msg) for code, msg in found)
        xf = X.x_findings(header, graph.texts.get(rel, ""))
        if not xf:
            triples += 1
            conc = header.concurrency
            exclusive += bool(conc and conc.exclusive)
        (findings if strict_x else pending).extend(
            Finding(f.code, rel, f.message, f.missing) for f in xf
        )
    if len(required) < MIN_REQUIRED:
        findings.append(
            Finding(
                "D8",
                D.PLANS_DIR,
                "only %d required plan(s) parsed, under the floor of %d; the corpus stopped "
                "loading, or the Status reader stopped matching" % (len(required), MIN_REQUIRED),
            )
        )
    if strict_x and triples < MIN_REQUIRED:
        findings.append(
            Finding(
                "D8",
                D.PLANS_DIR,
                "only %d required plan(s) carry a valid Priority/Concurrency/Owns triple, under the "
                "floor of %d; the X grammar stopped matching" % (triples, MIN_REQUIRED),
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
    stats: dict = {
        "plans": len(graph.plans),
        "required": len(required),
        "edges": edges,
        "verdicts": verdicts,
        "triples": triples,
        "exclusive": exclusive,
        "strict_x": strict_x,
        "pending": pending,
    }
    return findings, stats


# --------------------------------------------------------------------------- D17: the operator freeze, against the merge-base.


def operator_demotions(
    base: dict[str, D.Priority], graph: D.Graph
) -> tuple[list[Finding], list[str]]:
    """(D17 findings, INFO rows). `base` maps a plan basename to its `(operator)` Priority at the merge-base.

    A plan that is no longer required (finished, moved to _done/, a stub) owes nothing. A required plan whose Priority line is gone, malformed, or no longer carries `(operator)` is D17. A kept marker with a different level or reason is INFO: the operator's own hand edit looks exactly like that, so it is shown, never red.
    """
    findings: list[Finding] = []
    infos: list[str] = []
    required = {graph.plans[r].base: r for r in graph.required()}
    for name, was in sorted(base.items()):
        rel = required.get(name)
        if rel is None:
            continue
        now = graph.plans[rel].header.priority
        if now is None:
            findings.append(
                Finding(
                    D.D_OPERATOR_DEMOTED,
                    rel,
                    "the operator-set `Priority: %s` at the merge-base is gone or malformed now; "
                    "the AI never changes it. Restore the line; only the operator edits it" % was,
                )
            )
        elif not now.operator:
            findings.append(
                Finding(
                    D.D_OPERATOR_DEMOTED,
                    rel,
                    "the operator-set `Priority: %s` was demoted to the AI value `%s`. Restore it; "
                    "only the operator edits it" % (was, now),
                )
            )
        elif (now.level, " ".join(now.reason.split())) != (was.level, " ".join(was.reason.split())):
            infos.append("%s: operator Priority `%s` -> `%s` (marker kept)" % (rel, was, now))
    return findings, infos


_BASE_GREP_RE = re.compile(r"^[^:]+:(agent/plans/(PLAN-[^/:]+\.md)):(\d+):Priority: (.*)$")


def base_ref(root: pathlib.Path) -> str | None:
    """The merge-base with the target branch, the ladder check_plan_boxes.base_ref uses. None when there is none."""
    br = os.environ.get("GITHUB_BASE_REF") or ""
    cand = "origin/%s" % br if br else "origin/main"
    for ref in (cand, cand.replace("origin/", ""), "origin/main", "main"):
        r = subprocess.run(
            ["git", "-C", str(root), "merge-base", "HEAD", ref],
            capture_output=True,
            text=True,
            check=False,
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    return None


def base_operator_priorities(root: pathlib.Path, base: str) -> dict[str, D.Priority] | None:
    """{basename: Priority} of every `(operator)` Priority inside the X window of a top-level plan at `base`. One `git grep`, not one `git show` per plan. None when git failed (exit 1 is "no match", an empty map)."""
    r = subprocess.run(
        [
            "git", "-C", str(root), "grep", "-n", "-E",
            r"^Priority: P[0-3] \(operator\)", base, "--", D.PLANS_DIR + "/PLAN-*.md",
        ],
        capture_output=True,
        text=True,
        check=False,
    )  # fmt: skip
    if r.returncode not in (0, 1):
        return None
    out: dict[str, D.Priority] = {}
    for line in r.stdout.splitlines():
        m = _BASE_GREP_RE.match(line)
        if not m or "/" in m.group(1)[len(D.PLANS_DIR) + 1 :] or int(m.group(3)) > D.X_HEADER_LINES:
            continue
        parsed, errors = D.parse_priority(m.group(4))
        if parsed is not None and not errors and parsed.operator:
            out.setdefault(m.group(2), parsed)
    return out


def base_tree_priorities(tree: pathlib.Path) -> dict[str, D.Priority]:
    """The same map read from a directory of plan files (`--base-tree`), for fixtures that have no git."""
    out: dict[str, D.Priority] = {}
    for path in sorted((tree / D.PLANS_DIR).glob("PLAN-*.md")):
        pr = D.parse_header(path.read_text(encoding="utf-8", errors="replace")).priority
        if pr is not None and pr.operator:
            out[path.name] = pr
    return out


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
    """The Depends-On controls' verdict. Lax on the X fields by construction, so these controls mean the same before and after `X_FIELDS_REQUIRED` flips; the X controls below pass `strict` themselves."""
    findings, _stats = evaluate(D.Graph.from_texts(texts, index), strict_x=False)
    return {f.code for f in findings}


_X_OK = {
    D.PRIORITY: "P2 -- a sample plan of middling urgency",
    D.CONCURRENCY: "parallel",
}


def _xclean() -> dict[str, str]:
    """The clean fixture plus one more required plan, every required plan carrying a valid X triple with disjoint Owns. One more than the floor, so a single X defect trips its own code and not D8's X floor as well."""
    texts = _clean()
    texts["agent/plans/PLAN-extra.md"] = _plan(
        dep="no-dep -- the eleventh sample plan stands alone"
    )
    graph = D.Graph.from_texts(texts, _INDEX)
    for n, rel in enumerate(graph.required()):
        texts[rel] = D.set_x(
            texts[rel], dict(_X_OK, Owns="src/area%02d/**, docs/area%02d.md" % (n, n))
        )
    return texts


def _xcodes(texts: dict[str, str], strict: bool = True) -> set[str]:
    findings, _stats = evaluate(D.Graph.from_texts(texts, _INDEX), strict_x=strict)
    return {f.code for f in findings}


def _xwith(name: str, **fields: str) -> dict[str, str]:
    """The X-clean fixture with one plan's X fields set (the value `DROP` removes the line)."""
    texts = _xclean()
    rel = "agent/plans/PLAN-%s.md" % name
    keep = {k: v for k, v in fields.items() if v != "DROP"}
    text = D.set_x(texts[rel], keep) if keep else texts[rel]
    for k, v in fields.items():
        if v == "DROP":
            text = "".join(
                ln for ln in text.splitlines(keepends=True) if not ln.startswith(k + ":")
            )
    texts[rel] = text
    return texts


def _xraw(name: str, old: str, new: str) -> dict[str, str]:
    texts = _xclean()
    rel = "agent/plans/PLAN-%s.md" % name
    texts[rel] = controls.plant(texts[rel], old, new)
    return texts


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
        evaluate(D.Graph.from_texts(_clean(), _INDEX), strict_x=False)[1]["required"],
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
        f.message
        for f in evaluate(
            D.Graph.from_texts(_with(z=_plan(dep="PLAN-x.md")), _INDEX), strict_x=False
        )[0]
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
    _x_controls(tally)
    return 0 if tally.report() else 1


def _x_controls(tally: controls.Controls) -> None:
    """D8 (X floor) and D10-D17, the freeze in the verbs, and the migration seeds: each planted into the X-clean fixture, each with a twin that stays green."""
    tally.check("X clean fixture is green (strict)", _xcodes(_xclean()), set())
    tally.check(
        "X clean fixture counts 11 triples",
        evaluate(D.Graph.from_texts(_xclean(), _INDEX), strict_x=True)[1]["triples"],
        11,
    )
    lax = evaluate(D.Graph.from_texts(_clean(), _INDEX), strict_x=False)
    tally.check(
        "X lax: the fieldless fixture is green before the migration",
        {f.code for f in lax[0]},
        set(),
    )
    tally.check(
        "X lax: its missing fields are PENDING, not dropped",
        sorted({(f.code, f.missing) for f in lax[1]["pending"]}),
        [("D10", True), ("D12", True), ("D13", True)],
    )
    tally.check(
        "X strict: the fieldless fixture is red",
        _xcodes(_clean()) >= {"D10", "D12", "D13", "D8"},
        True,
    )

    tally.check("D10 planted: no Priority", _xcodes(_xwith("p00", Priority="DROP")), {"D10"})
    tally.check(
        "D10 twin: lax does not fail on it",
        _xcodes(_xwith("p00", Priority="DROP"), strict=False),
        set(),
    )
    for label, value in (
        ("P4", "P4"),
        ("a period separator", "P0. This is an operator ruling"),
        ("a lowercase level", "p1"),
        ("an unknown marker", "P1 (ops)"),
    ):
        tally.check("D11 planted: %s" % label, _xcodes(_xwith("p00", Priority=value)), {"D11"})
    tally.check(
        "D11 planted: a second Priority line",
        _xcodes(_xraw("p00", "Concurrency:", "Priority: P1\nConcurrency:")),
        {"D11"},
    )
    tally.check(
        "D11 planted: an emphasised key",
        _xcodes(_xraw("p00", "Priority:", "**Priority:**")),
        {"D11"},
    )
    tally.check(
        "D11 twin: an operator value",
        _xcodes(_xwith("p00", Priority="P1 (operator) -- ruled")),
        set(),
    )
    tally.check("D11 twin: no reason at all", _xcodes(_xwith("p00", Priority="P3")), set())
    for label, value in (
        ("an unknown mode", "sometimes"),
        ("exclusive without a reason", "exclusive"),
        ("exclusive with a short reason", "exclusive -- too short"),
        ("a period separator", "parallel. four writers"),
    ):
        tally.check("D12 planted: %s" % label, _xcodes(_xwith("p00", Concurrency=value)), {"D12"})
    tally.check("D12 planted: no Concurrency", _xcodes(_xwith("p00", Concurrency="DROP")), {"D12"})
    tally.check(
        "D12 twin: exclusive with a reason",
        _xcodes(_xwith("p00", Concurrency="exclusive -- regenerates every golden file")),
        set(),
    )
    for label, value in (
        ("none without a reason", "none"),
        ("an empty item", "a/**,, b/**"),
        ("two globs without a comma", "a/** b/**"),
        ("none mixed into a list", "a/**, none -- nothing"),
    ):
        tally.check("D13 planted: %s" % label, _xcodes(_xwith("p00", Owns=value)), {"D13"})
    tally.check("D13 planted: no Owns", _xcodes(_xwith("p00", Owns="DROP")), {"D13"})
    tally.check(
        "D13 twin: none with a reason",
        _xcodes(_xwith("p00", Owns="none -- an operator-action plan")),
        set(),
    )
    tally.check(
        "D13 twin: a noted glob",
        _xcodes(_xwith("p00", Owns="src/x.ts (one mount line only)")),
        set(),
    )
    for label, value in (
        ("an absolute glob", "/etc/x"),
        ("a climbing glob", "src/../x"),
        ("a negation", "!src/x"),
        ("a backslash", "src\\x"),
        ("more than 32 expansions", "{a,b}/{c,d}/{e,f}/{g,h}/{i,j}/{k,l}"),
    ):
        tally.check("D14 planted: %s" % label, _xcodes(_xwith("p00", Owns=value)), {"D14"})
    tally.check(
        "D14 twin: 32 expansions",
        _xcodes(_xwith("p00", Owns="{a,b}/{c,d}/{e,f}/{g,h}/{i,j}")),
        set(),
    )
    for value in ("**", "*", "**/*"):
        tally.check(
            "D15 planted: parallel claims %s" % value, _xcodes(_xwith("p00", Owns=value)), {"D15"}
        )
    tally.check(
        "D15 twin: exclusive may claim **",
        _xcodes(_xwith("p00", Owns="**", Concurrency="exclusive -- regenerates every golden file")),
        set(),
    )
    pad = "".join("Note-%d: x\n" % i for i in range(9))
    tally.check(
        "D16 planted: an X field at line 13",
        _xcodes(_xraw("p00", "Priority:", pad + "Priority:")),
        {"D16"},
    )

    def owner_at(line: int) -> dict[str, str]:
        # Status 3, Depends-On 4, Priority 5, Concurrency 6, Owns 7 once Owner leaves line 4; notes then fill up to `line`.
        texts = _xraw("p00", "Owner: cafe0000\n", "")
        rel = "agent/plans/PLAN-p00.md"
        filler = "".join("Note-%d: x\n" % i for i in range(line - 8))
        texts[rel] = controls.plant(
            texts[rel], "\n\n## Tasks", "\n%sOwner: cafe0000\n\n## Tasks" % filler
        )
        return texts

    tally.check("D16 planted: Owner pushed to line 11", _xcodes(owner_at(11)), {"D16"})
    tally.check("D16 twin: Owner at line 10", _xcodes(owner_at(10)), set())
    two = _xwith("p00", Priority="DROP")
    two["agent/plans/PLAN-p01.md"] = _xwith("p01", Priority="DROP")["agent/plans/PLAN-p01.md"]
    tally.check("D8 planted: X triples under the floor", _xcodes(two), {"D10", "D8"})

    # D17, pure: a base of operator values against the head graph.
    was, _ = D.parse_priority("P1 (operator) -- the operator ranked it")

    def d17(**fields: str) -> tuple[set[str], int]:
        graph = D.Graph.from_texts(_xwith("p00", **fields), _INDEX)
        found, infos = operator_demotions({"PLAN-p00.md": was}, graph)
        return {f.code for f in found}, len(infos)

    tally.check("D17 planted: the operator line removed", d17(Priority="DROP"), ({"D17"}, 0))
    tally.check(
        "D17 planted: demoted to an AI value",
        d17(Priority="P1 -- the operator ranked it"),
        ({"D17"}, 0),
    )
    tally.check("D17 planted: malformed", d17(Priority="P1 (operator)."), ({"D17"}, 0))
    tally.check(
        "D17 twin: unchanged", d17(Priority="P1 (operator) -- the operator ranked it"), (set(), 0)
    )
    tally.check(
        "D17 twin: whitespace only",
        d17(Priority="P1 (operator) -- the operator   ranked it"),
        (set(), 0),
    )
    tally.check(
        "D17 INFO: level changed, marker kept",
        d17(Priority="P0 (operator) -- the operator ranked it"),
        (set(), 1),
    )
    tally.check(
        "D17 twin: the plan finished",
        {
            f.code
            for f in operator_demotions(
                {"PLAN-p00.md": was},
                D.Graph.from_texts(
                    _xwith("p00", Priority="DROP")
                    | {"agent/plans/PLAN-p00.md": _plan(status="done")},
                    _INDEX,
                ),
            )[0]
        },
        set(),
    )

    # The verbs' freeze: no CLI path changes, drops or introduces `(operator)`.
    op_text = _xwith("p00", Priority="P1 (operator) -- the operator ranked it")[
        "agent/plans/PLAN-p00.md"
    ]
    ai_text = _xclean()["agent/plans/PLAN-p00.md"]
    tally.check(
        "--set-x refuses an operator level change",
        bool(x_problems(op_text, {"Priority": "P0 (operator) -- the operator ranked it"})[1]),
        True,
    )
    tally.check(
        "--set-x refuses dropping the marker",
        bool(x_problems(op_text, {"Priority": "P1 -- the operator ranked it"})[1]),
        True,
    )
    tally.check(
        "--set-x refuses introducing the marker",
        bool(x_problems(ai_text, {"Priority": "P1 (operator)"})[1]),
        True,
    )
    tally.check(
        "--set-x accepts an AI re-rank", x_problems(ai_text, {"Priority": "P1 -- moved up"})[1], []
    )
    tally.check(
        "--set-x accepts an Owns change on an operator plan",
        x_problems(op_text, {"Owns": "src/new/**"})[1],
        [],
    )
    tally.check(
        "--set-x refuses a universal parallel Owns",
        bool(x_problems(ai_text, {"Owns": "**"})[1]),
        True,
    )

    # The migration seeds (section 7).
    def seed(status: str, body: str = "", extra: str = "") -> dict:
        text = "# PLAN: s\n\nStatus: %s\nOwner: cafe0000\n%s\n## Tasks\n\n%s" % (
            status,
            extra,
            body,
        )
        return seed_row(
            pathlib.Path("/nonexistent-plan-x-root"),
            "agent/plans/PLAN-s.md",
            text,
            [],
            "2026-09-25",
        )

    tally.check("seed: executing is P1", seed("executing")[D.PRIORITY].split(" ")[0], "P1")
    tally.check("seed: approved is P2", seed("approved")[D.PRIORITY].split(" ")[0], "P2")
    tally.check("seed: draft is P3", seed("draft")[D.PRIORITY].split(" ")[0], "P3")
    tally.check(
        "seed: a recent operator order moves a draft up one",
        seed("draft", extra="\n**Operator order, 2026-09-24:** do it\n")[D.PRIORITY].split(" ")[0],
        "P2",
    )
    tally.check(
        "seed: an old operator order does not",
        seed("draft", extra="\n**Operator order, 2026-08-01:** do it\n")[D.PRIORITY].split(" ")[0],
        "P3",
    )
    tally.check(
        "seed: a valid Priority is kept",
        seed("draft", extra="Priority: P0 (operator) -- ruled\n")[D.PRIORITY],
        "P0 (operator) -- ruled",
    )
    tally.check(
        "seed: a period-separated Priority is salvaged",
        seed("draft", extra="Priority: P0. an operator ruling\n")[D.PRIORITY],
        "P0 -- an operator ruling",
    )
    tally.check(
        "seed: a period-separated Concurrency is salvaged",
        seed("draft", extra="Concurrency: parallel. four writers\n")[D.CONCURRENCY],
        "parallel -- four writers",
    )
    tally.check(
        "seed: a bulk box is exclusive",
        seed("draft", "- [ ] T1 reflow every plan\n")[D.CONCURRENCY].split(" ")[0],
        "exclusive",
    )
    tally.check(
        "seed: a plain box is parallel",
        seed("draft", "- [ ] T1 edit one file\n")[D.CONCURRENCY],
        "parallel",
    )
    tally.check(
        "seed: no cited path is Owns none",
        seed("draft", "- [ ] T1 talk to the operator\n")[D.OWNS].split(" ")[0],
        "none",
    )
    tally.check(
        "seed: four siblings collapse",
        collapse(["a/b/w.py", "a/b/x.py", "a/b/y.py", "a/b/z.py", "a/c.md"]),
        ["a/b/*.py", "a/c.md"],
    )
    tally.check(
        "seed: three siblings stay listed",
        collapse(["a/x.py", "a/y.py", "a/z.py"]),
        ["a/x.py", "a/y.py", "a/z.py"],
    )


# --------------------------------------------------------------------------- Verbs.


def _set_problems(graph: D.Graph, rel: str, value: str) -> list[tuple[str, str]]:
    """The D1-D7 verdict on `rel` with its field set to `value`."""
    text = graph.texts.get(rel, "")
    new_text = D.set_header(text, value)
    texts = dict(graph.texts)
    texts[rel] = new_text
    return D.Graph(texts, graph.index_text, graph.root).check(rel)


def _d17(root: pathlib.Path, graph: D.Graph, base_tree: pathlib.Path | None):
    """(findings, infos, how) for D17; `how` names the base, or says why D17 did not run."""
    if base_tree is not None:
        base = base_tree_priorities(base_tree)
        how = "base tree %s" % base_tree
    else:
        if not (root / ".git").exists():
            return (
                [],
                [],
                "SKIPPED: %s is not a git checkout (pass --base-tree to judge a fixture)" % root,
            )
        ref = base_ref(root)
        if ref is None:
            return [], [], "SKIPPED: no merge-base with origin/main or main (a shallow clone?)"
        got = base_operator_priorities(root, ref)
        if got is None:
            return [], [], "SKIPPED: `git grep` failed at %s" % ref[:9]
        base, how = got, "merge-base %s" % ref[:9]
    findings, infos = operator_demotions(base, graph)
    return findings, infos, "%s, %d operator-set Priority line(s) there" % (how, len(base))


def check(root: pathlib.Path, base_tree: pathlib.Path | None = None) -> int:
    graph = D.Graph.load(root)
    findings, stats = evaluate(graph)
    d17, infos, how = _d17(root, graph, base_tree)
    findings.extend(d17)
    pending: list[Finding] = stats["pending"]
    if pending:
        per: dict[str, int] = {}
        for f in pending:
            per[f.code] = per.get(f.code, 0) + 1
        present = [f for f in pending if not f.missing]
        print(
            "⚠ X fields pending migration (PLAN-plan-priority-concurrency T11): %d finding(s) on %d "
            "required plan(s) (%s). NOT enforced while wl_plandeps.X_FIELDS_REQUIRED is False."
            % (
                len(pending),
                len({f.rel for f in pending}),
                ", ".join("%s=%d" % kv for kv in sorted(per.items())),
            )
        )
        for f in present:
            print("    %s  %s  %s" % (f.code, f.rel, f.message[:160]))
    for row in infos:
        print("  INFO D17 %s" % row)
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
            "  Fix: `check_plan_deps.py --draft <path>` proposes a Depends-On value and "
            '`--set <path> "<value>" --write` applies it; `--set-x <path> "Owns: ..." --write` '
            "sets an X field. An `(operator)` Priority is the operator's to change, never the AI's.",
            file=sys.stderr,
        )
        return 1
    print(
        "✓ plan deps: %d required plan(s) carry a valid Depends-On (%d edge(s)), no cycle, of %d plan(s) parsed."
        % (stats["required"], stats["edges"], stats["plans"])
    )
    print(
        "  X fields: %d of %d required plan(s) carry a valid Priority/Concurrency/Owns triple "
        "(%d exclusive); enforcement %s. D17 %s."
        % (
            stats["triples"],
            stats["required"],
            stats["exclusive"],
            "ON" if stats["strict_x"] else "OFF until the T11 migration",
            how,
        )
    )
    print(
        "  Blind spot: whether an edge is the RIGHT one (citation is not dependency), task-edge "
        "boxes (D9, PLAN-plan-dependencies T12), and whether a plan's Owns is TRUE (overlap is "
        "judged on what plans declare)."
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


# --------------------------------------------------------------------------- The X verbs.


def _norm_ws(text: str) -> str:
    return " ".join((text or "").split())


def _parse_kv(items: list[str]) -> dict[str, str]:
    """`["Priority: P2 -- x", "Owns: a/**"]` -> {"Priority": "P2 -- x", "Owns": "a/**"}. ValueError on anything else."""
    out: dict[str, str] = {}
    for item in items:
        key, sep, value = item.partition(":")
        key = key.strip()
        if not sep or key not in D.X_FIELDS:
            raise ValueError("%r is not `Priority: ...`, `Concurrency: ...` or `Owns: ...`" % item)
        out[key] = value.strip()
    return out


def freeze_problem(old: D.Header, new: D.Header) -> str:
    """Why `new` breaks the operator freeze on `old`'s Priority, or "". The CLI verbs have no operator turn to consult, so they never change, drop or introduce an `(operator)` value."""
    was, now = old.priority, new.priority
    if was is not None and was.operator:
        if (
            now is None
            or not now.operator
            or (now.level, _norm_ws(now.reason))
            != (
                was.level,
                _norm_ws(was.reason),
            )
        ):
            return (
                "`Priority: %s` is operator-set; the AI never changes it. Ask the operator "
                "(AskUserQuestion), or they edit the line" % was
            )
    elif now is not None and now.operator:
        return (
            "introducing `(operator)` is the operator's act, not a verb's; write the AI value and "
            "let the operator mark it"
        )
    return ""


def x_problems(
    text: str, fields: dict[str, str], old_text: str | None = None
) -> tuple[str, list[str]]:
    """(new text, problems) for setting `fields` on `text`: the grammar, the glob rules, the window and the freeze. The new text is "" when set_x itself refused."""
    try:
        new_text = D.set_x(text, fields)
    except ValueError as exc:
        return "", [str(exc)]
    new_h = D.parse_header(new_text)
    problems = [
        "%s  %s" % (f.code, f.message)
        for f in X.x_findings(new_h, new_text)
        if f.message.split(":", 1)[0] in fields
        or f.code in (D.D_OWNS_GLOB, D.D_UNIVERSAL, D.D_WINDOW)
    ]
    why = freeze_problem(D.parse_header(old_text if old_text is not None else text), new_h)
    if why:
        problems.append("%s  %s" % (D.D_OPERATOR_DEMOTED, why))
    return new_text, problems


def _numstat(old: str, new: str) -> tuple[int, int]:
    added = removed = 0
    for line in difflib.ndiff(old.splitlines(), new.splitlines()):
        if line.startswith("+ "):
            added += 1
        elif line.startswith("- "):
            removed += 1
    return added, removed


def set_x_value(root: pathlib.Path, target: str, items: list[str], write: bool) -> int:
    rel = _rel(root, target)
    path = root / rel
    try:
        text = path.read_text(encoding="utf-8")
        fields = _parse_kv(items)
    except (OSError, ValueError) as exc:
        print("✗ %s: %s" % (rel, exc), file=sys.stderr)
        return 2
    new_text, problems = x_problems(text, fields)
    if problems:
        print("✗ refused: %s would carry:" % rel, file=sys.stderr)
        for line in problems:
            print("    %s" % line, file=sys.stderr)
        return 1
    added, removed = _numstat(text, new_text)
    print("%s  (%d added, %d removed)" % (rel, added, removed))
    for name, value in fields.items():
        print("  + %s: %s" % (name, value))
    if not write:
        print("  (dry run; add --write to apply)")
        return 0
    path.write_text(new_text, encoding="utf-8")
    print("  ✓ written")
    return 0


def _repo_files(root: pathlib.Path) -> list[str]:
    """Every tracked path (submodules included) when `root` is a git checkout, else every file under it."""
    if (root / ".git").exists():
        r = subprocess.run(
            ["git", "-C", str(root), "ls-files", "--recurse-submodules"],
            capture_output=True,
            text=True,
            check=False,
        )
        if r.returncode == 0:
            return r.stdout.splitlines()
    return sorted(
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if p.is_file() and ".git" not in p.parts
    )


def _owns_table(graph: D.Graph, root: pathlib.Path) -> tuple[dict[str, list[str]], list[str]]:
    """({rel: normalised globs} for required plans with a valid Owns, [rel without one])."""
    table: dict[str, list[str]] = {}
    skipped: list[str] = []
    for rel in graph.required():
        owns = graph.plans[rel].header.owns
        if owns is None:
            skipped.append(rel)
            continue
        globs, problems = X.normalize_owns(owns.globs, root)
        if problems:
            skipped.append(rel)
            continue
        table[rel] = [*globs, rel]
    return table, skipped


def overlaps(root: pathlib.Path) -> int:
    graph = D.Graph.load(root)
    table, skipped = _owns_table(graph, root)
    files = _repo_files(root)
    rels = sorted(table)
    pairs = 0
    for i, a in enumerate(rels):
        for b in rels[i + 1 :]:
            hits = X.owns_overlap(table[a], table[b])
            if not hits:
                continue
            pairs += 1
            shared = sorted(
                set(X.materialise([h[0] for h in hits], files))
                & set(X.materialise([h[1] for h in hits], files))
            )
            print("%s  x  %s" % (graph.plans[a].base, graph.plans[b].base))
            for ga, gb, w in hits[:4]:
                print("    `%s` vs `%s`, e.g. %s" % (ga, gb, w))
            if len(hits) > 4:
                print("    ... and %d more glob pair(s)" % (len(hits) - 4))
            print(
                "    shared files (%d): %s%s"
                % (len(shared), ", ".join(shared[:5]), " ..." if len(shared) > 5 else "")
            )
    print(
        "plan overlaps: %d overlapping pair(s) among %d required plan(s) with a valid Owns; "
        "%d without one (not judged), %d tracked file(s) materialised against."
        % (pairs, len(rels), len(skipped), len(files))
    )
    if not files:
        print(
            "✗ no file list to materialise against; the shared-file counts above mean nothing",
            file=sys.stderr,
        )
        return 2
    return 0


# ---- the migration seeds (section 7)

_PATH_RE = re.compile(r"(?<![\w/.@-])((?:[.\w@-]+/)+[\w.@*{},-]+)(?::\d+(?:-\d+)?)?")
_EVIDENCE_WORDS = frozenset({"see", "measured", "cf", "cf."})
_EXCLUSIVE_WORDS = (
    "npm run gen:",
    "regenerate",
    "every file",
    "repo-wide",
    "mass",
    "reflow",
    "bulk",
)
_OPERATOR_ORDER_RE = re.compile(r"Operator (?:order|ruling)[^\n]{0,60}?(\d{4}-\d{2}-\d{2})")
_BOX_RE = re.compile(r"^(\s*)[-*+] \[ \]")


def open_box_text(text: str) -> tuple[str, int]:
    """(the text of every OPEN box with its indented continuation lines, how many open boxes)."""
    out: list[str] = []
    count = 0
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        m = _BOX_RE.match(lines[i])
        if not m:
            i += 1
            continue
        count += 1
        indent = len(m.group(1))
        out.append(lines[i])
        i += 1
        while (
            i < len(lines) and lines[i].strip() and len(lines[i]) - len(lines[i].lstrip()) > indent
        ):
            out.append(lines[i])
            i += 1
    return "\n".join(out), count


def cited_paths(root: pathlib.Path, text: str) -> list[str]:
    """Repo paths `text` cites that exist, or are a new file under an existing directory, minus plan files and paths cited only as evidence (a `see` or `measured` in the six words before)."""
    out: list[str] = []
    for m in _PATH_RE.finditer(text):
        path = m.group(1).rstrip(".,;:)")
        before = re.findall(r"[\w.]+", text[max(0, m.start() - 80) : m.start()].lower())[-6:]
        if _EVIDENCE_WORDS & set(before):
            continue
        if (
            path.startswith(("agent/plans/", "http", "www."))
            or re.match(r"^agent/(?:[^/]+/)*PLAN-[^/]+\.md$", path)
            or "*" in path
            or "{" in path
        ):
            continue
        p = root / path
        if not (p.exists() or (p.parent.is_dir() and "." in p.name)):
            continue
        if path not in out:
            out.append(path)
    return out


def collapse(paths: list[str]) -> list[str]:
    """Four or more siblings with one extension become `dir/*.ext`."""
    groups: dict[tuple[str, str], list[str]] = {}
    for p in paths:
        d, _, name = p.rpartition("/")
        ext = name.rsplit(".", 1)[1] if "." in name else ""
        groups.setdefault((d, ext), []).append(p)
    out: list[str] = []
    for p in paths:
        d, _, name = p.rpartition("/")
        ext = name.rsplit(".", 1)[1] if "." in name else ""
        members = groups[(d, ext)]
        if len(members) >= 4 and ext:
            g = "%s/*.%s" % (d, ext)
            if g not in out:
                out.append(g)
        elif p not in out:
            out.append(p)
    return out


def _salvage(raw: str | None, value_re: re.Pattern[str]) -> str:
    """A malformed `P0. reason` / `parallel. reason` rewritten into the one spelling, or ""."""
    if not raw:
        return ""
    m = re.match(r"^(\S+?)[.;:,]\s+(\S.*)$", raw.strip())
    if not m:
        return ""
    cand = "%s -- %s" % (m.group(1), m.group(2))
    return cand if value_re.match(cand) else ""


def seed_row(root: pathlib.Path, rel: str, text: str, files: list[str], today: str) -> dict:
    """One migration seed (section 7). A field already valid is KEPT byte for byte; a malformed one is salvaged into the one spelling when it can be; anything else is seeded."""
    header = D.parse_header(text)
    status = header.status or "unknown"
    boxes, n_open = open_box_text(text)
    row: dict = {
        "rel": rel,
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "status": status,
        "open": n_open,
    }

    pf = header.get(D.PRIORITY)
    if pf is not None and not pf.errors:
        row[D.PRIORITY] = pf.value
    else:
        salvaged = _salvage(pf.value if pf else None, D.PRIORITY_VALUE_RE)
        if salvaged:
            row[D.PRIORITY] = salvaged
        else:
            if status in (
                "executing",
                "in-progress",
                "active",
                "partially",
                "phase",
            ) or status.startswith("mostly"):
                level = 1
            elif status in ("approved", "ready"):
                level = 2
            else:
                level = 3
            dates = [d for d in _OPERATOR_ORDER_RE.findall(text) if d <= today]
            recent = any(_days_between(d, today) <= 7 for d in dates)
            if recent and level > 1:
                level -= 1
            row[D.PRIORITY] = "P%d -- seed: Status %s, %d open box(es)%s" % (
                level, status, n_open, ", a recent operator order" if recent else "",
            )  # fmt: skip

    of = header.get(D.OWNS)
    if of is not None and not of.errors:
        row[D.OWNS] = of.value
        globs, _ = X.normalize_owns(of.parsed.globs, root)
    else:
        # The fallback reads the body only: a header's own pointers (`Full-Text: <sha> agent/PLAN-x.md`, `Supersedes: ...`) are provenance, not files the plan edits.
        lines = text.splitlines(keepends=True)
        try:
            body = "".join(lines[D.header_block_end(lines) :])
        except ValueError:
            body = text
        paths = cited_paths(root, boxes) or cited_paths(root, body)
        globs = collapse(paths)
        row[D.OWNS] = (
            ", ".join(globs) if globs else "none -- seed: the plan cites no repo path to edit"
        )
    n_files = len(X.materialise(X.normalize_owns(globs, root)[0], files)) if globs else 0
    row["files"] = n_files

    cf = header.get(D.CONCURRENCY)
    if cf is not None and not cf.errors:
        row[D.CONCURRENCY] = cf.value
    else:
        salvaged = _salvage(cf.value if cf else None, D.CONCURRENCY_VALUE_RE)
        low = boxes.lower()
        word = next((w for w in _EXCLUSIVE_WORDS if w in low), "")
        if salvaged:
            row[D.CONCURRENCY] = salvaged
        elif word:
            row[D.CONCURRENCY] = "exclusive -- seed: an open box mentions %r" % word
        elif n_files > EXCLUSIVE_FILES:
            row[D.CONCURRENCY] = "exclusive -- seed: the seed Owns names %d files" % n_files
        else:
            row[D.CONCURRENCY] = "parallel"
    return row


def _days_between(a: str, b: str) -> int:
    import datetime  # noqa: PLC0415 -- the migration verb alone

    try:
        return abs((datetime.date.fromisoformat(b) - datetime.date.fromisoformat(a)).days)
    except ValueError:
        return 10**6


def migrate_rows(root: pathlib.Path, today: str | None = None) -> list[dict]:
    import datetime  # noqa: PLC0415

    today = today or datetime.datetime.now(datetime.UTC).date().isoformat()
    graph = D.Graph.load(root)
    files = _repo_files(root)
    rows = []
    for rel in graph.required():
        text = (root / rel).read_text(encoding="utf-8")
        rows.append(seed_row(root, rel, text, files, today))
    table = {
        r["rel"]: X.normalize_owns(
            D.parse_owns(r[D.OWNS])[0].globs if D.parse_owns(r[D.OWNS])[0] else (), root
        )[0]
        for r in rows
    }
    for r in rows:
        r["overlaps"] = sorted(
            pathlib.PurePath(o).name
            for o in table
            if o != r["rel"] and X.owns_overlap(table[r["rel"]], table[o])
        )
    return rows


def _fields(row: dict) -> dict[str, str]:
    return {k: str(row[k]) for k in D.X_FIELDS if k in row}


def migrate_diff(root: pathlib.Path, rows: list[dict]) -> int:
    changed = 0
    for r in rows:
        text = (root / r["rel"]).read_text(encoding="utf-8")
        new_text, _problems = x_problems(text, _fields(r))
        if not new_text or new_text == text:
            continue
        changed += 1
        sys.stdout.writelines(
            difflib.unified_diff(
                text.splitlines(keepends=True),
                new_text.splitlines(keepends=True),
                "a/%s" % r["rel"],
                "b/%s" % r["rel"],
                n=1,
            )
        )
    print(
        "migrate-x --diff: %d of %d required plan(s) would change; nothing was written."
        % (changed, len(rows))
    )
    return 0


def migrate_table(rows: list[dict]) -> int:
    print(
        "#   plan                                        Status       open  Priority                         Conc.       Owns (n: first 2)                          overlaps with"
    )
    for n, r in enumerate(rows, 1):
        owns = D.parse_owns(r.get(D.OWNS, ""))[0]
        globs = list(owns.globs) if owns else []
        shown = (
            "%d: %s" % (len(globs), ", ".join(globs[:2])) if globs else str(r.get(D.OWNS, ""))[:40]
        )
        print(
            "%-3d %-43s %-12s %-5d %-32s %-11s %-42s %s"
            % (
                n,
                pathlib.PurePath(r["rel"]).name[:43],
                str(r.get("status", ""))[:12],
                int(r.get("open", 0)),
                str(r.get(D.PRIORITY, ""))[:32],
                str(r.get(D.CONCURRENCY, "")).split(" ")[0],
                shown[:42],
                ", ".join(r.get("overlaps") or []) or "-",
            )
        )
    print("%d row(s)." % len(rows))
    return 0


def migrate_apply(root: pathlib.Path, proposal: pathlib.Path, write: bool, diff: bool) -> int:
    try:
        doc = json.loads(proposal.read_text(encoding="utf-8"))
        rows = doc["rows"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print("✗ cannot read the proposal %s: %s" % (proposal, exc), file=sys.stderr)
        return 2
    plans: list[tuple[pathlib.Path, str, str]] = []
    bad = 0
    for r in rows:
        path = root / r["rel"]
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            print("✗ %s: %s" % (r["rel"], exc), file=sys.stderr)
            bad += 1
            continue
        if hashlib.sha256(text.encode("utf-8")).hexdigest() != r.get("sha256"):
            print(
                "✗ %s changed since --save (sha256 differs); re-run --migrate-x --save" % r["rel"],
                file=sys.stderr,
            )
            bad += 1
            continue
        new_text, problems = x_problems(text, _fields(r))
        # The migration may INTRODUCE `(operator)`: rows the operator changed in the approval table are written with it (decision D2). It may never change a line that already carries it.
        problems = [p for p in problems if "introducing `(operator)`" not in p]
        if problems:
            print("✗ %s:" % r["rel"], file=sys.stderr)
            for line in problems:
                print("    %s" % line, file=sys.stderr)
            bad += 1
            continue
        plans.append((path, text, new_text))
    if bad:
        print("✗ migrate-x --apply: %d row(s) refused; nothing was written." % bad, file=sys.stderr)
        return 1
    total_a = total_r = 0
    for path, text, new_text in plans:
        added, removed = _numstat(text, new_text)
        total_a, total_r = total_a + added, total_r + removed
        print("%d\t%d\t%s" % (added, removed, path.relative_to(root).as_posix()))
        if diff:
            sys.stdout.writelines(
                difflib.unified_diff(
                    text.splitlines(keepends=True), new_text.splitlines(keepends=True), n=1
                )
            )
        if write and new_text != text:
            path.write_text(new_text, encoding="utf-8")
    print(
        "migrate-x --apply: %d file(s), %d line(s) added, %d removed; %s"
        % (
            len(plans),
            total_a,
            total_r,
            "WRITTEN" if write else "dry run, nothing written (add --write)",
        )
    )
    return 0


def migrate(root: pathlib.Path, argv: list[str]) -> int:
    proposal = root / PROPOSAL_REL
    if "--apply" in argv:
        src = _arg_after(argv, "--apply")
        if src is None:
            print("✗ --apply needs a proposal JSON", file=sys.stderr)
            return 2
        return migrate_apply(root, pathlib.Path(src), "--write" in argv, "--diff" in argv)
    if "--table" in argv:
        try:
            rows = json.loads(proposal.read_text(encoding="utf-8"))["rows"]
        except (OSError, ValueError, KeyError) as exc:
            print(
                "✗ no saved proposal at %s (%s); run --migrate-x --save first" % (proposal, exc),
                file=sys.stderr,
            )
            return 2
        return migrate_table(rows)
    rows = migrate_rows(root)
    if "--diff" in argv:
        return migrate_diff(root, rows)
    if "--save" in argv:
        proposal.parent.mkdir(parents=True, exist_ok=True)
        proposal.write_text(json.dumps({"rows": rows}, indent=2) + "\n", encoding="utf-8")
        print(
            "migrate-x: %d row(s) saved to %s; review them, then --table and --apply."
            % (len(rows), proposal)
        )
        return 0
    for r in rows:
        print("%s  [Status: %s, %d open]" % (r["rel"], r["status"], r["open"]))
        for k in D.X_FIELDS:
            print("  %s: %s" % (k, r[k]))
        if r["overlaps"]:
            print("  overlaps: %s" % ", ".join(r["overlaps"]))
    print("migrate-x: %d seed row(s); nothing was written." % len(rows))
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
        if "--overlaps" in argv:
            return overlaps(root)
        if "--migrate-x" in argv:
            return migrate(root, argv)
        if "--set-x" in argv:
            i = argv.index("--set-x")
            items = [a for a in argv[i + 2 :] if not a.startswith("--")]
            if len(argv) < i + 3 or not items:
                print('✗ usage: --set-x <path> "<Key: value>" ... [--write]', file=sys.stderr)
                return 2
            return set_x_value(root, argv[i + 1], items, "--write" in argv)
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
        base_arg = _arg_after(argv, "--base-tree")
        return check(root, pathlib.Path(base_arg) if base_arg else None)
    except CannotRunError as exc:
        print("⚠ CANNOT RUN (exit 77, which is not a verdict): %s" % exc, file=sys.stderr)
        return 77


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

"""check:ci-step-phase-coverage -- every renet step id has a place in the console's phase map, and the map names no dead id.

WHY. The console run block picks its animation scene from the step events renet emits (agent/plans/PLAN-console-animations.md D1, D2). `private/account/web/src/lib/run-phases.json` maps each animated step id to a scene and lists every other id under `plain`. Nothing ties that file to renet: a new `timer.Start("x")` in renet renders as an unknown step that keeps the previous scene, and a renamed step leaves a json key that matches nothing, so a scene silently never plays. This gate is D7: the map and renet's emitters agree in both directions.

THE RULES.
- R1 unmapped: every step id the non-test renet sources pass to a step timer's `Start` or `Record` is a key of `scenes` or an entry of `plain`.
- R2 stale: every key of `scenes` and every entry of `plain` is an id renet still emits.
- R3 shape: no id is both a scene step and plain, `plain` holds no duplicate, and every scene value is a member of the `RunScene` union in run-phases.ts.
- R4 resolvable: a timer call's first argument is a string literal or a same-package string constant. Anything else is an id this gate cannot see, so it is a finding rather than a skip: an unread id is an unchecked id.

WHAT COUNTS AS A TIMER. A receiver whose last name segment is declared `*output.StepTimer` (a field, parameter or var), assigned from `output.NewStepTimer*()`, or assigned from a function whose signature returns `*output.StepTimer`. A method value bound from a timer (`mark: timer.Record`, as in cmd/renet/repository_migrate.go) makes its name an alias, and a call through the alias is a timer call. `reporter.Start("ping")` in pkg/functions is a progress reporter, not a step timer, and is not read. Comments are blanked before the scan, so a commented-out call is not an emitter.

ANTI-VACUITY. A tree without private/renet or without run-phases.json checked out is CANNOT RUN (exit 77), never a pass. On the real tree the scan must read at least MIN_GO_FILES Go files, MIN_CALLS timer calls and MIN_IDS distinct ids, or it is CANNOT RUN: a scan that collapsed (a renamed timer type, a sparse checkout) would otherwise report a clean map over nothing. The controls run before every verdict, and the success line prints the counts.

Exit 0 clean, 1 finding, 2 a control did not behave, 77 cannot run.

---- gate ----
step: Check renet step ids against the console phase map
lane: quality-code
needs: submodules
selftest: true
why: the run block animates from run-phases.json; a renet step missing from it, or a json id renet
     no longer emits, makes a scene silently never play.
---- end gate ----
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from typing import Any

from rediacc_ci import paths
from rediacc_ci.controls import plant

RENET_REL = "private/renet"
PHASES_REL = "private/account/web/src/lib/run-phases.json"
PHASES_TS_REL = "private/account/web/src/lib/run-phases.ts"
# The package that DEFINES StepTimer. Its own methods take `name` as a parameter, so it emits no id of its own and is not scanned.
TIMER_PKG_REL = "pkg/output"
EXIT_CANNOT_RUN = 77
# Floors for the REAL tree, measured 2026-11-25 against renet 7c5464c8: 1000+ non-test Go files, 47 timer calls, 29 distinct ids. Set well under each so routine churn never trips them and a collapse always does.
MIN_GO_FILES = 300
MIN_CALLS = 20
MIN_IDS = 15
SKIP_DIRS = frozenset({"vendor", "testdata", "node_modules", ".git"})

RED = "\033[0;31m"
GREEN = "\033[0;32m"
YELLOW = "\033[0;33m"
NC = "\033[0m"

# One alternation so a `//` inside a string literal is never read as a comment, and a quote inside a comment never opens a string.
_TOKEN_RE = re.compile(
    r'"(?:\\.|[^"\\\n])*"'  # interpreted string
    r"|`[^`]*`"  # raw string
    r"|'(?:\\.|[^'\\\n])*'"  # rune
    r"|//[^\n]*"  # line comment
    r"|/\*.*?\*/",  # block comment
    re.DOTALL,
)
_CONST_BLOCK_RE = re.compile(r"\bconst\s*\((.*?)\n\s*\)", re.DOTALL)
_CONST_LINE_RE = re.compile(r'\bconst\s+(\w+)\s*(?:[\w.]+\s*)?=\s*"((?:\\.|[^"\\\n])*)"')
_CONST_ENTRY_RE = re.compile(r'^\s*(\w+)\s*(?:[\w.]+\s*)?=\s*"((?:\\.|[^"\\\n])*)"', re.MULTILINE)
_TYPED_NAME_RE = re.compile(r"\b(\w+)\s+\*output\.StepTimer\b")
_NEW_TIMER_RE = re.compile(r"\b(\w+)\s*:?=\s*output\.NewStepTimer\w*\s*\(")
# `func Name(...)` or a method `func (r *R) Name(...)`; either returns the timer.
_TIMER_FUNC_RE = re.compile(r"\bfunc\s+(?:\([^)]*\)\s*)?(\w+)\s*\([^)]*\)\s*\*output\.StepTimer\b")
# A declaration prefix right before an alias name: `func ` or a method `func (r *R) `.
_FUNC_DECL_TAIL_RE = re.compile(r"\bfunc\s*(?:\([^)]*\)\s*)?$")
_RECEIVER_CALL_RE = re.compile(r"\b(\w+)\.(Start|Record)\s*\(\s*")
_FIRST_ARG_RE = re.compile(r'"((?:\\.|[^"\\\n])*)"\s*[,)]|`([^`]*)`\s*[,)]|([A-Za-z_]\w*)\s*[,)]')


class CannotRunError(Exception):
    """The inputs could not be read; exit 77, never a verdict."""


def blank_comments(src: str) -> str:
    """`src` with every comment replaced by spaces of the same length, newlines kept, so offsets and line numbers survive."""

    def repl(m: re.Match[str]) -> str:
        tok = m.group(0)
        if tok.startswith(("//", "/*")):
            return re.sub(r"[^\n]", " ", tok)
        return tok

    return _TOKEN_RE.sub(repl, src)


def mask_strings(src: str) -> str:
    """`src` (already comment-blanked) with every string and rune BODY replaced by spaces, delimiters kept, so a call spelled inside a string literal is not a call site. Offsets match `src`, which is where the argument is then read from."""

    def repl(m: re.Match[str]) -> str:
        tok = m.group(0)
        if tok.startswith(("//", "/*")):
            return tok
        return tok[0] + re.sub(r"[^\n]", " ", tok[1:-1]) + tok[-1]

    return _TOKEN_RE.sub(repl, src)


def package_constants(sources: list[str]) -> dict[str, str]:
    """Every string constant one package's (comment-blanked) files declare, name -> value."""
    out: dict[str, str] = {}
    for src in sources:
        for block in _CONST_BLOCK_RE.findall(src):
            out.update(_CONST_ENTRY_RE.findall(block))
        out.update(_CONST_LINE_RE.findall(src))
    return out


def timer_names(sources: list[str]) -> set[str]:
    """The names a step timer is held under, across every file: typed declarations, NewStepTimer assignments, and assignments from a function returning *output.StepTimer."""
    names: set[str] = set()
    funcs: set[str] = set()
    for src in sources:
        names.update(_TYPED_NAME_RE.findall(src))
        names.update(_NEW_TIMER_RE.findall(src))
        funcs.update(_TIMER_FUNC_RE.findall(src))
    for fn in funcs:
        pat = re.compile(r"\b(\w+)\s*:?=\s*(?:\w+\.)*" + re.escape(fn) + r"\s*\(")
        for src in sources:
            names.update(pat.findall(src))
    # A function's own name is not a holder, and `func` keyword captures are impossible by construction of the patterns above.
    return names - funcs


def timer_aliases(sources: list[str], names: set[str]) -> set[str]:
    """Names bound to a timer method VALUE (`mark: timer.Record`, `m := t.Start`); a call through one is a timer call."""
    if not names:
        return set()
    alt = "|".join(sorted(re.escape(n) for n in names))
    pat = re.compile(
        r"\b(\w+)\s*(?::=|=|:)\s*(?:\w+\.)*(?:" + alt + r")\.(?:Start|Record)\b(?!\s*\()"
    )
    out: set[str] = set()
    for src in sources:
        out.update(pat.findall(src))
    return out


def _line_of(src: str, offset: int) -> int:
    return src.count("\n", 0, offset) + 1


def calls_in(src: str, names: set[str], aliases: set[str], consts: dict[str, str]):
    """Yield (line, id_or_None, raw_arg) for every timer call in one comment-blanked file. id is None when the argument does not resolve."""
    masked = mask_strings(src)
    sites: list[int] = [m.end() for m in _RECEIVER_CALL_RE.finditer(masked) if m.group(1) in names]
    if aliases:
        alt = "|".join(sorted(re.escape(a) for a in aliases))
        # The optional receiver is deliberate: an alias bound as a struct field (`mark: timer.Record`) is called as `d.mark(`, and a receiver's type is not knowable from the text. An unrelated method that shares an alias name and takes a string is therefore read as a call (an R1 or R4 finding the author clears by renaming one side), which a missed emitter would not give.
        for m in re.finditer(r"(?<![\w])(?:\w+\.)?(?:" + alt + r")\s*\(\s*", masked):
            # A declaration `func mark(` or a method `func (r *R) mark(` is not a call.
            before = masked[max(0, m.start() - 80) : m.start()]
            if _FUNC_DECL_TAIL_RE.search(before):
                continue
            sites.append(m.end())
    for end in sorted(set(sites)):
        arg = _FIRST_ARG_RE.match(src, end)
        line = _line_of(src, end)
        if arg is None:
            yield line, None, src[end : end + 60].split("\n", 1)[0]
        elif arg.group(1) is not None:
            yield line, arg.group(1), arg.group(1)
        elif arg.group(2) is not None:
            yield line, arg.group(2), arg.group(2)
        else:
            ident = arg.group(3)
            yield line, consts.get(ident), ident


def go_files(renet: str) -> list[str]:
    """Non-test Go sources under renet, repo-relative to renet, outside the timer's own package."""
    out: list[str] = []
    for dirpath, dirnames, filenames in paths.walk_tree(renet, exclude_dirs=SKIP_DIRS):
        dirnames.sort()
        for fn in sorted(filenames):
            if not fn.endswith(".go") or fn.endswith("_test.go"):
                continue
            rel = os.path.relpath(os.path.join(dirpath, fn), renet).replace(os.sep, "/")
            if os.path.dirname(rel) == TIMER_PKG_REL:
                continue
            out.append(rel)
    return out


def emitted_ids(renet: str) -> dict:
    """{'ids': {id: [rel:line]}, 'unresolved': [finding], 'files': n, 'calls': n} for a renet tree."""
    files = go_files(renet)
    text: dict[str, str] = {}
    for rel in files:
        with open(os.path.join(renet, rel), encoding="utf-8", errors="replace") as fh:
            text[rel] = blank_comments(fh.read())
    by_pkg: dict[str, list[str]] = {}
    for rel in files:
        by_pkg.setdefault(os.path.dirname(rel), []).append(text[rel])
    consts = {pkg: package_constants(srcs) for pkg, srcs in by_pkg.items()}
    masked = [mask_strings(t) for t in text.values()]
    names = timer_names(masked)
    aliases = timer_aliases(masked, names)
    ids: dict[str, list[str]] = {}
    unresolved: list[str] = []
    calls = 0
    for rel in files:
        for line, sid, raw in calls_in(text[rel], names, aliases, consts[os.path.dirname(rel)]):
            calls += 1
            where = "%s/%s:%d" % (RENET_REL, rel, line)
            if sid is None:
                unresolved.append(
                    "%s: the step id argument `%s` is neither a string literal nor a same-package string constant,"
                    " so this gate cannot read it; pass a literal or a `const` (R4)"
                    % (where, raw.strip())
                )
            else:
                ids.setdefault(sid, []).append(where)
    return {
        "ids": ids,
        "unresolved": unresolved,
        "files": len(files),
        "calls": calls,
        "names": names,
        "aliases": aliases,
    }


def scene_union(ts_text: str) -> set[str]:
    m = re.search(r"\btype\s+RunScene\s*=\s*([^;]+);", ts_text)
    if not m:
        return set()
    return set(re.findall(r"'([^']+)'", m.group(1)))


def map_findings(phases: dict, union: set[str], ids: dict[str, list[str]]) -> list[str]:
    """R1-R3 over a parsed run-phases.json and the emitted id table."""
    out: list[str] = []
    scenes = phases.get("scenes")
    plain = phases.get("plain")
    if not isinstance(scenes, dict) or not isinstance(plain, list):
        return [
            '%s: expected {"scenes": {id: scene}, "plain": [id]}; the shape changed' % PHASES_REL
        ]
    plain_set = set()
    for pid in plain:
        if pid in plain_set:
            out.append(
                "%s: `%s` is listed twice under plain; delete the duplicate (R3)"
                % (PHASES_REL, pid)
            )
        plain_set.add(pid)
    for sid, scene in sorted(scenes.items()):
        if sid in plain_set:
            out.append(
                "%s: `%s` is both a scene step (%s) and plain; keep exactly one (R3)"
                % (PHASES_REL, sid, scene)
            )
        if scene not in union:
            out.append(
                "%s: `%s` maps to scene `%s`, which is not a member of RunScene in %s (%s) (R3)"
                % (PHASES_REL, sid, scene, PHASES_TS_REL, ", ".join(sorted(union)))
            )
    known = set(scenes) | plain_set
    out.extend(
        "%s: renet emits step `%s`, which %s neither maps to a scene nor lists under plain;"
        " add it to `scenes` with its scene, or to `plain` (R1)" % (where, sid, PHASES_REL)
        for sid in sorted(ids)
        if sid not in known
        for where in ids[sid]
    )
    out.extend(
        "%s: `%s` is an id no renet step timer emits any more; delete it, or rename it to the id renet now uses (R2)"
        % (PHASES_REL, sid)
        for sid in sorted(known - set(ids))
    )
    return out


def scan(root: str, floors: tuple[int, int, int] = (1, 1, 1)) -> dict:
    renet = os.path.join(root, RENET_REL)
    if not os.path.isdir(os.path.join(renet, "pkg")):
        raise CannotRunError(
            "%s is not checked out, so no step id can be read; run `git submodule update --init %s`"
            % (RENET_REL, RENET_REL)
        )
    phases_path = os.path.join(root, PHASES_REL)
    ts_path = os.path.join(root, PHASES_TS_REL)
    if not os.path.isfile(phases_path) or not os.path.isfile(ts_path):
        raise CannotRunError(
            "%s or %s is missing; run `git submodule update --init private/account`"
            % (PHASES_REL, PHASES_TS_REL)
        )
    try:
        with open(phases_path, encoding="utf-8") as fh:
            phases = json.load(fh)
    except (OSError, ValueError) as exc:
        raise CannotRunError("%s does not parse: %s" % (PHASES_REL, exc)) from exc
    with open(ts_path, encoding="utf-8") as fh:
        union = scene_union(fh.read())
    if not union:
        raise CannotRunError(
            "no `type RunScene = '...' | ...;` in %s, so scene values cannot be checked; update this gate with it"
            % PHASES_TS_REL
        )
    emitted = emitted_ids(renet)
    min_files, min_calls, min_ids = floors
    if (
        emitted["files"] < min_files
        or emitted["calls"] < min_calls
        or len(emitted["ids"]) < min_ids
    ):
        raise CannotRunError(
            "VACUOUS: %d Go file(s), %d timer call(s), %d distinct id(s) under %s, floors %d/%d/%d;"
            " the scan is not seeing renet's step timers, so its green would mean nothing"
            % (
                emitted["files"],
                emitted["calls"],
                len(emitted["ids"]),
                RENET_REL,
                min_files,
                min_calls,
                min_ids,
            )
        )
    findings = list(emitted["unresolved"]) + map_findings(phases, union, emitted["ids"])
    return {
        "files": emitted["files"],
        "calls": emitted["calls"],
        "ids": len(emitted["ids"]),
        "scene_ids": len(phases["scenes"]) if isinstance(phases.get("scenes"), dict) else 0,
        "plain_ids": len(phases["plain"]) if isinstance(phases.get("plain"), list) else 0,
        "aliases": sorted(emitted["aliases"]),
        "findings": findings,
    }


# ---- selftest ------------------------------------------------------------------

FIX_OUTPUT = (
    "package output\n"
    "type StepTimer struct{}\n"
    "func (t *StepTimer) Start(name string) {}\n"
    'func (t *StepTimer) Record(name string, d int, detail string) { t.Start("never_read") }\n'
)
FIX_ORCH = (
    "package orchestration\n"
    'import "x/pkg/output"\n'
    "type Orchestrator struct {\n\tTimer *output.StepTimer\n}\n"
    "func (o *Orchestrator) Up() {\n"
    '\to.Timer.Start("compose_up")\n'
    '\t// o.Timer.Start("commented_out")\n'
    '\to.Timer.Record("sessions_end", 0,\n\t\t"detail")\n'
    "}\n"
)
FIX_CMD = (
    "package main\n"
    'import "x/pkg/output"\n'
    'const cmdCheckpoint = "checkpoint"\n'
    'const (\n\tmarker = "cutover_complete"\n\tother  = "x"\n)\n'
    "type ops struct{ mark func(string, int, string) }\n"
    "func newForkTimer() *output.StepTimer { return output.NewStepTimer() }\n"
    "func run(o ops) {\n"
    "\ttimer := newForkTimer()\n"
    "\ttimer.Start(cmdCheckpoint)\n"
    '\ttimer.Start("cow_sync")\n'
    "\tr := ops{mark: timer.Record}\n"
    '\to.mark(marker, 0, "h")\n'
    '\treporter.Start("ping")\n'
    '\ts := "timer.Start(\\"in_a_string\\")"\n'
    "\t_ = s\n"
    "}\n"
)
FIX_TS = "type RunScene = 'clone' | 'transfer' | 'start' | 'stop' | 'cutover';\n"
FIX_PHASES: dict[str, Any] = {
    "scenes": {
        "cow_sync": "clone",
        "checkpoint": "transfer",
        "compose_up": "start",
        "cutover_complete": "cutover",
    },
    "plain": ["sessions_end"],
}


def _fixture(tmp: str, go: dict[str, str], phases: object, ts: str = FIX_TS) -> str:
    root = os.path.join(tmp, "root%d" % len(os.listdir(tmp)))
    files = {"%s/%s" % (RENET_REL, rel): body for rel, body in go.items()}
    files[PHASES_REL] = json.dumps(phases) if not isinstance(phases, str) else phases
    files[PHASES_TS_REL] = ts
    for rel, body in files.items():
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(body)
    os.makedirs(os.path.join(root, RENET_REL, "pkg"), exist_ok=True)
    return root


def _base_go() -> dict[str, str]:
    return {
        "pkg/output/steps.go": FIX_OUTPUT,
        "pkg/orchestration/up.go": FIX_ORCH,
        "cmd/renet/fork.go": FIX_CMD,
    }


def _phases(**changes) -> dict:
    p = json.loads(json.dumps(FIX_PHASES))
    p.update(changes)
    return p


def controls_fired() -> list[str]:
    """Each plant against a scratch tree; returns the plants that did NOT behave. Any entry means no verdict on the real tree may be issued."""
    missed: list[str] = []

    def case(
        label: str, go: dict[str, str], phases: object, expect: str | None, ts: str = FIX_TS
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _fixture(tmp, go, phases, ts)
            try:
                result = scan(root)
            except CannotRunError:
                if expect != "cannot-run":
                    missed.append("%s: CANNOT RUN where a verdict was expected" % label)
                return
            if expect == "cannot-run":
                missed.append("%s: produced a verdict where CANNOT RUN was expected" % label)
            elif expect is None and result["findings"]:
                missed.append(
                    "%s: fired on a tree that must pass: %s" % (label, result["findings"])
                )
            elif expect is not None and not any(expect in f for f in result["findings"]):
                missed.append(
                    "%s: did not report %r (got %s)"
                    % (label, expect, result["findings"] or "nothing")
                )

    # CONTROL 0 first: the healthy fixture passes, or every red below is the fixture's doing. It also proves the negatives: a comment, a string literal, a progress reporter and the timer package itself contribute no id, and the constant, the multi-line Record and the method-value alias all resolve.
    case("CONTROL 0 healthy tree", _base_go(), FIX_PHASES, None)
    if missed:
        return missed

    go = _base_go()
    go["cmd/renet/new.go"] = 'package main\nfunc n() { timer.Start("brand_new_step") }\n'
    case("R1 unmapped renet step id", go, FIX_PHASES, "renet emits step `brand_new_step`")

    case(
        "R2 stale json id",
        _base_go(),
        _phases(plain=["sessions_end", "retired_step"]),
        "`retired_step` is an id no renet",
    )
    case(
        "R2 stale scene id",
        _base_go(),
        _phases(scenes=dict(FIX_PHASES["scenes"], gone="clone")),
        "`gone` is an id no renet",
    )

    go = _base_go()
    go["cmd/renet/fork.go"] = plant(FIX_CMD, '\to.mark(marker, 0, "h")\n', "")
    case(
        "R2 alias call removed: cutover_complete goes stale",
        go,
        FIX_PHASES,
        "`cutover_complete` is an id no renet",
    )

    go = _base_go()
    go["cmd/renet/fork.go"] = plant(FIX_CMD, "timer.Start(cmdCheckpoint)", "timer.Start(stepName)")
    case("R4 unresolvable argument", go, FIX_PHASES, "`stepName` is neither a string literal")

    go = _base_go()
    go["pkg/orchestration/up.go"] = plant(
        FIX_ORCH, 'o.Timer.Start("compose_up")', "o.Timer.Start(cmdCheckpoint)"
    )
    case(
        "R4 a constant from ANOTHER package does not resolve",
        go,
        _phases(scenes={k: v for k, v in FIX_PHASES["scenes"].items() if k != "compose_up"}),
        "`cmdCheckpoint` is neither",
    )

    case(
        "R3 both scene and plain",
        _base_go(),
        _phases(plain=["sessions_end", "cow_sync"]),
        "both a scene step",
    )
    case(
        "R3 duplicate plain",
        _base_go(),
        _phases(plain=["sessions_end", "sessions_end"]),
        "listed twice",
    )
    case(
        "R3 scene outside the union",
        _base_go(),
        _phases(scenes=dict(FIX_PHASES["scenes"], cow_sync="teleport")),
        "not a member of RunScene",
    )

    go = _base_go()
    go["cmd/renet/fork_test.go"] = 'package main\nfunc t() { timer.Start("test_only") }\n'
    case("negative: a _test.go file is not an emitter", go, FIX_PHASES, None)

    go = _base_go()
    go["vendor/x/y.go"] = 'package y\nfunc t() { timer.Start("vendored") }\n'
    case("negative: vendor is not renet's own source", go, FIX_PHASES, None)

    case(
        "anti-vacuity: no timer calls at all",
        {"cmd/renet/main.go": "package main\n"},
        _phases(scenes={}, plain=[]),
        "cannot-run",
    )
    case("anti-vacuity: no RunScene union", _base_go(), FIX_PHASES, "cannot-run", ts="export {};\n")
    case("anti-vacuity: json does not parse", _base_go(), "{not json", "cannot-run")
    with tempfile.TemporaryDirectory() as tmp:
        try:
            scan(tmp)
            missed.append("anti-vacuity: no renet checkout produced a verdict")
        except CannotRunError:
            pass
    return missed


def selftest() -> int:
    missed = controls_fired()
    if missed:
        print(
            "%s✗%s step-phase-coverage selftest: controls did not behave:" % (RED, NC),
            file=sys.stderr,
        )
        for m in missed:
            print("  %s" % m, file=sys.stderr)
        return 2
    print(
        "%s✓%s step-phase-coverage selftest: every plant fired and every negative control stayed silent"
        % (GREEN, NC)
    )
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--selftest", action="store_true", help="run the planted controls only")
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    print("step-phase-coverage: controls first, then the verdict")
    if selftest():
        print(
            "✗ instrument control failed; every verdict below would be meaningless", file=sys.stderr
        )
        return 2
    root = str(paths.repo_root())
    # The floors hold under a REDIACC_CI_ROOT override too: an override is a copy of the real renet sources (the gate test builds one), and a seam that lowered the floors would be a way to read a green over nothing.
    floors = (MIN_GO_FILES, MIN_CALLS, MIN_IDS)
    try:
        result = scan(root, floors)
    except CannotRunError as exc:
        print("%sCANNOT RUN%s step-phase-coverage: %s" % (YELLOW, NC, exc), file=sys.stderr)
        return EXIT_CANNOT_RUN
    if result["findings"]:
        print("%s✗%s renet step ids and %s disagree:" % (RED, NC, PHASES_REL), file=sys.stderr)
        for f in result["findings"]:
            print("  %s" % f, file=sys.stderr)
        print(
            "\n  The run block animates only ids in `scenes`; every other emitted id belongs in `plain`"
            " (agent/plans/PLAN-console-animations.md D1, D7).",
            file=sys.stderr,
        )
        return 1
    print(
        "%s✓%s step phase coverage: %d timer call(s) in %d Go file(s) emit %d distinct id(s);"
        " %s maps %d to a scene and lists %d plain; alias(es): %s (floors %d/%d/%d)"
        % (
            GREEN,
            NC,
            result["calls"],
            result["files"],
            result["ids"],
            PHASES_REL,
            result["scene_ids"],
            result["plain_ids"],
            ", ".join(result["aliases"]) or "none",
            floors[0],
            floors[1],
            floors[2],
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

"""wl_planpreflight: revalidate a plan against the current tree before its first box is worked (agent/plans/PLAN-plan-preflight.md, box PF3).

WHY. A plan is written against one tree and implemented against another. Other plans land in between, cited lines move, a dependency closes with boxes still open. Nothing re-read a plan when it became a PR's plan, so the first writer worked from a description of a world that no longer existed. This module COMPUTES what changed; it refuses nothing by itself.

LEAN FIRST, ENFORCEMENT WARNS (operator ruling 2026-10-23). The findings feed three callers that land later: the verb `worklist.py --plan-preflight` (PF4) prints them and writes the plan, `wl_planrec.plan_tick` (PF5) and CI P-A9 (PF6) read `revalidation_state`. A stale citation is a warning there, never a refusal; the only refusal this module expresses is `apply`'s, which declines to stamp `Revalidated:` over a plan the survey says is not ready.

THE PUBLIC API IS FROZEN HERE. PF4, PF5 and PF6 build on it in parallel, so a change to a name, a parameter or a returned field is a change to three other boxes. Every function takes the repository root first and, where it reads the plan, an optional `text` (the plan as it would be written; default: the file on disk). Paths are repository-relative POSIX strings.

    merge_base(root) -> str | None
        B: `git merge-base HEAD origin/main`, else `git merge-base HEAD main` (a clone
        with no remote). None when neither resolves.

    watched_paths(root, rel, text=None, graph=None) -> list[str]
        Git pathspecs whose change on main makes the plan stale: every fileline path
        cited outside fences, every backticked token that is a tracked file, the
        `Owns:` globs as `:(glob)<glob>`, and the plan files of its `Depends-On:`
        targets. The plan's own path and RENDER_PATHS are dropped (Design 3a), and
        when a glob is present they follow as `:(exclude)<path>`. Plain paths
        sorted first, then the globs, then the excludes.

    revalidation_state(root, rel, text=None, base=None) -> RevalidationState
        .state is one of MISSING, ORPHAN, STALE, FRESH, UNKNOWN (module constants).
        .base is B (or None), .sha the header's sha ("" when missing), .commits the
        full shas in `<sha>..B` that touch the watched paths, newest first (STALE
        only), .detail one human line. UNKNOWN means B is unresolvable; callers fail
        closed on it.

    survey(root, rel, text=None, base=None, rows=None) -> list[BoxSurvey]
        One entry per OPEN box (`wl_planrec.open_boxes`): .line (0-based index),
        .sig, .body, .row (the latest investigation row or None), .verdict ("" when
        no row), .current (B is an ancestor of the row's `head`).

    overlap(root, rel, text=None, base=None, since=None, cap=OVERLAP_CAP) -> Overlap
        Commits in `<since>..B` touching the watched paths, newest first, capped.
        `since` defaults to the `Revalidated:` sha when it is an ancestor of B, else
        the last commit on B that touched the plan. .since/.base/.total/.commits,
        each commit an OverlapCommit(sha, subject, plans) where `plans` lists the
        plan files that commit changed.

    dep_findings(root, rel, text=None, graph=None) -> list[DepFinding]
        One entry per `Depends-On:` edge plus queue-order warnings: .edge, .level
        (BLOCK, WARN or OK), .why. Completion is `check_plan_record.unfinished_why`
        over `check_plan_record.deps_graph`, never Status alone; queue order is
        `check_plan_record.promoted_dep_order` filtered to this plan. `graph` must be
        a deps_graph-shaped `wl_plandeps.Graph` when given.

    citation_report(root, rel, runner=None) -> CitationReport
        Runs `check_plan_citations.py --plan <rel> --json` (PF2's frozen contract) and
        splits it: .report (the JSON object), .blocking_unresolved,
        .blocking_drifted (blocking, no relocation), .relocations (blocking,
        relocatable), .error ("" when the instrument answered). `runner(argv, root)
        -> (rc, stdout, stderr)` replaces the subprocess in tests.

    refusals(surveyed, cites, deps) -> list[str]
        Why `--write` is refused, one line each; [] means `apply` may write.

    render_block(base, surveyed, cites, deps, ov, relocated, today) -> str
        The generated `<!-- preflight:begin -->` ... `<!-- preflight:end -->` section;
        its body is fenced, so its shas and paths are history to the citation gate
        and invisible to `watched_paths`.

    apply(root, rel, text, base, surveyed, cites, deps, ov, today) -> ApplyResult
        Pure text transform (reads nothing but the arguments): raises PreflightError
        when `refusals` is non-empty, when a relocation cannot be applied without
        changing a box signature, or when the header line would leave the window.
        Otherwise returns .text with `Revalidated: <today> @ <B[:12]>` (replaced in
        place, or inserted right after `Owns:`), each relocatable blocking fileline
        citation rewritten to its new line number, one `(preflight)` continuation
        line per current `partial` row, and the generated block after the header;
        .relocated lists (plan line, old token, new token). The caller writes it
        (`wl_planrec.write_atomic`) and refreshes the index; this module never writes.

    preflight(root, rel, text=None, runner=None) -> Preflight
        The five parts in one call, for the verb: .base, .state, .survey,
        .citations, .overlap, .deps, .refusals.

DEPARTURES THE PLAN FORCES (its Design section). A partial box's remainder goes on an indented `(preflight)` line, never into the box text, so the box signature and check:ci-plan-boxes G-A1 are untouched. `Revalidated:` records the merge base with origin/main, not HEAD, so a rebase-merge keeps it resolvable. Staleness counts only commits that landed on main (`<sha>..B`), so the branch's own implementation never makes its plan stale.

IMPORTS. Stdlib at import time. `wl_planrec`, `wl_plandeps`, `wl_planfile` and `wl_checks` (for `CITE_RE`, the citation shape every pointer reader shares) are imported lazily, as the hook's other plan modules do. The dependency helpers are loaded lazily from `.ci/scripts/quality/check_plan_record.py` by path, because the 2026-10-23 validation asked for those helpers and not a second Status-only rule; a load failure is a BLOCK finding, never a silent pass. The citation gate is a subprocess (Design departure 5). Reads no environment variable; the citation child gets `PLAN_CITATIONS_ROOT` only when the root is not this checkout.
"""

from __future__ import annotations

import dataclasses
import importlib
import importlib.util
import json
import os
import pathlib
import re
import subprocess
import sys

MISSING = "missing"
ORPHAN = "orphan"
STALE = "stale"
FRESH = "fresh"
UNKNOWN = "unknown"

BLOCK = "block"
WARN = "warn"
OK = "ok"

OVERLAP_CAP = 30
BEGIN = "<!-- preflight:begin -->"
END = "<!-- preflight:end -->"
PREFLIGHT_TAG = "(preflight)"
REMAINDER_MAX = 300
GIT_TIMEOUT = 120
CITATIONS_TIMEOUT = 600

# This file is `.claude/hooks/stop/wl_planpreflight.py`; the checkout holding the gates is three levels up.
CHECKOUT = pathlib.Path(__file__).resolve().parents[3]
QUALITY_REL = ".ci/scripts/quality"
CITATIONS_REL = QUALITY_REL + "/check_plan_citations.py"
RECORD_REL = QUALITY_REL + "/check_plan_record.py"
QUEUE_REL = "agent/plans/QUEUE.md"
# The files a tick or a preflight regenerates beside the plan (Design 3a): a main commit touching only these and the plan itself never makes a plan stale.
RENDER_PATHS = (
    "agent/INDEX.md",
    QUEUE_REL,
    ".ci/config/plan-boxes.json",
    "agent/ledgers/plan-investigation.jsonl",
)

BACKTICK_RE = re.compile(r"`([^`\s]+)`")
FENCE_RE = re.compile(r"^\s*(```|~~~)")
FILELINE_TOKEN_RE = re.compile(r"^(.*):(\d+)(?:-(\d+))?$")
PREFLIGHT_LINE_RE = re.compile(r"^\s+\(preflight\) ")
# What loading the gate by path can raise short of a bug in this file: a missing or broken module, an unreadable checkout.
_LOAD_ERRORS = (ImportError, OSError, AttributeError, ValueError, SyntaxError, RuntimeError)


class PreflightError(Exception):
    """`apply` declined to write, with the reasons as the message."""


@dataclasses.dataclass(frozen=True)
class RevalidationState:
    state: str
    base: str | None
    sha: str = ""
    commits: tuple[str, ...] = ()
    detail: str = ""


@dataclasses.dataclass(frozen=True)
class BoxSurvey:
    line: int
    sig: str
    body: str
    row: dict | None
    verdict: str
    current: bool


@dataclasses.dataclass(frozen=True)
class OverlapCommit:
    sha: str
    subject: str
    plans: tuple[str, ...] = ()


@dataclasses.dataclass(frozen=True)
class Overlap:
    since: str | None
    base: str | None
    total: int
    commits: tuple[OverlapCommit, ...] = ()


@dataclasses.dataclass(frozen=True)
class DepFinding:
    edge: str
    level: str
    why: str


@dataclasses.dataclass(frozen=True)
class CitationReport:
    report: dict
    blocking_unresolved: tuple[dict, ...] = ()
    blocking_drifted: tuple[dict, ...] = ()
    relocations: tuple[dict, ...] = ()
    error: str = ""


@dataclasses.dataclass(frozen=True)
class ApplyResult:
    text: str
    relocated: tuple[tuple[int, str, str], ...] = ()


@dataclasses.dataclass(frozen=True)
class Preflight:
    rel: str
    base: str | None
    state: RevalidationState
    survey: tuple[BoxSurvey, ...]
    citations: CitationReport
    overlap: Overlap
    deps: tuple[DepFinding, ...]
    refusals: tuple[str, ...]


# --------------------------------------------------------------------------- lazy siblings


def _rec():
    return importlib.import_module("wl_planrec")


def _deps():
    return importlib.import_module("wl_plandeps")


def _planfile():
    return importlib.import_module("wl_planfile")


def _record_gate():
    """`check_plan_record`, loaded by path from this checkout. Raises on failure; the caller turns that into a BLOCK."""
    name = "check_plan_record"
    if name in sys.modules:
        return sys.modules[name]
    helper = CHECKOUT / ".claude" / "rediacc_hooks" / "syspath.py"
    hop_spec = importlib.util.spec_from_file_location("_rediacc_syspath", helper)
    if hop_spec is None or hop_spec.loader is None:
        raise ImportError("cannot load %s" % helper)
    syspath = importlib.util.module_from_spec(hop_spec)
    hop_spec.loader.exec_module(syspath)
    syspath.on_sys_path(CHECKOUT / QUALITY_REL)
    spec = importlib.util.spec_from_file_location(name, str(CHECKOUT / RECORD_REL))
    if spec is None or spec.loader is None:
        raise ImportError("cannot load %s" % RECORD_REL)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    try:
        spec.loader.exec_module(mod)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return mod


# --------------------------------------------------------------------------- git


def _git(root, *args) -> tuple[int, str]:
    try:
        r = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return 1, ""
    return r.returncode, r.stdout


def _commit(root, ref: str) -> str | None:
    rc, out = _git(root, "rev-parse", "--verify", "--quiet", ref + "^{commit}")
    return out.strip() if rc == 0 and out.strip() else None


def _is_ancestor(root, older: str, newer: str) -> bool:
    rc, _ = _git(root, "merge-base", "--is-ancestor", older, newer)
    return rc == 0


def merge_base(root) -> str | None:
    for ref in ("origin/main", "main"):
        if _commit(root, ref) is None:
            continue
        rc, out = _git(root, "merge-base", "HEAD", ref)
        if rc == 0 and out.strip():
            return out.strip()
    return None


def _log(root, rng: str, pathspecs: list[str]) -> list[tuple[str, str]] | None:
    """[(sha, subject)] newest first for `rng` restricted to `pathspecs`; [] when there is nothing to restrict to, None when `git log` itself failed (a timeout, a broken range), which no caller may read as "no commits"."""
    if not pathspecs:
        return []
    rc, out = _git(root, "log", "--format=%H%x09%s", rng, "--", *pathspecs)
    if rc != 0:
        return None
    rows = []
    for line in out.splitlines():
        sha, _, subject = line.partition("\t")
        if sha:
            rows.append((sha, subject))
    return rows


# --------------------------------------------------------------------------- the plan's text


def _read(root, rel, text):
    if text is not None:
        return text
    return (pathlib.Path(root) / rel).read_text(encoding="utf-8", errors="replace")


def _unfenced(text: str):
    """(index, line) for every line outside a fenced block; the fence lines themselves are skipped."""
    fenced = False
    for i, raw in enumerate(text.splitlines()):
        if FENCE_RE.match(raw):
            fenced = not fenced
            continue
        if not fenced:
            yield i, raw


def _safe_rel(path: str) -> bool:
    return bool(path) and not path.startswith("/") and ".." not in path.split("/")


def _tracked(root) -> set[str]:
    rc, out = _git(root, "ls-files", "-z")
    return set(out.split("\0")) - {""} if rc == 0 else set()


def _dep_rels(root, rel, graph) -> list[str]:
    dmod = _deps()
    graph = graph if graph is not None else dmod.Graph.load(root)
    out = []
    for edge in graph.edges(rel):
        target = graph.resolve(str(edge))
        if target.rel and target.rel != rel:
            out.append(target.rel)
    return out


def watched_paths(root, rel, text=None, graph=None) -> list[str]:
    text = _read(root, rel, text)
    cite_re = importlib.import_module("wl_checks").CITE_RE
    tracked = _tracked(root)
    paths = {rel}
    for _i, raw in _unfenced(text):
        for m in cite_re.finditer(raw):
            if _safe_rel(m.group(1)):
                paths.add(m.group(1))
        for m in BACKTICK_RE.finditer(raw):
            tok = m.group(1)
            fl = FILELINE_TOKEN_RE.match(tok)
            if fl:
                tok = fl.group(1)
            if tok in tracked:
                paths.add(tok)
    owns = _deps().parse_header(text).owns
    globs = {":(glob)%s" % g for g in (owns.globs if owns else ()) if _safe_rel(g)}
    paths.update(_dep_rels(root, rel, graph))
    # Design 3a: every merged tick rewrites the plan and its renders on main, so they never count. A glob can still reach them, hence the exclude pathspecs; they ride only beside a glob, because an exclude-only pathspec list means "everything else".
    unwatched = {rel, *RENDER_PATHS}
    paths -= unwatched
    excludes = sorted(":(exclude)%s" % p for p in unwatched) if globs else []
    return sorted(paths) + sorted(globs) + excludes


# --------------------------------------------------------------------------- freshness


def revalidation_state(root, rel, text=None, base=None) -> RevalidationState:
    text = _read(root, rel, text)
    base = base or merge_base(root)
    if not base:
        return RevalidationState(
            UNKNOWN, None, detail="the merge base with origin/main (or main) does not resolve"
        )
    stamp = _deps().parse_header(text).revalidated
    if stamp is None:
        return RevalidationState(MISSING, base, detail="no valid `Revalidated:` header")
    full = _commit(root, stamp.sha)
    if full is None or not _is_ancestor(root, full, base):
        return RevalidationState(
            ORPHAN,
            base,
            stamp.sha,
            detail="Revalidated sha %s is not an ancestor of the merge base %s"
            % (stamp.sha, base[:12]),
        )
    hits = _log(root, "%s..%s" % (full, base), watched_paths(root, rel, text))
    if hits is None:
        return RevalidationState(
            UNKNOWN,
            base,
            stamp.sha,
            detail="`git log` over %s..%s failed" % (stamp.sha[:12], base[:12]),
        )
    commits = tuple(sha for sha, _s in hits)
    if commits:
        return RevalidationState(
            STALE,
            base,
            stamp.sha,
            commits,
            "%d commit(s) on main touched the watched paths since %s"
            % (len(commits), stamp.sha[:12]),
        )
    return RevalidationState(
        FRESH, base, stamp.sha, detail="no main commit touched the watched paths"
    )


# --------------------------------------------------------------------------- survey


def survey(root, rel, text=None, base=None, rows=None) -> list[BoxSurvey]:
    text = _read(root, rel, text)
    rec = _rec()
    base = base or merge_base(root)
    rows = rec.read_investigations(root) if rows is None else rows
    out = []
    for i, _line, body, sig in rec.open_boxes(text):
        row = rec.investigation_for(root, rel, sig, rows)
        verdict = str((row or {}).get("verdict") or "").strip().lower()
        head = str((row or {}).get("head") or "")
        current = bool(row and base and head and _is_ancestor(root, base, head))
        out.append(BoxSurvey(i, sig, body, row, verdict, current))
    return out


# --------------------------------------------------------------------------- overlap


def _plans_changed(root, sha: str) -> tuple[str, ...]:
    rc, out = _git(root, "show", "--name-only", "--format=", sha, "--", "agent")
    if rc != 0:
        return ()
    return tuple(
        p
        for p in out.splitlines()
        if p.rsplit("/", 1)[-1].startswith("PLAN-") and p.endswith(".md")
    )


def overlap(root, rel, text=None, base=None, since=None, cap=OVERLAP_CAP) -> Overlap:
    text = _read(root, rel, text)
    base = base or merge_base(root)
    if not base:
        return Overlap(None, None, 0)
    if since is None:
        stamp = _deps().parse_header(text).revalidated
        full = _commit(root, stamp.sha) if stamp else None
        if full and _is_ancestor(root, full, base):
            since = full
        else:
            rc, out = _git(root, "log", "-1", "--format=%H", base, "--", rel)
            since = out.strip() if rc == 0 and out.strip() else None
    if not since:
        return Overlap(None, base, 0)
    hits = _log(root, "%s..%s" % (since, base), watched_paths(root, rel, text))
    if hits is None:
        # A failed `git log` is unknown, not "no commits": the same shape as an unresolved `since`.
        return Overlap(None, base, 0)
    commits = tuple(OverlapCommit(sha, subj, _plans_changed(root, sha)) for sha, subj in hits[:cap])
    return Overlap(since, base, len(hits), commits)


# --------------------------------------------------------------------------- dependencies


def _queue_warnings(root, rel, graph, gate) -> list[DepFinding]:
    try:
        qtext = (pathlib.Path(root) / QUEUE_REL).read_text(encoding="utf-8")
    except OSError:
        return []
    _new, said = gate.promoted_dep_order(root, qtext, graph)
    needle = "ahead of %s" % rel.rsplit("/", 1)[-1]
    return [DepFinding(QUEUE_REL, WARN, line.strip()) for line in said if needle in line]


def _edge_finding(root, edge, graph, gate) -> DepFinding:
    dmod, pfile = _deps(), _planfile()
    token = str(edge)
    t = graph.resolve(token)
    if t.state in (dmod.DANGLING, dmod.AMBIGUOUS, dmod.WITHDRAWN):
        return DepFinding(token, BLOCK, "%s: %s" % (t.state, t.detail or "no plan"))
    if edge.task and t.state == dmod.LIVE:
        tail = (": " + t.detail) if t.detail else ""
        return DepFinding(token, BLOCK, "task %s is not ticked with evidence%s" % (edge.task, tail))
    if edge.task:
        return DepFinding(token, OK, "task %s is ticked" % edge.task)
    if t.rel not in graph.plans:
        return DepFinding(token, OK, t.detail or "finished (tombstone)")
    why = gate.unfinished_why(root, graph, t.rel)
    status = graph.plans[t.rel].header.status
    done = status in dmod.finished_states() or status == dmod.REMOVED_STATUS
    if done and why:
        full = (pathlib.Path(root) / t.rel).read_text(encoding="utf-8", errors="replace")
        n_open = len(pfile.plan_boxes(full)[0])
        if pfile.ruling_line(full):
            return DepFinding(
                token, OK, "Status %s, %d open box(es) under a `Ruling:` line" % (status, n_open)
            )
        return DepFinding(
            token, WARN, "Status %s over %d open box(es) and no `Ruling:` line" % (status, n_open)
        )
    if done:
        return DepFinding(token, OK, "Status %s" % status)
    if why:
        return DepFinding(token, BLOCK, "unfinished: %s" % why)
    return DepFinding(
        token, WARN, "every box ticked under Status %s; close it" % (status or "(none)")
    )


def dep_findings(root, rel, text=None, graph=None) -> list[DepFinding]:
    text = _read(root, rel, text)
    dep = _deps().parse_header(text).depends
    if dep is None or not dep.edges:
        return []
    try:
        gate = _record_gate()
        graph = graph if graph is not None else gate.deps_graph(root)
    except _LOAD_ERRORS as exc:
        return [
            DepFinding(str(e), BLOCK, "dependency helpers unavailable: %s" % exc) for e in dep.edges
        ]
    out = [_edge_finding(root, edge, graph, gate) for edge in dep.edges]
    out.extend(_queue_warnings(root, rel, graph, gate))
    return out


# --------------------------------------------------------------------------- citations


def _run(argv, root):
    same = pathlib.Path(root).resolve() == CHECKOUT
    try:
        r = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=CITATIONS_TIMEOUT,
            check=False,
            env=None if same else {**os.environ, "PLAN_CITATIONS_ROOT": str(root)},
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return 2, "", str(exc)
    return r.returncode, r.stdout, r.stderr


def citation_report(root, rel, runner=None) -> CitationReport:
    argv = [sys.executable, str(CHECKOUT / CITATIONS_REL), "--plan", rel, "--json"]
    rc, out, err = (runner or _run)(argv, root)
    if rc not in (0, 1):
        tail = (err or "").strip().splitlines()[-1:] or ["no output"]
        return CitationReport({}, error="check_plan_citations --plan exited %d: %s" % (rc, tail[0]))
    try:
        report = json.loads(out)
        unresolved = list(report["unresolved"])
        drifted = list(report["drifted"])
    except (ValueError, KeyError, TypeError) as exc:
        return CitationReport(
            {}, error="check_plan_citations --plan printed no contract JSON: %s" % exc
        )
    return CitationReport(
        report,
        tuple(u for u in unresolved if u.get("blocking")),
        tuple(d for d in drifted if d.get("blocking") and d.get("relocate_to") is None),
        tuple(d for d in drifted if d.get("blocking") and d.get("relocate_to") is not None),
    )


# --------------------------------------------------------------------------- verdict


def refusals(surveyed, cites, deps) -> list[str]:
    out = []
    for b in surveyed:
        if not b.current:
            out.append(
                "box %s has no current investigation row (%s): %s"
                % (b.sig, "none" if b.row is None else "taken before the merge base", b.body[:80])
            )
        elif b.verdict == "present":
            out.append(
                "box %s has a `present` row and is still open; tick it first: %s"
                % (b.sig, b.body[:80])
            )
    if cites.error:
        out.append(cites.error)
    out.extend(
        "line %d: unresolved %s `%s` -- %s"
        % (u["line"], u.get("kind", "?"), u["token"], u.get("why", ""))
        for u in cites.blocking_unresolved
    )
    out.extend(
        "line %d: drifted `%s` with nowhere to relocate" % (d["line"], d["token"])
        for d in cites.blocking_drifted
    )
    out.extend("dependency %s blocks: %s" % (d.edge, d.why) for d in deps if d.level == BLOCK)
    return out


# --------------------------------------------------------------------------- apply


def render_block(base, surveyed, cites, deps, ov, relocated, today) -> str:
    counts: dict[str, int] = {}
    for b in surveyed:
        key = b.verdict if b.current and b.verdict else "uncovered"
        counts[key] = counts.get(key, 0) + 1
    tally = ", ".join("%s %d" % kv for kv in sorted(counts.items())) or "none"
    shown = " (first %d shown)" % len(ov.commits) if ov.total > len(ov.commits) else ""
    lines = [
        BEGIN,
        "```text",
        "preflight %s @ %s" % (today, (base or "?")[:12]),
        "open boxes: %d (%s)" % (len(surveyed), tally),
        "citations: %d unresolved, %d drifted, %d relocated"
        % (
            len(cites.report.get("unresolved", [])),
            len(cites.report.get("drifted", [])),
            len(relocated),
        ),
    ]
    lines.extend(
        "  relocated plan line %d: %s line %s -> %s"
        % (n, old.rsplit(":", 1)[0], old.rsplit(":", 1)[1], new.rsplit(":", 1)[1])
        for n, old, new in relocated
    )
    lines.append("overlap since %s: %d commit(s)%s" % ((ov.since or "none")[:12], ov.total, shown))
    for c in ov.commits:
        lines.append("  %s %s" % (c.sha[:12], c.subject[:100]))
        lines.extend("    plan %s" % p for p in c.plans)
    lines.append("dependencies: %d" % len(deps))
    lines.extend("  %s %s -- %s" % (d.level, d.edge, d.why) for d in deps)
    lines += ["```", END]
    return "\n".join(lines) + "\n"


def _relocate_line(raw: str, token: str, new_first: int) -> tuple[str, str] | None:
    """(new line, new token) with the first exact occurrence of `token` renumbered, or None when the line does not carry it."""
    m = FILELINE_TOKEN_RE.match(token)
    if not m:
        return None
    path, first, last = m.group(1), int(m.group(2)), m.group(3)
    new_tok = "%s:%d" % (path, new_first)
    if last is not None:
        new_tok += "-%d" % (new_first + int(last) - first)
    pat = re.compile(r"(?<![\w./-])%s(?![\d-])" % re.escape(token))
    if not pat.search(raw):
        return None
    return pat.sub(new_tok.replace("\\", "\\\\"), raw, count=1), new_tok


def _box_sig_of(rec, raw: str) -> str | None:
    m = rec.BOX_LINE_RE.match(raw.rstrip("\r\n"))
    return rec.box_sig(re.sub(r"[*_`]+", "", m.group(2)).strip()) if m else None


def _block_bounds(lines):
    starts = [i for i, ln in enumerate(lines) if ln.rstrip("\r\n") == BEGIN]
    if not starts:
        return None
    ends = [i for i in range(starts[0], len(lines)) if lines[i].rstrip("\r\n") == END]
    return (starts[0], ends[0]) if ends else None


def _relocate(rec, rel, lines, cites):
    relocated = []
    for d in sorted(cites.relocations, key=lambda x: (x["line"], x["token"])):
        idx = d["line"] - 1
        raw = lines[idx] if 0 <= idx < len(lines) else ""
        got = _relocate_line(raw, d["token"], int(d["relocate_to"]))
        if got is None:
            raise PreflightError(
                "%s: line %d no longer carries `%s`; re-run the preflight"
                % (rel, d["line"], d["token"])
            )
        new, new_tok = got
        if _box_sig_of(rec, raw) != _box_sig_of(rec, new):
            raise PreflightError(
                "%s: relocating `%s` on line %d would change that box's signature; re-cite it "
                "on a continuation line by hand" % (rel, d["token"], d["line"])
            )
        lines[idx] = new
        relocated.append((d["line"], d["token"], new_tok))
    return relocated


def _partial_lines(rec, lines, surveyed, today):
    for b in sorted(surveyed, key=lambda s: -s.line):
        if not (b.current and b.verdict == "partial"):
            continue
        note = " ".join(str((b.row or {}).get("note") or "").split())[:REMAINDER_MAX]
        indent = len(lines[b.line]) - len(lines[b.line].lstrip())
        new_line = "%s%s %s partial: %s\n" % (
            " " * (indent + 4),
            PREFLIGHT_TAG,
            today,
            note or "(no note)",
        )
        plain = [ln.rstrip("\r\n") for ln in lines]
        slot = rec._evidence_slot(plain, b.line)
        existing = next(
            (j for j in range(b.line + 1, slot) if PREFLIGHT_LINE_RE.match(plain[j])), None
        )
        if existing is not None:
            lines[existing] = new_line
        else:
            lines.insert(slot, new_line)


def apply(root, rel, text, base, surveyed, cites, deps, ov, today) -> ApplyResult:
    del root  # the transform is pure; the parameter keeps the API's root-first shape
    why = refusals(surveyed, cites, deps)
    if why:
        raise PreflightError("%s: --write refused:\n  %s" % (rel, "\n  ".join(why)))
    if not base:
        raise PreflightError("%s: the merge base does not resolve" % rel)
    rec, dmod = _rec(), _deps()
    lines = text.splitlines(keepends=True)
    if lines and not lines[-1].endswith(("\n", "\r")):
        lines[-1] += "\n"
    # Relocations first: in-line edits, so every line number the report gave stays valid.
    relocated = _relocate(rec, rel, lines, cites)
    _partial_lines(rec, lines, surveyed, today)
    block = render_block(base, surveyed, cites, deps, ov, relocated, today)
    bounds = _block_bounds(lines)
    if bounds:
        lines[bounds[0] : bounds[1] + 1] = [block]
    else:
        end = dmod.header_block_end(lines)
        lines[end:end] = ["\n", block]
    out = "".join(lines)
    header = dmod.parse_header(out)
    field = header.get(dmod.REVALIDATED)
    value = "%s: %s @ %s\n" % (dmod.REVALIDATED, today, base[:12])
    lines = out.splitlines(keepends=True)
    if field is not None:
        lines[field.lineno - 1] = value
    else:
        owns = header.get(dmod.OWNS)
        lines.insert(owns.lineno if owns is not None else dmod.header_block_end(lines), value)
    out = "".join(lines)
    got = dmod.parse_header(out).revalidated
    if got is None or got.sha != base[:12]:
        raise PreflightError(
            "%s: `Revalidated:` would land outside the %d-line header window; shorten the "
            "header above `Owns:`" % (rel, dmod.X_HEADER_LINES)
        )
    return ApplyResult(out, tuple(relocated))


# --------------------------------------------------------------------------- the bundle


def preflight(root, rel, text=None, runner=None) -> Preflight:
    text = _read(root, rel, text)
    base = merge_base(root)
    surveyed = survey(root, rel, text, base)
    cites = citation_report(root, rel, runner)
    deps = dep_findings(root, rel, text)
    why = refusals(surveyed, cites, deps)
    if not base:
        why.insert(0, "the merge base with origin/main (or main) does not resolve")
    return Preflight(
        rel,
        base,
        revalidation_state(root, rel, text, base),
        tuple(surveyed),
        cites,
        overlap(root, rel, text, base),
        tuple(deps),
        tuple(why),
    )

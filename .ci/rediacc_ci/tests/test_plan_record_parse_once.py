"""`check_plan_record.py --rendered-only` parses each plan once and builds its RF graph once, and says exactly what it said before it did.

NEW TEST, NOT A PORT, so there is no `.ci/scripts/test/gates/test-*.sh` named here.

THE COST IT PINS. Before 2026-11-19 one `--rendered-only` run took about 12 s idle and 26 s of CPU: RF asked `rf_context` about each of 32 fully ticked plans, and each call built a fresh `wl_plandeps.Graph` (every plan re-read and its header re-parsed, 21,284 `parse_header` calls), re-judged every task edge on it, and re-decoded the whole investigations ledger once per task edge (about 910k `json.loads`). The fix shares one graph per RF pass (`lazy_deps_graph`), reads the ledger once per graph (`Graph._present`), and memoizes the two pure text parsers (`wl_plandeps.parse_header` under the default specs, `wl_planfid.plan_tasks`).

THE TWO HALVES. `test_*_parsed_once_*` counts the work on the real tree, and each count has a control that bypasses its cache and must see the count rise, so a counter that cannot see a bypass fails the test rather than passing it. `test_*_identical_*` compares the cached answers with the uncached ones on the real tree, so the speed-up cannot have changed a verdict.
"""

import collections
import importlib.util
import pathlib
import sys

import pytest

from rediacc_ci import paths

GATE = paths.from_root(".ci", "scripts", "quality", "check_plan_record.py")
ROOT = paths.repo_root()
# How many plans the fresh-graph comparison judges: each fresh graph is the pre-fix cost, so the sample is small and chosen to hold real dependents.
FRESH_SAMPLE = 3


@pytest.fixture(scope="module")
def cpr():
    with pytest.MonkeyPatch.context() as mp:
        mp.delenv("PLAN_RECORD_ROOT", raising=False)
        # The gate's own directory carries `_cipath`, the hop every gate there imports first.
        paths.on_sys_path(GATE.parent)
        spec = importlib.util.spec_from_file_location("check_plan_record_parse_once", GATE)
        assert spec is not None
        assert spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    return mod


def _modules():
    return sys.modules["wl_plandeps"], sys.modules["wl_planfid"], sys.modules["wl_planrec"]


def _clear(deps, fid):
    deps._parse_default.cache_clear()
    fid._plan_tasks.cache_clear()


class _Counts:
    """Counting wrappers over the loads the fix made single, installed with `monkeypatch`."""

    def __init__(self, monkeypatch, cpr):
        deps, _fid, rec = _modules()
        self.headers: collections.Counter[str] = collections.Counter()
        self.graphs = 0
        self.ledger_reads = 0
        self.graph_objects = 0
        real_init = deps.Graph.__init__
        real_parse, real_graph, real_read = (
            deps._parse_header,
            cpr.deps_graph,
            rec.read_investigations,
        )

        def parse(text, specs):
            self.headers[text] += 1
            return real_parse(text, specs)

        def graph(root):
            self.graphs += 1
            return real_graph(root)

        def read(root):
            self.ledger_reads += 1
            return real_read(root)

        def init(graph_self, *args, **kwargs):
            self.graph_objects += 1
            real_init(graph_self, *args, **kwargs)

        monkeypatch.setattr(deps.Graph, "__init__", init)
        monkeypatch.setattr(deps, "_parse_header", parse)
        monkeypatch.setattr(cpr, "deps_graph", graph)
        monkeypatch.setattr(rec, "read_investigations", read)


def _depended_on(cpr, graph):
    """Plans some required plan names as a prerequisite, most-named first: `rf_context` has something to say about each."""
    named: collections.Counter[str] = collections.Counter()
    for r in graph.required():
        for target, _via in cpr.plan_prereqs(graph, r, {})[0]:
            named[target] += 1
    return [rel for rel, _n in named.most_common()]


def test_rendered_only_parses_each_plan_once_and_builds_one_rf_graph(cpr, monkeypatch, capsys):
    deps, fid, _rec = _modules()
    _clear(deps, fid)
    counts = _Counts(monkeypatch, cpr)
    rc = cpr.rendered_only(ROOT)
    out = capsys.readouterr()
    assert rc in (0, 1), out.err
    assert counts.headers, "no header was parsed: the counter is not on the path the gate takes"
    twice = {t[:60]: n for t, n in counts.headers.items() if n > 1}
    assert not twice, "plan texts parsed more than once: %r" % twice
    # One graph for RQ-DEPS (`promoted_dep_problems`) and at most one for the whole RF pass, which builds it only when some plan is fully ticked.
    assert 1 <= counts.graphs <= 2, counts.graphs
    # Every `Graph` reads the ledger at most once, whoever built it (`wl_planqueue.live_plans` builds its own).
    assert counts.ledger_reads <= counts.graph_objects, (counts.ledger_reads, counts.graph_objects)


def test_control_a_bypassed_header_cache_is_counted(cpr, monkeypatch):
    deps, fid, _rec = _modules()
    _clear(deps, fid)
    counts = _Counts(monkeypatch, cpr)
    monkeypatch.setattr(deps, "_parse_default", deps._parse_default.__wrapped__)
    deps.Graph.load(ROOT)
    deps.Graph.load(ROOT)
    assert counts.headers, "the counter saw no parse at all"
    assert max(counts.headers.values()) >= 2, (
        "a bypassed cache parsed every text once: the counter is blind"
    )


def test_control_a_per_plan_graph_and_per_edge_ledger_read_are_counted(cpr, monkeypatch):
    deps, fid, _rec = _modules()
    _clear(deps, fid)
    counts = _Counts(monkeypatch, cpr)
    shared = cpr.deps_graph(ROOT)
    rels = _depended_on(cpr, shared)[:2]
    assert len(rels) == 2, "the tree has fewer than two depended-on plans to drive the control with"
    counts.graphs = 0
    for rel in rels:
        cpr.rf_context(ROOT, rel)
    assert counts.graphs == 2, (
        "two rf_context calls without a shared graph built %d" % counts.graphs
    )
    # The ledger half: one graph asked twice reads the ledger once, and the same two questions with the remembered rows dropped read it twice.
    graph = cpr.deps_graph(ROOT)
    reads = counts.ledger_reads
    graph._present("agent/plans/PLAN-x.md", "deadbeef")
    graph._present("agent/plans/PLAN-x.md", "deadbeef")
    assert counts.ledger_reads - reads == 1, counts.ledger_reads - reads
    reads = counts.ledger_reads
    for _ in range(2):
        graph._investigations = None
        graph._present("agent/plans/PLAN-x.md", "deadbeef")
    assert counts.ledger_reads - reads == 2, (
        "a per-call ledger read was not counted: the counter is blind"
    )


def test_cached_rf_and_task_verdicts_are_identical_to_fresh_ones(cpr):
    deps, _fid, rec = _modules()
    shared = cpr.deps_graph(ROOT)
    rels = _depended_on(cpr, shared)[:FRESH_SAMPLE]
    assert rels, "no plan in the tree is anyone's prerequisite: nothing to compare"
    said = []
    for rel in rels:
        got = cpr.rf_context(ROOT, rel, shared)
        assert got == cpr.rf_context(ROOT, rel), rel
        said.append(got)
    assert any(said), "every sampled rf_context was empty: the comparison judged nothing"
    # Every task verdict the shared graph reached, against the ledger read afresh for that one box.
    for r in shared.required():
        cpr.plan_prereqs(shared, r, {})
    for (rel, _task), verdict in shared._tasks.items():
        if verdict.box is None or not verdict.box.done or verdict.box.ticked:
            continue
        row = rec.investigation_for(ROOT, rel, verdict.box.sig)
        present = bool(row) and str(row.get("verdict") or "").strip().lower() == "present"
        assert (verdict.state == deps.TASK_DONE) == present, (rel, verdict.box.sig)
    # Only a box ticked without a `(ticked)` line consults the ledger, so the loop above may have no subject on a tidy tree; the edges themselves must exist.
    assert shared._tasks, "the shared graph judged no task edge"


@pytest.mark.usefixtures("cpr")
def test_memoized_parsers_are_identical_to_the_uncached_ones_on_every_plan():
    deps, fid, _rec = _modules()
    texts = [
        path.read_text(encoding="utf-8", errors="replace")
        for folder in deps.PLAN_DIRS
        for path in sorted((ROOT / folder).glob("PLAN-*.md"))
    ]
    assert len(texts) >= 20, "the plan glob found %d plan(s)" % len(texts)
    for text in texts:
        assert deps.parse_header(text) == deps._parse_header(text, deps.FIELD_SPECS)
        assert fid.plan_tasks(text) == list(fid._plan_tasks.__wrapped__(text))
    # A caller that edits its copy cannot change the next caller's answer.
    first = deps.parse_header(texts[0])
    first.fields["Injected"] = None
    assert "Injected" not in deps.parse_header(texts[0]).fields
    tasks = fid.plan_tasks(texts[0])
    tasks.append("injected")
    assert "injected" not in fid.plan_tasks(texts[0])


@pytest.mark.usefixtures("cpr")
def test_a_failed_ledger_read_is_not_remembered(monkeypatch, tmp_path):
    deps, _fid, rec = _modules()
    graph = deps.Graph({}, "", pathlib.Path(tmp_path))
    calls = []

    def boom(root):
        calls.append(root)
        raise OSError("ledger unreadable")

    monkeypatch.setattr(rec, "read_investigations", boom)
    assert graph._present("agent/plans/PLAN-x.md", "deadbeef") is False
    assert graph._present("agent/plans/PLAN-x.md", "deadbeef") is False
    assert len(calls) == 2, "a read that raised was cached and hid the second failure"
    assert graph._investigations is None

"""wl_boxready: which open `[writer]` boxes a writer could start right now, and the IDLE CAPACITY block that names them (agent/plans/PLAN-idle-writer-capacity.md D1, D4, D5). There is no writer limit (agent/plans/PLAN-unlimited-writers.md), so the block counts no slots.

WHY. On 2026-11-09 the Stop hook printed that no queued plan was eligible for a free writer for hours while 17 of the then 25 writers' worth of capacity sat idle and PLAN-enterprise-isolation.md had `[writer]` boxes a writer could take. The plan picker of the time worked in whole plans and its ceiling counted live-only plans; nothing looked at boxes. The operator ruled (2026-11-09, R1-R4): a block that names the ready boxes and the spawn command, never an auto-spawn; only boxes explicitly tagged `[writer]` count; a box's own `Depends on:` line judges it, and a plan-level edge gates only the boxes that state none.

THE TAG GRAMMAR LIVES HERE, ONCE. The first bracketed tag after a box's id (`S2 [writer] ...`, `V1 [live, post-merge] ...`), split into lowercase words. `plan_gate.writer_startable` reads the same functions, so the two readings of "a writer can do this box" cannot drift. The grammar functions import nothing outside the standard library; `post_merge` imports `wl_planenforce` on first use and calls its `after_merge(line)`.

READY (D4). An open box is ready when it is writer-tagged and not post-merge; its plan is not held, not finished and has no `Writers: none` header; `wl_plandeps.Graph.box_blockers` finds nothing unresolved, where a LIVE plan-level edge is cleared for a writer box when the prerequisite's remaining open boxes (or the one box a task edge names) are all non-writer or post-merge, because a writer box builds on the prerequisite's code and code is writer work (an untagged open box of the prerequisite still holds it, failing closed); no open, deferred or leased worklist item names the plan and the box; and its `Owns:` line overlaps no box in flight, no other plan a live writer serves, and no box named before it.

NEEDS (agent/plans/PLAN-push-decoupling.md D3.3). A box's `Needs:` sub-line, read through `wl_plandeps.box_needs` (stated, else derived from a valid `GitHub-only:` or `Local-route:` tag), decides what else the box waits for: `none` (and a box that states none and derives none) is ready with no receipt and no push; `verified-vmcheck` once `rediacc_ci.proof.vm_tier.admit` admits HEAD's tree; `bench-deploy` once a clean bench deploy record (`.ci/cache/live-deploys/bench-<region>.json`) carries HEAD's tree or HEAD's `private/account` pointer; `pushed-head` once HEAD is on its upstream. A malformed value is held (LP8 names it). The three probes are `NeedsProbe` fields, built once per `ready_boxes` call and asked only for a box that needs them; a probe that cannot answer answers no, so a box is held rather than started early.

NEVER RAISES INTO A STOP from the grammar; `ready_boxes` and `idle_capacity_text` may raise, and the hook's arm reports that as a hook bug.
"""

from __future__ import annotations

import dataclasses
import functools
import importlib.util
import json
import os
import pathlib
import re
import subprocess
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

# The first bracketed tag after the box's id, on a raw box line or a parsed body. `- [ ] V1 [live] x`, `V1 [live] x`, `- [ ] [live] x` all read `live`; a box whose second token is not a bracket has no tag.
TAG_RE = re.compile(r"^\s*(?:[-*+]\s+\[[ xX?>]\]\s+)?(?:\*\*)?(?:[^\s\[]+\s+)?\[([^\]\n]{1,60})\]")
WRITER = "writer"
POST_MERGE = "post-merge"
# A tag word that names work no writer agent does: a live system, the operator, the lead, a machine or fleet, a drill, a date.
NON_WRITER_WORDS = frozenset(
    {"live", "operator", "lead", "hostinger", "fleet", "ops", "drill", "deadline", "bench", "local"}
)
# `Writers: none -- <reason>` in a plan header: no open box of it is a writer's.
WRITERS_NONE_RE = re.compile(r"^Writers:\s*none\b", re.IGNORECASE | re.MULTILINE)
_BULLET_RE = re.compile(r"^\s*[-*+]\s+\[[ xX?>]\]\s+")
_OWNS_LINE_RE = re.compile(r"^\s*Owns:\s*(.+?)\s*$", re.MULTILINE)
# How many boxes the block lists before it says "and N more".
LIST_MAX = 10


def tag_words(line: str) -> tuple[str, ...]:
    """The lowercase words of the box's first bracketed tag, () when it has none."""
    m = TAG_RE.match(re.sub(r"[`]+", "", line or ""))
    if not m:
        return ()
    return tuple(w for w in re.split(r"[,\s/]+", m.group(1).strip().lower()) if w)


def writer_tagged(line: str) -> bool:
    """True when the box is explicitly tagged `[writer]` (ruling R3)."""
    return WRITER in tag_words(line)


def non_writer(line: str) -> bool:
    """True when the box's tag names work no writer does (`[live]`, `[operator window]`, `[hostinger rollout]`, ...) and does not also say `writer`."""
    words = tag_words(line)
    return WRITER not in words and any(w in NON_WRITER_WORDS for w in words)


def post_merge(line: str) -> bool:
    """True when the box waits for the merge: a `post-merge` tag word, or its own `Depends on:` clause naming a merge (`wl_planenforce.AFTER_MERGE`)."""
    if POST_MERGE in tag_words(line):
        return True
    try:
        import wl_planenforce
    except ImportError:
        return False
    return wl_planenforce.after_merge(line)


def startable(line: str) -> bool:
    """True when a writer could do the box before the merge as far as its tags say: neither non-writer nor post-merge. An untagged box is startable."""
    return not non_writer(line) and not post_merge(line)


@dataclasses.dataclass(frozen=True)
class NeedsProbe:
    """The three facts a `Needs:` value waits on, each a no-argument callable answering True when it holds: a VERIFIED vm:check receipt admits HEAD's tree (`vmcheck`), bench carries the branch's code (`bench`), HEAD is on its upstream (`pushed`)."""

    vmcheck: Callable[[], bool]
    bench: Callable[[], bool]
    pushed: Callable[[], bool]


BENCH_RECORD_DIR = (".ci", "cache", "live-deploys")
BENCH_RECORD_RE = re.compile(r"^bench-[a-z0-9-]+\.json$")
ACCOUNT_GITLINK = "private/account"
# What a held box's skip line says, per value.
NEEDS_HELD = {
    "verified-vmcheck": "needs verified-vmcheck: no VERIFIED vm:check receipt admits HEAD's tree",
    "bench-deploy": "needs bench-deploy: no clean bench deploy record carries HEAD's account code",
    "pushed-head": "needs pushed-head: HEAD is not on its upstream",
}
# What a vm:check probe may raise while it judges: a failed import, a missing or unreadable receipt or map (MapError is a ValueError), a git call that failed.
_PROBE_ERRORS = (
    ImportError,
    OSError,
    ValueError,
    KeyError,
    TypeError,
    AttributeError,
    RuntimeError,
    SyntaxError,
    subprocess.SubprocessError,
)


def _git(root, *argv: str) -> tuple[int, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    try:
        done = subprocess.run(
            ["git", *argv],
            cwd=str(root),
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return 1, ""
    return done.returncode, done.stdout.strip()


def head_pushed(root) -> bool:
    """HEAD is its upstream's tip or an ancestor of it. No upstream (a detached lease, a branch never pushed) answers no."""
    rc, upstream = _git(root, "rev-parse", "--verify", "-q", "@{upstream}")
    if rc or not upstream:
        return False
    return _git(root, "merge-base", "--is-ancestor", "HEAD", upstream)[0] == 0


def bench_at_branch(root) -> bool:
    """A clean bench deploy record (`.ci/cache/live-deploys/bench-<region>.json`, the proxy records excluded) whose `tree` is HEAD's tree or whose unmodified `private/account` pointer is HEAD's gitlink: bench serves the branch's account code."""
    folder = pathlib.Path(root).joinpath(*BENCH_RECORD_DIR)
    try:
        names = sorted(p for p in folder.iterdir() if BENCH_RECORD_RE.match(p.name))
    except OSError:
        return False
    rc_tree, tree = _git(root, "rev-parse", "HEAD^{tree}")
    rc_link, link = _git(root, "rev-parse", "HEAD:%s" % ACCOUNT_GITLINK)
    tree = tree if not rc_tree else ""
    link = link if not rc_link else ""
    for path in names:
        try:
            rec = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(rec, dict) or rec.get("dirty") is not False:
            continue
        if tree and rec.get("tree") == tree:
            return True
        sub = (rec.get("submodules") or {}).get(ACCOUNT_GITLINK)
        if (
            link
            and isinstance(sub, dict)
            and sub.get("pointer") == link
            and not sub.get("modified")
        ):
            return True
    return False


# The canonical `.claude` hop, loaded BY FILE: this module lives outside the `rediacc_hooks` package (the wl_benchblock and wl_liveproof shape).
SYSPATH_HOP = pathlib.Path(__file__).resolve().parents[2] / "rediacc_hooks" / "syspath.py"


def proof_modules():
    """(`rediacc_ci.proof.surfaces`, `rediacc_ci.proof.vm_tier`) through SYSPATH_HOP; ImportError when the hop cannot load."""
    spec = importlib.util.spec_from_file_location("_wl_boxready_syspath", SYSPATH_HOP)
    if spec is None or spec.loader is None:
        raise ImportError("no loadable %s" % SYSPATH_HOP)
    syspath = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(syspath)
    except OSError as exc:
        raise ImportError("cannot load %s: %s" % (SYSPATH_HOP, exc)) from exc
    return (
        syspath.import_from_ci("rediacc_ci.proof.surfaces"),
        syspath.import_from_ci("rediacc_ci.proof.vm_tier"),
    )


def vmcheck_admits(root) -> bool:
    """`rediacc_ci.proof.vm_tier.admit` admits HEAD's tree with no side charged, through the verified chain of HEAD, the reading `block_vm_unverified_push` takes. A failure to import or to judge answers no."""
    rc_head, head = _git(root, "rev-parse", "HEAD")
    rc_tree, tree = _git(root, "rev-parse", "HEAD^{tree}")
    if rc_head or rc_tree or not head or not tree:
        return False
    try:
        surfaces, vm_tier = proof_modules()
        where = pathlib.Path(root)
        verdict = vm_tier.admit(
            where, tree, surfaces.inputs(where, tree), (), vm_tier.chain_for(where, head)
        )
    except _PROBE_ERRORS as exc:
        if isinstance(exc, SyntaxError):
            # A broken proof module answers no for every tree, so it is named rather than left as a silent no.
            sys.stderr.write(
                "wl_boxready: a proof module does not parse (%s); vm:check answers no\n" % exc
            )
        return False
    return bool(verdict.ok)


def default_probe(root) -> NeedsProbe:
    """The probes against the checkout at `root`, each run at most once."""
    return NeedsProbe(
        vmcheck=functools.cache(lambda: vmcheck_admits(root)),
        bench=functools.cache(lambda: bench_at_branch(root)),
        pushed=functools.cache(lambda: head_pushed(root)),
    )


def box_need(block: str) -> str:
    """The box's `Needs:` value: stated, else derived from a valid tag, else `none`; "" when a stated value is malformed."""
    import wl_plandeps as D

    wait = D.box_needs(block)
    if wait.needs_malformed:
        return ""
    return wait.effective_needs or "none"


def needs_hold(block: str, probe: NeedsProbe) -> str:
    """Why the box's `Needs:` holds it, "" when it is met. Only the probe the value names is asked."""
    need = box_need(block)
    if need == "none":
        return ""
    if not need:
        return "needs: the `Needs:` value is malformed (check:ci-plan-live-proof LP8 names it)"
    met = {
        "verified-vmcheck": probe.vmcheck,
        "bench-deploy": probe.bench,
        "pushed-head": probe.pushed,
    }
    return "" if met[need]() else NEEDS_HELD[need]


@dataclasses.dataclass(frozen=True)
class ReadyBox:
    rel: str
    sig: str
    id: str
    text: str
    owns: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class Skip:
    rel: str
    sig: str
    id: str
    why: str


@dataclasses.dataclass(frozen=True)
class _Box:
    rel: str
    sig: str
    id: str
    body: str
    block: str
    owns: tuple[str, ...]
    shown: str


# (path) -> (mtime_ns, size, text): one read per plan per process, re-read when the file changes.
_TEXT_CACHE: dict[str, tuple[int, int, str]] = {}


def _read(root, rel: str) -> str | None:
    path = pathlib.Path(root) / rel
    try:
        st = os.stat(path)
    except OSError:
        return None
    key = str(path)
    hit = _TEXT_CACHE.get(key)
    if hit and hit[0] == st.st_mtime_ns and hit[1] == st.st_size:
        return hit[2]
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    _TEXT_CACHE[key] = (st.st_mtime_ns, st.st_size, text)
    return text


def box_owns(block: str) -> tuple[str, ...]:
    """The globs of a box's own `Owns:` continuation line, `(note)`s and a closing period dropped; () when it states none."""
    import wl_plandeps as D

    m = _OWNS_LINE_RE.search(re.sub(r"[`]+", "", block or ""))
    if not m:
        return ()
    value = m.group(1).rstrip(".").strip()
    owns, errors = D.parse_owns(value)
    if not errors and owns is not None:
        return tuple(owns.globs)
    out = []
    for raw in value.split(","):
        glob = re.sub(r"\s*\([^)]*\)\s*$", "", raw).strip()
        if glob and " " not in glob:
            out.append(glob)
    return tuple(out)


def _promoted(root) -> list[str]:
    import wl_planqueue

    text = _read(root, wl_planqueue.QUEUE_REL)
    if text is None:
        return []
    return wl_planqueue.entries(text)[0]


def _stem_re(rel: str) -> re.Pattern[str]:
    stem = pathlib.Path(rel).name
    stem = stem.removesuffix(".md")
    return re.compile(r"(?<![\w-])%s(?:\.md)?(?![\w-])" % re.escape(stem))


def _names_box(text: str, stem: re.Pattern[str], box: _Box) -> bool:
    if not stem.search(text):
        return False
    if box.sig and box.sig in text:
        return True
    return (
        bool(box.id) and re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(box.id), text) is not None
    )


def _open_boxes(rel: str, text: str) -> list[_Box]:
    import wl_plandeps as D
    import wl_planrec as R

    out = []
    for i, raw, body, sig in R.open_boxes(text):
        block = D.box_block(text, i)
        # Shown from the raw line with only the bullet and checkbox dropped: the parsed body strips `_`, which mangles every path and name it carries.
        shown = _BULLET_RE.sub("", raw).strip()
        out.append(_Box(rel, sig, D.box_id(body), body, block, box_owns(block), shown))
    return out


def writer_clear(root):
    """The predicate `box_blockers` consults for a LIVE plan-level edge of a writer box: True when the prerequisite holds no writer work, i.e. every remaining open box of it (or the one box a task edge names) is non-writer or post-merge."""
    import wl_plandeps as D

    def clear(target, edge) -> bool:
        text = _read(root, target.rel)
        if text is None:
            return False
        if edge.task:
            box = next((b for b in D.plan_boxes(text) if edge.task in (b.id, b.sig)), None)
            if box is None:
                return False
            if box.done:
                return True
            block = D.box_block(text, box.line)
            return non_writer(box.body) or post_merge(block)
        if WRITERS_NONE_RE.search(text):
            return True
        return all(non_writer(b.body) or post_merge(b.block) for b in _open_boxes(target.rel, text))

    return clear


def ready_boxes(root, plans=None, live_plans=(), items=(), graph=None, probe=None):
    """([ReadyBox], [Skip]) over `plans` (default: the `## Promoted` entries of agent/plans/QUEUE.md), in queue and file order. `live_plans` are the plan basenames live writers serve (the roster's `plan_holders` keys); `items` are worklist records (`id`, `state`, `text`); `probe` answers what a `Needs:` value waits on (default: `default_probe(root)`). A skip is listed only for a writer-tagged box."""
    import wl_planconc
    import wl_plandeps as D
    import wl_planenforce

    root = str(root)
    rels = list(plans) if plans is not None else _promoted(root)
    if graph is None:
        graph = D.Graph.load(root)
    finished = D.finished_states() | {"moved", "removed"}
    tracking = [r for r in items or () if r.get("state") in (" ", ">", "?")]
    per_plan: list[tuple[str, list[_Box]]] = []
    for rel in rels:
        text = _read(root, rel)
        if text is None or "[writer" not in text:
            continue
        header = D.parse_header(text)
        if (
            header.status in finished
            or wl_planenforce.plan_held(text)
            or WRITERS_NONE_RE.search(text)
        ):
            continue
        per_plan.append((rel, _open_boxes(rel, text)))
    # Work in flight: every box a leased item names, with its Owns; and the header Owns of each plan a live writer serves.
    busy: list[tuple[str, tuple[str, ...]]] = []
    for rel, boxes in per_plan:
        stem = _stem_re(rel)
        busy.extend(
            ("%s in flight" % (box.id or box.sig), box.owns)
            for box in boxes
            if box.owns
            and any(
                r.get("state") == ">" and _names_box(str(r.get("text") or ""), stem, box)
                for r in tracking
            )
        )
    live = {pathlib.Path(str(p)).name for p in live_plans or ()}
    for base in sorted(live):
        found = next((r for r in graph.by_base.get(base, []) if not graph.plans[r].stub), None)
        owns = graph.plans[found].header.owns if found else None
        if owns is not None and not owns.none:
            busy.append(("%s (a live writer's plan)" % base, tuple(owns.globs)))
    clear = writer_clear(root)
    if probe is None:
        probe = default_probe(root)
    ready: list[ReadyBox] = []
    skipped: list[Skip] = []
    for rel, boxes in per_plan:
        stem = _stem_re(rel)
        base = pathlib.Path(rel).name
        for box in boxes:
            if not writer_tagged(box.body):
                continue

            def skip(why, box=box, rel=rel):
                skipped.append(Skip(rel, box.sig, box.id, why))

            if post_merge(box.block):
                skip("post-merge")
                continue
            held = needs_hold(box.block, probe)
            if held:
                skip(held)
                continue
            blockers = graph.box_blockers(rel, box.block, clear=clear) if rel in graph.plans else []
            if blockers:
                skip("waits on %s" % ", ".join("%s (%s)" % (t, why) for t, why in blockers[:3]))
                continue
            holder = next(
                (r for r in tracking if _names_box(str(r.get("text") or ""), stem, box)), None
            )
            if holder is not None:
                skip("tracked by #%s" % holder.get("id"))
                continue
            claims = [*busy, *(("%s named above" % (b.id or b.sig), b.owns) for b in ready)]
            claims = [(w, g) for w, g in claims if not w.startswith(base + " ")]
            clash = next(
                (
                    (who, hits[0][2])
                    for who, globs in claims
                    for hits in [wl_planconc.owns_overlap(box.owns, globs)]
                    if box.owns and hits
                ),
                None,
            )
            if clash is not None:
                skip("Owns overlap with %s at %s" % clash)
                continue
            ready.append(ReadyBox(rel, box.sig, box.id, box.shown, box.owns))
    return ready, skipped


def idle_capacity_text(
    root,
    *,
    phase,
    plans=None,
    live_plans=(),
    items=(),
    me8="",
    graph=None,
) -> str:
    """The IDLE CAPACITY block (D5), "" when it stands down: a babysit or merge phase (`phase`), or no ready box."""
    if phase:
        return ""
    ready, _skipped = ready_boxes(root, plans, live_plans, items, graph)
    if not ready:
        return ""
    import worklist_messages as M

    rows = [
        M.IDLE_CAPACITY_BOX % (pathlib.Path(b.rel).name, b.sig, b.text[:110])
        for b in ready[:LIST_MAX]
    ]
    if len(ready) > LIST_MAX:
        rows.append(M.IDLE_CAPACITY_MORE % (len(ready) - LIST_MAX))
    order = list(dict.fromkeys(pathlib.Path(b.rel).name for b in ready))
    return M.V_IDLE_CAPACITY % {
        "n": len(ready),
        "boxes": "\n".join(rows),
        "spawn": "\n".join(M.IDLE_CAPACITY_SPAWN % base for base in order),
        "who": me8,
    }

"""wl_planbind: what still binds to a plan, so no path compacts, moves or sweeps it while anything does (agent/plans/PLAN-plan-compaction-bindings.md, box CB1).

ONE FUNCTION DECIDES. `bindings(root, rel)` returns every live binding of the plan at `rel` (a path under agent/plans, `_done` and `_removed` included), and the compaction verbs (CB2), `check_plan_folders --move|--sweep` (CB3) and the plan-bindings gate (CB4) all ask it. A second reader would be a second grammar.

THE FOUR KINDS (operator ruling 2026-10-03):

- `box`: an open box of the plan itself. It binds unless the header carries a `Ruling:` that re-resolves (`wl_planfile.resolve_ruling`) AND the box names its new home: another live plan (`PLAN-y.md`) or an open worklist item (`#<id>`) whose own text cites a live plan. The home may sit on the box line or on the few lines beneath it, up to the next box. A box the operator DROPPED is released the same way when, under a resolving `Ruling:`, a line beneath it (never the box line itself, which keeps its signature) reads `dropped by ruling #<id>` and that item is closed `[x]` in the store: an open, deferred, tombstoned or unknown item is a question or nothing, not a decision.
- `item`: an open, in-flight or deferred worklist item of ANY session whose text cites the plan (`PLAN-x.md`) or one of its box signatures. A done or dropped item never binds.
- `dependent`: an unfinished plan whose `Depends-On:` reaches the plan (`wl_plandeps.Graph.dependents`). A finished dependent never binds.
- `citing-box`: an open box of another unfinished plan that cites one of this plan's boxes: `PLAN-x.md#<ref>`, `PLAN-x.md [<sig>]`, or a bare box signature. Naming the plan with no box reference is not a citation of a box.

PURE OVER ITS INPUTS. `texts` ({rel: full text}), `items` (records with `id`, `state`, `text`) and `index_text` are injectable, so the tests need no tree; left as None they are read from `root` (every plan in full, every `agent/worklist/*.jsonl` in the working tree, tracked or not, through the store's own fold, so the answer cannot disagree with the Stop hook about what a state means).

NEVER RAISES ON THE READ PATH. An unreadable plan or store file is skipped; the gate's vacuity floor (CB4) is what notices a corpus that stopped loading.
"""

from __future__ import annotations

import dataclasses
import functools
import os
import pathlib
import re

import wl_plandeps as D

KIND_BOX = "box"
KIND_ITEM = "item"
KIND_DEPENDENT = "dependent"
KIND_CITING_BOX = "citing-box"
KINDS = (KIND_BOX, KIND_ITEM, KIND_DEPENDENT, KIND_CITING_BOX)

# Item states that hold a plan: open, in-flight and deferred. `x` (done) and `~` (dropped) do not.
OPEN_ITEM_STATES = D._OPEN_ITEM_STATES
# How many lines under a box line may carry its re-home note.
HOME_LINES = 4
DETAIL_CHARS = 100

_PLAN_NAME_RE = re.compile(r"PLAN-[A-Za-z0-9._-]+?\.md(?![A-Za-z0-9_-])")
# A plan named with or without its `.md`, as items write both (`PLAN-docker-pin-digest proof: ...`).
_PLAN_STEM_RE = re.compile(
    r"(PLAN-[A-Za-z0-9._-]*?[A-Za-z0-9_-])(?:\.md(?![A-Za-z0-9_-])|(?![A-Za-z0-9_-])(?!\.[A-Za-z0-9]))"
)
_ITEM_REF_RE = re.compile(r"#([0-9a-f]{12}|[0-9a-f]{8})\b")
# `dropped by ruling #<id>` under a box: the operator ruling item that dropped its work.
_DROPPED_RE = re.compile(r"\bdropped by ruling #([0-9a-f]{12}|[0-9a-f]{8})\b", re.IGNORECASE)
# How a ruling item's text declares itself: "operator ruling ...", "ruling: ..." or a text that opens with the word. A text that only mentions a ruling in passing ("close the ruling doc gap") is no ruling (review f06eb96b.1).
_RULING_WORD_RE = re.compile(
    r"\boperator\s+ruling\b|\bruling\s*:|\A\W*(?:\([^)]*\)\s*)?ruling\b", re.IGNORECASE
)
# The one item state that makes a ruling a decision.
DROP_CLOSED_STATE = "x"


@dataclasses.dataclass(frozen=True)
class Binding:
    """One thing that holds a plan. `where` locates it (`#<id>`, `<plan rel>:<line>`, a plan rel); `detail` says why in one line."""

    kind: str
    where: str
    detail: str

    def __str__(self) -> str:
        return "%s %s: %s" % (self.kind, self.where, self.detail)


# --------------------------------------------------------------------------- Readers.


def load_texts(root) -> dict[str, str]:
    """{rel: full text} of every plan file under agent/plans, `_done` and `_removed`."""
    root = pathlib.Path(root)
    out: dict[str, str] = {}
    for folder in D.PLAN_DIRS:
        try:
            names = sorted(os.listdir(root / folder))
        except OSError:
            continue
        for name in names:
            if not (name.startswith("PLAN-") and name.endswith(".md")):
                continue
            try:
                out["%s/%s" % (folder, name)] = (root / folder / name).read_text(
                    encoding="utf-8", errors="replace"
                )
            except OSError:
                continue
    return out


def store_items(root) -> list[dict]:
    """The folded records of every writer file in the working tree under `<root>/agent/worklist/`, tombstoned ones dropped. The fold is `wl_store._fold_events`, as `wl_planfile.store_item_states` reads it."""
    import wl_store as S

    events: list[dict] = []
    for f in sorted((pathlib.Path(root) / "agent" / S.STORE_DIR_NAME).glob("*.jsonl")):
        try:
            events.extend(S._parse_events(f.read_text(encoding="utf-8", errors="replace")))
        except OSError:
            continue
    events.sort(key=S.event_order)
    records = S._fold_events(events)[0]
    return [dict(r, id=rid) for rid, r in records.items() if r.get("state") != "~"]


# --------------------------------------------------------------------------- Matchers.


def _sig_re(sigs) -> re.Pattern[str] | None:
    sigs = sorted(set(sigs))
    if not sigs:
        return None
    return re.compile(r"(?<![0-9A-Za-z])(?:%s)(?![0-9A-Za-z])" % "|".join(sigs))


def _cite_box_re(base: str) -> re.Pattern[str]:
    """`PLAN-x.md#<ref>` or `PLAN-x.md [<sig>]`: a reference to a box of the plan, not to the plan alone."""
    return re.compile(r"(?<![A-Za-z0-9._-])%s(?:#[A-Za-z0-9]|\s*\[[0-9a-f]{8}\])" % re.escape(base))


@functools.lru_cache(maxsize=1024)
def _open_boxes(text: str) -> tuple:
    """`wl_planrec.open_boxes`, memoised on the text: step 4 reads every other plan's open boxes once per judged plan."""
    import wl_planrec as R

    return tuple(R.open_boxes(text))


def _clip(text: str) -> str:
    one = " ".join(str(text or "").split())
    return one if len(one) <= DETAIL_CHARS else one[: DETAIL_CHARS - 3] + "..."


@functools.lru_cache(maxsize=1024)
def _plan_sigs_cached(text: str) -> tuple[str, ...]:
    import wl_planrec as R

    return tuple(b[3] for b in R.open_boxes(text)) + tuple(b[3] for b in R.done_boxes(text))


def _plan_sigs(text: str) -> list[str]:
    return list(_plan_sigs_cached(text))


def _box_home(text: str, index: int, body: str) -> list[str]:
    """The box line's body plus up to HOME_LINES lines beneath it, stopping at the next box line."""
    import wl_planrec as R

    lines = text.splitlines()
    chunk = [body]
    for raw in lines[index + 1 : index + 1 + HOME_LINES]:
        if R.BOX_LINE_RE.match(raw):
            break
        chunk.append(raw)
    return chunk


def _live_plan(graph: D.Graph, name: str, own_rel: str) -> bool:
    """True when `name` is a real plan other than the one judged whose Status is not finished."""
    if name == own_rel.rsplit("/", 1)[-1]:
        return False
    target = graph.resolve(name)
    return target.state == D.LIVE


def _rehomed(graph: D.Graph, own_rel: str, chunk: list[str], item_by_id: dict[str, dict]) -> str:
    """Where a box says its work went ("" when it names no live home): a live other plan, or an open item that cites a live plan."""
    blob = "\n".join(chunk)
    for name in _PLAN_NAME_RE.findall(blob):
        if _live_plan(graph, name, own_rel):
            return name
    for iid in _ITEM_REF_RE.findall(blob):
        item = item_by_id.get(iid)
        if item is None or item.get("state") not in OPEN_ITEM_STATES:
            continue
        for name in _PLAN_NAME_RE.findall(str(item.get("text") or "")):
            if _live_plan(graph, name, own_rel):
                return "#%s -> %s" % (iid, name)
    return ""


def _dropped(chunk: list[str], states: dict[str, str], item_by_id: dict[str, dict]) -> str:
    """`dropped by ruling #<id>` when a line UNDER the box (chunk[1:]) names a closed `[x]` item whose text says it is a ruling, else "". A closed item of any other kind does not release a box (review 8e5c269d.1)."""
    for line in chunk[1:]:
        for iid in _DROPPED_RE.findall(line):
            if states.get(iid, "").lower() != DROP_CLOSED_STATE:
                continue
            if _RULING_WORD_RE.search(str((item_by_id.get(iid) or {}).get("text") or "")):
                return "dropped by ruling #%s" % iid
    return ""


# --------------------------------------------------------------------------- The decision.


def bindings(
    root,
    rel: str,
    *,
    texts: dict[str, str] | None = None,
    items: list[dict] | None = None,
    index_text: str | None = None,
    graph: D.Graph | None = None,
) -> list[Binding]:
    """Every live binding of plan `rel`, in kind order (box, item, dependent, citing-box). [] means nothing holds it.

    `rel` is a path under agent/plans. `texts`, `items` and `index_text` replace the reads from `root` (the tests' door). `graph`, built once over the same `texts`, is reused across calls by a caller judging many plans (the plan-bindings gate): rebuilding it per call threw its caches away and cost about 50 s on the real tree."""
    import wl_planfile as PF
    import wl_planrec as R

    root = pathlib.Path(root)
    if texts is None:
        texts = load_texts(root)
    if items is None:
        items = store_items(root)
    if index_text is None:
        try:
            index_text = (root / D.INDEX_REL).read_text(encoding="utf-8", errors="replace")
        except OSError:
            index_text = ""
    own = texts.get(rel)
    if own is None:
        return []
    base = rel.rsplit("/", 1)[-1]
    if graph is None:
        graph = D.Graph(texts, index_text, root)
    elif graph.texts != texts:
        # A graph built over another plan set would answer dependents from that set (review 7aa999c1.1).
        raise ValueError("bindings: graph was built over different plan texts than `texts`")
    item_by_id = {str(r.get("id")): r for r in items}
    out: list[Binding] = []

    # 1. Own open boxes.
    opens = R.open_boxes(own)
    if opens:
        states = {str(r.get("id")): str(r.get("state") or " ") for r in items}
        ruled, _why = PF.resolve_ruling(root, rel, own, states)
        for index, _raw, body, sig in opens:
            if not ruled:
                out.append(
                    Binding(
                        KIND_BOX, "%s:%d" % (rel, index + 1), "open box %s: %s" % (sig, _clip(body))
                    )
                )
                continue
            chunk = _box_home(own, index, body)
            home = _rehomed(graph, rel, chunk, item_by_id) or _dropped(chunk, states, item_by_id)
            if not home:
                out.append(
                    Binding(
                        KIND_BOX,
                        "%s:%d" % (rel, index + 1),
                        "open box %s names no live home (Ruling resolves): %s" % (sig, _clip(body)),
                    )
                )

    # 2. Open items of any session that cite the plan or one of its box signatures.
    plan_pat = D._base_re(base)
    own_sigs = set(_plan_sigs(own))
    sig_pat = _sig_re(own_sigs)
    # A signature other plans also carry (identical box lines, such as every `LP-hostinger [live]` box) cannot say which plan an item means, so it binds only an item that names this plan (CB5: #658c04e3 bound PLAN-retired-terms-submodule-scan through 7692f2db, shared by 12 plans).
    shared = {
        sig for other, t in texts.items() if other != rel for sig in _plan_sigs_cached(t)
    } & own_sigs
    for rec in sorted(items, key=lambda r: str(r.get("id"))):
        if rec.get("state") not in OPEN_ITEM_STATES:
            continue
        text = str(rec.get("text") or "")
        # A signature binds an item that names this plan, or one that names no plan and cites at least one signature that is not `shared` (identical box lines in different plans, such as every `LP-bench [live]` box, hash alike).
        named = {m.group(1) for m in _PLAN_STEM_RE.finditer(text)}
        names_me = base[:-3] in named
        hits = set(sig_pat.findall(text)) if sig_pat is not None else set()
        sig_hit = bool(hits) and (names_me or (not named and bool(hits - shared)))
        # A plan named without its `.md` ("PLAN-ci-prebaked-vm-images B5") names it all the same.
        if plan_pat.search(text) or names_me or sig_hit:
            out.append(
                Binding(
                    KIND_ITEM,
                    "#%s" % rec.get("id"),
                    "[%s] %s" % (str(rec.get("state") or " ").strip() or "open", _clip(text)),
                )
            )

    # 3. Unfinished plans that depend on it.
    out.extend(
        Binding(KIND_DEPENDENT, other, "`Depends-On:` reaches %s" % base)
        for other in sorted(graph.dependents(rel))
    )

    # 4. Open boxes of other unfinished plans that cite one of its boxes.
    cite = _cite_box_re(base)
    for other, text in sorted(texts.items()):
        if other == rel:
            continue
        info = graph.plans.get(other)
        if info is None or info.stub:
            continue
        if info.header.status in graph.finished() or info.header.status == D.REMOVED_STATUS:
            continue
        for index, _raw, body, sig in _open_boxes(text):
            if cite.search(body) or (sig_pat is not None and sig_pat.search(body)):
                out.append(
                    Binding(
                        KIND_CITING_BOX,
                        "%s:%d" % (other, index + 1),
                        "open box %s cites a box of %s: %s" % (sig, base, _clip(body)),
                    )
                )
    return out


def render(rel: str, found: list[Binding]) -> str:
    """The refusal text for a non-empty list: every binding, then the commands that release it. "" for an empty list."""
    if not found:
        return ""
    base = rel.rsplit("/", 1)[-1]
    lines = [
        "%s is bound by %d thing(s) and cannot be compacted, moved or swept:" % (base, len(found))
    ]
    lines += ["  - %s" % b for b in found]
    lines.append("Release each one, then retry:")
    kinds = {b.kind for b in found}
    if KIND_ITEM in kinds:
        lines.append(
            "  item: worklist.py --tick <me> <id> <evidence>, or re-home it under a live plan "
            "(worklist.py --epic <me> plan)"
        )
    if KIND_BOX in kinds:
        lines.append(
            "  box: tick it, or add a `Ruling:` header line and name the live plan or item "
            "that took the work over under the box (or, for work the operator dropped, "
            "`dropped by ruling #<closed item>` on a line under it)"
        )
    if KIND_DEPENDENT in kinds:
        lines.append("  dependent: finish that plan, or drop this plan from its `Depends-On:`")
    if KIND_CITING_BOX in kinds:
        lines.append("  citing-box: tick that box, or move its citation to the plan that took over")
    lines.append("  work still wanted: worklist.py --plan-revive <me> %s" % base)
    return "\n".join(lines)

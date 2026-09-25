"""wl_defersettle: a `- [?]` whose premise the tree already answers is not a decision.

WHY THIS EXISTS (operator, 2026-09-23). Deferrals were being parked on questions the repository had already settled: a "should the operator provide the R2 key" item while the key was already available through the secret vault, and a "one PR or several" item that CLAUDE.md's big-bang packaging rule answers in so many words. Each one sat in every stop's report until its DEFAULT window closed. The design is agent/plans/PLAN-defer-settle-classifier.md.

WHAT IT IS NOT. `defer_audit` (wl_checks, DEFER_AUDIT_PROMPT) interrogates a deferral's PROSE and is a reasoning-only judge. This module is FACT-GROUNDED: Python computes a closed set of facts and hands them to the model as givens, the same no-tools grounding wl_judge uses for `fixset_files`. The model never investigates.

THE CLOSED FACT SET. gather_facts runs exactly three deterministic checks, and a fourth kind is a reviewed code change, never a runtime decision:

    env_key_present       a credential-shaped KEY_NAME in the item is present at
                          the start of a line in one of ENV_FILES. The KEY NAME
                          only: a Fact has no value field, so a value cannot
                          reach the prompt or the ledger by construction.
    standing_rule_match   a hand-maintained CATALOG entry whose trigger matches
                          the item, and whose quote is verified VERBATIM in the
                          cited file at gather time (a drifted quote emits
                          nothing rather than a stale citation).
    artifact_exists       an npm script key or a repo-relative file the item
                          asks about already exists.

Only PRESENT facts are emitted. An item with no fact is never sent to the model, which is the cost control: most `[?]` items carry no checkable claim.

TWO ENTRY POINTS. At creation (worklist.py --defer) one classifier call may REFUSE the deferral on a confident `settled`, which never touches the store. At stop time a bounded batch rides the judge's existing call via the optional `defer_settle` field.

FAIL SEMANTICS are the OPPOSITE of the stop judge's. Any failure -- no answer, a malformed array, a missing entry, an unknown fact index -- leaves the `[?]` exactly as it was. Nothing here ever blocks a stop or a --defer.

THE SIX HARD LIMITS (plan section 7):
  1. Never on first sight: an acting verdict is BANKED, and acts only when a later, separate judge call agrees on the same verdict citing the same fact.
  2. Never an operator-reserved act: the catalog's action/quote text is scanned against wl_judge.FORBIDDEN_ORDERS and wl_rules at import time (check_catalog), and `execute_default` only ever REPORTS, through the existing expired-DEFAULT demand.
  3. Never without the evidence gate: a settle tick passes completion_evidence and issue_only_evidence, the gates --tick uses, or it is refused and the item is left alone.
  4. Secret values never leave Python (the Fact shape above).
  5. The reserved actor ACTOR marks every machine tick in the append-only log; worklist.py refuses it as a session's <me>.
  6. At most SETTLE_CAP settles per session; the next one is reported, not acted on.
"""

import hashlib
import os
import pathlib
import re
import time
from typing import Any, NamedTuple

import wl_core as C
import wl_rules

# The reserved actor on every state event this module writes, greppable forever in the append-only log.
ACTOR = "haiku-defer-settle"
DEFER_SETTLE_MARKER = "THIS DEFERRAL'S PREMISE MAY ALREADY BE FALSE"
# Shorter than DEFER_AUDIT_MIN (45) on purpose: acting needs two agreeing samples, so an early first sample only banks.
DEFER_SETTLE_MIN = int(os.environ.get("WORKLIST_DEFER_SETTLE_MIN", "30"))
DEFER_SETTLE_BATCH = int(os.environ.get("WORKLIST_DEFER_SETTLE_BATCH", "4"))
SETTLE_CAP = int(os.environ.get("WORKLIST_DEFER_SETTLE_CAP", "5"))

VERDICTS = ("settled", "execute_default", "genuinely_operator", "uncertain")
ACTING = ("settled", "execute_default")
FACT_KINDS = ("env_key_present", "standing_rule_match", "artifact_exists")

# The ONLY place env_key_present looks. A fixed allowlist, never a search. Bitwarden is the single source of truth since 2026-09-24 (the account .env files are retired), and this tracked map holds its key NAMES and ids, never a value.
ENV_FILES = (".ci/config/bws-secret-map.json",)

ENV_KEY_RE = re.compile(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b")
SCRIPT_KEY_RE = re.compile(r"(?<![\w:-])((?:check|gate-test|lint|i18n|test):[\w.:-]*\w)")
PATH_TOKEN_RE = re.compile(r"(?<![\w/.-])((?:\.?[\w-]+/)+[\w.-]+\.\w+)")
# artifact_exists asks only about an item phrased around existence or building.
EXISTENCE_RE = re.compile(
    r"\b(exists?|already|need(?:s|ed)?|build|built|add|create|write|whether|register(?:ed)?)\b",
    re.IGNORECASE,
)
# The tracking tree: a plan or ledger a deferral names is its own bookkeeping, never the artifact it asks about.
AGENT_TRACKING = ("agent/",)
MAX_ENV_CANDIDATES = 12
MAX_ARTIFACT_CANDIDATES = 6


class Fact(NamedTuple):
    """One checked fact. There is deliberately NO value field: an env fact cannot carry a secret because the type has nowhere to put one."""

    kind: str
    subject: str
    cite: str
    claim: str

    @property
    def key(self):
        return "%s|%s|%s" % (self.kind, self.subject, self.cite)


# The hand-maintained standing-rule catalog. A live grep of CLAUDE.md was rejected: it would quote a paragraph nobody vetted for this purpose. Each `quote` must appear VERBATIM on one line of `file`; the citation is derived from where it is found, so an edit to the rule drops the fact instead of citing a line that no longer says it.
CATALOG: tuple[dict[str, Any], ...] = (
    {
        "id": "big-bang-packaging",
        "triggers": (
            re.compile(
                r"\b(separate|one|which|split|combine|bundle)\b.{0,40}\bPRs?\b", re.IGNORECASE
            ),
            re.compile(r"\bbig[- ]bang\b", re.IGNORECASE),
            re.compile(r"\bcluster\b.{0,40}\bfindings?\b", re.IGNORECASE),
        ),
        "file": "CLAUDE.md",
        "quote": "The ask decides PACKAGING (one comprehensive change versus riding the current PR), "
        "never WHETHER the findings get fixed",
        "action": "execute_default when the DEFAULT already fixes the cluster this session",
    },
    {
        "id": "model-routing-haiku",
        "triggers": (
            re.compile(
                r"\b(haiku|sonnet|opus|model tier|which model)\b.{0,80}"
                r"\b(writ\w*|implement\w*|port\w*|sweep\w*|edit\w*|author\w*)\b",
                re.IGNORECASE,
            ),
            re.compile(
                r"\b(writ\w*|implement\w*|port\w*|sweep\w*|edit\w*|author\w*)\b.{0,80}"
                r"\b(haiku|sonnet|opus|model tier|which model)\b",
                re.IGNORECASE,
            ),
        ),
        "file": "CLAUDE.md",
        "quote": "Haiku is NOT routed general write or implementation work any more",
        "action": "execute_default when the DEFAULT already routes the write away from Haiku, "
        "otherwise genuinely_operator",
    },
)


def check_catalog(orders=()):
    """Refuse a catalog entry whose action or quote would order an operator-reserved act (hard limit 2).

    Called at import with no `orders` (the wl_rules scans), and again from wl_judge once FORBIDDEN_ORDERS exists, since wl_judge imports this module before defining it.
    """
    for entry in CATALOG:
        text = "%s %s" % (entry["action"], entry["quote"])
        for pattern, label in orders:
            if pattern.search(text):
                raise AssertionError("defer-settle catalog %s orders %s" % (entry["id"], label))
        bad = wl_rules.names_operator_reserved(text) or wl_rules.names_tree_destroying(text)
        if bad:
            raise AssertionError("defer-settle catalog %s names %r" % (entry["id"], bad))


check_catalog()


def _item_text(rec):
    """The item's own text plus its WHY/HOW, the whole surface a fact may be drawn from."""
    j = rec.get("just") if isinstance(rec.get("just"), dict) else {}
    parts = [str(rec.get("text") or "")]
    parts.extend(str(v) for v in j.values() if isinstance(v, str))
    return "\n".join(parts)


def _env_key_line(root, rel, key):
    """1-based line where `key` is assigned in root/rel, or None. The value is never kept."""
    p = pathlib.Path(root) / rel
    if not p.is_file():
        return None
    pat = re.compile(r'^\s*(?:(?:export\s+)?%s\s*=|"%s"\s*:)' % (re.escape(key), re.escape(key)))
    try:
        with open(p, encoding="utf-8", errors="replace") as fh:
            for n, line in enumerate(fh, 1):
                if pat.match(line):
                    return n
    except OSError:
        return None
    return None


def _env_facts(root, text):
    out, seen = [], set()
    for m in ENV_KEY_RE.finditer(text):
        key = m.group(0)
        if key in seen:
            continue
        seen.add(key)
        if len(seen) > MAX_ENV_CANDIDATES:
            break
        for rel in ENV_FILES:
            n = _env_key_line(root, rel, key)
            if n:
                cite = "%s:%d" % (rel, n)
                out.append(
                    Fact(
                        "env_key_present",
                        key,
                        cite,
                        "key %s is present at %s (value not shown; presence only)" % (key, cite),
                    )
                )
                break
    return out


def _quote_line(root, rel, quote):
    try:
        lines = (pathlib.Path(root) / rel).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for n, line in enumerate(lines.splitlines(), 1):
        if quote in line:
            return n
    return None


def _rule_facts(root, text):
    out = []
    for entry in CATALOG:
        if not any(t.search(text) for t in entry["triggers"]):
            continue
        n = _quote_line(root, entry["file"], entry["quote"])
        if not n:
            continue
        cite = "%s:%d" % (entry["file"], n)
        out.append(
            Fact(
                "standing_rule_match",
                entry["id"],
                cite,
                'standing rule %s at %s says: "%s" (suggested: %s)'
                % (entry["id"], cite, entry["quote"], entry["action"]),
            )
        )
    return out


def _script_line(root, key):
    try:
        lines = (pathlib.Path(root) / "package.json").read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    needle = '"%s"' % key
    for n, line in enumerate(lines, 1):
        if needle in line:
            return n
    return None


def _artifact_facts(root, text):
    if not EXISTENCE_RE.search(text):
        return []
    import wl_reggate  # noqa: PLC0415 -- lazy: a heavier sibling only this path needs

    out, budget = [], MAX_ARTIFACT_CANDIDATES
    scripts = None
    for m in SCRIPT_KEY_RE.finditer(text):
        if budget <= 0:
            break
        budget -= 1
        key = m.group(1)
        if scripts is None:
            scripts = wl_reggate.package_scripts(root)
        n = _script_line(root, key) if key in scripts else None
        if n:
            cite = "package.json:%d" % n
            out.append(
                Fact(
                    "artifact_exists",
                    key,
                    cite,
                    "npm script %s is already registered in package.json scripts (%s)"
                    % (key, cite),
                )
            )
    base = pathlib.Path(root).resolve()
    for m in PATH_TOKEN_RE.finditer(text):
        if budget <= 0:
            break
        budget -= 1
        tok = m.group(1)
        try:
            p = (base / tok).resolve()
            p.relative_to(base)  # inside the repo, never a traversal out of it
        except (OSError, ValueError):
            continue
        if not p.is_file() or os.path.basename(tok).startswith(".env"):
            continue  # an env file is env_key_present's business, never quoted as an artifact
        if tok.startswith(AGENT_TRACKING):
            # Measured on the live store 2026-09-24: five of six fact-bearing deferrals were a [?] naming its own plan file, which exists by definition and settles nothing.
            continue
        try:
            with open(p, "rb") as fh:
                nonempty = bool(fh.read(1))
        except OSError:
            continue
        if nonempty:
            cite = "%s:1" % tok
            out.append(
                Fact("artifact_exists", tok, cite, "file %s already exists (%s)" % (tok, cite))
            )
    return out


def gather_facts(root, rec):
    """The closed fact set for one `[?]` record: a list of Fact, present ones only, never a value."""
    text = _item_text(rec)
    facts = _env_facts(root, text) + _rule_facts(root, text) + _artifact_facts(root, text)
    uniq, seen = [], set()
    for f in facts:
        if f.key not in seen:
            seen.add(f.key)
            uniq.append(f)
    return uniq


def facts_sig(facts):
    return hashlib.sha1("\n".join(sorted(f.key for f in facts)).encode()).hexdigest()[:12]


DEFER_SETTLE_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "id": {"type": "string", "maxLength": 16},
            "verdict": {"type": "string", "enum": list(VERDICTS)},
            "reason": {"type": "string", "maxLength": 300},
            "fact_used": {"type": "string", "maxLength": 16},
        },
        "required": ["id", "verdict", "reason", "fact_used"],
        "additionalProperties": False,
    },
}

# The creation-time call asks this question alone, so the array is the whole answer.
ONE_SCHEMA = {
    "type": "object",
    "properties": {"defer_settle": DEFER_SETTLE_SCHEMA},
    "required": ["defer_settle"],
    "additionalProperties": False,
}

_BODY = """
You are given, for each item, a CLOSED set of FACTS this session's own code
already checked -- you are not being asked to investigate anything yourself,
only to reason about what is handed to you. Never assume a fact that is not
listed; never treat a KEY NAME being present as proof of its VALUE.

Verdict per item:
  "settled": one of the given facts makes the [?]'s own QUESTION moot -- the
    thing it asks the operator to decide or provide is already true, present,
    or already answered by a quoted standing rule that requires no operator
    judgment call. Put that fact's number in `fact_used` (e.g. "1").
  "execute_default": a given fact is a STANDING RULE that already settles
    HOW to package this, and the DEFAULT already names the packaging that
    rule requires -- so there is nothing left to wait out the window for.
    Put the rule fact's number in `fact_used`.
  "genuinely_operator": the facts given do not settle this; it is a real
    decision for the operator, or the standing rule quoted requires a
    judgment call the rule itself does not make (state which).
  "uncertain": you are not confident either way. USE THIS WHENEVER IN DOUBT --
    an uncertain [?] is left exactly as it is; only a confident "settled" or
    "execute_default" ever changes anything.
Set `fact_used` to "" for the last two.

Items and their FACTS (%(n)d):
%(items)s
"""

DEFER_SETTLE_PROMPT = (
    "\n\n"
    + DEFER_SETTLE_MARKER
    + ". ALSO fill the `defer_settle`\narray: exactly one entry per item below, using the same id.\n"
    + _BODY
)

CREATE_PROMPT = (
    DEFER_SETTLE_MARKER + ". A session is about to park the [?] below on the operator.\n"
    "Fill the `defer_settle` array with exactly one entry, id=new.\n" + _BODY
)


def render_item(rid, rec, facts):
    j = rec.get("just") if isinstance(rec.get("just"), dict) else {}
    head = "  id=%s  [?] %s\n    WHY: %s\n    HOW: %s" % (
        rid,
        str(rec.get("text") or "")[:240],
        str(j.get("why") or "(none)")[:200],
        str(j.get("how") or "(none)")[:200],
    )
    return head + "".join(
        "\n    FACT #%d (%s): %s" % (i, f.kind, f.claim) for i, f in enumerate(facts, 1)
    )


def prompt_section(batch):
    """The stop-time section for [(rec, facts)], or "" for an empty batch."""
    if not batch:
        return ""
    return DEFER_SETTLE_PROMPT % {
        "n": len(batch),
        "items": "\n".join(render_item(r["id"], r, f) for r, f in batch),
    }


def _fact_for(entry, facts):
    raw = str(entry.get("fact_used") or "").strip().lstrip("#").upper().replace("FACT", "").strip()
    if not raw.isdigit():
        return None
    i = int(raw)
    return facts[i - 1] if 1 <= i <= len(facts) else None


def read_rows(rows, batch):
    """({id: (verdict, fact_or_None, reason)}, note). Tolerant by contract: whatever is unusable is simply absent, and `note` says why."""
    if not isinstance(rows, list):
        return {}, "no defer_settle array: %s" % repr(rows)[:80]
    by_id = {}
    for e in rows:
        if isinstance(e, dict) and e.get("verdict") in VERDICTS:
            by_id[str(e.get("id", ""))] = e
    out, missing = {}, []
    for rec, facts in batch:
        e = by_id.get(rec["id"])
        if e is None:
            missing.append(rec["id"])
            continue
        verdict, fact = e["verdict"], None
        if verdict in ACTING:
            fact = _fact_for(e, facts)
            if fact is None:
                verdict = "uncertain"  # an acting verdict that cites no given fact acts on nothing
        out[rec["id"]] = (verdict, fact, str(e.get("reason", ""))[:200])
    note = "no usable entry for %s" % ", ".join("#" + m for m in missing) if missing else ""
    return out, note


def _cache(state_doc):
    c = state_doc.setdefault("defer_settle", {})
    if not isinstance(c.get("items"), dict):
        c["items"] = {}
    if not isinstance(c.get("settled"), list):
        c["settled"] = []
    return c


def build_batch(root, state_doc, deferred_recs, disabled=False):
    """[(rec, facts)] to put to the judge this stop: aged, defaulted, carrying a present fact, and not already answered at this stamp and fact set."""
    cache = _cache(state_doc)
    live = {r.get("id") for r in deferred_recs}
    for k in [k for k in cache["items"] if k not in live]:
        del cache["items"][k]
    if disabled:
        return []
    batch = []
    for r in sorted(
        deferred_recs, key=lambda r: (-(C.stamp_age_min(r.get("upd", "")) or 0), r.get("id", ""))
    ):
        if (C.stamp_age_min(r.get("upd", "")) or 0) < DEFER_SETTLE_MIN:
            break  # oldest first: everything after is younger
        if not C.DEFAULT_TOKEN.search(r.get("line") or r.get("text") or ""):
            continue
        facts = gather_facts(root, r)
        if not facts:
            continue
        banked = cache["items"].get(r["id"])
        if (
            isinstance(banked, dict)
            and banked.get("done")
            and banked.get("stamp") == r.get("upd")
            and banked.get("sig") == facts_sig(facts)
        ):
            continue
        batch.append((r, facts))
        if len(batch) >= DEFER_SETTLE_BATCH:
            break
    return batch


def build_evidence(fact, first_at, now):
    return (
        "MACHINE-CLASSIFIED (%s): premise settled -- %s; corroborated over 2 stops (%s, %s), "
        "verdict cited fact %s both times" % (ACTOR, fact.claim, first_at, now, fact.key)
    )


def _default_gate(root, evidence):
    import wl_checks  # noqa: PLC0415 -- lazy: wl_checks imports this module

    return wl_checks.completion_evidence(root, evidence) and not wl_checks.issue_only_evidence(
        root, evidence
    )


def apply_stop(out, batch, state_doc, root, worklist, run_id=None, gate=None, set_state=None):
    """Bank, corroborate and act on this stop's defer_settle answer. Returns report notes. Never raises into the stop, never blocks.

    `out` is the judge verdict; a degraded answer is appended to its reason, the convention the sibling modules use.
    """
    if not batch:
        return []
    if set_state is None:
        import wl_store  # noqa: PLC0415 -- lazy, and injectable so the controls observe the write

        set_state = wl_store.set_state
    gate = gate or _default_gate
    run_id = run_id or "%x" % time.time_ns()
    cache = _cache(state_doc)
    results, note = read_rows((out or {}).get("defer_settle"), batch)
    if note and isinstance(out, dict):
        out["reason"] = ("%s [defer-settle not judged: %s]" % (out.get("reason", ""), note))[:400]
    notes, now = [], C.stamp_now()
    for rec, facts in batch:
        rid = rec["id"]
        if rid not in results:
            continue  # fail-safe: an unanswered item is left exactly as it was
        verdict, fact, reason = results[rid]
        base = {"stamp": rec.get("upd"), "sig": facts_sig(facts), "verdict": verdict, "at": now}
        if verdict not in ACTING:
            cache["items"][rid] = {**base, "done": True, "reason": reason}
            continue
        prior = cache["items"].get(rid)
        same = (
            isinstance(prior, dict)
            and not prior.get("done")
            and prior.get("stamp") == rec.get("upd")
            and prior.get("verdict") == verdict
            and prior.get("fact") == fact.key
            and prior.get("run") != run_id
        )
        if not same:
            # First sight, or a disagreeing sample: bank it, act on nothing (hard limit 1).
            cache["items"][rid] = {**base, "fact": fact.key, "run": run_id, "first_at": now}
            continue
        first_at = prior.get("first_at") or now
        done = {**base, "fact": fact.key, "done": True, "corroborated": True, "first_at": first_at}
        if verdict == "execute_default":
            cache["items"][rid] = {**done, "accelerate": True}
            notes.append(
                "Deferral #%s: its DEFAULT is already required by %s (corroborated over two "
                "stops); it is demanded as an expired DEFAULT from the next stop."
                % (rid, fact.cite)
            )
            continue
        if len(cache["settled"]) >= SETTLE_CAP:
            cache["items"][rid] = {**done, "outcome": "capped"}
            notes.append(
                "Deferral #%s looks settled by %s, NOT auto-settled: %d deferrals were already "
                "auto-settled this session (cap %d). Review those before more auto-settle; tick "
                "this one by hand if the fact holds."
                % (rid, fact.claim, len(cache["settled"]), SETTLE_CAP)
            )
            continue
        evidence = build_evidence(fact, first_at, now)
        if not gate(root, evidence):
            cache["items"][rid] = {**done, "outcome": "refused-evidence-gate"}
            notes.append(
                "Deferral #%s: auto-settle refused by the evidence gate (%s)." % (rid, fact.cite)
            )
            continue
        set_state(worklist, ACTOR, rid, "x", evidence)
        cache["items"][rid] = {**done, "outcome": "ticked"}
        cache["settled"].append(rid)
        notes.append("Deferral #%s auto-settled: %s" % (rid, evidence[:300]))
    return notes


def accelerated(state_doc, deferred_recs, already):
    """Deferrals whose corroborated execute_default verdict still holds at the current stamp, for the expired-DEFAULT demand. `already` is that demand's own list, never duplicated."""
    items = (state_doc.get("defer_settle") or {}).get("items") or {}
    have = {r["id"] for r in already}
    return [
        r
        for r in deferred_recs
        if r["id"] not in have
        and isinstance(items.get(r["id"]), dict)
        and items[r["id"]].get("accelerate")
        and items[r["id"]].get("stamp") == r.get("upd")
    ]


def classify_one(root, text, just):
    """(verdict_dict, error) for a deferral about to be created; (None, None) when nothing is checkable.

    Advisory: the caller refuses the --defer only on a confident `settled` and treats every error as "create it as before".
    """
    if os.environ.get("WORKLIST_JUDGE") == "off":
        return None, "judge disabled"
    rec = {"id": "new", "text": text, "just": just if isinstance(just, dict) else {}}
    facts = gather_facts(root, rec)
    if not facts:
        return None, None
    import wl_judge  # noqa: PLC0415 -- lazy: wl_judge imports this module

    def _extract(out):
        rows = out.get("defer_settle")
        return rows if isinstance(rows, list) else None

    rows, err = wl_judge._run_structured(
        "defer-settle",
        CREATE_PROMPT % {"n": 1, "items": render_item("new", rec, facts)},
        ONE_SCHEMA,
        _extract,
    )
    if err:
        return None, err
    results, note = read_rows(rows, [(rec, facts)])
    if "new" not in results:
        return None, note or "no entry"
    verdict, fact, reason = results["new"]
    return {
        "verdict": verdict,
        "reason": reason,
        "fact_cite": fact.claim if fact else "",
        "fact_key": fact.key if fact else "",
    }, None

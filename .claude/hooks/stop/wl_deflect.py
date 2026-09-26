"""wl_deflect: catch a finding dismissed in prose without being fixed, tracked, or door-named.

WHY THIS EXISTS. The operator flagged a real instance this session: "Confirmed pre-existing and unrelated (untouched file, no uncommitted changes, environment-dependent identity-cache check)." CLAUDE.md rule 2 requires a finding to be fixed, tracked, or door-named in the session that finds it -- not just labeled and left. This module is the mechanical (regex, not judge-call) Stop-hook check for that class, cheap enough to run on every stop.

WHAT ALREADY EXISTS AND WHY THIS IS NOT THAT. `wl_admit.py` scans the assistant's whole-turn text
for evasive/admission phrasing about IRREVERSIBLE DAMAGE this session caused. `DEFERRED_FINDING_RE`
in `wl_checks.py` is a closer precedent (a hand-written regex firing on "found/reported/flagged
... not fixed" language), but it is `last_msg`-scoped, and the real incident's corroboration (a
`worklist.py --add` call) landed in a LATER tool call in the same turn, not adjacent prose.

THE PHRASE FAMILY, grounded in this session's own transcript rather than a hypothetical list. Two shapes, not a bare word list -- a bare list badly over-fires: "pre-existing docstrings/content/bumps" are all harmless adjectival uses measured live this session.

    verdict-shape          "(that's|this is|confirmed[,:]?) ... (pre-existing|unrelated|environmental|not caused by|not my <noun>)"
    finding-noun-adjacent  a finding/bug/defect/failure/regression noun within ~60 chars of the attribution word, either order

Excluded when the match is immediately followed by a harmless noun (docstrings/content/comments/bumps/"tests pass"), and excluded entirely when baseline|ratchet(ed)?|floor|grandfathered appears in the same clause -- that debt is already tracked by the repo's own baseline mechanism.

CORROBORATION WINDOW: the whole turn since the last genuine operator message, tools included. `_turn_text_and_commands` below is `wl_admit.turn_text` plus Bash command-string capture (box 2 of PLAN-stop-hook-overhaul.md's sibling plan: "either generalize into wl_core.py ... or a small local duplicate ... with a comment flagging the duplication for a future fold-in" -- this is that local duplicate). If a worklist verb call, a `#<hex-id>` citation, or a `door:` token appears anywhere in the turn, the check stays quiet even though the phrase matched -- exactly matching this session's own correctly-handled real instance.

FAIL-SAFE AND COST, matching every sibling detector: `always=False` (HYGIENE tier, rotates), a settled-signature cache (one free forced disposition per distinct dismissal per session, not a nag on every stop), and a crash here must never crash a stop.
"""

import contextlib
import hashlib
import json
import pathlib
import re
import time
from typing import Any

import wl_common

TAIL_BYTES = 2 * 1024 * 1024

# HARMLESS ADJECTIVAL USES, measured live this session: "pre-existing docstrings", "unrelated content", "environmental bumps" and "tests pass" all badly over-fire a bare word list. Checked immediately after the matched attribution word; presence here silences the whole match.
_HARMLESS_NOUN_RE = re.compile(
    r"^[\s,]*(docstring|content|comment|bump|test)s?\b|^[\s,]*tests?\s+pass\b", re.IGNORECASE
)

# Already tracked by the repo's own shrink-only baseline mechanism (see docs/agent-reference/suppressions.md); a dismissal in the SAME CLAUSE as one of these words is not this check's business.
_BASELINE_EXEMPT_RE = re.compile(
    r"\b(baseline|ratchet(?:ed)?|floor|grandfathered)\b", re.IGNORECASE
)

_ATTRIBUTION_WORDS = r"(pre-existing|unrelated|environmental|not caused by|not my \w+)"

_VERDICT_RE = re.compile(
    r"\b(that's|this is|confirmed[,:]?)\s+(\w+\s+){0,4}?" + _ATTRIBUTION_WORDS,
    re.IGNORECASE,
)

_FINDING_NOUN_RE = re.compile(r"\b(finding|bug|defect|failure|regression)\b", re.IGNORECASE)
_ATTRIBUTION_WORD_RE = re.compile(_ATTRIBUTION_WORDS, re.IGNORECASE)

_CORROBORATION_RE = re.compile(
    r"worklist\.py\s+--(add|triage|defer|tick)\b|#[0-9a-f]{6,}|door:(operator-only|operator-deferred|no-write-access)",
    re.IGNORECASE,
)


def _is_operator_turn(rec):
    """True for a record that is the OPERATOR speaking, and nothing else. Mirrors wl_admit._is_operator_turn."""
    if rec.get("type") != "user":
        return False
    content = (rec.get("message") or {}).get("content")
    blocks = content if isinstance(content, list) else []
    return not any(isinstance(b, dict) and b.get("type") == "tool_result" for b in blocks)


def _turn_text_and_commands(path):
    """(assistant_text, [bash_command_strings]) since the last genuine operator turn.

    LOCAL DUPLICATE OF wl_admit.turn_text, extended to also capture Bash `command` argument strings -- deliberately, per this module's own design note above, rather than editing the shared walker under time pressure. A future session folding this into wl_core.py should delete this function and both callers' local copies together.
    """
    recs = wl_common.tail_records(path, TAIL_BYTES)
    if recs is None:
        return "", []
    texts: list[Any] = []
    commands: list[Any] = []
    for rec in recs:
        if _is_operator_turn(rec):
            texts, commands = [], []  # a genuine operator turn starts the window over
            continue
        if rec.get("type") != "assistant":
            continue
        for block in (rec.get("message") or {}).get("content") or []:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text" and block.get("text", "").strip():
                texts.append(block["text"])
            elif block.get("type") == "tool_use" and block.get("name") == "Bash":
                cmd = (block.get("input") or {}).get("command")
                if isinstance(cmd, str) and cmd.strip():
                    commands.append(cmd)
    return "\n\n".join(texts), commands


def deflected_findings(text):
    """[(shape, matched span)] for every dismissal in `text` not otherwise excluded.

    Recall runs first (both shapes independently), then the two exclusions apply to each hit.
    """
    hits = []
    for m in _VERDICT_RE.finditer(text or ""):
        tail = text[m.end() : m.end() + 30]
        if _HARMLESS_NOUN_RE.search(tail):
            continue
        clause_start = max(0, m.start() - 80)
        clause = text[clause_start : m.end() + 80]
        if _BASELINE_EXEMPT_RE.search(clause):
            continue
        hits.append(
            ("verdict", text[max(0, m.start() - 20) : m.end() + 40].replace("\n", " ").strip())
        )
    for m in _FINDING_NOUN_RE.finditer(text or ""):
        window = text[max(0, m.start() - 60) : m.end() + 60]
        aw = _ATTRIBUTION_WORD_RE.search(window)
        if not aw:
            continue
        tail = window[aw.end() : aw.end() + 30]
        if _HARMLESS_NOUN_RE.search(tail):
            continue
        if _BASELINE_EXEMPT_RE.search(window):
            continue
        hits.append(("finding-noun", window.replace("\n", " ").strip()))
    return hits


def corroborated(commands, text):
    """True if the turn's Bash commands or prose carry a worklist verb, a #id citation, or a door token."""
    for cmd in commands or []:
        if _CORROBORATION_RE.search(cmd):
            return True
    return bool(_CORROBORATION_RE.search(text or ""))


def turn_sig(text):
    """Stable id for a turn, so a settled dismissal is never re-asked. Mirrors wl_admit.turn_sig."""
    return hashlib.sha1((text or "").encode("utf-8", "replace")).hexdigest()[:16]


def load_settled(worklist, session_id):
    """{sig: True} of dismissals already flagged once. Corrupt state is DISCARDED. Mirrors wl_admit.load_settled."""
    p = pathlib.Path(str(worklist) + ".deflect-settled-%s.json" % (session_id or "unknown")[:8])
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("settled"), dict):
            return data["settled"]
    except (OSError, ValueError):
        pass
    return {}


def save_settled(worklist, session_id, settled):
    p = pathlib.Path(str(worklist) + ".deflect-settled-%s.json" % (session_id or "unknown")[:8])
    with contextlib.suppress(OSError):
        p.write_text(json.dumps({"settled": settled}, indent=1), encoding="utf-8")


def check(worklist, session_id, transcript_path):
    """(fired, matched_text) -- True and the dismissal's own words when an uncorroborated deflection is found and not yet settled this session.

    Never raises: every step that touches the filesystem or the transcript is already exception-safe in its own right, and the caller wraps this call in try/except anyway, matching every sibling detector.
    """
    text, commands = _turn_text_and_commands(transcript_path)
    if not text:
        return False, ""
    hits = deflected_findings(text)
    if not hits:
        return False, ""
    if corroborated(commands, text):
        return False, ""
    sig = turn_sig(text)
    settled = load_settled(worklist, session_id)
    if settled.get(sig):
        return False, ""
    settled[sig] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    save_settled(worklist, session_id, settled)
    return True, hits[0][1]

"""wl_checklist: the /handoff checklist gate over agent/programs/<slug>/CHECKLIST.md.

WHY THIS EXISTS: /handoff distills a session into an agent/programs/<slug>/ suite
and then told the FUTURE session, in prose inside PROMPT.md, to seed the
worklist. Prose is not a gate. Nothing verified that the producing session
actually wrote every deliverable, and nothing verified that the consuming
sessions ever covered the waves, so an ignored or compacted-away PROMPT.md
dropped program work silently and nobody found out.

The checklist is the machine-readable half of a handoff. Its two halves are
enforced by DIFFERENT means, and confusing them is the whole trap:

  * DELIVERABLES ARE FILE-VERIFIED, period. Every `file:<path>` token must
    exist and be non-empty. The tick is bookkeeping; the FILE is the truth,
    so a ticked-but-missing deliverable is called out louder than an
    unticked one, not quieter.
  * WAVES ARE TICK-ON-TRUST WITH STORE LINKAGE. A wave is settled by `[x]`,
    or COVERED by any live worklist item whose text carries the token
    `cl:<slug>/<wN>`. Evidence discipline then rides the existing --tick
    gate rather than being re-invented here, and no checklist state is
    written into the JSONL store (one source of truth, no reconciliation).

FAIL CLOSED, everywhere. A checklist this module cannot parse gates nothing,
so it BLOCKS rather than passing quietly (the V_CI_UNREADABLE precedent), and
an unexpected exception becomes an ALWAYS-tier violation naming itself. The
hook never WRITES a checklist: every exit is one file edit or one worklist
command a session can complete alone in a single turn.

COST: the full Stop battery reads these files, because they are the
enforcement point, and a repo with none pays exactly one glob. The poll fast
path never opens one -- checklists_sig() is stat-only and is banked in the
pollbase, so a live checklist forfeits the silent path without ever costing a
read on it.
"""

import glob
import hashlib
import os
import re
import stat

import wl_core as C
import wl_store as S
import worklist_messages as M

# Header contract, mirroring the PLAN-*.md convention (wl_checks.PLAN_STATUS_RE).
CL_HEADER_LINES = 10
CL_STATUS_RE = re.compile(r"^Status:\s*([A-Za-z-]+)\s*$", re.MULTILINE)
CL_OWNER_RE = re.compile(r"^Owner:\s*([A-Za-z0-9][A-Za-z0-9._-]{0,31})\s*$", re.MULTILINE)
# Only ' ' and 'x': leases and deferrals are worklist states, not checklist
# states, and a checklist that grew its own state machine would be a second
# store to reconcile.
CL_ITEM = re.compile(r"^\s*-\s*\[(?P<state>[ x])\]\s+(?P<id>[dw][0-9]{1,3})\s+(?P<text>\S.*)$")
# The INTENDED-checkbox detector, deliberately loose, so a typo'd item is a
# loud shape error instead of an invisible ignored line. Prose links of the
# form `- [text](url)` do NOT match: the bracket body is capped at one char.
CL_BOXLIKE = re.compile(r"^\s*-\s*\[.?\]\s")
CL_SECTION_RE = re.compile(r"^##\s+(Deliverables|Waves)\s*$", re.IGNORECASE)
CL_FILE_TOKEN = re.compile(r"\bfile:(\S+)")
# slug, item id -- the worklist-linkage token, `cl:<slug>/<wN>`. Named _LINK_
# rather than _TOKEN_ because ruff's S105 (hardcoded-password) fires on any
# string literal bound to a name containing "TOKEN", and this repo's rule is to
# fix the finding rather than to noqa past the gate.
CL_LINK_FMT = "cl:%s/%s"
CL_LIVE = ("producing", "executing")
CL_STATES = ("producing", "executing", "done", "superseded")


def checklist_paths(root):
    """Every agent/programs/<slug>/CHECKLIST.md, sorted. One glob is the entire
    cost of this module for a repo that keeps no handoffs."""
    return sorted(glob.glob(os.path.join(str(root), "agent", "programs", "*", "CHECKLIST.md")))


def _rel(root, path):
    try:
        return os.path.relpath(path, str(root))
    except ValueError:
        return str(path)


def checklists_sig(root):
    """A STAT-ONLY signature of every checklist: sha1 over sorted
    (relpath, mtime_ns, size).

    Never opens a file, and that is a contract rather than an optimisation:
    this is what the poll fast path compares against its banked baseline, and
    a poll that read files would pay the cost the fast path exists to avoid.
    A path that cannot be stat'd contributes a sentinel instead of raising, so
    a permission-denied checklist still MOVES the signature (which forfeits
    the silent path) rather than wedging the poll.
    """
    h = hashlib.sha1()
    for path in checklist_paths(root):
        rel = _rel(root, path)
        try:
            st = os.stat(path)
            row = (rel, st.st_mtime_ns, st.st_size)
        except OSError:
            row = (rel, -1, -1)
        h.update(("%s|%d|%d\n" % row).encode("utf-8", "replace"))
    return h.hexdigest()[:16]


def _err(lineno, line, why):
    return "line %d: %s -- %s" % (lineno, (line or "").strip()[:80], why)


def parse_checklist(root, path):
    """{path, rel, slug, status, owner, deliverables, waves, errors}.

    EVERY shape problem is collected, never the first one only: a session
    handed one error per stop would pay one turn per typo. `status` is the
    lowercased value and is empty when the header is unusable, which the
    caller reads as malformed rather than as a state.
    """
    out = {
        "path": str(path),
        "rel": _rel(root, path),
        "slug": os.path.basename(os.path.dirname(str(path))),
        "status": "",
        "owner": "",
        "deliverables": [],
        "waves": [],
        "errors": [],
    }
    with open(str(path), encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    lines = text.splitlines()
    header = "\n".join(lines[:CL_HEADER_LINES])

    m = CL_STATUS_RE.search(header)
    if not m:
        out["errors"].append(
            _err(
                1,
                lines[0] if lines else "",
                "no 'Status:' line in the first %d lines" % CL_HEADER_LINES,
            )
        )
    else:
        st_val = m.group(1).strip().lower()
        if st_val not in CL_STATES:
            out["errors"].append(
                _err(
                    header.count("\n", 0, m.start()) + 1,
                    m.group(0),
                    "unknown Status '%s'; expected one of %s" % (st_val, ", ".join(CL_STATES)),
                )
            )
        else:
            out["status"] = st_val
    mo = CL_OWNER_RE.search(header)
    if mo:
        out["owner"] = mo.group(1)
    elif out["status"] == "producing":
        out["errors"].append(
            _err(1, lines[0] if lines else "", "no 'Owner:' line while 'Status: producing'")
        )

    section, seen = None, {}
    for n, line in enumerate(lines, 1):
        ms = CL_SECTION_RE.match(line)
        if ms:
            section = ms.group(1).lower()
            continue
        if line.startswith("#"):
            section = None  # any other heading ends the section it followed
            continue
        mi = CL_ITEM.match(line)
        if not mi:
            if CL_BOXLIKE.match(line):
                out["errors"].append(
                    _err(
                        n,
                        line,
                        "not a checklist item; expected '- [ ] d1 file:<path>' "
                        "or '- [ ] w1 <title>'",
                    )
                )
            continue
        iid, body = mi.group("id"), mi.group("text").strip()
        if section is None:
            out["errors"].append(
                _err(n, line, "item sits outside '## Deliverables' and '## Waves'")
            )
            continue
        want = "d" if section == "deliverables" else "w"
        if iid[0] != want:
            out["errors"].append(
                _err(
                    n,
                    line,
                    "id '%s' does not belong under that section (expected a '%s' prefix)"
                    % (iid, want),
                )
            )
            continue
        if iid in seen:
            out["errors"].append(
                _err(n, line, "duplicate id '%s', first seen on line %d" % (iid, seen[iid]))
            )
            continue
        seen[iid] = n
        item = {"id": iid, "ticked": mi.group("state") == "x", "text": body}
        if want == "d":
            item["files"] = CL_FILE_TOKEN.findall(body)
            if not item["files"]:
                out["errors"].append(
                    _err(
                        n,
                        line,
                        "deliverable carries no 'file:<path>' token, so nothing verifies it",
                    )
                )
                continue
            out["deliverables"].append(item)
        else:
            out["waves"].append(item)
    return out


def verify_files(root, files):
    """[(token, 'ok'|'missing'|'empty')] for the file: tokens of one item.

    A zero-byte file is EMPTY and named distinctly from MISSING, because the
    two have different causes (a write that never happened versus one that
    was truncated) and reading them as one hid a truncated PROMPT.md. A path
    that exists but is not a regular file reads as missing: a directory is
    not a deliverable.
    """
    out = []
    for tok in files:
        p = os.path.expanduser(tok)
        full = p if os.path.isabs(p) else os.path.join(str(root), p)
        try:
            st = os.stat(full)
        except OSError:
            out.append((tok, "missing"))
            continue
        if not stat.S_ISREG(st.st_mode):
            out.append((tok, "missing"))
        elif st.st_size == 0:
            out.append((tok, "empty"))
        else:
            out.append((tok, "ok"))
    return out


def _deliverable_rows(root, parsed):
    """(rows, met, total) -- one row per file: token that does not verify."""
    rows, met = [], 0
    for d in parsed["deliverables"]:
        bad = [(t, v) for t, v in verify_files(root, d["files"]) if v != "ok"]
        if not bad:
            met += 1
            continue
        rows.extend("    %s %s -- %s" % (d["id"], t, v.upper()) for t, v in bad)
    return rows, met, len(parsed["deliverables"])


def _covering_items(fold, token):
    """Live store records whose text carries the linkage token.

    Word-bounded and literal-escaped, so `cl:demo/w1` never matches
    `cl:demo/w10`. Any live state counts as coverage: an open item, a lease
    and a deferral are all somebody having CLAIMED the wave, which is exactly
    what an uncovered wave lacks.
    """
    rx = re.compile(r"\b%s\b" % re.escape(token))
    return [
        rec
        for rec in (getattr(fold, "items", None) or [])
        if rx.search(rec.get("line") or rec.get("text") or "")
    ]


# The three doors from CLAUDE.md's findings rule. Closing an item through one
# means "no session can do this", NOT "this is finished": operator-only powers
# (secrets, purchases, production deploys), an explicit operator deferral, or a
# target outside this session's write access.
_DOOR_RX = re.compile(r"\bdoor:(?:operator-only|operator-deferred|no-write-access)\b")


def _closed_through_door(rec):
    """True when this record was ticked by naming a door rather than by doing it."""
    blob = "%s %s" % (rec.get("text") or "", rec.get("lastnote") or "")
    return bool(_DOOR_RX.search(blob))


def _wave_rows(fold, parsed, session_id, actor=None):
    """Problem rows for the unticked waves, each carrying its one-command exit.

    `actor` is whose prefix the `--add` exit names. It defaults to this session,
    which is right whenever this session is the one that must act. On a FOREIGN
    checklist it is the owner's prefix instead: the row is then a description of
    what that session will do, not an instruction to this one. Naming the reader
    there would contradict the advisory in the same breath -- "the owner creates
    these items" directly above a command that claims them for somebody else.
    """
    me8 = (actor or session_id or "unknown")[:8]
    slug, rel, rows = parsed["slug"], parsed["rel"], []
    for w in parsed["waves"]:
        if w["ticked"]:
            continue
        token = CL_LINK_FMT % (slug, w["id"])
        matches = _covering_items(fold, token)
        if not matches:
            # Quotes are stripped from the title because the exit is a shell
            # command, and an exit a reader has to repair is not an exit.
            title = w["text"][:60].replace("'", "").replace('"', "")
            rows.append(
                "    %s UNCOVERED: no worklist item carries '%s'\n"
                "        NEXT: .claude/hooks/stop/worklist.py --add %s '%s %s'"
                % (w["id"], token, me8, token, title)
            )
        elif all((r.get("state") or "") == "x" for r in matches):
            # A wave whose only covering items were closed through a DOOR is
            # correctly unticked, and demanding its tick would be demanding a
            # lie. `door:operator-only` means the secrets are unset, the machines
            # unmigrated and the cutover unrun -- the item left the session, the
            # WORK did not happen. This checklist's own comment block says an
            # overstating handoff is worse than an incomplete one, because the
            # next session reads it as ground truth. So: covered, not done, no
            # row. Ticking the box is the operator's to do once the door opens.
            if any(_closed_through_door(r) for r in matches):
                continue
            ids = ", ".join("#%s" % r.get("id") for r in matches)
            rows.append(
                "    %s DONE-BUT-UNTICKED: store item %s is done with evidence; "
                "tick '- [x] %s' in %s" % (w["id"], ids, w["id"], rel)
            )
    return rows


def _door_parked_rows(fold, parsed):
    """Rows for unticked waves whose covering items were ALL closed through a door.

    _wave_rows above skips these on purpose and the reasoning there is right:
    the work did not happen, no session can make it happen, and demanding a tick
    would be demanding a lie. But it skipped them into TOTAL silence, and that
    is a different claim. Such a wave emits no violation, and its covering item
    is `[x]` so it has also left `--list --open`: nothing in the machinery
    surfaces it again, ever.

    What kept `cl:backup-storage/w8` (the credentialed cutover legs) visible for
    a whole day was one session choosing to write it into STATE.md and into
    every report. That is discipline, not a control, and the doors exist
    precisely because discipline is what fails across a compaction. So these are
    reported as an ADVISORY: never blocking, because nothing here can act on
    them, but never silent either, because the operator can.
    """
    slug, rows = parsed["slug"], []
    for w in parsed["waves"]:
        if w["ticked"]:
            continue
        matches = _covering_items(fold, CL_LINK_FMT % (slug, w["id"]))
        if not matches or not all((r.get("state") or "") == "x" for r in matches):
            continue
        doors = [r for r in matches if _closed_through_door(r)]
        if not doors:
            continue
        why = ", ".join(sorted({_door_name(r) for r in doors}))
        rows.append("    %s [%s] %s" % (w["id"], why, w["text"][:70].rstrip(" -\u2014")))

    return rows


def _door_name(rec):
    """The door a record names, for the advisory. 'a door' when it cannot be read
    -- the row is worth printing even when the reason is unparseable."""
    m = _DOOR_RX.search(" ".join(str(v) for v in rec.values() if isinstance(v, str)))

    return m.group(0) if m else "a door"


def _adopt_hint(owner, projects_dir, rel):
    """The adoption sentence for a foreign checklist whose owner is dead, "" otherwise."""
    try:
        age = S.owner_age_hours(owner, projects_dir)
    except Exception:  # noqa: BLE001 -- an advisory hint must never break the gate
        age = None
    if age is None or age < float(os.environ.get("WORKLIST_DEAD_HOURS", "24")):
        return ""
    return (
        " That session's transcript has been idle %dh, so the handoff is very "
        "likely abandoned: adopt it by editing the 'Owner:' line of %s to your "
        "own prefix, or set 'Status: superseded' if the program is dead." % (int(age), rel)
    )


def _ckey(prefix, slug):
    """The finding key for ONE checklist: `<check-class>:<slug>`.

    A FIXED key per check class was the bug (automated review, PR #563). Two
    things downstream read the key as an identity, and both starve the second
    checklist rather than delaying it:

      * the focused block's rotation (wl_checks.py) ties-breaks on
        `order = {v[0]: i for ...}`, a dict comp in which duplicate keys
        COLLAPSE, so two violations sharing a key get identical sort tuples and
        `min` returns the first one on every stop, forever;
      * outq_add finds a non-sticky entry by key alone, so the second
        advisory's text OVERWRITES the first's instead of queueing beside it.

    Two concurrent handoffs is an ordinary state here, so the second one simply
    vanished into the "N more outstanding" count. Scoping by slug costs
    nothing: the rotation prunes any key that is no longer outstanding, so a
    settled checklist's key leaves `served` on the next stop. The PREFIX is
    preserved verbatim so a grep on the check class still matches.
    """
    return "%s:%s" % (prefix, slug)


def _adjudicate(root, path, fold, session_id, projects_dir):
    """(violations, advisories, live) for ONE checklist. See checklist_findings."""
    v, a = [], []
    parsed = parse_checklist(root, path)
    rel, slug, status, owner = parsed["rel"], parsed["slug"], parsed["status"], parsed["owner"]
    if parsed["errors"]:
        # A malformed checklist is adjudicated NO FURTHER: every verdict below
        # would be read off a file the parser has already said it misread.
        rows = "\n".join("    " + e for e in parsed["errors"])
        return [(_ckey("cl-shape", slug), False, M.V_CL_SHAPE % (rel, rows))], a, 1
    if status == "superseded":
        return v, a, 0  # the terminal escape for an abandoned program
    drows, met, total = _deliverable_rows(root, parsed)

    if status == "done":
        rows = list(drows)
        rows.extend(
            "    wave %s is not ticked, yet the checklist claims done" % w["id"]
            for w in parsed["waves"]
            if not w["ticked"]
        )
        if not rows:
            return v, a, 0
        if C.owned_by_me(owner or None, session_id):
            v.append(
                (
                    _ckey("cl-flip", slug),
                    False,
                    M.V_CL_FLIP % (rel, "done", "\n".join(rows), rel),
                )
            )
        else:
            a.append(
                (
                    _ckey("cl-foreign", slug),
                    M.N_CL_FOREIGN_DRIFT % (rel, "done", owner, "\n".join(rows)),
                    2,
                )
            )
        return v, a, 1

    if status == "producing":
        # Owner is guaranteed present here: its absence is a shape error above.
        if C.same_session(owner, session_id):
            if drows:
                v.append(
                    (
                        _ckey("cl-producing", slug),
                        False,
                        M.V_CL_PRODUCING % (slug, met, total, "\n".join(drows), rel),
                    )
                )
            else:
                v.append((_ckey("cl-producing", slug), False, M.V_CL_PRODUCING_DONE % (slug, rel)))
        else:
            a.append(
                (
                    _ckey("cl-foreign", slug),
                    M.N_CL_FOREIGN % (slug, owner, _adopt_hint(owner, projects_dir, rel)),
                    2,
                )
            )
        return v, a, 1

    # executing: two INDEPENDENT checks, because a program can lose an
    # artifact and drop a wave at the same time and each has its own exit.
    if drows:
        # Deliverables are re-verified regardless of their ticks, which is what
        # catches both a ticked-but-missing artifact and one deleted after the flip.
        if C.owned_by_me(owner or None, session_id):
            v.append(
                (
                    _ckey("cl-flip", slug),
                    False,
                    M.V_CL_FLIP % (rel, "executing", "\n".join(drows), rel),
                )
            )
        else:
            a.append(
                (
                    _ckey("cl-foreign", slug),
                    M.N_CL_FOREIGN_DRIFT % (rel, "executing", owner, "\n".join(drows)),
                    2,
                )
            )
    _foreign_owner = bool(owner) and not C.owned_by_me(owner or None, session_id)
    wrows = _wave_rows(fold, parsed, session_id, actor=owner if _foreign_owner else None)
    if not wrows and not drows and all(w["ticked"] for w in parsed["waves"]):
        wrows = ["    everything is settled; set 'Status: done' in %s" % rel]
    if wrows:
        # OWNERSHIP-GATED SINCE 2026-08-23, and the comment it replaces argued
        # the opposite: "an uncovered wave is UNCLAIMED work, the same semantics
        # as an untagged worklist item, so it blocks whoever tries to stop."
        # That analogy is exactly right for a checklist with NO owner and wrong
        # for one that names a live session. An untagged item has no owner; a
        # handoff with `Owner: <prefix>` has one that simply has not created the
        # item yet, which is what an owner does WHEN IT STARTS THE WAVE.
        #
        # Measured, not argued: on 2026-08-23 the www-round5 handoff
        # (`Owner: a68f3ab4`, Status: executing) blocked an unrelated pr-babysit
        # session in the same worktree. Its four exits all read
        # `--add <this session> ...`, so the only offered way to stop was to
        # claim four waves of work this session was not doing -- and a
        # self-tagged item then blocks ITS stops until ticked with evidence.
        # The owner was live throughout: its transcript was being written that
        # minute. This is the same rule CLAUDE.md already states for worklist
        # items -- other sessions' open items are REPORTED, never blocked on --
        # applied to the artifact that carries them.
        #
        # Blocking is preserved where the analogy holds: no owner at all, the
        # owner is me, or the owner is provably dead (the adopt hint then says
        # how to take it over). UNKNOWN counts as alive, deliberately, because
        # `owner_age_hours` answers None for a session whose transcript lives in
        # a different project directory -- true for every session predating this
        # repo's move, which is precisely the population most likely to own an
        # old handoff. Accusing an unverifiable owner of being dead is the
        # failure this codebase refuses everywhere else.
        foreign = _foreign_owner
        hint = _adopt_hint(owner, projects_dir, rel) if foreign else ""
        if foreign and not hint:
            a.append(
                (
                    _ckey("cl-foreign-waves", slug),
                    M.N_CL_FOREIGN_WAVES % (slug, rel, owner, "\n".join(wrows) + "\n", ""),
                    2,
                )
            )
        else:
            v.append(
                (
                    _ckey("cl-waves", slug),
                    False,
                    M.V_CL_WAVES % (slug, rel, "\n".join(wrows)) + hint,
                )
            )
    # Door-parked waves: reported, never blocked on. _wave_rows skips them for
    # the right reason and into the wrong silence -- see _door_parked_rows.
    # NOT ownership-gated, for the same reason the wave check is not: whoever is
    # here is the one who can tell the operator, and the operator is the only
    # party who can open the door.
    prows = _door_parked_rows(fold, parsed)
    if prows:
        a.append(
            (
                _ckey("cl-door", slug),
                M.N_CL_DOOR_PARKED % (rel, len(prows), "\n".join(prows)),
                2,
            )
        )
    return v, a, 1


def checklist_findings(root, fold, session_id, projects_dir):
    """(violations, advisories, live_count) for every checklist in the repo.

    violations are (key, always, text) ready for run_stop's vadd; advisories
    are (key, text, prio) ready for outq_add. live_count is what the poll
    fast path banks: 0 means no checklist can block, so a poll may still take
    the silent path.

    NEVER RAISES. Any unexpected exception becomes the ALWAYS-tier unreadable
    violation and counts as live, because a gate that went blind must say so
    and must not also hand the poll path a clean baseline.
    """
    violations, advisories, live = [], [], 0
    try:
        paths = checklist_paths(root)
    except Exception as exc:  # noqa: BLE001 -- fail CLOSED
        # UNSCOPED, and deliberately so: the glob itself failed, so there is no
        # slug to scope by, and this path returns immediately -- at most one
        # such finding can exist per stop, so it has nothing to collide with.
        return [("cl-shape", True, M.V_CL_UNREADABLE % str(exc)[:160])], [], 1
    for path in paths:
        try:
            v, a, n = _adjudicate(root, path, fold, session_id, projects_dir)
        except Exception as exc:  # noqa: BLE001 -- fail CLOSED, per file
            # Per FILE, so scoped like every other per-checklist finding. The
            # slug is read off the path rather than out of the parse, because
            # the parse is what just threw.
            slug = os.path.basename(os.path.dirname(str(path)))
            violations.append((_ckey("cl-shape", slug), True, M.V_CL_UNREADABLE % str(exc)[:160]))
            live += 1
            continue
        violations.extend(v)
        advisories.extend(a)
        live += n
    return violations, advisories, live


def checklists_block(root):
    """(listing, n): one line per live-or-malformed checklist, for
    SessionStart and PostCompact. ("", 0) when there is nothing to say, so a
    repo without handoffs emits no block at all.

    Reading files HERE is fine: these two events fire once each, unlike the
    poll path this module is otherwise careful never to charge.
    """
    lines = []
    for path in checklist_paths(root):
        rel = _rel(root, path)
        try:
            p = parse_checklist(root, path)
        except Exception:  # noqa: BLE001 -- name it, never drop it
            lines.append("  %s [UNREADABLE] the Stop hook will block on this one" % rel)
            continue
        malformed = bool(p["errors"])
        if not malformed and p["status"] not in CL_LIVE:
            continue
        met = sum(
            1
            for d in p["deliverables"]
            if all(v == "ok" for _t, v in verify_files(root, d["files"]))
        )
        settled = sum(1 for w in p["waves"] if w["ticked"])
        lines.append(
            "  %s [%s] owner=%s deliverables %d/%d verified, waves %d/%d settled"
            % (
                rel,
                "MALFORMED" if malformed else p["status"],
                p["owner"] or "-",
                met,
                len(p["deliverables"]),
                settled,
                len(p["waves"]),
            )
        )
    return "\n".join(lines), len(lines)

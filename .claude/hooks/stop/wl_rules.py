"""wl_rules: the plumbing shared by the judged stop rules.

Two things live here, both needed by wl_classsweep and wl_bravedefault, and neither written twice -- writing it twice is precisely the defect wl_classsweep exists to catch.

  Demand      a per-checkout, TTL'd, hard-capped "you still owe this" marker,
              because an order issued on one stop has to survive onto the next:
              the signal that raised it is de-duplicated and will not raise it
              again.
  apply_order how a rule writes its finding into a judge verdict WITHOUT
              destroying one that is already there. See its docstring; it is
              the difference between adding a demand and replacing the judge.

WHY A FILE AND NOT A TRACKED ITEM. The durable mechanism this repo actually uses
for "you still owe this" is a worklist item, whose creation needs the session id
and the store handle -- both of which live in wl_checks, which the change that introduced these rules deliberately did not touch. A file marker is the weaker substitute, so it is bounded hard enough that it can never wedge a session: past `max_fires`, or past `ttl_min`, the demand simply stops existing.

Keyed by the checkout path, so two worktrees never share a demand, and stored under the judge's own scratch dir, which the harness already owns.
"""

import contextlib
import hashlib
import json
import os
import pathlib
import re
import time

# -- What a model-authored order is allowed to tell a session to DO ----------
#
# BOTH judged rules interpolate model text into an order the session then acts on, so the question "may this order write?" belongs here rather than in either one. It is answered DIFFERENTLY by each, and the difference is the whole point:
#
# wl_classsweep a sweep ENUMERATES. It has an intrinsic read-only guarantee, so the full write set is refused. wl_bravedefault a braver DEFAULT may legitimately write -- "delete the stale baseline entries" is exactly the kind of action that rule exists to push a session toward -- so only TREE_DESTROYING is refused. That subset is never acceptable on any path in this repo: the
# working tree carries other sessions' uncommitted work, and a brave DEFAULT is worse than a sweep order because it EXECUTES on a timer with nobody reading it first.
WRITE_VERBS = frozenset(
    (
        "rm",
        "rmdir",
        "mv",
        "cp",
        "dd",
        "truncate",
        "shred",
        "install",
        "chmod",
        "chown",
        "chgrp",
        "ln",
        "mkdir",
        "touch",
        "tee",
        "kill",
        "pkill",
        "reboot",
        "shutdown",
    )
)
# git subcommands that discard work or publish. `git grep` / `git ls-files` are what a sweep should use, so git itself is never denied -- only these second words.
WRITE_GIT = frozenset(
    ("checkout", "restore", "stash", "clean", "reset", "rm", "mv", "push", "commit")
)
# The subset that destroys work nobody can get back. Forbidden everywhere.
TREE_DESTROYING = frozenset(("checkout", "restore", "stash", "clean", "reset"))


def names_write(text, verbs=None, git_subs=None):
    """The write verb this PROSE names, or "".

    Word boundaries are load-bearing in both directions: "remove the duplicate line" must not trip on `rm` and "move the check" must not trip on `mv`, while "rm the stale entries" and "git clean -xdf" must. An instruction is prose, where ordinary English words are expected.
    """
    verbs = WRITE_VERBS if verbs is None else verbs
    git_subs = WRITE_GIT if git_subs is None else git_subs
    low = " %s " % (text or "").lower().replace("`", " ").replace("\n", " ")
    for verb in sorted(verbs):
        if re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(verb), low):
            return verb
    for sub in sorted(git_subs):
        if re.search(r"(?<![\w-])git\s+%s(?![\w-])" % re.escape(sub), low):
            return "git %s" % sub
    if verbs is WRITE_VERBS and re.search(r"(?<![\w-])-delete(?![\w-])", low):
        return "-delete"
    return ""


def names_tree_destroying(text):
    """Only the git verbs that destroy uncommitted work. No plain-verb set."""
    return names_write(text, verbs=frozenset(), git_subs=TREE_DESTROYING)


# ACTS THIS REPO RESERVES TO AN EXPLICIT OPERATOR ASK. CLAUDE.md's first standing order is that the deliverable is an UNCOMMITTED working tree: no commit, no branch, no push, no PR unless the operator asked for it in that task, and approving a plan is not that ask. So an order that tells a session to commit is a rule instructing a standing-order violation -- which is exactly what
# happened on 2026-09-02, when the brave-default rule's own next_action read "Rename ... then commit to the open branch" and the session silently did the rename part only. A rule that has to be quietly disobeyed is a broken rule.
#
# PROSE, NOT ARGV. The offending text was "commit to the open branch" with no `git` in it, so the git-subcommand matcher above could never have seen it. Hence a phrase matcher: it wants the version-control sense of the word and not the ordinary English one, because "commit to option A" means DECIDE and is precisely the bravery this rule exists to encourage.
OPERATOR_RESERVED_RE = re.compile(
    r"(?<![\w-])(?:"
    r"git\s+(?:commit|push|merge|tag)"
    r"|commit(?:s|ed|ting)?\s+(?:it|them|that|this|the\b|these\b|onto\b|on\s+the\b"
    r"|to\s+(?:the\s+)?(?:open\s+)?(?:pr\b|branch\b|main\b))"
    r"|(?:leave|left)\s+(?:it|them)\s+committed"
    r"|push(?:es|ed|ing)?\s+(?:it|them|to\s|onto\s)"
    r"|open(?:s|ed|ing)?\s+(?:a|the)\s+(?:pr\b|pull\s+request)"
    r"|cut(?:s|ting)?\s+(?:a|the)\s+release"
    r")",
    re.IGNORECASE,
)


def names_operator_reserved(text):
    """The commit/push/PR phrase this PROSE names, or "".

    Not a safety guard like `names_tree_destroying` -- nothing here destroys anything. It is a STANDING-ORDER guard: these acts need the operator's ask, so a generated order must never contain one.
    """
    m = OPERATOR_RESERVED_RE.search((text or "").replace("`", " ").replace("\n", " "))
    return " ".join(m.group(0).split()) if m else ""


def scope_grounded(text, fixset_files):
    """True when `text` plausibly names something in the real fix-set, or when there is nothing to check against.

    Written for wl_proofcheck/wl_classsweep's own fired findings, ANNOTATING never SUPPRESSING (see agent/plans/PLAN-judge-prompt-trap-conflation.md): a judge fabricated a "bulk transform" naming files that did not exist in the tree, twice in one session, pattern-matching a worked example instead of the actual diff. `fixset_files is None` means the computation was UNAVAILABLE and
    must never be read as "ungrounded" -- only a SUCCESSFULLY COMPUTED empty list counts as "nothing changed", so a caller that has not adopted the parameter yet, or hit a git error, gets the pre-existing behavior (no caveat) rather than a false accusation.
    """
    if fixset_files is None:
        return True
    if not fixset_files:
        return False
    low = (text or "").lower()
    for f in fixset_files:
        if f.lower() in low or any(part and part in low for part in f.lower().split("/")):
            return True
    return False


# A demand displaced into the `owed` slot may be carried forward at most this many times before it is dropped rather than carried again -- the bound named in agent/plans/PLAN-sweep-obligation-carry-forward.md task 6, shared by every Demand instance because the unbounded-nag failure it guards against is the same shape for a sweep and for a proof obligation.
CARRY_MAX = 2


def _carry_candidate(head):
    """The `owed`-shaped record `head` becomes on displacement, or None when its own carry count already caps out. `head`'s `at` is left untouched -- the TTL keeps running from wherever it already was, never refreshed by a displacement."""
    if not isinstance(head, dict):
        return None
    try:
        carried = int(head.get("carried", 0)) + 1
    except (TypeError, ValueError):
        return None
    if carried > CARRY_MAX:
        return None
    out = {k: v for k, v in head.items() if k not in ("owed", "fires", "carried")}
    out["carried"] = carried
    return out


def _newer_of(a, b):
    """Whichever of two owed-candidates has the more recent `at`; None-safe. Used when a displacement finds the single `owed` slot already occupied: the OLDER of the two is dropped, since it has already had its one reminder and is closest to its own TTL (see the plan's task 3/6)."""
    if not isinstance(a, dict):
        return b if isinstance(b, dict) else None
    if not isinstance(b, dict):
        return a
    try:
        return a if float(a.get("at", 0)) >= float(b.get("at", 0)) else b
    except (TypeError, ValueError):
        return a


class Demand:
    """One rule's outstanding-order marker. Every read fails toward "nothing owed".

    A marker holds a HEAD demand (the one actively being asked about) and, in at most one `owed` slot, a demand a fresh fire displaced rather than lost. `bank` re-fires the head in place (a follow-up on the SAME class); `displace` fires a NEW head and files whatever head existed into `owed`, bounded by CARRY_MAX and by the single-slot capacity; `promote` is called when the head is discharged and moves a live `owed` record up to become the new head.
    """

    def __init__(self, name, ttl_min, max_fires):
        self.name = name
        self.ttl_min = ttl_min
        self.max_fires = max_fires

    def path(self, cwd=None):
        base = pathlib.Path(os.environ.get("TMPDIR", "/tmp")) / "claude-worklist" / ".judge"
        key = hashlib.sha1((cwd or os.getcwd()).encode("utf-8", "replace")).hexdigest()[:12]
        return base / ("%s-%s.json" % (self.name, key))

    def _raw(self, path=None):
        """The whole stored dict, TTL and shape unchecked. For `promote`/`displace`, which need to see a possibly-expired head's own `owed` slot."""
        try:
            d = json.loads((path or self.path()).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return d if isinstance(d, dict) else None

    def _read(self, path=None):
        d = self._raw(path)
        if d is None or not isinstance(d.get("fires"), int):
            return None
        try:
            if time.time() - float(d.get("at", 0)) > self.ttl_min * 60:
                return None
        except (TypeError, ValueError):
            return None
        return d

    def peek(self, path=None):
        """The raw record, cap ignored. For a rule whose cap suppresses the FIRE rather than the demand -- it still has to see the count it is capped at."""
        return self._read(path)

    def load(self, path=None):
        """The live demand, or None. A demand at its cap no longer exists."""
        d = self._read(path)
        if d is None or d["fires"] >= self.max_fires:
            return None
        return d

    def fires(self, path=None):
        """How many times this rule has already fired on this demand. Stale is 0."""
        d = self._read(path)
        return d["fires"] if d else 0

    def bank(self, fields, prior=None, path=None):
        """Re-fire the head demand in place: same class, one more fire. The prior record's `owed` slot rides through untouched -- a follow-up re-fire on the head is not a displacement and must not disturb whatever is parked. `prior`'s own `carried` count (set only when this head was itself promoted from a prior displacement) rides through too, so a LATER displacement of this same head still remembers how many times it has already been carried."""
        p = path or self.path()
        with contextlib.suppress(OSError):
            p.parent.mkdir(parents=True, exist_ok=True)
            payload = dict(fields)
            payload["fires"] = int((prior or {}).get("fires", 0)) + 1
            payload["at"] = time.time()
            # THE FIRST FIRE'S TIME rides through a re-fire, because `at` moves on every bank and evidence the session produced between two fires is still evidence (agent/plans/PLAN-stop-hook-retro-20260924.md R.2).
            payload["first_at"] = (
                (prior or {}).get("first_at") or (prior or {}).get("at") or payload["at"]
            )
            payload["owed"] = (prior or {}).get("owed")
            if prior and "carried" in prior:
                payload["carried"] = prior["carried"]
            p.write_text(json.dumps(payload, indent=1), encoding="utf-8")

    def displace(self, fields, head=None, path=None):
        """Fire a NEW head demand, preserving `head` (today's head, if any) in the single `owed` slot rather than destroying it. `head` should be the record `load`/`peek` returned before this call -- its own `owed` slot (something displaced earlier) competes for the same one slot, and the older of the two loses per `_newer_of`."""
        p = path or self.path()
        with contextlib.suppress(OSError):
            p.parent.mkdir(parents=True, exist_ok=True)
            existing_owed = head.get("owed") if isinstance(head, dict) else None
            owed = _newer_of(_carry_candidate(head), existing_owed)
            payload = dict(fields)
            payload["fires"] = 1
            payload["at"] = time.time()
            payload["first_at"] = payload["at"]
            payload["owed"] = owed
            p.write_text(json.dumps(payload, indent=1), encoding="utf-8")

    def promote(self, path=None):
        """Discharge the head demand; if a live (non-expired) `owed` record is waiting, it becomes the new head. Fails toward nothing owed: a missing, malformed or TTL-expired `owed` slot is dropped silently, never raised."""
        p = path or self.path()
        raw = self._raw(p)
        owed = raw.get("owed") if isinstance(raw, dict) else None
        if not isinstance(owed, dict):
            self.clear(p)
            return
        try:
            expired = time.time() - float(owed.get("at", 0)) > self.ttl_min * 60
        except (TypeError, ValueError):
            expired = True
        if expired:
            self.clear(p)
            return
        with contextlib.suppress(OSError):
            p.parent.mkdir(parents=True, exist_ok=True)
            # `carried` rides along rather than being reset: it is how a demand promoted back to head remembers it was already displaced once, so a SECOND displacement can still hit CARRY_MAX and a THIRD is refused rather than restarting the count from zero.
            payload = dict(owed)
            payload.setdefault("fires", 1)
            payload["owed"] = None
            p.write_text(json.dumps(payload, indent=1), encoding="utf-8")

    def clear(self, path=None):
        with contextlib.suppress(OSError):
            (path or self.path()).unlink(missing_ok=True)


def still_owed_sentence(label, detail):
    """The deterministic "STILL OWED" clause appended to a displacing stop's reason (plan task 4/121): code-authored text built only from a class and search/scope this same rule already validated when the demand first fired -- never a re-emission of fresh model text."""
    return " STILL OWED: %s -- %s" % ((label or "")[:160], (detail or "")[:160])


def apply_order(out, reason, action):
    """Write a rule's finding into a judge verdict. Returns nothing; mutates.

    A STOP becomes a CONTINUE carrying this rule's reason and order, which is how the rule blocks: wl_checks turns any "continue" into a block.

    A verdict that is ALREADY "continue" is APPENDED to, never overwritten. The judge's own order ("three items are open, work #a1b2") is not less important than a rule's, and a rule that clobbered it would trade one true instruction
    for another and hide the trade. The session then sees both, and the block it
    was getting anyway now carries the extra finding.
    """
    if out.get("verdict") == "continue":
        out["reason"] = ("%s  ALSO: %s NEXT: %s" % (out.get("reason", ""), reason, action))[:700]
        return
    out["verdict"] = "continue"
    out["reason"] = reason[:400]
    out["next_action"] = action[:200]

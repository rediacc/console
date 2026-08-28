"""wl_rules: the plumbing shared by the judged stop rules.

Two things live here, both needed by wl_classsweep and wl_bravedefault, and
neither written twice -- writing it twice is precisely the defect wl_classsweep
exists to catch.

  Demand      a per-checkout, TTL'd, hard-capped "you still owe this" marker,
              because an order issued on one stop has to survive onto the next:
              the signal that raised it is de-duplicated and will not raise it
              again.
  apply_order how a rule writes its finding into a judge verdict WITHOUT
              destroying one that is already there. See its docstring; it is
              the difference between adding a demand and replacing the judge.

WHY A FILE AND NOT A TRACKED ITEM. The durable mechanism this repo actually uses
for "you still owe this" is a worklist item, whose creation needs the session id
and the store handle -- both of which live in wl_checks, which the change that
introduced these rules deliberately did not touch. A file marker is the weaker
substitute, so it is bounded hard enough that it can never wedge a session: past
`max_fires`, or past `ttl_min`, the demand simply stops existing.

Keyed by the checkout path, so two worktrees never share a demand, and stored
under the judge's own scratch dir, which the harness already owns.
"""

import contextlib
import hashlib
import json
import os
import pathlib
import time


class Demand:
    """One rule's outstanding-order marker. Every read fails toward "nothing owed"."""

    def __init__(self, name, ttl_min, max_fires):
        self.name = name
        self.ttl_min = ttl_min
        self.max_fires = max_fires

    def path(self, cwd=None):
        base = pathlib.Path(os.environ.get("TMPDIR", "/tmp")) / "claude-worklist" / ".judge"
        key = hashlib.sha1((cwd or os.getcwd()).encode("utf-8", "replace")).hexdigest()[:12]
        return base / ("%s-%s.json" % (self.name, key))

    def _read(self, path=None):
        try:
            d = json.loads((path or self.path()).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(d, dict) or not isinstance(d.get("fires"), int):
            return None
        try:
            if time.time() - float(d.get("at", 0)) > self.ttl_min * 60:
                return None
        except (TypeError, ValueError):
            return None
        return d

    def peek(self, path=None):
        """The raw record, cap ignored. For a rule whose cap suppresses the FIRE
        rather than the demand -- it still has to see the count it is capped at."""
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
        p = path or self.path()
        with contextlib.suppress(OSError):
            p.parent.mkdir(parents=True, exist_ok=True)
            payload = dict(fields)
            payload["fires"] = int((prior or {}).get("fires", 0)) + 1
            payload["at"] = time.time()
            p.write_text(json.dumps(payload, indent=1), encoding="utf-8")

    def clear(self, path=None):
        with contextlib.suppress(OSError):
            (path or self.path()).unlink(missing_ok=True)


def apply_order(out, reason, action):
    """Write a rule's finding into a judge verdict. Returns nothing; mutates.

    A STOP becomes a CONTINUE carrying this rule's reason and order, which is
    how the rule blocks: wl_checks turns any "continue" into a block.

    A verdict that is ALREADY "continue" is APPENDED to, never overwritten. The
    judge's own order ("three items are open, work #a1b2") is not less important
    than a rule's, and a rule that clobbered it would trade one true instruction
    for another and hide the trade. The session then sees both, and the block it
    was getting anyway now carries the extra finding.
    """
    if out.get("verdict") == "continue":
        out["reason"] = ("%s  ALSO: %s NEXT: %s" % (out.get("reason", ""), reason, action))[:700]
        return
    out["verdict"] = "continue"
    out["reason"] = reason[:400]
    out["next_action"] = action[:200]

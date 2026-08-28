"""wl_bravedefault: a `- [?]` whose DEFAULT is a no-op is a parking bay.

WHY THIS EXISTS, in the operator's words: "I want braver defaults!"

CLAUDE.md already says a `DEFAULT:` is time-boxed autonomy, not a parking bay,
and that an unanswered deferral whose window closes "becomes an order to do the
default". That machinery is real -- wl_checks executes expired defaults. It is
also decorative whenever the default does NOTHING: the timer fires, the no-op
executes, and the item is exactly the parking bay the rule forbids.

MEASURED, not theorised. Every default written in the session that commissioned
this rule, plus one from a live peer, in one evening:

    DEFAULT: keep carrying it.
    DEFAULT: leave it on its branch.
    DEFAULT: hold until CI green.
    "... or hold. Yours; default is to hold and report the numbers."

Four for four, all inaction.

THE PROMPT INVITES IT. The catalogue asks for `DEFAULT: <what you do if
unanswered>` in four places, which reads perfectly well as "nothing". Rewording
those is worth doing and is not enough on its own, which is why this is a judged
rule: telling a no-op apart from an action is a reading of what the sentence
COMMITS TO, and a regex cannot do it. "hold until CI green" and "land the work
when CI is green" differ by one verb and by everything.

(Merging, pushing main and releasing are excluded from the braver form on
purpose. They are the operator's, this judge is already forbidden to order them
-- sanitize_next_action rewrites any next_action that does -- and an example
list that offered "merge it into the open PR" as the brave default would have
generated orders the sanitiser then blanked. That is not hypothetical: it was
in the first draft of this rubric.)

THE BOUNDARY, drawn explicitly, because "never hold" would be wrong. A hold is
legitimate when the act it declines is IRREVERSIBLE or lands on someone else:
publishing, releasing, deleting, pushing to a second repo, spending money,
mailing a human. So the rule does not ask "does it hold?" -- it asks WHY it
holds, as one of five reasons, and rejects exactly two of them:

    irreversible     the act cannot be undone            -> legitimate
    outward          it leaves this repo or reaches a
                     third party                         -> legitimate
    cost-on-others   it spends someone else's time,
                     money or attention                  -> legitimate
    preference       "the operator might want it the
                     other way"                          -> REJECTED
    none             no reason given at all              -> REJECTED

`preference` is the whole point. The operator "almost always takes the
recommended action", so deferring on the possibility that they might not is not
caution, it is a round trip bought with a certainty.

TRIGGER BOUNDARY. Asked only on a stop whose remaining list actually contains a
`- [?]` carrying a `DEFAULT:` token -- the same token wl_checks already requires
on every deferral. No deferrals, no question, no cost. That is a narrow trigger
on purpose: this rule reads on EVERY stop that has a parked decision, which is
most of them, and a rule that fires always is a rule that gets skimmed.

FAIL SEMANTICS are wl_classsweep's, not the regression gate's: a missing or
malformed object degrades to a reported non-answer and never blocks, because the
only thing this object can do is turn a stop into a continue.

WEDGE BOUND. Unlike the class sweep, this rule needs no marker to persist -- the
timid `[?]` sits in the worklist until it is rewritten, so the trigger renews
itself. The marker exists ONLY as a cap: three fires on the same deferral inside
the TTL and it goes quiet, so a session that cannot satisfy the judge is not
walled in by it. The cap resets when the deferral changes, which is the event
that means the session responded.
"""

import hashlib
import os

import wl_core as C
import wl_rules

# The substring the prompt section carries; judge_schema_for requires the object
# iff this is present, the same contract as the other two optional objects.
BRAVE_MARKER = "A DEFAULT THAT DOES NOTHING IS NOT A DEFAULT"

# THE SAME TOKEN the rest of the program already requires on every `- [?]`,
# IMPORTED rather than re-spelled. A second copy of this regex would drift from
# the first the day either changes, which is precisely the defect the sibling
# rule in wl_classsweep exists to catch; writing it twice here would be that
# rule failing inside its own pull request.
DEFAULT_TOKEN = C.DEFAULT_TOKEN

HOLD_REASONS = ("irreversible", "outward", "cost-on-others", "preference", "none")
# The two that are not reasons, only reluctance.
TIMID_REASONS = ("preference", "none")

BRAVE_DEFAULT_SCHEMA = {
    "type": "object",
    "properties": {
        "applicable": {"type": "boolean"},
        "quote": {"type": "string", "maxLength": 300},
        "default_text": {"type": "string", "maxLength": 200},
        "changes_state": {"type": "boolean"},
        "hold_reason": {"type": "string", "enum": list(HOLD_REASONS)},
        "braver": {"type": "string", "maxLength": 200},
        "instruction": {"type": "string", "maxLength": 300},
    },
    "required": [
        "applicable",
        "quote",
        "default_text",
        "changes_state",
        "hold_reason",
        "braver",
        "instruction",
    ],
    "additionalProperties": False,
}

BRAVE_PROMPT = """

A DEFAULT THAT DOES NOTHING IS NOT A DEFAULT. ALSO fill the `brave_default`
object, about the `[?]` items in the remaining list above.

This project's rule: a `- [?]` is time-boxed autonomy, not a parking bay. Its
`DEFAULT:` is what the session WILL DO, on its own, when the window closes and
the operator has not answered. That machinery is real -- an expired default
gets executed. It is decorative whenever the default does nothing. Four
consecutive real ones, written in a single evening:

    DEFAULT: keep carrying it.
    DEFAULT: leave it on its branch.
    DEFAULT: hold until CI green.
    "Yours; default is to hold and report the numbers."

Every one of them describes the status quo. The timer fires, nothing happens,
and the item is the parking bay the rule forbids.

Pick the ONE `[?]` whose default is weakest and answer about it.

(1) DOES IT CHANGE STATE? A default changes state when, executed alone, it
leaves the repo, the branch, or the world different: write it and commit it
onto the open PR's branch, delete the dead path, pick option A and implement
it, regenerate the files. It does NOT change state when it describes
continuing: "hold", "keep carrying", "leave it", "wait for", "do not touch",
"report the numbers", "revisit later", "ask again". Reporting is not acting.

THREE ACTS ARE NEVER A BRAVE DEFAULT, because they are reserved to the
operator and this gate is forbidden to order them: merging a PR, pushing to
main, and cutting or publishing a release. A deferral about one of those is a
legitimate hold -- answer `irreversible` or `outward`, not `preference`. The
braver form for such an item is the work that stands ready underneath it
("finish it and leave it committed on the branch"), never the act itself.

(2) IF IT HOLDS, WHY? Answer with exactly one:
  irreversible     the act cannot be undone once done (a release, a delete, a
                   force-push, a payment).
  outward          it reaches a third party in a way that cannot be taken
                   back: mailing a human, a published release, anything with
                   an audience that has already seen it.
  cost-on-others   it spends someone else's time, money, or attention.

REVERSIBLE IS NOT OUTWARD. Deploying, republishing regenerated content,
pushing to a preview or edge environment, regenerating and shipping files --
all of these can be done again or rolled back, so they are ACTIONS, not holds.
"Publish the regenerated files when the pass finishes, or hold" defaults to
PUBLISHING. Reserve `outward` for the thing that cannot be recalled once it
has left.
  preference       nothing is at risk; it holds only because the operator
                   might have wanted it the other way.
  none             no reason is given at all.

The first three are legitimate reasons to default to not-doing. The last two
are not: this operator almost always takes the recommended action, so holding
on the CHANCE they would not is a round trip bought with a certainty. Set
hold_reason honestly -- an inaction dressed up as `irreversible` when nothing
irreversible is being declined is the failure this object exists to catch.

(3) THE BRAVER FORM. Write in `braver` the default the session would actually
choose if it had to decide alone -- almost always the recommended action,
stated as an executable step ("commit it onto the open PR's branch",
"implement option A", "delete the dead path"), never as a question, and never
one of the three operator-only acts above.

Set applicable=false only when there is genuinely no `[?]` with a `DEFAULT:`
in the list above, or when every one of them already commits to an action.
"""


def has_deferral_with_default(remaining_lines):
    """The trigger: a parked decision that carries a default at all."""
    return any("[?]" in ln and DEFAULT_TOKEN.search(ln) for ln in (remaining_lines or []) if ln)


def prompt_section(remaining_lines):
    return BRAVE_PROMPT if has_deferral_with_default(remaining_lines) else ""


def _clean(obj, key, limit):
    v = obj.get(key)
    return v.strip()[:limit] if isinstance(v, str) else ""


def read_verdict(out):
    """(kind, payload). kind is 'silent', 'fire' or 'degraded'."""
    bd = out.get("brave_default") if isinstance(out, dict) else None
    if not isinstance(bd, dict):
        return "degraded", "no brave_default object: %s" % repr(bd)[:120]
    if not isinstance(bd.get("applicable"), bool) or not isinstance(bd.get("changes_state"), bool):
        return "degraded", "brave_default applicable/changes_state not booleans"
    reason = bd.get("hold_reason")
    if reason not in HOLD_REASONS:
        return "degraded", "brave_default hold_reason %r is not one of %s" % (reason, HOLD_REASONS)
    if not bd["applicable"]:
        return "silent", "no deferral with a default to judge"
    if bd["changes_state"]:
        return "silent", "the default commits to an action: %s" % _clean(bd, "default_text", 160)
    if reason not in TIMID_REASONS:
        # A justified hold. The reason is KEPT in the note so an operator can
        # audit whether "irreversible" was true, which is the only way this
        # escape hatch can be checked at all.
        return "silent", "holding is justified (%s): %s" % (reason, _clean(bd, "default_text", 120))
    quote = _clean(bd, "quote", 300)
    if not quote:
        # Which deferral? Without that the order cannot be acted on, and an
        # unactionable block is the noise that gets a rule routed around.
        return "degraded", "brave_default fired without naming the deferral"
    return "fire", {
        "quote": quote,
        "default_text": _clean(bd, "default_text", 200),
        "hold_reason": reason,
        "braver": _clean(bd, "braver", 200),
        "instruction": _clean(bd, "instruction", 300),
    }


V_REASON = (
    "A DEFAULT THAT DOES NOTHING IS NOT A DEFAULT. The deferral %r defaults to "
    "%r, which is the status quo, and it holds only %s. A `[?]` is time-boxed "
    "autonomy, not a parking bay."
)
V_ACTION = "Rewrite that deferral's DEFAULT as the action you would take alone: %s"
V_ACTION_GENERIC = (
    "Rewrite that deferral's DEFAULT as the action you would take alone -- the recommended "
    "one, stated as an executable step, not as a hold. %s"
)
_WHY = {
    "preference": "because the operator might prefer otherwise",
    "none": "for no stated reason",
}


def enforce(out, payload):
    """Write the braver-default order into a judge verdict, in place."""
    reason = V_REASON % (
        payload["quote"][:120],
        payload["default_text"][:80] or "(nothing)",
        _WHY.get(payload["hold_reason"], "for no stated reason"),
    )
    action = (
        V_ACTION % payload["braver"]
        if payload["braver"]
        else V_ACTION_GENERIC % payload["instruction"]
    )
    wl_rules.apply_order(out, reason, action)
    return "brave-default: %s" % payload["quote"][:160]


# The cap, not a memory. See WEDGE BOUND in the module docstring.
BRAVE_TTL_MIN = int(os.environ.get("WORKLIST_BRAVE_TTL_MIN", "120"))
BRAVE_MAX_FIRES = int(os.environ.get("WORKLIST_BRAVE_MAX_FIRES", "3"))

BRAVE_DEMAND = wl_rules.Demand("bravedefault", BRAVE_TTL_MIN, BRAVE_MAX_FIRES)


def _key(quote):
    return hashlib.sha1(quote.encode("utf-8", "replace")).hexdigest()[:12]


def apply_verdict(out, path=None):
    """(kind, note). Mutates `out` when the rule fires; owns the cap.

    kind is 'fire', 'silent', 'degraded' or 'capped'. 'capped' means the same
    deferral has already been blocked on BRAVE_MAX_FIRES times inside the TTL:
    the finding stands but the session is let past, because a rule that cannot
    be satisfied must not be a wall.
    """
    kind, payload = read_verdict(out)
    if kind != "fire":
        BRAVE_DEMAND.clear(path)
        return kind, payload if isinstance(payload, str) else ""
    key = _key(payload["quote"])
    prior = BRAVE_DEMAND.peek(path)
    same = bool(prior) and prior.get("key") == key
    if same and prior["fires"] >= BRAVE_MAX_FIRES:
        return "capped", "brave-default: capped after %d blocks on the same deferral" % (
            BRAVE_MAX_FIRES,
        )
    note = enforce(out, payload)
    BRAVE_DEMAND.bank({"key": key, "quote": payload["quote"][:200]}, prior if same else None, path)
    return "fire", note

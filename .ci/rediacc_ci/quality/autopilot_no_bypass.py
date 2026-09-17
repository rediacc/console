"""The rediacc-autopilot App must hold NO bypass on console's branch ruleset.

Ported from `.ci/scripts/quality/check-autopilot-no-bypass.sh`, which is NOT deleted; see `rediacc_ci.quality.__init__` for why both copies live.

The twin's header, carried whole because the trap it records is the whole design:

    WHY THIS IS THE LOAD-BEARING WAVE C INVARIANT. The autopilot exists to drive
    a PR to green without a human. The only thing that makes that safe is that
    it is subject to exactly the same required checks as a human contributor: it
    must never be able to merge past `CI Complete`. A bypass entry would make
    every other Wave C control decorative, and it is added in the GitHub UI, so
    nothing in this repository would otherwise notice.

    THE TRAP THIS GATE IS BUILT AROUND, measured not assumed. console is public,
    so

        curl https://api.github.com/repos/rediacc/console/rulesets/<id>

    answers 200 WITHOUT authentication, and the unauthenticated payload silently
    OMITS `bypass_actors` entirely (verified: top-level keys are id, name,
    target, source_type, source, enforcement, conditions, rules, node_id,
    created_at, updated_at, _links). A naive gate would fetch that, find no
    autopilot in a list that does not exist, and report PASS forever.

    So presence of the field is asserted BEFORE its contents. A token that
    cannot see bypass actors makes this check BLIND, and blind is not clean.

    Usage:
      GITHUB_AUTOPILOT_APP_ID=<id> .ci/scripts/quality/check-autopilot-no-bypass.sh

    Env:
      GITHUB_AUTOPILOT_APP_ID  required. The App ID (org variable of the same name).
      RULESET_REPO      optional, default rediacc/console.

    Exits 0 when the App is absent from bypass_actors, 1 on a bypass entry, a
    blind read, an ambiguous ruleset, or unset config.

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

THE RULESET IS FOUND BY SHAPE, NOT BY A PINNED ID, and the twin says why in one line kept at the call site: "ids change when a ruleset is recreated, and a gate pointing at a deleted id would 404 rather than protect."

`jq` IS STILL PROBED EVEN THOUGH THIS PORT DOES NOT USE IT. That is a deliberate choice and it is the kind that goes wrong silently if it is not written down. The twin runs `require_cmd jq` and refuses without it; this module parses the same payloads with `json.loads`. Dropping the probe would mean the port RUNS in an environment where its twin REFUSES, so the two would disagree
about the only machine where the question is interesting, and the differential would have nothing to say about it. The probe is therefore carried, with the twin's exact message, and it is the FIRST thing W7 phase 5 should delete when the twin dies: at that point it is a dependency on a tool nothing calls.

AN UNPARSEABLE RULESET LIST IS THE ONE DELIBERATE DIVERGENCE, and it is a twin DEFECT rather than a design. The twin pipes the payload into `jq -r '.[] | select(...)'` inside a `set -e` assignment, so a body that is not a JSON array kills the whole gate with jq's own diagnostic on stderr and jq's exit status (5) as the gate's. Nothing in the gate's vocabulary appears, and a reader
sees what looks like a broken runner. This port refuses with its own message and exit 1 instead. Reported rather than reproduced, because reproducing it would mean forging another program's error text, and no ledger row exercises it.

`jq -r '.name'` PRINTS THE FOUR CHARACTERS `null` FOR A MISSING NAME, not an empty string, and the twin interpolates that into two messages. The port carries the same spelling: a ruleset with no name reports `(null)`, which is what a reader of the twin's output has always seen.

`${actors:-none}` IS BASH'S EMPTY-OR-UNSET DEFAULT and it is what makes the
success line read `bypass actors are [none]` rather than `[]`. Carried, because a green line that changed shape is the one thing a reader scanning a CI log would notice, and it would look like the gate had changed its mind.

THE LOOP DOES NOT STOP AT THE FIRST BAD RULESET. The twin sets `rc=1` and
`continue`s three separate times, so a repository with two active branch rulesets reports on both. A port that returned early would hide the second, and the difference is invisible in the one-ruleset case this repository actually has.
"""

import json
import os
import shutil
import subprocess
import sys

from rediacc_ci import log
from rediacc_ci.controls import Controls

# The default the twin carries. Named here so the one place it is written down is next to the comment saying it is a default and not a pin.
DEFAULT_RULESET_REPO = "rediacc/console"

# The organisation variable that names the App. Deliberately has NO default: the twin's own words are that "a wrong-or-absent id would make this gate pass against nothing".
APP_ID_ENV = "GITHUB_AUTOPILOT_APP_ID"

# The commands both implementations require on PATH. `jq` is here for the reason in the port notes: this module never calls it, and its twin refuses without it.
REQUIRED_COMMANDS = ("gh", "jq")


class RulesetPayloadError(ValueError):
    """The ruleset list came back as something that cannot be iterated.

    A NAMED type rather than a bare ValueError, and it subclasses ValueError so the caller's single `except ValueError` still covers both this and `json.JSONDecodeError`. Both are the same event from the gate's point of view: the body GitHub returned is not the array the query needs, which is the shape a 404 error object arrives in.
    """


def require_cmd(name: str) -> bool:
    """`common.sh:141-147`, in one function, with its message byte for byte.

    Returns True when the command is present. The twin exits immediately; the caller here does the exiting, so the probe stays testable.
    """
    if shutil.which(name) is not None:
        return True
    log.error("Required command '%s' is not available" % name)
    return False


def gh_api(path: str) -> tuple[int, str]:
    """`gh api <path> 2>/dev/null`. Returns (exit status, stdout).

    STDERR IS DISCARDED, matching the twin's `2>/dev/null` on both calls. That is not tidiness: the twin decides purely on the exit status, and a gh failure that printed a rate-limit notice into this gate's stderr would be read by the comparator as a finding neither implementation meant to report.
    """
    try:
        proc = subprocess.run(
            ["gh", "api", path],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except OSError:
        # No gh on PATH. require_cmd has already refused in the normal flow;
        # reaching here means a caller drove this directly, and "the call did not succeed" is the honest answer.
        return 127, ""
    return proc.returncode, proc.stdout.decode("utf-8", "replace")


def active_branch_ruleset_ids(payload: str) -> list[str]:
    """The twin's `jq -r '.[] | select(.target == "branch" and .enforcement == "active") | .id'`.

    Ids come back as STRINGS because that is what `jq -r` writes and what the twin then interpolates into a URL. `json.loads` gives integers, so they are stringified here rather than at three call sites.

    Raises ValueError when the payload is not a JSON array. See the port notes: the twin dies with jq's diagnostic in that case, and this is the one place the port deliberately behaves better.
    """
    parsed = json.loads(payload)
    if not isinstance(parsed, list):
        raise RulesetPayloadError("rulesets payload is a %s, not a list" % type(parsed).__name__)
    out: list[str] = []
    for entry in parsed:
        if not isinstance(entry, dict):
            continue
        if entry.get("target") == "branch" and entry.get("enforcement") == "active":
            out.append(_jq_string(entry.get("id")))
    return out


def _jq_string(value: object) -> str:
    """What `jq -r` writes for a scalar. `null` is the literal four characters.

    This is the difference between the port's output and the twin's for a ruleset with no name, and it is the sort of thing that reads as a port bug
    for anyone comparing two CI logs.
    """
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    return str(value)


def bypass_hit(ruleset: dict, app_id: str) -> str:
    r"""The twin's hit query, including its `"\(.actor_type)/\(.bypass_mode)"` shape.

    `(.actor_id|tostring) == $id` is a STRING comparison in the twin, so an
    actor_id of 12345 matches the environment variable "12345". Comparing integers here would work today and would break the moment GitHub returns an id this repository stores as a string, which is exactly the class of change nobody would notice until the gate stopped matching.
    """
    lines = []
    for actor in ruleset.get("bypass_actors") or []:
        if not isinstance(actor, dict):
            continue
        if _jq_string(actor.get("actor_id")) == app_id:
            lines.append(
                "%s/%s"
                % (_jq_string(actor.get("actor_type")), _jq_string(actor.get("bypass_mode")))
            )
    return "\n".join(lines)


def actor_summary(ruleset: dict) -> str:
    """`[.bypass_actors[] | "\\(.actor_type):\\(.actor_id)"] | join(", ")`."""
    return ", ".join(
        "%s:%s" % (_jq_string(a.get("actor_type")), _jq_string(a.get("actor_id")))
        for a in (ruleset.get("bypass_actors") or [])
        if isinstance(a, dict)
    )


def main(argv: list[str] | None = None) -> int:
    """Run the gate. 0 when the App holds no bypass, 1 on anything else.

    `--selftest` is intercepted BEFORE any network call, so the controls run on a machine with no token at all.
    """
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    for name in REQUIRED_COMMANDS:
        if not require_cmd(name):
            return 1

    ruleset_repo = os.environ.get("RULESET_REPO") or DEFAULT_RULESET_REPO
    app_id = os.environ.get(APP_ID_ENV, "")

    if not app_id:
        log.error("%s is not set." % APP_ID_ENV)
        log.error("It is an organisation variable; pass it explicitly rather than defaulting,")
        log.error("because a wrong-or-absent id would make this gate pass against nothing.")
        return 1

    log.step("Checking rediacc-autopilot (app %s) has no bypass on %s..." % (app_id, ruleset_repo))

    # Find the ruleset by SHAPE, not by a pinned id: ids change when a ruleset is recreated, and a gate pointing at a deleted id would 404 rather than protect.
    code, rulesets = gh_api("repos/%s/rulesets" % ruleset_repo)
    if code != 0:
        log.error("Could not list rulesets for %s." % ruleset_repo)
        log.error("Reading bypass actors needs a token with Administration: read.")
        return 1

    try:
        ids = active_branch_ruleset_ids(rulesets)
    except ValueError as exc:
        # THE ONE DELIBERATE DIVERGENCE. See the port notes: the twin dies here
        # with jq's own diagnostic and jq's exit status. Refusing in the
        # repository's own vocabulary is strictly better and is NOT what the twin does, so it is named rather than hidden.
        log.error("Could not read the ruleset list for %s: %s." % (ruleset_repo, exc))
        log.error("Refusing to report a verdict from a payload this gate cannot parse.")
        return 1

    if len(ids) == 0:
        log.error("No ACTIVE branch ruleset on %s." % ruleset_repo)
        log.error("Either protection was removed, or this token cannot see it. Both are failures.")
        return 1

    rc = 0
    for ruleset_id in ids:
        code, body = gh_api("repos/%s/rulesets/%s" % (ruleset_repo, ruleset_id))
        if code != 0:
            log.error("Could not read ruleset %s." % ruleset_id)
            rc = 1
            continue

        try:
            parsed = json.loads(body)
        except ValueError:
            # Same divergence as above, at the second call. The twin's `jq -r '.name'` would print its own error and take the gate down with it.
            log.error("Could not read ruleset %s." % ruleset_id)
            rc = 1
            continue
        if not isinstance(parsed, dict):
            log.error("Could not read ruleset %s." % ruleset_id)
            rc = 1
            continue

        name = _jq_string(parsed.get("name"))

        # PRESENCE FIRST. See the header: an unauthenticated (or under-permissioned) read returns 200 with this key missing, which would otherwise read as "no bypass actors" and pass.
        if "bypass_actors" not in parsed:
            log.error(
                "Ruleset %s (%s) came back WITHOUT a bypass_actors field." % (ruleset_id, name)
            )
            log.error("That is a BLIND read, not a clean one: console is public, so an")
            log.error("unauthenticated GET answers 200 and omits the field entirely.")
            log.error("Use a token with Administration: read.")
            rc = 1
            continue

        hit = bypass_hit(parsed, app_id)
        if hit:
            log.error(
                "rediacc-autopilot (app %s) HAS a bypass on ruleset %s (%s): %s"
                % (app_id, ruleset_id, name, hit)
            )
            log.error("Remove it. The autopilot must be subject to the same required checks")
            log.error("as a human contributor, or every other Wave C control is decorative.")
            rc = 1
            continue

        actors = actor_summary(parsed)
        log.info(
            "OK: ruleset %s (%s) bypass actors are [%s]; autopilot absent."
            % (ruleset_id, name, actors or "none")
        )

    if rc != 0:
        return 1

    log.info("OK: rediacc-autopilot holds no ruleset bypass on %s." % ruleset_repo)
    return 0


# --------------------------------------------------------------------------- Selftest ---------------------------------------------------------------------------

# The unauthenticated payload's top-level keys, transcribed from the twin's header. The blind-read control is built from THIS list rather than by deleting a key from an authenticated payload, so it models what GitHub actually returns rather than what a mutation happens to produce.
UNAUTHENTICATED_KEYS = (
    "id",
    "name",
    "target",
    "source_type",
    "source",
    "enforcement",
    "conditions",
    "rules",
    "node_id",
    "created_at",
    "updated_at",
    "_links",
)


def selftest() -> int:
    """Both directions for every query, with no network and no token.

    The whole gate is three JSON queries and a presence test, so the controls below drive those four things directly. A control suite that only planted a bypass would pass against a query hard-wired to "yes".
    """
    ctl = Controls("autopilot-no-bypass", floor=18, verbose=True)

    # -- ruleset selection, both directions --------------------------------
    payload = json.dumps(
        [
            {"id": 1, "target": "branch", "enforcement": "active"},
            {"id": 2, "target": "branch", "enforcement": "evaluate"},
            {"id": 3, "target": "tag", "enforcement": "active"},
            {"id": 4, "target": "branch", "enforcement": "active"},
        ]
    )
    ctl.check(
        "PLANT: active branch rulesets are selected, in payload order",
        active_branch_ruleset_ids(payload),
        ["1", "4"],
    )
    ctl.check(
        "MIRROR: an inactive branch ruleset is not selected",
        "2" in active_branch_ruleset_ids(payload),
        False,
    )
    ctl.check(
        "MIRROR: an active TAG ruleset is not selected",
        "3" in active_branch_ruleset_ids(payload),
        False,
    )
    ctl.check(
        "MIRROR: an empty list selects nothing (which the caller must treat as a FAILURE)",
        active_branch_ruleset_ids("[]"),
        [],
    )
    ctl.raises(
        "PLANT: a non-array payload is refused rather than iterated",
        RulesetPayloadError,
        active_branch_ruleset_ids,
        '{"message":"Not Found"}',
    )

    # -- the id is a STRING, as jq -r writes it ----------------------------
    ctl.check("ids are stringified the way jq -r writes them", _jq_string(12345), "12345")
    ctl.check("a missing value prints the four characters 'null'", _jq_string(None), "null")

    # -- the blind read, which is the trap this gate exists for -------------
    blind = dict.fromkeys(UNAUTHENTICATED_KEYS, "x")
    ctl.check(
        "PLANT: the unauthenticated payload has no bypass_actors key",
        "bypass_actors" in blind,
        False,
    )
    authed = dict(blind)
    authed["bypass_actors"] = []
    ctl.check(
        "MIRROR: an authenticated payload with an EMPTY list does have the key",
        "bypass_actors" in authed,
        True,
    )
    # The distinction the whole gate rests on: an empty list and a missing key produce the same answer from the hit query, and only one of them is clean.
    ctl.check("an empty bypass list yields no hit", bypass_hit(authed, "42"), "")
    ctl.check("a missing bypass list yields no hit either", bypass_hit(blind, "42"), "")

    # -- the hit query, both directions ------------------------------------
    with_app = {
        "bypass_actors": [
            {"actor_id": 7, "actor_type": "Team", "bypass_mode": "always"},
            {"actor_id": 42, "actor_type": "Integration", "bypass_mode": "pull_request"},
        ]
    }
    ctl.check(
        "PLANT: the App id is found and reported as type/mode",
        bypass_hit(with_app, "42"),
        "Integration/pull_request",
    )
    ctl.check(
        "MIRROR: a different App id is not reported",
        bypass_hit(with_app, "43"),
        "",
    )
    ctl.check(
        "the comparison is on STRINGS, so a numeric id matches its env-var spelling",
        bypass_hit({"bypass_actors": [{"actor_id": 42}]}, "42"),
        "null/null",
    )
    ctl.check(
        "the summary joins every actor, not just the matching one",
        actor_summary(with_app),
        "Team:7, Integration:42",
    )
    ctl.check("an empty summary is the empty string, not 'none'", actor_summary(authed), "")

    # -- require_cmd, both directions ---------------------------------------
    ctl.check("require_cmd finds a command that exists", require_cmd("sh"), True)
    ctl.check(
        "require_cmd refuses a command that does not",
        require_cmd("definitely-not-a-real-binary-portf"),
        False,
    )

    # -- the whole gate refuses an unset App id -----------------------------
    saved = os.environ.get(APP_ID_ENV)
    os.environ.pop(APP_ID_ENV, None)
    try:
        ctl.check("PLANT: an unset App id reds rather than defaulting", main([]), 1)
    finally:
        if saved is not None:
            os.environ[APP_ID_ENV] = saved

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

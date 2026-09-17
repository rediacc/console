"""The autopilot's hold-open debug session COPIES three dispatch inputs from breakpoint. This gate holds the copies to the original.

Ported from `.ci/scripts/quality/check-autopilot-breakpoint-alignment.sh`, which is not deleted; see `rediacc_ci.quality.__init__` for why both copies live.

WHY A GATE AND NOT A COMMENT. `.github/workflows/autopilot.yml`'s model job can hold its runner open with a tmate shell behind a Cloudflare tunnel, driven by the vendored scripts in `.ci/breakpoint/scripts/`. The inputs that drive it (`hold-duration`, `debug-shell`, `send-email`) are hand-copied from `.ci/breakpoint/workflow/breakpoint.yml`, because breakpoint.yml is FROZEN in
MANIFEST.sha256 and cannot grow an autopilot-shaped variant, and GitHub has no include mechanism for workflow inputs. Hand-copied shapes drift silently, and the drift is worst exactly where it matters: `send-email` defaulting to false in one file and true in the other would mean one of the two tools prints a bearer-credential URL into a world-readable log while the operator
believes both behave the same way.

breakpoint.yml is the CANONICAL side. autopilot.yml follows it, never the reverse: this gate never asks anyone to edit the frozen file.

WHAT IS COMPARED
  breakpoint `duration`      options == autopilot `hold-duration` options
  breakpoint `debug-shell`   type + default == autopilot `debug-shell`
  breakpoint `send-email`    type + default == autopilot `send-email`
Descriptions are deliberately NOT compared: breakpoint's `duration` text talks about named-mode Access logins, which the autopilot (quick tunnel only) does not have, and forcing prose equality would make the gate wrong.

ANTI-VACUITY. Every extraction that comes back empty is a FAILURE, not a pass: a missing file, a missing input block, a missing field, or an options list that parses to nothing all exit 1. A gate that silently compares "" to "" is the failure mode this repo has already shipped once.

Env seams (for the gate's own test; both default to the real files):
  AUTOPILOT_BP_ALIGN_BREAKPOINT_FILE
  AUTOPILOT_BP_ALIGN_AUTOPILOT_FILE

Exit: 0 aligned, 1 drift or nothing-to-check.

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

THE EXTRACTOR IS A HAND-ROLLED SCANNER ON BOTH SIDES, AND DELIBERATELY SO. This
package already owns a YAML reader -- `rediacc_ci.workflows` -- and the obvious
port routes `input_field` through it. That would be a DIFFERENT GATE. The twin's awk program reads `on:` -> `workflow_dispatch:` -> `inputs:` positionally, by indentation, and its comment states the constraint that makes that correct: "both files declare inputs at the same depth (`on:` -> `workflow_dispatch:` -> `inputs:` -> the input at 6 spaces, its fields at 8), so one extractor
serves both. Scanning is scoped to the inputs block: a 6-space bare key elsewhere in the file (there are several) must never be mistaken for an input." A real YAML parser would resolve anchors, accept a block list where the twin returns empty, and accept a different indentation where the twin exits -- each of which turns an anti-vacuity refusal into a silent pass. So the scanner is
reproduced line for line, and the reason it is not a parser is recorded here rather than rediscovered by whoever next reaches
for `workflows.load`.

`if (ind < 6) exit` IS THE END OF THE INPUTS BLOCK, and it is an `exit` in awk -- the whole program stops, not just the loop. Reproduced as an early `return`, which is the same thing for a function that has already found nothing.

VALUES ARE READ AS WRITTEN, then normalized by the caller. An inline flow list (`['5', '10']`) is the shape both files use; a block list would return empty here and be caught by the anti-vacuity check rather than silently comparing nothing.

`normalize_options` IS `tr -d "[]'\\" "` FOLLOWED BY `sed 's/,$//'`. Character deletion, not tokenisation: the comparison is over the VALUES, not over the YAML author's spacing. Reproduced as `str.translate` plus one trailing-comma strip, because a "cleaner" split-and-rejoin would silently normalise `5,,10` into `5,10` and stop the gate noticing a malformed list.

THE TWIN SOURCES `.ci/scripts/lib/common.sh` AND THE PORT DOES NOT, which is the one archaeology token this file would otherwise drop. Its two `# shellcheck
source=` / `# BLOCKER:` lines record that `log_error`, `log_info` and
`get_repo_root` are used throughout, and that the BLOCKER exists because `check-python-gate-deps` and shellcheck would otherwise read the source line as unused. In the port `log_*` comes from `rediacc_ci.log` and the root from `rediacc_ci.paths.repo_root()`, so there is no source line and no suppression to justify -- but the FACT that these three helpers are the gate's only
dependency on the shared bash library is what makes the twin cheap to retire, and that is worth keeping.

THE MULTI-LINE FINDING. The twin's `fail()` calls `log_error` with an embedded newline, so only the FIRST line carries the `✗` glyph and the rest arrive as indented continuation. `scripts/lib/shadow-gate.ts` handles exactly that with its continuation rule -- "findings in this tree are overwhelmingly printed as a marked HEADER followed by the actual findings on unmarked indented
lines" -- so the newlines are preserved rather than flattened into one long line, which would make the port's finding set a different size from the twin's and read as a mismatch.
"""

import os
import pathlib
import re
import tempfile

from rediacc_ci import log, paths
from rediacc_ci.controls import Controls, plant

BREAKPOINT_FILE_ENV = "AUTOPILOT_BP_ALIGN_BREAKPOINT_FILE"
AUTOPILOT_FILE_ENV = "AUTOPILOT_BP_ALIGN_AUTOPILOT_FILE"
DEFAULT_BREAKPOINT_FILE = ".ci/breakpoint/workflow/breakpoint.yml"
DEFAULT_AUTOPILOT_FILE = ".github/workflows/autopilot.yml"

# The three depths the scanner is built on. Named rather than inlined because they are the load-bearing assumption -- see the module docstring -- and a reader who does not know that reads `6` and `8` as arbitrary.
WORKFLOW_DISPATCH_RE = re.compile(r"^  workflow_dispatch:[ \t]*$")
INPUTS_RE = re.compile(r"^    inputs:[ \t]*$")
INPUT_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+:[ \t]*$")
INPUT_INDENT = 6
FIELD_INDENT = 8

# FLOOR. A one- or two-entry list means the extractor matched something that is not the option list at all; the real one has always carried the full ladder.
MIN_DURATION_OPTIONS = 5

# The two booleans, and the two fields of each, that must agree. A list rather than four hand-written comparisons so a fifth copied input is one row.
BOOLEAN_INPUTS = ("debug-shell", "send-email")
BOOLEAN_FIELDS = ("type", "default")

_OPTION_STRIP = str.maketrans("", "", "[]'\" ")


def input_field(path: pathlib.Path, want: str, field: str) -> str:
    """One field out of one workflow_dispatch input block, as written.

    A faithful transcription of the twin's awk program. The `next`/`exit` control flow is preserved as `continue`/`return` at the same points, because the points are where the anti-vacuity refusals come from: every path that returns "" here becomes a `require_value` failure in the caller, and a port that returned a value where awk returned nothing would turn a refusal into a pass.
    """
    in_dispatch = False
    in_inputs = False
    current = False
    prefix = field + ": "
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    for raw in text.split("\n"):
        if not in_dispatch:
            if WORKFLOW_DISPATCH_RE.match(raw):
                in_dispatch = True
            continue
        if not in_inputs:
            if INPUTS_RE.match(raw):
                in_inputs = True
            continue
        # awk: `if ($0 ~ /^[[:space:]]*$/) next` -- a blank line inside the block is not the end of it, so indentation is not measured for it.
        if raw.strip() == "":
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        body = raw[indent:]
        if body.startswith("#"):
            continue
        if indent < INPUT_INDENT:
            # awk `exit`: the inputs block has ended and there is nothing further to find. Not a `break` into a later search.
            return ""
        if indent == INPUT_INDENT and INPUT_NAME_RE.match(body):
            name = body.split(":", 1)[0]
            current = name == want
            continue
        if current and indent == FIELD_INDENT and body.startswith(prefix):
            return body[len(prefix) :]
    return ""


def normalize_options(value: str) -> str:
    """`tr -d "[]'\\" "` then `sed 's/,$//'`. Character deletion, not parsing."""
    return value.translate(_OPTION_STRIP).removesuffix(",")


def _require_value(label: str, value: str) -> bool:
    """An empty extraction means the parser lost its target.

    That is a broken gate, not an aligned pair, and the distinction is the whole anti-vacuity contract: two empty strings compare equal.
    """
    if value:
        return True
    log.error(
        "could not extract %s (the input block, the field, or the file layout moved; "
        "this gate refuses to pass blind)" % label
    )
    return False


def main(argv: list[str] | None = None) -> int:
    if argv and argv[0] == "--selftest":
        return selftest()

    root = paths.repo_root()
    bp_name = os.environ.get(BREAKPOINT_FILE_ENV, DEFAULT_BREAKPOINT_FILE)
    ap_name = os.environ.get(AUTOPILOT_FILE_ENV, DEFAULT_AUTOPILOT_FILE)
    bp_file = root / bp_name
    ap_file = root / ap_name

    for name, candidate in ((bp_name, bp_file), (ap_name, ap_file)):
        if not candidate.is_file():
            log.error("file not found: %s (nothing to compare cannot pass)" % name)
            return 1

    failed = False

    def fail(message: str) -> None:
        nonlocal failed
        log.error("AUTOPILOT/BREAKPOINT DRIFT: %s" % message)
        failed = True

    # --- 1. duration option lists must be identical --------------------------
    bp_duration = normalize_options(input_field(bp_file, "duration", "options"))
    ap_duration = normalize_options(input_field(ap_file, "hold-duration", "options"))
    if not _require_value("breakpoint duration options (%s)" % bp_name, bp_duration):
        return 1
    if not _require_value("autopilot hold-duration options (%s)" % ap_name, ap_duration):
        return 1

    if len([part for part in bp_duration.split(",") if part]) < MIN_DURATION_OPTIONS:
        log.error(
            "breakpoint duration parsed to fewer than %d options ('%s'); the extractor is broken"
            % (MIN_DURATION_OPTIONS, bp_duration)
        )
        return 1

    if bp_duration != ap_duration:
        fail(
            "hold-duration options differ from breakpoint's duration options\n"
            "  breakpoint (%s): %s\n"
            "  autopilot  (%s): %s\n"
            "  Fix: copy breakpoint's list verbatim. breakpoint.yml is frozen in "
            "MANIFEST.sha256 and is the canonical side."
            % (bp_name, bp_duration, ap_name, ap_duration)
        )

    # --- 2. the two booleans must share type AND default ---------------------
    for name in BOOLEAN_INPUTS:
        for field in BOOLEAN_FIELDS:
            bp_value = input_field(bp_file, name, field)
            ap_value = input_field(ap_file, name, field)
            if not _require_value("breakpoint %s.%s (%s)" % (name, field, bp_name), bp_value):
                return 1
            if not _require_value("autopilot %s.%s (%s)" % (name, field, ap_name), ap_value):
                return 1
            if bp_value != ap_value:
                fail(
                    "%s.%s differs: breakpoint '%s' vs autopilot '%s'\n"
                    "  Fix: match breakpoint. send-email in particular defaults to true because "
                    "on a public repo the session URL is a bearer credential."
                    % (name, field, bp_value, ap_value)
                )

    if failed:
        log.error("the autopilot's copied debug inputs have drifted from breakpoint's originals")
        return 1

    log.info(
        "autopilot debug inputs match breakpoint: duration options (%s), debug-shell and "
        "send-email type+default" % bp_duration
    )
    return 0


# The smallest pair of files the scanner accepts, used by the selftest as the base every plant is a one-field mutation of. Written out rather than copied
# from the real workflows: a fixture built by mutating a real file is a fixture
# that stops testing the day the real file is reworded, and `check-control- vacuity.sh` exists because that has happened here.
_BREAKPOINT_FIXTURE = """\
name: breakpoint
on:
  workflow_dispatch:
    inputs:
      duration:
        description: 'how long'
        type: choice
        options: ['5', '10', '15', '30', '45']
      debug-shell:
        type: boolean
        default: false
      send-email:
        type: boolean
        default: true
jobs:
  a:
    steps:
      - run: true
"""

_AUTOPILOT_FIXTURE = """\
name: autopilot
on:
  workflow_dispatch:
    inputs:
      hold-duration:
        description: 'how long'
        type: choice
        options: ['5', '10', '15', '30', '45']
      debug-shell:
        type: boolean
        default: false
      send-email:
        type: boolean
        default: true
jobs:
  a:
    steps:
      - run: true
"""


def selftest() -> int:
    """Plant every drift the gate names, plus the mirror for each.

    The mirrors are not padding. This gate's failure mode is an extractor that stopped finding anything, and an extractor that finds nothing reports DRIFT on every plant while being completely broken -- so a suite of plants alone would look perfect on a dead scanner. Each plant is therefore paired with the unmutated fixture, which must come back clean.
    """
    ctl = Controls("autopilot-breakpoint-alignment", floor=14, verbose=True)

    with tempfile.TemporaryDirectory() as tmp:
        base = pathlib.Path(tmp)
        bp = base / "breakpoint.yml"
        ap = base / "autopilot.yml"

        def run(bp_text: str | None, ap_text: str | None) -> int:
            if bp_text is None:
                bp.unlink(missing_ok=True)
            else:
                bp.write_text(bp_text, encoding="utf-8")
            if ap_text is None:
                ap.unlink(missing_ok=True)
            else:
                ap.write_text(ap_text, encoding="utf-8")
            saved = dict(os.environ)
            os.environ[BREAKPOINT_FILE_ENV] = str(bp)
            os.environ[AUTOPILOT_FILE_ENV] = str(ap)
            try:
                return main([])
            finally:
                os.environ.clear()
                os.environ.update(saved)

        ctl.check(
            "CONTROL: the unmutated pair is aligned",
            run(_BREAKPOINT_FIXTURE, _AUTOPILOT_FIXTURE),
            0,
        )

        # THE PLANT THAT MATTERS MOST. send-email's default is what decides whether a bearer-credential URL reaches a world-readable log.
        ctl.check(
            "PLANT: send-email.default drift is caught",
            run(
                _BREAKPOINT_FIXTURE,
                plant(
                    _AUTOPILOT_FIXTURE,
                    "      send-email:\n        type: boolean\n        default: true",
                    "      send-email:\n        type: boolean\n        default: false",
                ),
            ),
            1,
        )
        ctl.check(
            "PLANT: debug-shell.type drift is caught",
            run(
                _BREAKPOINT_FIXTURE,
                plant(
                    _AUTOPILOT_FIXTURE,
                    "      debug-shell:\n        type: boolean",
                    "      debug-shell:\n        type: string",
                ),
            ),
            1,
        )
        ctl.check(
            "PLANT: a dropped duration option is caught",
            run(
                _BREAKPOINT_FIXTURE,
                plant(_AUTOPILOT_FIXTURE, "'30', '45'", "'30'"),
            ),
            1,
        )
        ctl.check(
            "PLANT: a reordered duration list is caught (order is part of the value)",
            run(
                _BREAKPOINT_FIXTURE,
                plant(
                    _AUTOPILOT_FIXTURE,
                    "['5', '10', '15', '30', '45']",
                    "['10', '5', '15', '30', '45']",
                ),
            ),
            1,
        )
        # The mirror of the whole plant family: differing WHITESPACE and quoting inside the list is not drift, because normalize_options deletes both.
        ctl.check(
            "MIRROR: quoting and spacing inside the list are not drift",
            run(
                _BREAKPOINT_FIXTURE,
                plant(_AUTOPILOT_FIXTURE, "['5', '10', '15', '30', '45']", '[ 5,10, "15" ,30,45 ]'),
            ),
            0,
        )

        # ANTI-VACUITY, both files and every extraction.
        ctl.check("VACUITY: a missing breakpoint file is refused", run(None, _AUTOPILOT_FIXTURE), 1)
        ctl.check("VACUITY: a missing autopilot file is refused", run(_BREAKPOINT_FIXTURE, None), 1)
        ctl.check(
            "VACUITY: no workflow_dispatch block at all is refused",
            run(
                _BREAKPOINT_FIXTURE, "name: autopilot\njobs:\n  a:\n    steps:\n      - run: true\n"
            ),
            1,
        )
        ctl.check(
            "VACUITY: a renamed input (hold-duration gone) is refused, not passed",
            run(_BREAKPOINT_FIXTURE, plant(_AUTOPILOT_FIXTURE, "hold-duration:", "hold_duration:")),
            1,
        )
        ctl.check(
            "VACUITY: a missing send-email.default is refused, not compared to empty",
            run(
                _BREAKPOINT_FIXTURE,
                plant(
                    _AUTOPILOT_FIXTURE,
                    "      send-email:\n        type: boolean\n        default: true",
                    "      send-email:\n        type: boolean",
                ),
            ),
            1,
        )
        # A BLOCK list returns empty from this scanner by design, and the twin's comment says so: "a block list would return empty here and be caught by the anti-vacuity check rather than silently comparing nothing."
        ctl.check(
            "VACUITY: a block-style options list is refused rather than read as empty",
            run(
                _BREAKPOINT_FIXTURE,
                plant(
                    _AUTOPILOT_FIXTURE,
                    "        options: ['5', '10', '15', '30', '45']",
                    "        options:\n          - '5'\n          - '10'",
                ),
            ),
            1,
        )

        # THE FLOOR, and its mirror. Four options is below MIN_DURATION_OPTIONS, so an ALIGNED pair must still be refused -- a green there would mean the extractor matched something that is not the option list.
        four = plant(_BREAKPOINT_FIXTURE, "'30', '45'", "'30'")
        four_ap = plant(_AUTOPILOT_FIXTURE, "'30', '45'", "'30'")
        ctl.check("FLOOR: four aligned options is still a refusal", run(four, four_ap), 1)
        ctl.check(
            "FLOOR MIRROR: exactly %d aligned options passes" % MIN_DURATION_OPTIONS,
            run(_BREAKPOINT_FIXTURE, _AUTOPILOT_FIXTURE),
            0,
        )

    return 0 if ctl.report() else 1

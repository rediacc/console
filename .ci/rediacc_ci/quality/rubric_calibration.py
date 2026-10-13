"""A calibrated rubric may not change without being re-calibrated.

Ported from `.ci/scripts/quality/check-rubric-calibration.sh`, retired in W7 P5; see `rediacc_ci.quality.__init__` for the phase-5 decision that retired the twin.

THE GAP. Three prompt constants drive the stop judge's rules, and each has a fixture set in `.claude/hooks/stop/calibrate-judge-rules.py` that scores it against a REAL model: SWEEP_PROMPT (SWEEP_CASES), BRAVE_PROMPT (BRAVE_CASES), REGGATE_PROMPT, SHAPE_PROMPT (SHAPE_CASES). Nothing forced the two to move together. Editing a rubric is cheap and silent; re-calibrating costs 14 live
model calls and several minutes, so the pressure is entirely toward skipping it -- and a rubric whose calibration describes an older text is a rubric nobody has measured.

`wl_classsweep`'s own docstring records that its examples ARE the calibration set the operator supplied. That session trimmed five of them to three, which is exactly the edit this gate exists to catch: it was re-calibrated by choice, not by machinery.

WHAT THIS DOES NOT CLAIM. It cannot verify the calibration PASSED -- only that the recorded hash matches the text on disk, so a human or a session had the current text in front of the model. Recording a hash after a 12/14 run is possible and is a lie the gate cannot see; the run's own output is the evidence for that.

THE SOURCE MAP, carried with its history intact:

  SWEEP_PROMPT    .claude/hooks/stop/wl_classsweep.py
  BRAVE_PROMPT    .claude/hooks/stop/wl_bravedefault.py
  REGGATE_PROMPT  .claude/hooks/stop/worklist_messages.py
  SHAPE_PROMPT    .claude/hooks/stop/wl_shapedup.py

SHAPE_PROMPT was added 2026-09-02. It had live fixtures (SHAPE_CASES) and was calibrated by the same runner, yet was absent from this map -- so its text could drift with nothing noticing, which is the one thing this gate exists to prevent. It was the only rubric in that state with fixtures already written; the remaining five (FOLLOWUP, DEFER_AUDIT, TRIAGE, ADMISSION, PLANFID) have
neither fixtures nor a hash, and adding a hash without fixtures would freeze text nothing has ever proven correct.

THE OTHER DIRECTION, and it was missing until it was probed. The comparison walks the rubrics found in SOURCE and looks each up in the manifest; a manifest entry naming a rubric that no longer exists is never visited. Probed 2026-09-04 by planting NO_SUCH_RUBRIC_XYZ: the gate printed "all 4 calibrated rubric(s) match"
while the file held five, so a calibration could outlive the rubric it measured
and read as coverage. Its sibling `.ci/scripts/ci/shadow-compare.sh` already refuses the same shape ("is in SHADOW_EXPECTED_MISMATCH but not in SHADOW_NAMES -- it excuses nothing here").

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

THE TWIN IS ALREADY MOSTLY PYTHON, RUN THROUGH TWO HEREDOCS. `hashes()` is a `python3 - "$1" <<'PY'` block and the manifest comparison is a `python3 - "$MANIFEST" <<PY` block -- note the UNQUOTED marker on the second, which is what lets `'''$live'''` interpolate the first block's JSON output through the shell. That interpolation is the port's one genuine safety improvement and it
is worth naming rather than silently removing: a rubric hash is 16 hex characters so it can never contain a quote today, but the value crossing a shell expansion into a Python string literal is a shape that only stays safe by accident of what happens to be in it. In the port the two halves are one process and the value never becomes source text.

THE SORT ORDER OF `bad` IS PRESERVED, AND IT IS NOT OBVIOUS. The twin's first
heredoc prints `json.dumps(out, sort_keys=True)` and the second parses that back,
so `live.items()` iterates in SORTED KEY order even though `SRC` is written in a different order. A port that iterated `SRC` would report the same findings in a different sequence -- which the shadow comparator would forgive, since it compares a multiset -- but a human diffing two logs would not. `live` is therefore built sorted.

THE FLOOR SAYS THREE WHILE FOUR RUBRICS EXIST, and that is deliberate in the original: SHAPE_PROMPT was added later and the floor was not raised with it. It is carried at 3 unchanged. Raising it would be a behaviour change, and this file's job is to keep the verdict; it is reported as a finding instead.

-----------------------------------------------------------------------------
TWO CHECKS ADDED 2026-10-09, for review 18700a76.
-----------------------------------------------------------------------------

A RIDING RUBRIC RECORDS THE HASH OF WHAT IT RIDES (18700a76.5). REGGATE_PROMPT has no fixtures of its own: the calibrator measures it through SWEEP_CASES, every one of which is judged in a prompt carrying REGGATE_PROMPT and SWEEP_PROMPT together (`sweep_extra` in calibrate-judge-rules.py, and `run_judge` appending the sweep section). So each of the two passes is a measurement of BOTH texts, and a recorded sha for one said nothing about the other: REGGATE was recorded fully calibrated at a sha that did not move when SWEEP_PROMPT, the text its only fixtures ran under, was rewritten. RIDES names that coupling in code, where the manifest cannot drop it; the manifest entry carries `rides: {<rubric>: <sha>}` measured in the same run, and the gate refuses an entry whose ride-along hash is absent, stale, or names a rubric RIDES does not declare.

A FIXTURE IS HELD OUT FROM THE RUBRIC IT CALIBRATES (18700a76.4). The rubrics teach by worked example, and the examples are the measured defects, so a fixture worded as an example scores whether the model recognises a quoted sentence, not whether it applies the rule. 18700a769 quoted a whole brave fixture, question, default and answer, into BRAVE_PROMPT. Every string a fixture SENDS to the model (not its label or expected answer) is compared with every calibrated rubric, and a shared run of FIXTURE_NGRAM words is refused. Five words is measured, not chosen: on the tree that prompted it, five caught the four brave defaults and the typo control the prompts quote, and no fixture/rubric pair shared any five-word run that was not a quotation. Read by `ast`, never by importing the calibrator, which imports the whole stop hook.
"""

import ast
import hashlib
import json
import pathlib
import re
import shutil
import sys
import tempfile

from rediacc_ci import paths
from rediacc_ci.controls import Controls, plant

# The manifest, and the default the twin uses when given no argument.
DEFAULT_MANIFEST = ".ci/config/rubric-calibration.json"

# The rubric constants and the file each lives in, relative to the repo root. See the module docstring for why SHAPE_PROMPT arrived late and why five other prompts are deliberately absent.
SOURCES = {
    "SWEEP_PROMPT": ".claude/hooks/stop/wl_classsweep.py",
    "BRAVE_PROMPT": ".claude/hooks/stop/wl_bravedefault.py",
    "REGGATE_PROMPT": ".claude/hooks/stop/worklist_messages.py",
    "SHAPE_PROMPT": ".claude/hooks/stop/wl_shapedup.py",
}

# {rubric: the rubrics whose text is in the same prompt as its fixtures}. Both directions, because both passes come from the same sweep fixtures (SWEEP_CASES, every entry): an edit to either text leaves the OTHER's recorded pass describing a prompt that no longer exists. See the module docstring.
RIDES = {
    "REGGATE_PROMPT": ("SWEEP_PROMPT",),
    "SWEEP_PROMPT": ("REGGATE_PROMPT",),
}

# The calibrator and the fixture lists in it, read by `ast`.
CALIBRATOR = ".claude/hooks/stop/calibrate-judge-rules.py"
FIXTURE_LISTS = ("SWEEP_CASES", "BRAVE_CASES", "SHAPE_CASES")
# Elements 0 and 1 of every fixture tuple are its label and its expected answer, which never reach the model; the rest is what the calibrator sends.
FIXTURE_SENT_FROM = 2
FIXTURE_NGRAM = 5

# FLOOR. Three constants existed when the floor was written. Finding fewer means a rename moved one out of reach and this green would assert nothing about it. See the module docstring: the value is stale by one and is carried unchanged anyway.
MIN_RUBRICS = 3

# 16 hex characters of sha256. Not the full digest, matching the twin, so a recorded hash stays readable in a JSON file a human edits.
HASH_CHARS = 16


def texts(root: pathlib.Path) -> dict[str, str]:
    """{constant: text} for every rubric whose file and heredoc are present, sorted by name.

    A missing FILE and a missing CONSTANT both yield an absent key rather than an error, exactly as the twin's `continue` and unmatched-regex do. That is what makes the floor below load-bearing: absence is silent here, so something has to count what came back.
    """
    out: dict[str, str] = {}
    for name, relative in SOURCES.items():
        path = root / relative
        if not path.exists():
            continue
        # `^NAME = \"\"\"(.*?)\"\"\"` with DOTALL and MULTILINE, non-greedy so the
        # first closing triple-quote ends the constant. Anchored at the start of a line so a mention of the name inside another string cannot match.
        match = re.search(
            r'^%s = """(.*?)"""' % name, path.read_text(encoding="utf-8"), re.DOTALL | re.MULTILINE
        )
        if match:
            out[name] = match.group(1)
    # Sorted, because the twin round-trips this through `json.dumps(sort_keys=True)`
    # and every later iteration inherits that order. See the port notes.
    return dict(sorted(out.items()))


def hashes(root: pathlib.Path) -> dict[str, str]:
    """{constant: sha256[:16]} for every rubric `texts` finds."""
    return {
        name: hashlib.sha256(text.encode()).hexdigest()[:HASH_CHARS]
        for name, text in texts(root).items()
    }


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [s for item in value for s in _strings(item)]
    return []


class FixtureShapeError(ValueError):
    """A fixture entry the gate does not know how to read, named by list and index."""


def fixtures(source: str) -> dict[str, list[tuple[str, list[str]]]]:
    """{list name: [(label, the strings it sends to the model)]} for each FIXTURE_LISTS assignment found in the calibrator's source. A list that is absent or not a literal is absent here, and the caller's floor refuses that.

    EVERY ENTRY IS READ OR REFUSED (review fdb82cba.2). A tuple and a list are the same fixture to the calibrator, so both are read; any other entry (a dict, a bare string, a sequence too short to send anything) raises FixtureShapeError naming it. Dropping it silently was a fixture the held-out scan never saw, so a list-shaped fixture could quote its rubric under a green gate.
    """
    out: dict[str, list[tuple[str, list[str]]]] = {}
    for node in ast.parse(source).body:
        if not (isinstance(node, ast.Assign) and len(node.targets) == 1):
            continue
        target = node.targets[0]
        if not (isinstance(target, ast.Name) and target.id in FIXTURE_LISTS):
            continue
        try:
            cases = ast.literal_eval(node.value)
        except ValueError:
            continue
        if not isinstance(cases, (list, tuple)):
            raise FixtureShapeError(
                "%s is a %s, not a list of fixtures" % (target.id, type(cases).__name__)
            )
        entries: list[tuple[str, list[str]]] = []
        for index, case in enumerate(cases):
            if not isinstance(case, (list, tuple)) or len(case) <= FIXTURE_SENT_FROM:
                raise FixtureShapeError(
                    "%s[%d] is %s; a fixture is a tuple or list of (label, expected, what it sends...)"
                    % (target.id, index, _shape(case))
                )
            entries.append((str(case[0]), _strings(list(case[FIXTURE_SENT_FROM:]))))
        out[target.id] = entries
    return out


def _shape(case: object) -> str:
    if isinstance(case, (list, tuple)):
        return "a %s of %d element(s)" % (type(case).__name__, len(case))
    return "a %s" % type(case).__name__


def _words(text: str) -> list[str]:
    # Lowercased words, punctuation inside a token kept (`check:ci-x`, `don't`, `a/b.py`), punctuation around it dropped, so "branch." and "branch" are one word.
    return re.findall(r"[a-z0-9]+(?:['._/$:-][a-z0-9]+)*", text.lower())


def quoted(
    rubrics: dict[str, str], cases: dict[str, list[tuple[str, list[str]]]], n: int = FIXTURE_NGRAM
) -> list[tuple[str, str, str, str]]:
    """[(list, label, rubric, the shared run)] for every fixture that shares `n` consecutive words with a rubric. One finding per (fixture, rubric) pair, naming the first run found, so a quoted paragraph is one line rather than forty."""
    grams = {
        name: {" ".join(w[i : i + n]) for i in range(len(w) - n + 1)}
        for name, w in ((name, _words(text)) for name, text in rubrics.items())
    }
    found: list[tuple[str, str, str, str]] = []
    for list_name, entries in cases.items():
        for label, sent in entries:
            for rubric, rubric_grams in grams.items():
                hit = next(
                    (
                        g
                        for s in sent
                        for w in [_words(s)]
                        for g in (" ".join(w[i : i + n]) for i in range(len(w) - n + 1))
                        if g in rubric_grams
                    ),
                    None,
                )
                if hit:
                    found.append((list_name, label, rubric, hit))
    return found


def run_control() -> int:
    """CONTROL, before the real run. A gate that cannot fire is worse than no gate.

    Two assertions, and they cover different failures. That a CHANGED rubric produces a DIFFERENT hash proves the extractor is reading the constant rather than, say, the file's mtime. That the extractor found a constant AT ALL proves the regex still matches the shape these files are written in -- without it,
    an extractor that returns `{}` for everything would satisfy the first
    assertion trivially, since `{} != {}` is false but so is any comparison it
    could make.
    """
    with tempfile.TemporaryDirectory() as tmp:
        ctl = pathlib.Path(tmp)
        target = ctl / ".claude/hooks/stop"
        target.mkdir(parents=True)
        sweep = target / "wl_classsweep.py"
        sweep.write_text('SWEEP_PROMPT = """original text"""\n', encoding="utf-8")
        before = hashes(ctl)
        sweep.write_text('SWEEP_PROMPT = """MUTATED text"""\n', encoding="utf-8")
        after = hashes(ctl)
        if before == after:
            print(
                "CONTROL DID NOT FIRE: a changed rubric produced an identical hash", file=sys.stderr
            )
            return 1
        if "SWEEP_PROMPT" not in before:
            print(
                "CONTROL COULD NOT PLANT: the extractor found no constant in the fixture",
                file=sys.stderr,
            )
            return 1
    print("✓ control: a changed rubric changes its hash, and the extractor finds one")
    return 0


def check_rides(recorded: dict, live: dict[str, str], manifest_name: str) -> int:
    """The ride-along hashes. 0 when every RIDES entry is recorded and current and no entry carries a ride RIDES does not declare."""
    problems: list[str] = []
    for key in sorted(recorded):
        rides = recorded[key].get("rides")
        declared = set(RIDES.get(key, ()))
        if rides is None:
            if declared:
                problems.append(
                    "%s rides %s but records no `rides` hash for it"
                    % (key, ", ".join(sorted(declared)))
                )
            continue
        if not isinstance(rides, dict):
            problems.append("%s: `rides` is not an object" % key)
            continue
        problems.extend(
            "%s rides %s but records no hash for it" % (key, other)
            for other in sorted(declared - set(rides))
        )
        problems.extend(
            "%s records a ride on %s, which RIDES does not declare; a hash nothing"
            " requires reads as a coupling that was measured" % (key, other)
            for other in sorted(set(rides) - declared)
        )
        problems.extend(
            "%s rides %s, which changed since %s was calibrated"
            "\n    recorded %s  now %s"
            % (key, other, key, rides[other], live.get(other, "(absent)"))
            for other in sorted(declared & set(rides))
            if rides[other] != live.get(other)
        )
    if not problems:
        return 0
    for line in problems:
        print("✗ %s" % line, file=sys.stderr)
    print(file=sys.stderr)
    print("  Its fixtures run in one prompt with the rubric it rides, so a pass", file=sys.stderr)
    print("  recorded for one text says nothing once the other moves. Re-run:", file=sys.stderr)
    print("    python3 .claude/hooks/stop/calibrate-judge-rules.py --live", file=sys.stderr)
    print("  and record the ridden sha under `rides` in %s." % manifest_name, file=sys.stderr)
    return 1


def check_held_out(root: pathlib.Path, rubrics: dict[str, str]) -> tuple[int, int]:
    """(rc, fixtures scanned). rc 1 when the calibrator's fixture lists are missing or any fixture quotes a rubric."""
    path = root / CALIBRATOR
    if not path.is_file():
        print("✗ no calibrator at %s; the fixtures cannot be read" % CALIBRATOR, file=sys.stderr)
        return 1, 0
    try:
        cases = fixtures(path.read_text(encoding="utf-8"))
    except FixtureShapeError as exc:
        print(
            "✗ %s: %s. The held-out check cannot scan it, and dropping it would let it quote"
            " its rubric under a green gate." % (CALIBRATOR, exc),
            file=sys.stderr,
        )
        return 1, 0
    missing = [name for name in FIXTURE_LISTS if not cases.get(name)]
    if missing:
        print(
            "✗ %s: no literal %s found. The held-out check would compare nothing,"
            " and its green would mean nothing." % (CALIBRATOR, ", ".join(missing)),
            file=sys.stderr,
        )
        return 1, 0
    scanned = sum(len(v) for v in cases.values())
    found = quoted(rubrics, cases)
    if not found:
        return 0, scanned
    for list_name, label, rubric, run in found:
        print(
            "✗ %s fixture %r shares %r with %s" % (list_name, label, run, rubric), file=sys.stderr
        )
    print(file=sys.stderr)
    print(
        "  A fixture worded as its rubric's own example measures whether the model", file=sys.stderr
    )
    print("  recognises the sentence, not whether it applies the rule. Reword the", file=sys.stderr)
    print(
        "  fixture (or the example) so no %d-word run is shared." % FIXTURE_NGRAM, file=sys.stderr
    )
    print("  Do not exempt it.", file=sys.stderr)
    return 1, scanned


def run(root: pathlib.Path, manifest_name: str) -> int:
    manifest = root / manifest_name

    if run_control() != 0:
        return 1

    rubrics = texts(root)
    live = hashes(root)
    if len(live) < MIN_RUBRICS:
        print(
            "✗ found only %d calibrated rubric(s); expected %d. A constant was renamed or"
            % (len(live), MIN_RUBRICS),
            file=sys.stderr,
        )
        print(
            "  its heredoc shape changed, and this green would cover it no longer.", file=sys.stderr
        )
        return 1

    if not manifest.is_file():
        print("✗ no calibration manifest at %s" % manifest_name, file=sys.stderr)
        return 1

    recorded = json.loads(manifest.read_text(encoding="utf-8"))["rubrics"]

    # THE OTHER DIRECTION FIRST, because it is the one that was missing. A manifest entry naming a rubric that is gone is never visited by the sha comparison below, and reads as coverage.
    orphans = sorted(set(recorded) - set(live))
    if orphans:
        for key in orphans:
            print(
                "✗ %s is calibrated in the manifest but no such rubric exists in source" % key,
                file=sys.stderr,
            )
        print(file=sys.stderr)
        print(
            "  A calibration for a rubric that is gone measures nothing and reads as",
            file=sys.stderr,
        )
        print("  coverage. Delete the entry from %s." % manifest_name, file=sys.stderr)
        return 1

    bad = [key for key, value in live.items() if recorded.get(key, {}).get("sha") != value]
    if bad:
        for key in bad:
            print("✗ %s changed since it was last calibrated" % key, file=sys.stderr)
            print(
                "    recorded %s  now %s"
                % (recorded.get(key, {}).get("sha", "(absent)"), live[key]),
                file=sys.stderr,
            )
        print(file=sys.stderr)
        print("  Re-calibrate, then record the new hash:", file=sys.stderr)
        print("    python3 .claude/hooks/stop/calibrate-judge-rules.py --live", file=sys.stderr)
        print("  Require the full pass, then update %s." % manifest_name, file=sys.stderr)
        return 1

    if check_rides(recorded, live, manifest_name) != 0:
        return 1

    rc, scanned = check_held_out(root, rubrics)
    if rc != 0:
        return 1

    print(
        "✓ all %d calibrated rubric(s) match the text they were measured on, "
        "and no manifest entry names a rubric that is gone" % len(live)
    )
    print(
        "✓ %d ride-along hash(es) current (%s); %d fixture(s) across %d list(s) share no "
        "%d-word run with a rubric"
        % (
            sum(len(v) for v in RIDES.values()),
            ", ".join("%s rides %s" % (k, "+".join(v)) for k, v in sorted(RIDES.items())),
            scanned,
            len(FIXTURE_LISTS),
            FIXTURE_NGRAM,
        )
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()
    return run(paths.repo_root(), args[0] if args else DEFAULT_MANIFEST)


def _truthful(live: dict[str, str]) -> dict:
    return {
        "rubrics": {
            k: dict({"sha": v}, **({"rides": {o: live[o] for o in RIDES[k]}} if k in RIDES else {}))
            for k, v in live.items()
        }
    }


def selftest() -> int:
    """Plant each finding class and its mirror.

    The manifest plants run against the real tree's rubric text. The ride-along and held-out plants run against a COPY of the real rubric files and calibrator in a temporary root, edited the way a session would edit them, so they prove the gate reads the real shapes rather than a fixture written to suit it.
    """
    ctl = Controls("rubric-calibration", floor=19, verbose=True)
    real = paths.repo_root()
    live = hashes(real)

    with tempfile.TemporaryDirectory() as tmp:
        base = pathlib.Path(tmp)

        def manifest(payload: object) -> str:
            path = base / "m.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            return str(path)

        truthful = _truthful(live)
        ctl.check("CONTROL: a truthful manifest passes", main([manifest(truthful)]), 0)

        # THE PLANT. One recorded sha no longer describes the text on disk, which is precisely "a rubric whose calibration describes an older text".
        first = min(live)
        stale = _truthful(live)
        stale["rubrics"][first]["sha"] = "0" * HASH_CHARS
        ctl.check("PLANT: one stale sha is caught", main([manifest(stale)]), 1)

        # Every sha stale, so a gate that only ever looks at the first key fails the same way and this control alone would not distinguish them -- which is why the single-key plant above exists as well.
        allstale = _truthful(live)
        for entry in allstale["rubrics"].values():
            entry["sha"] = "1" * HASH_CHARS
        ctl.check("PLANT: every stale sha is caught", main([manifest(allstale)]), 1)

        # A rubric present in source but ABSENT from the manifest: `.get(key, {})`
        # yields `(absent)` and the entry is bad. Not the orphan direction.
        missing = _truthful(live)
        del missing["rubrics"][first]
        ctl.check("PLANT: an uncalibrated rubric is caught", main([manifest(missing)]), 1)

        # THE DIRECTION THAT WAS MISSING, replanted with the same name the 2026-09-04 probe used, so the record and the control agree.
        orphan = _truthful(live)
        orphan["rubrics"]["NO_SUCH_RUBRIC_XYZ"] = {"sha": "2" * HASH_CHARS}
        ctl.check("PLANT: an orphaned manifest entry is caught", main([manifest(orphan)]), 1)

        # ORDER MATTERS: an orphan AND a stale sha must report the orphan, because a stale-sha report would send the reader to re-calibrate a rubric that no longer exists.
        both = _truthful(live)
        both["rubrics"][first]["sha"] = "3" * HASH_CHARS
        both["rubrics"]["NO_SUCH_RUBRIC_XYZ"] = {"sha": "4" * HASH_CHARS}
        ctl.check("ORDER: orphan is reported before stale sha", main([manifest(both)]), 1)

        ctl.check("PLANT: a missing manifest is refused", main([str(base / "absent.json")]), 1)

        # RIDES, finding 18700a76.5: each way a ride-along hash can lie.
        rider, ridden = "REGGATE_PROMPT", RIDES["REGGATE_PROMPT"][0]
        no_rides = _truthful(live)
        del no_rides["rubrics"][rider]["rides"]
        ctl.check("PLANT: a rider with no `rides` is caught", main([manifest(no_rides)]), 1)
        stale_ride = _truthful(live)
        stale_ride["rubrics"][rider]["rides"][ridden] = "5" * HASH_CHARS
        ctl.check("PLANT: a stale ride-along hash is caught", main([manifest(stale_ride)]), 1)
        undeclared = _truthful(live)
        undeclared["rubrics"]["BRAVE_PROMPT"]["rides"] = {"SHAPE_PROMPT": live["SHAPE_PROMPT"]}
        ctl.check("PLANT: an undeclared ride is caught", main([manifest(undeclared)]), 1)

        # THE REAL EDIT the finding describes, on a copy of the tree: SWEEP_PROMPT is rewritten and its OWN sha re-recorded, as a session that re-ran only the fixtures it changed would do. REGGATE's sha still matches; only the ride-along hash can see it.
        copy = base / "tree"
        for rel in [*SOURCES.values(), CALIBRATOR]:
            (copy / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(real / rel, copy / rel)
        sweep = copy / SOURCES["SWEEP_PROMPT"]
        sweep.write_text(
            plant(
                sweep.read_text(encoding="utf-8"),
                "SWEEP THE CLASS, NOT THE INSTANCE.",
                "SWEEP THE CLASS.",
                1,
            ),
            encoding="utf-8",
        )
        edited = hashes(copy)
        ctl.check(
            "CONTROL: the plant moved SWEEP_PROMPT's sha",
            edited["SWEEP_PROMPT"] != live["SWEEP_PROMPT"],
            True,
        )
        resha = _truthful(live)
        resha["rubrics"]["SWEEP_PROMPT"]["sha"] = edited["SWEEP_PROMPT"]
        ctl.check(
            "PLANT: a SWEEP_PROMPT edit invalidates REGGATE's pass", run(copy, manifest(resha)), 1
        )
        ctl.check(
            "MIRROR: recording the new ride-along hash passes",
            run(copy, manifest(_truthful(edited))),
            0,
        )

        # HELD OUT, finding 18700a76.4: a brave fixture reworded into the sentence BRAVE_PROMPT quotes, which is what 18700a769 shipped.
        cal = copy / CALIBRATOR
        clean_cal = cal.read_text(encoding="utf-8")
        ctl.check(
            "CONTROL: the copied calibrator's fixtures are held out",
            run(copy, manifest(_truthful(edited))),
            0,
        )
        brave_text = texts(copy)["BRAVE_PROMPT"]
        # The LONGEST quoted default, because a four-word one ("DEFAULT: keep carrying it.") is under the run length and would make this plant vacuous: measured, it did.
        examples = re.findall(r"DEFAULT: [^\n.]+\.", brave_text)
        quote = max(examples, key=lambda e: len(_words(e)), default="")
        ctl.truthy(
            "CONTROL: BRAVE_PROMPT carries a DEFAULT example long enough to quote",
            len(_words(quote)) >= FIXTURE_NGRAM,
        )
        cal.write_text(
            plant(clean_cal, "DEFAULT: let it sit where it is for now.", quote or "x", 1),
            encoding="utf-8",
        )
        ctl.check(
            "PLANT: a fixture quoting its rubric is caught",
            run(copy, manifest(_truthful(edited))),
            1,
        )
        # A LABEL is never sent, so quoting the rubric there is not a leak. Without this the check could be satisfied only by renaming fixtures.
        cal.write_text(
            plant(
                clean_cal,
                '"HELD-OUT (measured: keep carrying it)"',
                '"HELD-OUT %s"' % (quote or "x"),
                1,
            ),
            encoding="utf-8",
        )
        ctl.check(
            "CONTROL: the same words in a LABEL are not a leak",
            run(copy, manifest(_truthful(edited))),
            0,
        )
        # A LIST-SHAPED FIXTURE IS A FIXTURE (review fdb82cba.2): the same quote, in a fixture written with brackets, is still caught, and an entry of no known shape is refused rather than dropped.
        cal.write_text(
            plant(
                clean_cal,
                "BRAVE_CASES = [\n",
                "BRAVE_CASES = [\n    ['as a list', 'fire', %r],\n" % ("x? " + (quote or "x")),
                1,
            ),
            encoding="utf-8",
        )
        ctl.check(
            "PLANT: a list-shaped fixture quoting its rubric is caught",
            run(copy, manifest(_truthful(edited))),
            1,
        )
        # The mirror, so a gate that refused every list would fail here rather than pass the plant above for the wrong reason.
        cal.write_text(
            plant(
                clean_cal,
                "BRAVE_CASES = [\n",
                "BRAVE_CASES = [\n    ['as a list', 'silent', 'a clean question, held out'],\n",
                1,
            ),
            encoding="utf-8",
        )
        ctl.check(
            "MIRROR: a list-shaped fixture that quotes nothing passes",
            run(copy, manifest(_truthful(edited))),
            0,
        )
        cal.write_text(
            plant(clean_cal, "BRAVE_CASES = [\n", "BRAVE_CASES = [\n    {'label': 'x'},\n", 1),
            encoding="utf-8",
        )
        ctl.check(
            "PLANT: a fixture of no known shape is refused",
            run(copy, manifest(_truthful(edited))),
            1,
        )
        # ZERO FIXTURES IS A FAILURE: a renamed list must not read as "nothing quoted".
        cal.write_text(
            plant(clean_cal, "BRAVE_CASES = [", "BRAVE_FIXTURES = [", 1), encoding="utf-8"
        )
        ctl.check(
            "PLANT: a fixture list the gate cannot find is refused",
            run(copy, manifest(_truthful(edited))),
            1,
        )
        cal.write_text(clean_cal, encoding="utf-8")

        # THE MIRROR of every plant above: the truthful manifest, again, AFTER the refusals. A gate that got stuck in a failed state would fail here and nowhere else.
        ctl.check("MIRROR: the truthful manifest still passes", main([manifest(truthful)]), 0)

    return 0 if ctl.report() else 1

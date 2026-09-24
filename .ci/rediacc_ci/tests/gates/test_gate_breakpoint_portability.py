"""Port of `.ci/scripts/test/gates/test-breakpoint-portability.sh`, retired in W7 P5.

Makes the "self-contained, copyable folder" claim about `.ci/breakpoint/` ENFORCEABLE rather than aspirational.

`.ci/breakpoint/` exists to be copied wholesale into renet / account / elite, repos that have no `.ci/scripts/`, no package.json, no app-token plumbing and no rediacc-specific anything. Nothing about a copy FAILS loudly when that stops being true: the folder keeps working here, in console, where all of those things happen to exist, and only breaks in the downstream repo months
later, in somebody
else's CI, with an error that points nowhere useful.

SO THE FIXTURE IS THE POINT. Every case runs against a COPY of `.ci/breakpoint/` made into an empty temp dir with no `.ci/scripts`, no package.json and no `.git` alongside it. What passes there is what a downstream repo actually gets. NOTHING HERE WRITES UNDER `.ci/breakpoint/`: the two cases that mutate (deleting `MANIFEST.sha256`, mutating the canonical validator) mutate the
COPY, which is what makes this subject safe to drive from a tree holding other sessions' work.

TWO ASSERTIONS ARE NARROWER THAN THEY LOOK, both written strict first and both having found something real:
  * console's script tree IS referenced, in three scripts, as an OPTIONAL hook
    guarded by `[[ -x ]]`. That is portable (absent means skipped), so the case
    pins the exact file set plus the guard, not a blanket zero.
  * `rediacc/` IS present in scripts, as a `${BREAKPOINT_UPSTREAM_REPO:-}`
    fallback default and one usage example. Those are conf-overridable or
    diagnostic, so the case pins those two shapes, not a blanket zero.
Both keep the property that a NEW hardcoded reference is red.

WHY THIS MODULE OPTS IN TO THE REAL-TREE GROUP. `gates.lock.json` records `reads: ["tree:repo"]` for `gate-test:breakpoint-portability`: every case copies `.ci/breakpoint/` and the subset cases read `.ci/scripts/lib/blocker-validator.sh`
while another gate may be rewriting neither, but the lock is the contract and
`real_tree_admission` refuses a twin in that set that does not declare `REAL_TREE_TWIN`.

`check_subset` TAKES ITS EXTRACTOR AS AN ARGUMENT, which is the port's shape for the twin's function shadowing. The flaky-read control needs the SAME code path driven with a truncating reader; a control that re-implemented the comparison would prove only that it agrees with itself.
"""

import hashlib
import os
import pathlib
import re
import shutil

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

# `gate-test:breakpoint-portability` carries `reads: ["tree:repo"]`.
REAL_TREE_TWIN = True

ROOT = paths.repo_root()
BP_SRC = ROOT / ".ci" / "breakpoint"
CANONICAL_VALIDATOR = ROOT / ".ci" / "scripts" / "lib" / "blocker-validator.sh"

# The scripts allowed to reach for console's tree, and the reason. Each calls a console-only service helper behind an `[[ -x ]]` existence test, so a repo without that tree takes an explicit branch instead of dying obscurely.
#
# An EXACT set, not a prefix or a count: a new hardcoded reference is red until it is listed here with a justification. Widening it is a decision, which is the point. `workflow/breakpoint.yml` joined on 2026-09-03 and LEFT AGAIN on 2026-09-04, which is the outcome this rule is for -- the set narrows rather than widening, and that only happens if it is asserted exactly.
ALLOWED_CONSOLE_HOOKS = (
    "scripts/pull-service-images.sh",
    "scripts/start-origin.sh",
    "scripts/stop-breakpoint.sh",
)

FILE_SUFFIXES = (".sh", ".yml", ".yaml")

# A whole-line comment, in the twin's `grep -Ev '^[0-9]+:[[:space:]]*#'` sense. Comments matter here: most of breakpoint's references to console are prose explaining what was deleted and why, and a scan that cannot tell prose from code would force the docs to be stripped.
COMMENT_RE = re.compile(r"^[ \t]*#")

# `readonly NAME=(` ... `)` at column 1, the twin's awk program.
ASSIGNED_NAME_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=")
QUOTED_RE = re.compile(r'"([^"]*)"')

CANON_ARRAY = "LOW_EFFORT_BLOCKER_PATTERNS"
VENDORED_ARRAY = "BREAKPOINT_LOW_EFFORT_BLOCKERS"

# Floors on each read. Both are documented as INSUFFICIENT on their own by the twin, which is why the second independent read exists beside them.
CANON_FLOOR = 30
VENDORED_FLOOR = 20


def make_isolated(tmp: pathlib.Path) -> pathlib.Path:
    """An isolated copy with NOTHING around it."""
    if not BP_SRC.is_dir():
        raise harness.GateAssertionError(
            "%s is gone; every case here copies it and would be asserting about an empty "
            "directory" % paths.relative_to_root(BP_SRC)
        )
    (tmp / ".ci").mkdir(parents=True, exist_ok=True)
    target = tmp / ".ci" / "breakpoint"
    shutil.copytree(BP_SRC, target, symlinks=True)
    return target


def bp_files(root: pathlib.Path) -> list[str]:
    """Every shell/workflow file in the copy, relative, in C order."""
    found = []
    for dirpath, _dirnames, filenames in os.walk(root):
        found.extend(
            os.path.relpath(os.path.join(dirpath, name), root)
            for name in filenames
            if name.endswith(FILE_SUFFIXES)
        )
    return sorted(found)


def bp_code_hits(root: pathlib.Path, pattern: str) -> list[str]:
    """`<relpath>:<lineno>` for every matching line that is NOT a whole-line comment."""
    regex = re.compile(pattern)
    hits = []
    for rel in bp_files(root):
        try:
            text = (root / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for number, line in enumerate(text.split("\n"), start=1):
            if COMMENT_RE.match(line):
                continue
            if regex.search(line):
                hits.append("%s:%d" % (rel, number))
    return hits


def bp_hit_files(root: pathlib.Path, pattern: str) -> list[str]:
    """Just the distinct files, in C order."""
    return sorted({hit.rsplit(":", 1)[0] for hit in bp_code_hits(root, pattern)})


def extract_array(path: pathlib.Path, name: str) -> list[str]:
    """The quoted string elements of a `readonly <name>=(` array literal.

    Comment lines inside the array carry no quotes and are therefore skipped for free, exactly as the twin's `grep -oE '"[^"]*"'` skips them.
    """
    start = "readonly %s=(" % name
    out: list[str] = []
    inside = False
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    for line in text.split("\n"):
        if line.startswith(start):
            inside = True
            continue
        if inside and line.startswith(")"):
            inside = False
            continue
        if inside:
            out.extend(QUOTED_RE.findall(line))
    return out


def check_subset(canon_path: pathlib.Path, bp: pathlib.Path, extract=extract_array):
    """`(rc, log)` for "the vendored BLOCKER list is a subset of the canonical one".

    A SEPARATE FUNCTION taking both paths AND its extractor, precisely so the planted-defect controls below can drive it against synthetic inputs instead of only ever exercising today's real, already-agreeing files. A test that only runs the happy path proves the mechanism ran, never that it can still catch anything -- which is exactly how the two count-floors this function
    replaced went undetected until they misfired in CI.

    THE RE-VERIFICATION IS THE POINT, and it is ANNOUNCED rather than silent. The `canon_count` floor was added after a truncated canonical read false-accused the vendored list on 2026-07-31, and it is NOT sufficient: on 2026-08-28 the lane reported "vendored-only phrase: 'skipped'" and failed while the same gate passed standalone three times, and a read that drops ONE phrase
    clears a floor of 30 comfortably. A second, independent read separates the two cases by construction: a transient truncation does not survive it, a real subset violation does.
    """
    log: list[str] = []

    def fail(message: str) -> tuple[int, str]:
        log.append(message)
        return 1, "\n".join(log)

    canon = extract(canon_path, CANON_ARRAY)
    vendored = extract(bp / "lib" / "breakpoint-blocker.sh", VENDORED_ARRAY)
    if not canon:
        return fail("could not parse %s out of %s" % (CANON_ARRAY, canon_path))
    if not vendored:
        return fail("could not parse %s out of the vendored copy" % VENDORED_ARRAY)
    if len(canon) < CANON_FLOOR:
        return fail(
            "only %d canonical phrases parsed; the extractor or its read was truncated, "
            "not the list" % len(canon)
        )

    canon2: list[str] | None = None
    missing = 0
    count = 0
    for phrase in vendored:
        count += 1
        if phrase in canon:
            continue
        if canon2 is None:
            canon2 = extract(canon_path, CANON_ARRAY)
        if phrase in canon2:
            log.append("  re-verified: '%s' IS canonical; the first read was short" % phrase)
            continue
        log.append("  vendored-only phrase: '%s' (absent from two independent reads)" % phrase)
        missing += 1

    # THE VENDORED FLOOR HAS THE SAME WEAKNESS AS THE CANONICAL ONE, in the more dangerous direction. A canonical read that drops a phrase produces a false RED, which is loud. A VENDORED read that drops one produces a false GREEN: fewer phrases are checked, `missing` stays 0, and the pass line reports "all N ... exist" with an N nobody compares against the truth.
    count2 = len(extract(bp / "lib" / "breakpoint-blocker.sh", VENDORED_ARRAY))
    if count != count2:
        return fail(
            "vendored read is unstable: %d phrases then %d; the extractor or its read is "
            "at fault, not the list" % (count, count2)
        )
    if count < VENDORED_FLOOR:
        return fail(
            "only %d vendored phrases parsed; the extractor is broken, not the list" % count
        )
    if missing:
        return fail(
            "the vendored blocker list must stay a SUBSET of the canonical one: %d missing"
            % missing
        )
    log.append("all %d vendored BLOCKER phrases exist in the canonical validator" % count)
    return 0, "\n".join(log)


# ---------------------------------------------------------------------------


def test_console_script_tree_is_optional(gate):
    with harness.temp_dir() as tmp:
        bp = make_isolated(tmp)
        files = bp_hit_files(bp, r"\.ci/scripts/")
        gate.assert_eq(
            files,
            sorted(ALLOWED_CONSOLE_HOOKS),
            "only the listed optional-hook scripts may name console's .ci/scripts/ in code",
        )
        gate.log_pass("no new script reaches into console's .ci/scripts/ tree")

        # ...and in each of them the reference is guarded by an existence test, so a repo without those console scripts takes an explicit branch rather than dying obscurely.
        #
        # BOTH IDIOMS COUNT, and that is a fix rather than a relaxation. The check used to demand the literal inline form, which only one of the three scripts happens to use; the other two assign the path to a variable first and test `[[ -x "$VAR" ]]`, which is the same guard. The old check therefore reported a guard as MISSING when it was present -- and nobody noticed, because the
        # exact-set assertion above fails first and log_fail exits, so the loop had only ever run against one script.
        for rel in ALLOWED_CONSOLE_HOOKS:
            body = (bp / rel).read_text(encoding="utf-8", errors="replace")
            guarded = '-x "$REPO_ROOT/.ci/scripts/' in body
            if not guarded:
                for name in {
                    m.group(1)
                    for m in (ASSIGNED_NAME_RE.match(line) for line in body.split("\n"))
                    if m
                }:
                    if '-x "$%s"' % name in body:
                        guarded = True
                        break
            if not guarded:
                gate.log_fail(
                    "%s references console's .ci/scripts/ without an [[ -x ]] existence "
                    "guard (checked both the inline and the assigned-variable idiom)" % rel
                )
    gate.log_pass(
        "every console hook is [[ -x ]]-guarded (absent tree => explicit branch, not break)"
    )


def test_no_nonportable_common_helpers(gate):
    with harness.temp_dir() as tmp:
        bp = make_isolated(tmp)
        hits = bp_code_hits(bp, r"get_repo_root|r2_count_objects|require_submodule")
        gate.assert_eq(hits, [], "console's non-portable common.sh helpers must not be used")
        gate.log_pass("no get_repo_root / r2_count_objects / require_submodule in code")

        # Both directions: the omission has to be DOCUMENTED, not accidental, or the next person re-adds them from common.sh without knowing why they are gone.
        gate.assert_contains(
            (bp / "lib" / "breakpoint-common.sh").read_text(encoding="utf-8"),
            "DELIBERATELY NOT COPIED",
            "breakpoint-common.sh must record which common.sh helpers were skipped",
        )
    gate.log_pass("breakpoint-common.sh documents the deliberately-omitted helpers")


def test_no_app_token_plumbing(gate):
    """No GitHub App / token plumbing on the DEFAULT path.

    THE CONTRACT CHANGED AND THIS ENCODES THE NEW ONE. The original rule was "no app token anywhere", correct while breakpoint only served its own origin. Then `services: onprem` landed, and the on-prem compose file lives in a PRIVATE repo the default GITHUB_TOKEN cannot clone. So the property is no longer "never", it is "not on the default path": `services` defaults to `none`, the
    default dispatch stays token-free, and the token step is legal
    ONLY in the workflow and ONLY behind `inputs.services != 'none'`.

    Scripts remain absolutely forbidden: a script is what gets vendored and called directly, so a token dependency there has no `if:` to hide behind.

    NOT COMMENT-STRIPPED, on purpose: even a commented-out app-token step is a copy-paste hazard in a repo with no such app registered. BOTH spellings are matched because this is a DETECTOR pattern rather than a reference -- the 2026-09-02 rename rewrote `APP_PRIVATE_KEY` to `GITHUB_APP_PRIVATE_KEY` and the assertion silently stopped matching, while a vendored copy in an un-renamed
    repo is exactly where the old spelling is a violation.
    """
    token_re = re.compile(r"app-token|vars\.APP_ID|(?:GITHUB_)?APP_PRIVATE_KEY")
    with harness.temp_dir() as tmp:
        bp = make_isolated(tmp)
        offenders = []
        for dirpath, _dirnames, filenames in os.walk(bp):
            for name in filenames:
                abs_path = pathlib.Path(dirpath) / name
                try:
                    text = abs_path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                if not token_re.search(text):
                    continue
                rel = os.path.relpath(abs_path, bp)
                if rel != os.path.join("workflow", "breakpoint.yml"):
                    offenders.append(rel)
        gate.assert_eq(
            sorted(offenders),
            [],
            "only the workflow may reference the GitHub App token; scripts must never",
        )

        workflow = bp / "workflow" / "breakpoint.yml"
        text = workflow.read_text(encoding="utf-8", errors="replace") if workflow.is_file() else ""
        marker = "uses: ./.github/actions/app-token"
        if marker in text:
            lines = text.split("\n")
            index = next(i for i, line in enumerate(lines) if marker in line)
            step = "\n".join(lines[index : index + 5])
            gate.assert_contains(
                step,
                "if: inputs.services != 'none'",
                "the app-token step must be guarded by inputs.services != 'none' so the "
                "default dispatch needs no App",
            )
            gate.log_pass(
                "app-token step exists but is confined to services != none "
                "(default path stays token-free)"
            )
        else:
            gate.log_pass("workflow references no GitHub App token at all")
    gate.log_pass("no script references the GitHub App token (workflow-only, checked above)")


def test_upstream_slug_is_configurable(gate):
    """The upstream slug lives in conf, not welded into scripts.

    FINDING, reported rather than fixed, because `.ci/breakpoint/` is another owner's: code lines DO name the canonical slug. Some are
    `${BREAKPOINT_UPSTREAM_REPO:-...}` fallbacks (harmless: conf wins, and every
    vendored copy ships a conf) and one is an `e.g.` in an error message. A blanket zero-reference assertion is therefore false today; this pins the two shapes that are safe so that a NEW, non-overridable hardcode is red.
    """
    with harness.temp_dir() as tmp:
        bp = make_isolated(tmp)
        gate.assert_contains(
            (bp / "breakpoint.conf").read_text(encoding="utf-8"),
            'BREAKPOINT_UPSTREAM_REPO="rediacc/console"',
            "breakpoint.conf must declare the canonical repo",
        )
        gate.log_pass("breakpoint.conf carries BREAKPOINT_UPSTREAM_REPO=rediacc/console")

        for hit in bp_code_hits(bp, r"rediacc/"):
            rel, lineno = hit.rsplit(":", 1)
            text = (
                (bp / rel)
                .read_text(encoding="utf-8", errors="replace")
                .split("\n")[int(lineno) - 1]
            )
            if "BREAKPOINT_UPSTREAM_REPO" not in text and "e.g." not in text:
                gate.log_fail(
                    "hardcoded upstream slug in %s:%s (not conf-overridable): %s"
                    % (rel, lineno, text)
                )
    gate.log_pass("every rediacc/ reference in a script is conf-overridable or diagnostic")


def test_workflow_runner_choices(gate):
    """The workflow cannot be dispatched onto a runner that cannot host a session.

    ubuntu-slim's hard 15-minute cap makes a debug session impossible: the box dies mid-investigation, which reads as a breakpoint bug rather than as a runner limit. Offering it as a choice is offering a trap.
    """
    with harness.temp_dir() as tmp:
        bp = make_isolated(tmp)
        workflow = bp / "workflow" / "breakpoint.yml"
        lines = workflow.read_text(encoding="utf-8", errors="replace").split("\n")
        options: list[str] = []
        inside = False
        for line in lines:
            if line.startswith("      runner:"):
                inside = True
            elif inside and line == "":
                inside = False
            if inside and line.startswith("          - "):
                options.append(line)
        block = "\n".join(options)
        if not block:
            gate.log_fail("could not parse the runner choice options out of %s" % workflow)
        gate.assert_not_contains(
            block, "ubuntu-slim", "ubuntu-slim must not be a runner choice (15-min cap)"
        )
        gate.log_pass("workflow does not offer ubuntu-slim as a session runner")

        gate.assert_contains(
            block, "'ubuntu-latest'", "ubuntu-latest must be among the runner choices"
        )
        index = next(i for i, line in enumerate(lines) if line.startswith("      runner:"))
        gate.assert_contains(
            "\n".join(lines[index : index + 6]),
            "default: 'ubuntu-latest'",
            "ubuntu-latest must be the default runner",
        )
    gate.log_pass("ubuntu-latest is offered and is the default runner")


def test_all_scripts_parse_standalone(gate):
    """Every script parses with no console around it.

    `env -i` is the point: a script that only parses because this shell exported something is not portable, and the downstream repo will not have it.
    """
    bash = harness.require_tool("bash", "install bash; the subject is a folder of shell scripts")
    with harness.temp_dir() as tmp:
        bp = make_isolated(tmp)
        checked = 0
        for rel in bp_files(bp):
            if not rel.endswith(".sh"):
                continue
            result = harness.run(
                [bash, "-n", str(bp / rel)],
                env={"PATH": os.environ.get("PATH", "")},
                env_replace=True,
                timeout=120,
            )
            if result.rc != 0:
                gate.log_fail(
                    "bash -n failed for %s in the isolated copy: %s" % (rel, result.err.strip())
                )
            checked += 1
        if checked < 10:
            gate.log_fail("only %d scripts were syntax-checked; the fixture looks empty" % checked)
    gate.log_pass("bash -n clean on all %d shell scripts in the isolated copy" % checked)


def test_drift_gate_runs_standalone(gate):
    """The folder SELF-VERIFIES with no console around it.

    This is the assertion that makes the rest credible: the integrity gate is the one script a downstream repo MUST be able to run, and it must not need console's `.ci/`, a git remote, or the network to do it.
    """
    bash = harness.require_tool("bash", "install bash; the drift gate is a shell script")
    with harness.temp_dir() as tmp:
        bp = make_isolated(tmp)
        drift = bp / "scripts" / "check-breakpoint-drift.sh"
        env = {"PATH": os.environ.get("PATH", ""), "HOME": str(tmp), "RUNNER_TEMP": str(tmp)}
        result = harness.run([bash, str(drift)], env=env, env_replace=True, timeout=600)
        gate.assert_exit(0, result, "check-breakpoint-drift.sh must pass inside an isolated copy")
        gate.assert_contains(
            result.combined, "Verified", "the drift gate must report what it verified"
        )
        gate.assert_not_contains(
            result.combined, "Verified 0 files", "a drift gate that verified nothing is vacuous"
        )
        gate.log_pass(
            "check-breakpoint-drift.sh self-verifies standalone (no .ci/scripts, no .git)"
        )

        # ...and it must FAIL when the manifest is gone. Deleting MANIFEST.sha256 is the cheapest possible way to make a diverged vendored copy "pass", so "nothing to compare against" has to be a hard error, not a quiet success. This lives here rather than in the anti-vacuity meta-gate because that harness's fixture does not copy `.ci/breakpoint/` at all: registered there, it could
        # only ever observe a "No such file" crash and score it as a pass.
        (bp / "MANIFEST.sha256").unlink(missing_ok=True)
        after = harness.run([bash, str(drift)], env=env, env_replace=True, timeout=600)
        if after.rc == 0:
            gate.log_fail(
                "check-breakpoint-drift.sh reported SUCCESS with no manifest -- deleting it "
                "would be a free pass"
            )
        gate.assert_contains(
            after.combined,
            "no manifest",
            "the drift gate must say WHY it refused, not just exit non-zero",
        )
    gate.log_pass("check-breakpoint-drift.sh rejects a copy whose manifest was deleted")


def test_vendored_blocker_list_is_a_subset(gate):
    with harness.temp_dir() as tmp:
        bp = make_isolated(tmp)
        if not CANONICAL_VALIDATOR.is_file():
            # Downstream: there is no canonical file to compare against, and that is the normal state there. Skipping is correct -- but it must be SAID, or a silently-skipped subset check looks identical to a passing one.
            gate.log_pass(
                "SKIPPED (no %s here): subset check is console-only"
                % paths.relative_to_root(CANONICAL_VALIDATOR)
            )
            return
        rc, log = check_subset(CANONICAL_VALIDATOR, bp)
        if rc != 0:
            gate.log_fail("the vendored blocker list is not a subset:\n%s" % log)
    gate.log_pass(log.splitlines()[-1])


def test_subset_check_catches_a_real_violation(gate):
    """PLANTED-DEFECT REGRESSION: a REAL subset violation must still fire, and must be named as one rather than excused as instability.

    Both reads of the mutated canonical see the SAME (genuinely missing) content, which is exactly what distinguishes a real violation from the transient case below. The deleted phrase is the exact one this gate's own history cites as having false-accused the vendored list on 2026-08-28, so the fixture is not a synthetic string the check happens to ignore.
    """
    with harness.temp_dir() as tmp:
        bp = make_isolated(tmp)
        if not CANONICAL_VALIDATOR.is_file():
            gate.log_pass(
                "SKIPPED (no %s here): planted-violation control is console-only"
                % paths.relative_to_root(CANONICAL_VALIDATOR)
            )
            return
        source = CANONICAL_VALIDATOR.read_text(encoding="utf-8")
        needle = '"skip" "skipping" "skipped" "ignore"'
        if needle not in source:
            gate.log_fail(
                "the plant did not land: %s no longer spells the phrase list as %r, so this "
                "control would run against an unchanged canonical copy"
                % (paths.relative_to_root(CANONICAL_VALIDATOR), needle)
            )
        mutant = tmp / "canonical-missing-skipped.sh"
        mutant.write_text(source.replace(needle, '"skip" "skipping" "ignore"', 1), encoding="utf-8")
        gate.assert_eq(mutant.read_text(encoding="utf-8") == source, False, "the plant landed")

        rc, log = check_subset(mutant, bp)
        gate.assert_eq(rc, 1, "a genuine subset violation must still FAIL, not pass silently")
        gate.assert_contains(
            log,
            "absent from two independent reads",
            "a STABLE violation must be named as real, not excused as a flaky read",
        )
    gate.log_pass("a real subset violation (stable across both reads) still fails, named correctly")


def test_subset_check_survives_a_flaky_second_read(gate):
    """PLANTED-DEFECT REGRESSION: a TRANSIENT truncation on the FIRST read must be reported as a re-verified phrase, never as a subset violation.

    This is the exact shape of the 2026-07-31 and 2026-08-28 incidents: the two reads DISAGREE, which is the one fact that proves the list is not at fault.

    THE TRUNCATION IS ON CALL #1, not on the re-verify call, and that ordering is the whole control: call #1 is the initial canon capture the loop checks vendored phrases against, so truncating THAT is what makes a real phrase look absent on first read and forces the re-verify path to fire. Exactly ONE real phrase is dropped -- the same one the 2026-08-28 incident dropped -- so the
    canonical count stays comfortably above its floor and the per-phrase re-verify loop is what has to catch this, not the coarse floor.
    """
    with harness.temp_dir() as tmp:
        bp = make_isolated(tmp)
        if not CANONICAL_VALIDATOR.is_file():
            gate.log_pass(
                "SKIPPED (no %s here): flaky-read control is console-only"
                % paths.relative_to_root(CANONICAL_VALIDATOR)
            )
            return

        seen = {"canon": 0}

        def flaky(path: pathlib.Path, name: str) -> list[str]:
            full = extract_array(path, name)
            if name == CANON_ARRAY:
                seen["canon"] += 1
                if seen["canon"] == 1:
                    return [p for p in full if p != "skipped"]
            return full

        # THE PLANT MUST BE ABLE TO BITE. If the canonical list stopped carrying 'skipped', or the vendored one did, the truncation would remove nothing observable and this control would pass against an un-plantable subject.
        canon_phrases = extract_array(CANONICAL_VALIDATOR, CANON_ARRAY)
        vendored_phrases = extract_array(bp / "lib" / "breakpoint-blocker.sh", VENDORED_ARRAY)
        if "skipped" not in canon_phrases or "skipped" not in vendored_phrases:
            gate.log_fail(
                "CONTROL COULD NOT PLANT: 'skipped' is not in both lists (canonical=%s, "
                "vendored=%s), so truncating it changes nothing and this case would pass "
                "vacuously" % ("skipped" in canon_phrases, "skipped" in vendored_phrases)
            )

        rc, log = check_subset(CANONICAL_VALIDATOR, bp, extract=flaky)
        gate.assert_contains(
            log,
            "IS canonical; the first read was short",
            "a phrase absent only from a truncated read must be recognised as re-verified, "
            "not missing",
        )
        gate.assert_eq(rc, 0, "a transient truncation must not fail the check")
    gate.log_pass(
        "a flaky second canonical read is caught and excused, never blamed on the vendored list"
    )


def test_the_isolated_copy_is_a_copy_and_the_source_is_untouched(gate):
    """ADDED BY THE PORT, and it is the claim every other case rests on.

    Two cases MUTATE their fixture: one deletes `MANIFEST.sha256`, one rewrites the canonical validator. Both are safe only because `make_isolated` copies first. If it ever returned the real path -- a refactor, a symlink, a `copytree(dirs_exist_ok)` pointed at the source -- the delete would land on `.ci/breakpoint/` in a tree holding other sessions' work, and the very next drift
    check would report a defect nobody introduced.

    So: the copy is not the source, it holds the same file set, and the source's digest is unchanged after a full copy-and-mutate cycle.
    """

    def tree_digest(root: pathlib.Path) -> str:
        h = hashlib.sha256()
        for rel in sorted(
            os.path.relpath(os.path.join(dirpath, name), root)
            for dirpath, _d, filenames in os.walk(root)
            for name in filenames
        ):
            h.update(rel.encode("utf-8"))
            h.update(b"\0")
            h.update((root / rel).read_bytes())
        return h.hexdigest()

    before = tree_digest(BP_SRC)
    with harness.temp_dir() as tmp:
        bp = make_isolated(tmp)
        gate.assert_eq(
            bp.resolve() == BP_SRC.resolve(), False, "the fixture must not BE the source"
        )
        gate.assert_eq(
            bp_files(bp), bp_files(BP_SRC), "the copy must hold the same shell/workflow set"
        )
        # Mutate the copy the way `test_drift_gate_runs_standalone` does.
        (bp / "MANIFEST.sha256").unlink(missing_ok=True)
    after = tree_digest(BP_SRC)
    gate.assert_eq(after, before, "the real .ci/breakpoint/ is byte-identical after the cycle")
    gate.log_pass(
        "the fixture is a real copy and %s is untouched (%s)"
        % (paths.relative_to_root(BP_SRC), before[:16])
    )

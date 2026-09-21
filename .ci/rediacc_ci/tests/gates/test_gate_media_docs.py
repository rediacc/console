"""Port of `.ci/scripts/test/gates/test-media-docs.sh`, retired in W7 P5.

Tests that the media folder's own DOCUMENTATION stays true, and that its coverage probe stays honest.

WHY DOCUMENTATION NEEDS A GATE HERE MORE THAN ANYWHERE ELSE IN THIS TREE. These files carry an unusual amount of prose, on purpose: several of the paragraphs are the only surviving record of an incident. Prose that dense decays in one specific way a reader cannot catch -- a path that was true when it was written and is not true now. Phase 3 alone moved four files, and every comment
naming `.ci/docker/tts` became a lie the moment it did.

Three subjects, in the twin's order: the dangling `.ci/` path scan, the coverage probe (that it measures, that its seam does not perturb, and that it names modules no test drives), and `.ci/docs/r2-media-setup.md`'s function homes and commit citations.

Nothing here needs docker, node, npm, nvcc, aws, ssh, a GPU or a network.

WHERE THIS REIMPLEMENTS grep, sed, sort, comm AND awk, AND WHY THE ANSWERS AGREE.

  `grep -oE '\\.ci/[A-Za-z0-9._*/-]+' | sed 's/[.,;:)]*$//' | sort -u` is a token
  scan, a trailing-punctuation strip and a unique sort. `-o` prints EVERY match on a
  line, which is `re.findall` over the whole text; the sed class is stripped with
  `rstrip(".,;:)")`, which removes the same set from the same end; `sort -u` over
  tokens that all begin `.ci/` and continue in one ASCII class is `sorted(set(...))`
  under any collation that cannot reorder them. The order only affects the ORDER of
  findings, never the SET, and the assertions are about emptiness.

  `grep -hoE '^[a-z_][a-z0-9_]*\\(\\)' .ci/media/*.sh | sed 's/()//' | sort -u`
  becomes the same anchored per-line match with the `()` in a non-captured suffix.
  `comm -12` over two sorted unique streams is set intersection, and both sides here
  are already sets of ASCII identifiers, so `&` gives the same members.

  `grep -oE '`[0-9a-f]{7,12}`'` is a BACKTICK-DELIMITED bounded hex run. The bound
  is what keeps the 32-hex Cloudflare zone id out of the set, and it does so for a
  reason worth stating because it looks fragile: after the opening backtick the
  regex needs 7 to 12 hex characters and then a CLOSING BACKTICK, and inside a
  32-character run the 8th through 13th characters are hex, not a backtick, so no
  match starts there or anywhere later. Python's `re.findall` on the identical
  pattern makes the identical choice, and the fixture case below pins it.

  `awk '$1 == "r2.sh" {gsub(/%/, "", $4); print $4}'` is a whitespace-split field
  lookup. `str.split()` splits on runs of whitespace exactly as awk's default FS
  does, so field 4 is field 4.

  `git merge-base --is-ancestor <tok> HEAD` is driven as the real command, not
  reimplemented. An ancestry predicate written in Python would be a second answer to
  a question git already answers.

WHAT IS NOT PORTED, AND WHY IT IS NOT A GAP. The twin's `|| true` on its grep is a bash-specific defence: without it, a file naming no `.ci/` path makes grep exit 1, `pipefail` carries that out, and `set -e` kills the caller with an empty stderr. Python has no such hazard, but the CASE that proves the hazard is closed is kept verbatim -- a file with no `.ci` path must leave the
scan alive and return an empty result -- because what the case really asserts is "the scan survives a file with nothing in it", and that claim is language-independent.

NO `xdist_group`, WITH ONE THING WORTH SAYING OUT LOUD. Two cases execute `.ci/scripts/test/gates/test-media-r2.sh` and `.ci/media/coverage.sh`, which are real programs in the checkout, but both are READ-ONLY with respect to the tree: the r2 twin builds its fixtures under its own `mktemp -d`, and the coverage probe writes only to the trace file it is handed. Nothing here writes
into the repository, so there is no state for two workers to share.
"""

import pathlib
import re

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

ROOT = paths.repo_root()
COVERAGE = ROOT / ".ci" / "media" / "coverage.sh"
R2_DOC = ROOT / ".ci" / "docs" / "r2-media-setup.md"
MEDIA_R2_TWIN = ROOT / ".ci" / "scripts" / "test" / "gates" / "test-media-r2.sh"

CI_PATH_RE = re.compile(r"\.ci/[A-Za-z0-9._*/-]+")
DEFINED_FN_RE = re.compile(r"^([a-z_][a-z0-9_]*)\(\)", re.MULTILINE)
BACKTICK_WORD_RE = re.compile(r"`([A-Za-z_][A-Za-z0-9_]*)`")
COMMIT_TOKEN_RE = re.compile(r"`([0-9a-f]{7,12})`")


def media_owned_files() -> list[pathlib.Path]:
    """EVERY FILE THIS FOLDER OWNS, including the two shims that live outside it.

    The shims exist only to describe a move, so their prose is the most likely in the change to go stale; leaving them out would exempt the highest-risk prose.
    """
    fixed = [
        ROOT / "media.sh",
        ROOT / ".ci" / "docker" / "run-in-tts.sh",
        ROOT / ".ci" / "scripts" / "deploy" / "upload-media-to-r2.sh",
        ROOT / ".ci" / "docs" / "r2-media-setup.md",
    ]
    return fixed + sorted((ROOT / ".ci" / "media").rglob("*.sh"))


def dangling_ci_paths(*files: pathlib.Path) -> list[str]:
    """Every `.ci/...` path a file names that does not exist, as `<file>: <path>`.

    GLOBS ARE NOT PATHS. `test-media-*.sh` appears in several headers as the NAME OF A SET; a token containing `*` is dropped rather than resolved, because the alternative is either a false finding on every one of them or an exception list that grows with the prose.
    """
    findings = []
    for path in files:
        tokens = sorted(
            {
                token.rstrip(".,;:)")
                for token in CI_PATH_RE.findall(path.read_text(encoding="utf-8"))
            }
        )
        for token in tokens:
            if "*" in token:
                continue
            if not (ROOT / token).exists():
                # `${f#"$ROOT/"}` in bash, which strips the prefix when it is there
                # and leaves the path alone when it is not. `is_relative_to` asks the question directly rather than raising and swallowing, which matters because the control cases below scan FIXTURE files under tmp_path: those are genuinely outside the repo and must print their full path, not be mistaken for an error.
                relative = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path
                findings.append("%s: %s" % (relative, token))
    return findings


def doc_media_functions(doc: pathlib.Path) -> list[str]:
    """Every shell function DEFINED in `.ci/media` that `doc` names inside backticks.

    Derived from BOTH sides, so a renamed function drops out of the set instead of becoming a stale exception nobody removes.
    """
    defined: set[str] = set()
    for module in sorted((ROOT / ".ci" / "media").glob("*.sh")):
        defined.update(DEFINED_FN_RE.findall(module.read_text(encoding="utf-8")))
    tokens = set(BACKTICK_WORD_RE.findall(doc.read_text(encoding="utf-8")))
    return sorted(defined & tokens)


def misplaced_function_homes(doc: pathlib.Path) -> list[str]:
    """Every function above whose defining file the doc does NOT also name."""
    text = doc.read_text(encoding="utf-8")
    findings = []
    for function in doc_media_functions(doc):
        anchor = re.compile(r"^%s\(\)" % re.escape(function), re.MULTILINE)
        for module in sorted((ROOT / ".ci" / "media").glob("*.sh")):
            if not anchor.search(module.read_text(encoding="utf-8")):
                continue
            if ".ci/media/%s" % module.name not in text:
                findings.append(
                    "%s: defined in .ci/media/%s, which this document never names"
                    % (function, module.name)
                )
    return findings


def doc_commit_tokens(doc: pathlib.Path) -> list[str]:
    """Every BACKTICKED 7-to-12 hex token, sorted and unique."""
    return sorted(set(COMMIT_TOKEN_RE.findall(doc.read_text(encoding="utf-8"))))


def non_ancestor_commits(repo: pathlib.Path, doc: pathlib.Path) -> list[str]:
    """Every cited token that is not an ancestor of HEAD in `repo`.

    Unresolvable and merely-unreachable collapse into one finding on purpose: from a reader's seat, "git cannot show me this" and "git shows me something on no branch" are the same broken citation.
    """
    git = harness.require_tool("git", "install git")
    dead = []
    for token in doc_commit_tokens(doc):
        probe = harness.run([git, "-C", str(repo), "merge-base", "--is-ancestor", token, "HEAD"])
        if probe.rc != 0:
            dead.append(token)
    return dead


def test_every_ci_path_the_media_files_name_exists(gate):
    files = media_owned_files()
    # ANTI-VACUITY FIRST. A scan over an empty file list finds nothing wrong, and would keep on finding nothing wrong after this folder was renamed out from under it.
    if len(files) < 12:
        gate.log_fail(
            "the media file list collapsed to %d entries; the scan below would pass "
            "over almost nothing" % len(files)
        )
    findings = dangling_ci_paths(*files)
    if findings:
        gate.log_fail("media files name .ci paths that do not exist:\n%s" % "\n".join(findings))
    gate.log_pass(
        "every .ci path named across the %d media files resolves to something that exists"
        % len(files)
    )


def test_the_dangling_path_scan_can_fail(gate, tmp_path):
    # CONTROL, in both directions. The scan is a pattern match with a character class and a filter, which is the shape that goes quiet without announcing it.
    stale = tmp_path / "stale.sh"
    stale.write_text("# see .ci/media/no-such-file.sh for details\n", encoding="utf-8")
    if not dangling_ci_paths(stale):
        gate.log_fail("the scan did not notice a comment naming a .ci path that does not exist")

    fresh = tmp_path / "fresh.sh"
    fresh.write_text("# see .ci/media/verify.sh for details\n", encoding="utf-8")
    if dangling_ci_paths(fresh):
        gate.log_fail(
            "the scan reported a finding for a .ci path that does exist, so it fires on everything"
        )

    globbed = tmp_path / "globbed.sh"
    globbed.write_text(
        "# every .ci/scripts/test/gates/test-media-*.sh sources it\n", encoding="utf-8"
    )
    if dangling_ci_paths(globbed):
        gate.log_fail(
            "the scan treated a glob as a path, which would make it impossible to name a "
            "set of files in a comment"
        )

    # A FILE THAT NAMES NO .ci PATH AT ALL. This is the case that killed the bash gate silently before its `|| true`: grep exits 1, pipefail propagates it, set -e ends the script mid-assertion, and the operator sees exit 1 with an empty stderr. Python cannot fail that way, but the claim -- the scan survives a file with nothing in it and returns -- is language-independent, so the
    # case stays.
    nopaths = tmp_path / "nopaths.sh"
    nopaths.write_text("zzz_no_paths_here() { :; }\n", encoding="utf-8")
    gate.assert_eq(
        dangling_ci_paths(nopaths),
        [],
        "a file naming no .ci path must leave the scan alive, not end the gate with an "
        "empty message",
    )
    gate.log_pass(
        "the dangling-path scan fires on a stale path, stays silent on a live one, "
        "ignores a glob, and survives a file with no .ci path at all"
    )


def test_the_coverage_probe_still_measures_something(gate):
    # ONE fast test rather than the whole set: this is a gate, and a full probe run drives every media gate test. What is under test is the instrument, not the number.
    result = harness.run([str(COVERAGE), "--only", "r2"], timeout=600)
    if result.rc != 0:
        gate.log_fail("the coverage probe failed to run: %s" % result.combined)
    gate.assert_contains(
        result.combined, "r2.sh", "the probe must report the module the measured test exercises"
    )
    gate.assert_contains(result.combined, "TOTAL", "the probe must print a total")

    # NON-VACUITY, which for a coverage tool is the whole risk. A probe whose trace parsing has silently stopped matching reports every module at zero, and zero is also what a genuinely untested module looks like.
    percent = None
    for line in result.combined.splitlines():
        fields = line.split()
        if len(fields) >= 4 and fields[0] == "r2.sh":
            percent = fields[3].replace("%", "")
            break
    if percent is None or not percent.isdigit():
        gate.log_fail("the probe printed no percentage for r2.sh; its output format has changed")
    if int(percent) < 50:
        gate.log_fail(
            "the probe measured r2.sh at %s%% while running r2's own gate test, which "
            "drives both of its functions -- the trace is not being parsed" % percent
        )
    gate.log_pass(
        "the coverage probe runs, reports r2.sh at %s%% from r2's own gate test, and "
        "prints a total" % percent
    )


def test_the_coverage_seam_does_not_perturb_the_run(gate, tmp_path):
    # THE CLAIM COVERAGE.SH MAKES ABOUT ITSELF, asserted rather than believed. The
    # first design of this probe forced SHELLOPTS=xtrace into every child shell, and
    # eight of the ten media gate tests then failed, because media_run_module captures merged stdout and stderr and the behaviour cases assert on that text.
    trace = tmp_path / "trace"
    off = harness.run(["bash", str(MEDIA_R2_TWIN)], timeout=600)
    on = harness.run(
        ["bash", str(MEDIA_R2_TWIN)],
        env={"MEDIA_COVERAGE_FILE": str(trace)},
        timeout=600,
    )
    gate.assert_eq(on.rc, off.rc, "tracing must not change whether a gate test passes")
    if on.out != off.out:
        gate.log_fail(
            "tracing changed what the gate test printed:\n--- off ---\n%s\n--- on ---\n%s"
            % (off.out, on.out)
        )
    # And the trace must actually have been written, or the comparison above is between two untraced runs and proves nothing at all.
    if not (trace.is_file() and trace.stat().st_size > 0):
        gate.log_fail(
            "MEDIA_COVERAGE_FILE produced no trace, so the two runs compared above were "
            "identical for the wrong reason"
        )
    gate.log_pass(
        "a gate test's exit status and its entire stdout are identical with the coverage "
        "seam on and off, and the seam did write a trace"
    )


def test_the_r2_doc_names_the_file_that_defines_each_media_function_it_names(gate):
    functions = doc_media_functions(R2_DOC)
    # ANTI-VACUITY. If the doc stops naming any media function, or the extraction of
    # function names stops matching, the loop below runs zero times and reports a
    # clean invariant it never tested.
    if len(functions) < 3:
        gate.log_fail(
            "only %d .ci/media function(s) are named in the R2 doc; the homing check "
            "below would assert almost nothing" % len(functions)
        )
    findings = misplaced_function_homes(R2_DOC)
    if findings:
        gate.log_fail(
            "the R2 media doc names functions without naming the file that defines "
            "them:\n%s" % "\n".join(findings)
        )
    gate.log_pass(
        "all %d .ci/media functions the R2 doc names are accompanied by the module that "
        "defines them" % len(functions)
    )


def test_the_function_home_scan_can_fail(gate, tmp_path):
    # CONTROL, both directions, against fixture docs rather than the real one. run.sh is the exact wrong home this check was written for, so it is the one planted.
    wrong = tmp_path / "wrong.md"
    wrong.write_text("`www_tutorial_audio_restore` lives in `run.sh`\n", encoding="utf-8")
    if not misplaced_function_homes(wrong):
        gate.log_fail(
            "the scan accepted a doc that homes www_tutorial_audio_restore in run.sh, "
            "which is the defect it exists for"
        )

    right = tmp_path / "right.md"
    right.write_text("`www_tutorial_audio_restore` lives in `.ci/media/r2.sh`\n", encoding="utf-8")
    findings = misplaced_function_homes(right)
    if findings:
        gate.log_fail(
            "the scan reported a finding for a doc that names the correct module, so it "
            "fires on everything:\n%s" % "\n".join(findings)
        )
    gate.log_pass(
        "the function-home scan catches a function homed in the wrong file and stays "
        "silent on the right one"
    )


def test_every_commit_the_r2_doc_cites_is_in_this_history(gate):
    git = harness.require_tool("git", "install git")
    tokens = doc_commit_tokens(R2_DOC)
    if len(tokens) < 1:
        gate.log_fail(
            "no backticked commit citation found in the R2 doc; either it stopped citing "
            "one or the token pattern stopped matching, and this check would pass forever "
            "either way"
        )

    # A SHALLOW CLONE CANNOT ANSWER THIS, and saying so beats both a silent skip and a red that is about the checkout rather than the doc. CI's quality-security job checks out with fetch-depth: 0 paired with filter: blob:none, so the assertion does run there. The control beside this one runs either way, so the checker is never left unproven.
    shallow = harness.run([git, "-C", str(ROOT), "rev-parse", "--is-shallow-repository"])
    if shallow.out.strip() == "true":
        gate.log_info(
            "this clone is shallow, so the %d commit citation(s) in the R2 doc cannot be "
            "checked for ancestry here" % len(tokens)
        )
        gate.log_pass(
            "the %d commit citation(s) were enumerated; ancestry is unanswerable in a "
            "shallow clone and is reported as such rather than assumed" % len(tokens)
        )
        return

    dead = non_ancestor_commits(ROOT, R2_DOC)
    if dead:
        gate.log_fail(
            "the R2 media doc cites commit(s) that are not in this repository's "
            "history:\n%s\nA history rewrite invalidates every SHA. Re-derive the "
            "citation, or write it without backticks if the point is that it is dead."
            % "\n".join(dead)
        )
    gate.log_pass("all %d commit citation(s) in the R2 doc are ancestors of HEAD" % len(tokens))


def test_the_commit_citation_scan_can_fail(gate, tmp_path):
    # CONTROL, in a throwaway repository, because the real doc has exactly one correct citation and a scan with nothing to find proves nothing. Two divergent branches give a commit that RESOLVES and is not an ancestor, which is the exact shape a rewritten SHA has and the shape a scan built on `git cat-file -e` alone would wave through.
    git = harness.require_tool("git", "install git")
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)

    def run_git(*argv):
        result = harness.run([git, "-C", str(repo), *argv])
        if result.rc != 0:
            gate.log_fail("git %s failed in the fixture: %s" % (" ".join(argv), result.err))
        return result

    # `--initial-branch=main` on purpose: a fixture whose HEAD points at a branch the
    # runner's init.defaultBranch does not create is the second shape of the empty-fixture trap test_gate_fetch_depth_safety.py exists for.
    run_git("init", "-q", "--initial-branch=main")
    run_git("config", "user.email", "probe@example.com")
    run_git("config", "user.name", "probe")
    (repo / "f").write_text("a\n", encoding="utf-8")
    run_git("add", "f")
    run_git("commit", "-qm", "base")
    live = run_git("rev-parse", "--short=9", "HEAD").out.strip()
    run_git("checkout", "-q", "-b", "sibling")
    (repo / "f").write_text("b\n", encoding="utf-8")
    run_git("commit", "-qam", "sibling")
    dead = run_git("rev-parse", "--short=9", "HEAD").out.strip()
    run_git("checkout", "-q", "-")
    # HEAD is back on the base commit, so `dead` resolves and is not an ancestor of it.

    dead_doc = tmp_path / "dead.md"
    dead_doc.write_text("see `%s`\n" % dead, encoding="utf-8")
    gate.assert_eq(
        non_ancestor_commits(repo, dead_doc),
        [dead],
        "a citation that resolves but sits on no ancestor path must be reported",
    )

    live_doc = tmp_path / "live.md"
    live_doc.write_text("see `%s`\n" % live, encoding="utf-8")
    if non_ancestor_commits(repo, live_doc):
        gate.log_fail(
            "the scan reported a citation that IS an ancestor of HEAD, so it fires on everything"
        )

    junk_doc = tmp_path / "junk.md"
    junk_doc.write_text("see `deadbeefcafe`\n", encoding="utf-8")
    if not non_ancestor_commits(repo, junk_doc):
        gate.log_fail("the scan accepted a citation git cannot resolve at all")

    # AND THE LENGTH CEILING, which is why the zone id in the real doc is not a finding. A 32-hex token is not a commit citation in this file's vocabulary.
    zone_doc = tmp_path / "zone.md"
    zone_doc.write_text("zone `9e802649c143c9cefd811d8fd671d31c`\n", encoding="utf-8")
    gate.assert_eq(
        doc_commit_tokens(zone_doc),
        [],
        "a 32-hex identifier was taken for a commit citation, which would make every zone "
        "and account id in this document a permanent finding",
    )
    gate.log_pass(
        "the citation scan catches an unreachable SHA and an unresolvable one, accepts an "
        "ancestor, and ignores a 32-hex identifier"
    )


def test_no_media_module_is_without_a_test(gate):
    result = harness.run([str(COVERAGE), "--modules-without-tests"], timeout=600)
    if result.rc != 0:
        gate.log_fail("a .ci/media module has no gate test naming it:\n%s" % result.combined)
    gate.assert_contains(
        result.combined,
        "named in the code of at least one media gate test",
        "the probe must say what it checked",
    )
    gate.log_pass("every .ci/media module is named in the code of at least one media gate test")


def test_the_untested_module_report_can_fail(gate, tmp_path):
    # CONTROL, in all three directions the report has. Without it the assertion above is a command that printed a reassuring sentence, and a coverage tool whose corpus has collapsed prints exactly that sentence.
    mods = tmp_path / "mods"
    gates = tmp_path / "gates"
    empty = tmp_path / "empty"
    for directory in (mods, gates, empty):
        directory.mkdir(parents=True, exist_ok=True)
    (mods / "covered.sh").write_text("covered_fn() { :; }\n", encoding="utf-8")
    (mods / "lonely.sh").write_text("lonely_fn() { :; }\n", encoding="utf-8")
    fixture = gates / "test-media-fixture.sh"
    # lonely.sh is named ONLY in a comment, which must not count as a test.
    fixture.write_text(
        "#!/bin/bash\n# this header mentions lonely.sh in prose\n"
        'MODULE="$ROOT/.ci/media/covered.sh"\n',
        encoding="utf-8",
    )

    def probe(module_dir, gates_dir):
        return harness.run(
            [str(COVERAGE), "--modules-without-tests"],
            env={
                "MEDIA_COVERAGE_MODULE_DIR": str(module_dir),
                "MEDIA_COVERAGE_GATES_DIR": str(gates_dir),
            },
            timeout=600,
        )

    result = probe(mods, gates)
    gate.assert_exit_code(1, result.rc, "a module no test names must make the probe exit non-zero")
    gate.assert_contains(
        result.combined,
        "lonely.sh",
        "the probe must NAME the untested module, not merely count it",
    )
    gate.assert_not_contains(
        result.combined, "covered.sh", "the probe must not report a module a test does name"
    )

    # THE OTHER DIRECTION.
    fixture.write_text(
        '#!/bin/bash\nmedia_run_module "$1" "lonely.sh" "$2"\n'
        'MODULE="$ROOT/.ci/media/covered.sh"\n',
        encoding="utf-8",
    )
    result = probe(mods, gates)
    gate.assert_exit_code(
        0,
        result.rc,
        "with every module named in code the probe must pass: %s" % result.combined,
    )

    # AND THE VACUOUS CORPUS, which is the failure this whole check guards against elsewhere: an empty module list reports nothing wrong and looks identical to a folder in which everything is tested.
    result = probe(empty, gates)
    gate.assert_exit_code(
        1, result.rc, "an empty module folder must be refused, not reported as clean"
    )
    gate.assert_contains(
        result.combined, "no subject modules", "the refusal must say the corpus was empty"
    )
    gate.log_pass(
        "the untested-module report names a planted module, ignores a prose-only mention, "
        "passes when every module is named in code, and refuses an empty corpus"
    )

"""Port of `.ci/scripts/test/gates/test-media-args.sh`, retired in W7 P5.

Tests for the ARGUMENT PARSING in `.ci/media/tutorials.sh`, and for `.ci/media/teaser.sh`.

WHY THESE TWO SHARE A FILE. What is left in tutorials.sh after the venv, the GPU probe, the render pool, the bridge and the R2 cache moved out is control flow and option parsing. Option parsing is the half a test can drive end to end -- the other half ends in a real render -- and it is also the half that fails silently: a `--lang` routed into the wrong bucket does not error, it
just narrates the wrong set. teaser.sh is the same kind of surface for the private/growth side.

Every case replaces the downstream work with recorders AFTER sourcing the module, so nothing here runs npm, node, python or a render.

WHERE THIS REIMPLEMENTS grep, AND WHY THE ANSWERS AGREE.

  `grep "^${key}=" tutorials.sh` becomes a scan for lines STARTING with that
  literal. grep is line-oriented and `^` anchors at line start, so `startswith` over
  `splitlines()` is the same predicate. The twin keeps the WHOLE matching line and
  later compares it to what `media-entry.sh` puts in scope, spelled `KEY=value`;
  this keeps the same line for the same comparison, so the equality being asserted
  is byte for byte the twin's.

  `printf '%s\\n' "$LAST_OUT" | grep '^producer:'` selects one line out of the merged
  output. A `grep` matching several lines would join them with newlines and the
  twin's `assert_contains` would still pass; the Python form selects the same lines
  and joins them the same way, so a second `producer:` line cannot change the
  verdict in either direction.

  `grep -qF "$sentence"` is a FIXED-STRING search with no anchor, which is `in`.

THE ONE HELPER THAT COULD NOT BE A DIRECT TRANSLATION. `_absence_verdict` runs the absence assertion in a SUBSHELL so that its `log_fail`'s `exit` takes down the subshell rather than the gate. Python's `log_fail` raises, and catching an exception in a control makes a bug in the control indistinguishable from the finding it is looking for. So `media_verify_ext.absent_from_origins`
returns the reason as an ordinary value and the assertion is a thin wrapper over it; the control reads the value. Same two directions, no exception in the middle.

WHY `STUBS_STEPS` IS NOT FOLDED INTO `STUBS_BASE`, kept from the twin because the mistake it records was made here on a first run: stubbing a verb while testing that same verb is how an argument-validation case comes back green having exercised a two-line echo. `www_tutorials_video --jobs abc` reported exit 0 because the stub, not the parser, is what answered.

NO `xdist_group`. Every fixture and sandbox is under pytest's own `tmp_path`; the only process-wide state is `os.environ["PATH"]`, restored per call by `harness.fake_bin`.
"""

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness, media_verify, media_verify_ext

ROOT = paths.repo_root()
TUTORIALS = ROOT / ".ci" / "media" / "tutorials.sh"
TEASER = ROOT / ".ci" / "media" / "teaser.sh"

TUTORIAL_MOVED = (
    "_grand_env_is_wildcard",
    "_tutorial_script_hash",
    "www_tutorials_record",
    "www_tutorials_extract",
    "www_tutorials_scaffold_locales",
    "www_tutorials_generate",
    "www_tutorials_video",
    "_tutorial_media_producer",
    "www_tutorials_media",
    "_tutorial_watch_producer",
    "www_tutorials_watch",
    "www_tutorials_validate",
    "www_tutorials_all",
    "www_all",
)

TEASER_MOVED = ("die", "pass_owns", "venv_for")

STUBS_BASE = """
check_node_version() { :; }
ensure_deps() { :; }
ensure_packages_built() { :; }
ensure_audio_system_deps() { :; }
ensure_generative_repo() { :; }
ensure_python_installed() { :; }
ensure_generative_venv() { echo "venv: $*"; }
www_tutorial_audio_restore() { echo "restore"; }
www_tutorial_audio_upload() { echo "upload"; }
_tutorial_render_pairs() { printf "installation\\ten\\n"; }
_tutorial_auto_jobs() { echo 3; }
_tutorial_video_pool() { echo "pool: $*"; while read -r _; do :; done; }
_tutorial_media_producer() { echo "producer: $*" >&2; }
"""

STUBS_STEPS = """
www_tutorials_record() { echo "record: $*"; }
www_tutorials_extract() { echo "extract"; }
www_tutorials_scaffold_locales() { echo "scaffold"; }
www_tutorials_generate() { echo "generate: $*"; }
www_tutorials_video() { echo "video: $*"; }
www_tutorials_validate() { echo "validate"; }
"""


def run_tutorials(root, code):
    return media_verify.media_run_module(root, "tutorials.sh", STUBS_BASE + "\n" + code)


def run_tutorials_all(root, code):
    return media_verify.media_run_module(
        root, "tutorials.sh", STUBS_BASE + "\n" + STUBS_STEPS + "\n" + code
    )


def run_teaser(root, code):
    return media_verify.media_run_module(root, "teaser.sh", code)


def lines_matching(text: str, prefix: str) -> str:
    """`grep '^<prefix>'` over merged output, joined the way a command substitution would join it."""
    return "\n".join(line for line in text.splitlines() if line.startswith(prefix))


def test_every_moved_tutorial_function_is_solely_owned_by_this_module(gate):
    # WHAT THIS REPLACED. Until the cutover run.sh carried its own copy of all fourteen and this compared the bodies byte for byte. run.sh has no copies now, so the claim worth asserting is ownership.
    media_verify.media_assert_module_owns(gate, "tutorials.sh", *TUTORIAL_MOVED)


def test_the_recorded_terminal_geometry_lives_here_and_only_here(gate):
    # TUTORIAL_COLS/TUTORIAL_ROWS are the single source of truth for the cast header and every downstream renderer, and being plain assignments the ownership assertion cannot see them.
    source = TUTORIALS.read_text(encoding="utf-8").splitlines()
    for key in ("TUTORIAL_COLS", "TUTORIAL_ROWS"):
        in_module = [line for line in source if line.startswith("%s=" % key)]
        if not in_module:
            gate.log_fail(
                "%s is not defined in tutorials.sh -- this assertion has nothing to check" % key
            )
        media_verify_ext.assert_absent_from_origins(
            gate,
            r"^%s=" % key,
            ROOT,
            "an origin still assigns %s -- the cutover left a second source of truth "
            "for the cast geometry" % key,
        )
        in_scope = harness.run(
            [
                media_verify._BASH,
                "-c",
                "source '%s/.ci/media/media-entry.sh' >/dev/null 2>&1; "
                "printf '%%s=%%s' '%s' \"${%s:-}\"" % (ROOT, key, key),
            ]
        )
        gate.assert_eq(
            in_scope.out,
            "\n".join(in_module),
            "media-entry.sh must put tutorials.sh's %s in scope with its own value" % key,
        )
    gate.log_pass(
        "TUTORIAL_COLS and TUTORIAL_ROWS are defined only in tutorials.sh and reach the "
        "entry point unchanged"
    )


def test_the_ownership_assertion_can_fail(gate, tmp_path):
    media_verify.media_assert_ownership_control(
        gate, tmp_path, "tutorials.sh", "www_tutorials_record"
    )


def test_the_absence_assertion_can_fail(gate, tmp_path):
    # THE OTHER HALF OF THE CUTOVER PROOF HAS ITS OWN VACUITY, and it is worse than the ownership assertion's because it is invisible: `grep -q pat a b` with b missing exits 2, which reads as "not found". Every arm plants the pattern in ONE origin and requires a finding, then a fourth removes an origin and requires a finding for that too.
    repo = media_verify_ext.media_chain_sandbox(tmp_path)

    if media_verify_ext.absent_from_origins(r"^TUTORIAL_COLS=", repo) is not None:
        gate.log_fail(
            "the absence assertion already reports a finding on a clean sandbox, so the "
            "arms below would prove nothing"
        )

    for relative in ("run.sh", "media.sh", ".ci/legacy/run-legacy.sh"):
        target = repo / relative
        target.write_text(
            target.read_text(encoding="utf-8") + "\nTUTORIAL_COLS=999\n", encoding="utf-8"
        )
        gate.assertions += 1
        if media_verify_ext.absent_from_origins(r"^TUTORIAL_COLS=", repo) is None:
            gate.log_fail(
                "the absence assertion passed with %s assigning TUTORIAL_COLS -- that "
                "origin is not being read" % relative
            )
        target.write_bytes((ROOT / relative).read_bytes())

    parked = repo / "absent-origin"
    (repo / "media.sh").rename(parked)
    gate.assertions += 1
    if media_verify_ext.absent_from_origins(r"^TUTORIAL_COLS=", repo) is None:
        gate.log_fail(
            "the absence assertion passed with an origin missing -- a file nobody read "
            "cannot testify that the value is not in it"
        )
    parked.rename(repo / "media.sh")

    gate.log_pass(
        "the absence assertion fires on a value planted in each of the 3 origins and on "
        "an origin that is missing"
    )


def test_run_sh_still_reaches_this_module(gate, tmp_path):
    # THE DELEGATION ITSELF, for the surface that carries almost all of it. Two verbs are probed rather than one because they take different routes through the case tree: `www tutorials <verb>` is two levels deep, `www all` is one.
    repo = media_verify_ext.media_chain_sandbox(tmp_path)

    media_verify_ext.probe(repo, "tutorials.sh", "www_tutorials_record")
    with harness.fake_bin("+uname +dirname"):
        result = media_verify_ext.run(
            repo, "run.sh", "www", "tutorials", "record", "--force", "installation"
        )
    if result.rc != 0:
        gate.log_fail(
            "./run.sh www tutorials record failed in the sandbox: %s" % result.combined.strip()
        )
    gate.assert_eq(
        result.combined.strip(),
        "MEDIA_CHAIN_REACHED:www_tutorials_record:--force installation",
        "run.sh must reach tutorials.sh's www_tutorials_record with its arguments intact",
    )

    media_verify_ext.probe(repo, "tutorials.sh", "www_all")
    with harness.fake_bin("+uname +dirname"):
        result = media_verify_ext.run(repo, "run.sh", "www", "all", "installation")
    if result.rc != 0:
        gate.log_fail("./run.sh www all failed in the sandbox: %s" % result.combined.strip())
    gate.assert_eq(
        result.combined.strip(),
        "MEDIA_CHAIN_REACHED:www_all:installation",
        "the shallower www arm reaches tutorials.sh's www_all",
    )

    # CONTROL: rename the function the delegation looks for. Nothing else changes.
    media_verify_ext.probe(repo, "tutorials.sh", "www_tutorials_record")
    media_verify_ext.mutate(
        repo,
        ".ci/media/tutorials.sh",
        r"^www_tutorials_record\(\) \{",
        "www_tutorials_record_RENAMED() {",
    )
    with harness.fake_bin("+uname +dirname"):
        broken = media_verify_ext.run(
            repo, "run.sh", "www", "tutorials", "record", "--force", "installation"
        )
    if broken.rc == 0:
        gate.log_fail(
            "the chain still succeeded after www_tutorials_record was renamed in "
            "tutorials.sh, so the probe proves nothing"
        )
    gate.assert_not_contains(
        broken.combined,
        "MEDIA_CHAIN_REACHED",
        "no marker may be reported once the module no longer defines the name",
    )
    gate.assert_contains(
        broken.combined,
        "www_tutorials_record",
        "the failure names the function the delegation could not find",
    )
    gate.log_pass(
        "./run.sh www reaches tutorials.sh at both depths of its case tree, and stops "
        "reaching it when the module renames the function"
    )


def test_grand_env_wildcard_detection(gate, tmp_path):
    # The `*` must never be glob-expanded against the cwd, which is why the function uses `read -ra`. A fixture directory full of files is staged so a regression would produce a filename rather than "WILD".
    tmp_path.joinpath("decoy-one").write_text("", encoding="utf-8")
    tmp_path.joinpath("decoy-two").write_text("", encoding="utf-8")
    with harness.fake_bin("+uname"):
        result = run_tutorials(
            tmp_path,
            '''
        probe() { REDIACC_ALLOW_GRAND_REPO="$1" _grand_env_is_wildcard && echo "WILD" || echo "no"; }
        probe "*"
        probe "repo1,*,repo2"
        probe "  *  "
        probe "repo1,repo2"
        probe ""''',
        )
    if result.rc != 0:
        gate.log_fail("the probe failed (output: %s)" % result.combined)
    observed = result.combined.splitlines()
    for index, (want, why) in enumerate(
        (
            ("WILD", "a bare * is a wildcard"),
            ("WILD", "a * mixed into a list is a wildcard"),
            ("WILD", "surrounding whitespace is trimmed"),
            ("no", "a list without * is not a wildcard"),
            ("no", "an empty value is not a wildcard"),
        )
    ):
        gate.assert_eq(observed[index] if index < len(observed) else "", want, why)
    gate.log_pass(
        "_grand_env_is_wildcard accepts *, a mixed list and padded whitespace, and rejects the rest"
    )


def test_tutorials_all_routes_each_flag_to_the_step_that_understands_it(gate, tmp_path):
    with harness.fake_bin("+uname"):
        result = run_tutorials_all(
            tmp_path,
            "cd '%s' && www_tutorials_all --lang de --keep-temp --clean-venv --force "
            "--max-idle-ms 400 installation" % tmp_path,
        )
    if result.rc != 0:
        gate.log_fail("www_tutorials_all failed (output: %s)" % result.combined)
    out = result.combined
    gate.assert_contains(
        out,
        "record: --force --max-idle-ms 400 installation",
        "record gets --force, --max-idle-ms and the positional",
    )
    gate.assert_contains(
        out, "generate: --clean-venv --lang de", "generate gets the venv flag and the language"
    )
    gate.assert_contains(
        out, "video: --keep-temp --lang de", "video gets --keep-temp and the language"
    )
    gate.assert_not_contains(out, "record: --lang", "--lang must NOT reach record")
    gate.assert_not_contains(out, "video: --clean-venv", "--clean-venv must NOT reach video")
    gate.assert_contains(out, "extract", "extract runs between record and generate")
    gate.assert_contains(out, "scaffold", "scaffold-locales runs too")
    gate.assert_contains(out, "validate", "validate closes the pipeline")
    gate.log_pass(
        "www_tutorials_all splits --lang / --keep-temp / --clean-venv / --force / "
        "--max-idle-ms to the right steps"
    )


def test_the_numeric_options_are_validated_before_any_work_starts(gate, tmp_path):
    (tmp_path / "packages/www/src/data/tutorial-timeline/en").mkdir(parents=True, exist_ok=True)
    (tmp_path / "artifacts").mkdir(parents=True, exist_ok=True)

    with harness.fake_bin("+rm +uname"):
        result = run_tutorials(tmp_path, "www_tutorials_video --jobs abc")
        gate.assert_exit_code(1, result.rc, "a non-numeric --jobs must be rejected")
        gate.assert_contains(
            result.combined,
            "--jobs must be a positive integer, got: abc",
            "names the bad value",
        )

        result = run_tutorials(tmp_path, "www_tutorials_video --jobs 0")
        gate.assert_exit_code(1, result.rc, "--jobs 0 must be rejected")

        result = run_tutorials(tmp_path, "www_tutorials_video --jobs=2 --lang=fr --debug")
        gate.assert_exit_code(
            0, result.rc, "the =-joined forms must be accepted (output: %s)" % result.combined
        )
        gate.assert_contains(result.combined, "pool: 2 ", "--jobs=2 reaches the pool")
        gate.assert_contains(result.combined, "--debug", "a passthrough flag reaches the pool")

    with harness.fake_bin("+rm +basename +grep +uname"):
        result = run_tutorials(tmp_path, "www_tutorials_media --jobs abc")
        gate.assert_exit_code(1, result.rc, "a non-numeric --jobs must be rejected")

        result = run_tutorials(
            tmp_path,
            "RDC_TUTORIAL_HWENC=1 www_tutorials_media --langs en,de --subtitle --debug",
        )
        gate.assert_exit_code(
            0, result.rc, "the happy path must succeed (output: %s)" % result.combined
        )
        gate.assert_contains(
            result.combined,
            "forcing it to 0 so renders stay off the GPU",
            "hardware encoding is refused, loudly",
        )
        # THE SPLIT IS THE ASSERTION. --subtitle belongs to the narration process and --debug to the renderer, and the two are collected into different variables by the same while-loop. Checking only that both appear somewhere would pass even if the loop sent both to both.
        producer_line = lines_matching(result.combined, "producer:")
        pool_line = lines_matching(result.combined, "pool:")
        gate.assert_contains(producer_line, "--subtitle", "--subtitle is a TTS flag")
        gate.assert_not_contains(
            producer_line, "--debug", "a render passthrough must not reach the narrator"
        )
        gate.assert_contains(
            producer_line,
            "en de",
            "--langs is split on commas into the producer's language list",
        )
        gate.assert_contains(pool_line, "--debug", "--debug is a render passthrough")
        gate.assert_not_contains(
            pool_line, "--subtitle", "a TTS flag must not reach the render pool"
        )
        gate.assert_contains(
            pool_line, "pool: 3", "an absent --jobs falls back to _tutorial_auto_jobs"
        )

    with harness.fake_bin("+mkdir +date +flock +rm +tee +uname"):
        result = run_tutorials(tmp_path, "www_tutorials_watch --nope")
        gate.assert_exit_code(
            1,
            result.rc,
            "an unknown watch option must be rejected rather than treated as a name",
        )
        gate.assert_contains(
            result.combined, "Unknown watch option: --nope", "names the option it refused"
        )

        result = run_tutorials(tmp_path, "www_tutorials_watch --poll abc")
        gate.assert_exit_code(1, result.rc, "a non-numeric --poll must be rejected")
        gate.assert_contains(
            result.combined, "--poll must be a positive integer", "says what --poll must be"
        )
    gate.log_pass(
        "--jobs and --poll are validated, unknown watch options are refused, and hardware "
        "encoding is forced off"
    )


def test_the_teaser_functions_are_solely_owned_by_this_module(gate):
    media_verify.media_assert_module_owns(gate, "teaser.sh", *TEASER_MOVED)


def test_the_teaser_ownership_assertion_can_fail(gate, tmp_path):
    # `die` is the name this control uses because media.sh wrote it in the ONE-LINE
    # `die() { ...; }` form, and the shared control plants that spelling into
    # media.sh specifically. A block-only search would report the re-planted copy as absent and pass, so this is also the case that proves `fidelity_extract_any` is wired in.
    media_verify.media_assert_ownership_control(gate, tmp_path, "teaser.sh", "die")


def test_the_teaser_archaeology_is_here_and_nowhere_else(gate):
    # The incident prose is what makes these three functions the shape they are, and it is the part no structural assertion can see.
    teaser = TEASER.read_text(encoding="utf-8")
    media_sh = (ROOT / "media.sh").read_text(encoding="utf-8")
    for sentence in (
        "a guard that blocks everything gets switched off",
        "exits only the SUBSHELL",
        "so this teaser will",
        "the pre-palette artifacts measure 30 to 50",
    ):
        if sentence not in teaser:
            gate.log_fail("the incident comment is missing from teaser.sh: %s" % sentence)
        if sentence in media_sh:
            gate.log_fail(
                "media.sh carries a second copy of this comment, which will fork: %s" % sentence
            )
        gate.assertions += 2
    gate.log_pass(
        "every incident comment lives in teaser.sh, and media.sh keeps no second copy to drift from"
    )


def test_media_sh_still_reaches_this_module(gate, tmp_path):
    # THE DELEGATION FOR THE private/growth SIDE.
    repo = media_verify_ext.media_chain_sandbox(tmp_path)
    media_verify_ext.probe(repo, "teaser.sh", "growth_run")
    with harness.fake_bin("+uname +dirname"):
        result = media_verify_ext.run(repo, "media.sh", "run", "video_pipeline", "--step", "8000")
    if result.rc != 0:
        gate.log_fail("./media.sh run failed in the sandbox: %s" % result.combined.strip())
    gate.assert_eq(
        result.combined.strip(),
        "MEDIA_CHAIN_REACHED:growth_run:video_pipeline --step 8000",
        "media.sh must reach teaser.sh's growth_run with its arguments intact",
    )

    media_verify_ext.mutate(
        repo, ".ci/media/teaser.sh", r"^growth_run\(\) \{", "growth_run_RENAMED() {"
    )
    with harness.fake_bin("+uname +dirname"):
        broken = media_verify_ext.run(repo, "media.sh", "run", "video_pipeline", "--step", "8000")
    if broken.rc == 0:
        gate.log_fail(
            "the chain still succeeded after growth_run was renamed in teaser.sh, so the "
            "probe proves nothing"
        )
    gate.assert_not_contains(
        broken.combined,
        "MEDIA_CHAIN_REACHED",
        "no marker may be reported once the module no longer defines the name",
    )
    gate.assert_contains(
        broken.combined,
        "growth_run",
        "the failure names the function the delegation could not find",
    )
    gate.log_pass(
        "./media.sh run reaches teaser.sh's growth_run, and stops reaching it when the "
        "module renames it"
    )


def test_teaser_dies_before_it_can_half_finish(gate, tmp_path):
    (tmp_path / "private/growth/video_pipeline").mkdir(parents=True, exist_ok=True)
    # python3 and ffmpeg are deliberately absent: every case here must be refused BEFORE anything is executed, which is the property that keeps a tree from being left mid-operation with its sentinels already deleted.
    with harness.fake_bin("+cat +uname"):
        result = run_teaser(tmp_path, "growth_run")
        gate.assert_exit_code(1, result.rc, "growth_run with no pipeline must die")
        gate.assert_contains(result.combined, "usage: ./media.sh run", "prints the usage line")

        result = run_teaser(tmp_path, "growth_run nosuchpipeline")
        gate.assert_exit_code(1, result.rc, "an unknown pipeline must die")
        gate.assert_contains(
            result.combined,
            "no such pipeline: nosuchpipeline",
            "names the pipeline it could not find",
        )

        result = run_teaser(tmp_path, "venv_for video_pipeline")
        gate.assert_exit_code(1, result.rc, "a pipeline with no venv must die")
        gate.assert_contains(
            result.combined,
            "no venv for pipeline 'video_pipeline'",
            "names the pipeline and where it looked",
        )

        result = run_teaser(tmp_path, "growth_usage")
        gate.assert_exit_code(0, result.rc, "the usage text must print cleanly")
        gate.assert_contains(
            result.combined,
            "cwd = private/growth",
            "the usage states the invariant the wrapper exists for",
        )
    gate.log_pass("growth_run and venv_for refuse a bad invocation before running anything")

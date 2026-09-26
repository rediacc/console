"""Port of `.ci/scripts/test/gates/test-media-pool.sh`, retired in W7 P5.

`.ci/media/pool.sh`, the render side of tutorial media.

WHAT IS ACTUALLY WORTH ASSERTING HERE. Three of these four functions carry a property a reader cannot check by reading:

  `_tutorial_render_pairs` forwards everything after its first two arguments to the
  readiness predicate VERBATIM. That is the whole reason the watch can ask a narrower
  question without a second copy of the invocation existing; a lost "$@" would be
  invisible until a watch quietly rendered the wrong set.

  `_tutorial_auto_jobs` prints its number on STDOUT while every log line goes to
  stderr. The pool's stdin is a work queue, so one log line on the wrong stream
  becomes a bogus render. The case below captures stdout ALONE and requires it to
  hold nothing but the number.

  `_tutorial_video_pool` keeps at most `$jobs` renders in flight while STREAMING. A
  pool that waited for each batch would still render everything and still pass a "did
  all the work happen" test, so concurrency is MEASURED rather than assumed.

  `_tutorial_video_pool` RETURNS 0 EVEN WHEN RENDERS FAIL, and that is a contract
  rather than sloppiness: its three callers report failures from a `compgen -G` block
  placed AFTER it returns, and two of them call it bare under `set -e`. Phase 1 found
  the opposite behaviour and pinned it as a defect; phase 2 fixed it in pool.sh, and
  the case below is now the regression test, with the caller's report block reproduced
  verbatim so "the report is reached" is OBSERVED rather than inferred.

All of it runs with node, npx and tsx absent: the renderer is a fake that records when it starts and stops, which is exactly the evidence the concurrency claim needs.

TWO THINGS THE PORT REIMPLEMENTS, and both agree with the twin by construction. `max_overlap` is a running +1/-1 over the trace's S and E lines, identical arithmetic in either language. `compgen -G "<prefix>.*"` becomes `glob` over the same pattern: both ask "which files begin with this prefix and a dot", and both answer nothing rather than erroring when none do -- which matters,
because the CLEAN-run case asserts exactly that emptiness.

WHY ONE CASE BYPASSES `media_run_module`. `_tutorial_auto_jobs` is asserted on its STREAM SEPARATION, and `media_run_module` returns a `RunResult` whose `.combined` would merge the very two streams under test. That case therefore builds its own `bash -c` with the same three sources and reads `.out` and `.err` apart, which is the same shell the helper would have built.

NO `xdist_group`. `fake_bin` mutates PATH on this process and restores it in a `finally`; every case owns its own `mktemp -d`, nothing is bound, and `MEDIA_MODULE_DIR` is a per-call argument here rather than an environment variable.
"""

import stat

from rediacc_ci.tests.gates import harness, media_verify

MODULE = media_verify.MEDIA_DIR / "pool.sh"

MOVED = (
    "_tutorial_render_pairs",
    "_tutorial_auto_jobs",
    "_tutorial_video_render_one",
    "_tutorial_video_pool",
)

# THE CALLER'S REPORT BLOCK, REPRODUCED VERBATIM. `www_tutorials_video`, `_media` and `_watch` all end the same way: run the pool, then `if compgen -G` to print the list and return 1. Two of the three call the pool BARE, so under `set -e` a non-zero
# return from it skips that block entirely. Running the pool alone therefore cannot
# tell the fixed behaviour from the broken one -- both end with failure files on disk and a non-zero somewhere -- which is why this reproduces the CALLER.
POOL_WITH_CALLER_REPORT = """
    printf "a\\ten\\nb\\tfr\\n" | _tutorial_video_pool 2 "PREFIX"
    if compgen -G "PREFIX".* >/dev/null; then
        log_error "Failed tutorials:"
        cat "PREFIX".* >&2
        exit 1
    fi
    echo "NO-FAILURES-SEEN"
"""


def write_exec(path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def run_pool(root, code: str, *, module_dir=None) -> harness.RunResult:
    return media_verify.media_run_module(root, "pool.sh", code, module_dir=module_dir)


def script_machine(bindir, cores: int, gib: int) -> None:
    """`_tutorial_auto_jobs` reads the machine through exactly two commands.

    `nproc`, and an `awk` over /proc/meminfo. /proc/meminfo cannot be staged, so awk is the injection point -- it is scripted to print the memory figure the case wants, which is precisely what the real one would have printed.

    BOTH NOW REACH THE MACHINE THROUGH `.ci/media/portable.sh`'s seams (`media_cpu_count` and `media_avail_mem_gb`) rather than being spelled inline, and both fakes still work unchanged, which is the point: a seam that changed what the module observes would be a rewrite wearing a refactor's clothes. `media_avail_mem_gb` keeps the division INSIDE awk for exactly this reason -- the
    fake prints GiB, and a shell-side divide would turn that into 0.
    """
    write_exec(bindir / "nproc", "#!/bin/bash\necho %d\n" % cores)
    write_exec(bindir / "awk", "#!/bin/bash\necho %d\n" % gib)


def script_renderer(bindir, trace, code: int = 0) -> None:
    """flock and nice become transparent passthroughs; npx becomes the renderer.

    The real flock and nice would need a lock file and a priority change that prove nothing here. The renderer records the moment it starts and the moment it stops, and that trace is what makes the concurrency claim MEASURABLE instead of asserted.
    """
    write_exec(bindir / "flock", '#!/bin/bash\nshift\nexec "$@"\n')
    write_exec(bindir / "nice", '#!/bin/bash\nshift 2\nexec "$@"\n')
    write_exec(
        bindir / "npx",
        "#!/bin/bash\nprintf 'S\\n' >>\"%s\"\nsleep 0.3\nprintf 'E\\n' >>\"%s\"\nexit %d\n"
        % (trace, trace, code),
    )


def max_overlap(trace) -> int:
    """The largest number of renders that were ever in flight. See the module docstring."""
    current = highest = 0
    for line in trace.read_text(encoding="utf-8").splitlines():
        if line == "S":
            current += 1
        elif line == "E":
            current -= 1
        highest = max(highest, current)
    return highest


def failure_files(directory, prefix: str) -> list:
    """`compgen -G "<prefix>.*"`, as a sorted list of paths."""
    return sorted(directory.glob("%s.*" % prefix))


def test_every_moved_function_is_solely_owned_by_this_module(gate):
    """WHAT THIS REPLACED. Until the cutover run.sh carried its own copy of all four and this compared the bodies byte for byte. run.sh has no copies now -- and this module has DELIBERATELY diverged from what run.sh used to hold, because phase 2 fixed the `wait -n` defect here -- so byte-identity is not merely unmeasurable, it is the wrong question."""
    gate.log_test("pool.sh must hold the ONLY definition of all four moved functions")
    media_verify.media_assert_module_owns(gate, "pool.sh", *MOVED)


def test_the_ownership_assertion_can_fail(gate):
    gate.log_test("CONTROL: every way the ownership assertion could go quiet")
    with harness.temp_dir() as d:
        media_verify.media_assert_ownership_control(gate, d, "pool.sh", "_tutorial_video_pool")


def test_render_pairs_is_a_thin_forwarder(gate):
    gate.log_test("everything after the first two arguments must reach the predicate verbatim")
    with harness.temp_dir() as d:
        with harness.fake_bin("node +uname") as fake:
            result = run_pool(
                d,
                "_tutorial_render_pairs installation en --stale-only --require-provider voxcpm2",
            )
            if result.rc != 0:
                gate.log_fail("the predicate call failed", result)
            call = fake.record("node")
            gate.assert_contains(
                call,
                "packages/www/scripts/list-tutorial-render-pairs.js",
                "calls the ONE readiness predicate",
            )
            gate.assert_contains(call, "--cast installation", "the first argument becomes --cast")
            gate.assert_contains(call, "--lang en", "the second argument becomes --lang")
            gate.assert_contains(
                call,
                "--stale-only --require-provider voxcpm2",
                "everything after the first two is forwarded verbatim",
            )

        with harness.fake_bin("node +uname") as fake:
            result = run_pool(d, "_tutorial_render_pairs '' ''")
            if result.rc != 0:
                gate.log_fail("the predicate call failed", result)
            call = fake.record("node")
            gate.assert_not_contains(
                call, "--cast", "an empty name must not become an empty --cast"
            )
            gate.assert_not_contains(
                call, "--lang", "an empty lang must not become an empty --lang"
            )
    gate.log_pass(
        "_tutorial_render_pairs forwards extra arguments verbatim and omits empty selectors"
    )


def test_auto_jobs_is_bounded_by_cpu_memory_and_a_ceiling(gate):
    gate.log_test("the job count is bounded by CPU, by memory, by a ceiling and by a floor")
    with harness.temp_dir() as d:
        # (cores, GiB, expected jobs). CPU-bound: (20-4)/4 = 4 against (64-16)/4 = 12.
        # Memory-bound: (64-4)/4 = 15 against (32-16)/4 = 4. The ceiling: both arms
        # exceed 6. The floor: a small machine still gets one render rather than zero.
        for cores, gib, expect in ((20, 64, "4"), (64, 32, "4"), (64, 256, "6"), (4, 8, "1")):
            with harness.fake_bin("nproc awk +chmod +uname") as fake:
                script_machine(fake.dir, cores, gib)
                # STDOUT ALONE. The number is the return value; every log_* line is stderr, and the pool READS this stream. Keeping them apart is the assertion, not a convenience.
                script = "\n".join(
                    [
                        "ROOT_DIR='%s'" % d,
                        "source '%s/.ci/scripts/lib/common.sh'" % media_verify.MEDIA_ROOT,
                        "source '%s/portable.sh'" % media_verify.MEDIA_DIR,
                        "source '%s'" % MODULE,
                        "_tutorial_auto_jobs",
                    ]
                )
                result = harness.run([media_verify._BASH, "-c", script])
                gate.assert_eq(
                    result.out.strip(), expect, "jobs for %d cores / %d GiB" % (cores, gib)
                )
                gate.assert_contains(
                    result.err, "auto --jobs", "the log line exists, and it is on STDERR"
                )
    gate.log_pass(
        "_tutorial_auto_jobs is bounded by CPU, by memory, by a ceiling of 6 and a floor of 1, "
        "and prints only the number on stdout"
    )


def test_the_pool_streams_within_its_bound_and_records_failures(gate):
    gate.log_test("at most --jobs in flight, one file per failed pair, and the caller reports")
    with harness.temp_dir() as d:
        (d / "packages" / "www").mkdir(parents=True)

        # 1. CONCURRENCY, measured rather than assumed.
        with harness.fake_bin("flock nice npx +sleep +grep +chmod +cat +uname") as fake:
            trace = d / "trace"
            script_renderer(fake.dir, trace)
            trace.write_text("", encoding="utf-8")
            result = run_pool(
                d,
                "printf 'a\\ten\\nb\\ten\\nc\\ten\\nd\\ten\\ne\\ten\\n' | "
                "_tutorial_video_pool 2 '%s/fail'" % d,
            )
            if result.rc != 0:
                gate.log_fail("the pool failed", result)
            starts = trace.read_text(encoding="utf-8").splitlines().count("S")
            gate.assert_eq(starts, 5, "every queued pair must be rendered")
            gate.assert_eq(max_overlap(trace), 2, "at most --jobs renders may be in flight at once")
            gate.assert_eq(failure_files(d, "fail"), [], "a clean run leaves no failure files")

        # 2. FEWER ITEMS THAN --jobs, so the loop never reaches `wait -n`. The pool records the failure and returns 0, which is what lets the caller's `compgen -G` block print the "Failed tutorials:" list.
        with harness.fake_bin("flock nice npx +sleep +chmod +cat +wc +uname") as fake:
            trace2 = d / "trace2"
            script_renderer(fake.dir, trace2, 1)
            trace2.write_text("", encoding="utf-8")
            result = run_pool(d, "printf 'a\\ten\\n' | _tutorial_video_pool 2 '%s/f2'" % d)
            gate.assert_exit(0, result, "with fewer pairs than jobs the pool records and returns 0")
            files = failure_files(d, "f2")
            gate.assert_eq(
                len(files),
                1,
                "each failed render writes its OWN file, so nothing depends on append atomicity",
            )
            gate.assert_contains(
                "".join(f.read_text(encoding="utf-8") for f in files),
                "a × en",
                "the failure file names the pair",
            )

        # 3. THE DEFECT THIS PINS, AND THE FIX THAT CLOSED IT. Once the queue reaches --jobs the pool calls `wait -n`, which returns the REAPED JOB'S exit status. Under the `set -euo pipefail` that run.sh and common.sh both set, a non-zero there aborted _tutorial_video_pool on the spot, so the report block never ran: the list was never printed and the per-pair files were abandoned
        # in /tmp. Reproduced 2026-09-06 and fixed in pool.sh (`wait -n || true`, plus an explicit `return 0`).
        #
        # rc is 1 either way, so IT IS NOT THE EVIDENCE. The report line is: before the fix nothing printed it, and the sibling job was still in flight when the pool's shell died, so its failure file was a race.
        with harness.fake_bin("flock nice npx +sleep +chmod +cat +wc +uname") as fake:
            trace3 = d / "trace3"
            script_renderer(fake.dir, trace3, 1)
            trace3.write_text("", encoding="utf-8")
            result = run_pool(d, POOL_WITH_CALLER_REPORT.replace("PREFIX", "%s/f3" % d))
            gate.assert_exit(
                1,
                result,
                "failures still make the CALLER exit 1 -- via its report block, not via the "
                "pool aborting",
            )
            gate.assert_contains(
                result.combined,
                "Failed tutorials:",
                "the report block must be REACHED; this line is the whole difference the fix makes",
            )
            gate.assert_contains(result.combined, "a × en", "the first pair is named in the report")
            gate.assert_contains(
                result.combined,
                "b × fr",
                "and so is the pair that was in flight when the old code aborted",
            )
            gate.assert_not_contains(
                result.combined,
                "NO-FAILURES-SEEN",
                "the clean-run path must not be taken when renders failed",
            )
            gate.assert_eq(
                len(failure_files(d, "f3")),
                2,
                "both failed pairs write their own file, and the pool now waits for both",
            )

        # 4. THE CONTROL, and the red half of a red-then-green. A copy of pool.sh with `|| true` and the explicit `return 0` taken back out -- which is exactly the pre-fix source -- must make case 3 fail. If the report still appeared, the assertion carrying the fix would be proving nothing.
        mutant = d / "mutant"
        mutant.mkdir()
        lines = MODULE.read_text(encoding="utf-8").splitlines(keepends=True)
        rewritten = [
            "            wait -n\n" if line == "            wait -n || true\n" else line
            for line in lines
            if line != "    return 0\n"
        ]
        (mutant / "pool.sh").write_text("".join(rewritten), encoding="utf-8")
        mutated_text = (mutant / "pool.sh").read_text(encoding="utf-8")
        if "\n            wait -n\n" not in mutated_text:
            gate.log_fail(
                "the fix was not undone in the mutant, so the control would pass for the "
                "wrong reason"
            )
        if "\n    return 0\n" in mutated_text:
            gate.log_fail(
                "the explicit return 0 survived in the mutant, so the control would pass for "
                "the wrong reason"
            )
        with harness.fake_bin("flock nice npx +sleep +chmod +cat +wc +uname") as fake:
            trace4 = d / "trace4"
            script_renderer(fake.dir, trace4, 1)
            trace4.write_text("", encoding="utf-8")
            result = run_pool(
                d, POOL_WITH_CALLER_REPORT.replace("PREFIX", "%s/f4" % d), module_dir=mutant
            )
            gate.assert_exit(
                1,
                result,
                "the pre-fix pool still ends non-zero, which is why the exit code alone never "
                "showed the bug",
            )
            gate.assert_not_contains(
                result.combined,
                "Failed tutorials:",
                "with the defect restored the report block must NOT be reached",
            )
            gate.assert_not_contains(
                result.combined,
                "NO-FAILURES-SEEN",
                "and the clean-run path is not reached either -- the shell simply died",
            )
    gate.log_pass(
        "the pool keeps at most --jobs renders in flight, writes one failure file per failed "
        "pair, and lets the caller's report block run -- which the pre-fix source does not"
    )

"""Port of `.ci/scripts/test/gates/test-media-r2.sh`.

`.ci/media/r2.sh`, the tutorial-narration cache in R2.

THE BEHAVIOUR THAT MATTERS IS THE ABSENT-CREDENTIALS ONE. Regenerating narration costs real TTS GPU time, which is why this cache exists at all; but a developer without R2 credentials must still be able to run the pipeline, so both functions WARN and RETURN 0 rather than failing. Get that backwards and a fresh checkout either cannot generate tutorials at all, or silently re-pays
for every mp3.

Both directions are driven here with aws, curl and the network absent, and the sync scripts replaced by RECORDERS at the fixture root. No bucket is touched and no credential is read: the three CLOUDFLARE_R2_MEDIA_* variables are set to obvious placeholders in the credentials-present case.

WHY THE SEAM IS A FIXTURE TREE AND NOT A FAKE BINARY. The two functions call the sync scripts by ABSOLUTE path under `$ROOT_DIR`, not through PATH, so shadowing a name on PATH would shadow nothing. The recorder is written into `<fixture>/.ci/scripts/deploy/` and `ROOT_DIR` points at the fixture.

THE OWNERSHIP ASSERTION replaced a byte-identity check against run.sh's copy. run.sh has no copy now, so the question became ownership: exactly one file defines each name, it is this module, run.sh and media.sh define neither, and media-entry.sh resolves both names here.

NO `xdist_group`, for the reasons written out in test_gate_media_cuda.py: every
case takes its own `mktemp -d`, nothing is bound, and `MEDIA_MODULE_DIR` is a
per-call ARGUMENT here rather than the environment variable it is in bash.
"""

import pathlib
import stat

from rediacc_ci.tests.gates import harness, media_verify

BASH_TWIN = ".ci/scripts/test/gates/test-media-r2.sh"

MODULE = media_verify.MEDIA_DIR / "r2.sh"
MOVED = ("www_tutorial_audio_restore", "www_tutorial_audio_upload")

# `+uname` is REQUIRED: common.sh runs `CI_OS="$(detect_os)"` at source time and
# detect_os shells out to uname. `+cat` matches the twin's spec.
BASE_SPEC = "+cat +uname"

CREDENTIALS = (
    "export CLOUDFLARE_R2_MEDIA_ACCESS_KEY_ID=placeholder-key\n"
    "export CLOUDFLARE_R2_MEDIA_SECRET_ACCESS_KEY=placeholder-secret\n"
    "export CLOUDFLARE_R2_MEDIA_ENDPOINT=https://example.invalid\n"
)

NO_CREDENTIALS = (
    "unset CLOUDFLARE_R2_MEDIA_ACCESS_KEY_ID CLOUDFLARE_R2_MEDIA_SECRET_ACCESS_KEY "
    "CLOUDFLARE_R2_MEDIA_ENDPOINT\n"
)


def stage_sync_scripts(root: pathlib.Path, code: int = 0) -> pathlib.Path:
    """Replace both sync scripts with recorders under the FIXTURE root.

    Returns the path of the call log. Truncated on every call, so a case reads only its own invocations.
    """
    deploy = root / ".ci" / "scripts" / "deploy"
    deploy.mkdir(parents=True, exist_ok=True)
    calls = root / "sync-calls"
    for name in ("sync-media-from-r2.sh", "sync-media-to-r2.sh"):
        target = deploy / name
        target.write_text(
            '#!/bin/bash\nprintf "%%s\\n" "%s $*" >>"%s"\nexit %d\n' % (name, calls, code),
            encoding="utf-8",
        )
        target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    calls.write_text("", encoding="utf-8")
    return calls


def run_r2(root, code: str, *, module_dir=None):
    return media_verify.media_run_module(root, "r2.sh", code, module_dir=module_dir)


def test_this_module_solely_owns_the_moved_functions(gate):
    gate.log_test("r2.sh must be the only definition of both moved names")
    media_verify.media_assert_module_owns(gate, "r2.sh", *MOVED)


def test_the_ownership_assertion_can_fail(gate):
    gate.log_test("CONTROL: every way the ownership assertion could go quiet")
    with harness.temp_dir() as d:
        media_verify.media_assert_ownership_control(gate, d, "r2.sh", MOVED[0])


def test_a_planted_mutation_is_visible_to_the_behaviour_cases(gate):
    gate.log_test("CONTROL FOR THE CASES BELOW: the module seam must be load-bearing")
    # `--audio-only` is the flag that keeps this from syncing the whole media bucket, and the credentialed case asserts it BY NAME. Drop it in a copy of the module and that assertion must stop holding; if it still held, the case would be reading something other than the module under test.
    with harness.temp_dir() as d:
        mutant = d / "mutant"
        mutant.mkdir()
        mutated = MODULE.read_text(encoding="utf-8").replace("--audio-only", "--all")
        (mutant / "r2.sh").write_text(mutated, encoding="utf-8")
        if "--all" not in mutated:
            gate.log_fail(
                "the mutation did not apply, so this control would pass for the wrong reason"
            )
        calls = stage_sync_scripts(d)
        with harness.fake_bin(BASE_SPEC):
            result = run_r2(d, CREDENTIALS + "www_tutorial_audio_restore", module_dir=mutant)
            gate.assert_exit(0, result, "the mutated copy still runs; only its flag changed")
            media_verify.media_assert_mutation_swapped(
                gate,
                calls.read_text(encoding="utf-8"),
                "sync-media-from-r2.sh --audio-only",
                "sync-media-from-r2.sh --all",
                "flag",
            )
    gate.log_pass(
        "swapping --audio-only for --all in r2.sh changes what the behaviour cases observe"
    )


def test_the_cache_is_optional_in_both_directions(gate):
    gate.log_test("no credentials SKIPS; credentials sync the audio prefix and nothing else")
    with harness.temp_dir() as d:
        calls = stage_sync_scripts(d)

        # NO CREDENTIALS. The load-bearing direction: a fresh checkout must still be able to run the pipeline.
        with harness.fake_bin(BASE_SPEC):
            result = run_r2(
                d,
                NO_CREDENTIALS + "www_tutorial_audio_restore\nwww_tutorial_audio_upload\n",
            )
            gate.assert_exit(0, result, "no credentials must SKIP, never fail the pipeline")
            gate.assert_contains(
                result.combined,
                "skipping tutorial-audio cache restore",
                "says the restore was skipped",
            )
            gate.assert_contains(
                result.combined,
                "skipping tutorial-audio cache upload",
                "says the upload was skipped",
            )
            gate.assert_eq(
                calls.read_text(encoding="utf-8"),
                "",
                "no sync script may run without credentials",
            )

        # CREDENTIALS PRESENT. Placeholders only; no bucket is touched.
        with harness.fake_bin(BASE_SPEC):
            result = run_r2(
                d, CREDENTIALS + "www_tutorial_audio_restore\nwww_tutorial_audio_upload\n"
            )
            gate.assert_exit(0, result, "the credentialed path must succeed")
            recorded = calls.read_text(encoding="utf-8")
            gate.assert_contains(
                recorded,
                "sync-media-from-r2.sh --audio-only",
                "restore pulls only the audio prefix",
            )
            gate.assert_contains(
                recorded,
                "sync-media-to-r2.sh --audio-only",
                "upload pushes only the audio prefix",
            )
    gate.log_pass(
        "no credentials skips both directions; credentials sync the audio prefix and nothing else"
    )


def test_a_broken_sync_never_fails_the_pipeline(gate):
    gate.log_test("a sync script that exits non-zero must warn, not kill the pipeline")
    with harness.temp_dir() as d:
        stage_sync_scripts(d, code=1)
        with harness.fake_bin(BASE_SPEC):
            result = run_r2(
                d, CREDENTIALS + "www_tutorial_audio_restore\nwww_tutorial_audio_upload\n"
            )
            gate.assert_exit(0, result, "a failed cache sync must not fail the pipeline")
            gate.assert_contains(
                result.combined,
                "Audio cache restore failed, continuing without it",
                "the restore failure is a warning",
            )
            gate.assert_contains(
                result.combined, "Audio cache upload failed", "the upload failure is a warning"
            )
    gate.log_pass("a sync script that exits non-zero produces a warning and a zero exit")

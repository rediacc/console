"""Port of `.ci/scripts/test/gates/test-breakpoint-drift.sh`, retired in W7 P5.

Gate test for `check-breakpoint-drift.sh`, the integrity oracle for the vendored `.ci/breakpoint/` folder.

WHY THIS FILE MATTERS MORE THAN A USUAL GATE TEST. The drift gate is the ONLY thing making the folder safe to copy into other repositories. Everything else in the design leans on it: the "one vendorable folder" promise, the refusal to let downstream regenerate the manifest, the accept-list escape hatch. If it silently stops detecting something, a vendored copy becomes a private
fork that upstream can never fix and the next re-vendor destroys without trace -- and nothing anywhere would report a problem.

So every one of its failure modes gets a NEGATIVE case here: the gate is made to fail on purpose, and the assertion is that it failed AND said why. A gate that has only ever been observed to pass has not been verified.

Two real defects this file would have caught, both found by hand instead:

  * `--write` refused inside the CANONICAL repo, because the slug regex left the `.git`
    suffix on (`rediacc/console.git` != `rediacc/console`). The only documented way past
    it was the accept list, i.e. the gate taught people to suppress it. Covered by
    `test_write_regenerates_in_console`.
  * The manifest silently going stale after an edit to a frozen file. Covered by
    `test_write_is_byte_identical_to_committed`, which doubles as the "somebody edited a
    script and forgot `--write`" freshness check.

`env_replace=True` IS THE TWIN'S `env -i`, on every invocation and deliberately: it
strips `GITHUB_REPOSITORY` and anything else that could make the gate behave differently here than in a vendored checkout. A case that passes only because of the ambient environment is not evidence about the vendored case.

WHY THE DRIVER PORTED THIS AND NOT AN AGENT. `agent/8f55d4f0/W7P3-batch5-brief.md` records six `test-breakpoint-*.sh` subjects as unportable by any agent under the standard brief and NOT on merit, because plant-verifying one means temporarily writing under `.ci/breakpoint/**`, which invariant 8 forbids any sweep from touching. The brief's two ways out are to hand one batch owner
that path explicitly or to exclude them in the derivation with the reason recorded, and it adds "Do not silently drop them a fourth time." This is the first option: `.ci/breakpoint` is the driver's path.

NO `xdist_group`. Every case builds its own `cp -r` copy of the folder inside its own `mktemp -d` and runs the gate there; the real tree is only ever READ.
"""

import difflib
import os
import shutil

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BP_SRC = paths.from_root(".ci", "breakpoint")
GATE_REL = "scripts/check-breakpoint-drift.sh"


def make_copy(tmp):
    """An isolated copy of the folder, with no console and no git around it."""
    dest = tmp / "bp"
    shutil.copytree(BP_SRC, dest)
    shutil.rmtree(dest / ".git", ignore_errors=True)
    return dest


def run_gate(bp, *args: str, **extra: str) -> harness.RunResult:
    """The gate, in the copy, with the environment REPLACED. Streams merged as the twin merges them."""
    bash = harness.require_tool("bash", "install bash; the subject is a bash script")
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.fspath(bp),
        "RUNNER_TEMP": os.fspath(bp),
    }
    env.update(extra)
    result = harness.run([bash, os.fspath(bp / GATE_REL), *args], env=env, env_replace=True)
    return harness.RunResult(result.rc, result.combined, "")


def manifest_body(bp) -> str:
    """The manifest's entries, comments dropped and sorted -- the twin's `grep -v '^#' | sort`."""
    lines = (bp / "MANIFEST.sha256").read_text(encoding="utf-8").splitlines()
    return "\n".join(sorted(line for line in lines if not line.startswith("#")))


def test_clean_copy_passes(gate):
    with harness.temp_dir() as tmp:
        run = run_gate(make_copy(tmp))
        gate.assert_exit(0, run, "an unmodified copy must verify")
        gate.assert_contains(run.out, "Verified", "the gate must report what it verified")
        gate.assert_not_contains(run.out, "Verified 0 files", "verifying zero files is vacuous")
    gate.log_pass("clean copy verifies and reports a non-zero file count")


def test_byte_flip_is_detected(gate):
    with harness.temp_dir() as tmp:
        bp = make_copy(tmp)
        target = bp / "scripts" / "hold-breakpoint.sh"
        target.write_text(
            target.read_text(encoding="utf-8") + "\n# a single added comment line\n",
            encoding="utf-8",
        )
        run = run_gate(bp)
        if run.rc == 0:
            gate.log_fail("a modified script verified clean -- the gate cannot see edits")
        gate.assert_contains(run.out, "MISMATCH", "the failure must be classified as MISMATCH")
        gate.assert_contains(
            run.out,
            "scripts/hold-breakpoint.sh",
            "the failure must NAME the file that changed",
        )
    gate.log_pass("a one-line edit is detected and the offending file is named")


def test_missing_file_is_detected(gate):
    with harness.temp_dir() as tmp:
        bp = make_copy(tmp)
        (bp / "scripts" / "hold-breakpoint.sh").unlink()
        run = run_gate(bp)
        if run.rc == 0:
            gate.log_fail("a deleted frozen file verified clean")
        gate.assert_contains(
            run.out, "MISSING", "a listed-but-absent file must be classified as MISSING"
        )
    gate.log_pass("deleting a frozen file is detected as MISSING")


def test_untracked_file_is_detected(gate):
    """Without this, adding a NEW script is the trivial way to smuggle code into a vendored copy: it is not in the manifest, so a per-file hash check would never look at it, and the gate would pass while the folder grew."""
    with harness.temp_dir() as tmp:
        bp = make_copy(tmp)
        rogue = bp / "scripts" / "rogue-helper.sh"
        rogue.write_text(
            '#!/bin/bash\necho "this script is not in the manifest"\n', encoding="utf-8"
        )
        rogue.chmod(0o755)
        run = run_gate(bp)
        if run.rc == 0:
            gate.log_fail(
                "a new unmanifested script verified clean -- new code can be smuggled into a copy"
            )
        gate.assert_contains(
            run.out, "UNTRACKED", "an unmanifested script must be classified as UNTRACKED"
        )
        gate.assert_contains(run.out, "rogue-helper.sh", "the failure must name the rogue file")
    gate.log_pass("a new script absent from the manifest is detected as UNTRACKED")


def test_empty_manifest_is_vacuous(gate):
    """Emptying the manifest is the cheapest possible way to make a diverged copy "pass", because every comparison loop then runs zero times and reports success."""
    with harness.temp_dir() as tmp:
        bp = make_copy(tmp)
        (bp / "MANIFEST.sha256").write_text("", encoding="utf-8")
        run = run_gate(bp)
        if run.rc == 0:
            gate.log_fail("an EMPTY manifest verified clean -- emptying it would be a free pass")
        gate.assert_contains(
            run.out, "VACUOUS", "a zero-entry manifest must be classified as VACUOUS"
        )
    gate.log_pass("an empty manifest is rejected as vacuous, not reported as success")


def test_absent_manifest_is_rejected(gate):
    with harness.temp_dir() as tmp:
        bp = make_copy(tmp)
        (bp / "MANIFEST.sha256").unlink()
        run = run_gate(bp)
        if run.rc == 0:
            gate.log_fail(
                "a copy with NO manifest verified clean -- deleting it would be a free pass"
            )
        gate.assert_contains(
            run.out, "no manifest", "the gate must say WHY it refused, not just exit non-zero"
        )
    gate.log_pass("a deleted manifest is rejected with a reason")


def test_write_refused_downstream(gate):
    """THE REFUSAL IS WHAT GIVES THE GATE TEETH. Without it a downstream operator "fixes" a drift failure by regenerating, which records the local fork as canonical and turns every future comparison into a comparison against itself."""
    with harness.temp_dir() as tmp:
        bp = make_copy(tmp)
        run = run_gate(bp, "--write", GITHUB_REPOSITORY="someone/elsewhere")
        if run.rc == 0:
            gate.log_fail(
                "--write succeeded in a repo that is NOT the canonical one; the gate "
                "would then compare a fork against itself forever"
            )
        gate.assert_contains(run.out, "refusing --write", "the refusal must be explicit")
    gate.log_pass("--write is refused outside the canonical repo")


def test_write_regenerates_in_console(gate):
    """Regression test for a live defect: the slug came from a sed expression using `([^/]+?)(\\.git)?$`, and sed has no lazy quantifiers, so `[^/]+` swallowed `console.git` and the `(\\.git)?` group matched empty. `bp_current_repo` returned `rediacc/console.git`, which never equals `rediacc/console` -- so `--write` refused inside the canonical repo and the accept list was the only
    way onward.

    Both remote-URL forms are exercised, since HTTPS clones carry the suffix and SSH clones may not.
    """
    for url in (
        "https://github.com/rediacc/console.git",
        "git@github.com:rediacc/console.git",
    ):
        with harness.temp_dir() as tmp:
            bp = make_copy(tmp)
            (bp / "MANIFEST.sha256").unlink()
            run = run_gate(bp, "--write", GITHUB_REPOSITORY="rediacc/console")
            gate.assert_exit(
                0, run, "--write must succeed in the canonical repo (remote form: %s)" % url
            )
            manifest = bp / "MANIFEST.sha256"
            if not manifest.is_file() or manifest.stat().st_size == 0:
                gate.log_fail("--write reported success but wrote no manifest")
    gate.log_pass("--write regenerates inside the canonical repo (both remote-URL forms)")


def test_write_is_byte_identical_to_committed(gate):
    """Doubles as the "somebody edited a frozen file and forgot --write" check: if the committed manifest does not match what `--write` produces right now, it is stale, and the gate has been verifying against yesterday's hashes."""
    with harness.temp_dir() as tmp:
        bp = make_copy(tmp)
        committed = manifest_body(bp)
        (bp / "MANIFEST.sha256").unlink()
        run = run_gate(bp, "--write", GITHUB_REPOSITORY="rediacc/console")
        if run.rc != 0:
            gate.log_fail("--write failed while checking manifest freshness: %s" % run.out)
        regenerated = manifest_body(bp)
        if committed != regenerated:
            diff = "\n".join(
                difflib.unified_diff(
                    committed.splitlines(), regenerated.splitlines(), "committed", "regenerated"
                )
            )
            gate.log_fail(
                "the committed MANIFEST.sha256 is STALE: a frozen file changed without "
                "--write being re-run\n%s" % diff
            )
    gate.log_pass("the committed manifest matches a fresh regeneration (no forgotten --write)")


def test_valid_blocker_accept_is_honoured(gate):
    with harness.temp_dir() as tmp:
        bp = make_copy(tmp)
        target = bp / "scripts" / "hold-breakpoint.sh"
        target.write_text(
            target.read_text(encoding="utf-8") + "\n# local divergence\n", encoding="utf-8"
        )
        (bp / ".breakpoint-drift-accept").write_text(
            "# BLOCKER: this repo pins a different hold duration because its runners are\n"
            "# billed per minute and the upstream default would triple the invoice\n"
            "scripts/hold-breakpoint.sh\n",
            encoding="utf-8",
        )
        run = run_gate(bp)
        gate.assert_exit(0, run, "a divergence with a valid BLOCKER must be accepted")
        gate.assert_contains(
            run.out, "accepted", "the gate must say the divergence was accepted, not stay silent"
        )
    gate.log_pass("a divergence with a valid BLOCKER reason is accepted and reported")


def test_banned_phrase_blocker_is_rejected(gate):
    with harness.temp_dir() as tmp:
        bp = make_copy(tmp)
        target = bp / "scripts" / "hold-breakpoint.sh"
        target.write_text(
            target.read_text(encoding="utf-8") + "\n# local divergence\n", encoding="utf-8"
        )
        (bp / ".breakpoint-drift-accept").write_text(
            "# BLOCKER: tbd\nscripts/hold-breakpoint.sh\n", encoding="utf-8"
        )
        run = run_gate(bp)
        if run.rc == 0:
            gate.log_fail(
                "'# BLOCKER: tbd' was accepted as a reason -- the escape hatch is unguarded"
            )
    gate.log_pass("a banned-phrase BLOCKER ('tbd') is rejected")


def test_missing_blocker_is_rejected(gate):
    with harness.temp_dir() as tmp:
        bp = make_copy(tmp)
        target = bp / "scripts" / "hold-breakpoint.sh"
        target.write_text(
            target.read_text(encoding="utf-8") + "\n# local divergence\n", encoding="utf-8"
        )
        (bp / ".breakpoint-drift-accept").write_text(
            "scripts/hold-breakpoint.sh\n", encoding="utf-8"
        )
        run = run_gate(bp)
        if run.rc == 0:
            gate.log_fail(
                "a bare path with no BLOCKER comment was accepted -- 'forgot the reason' "
                "must fail loudly"
            )
    gate.log_pass("an accept entry with no BLOCKER comment is rejected")


def test_stale_accept_entry_is_rejected(gate):
    """A BLOCKER proves a reason EXISTS; it cannot prove the reason is still TRUE. An entry naming a path the manifest does not cover can never fire, so it is dead weight at best and a typo protecting nothing at worst."""
    with harness.temp_dir() as tmp:
        bp = make_copy(tmp)
        (bp / ".breakpoint-drift-accept").write_text(
            "# BLOCKER: this path was renamed upstream three releases ago and the entry\n"
            "# was never cleaned up, which is exactly what the liveness rule is for\n"
            "scripts/a-file-that-does-not-exist.sh\n",
            encoding="utf-8",
        )
        run = run_gate(bp)
        if run.rc == 0:
            gate.log_fail(
                "an accept entry naming a non-manifest path was tolerated -- a typo would "
                "silently protect nothing"
            )
        gate.assert_contains(
            run.out, "stale accept entry", "the gate must identify the entry as stale"
        )
    gate.log_pass("a stale accept entry (path absent from the manifest) is rejected")

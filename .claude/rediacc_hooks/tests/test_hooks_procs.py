"""The guards whose subject is the PROCESS TABLE, and the hazard one of them names.

Editing a shell script a process is RUNNING corrupts the running interpreter: bash reads lazily by byte offset, so the edit lands under its feet and it dies at an innocent line while `bash -n` stays clean. Documented at TRAPS.md since 2026-08-09 and hit again on 2026-08-26, on the harness itself, costing a suite pass.

THESE NEED A GENUINELY LIVE PROCESS, not a stubbed pgrep. Each guard's whole claim is that it reads the process table, and a stub would prove the arithmetic while leaving that claim untested. So the fixtures spawn real ones, and every block also carries the LIVENESS control -- the same payload once the process is gone -- because without it the guard could be keyed on the filename
and every case would still pass.

WHY THEY SHARE test_guards_differential's XDIST GROUP, and not one of their own. A group pins its own tests to ONE worker; it does NOT stop a DIFFERENT group running beside it on another. These fixtures are visible to every process on the machine, and `test_guards_differential` asks the process table the same question about the same two guards. Measured 2026-09-09: run
concurrently, its anti-vacuity controls both went red --

    these guards answered identically on every case, so comparing them proves
    nothing: ['block_bash_write_to_running_script']
    these ports answered identically with their declared defect planted, so this
    file's green does not depend on that branch being right

-- and the same test passed in isolation (`-k test_the_differential_can_fail`, 1 passed in 316.07s). Sharing the group serialises them onto one worker, which costs about ten seconds against that file's five minutes.
"""

import os
import subprocess
import time

import pytest

from rediacc_hooks.tests import hookblocks, hookcases, test_guards_differential

# The fixtures spawn `sleep 8` and the case must be asked while it is alive. 0.3s is what the shell suite waited for the process to appear in the table.
SPAWN_SETTLE_S = 0.3

# GNU `timeout` is the whole point of the two blocks below -- they prove a hang is REALLY bounded by watching for its exit-124 convention, not by trusting a comment -- so it is shelled out to for real rather than reimplemented with
# `subprocess.run(timeout=...)`, which raises instead of returning 124. That
# binary does not ship on a bare macOS/BSD userland; `REDIACC_TIMEOUT_BIN` lets a workstation with GNU coreutils installed under a different name (Homebrew's `coreutils` package installs `gtimeout`) point this file at it.
TIMEOUT_BIN = os.environ.get("REDIACC_TIMEOUT_BIN", "timeout")


def path_json(path) -> str:
    return hookcases.path_json(str(path))


@pytest.mark.xdist_group(test_guards_differential.XDIST_GROUP)
def test_a_self_matching_pgrep_wait_really_does_hang():
    """THE PREMISE, MEASURED RATHER THAN ASSERTED.

    Every control around block_self_matching_pgrep proves the GUARD fires; none proved the hazard is real. This spawns the two loops for real and times them, so "a self-matching pgrep never exits" stops being a claim inherited from a comment.

    BOUNDED ON BOTH SIDES, deliberately. The deadlock case is capped at 3s, which is the whole reason this can live in a test suite at all -- an unbounded reproduction of a hang IS the hang. The remedy case is given the same 3s and must finish well inside it; if the bracket form ever started hanging too, the guard's advice would be worthless and this goes red.
    """
    block = hookblocks.Block("self-pgrep")
    mark = "selfmatch-probe-%d" % os.getpid()
    hung = subprocess.run(
        [
            TIMEOUT_BIN,
            "3",
            "bash",
            "-c",
            "until ! pgrep -f '%s' >/dev/null 2>&1; do sleep 0.2; done" % mark,
        ],
        capture_output=True,
        stdin=subprocess.DEVNULL,
        timeout=30,
        check=False,
    )
    block.note(
        2,
        "self-pgrep PREMISE: a self-matching wait really does hang (timed out at 3s)",
        ok=hung.returncode == 124,
        detail="the self-matching wait EXITED (rc %d), so the guard guards nothing"
        % hung.returncode,
    )
    remedy = subprocess.run(
        [
            TIMEOUT_BIN,
            "3",
            "bash",
            "-c",
            "until ! pgrep -f '[s]elfmatch-probe-absent-%d' >/dev/null 2>&1; do sleep 0.2; done"
            % os.getpid(),
        ],
        capture_output=True,
        stdin=subprocess.DEVNULL,
        timeout=30,
        check=False,
    )
    block.note(
        0,
        "self-pgrep CONTROL: the bracket-class remedy exits promptly",
        ok=remedy.returncode == 0,
        detail="the documented remedy hung too (rc %d); the advice is wrong" % remedy.returncode,
    )
    block.done()


@pytest.mark.xdist_group(test_guards_differential.XDIST_GROUP)
def test_block_edit_of_running_script(tmp_path):
    block = hookblocks.Block("running-script")
    fixture = tmp_path / "running-fixture.sh"
    fixture.write_text("#!/usr/bin/env bash\nsleep 8\n", encoding="utf-8")
    live = subprocess.Popen(
        ["bash", str(fixture)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
    )
    try:
        time.sleep(SPAWN_SETTLE_S)
        block.check(
            "check 2 guards/block_edit_of_running_script.py",
            path_json(fixture),
            "running-script: editing a .sh a live process is executing is refused",
        )
        block.check(
            "check 0 guards/block_edit_of_running_script.py",
            path_json(tmp_path / "idle-fixture.sh"),
            "running-script CONTROL: a .sh nothing is running is untouched",
        )
        block.check(
            "check 0 guards/block_edit_of_running_script.py",
            path_json(tmp_path / "running-fixture.ts"),
            "running-script CONTROL: a non-shell file is out of scope",
        )
        # `running-script CONTROL: no file_path names nothing` lives in hookcases.STATIC: its payload is the empty tool_input and its verdict does not depend on this fixture, so asserting it here as well would put the same label in the multiset twice. THE SAME WILDCARD BUG AS THE BASH-SIDE TWIN, found by sweeping the class rather than by being bitten a second time. Both guards
        # built their pattern by interpolating the basename RAW, so a one-letter name plus the shell suffix gave `[x].sh` -- and `.` is a wildcard, so for `b` that matches /bin/bash, every bash process alive.
        block.check(
            "check 0 guards/block_edit_of_running_script.py",
            path_json(tmp_path / "b.sh"),
            "running-script CONTROL: a one-letter name does not match /bin/bash",
        )
        # THE MENTION-VS-EXECUTION BYPASS, review-found on PR #579. A real incident hit mid-session: the stop-hook judge's own `claude -p '<huge prompt>'` process had this guard's OWN filename embedded in its prompt text, and the guard scored that as "executing" it -- blocking an edit with no interpreter anywhere near the file. Two fixtures reproduce both halves: a non-shell
        # process, and a shell process with the name buried in a late free-text argument rather than at an invocation position.
        #
        # `exec -a` RATHER THAN A TRAILING ARGUMENT, and the difference decides whether this control exists. `sleep 8 -- "prose..."` does not survive to the settle window at all: GNU sleep validates every operand as a NUMBER before sleeping, so a non-numeric trailing argument makes it exit immediately and the control then passes VACUOUSLY. `exec -a` renames argv[0] without touching
        # the numeric operand, so the process stays alive for real with
        # comm=sleep and the fixture name genuinely in argv.
        nonshell_name = "rs-nonshell-fixture-%d.sh" % os.getpid()
        nonshell = subprocess.Popen(
            ["bash", "-c", 'exec -a "$1" sleep 8', "--", nonshell_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
        )
        try:
            time.sleep(SPAWN_SETTLE_S)
            block.check(
                "check 0 guards/block_edit_of_running_script.py",
                path_json(tmp_path / nonshell_name),
                "running-script CONTROL: a NON-SHELL process carrying the name in argv "
                "is not running it",
            )
        finally:
            nonshell.kill()
            nonshell.wait()

        prose_name = "rs-prose-fixture-%d.sh" % os.getpid()
        # stdin is a PIPE so `read x` blocks and the process stays alive; `with` is what closes that pipe. Killing the child and leaving the descriptor to the garbage collector raises an unraisable ResourceWarning that pytest turns into a failure of this test, for a reason that has nothing to do with the guard.
        with subprocess.Popen(
            [
                "bash",
                "-c",
                "read x",
                "--",
                "a long prose payload mentioning %s deep inside it, not as an invocation"
                % prose_name,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.PIPE,
        ) as prose:
            try:
                time.sleep(SPAWN_SETTLE_S)
                block.check(
                    "check 0 guards/block_edit_of_running_script.py",
                    path_json(tmp_path / prose_name),
                    "running-script CONTROL: a SHELL process mentioning the name outside "
                    "argv position is not running it",
                )
            finally:
                prose.kill()
    finally:
        live.kill()
        live.wait()
    # CONTROL THAT MATTERS: once the process is gone the guard must go QUIET, or it would block every edit to any script that was ever run.
    block.check(
        "check 0 guards/block_edit_of_running_script.py",
        path_json(fixture),
        "running-script CONTROL: the guard goes quiet once the process exits",
    )
    block.done()


@pytest.mark.xdist_group(test_guards_differential.XDIST_GROUP)
def test_block_bash_write_to_running_script(tmp_path):
    """block_bash_write_to_running_script shipped 2026-08-27 with ZERO cases in either direction -- the only guard in the tree in that state, and the reason check:ci-hook-integrity was red."""
    block = hookblocks.Block("bash-write")
    bash_json = hookcases.bash_json
    fixture = tmp_path / "bw-fixture.sh"
    fixture.write_text("#!/usr/bin/env bash\nsleep 8\n", encoding="utf-8")
    # A decoy whose NAME CONTAINS the live fixture's, never run. Without it, nothing distinguishes "matches this process" from "appears in this process's name".
    (tmp_path / "myLongbw-fixture.sh").write_text(
        "#!/usr/bin/env bash\nsleep 8\n", encoding="utf-8"
    )
    (tmp_path / "b.sh").write_text("", encoding="utf-8")
    live = subprocess.Popen(
        ["bash", str(fixture)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
    )
    try:
        time.sleep(SPAWN_SETTLE_S)
        block.check(
            "check 2 guards/block_bash_write_to_running_script.py",
            bash_json("echo x > %s" % fixture),
            "bash-write: a redirect onto a live script is refused",
        )
        block.check(
            "check 2 guards/block_bash_write_to_running_script.py",
            bash_json("sed -i s/a/b/ %s" % fixture),
            "bash-write: an in-place edit of a live script is refused",
        )
        block.check(
            "check 2 guards/block_bash_write_to_running_script.py",
            bash_json("cp other.sh %s" % fixture),
            "bash-write: copying over a live script is refused",
        )
        # WRITE INTENT, not the filename. Every second command here names a .sh path;
        # blocking on the name alone is the over-matching that gets a guard switched off, and one session produced twelve instances of exactly that class.
        block.check(
            "check 0 guards/block_bash_write_to_running_script.py",
            bash_json("cat %s" % fixture),
            "bash-write CONTROL: READING a live script is not writing to it",
        )
        block.check(
            "check 0 guards/block_bash_write_to_running_script.py",
            bash_json("bash %s" % fixture),
            "bash-write CONTROL: RUNNING it is not writing to it",
        )
        block.check(
            "check 0 guards/block_bash_write_to_running_script.py",
            bash_json("grep -n sleep %s" % fixture),
            "bash-write CONTROL: grepping it is not writing to it",
        )
        block.check(
            "check 0 guards/block_bash_write_to_running_script.py",
            bash_json("echo x > %s/never-run.sh" % tmp_path),
            "bash-write CONTROL: a .sh nothing is running is untouched",
        )
        # THE TARGET NAME ITSELF BECAME A WILDCARD, round six and a different mechanism from the five before it. `pat` interpolated the basename RAW, so a one-letter name plus the shell suffix produced `[x].sh` -- and `.` is a regex wildcard, so for the letter `b` that matches /bin/bash, i.e. every bash process alive. Measured 2026-09-01.
        block.check(
            "check 0 guards/block_bash_write_to_running_script.py",
            bash_json("echo x > %s/b.sh" % tmp_path),
            "bash-write CONTROL: a one-letter name does not match /bin/bash",
        )
        # ROUND FIVE OF "A MENTION IS NOT A TARGET", measured 2026-09-01. Writing a plain markdown file was refused because its PROSE contained `check:ci-hook-worklist-suite -> <a live>.sh`: the ASCII arrow scored as a redirect and the path after it as the target. A real redirect's `>` follows whitespace, start-of-string or a digit.
        block.check(
            "check 0 guards/block_bash_write_to_running_script.py",
            bash_json(
                "cat > agent/NOTES.md <<MD\n"
                "the suite is check:ci-hook-worklist-suite -> %s\nMD" % fixture
            ),
            "bash-write CONTROL: an ASCII arrow in prose is not a redirect",
        )
        # The two redirect FORMS the arrow fix had to keep working. Neither was covered.
        block.check(
            "check 2 guards/block_bash_write_to_running_script.py",
            bash_json("echo x >> %s" % fixture),
            "bash-write: an APPEND onto a live script is refused",
        )
        block.check(
            "check 2 guards/block_bash_write_to_running_script.py",
            bash_json("foo 2> %s" % fixture),
            "bash-write: a NUMBERED stderr redirect is still a redirect",
        )
        # The guard header names `p.write_text(...)` as the idiom it exists for, and it caught that spelling while `open(path, "w").write(...)`, the commoner one, walked through its write-detector untouched. Verified missed 2026-08-27.
        block.check(
            "check 2 guards/block_bash_write_to_running_script.py",
            bash_json("python3 - <<PY\nopen('%s', 'w').write('x')\nPY" % fixture),
            "bash-write: open(path,w) in a heredoc is refused, not only write_text",
        )
        # Naming a live script in the CONTENT you write elsewhere is not writing to it. The broad scan got this wrong, and a guard that blocks correct commands is a guard people route around, which costs more than the block saves.
        block.check(
            "check 0 guards/block_bash_write_to_running_script.py",
            bash_json("printf '%%s' 'bash %s' > %s/other-target.sh" % (fixture, tmp_path)),
            "bash-write CONTROL: MENTIONING a live script while writing a different file",
        )
        # THE SAME DISTINCTION ON THE HEREDOC PATH, which is a different branch: the redirect above is caught by the precise grep, while a python heredoc falls to the broad scan that takes every .sh token in the command. That branch had no mention-control, so it refused three honest edits in a row on 2026-08-27.
        block.check(
            "check 0 guards/block_bash_write_to_running_script.py",
            bash_json(
                "python3 - <<PY\np = '%s/notes.py'\n"
                "open(p, 'w').write('docs: bash %s')\nPY" % (tmp_path, fixture)
            ),
            "bash-write CONTROL: a heredoc writing a .py that MENTIONS a live script",
        )
        # THE THIRD ROUND OF THE SAME CLASS, 2026-08-28. Not inside a .write() argument this time -- the mention text is ITSELF shaped like an assignment,
        # `ROUTE="./x.sh ..."`, because it is genuine bash SOURCE TEXT being written out
        # as data. Fixed by requiring a space on both sides of `=`: every
        # ruff-formatted real target assignment in this repo has one; a bash env-assignment never can.
        block.check(
            "check 0 guards/block_bash_write_to_running_script.py",
            bash_json(
                "python3 - <<PY\np = '%s/other-guard.py'\ns = open(p).read()\n"
                "s = s.replace('X', 'ROUTE=\".%s devbox exec\"')\n"
                "open(p, 'w').write(s)\nPY" % (tmp_path, "/" + str(fixture))
            ),
            "bash-write CONTROL: a bash-shaped assignment MENTION inside replacement text",
        )
        # And the hole that narrowing could have opened: when NO target position is identifiable, the broad scan must still fire. Without this the fix would trade a false positive for a silent miss, which is the worse of the two.
        block.check(
            "check 2 guards/block_bash_write_to_running_script.py",
            bash_json(
                "python3 - <<PY\nimport pathlib\n"
                "pathlib.Path(*['%s']).write_text('x')\nPY" % fixture
            ),
            "bash-write: unidentifiable target falls back to the broad scan",
        )
        # And the expensive one: `pgrep -af` matched a PEER SESSION whose long prompt merely contained a filename, so the guard reported a script as executing when no interpreter had it open. Only a SHELL running it counts.
        argv_only = subprocess.Popen(
            ["python3", "-c", "import sys,time; time.sleep(45)", str(tmp_path / "argv-only.sh")],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
        )
        try:
            block.check(
                "check 0 guards/block_bash_write_to_running_script.py",
                bash_json("echo x > %s/argv-only.sh" % tmp_path),
                "bash-write CONTROL: a NON-SHELL process carrying the name in argv is "
                "not running it",
            )
        finally:
            argv_only.kill()
            argv_only.wait()
        # A DECOY WHOSE NAME CONTAINS THE LIVE ONE. `pgrep -f` matches anywhere in a command line, so a bare basename matched by SUBSTRING: the candidate `ver.sh` matched a running `wslServer.sh`, and the guard reported VS Code's server as the job about to be corrupted. The pattern now anchors to a path boundary.
        block.check(
            "check 0 guards/block_bash_write_to_running_script.py",
            bash_json("echo x > %s/myLongbw-fixture.sh" % tmp_path),
            "bash-write CONTROL: a name CONTAINING the live one is not the live one",
        )
    finally:
        live.kill()
        live.wait()
    # THE CONTROL THAT MATTERS: liveness, not the filename. Without this the guard could be keyed on the name and every case above would still pass.
    block.check(
        "check 0 guards/block_bash_write_to_running_script.py",
        bash_json("echo x > %s" % fixture),
        "bash-write CONTROL: the guard goes quiet once the process exits",
    )
    block.done()

r"""Port of `.ci/scripts/test/gates/test-media-portable.sh`, retired in W7 P5.

`.ci/media/portable.sh`, the seams where this pipeline names a system tool that is spelled differently, or does not exist, off Linux.

WHY A SEAM MODULE NEEDS A GATE MORE THAN MOST CODE DOES. Its whole value is in the branch that never runs here. `stat -c %Y` works on this host, so does `nproc`, so does `sha256sum`; a test that only calls the seams on this machine proves that the GNU spelling still works, which nobody doubted, and says nothing at all about the fallbacks that are the reason the file exists. So
every seam is driven THREE ways: the platform spelling this host has, the fallback spelling with the first one hidden
from PATH, and the case where NOTHING answers, which must produce a named refusal
rather than an empty string. The third is the one that matters: the defect this module was written to close was `stat -c %Y` returning nothing into `$(( now - ))`, and "nothing" is what a fallback chain produces when its last link also fails silently.

THE FOURTH CASE IS THE ONE THAT KEEPS THE OTHERS TRUE. Seams do not decay by breaking, they decay by being BYPASSED: the next person writes `stat -c %Y` inline because it works on the machine in front of them, and portable.sh becomes a file that three call sites use and eleven do not. `test_no_unseamed_platform_tool_remains_in_this_folder` scans the whole folder and refuses any
un-seamed spelling, so the careless version is not available rather than merely discouraged.

THE SCAN IS REIMPLEMENTED, AND THAT IS THE INTERESTING PART OF THIS PORT. The twin spells it as a `grep -rnE` with an eleven-branch alternation, piped through three `grep -v` filters. This module runs the SAME eleven branches as one Python regex over the same files, with the same three exclusions, and the fifth case below is what makes the two agree rather than merely look alike:
it plants every one of the eleven spellings, requires each to be found, plants a COMMENT naming them and requires silence, and plants five near-miss portable forms and requires silence again. Both directions, on both spellings.

There is a house reason to prefer Python here beyond tidiness. `grep -E` on this host is ugrep 7.5.0, which returns SILENT FALSE ZEROS when `^` is alternated with a negated character class -- exactly the shape of the twin's `grep -vE '^[^:]+:[0-9]+:\s*#'` comment filter. A comment filter that quietly matched nothing would make the scan report the seam module's own explanations as
findings, which the twin's own control would catch; a filter that quietly matched EVERYTHING would suppress every finding, which nothing on the bash side is watching for. Python's `re` has no such behaviour, and the planted-spelling case pins it either way.

Nothing here needs docker, node, npm, nvcc, aws, ssh, a GPU or a network. The fallbacks are driven with scripted fakes on an emptied PATH, and the refusals with an emptied PATH and a meminfo path that points at nothing.

NO `xdist_group`. `fake_bin` mutates PATH on this process and restores it in a `finally`; every case owns its own `mktemp -d`, and the real `.ci/media` folder is only ever READ or copied out of.
"""

import re
import shutil
import stat

from rediacc_ci.tests.gates import harness, media_verify

MODULE = media_verify.MEDIA_DIR / "portable.sh"

# The digest of the four bytes "abc\n", which is what every arm below hashes. Written out rather than computed, because computing the expected value with the tool under test is the classic way a hash assertion agrees with itself no matter what it is measuring.
ABC_SHA256 = "edeaaff3f1774ad2888673770c6d64097e391bc362d7d6fb34982ddf0efd18cb"

# The twin's eleven-branch alternation, branch for branch and in the same order.
UNSEAMED = re.compile(
    r"\bnproc\b|\bsha256sum\b|\bshasum\b|stat -c|stat -f|grep -[a-zA-Z]*P|MemAvailable"
    r"|\bsed\b(\s+-[A-Za-z.]+)*\s+-i|\breadlink\b\s+-[A-Za-z]*f|\bdate\b\s+-[A-Za-z]*d"
)

# `^[^:]+:[0-9]+:\s*#` in the twin, applied to `<file>:<line>: <text>`. Here the file and line are not in the string at all, so the same claim is simply "the line, once stripped, starts with a #".
COMMENT = re.compile(r"^\s*#")


def probe_portable(gate, code: str) -> harness.RunResult:
    """Source ONLY portable.sh in a fresh bash and run `code`. Streams MERGED.

    FRESH, because `MEDIA_SHA256` is resolved at SOURCE time by a `command -v` probe: a fallback test has to source the module again with the emptied PATH in effect, not reuse the array an earlier source produced.

    THE COVERAGE PRELUDE IS SPLICED IN, and leaving it out was a measurement defect rather than a style slip. This file does not go through `media_run_module` -- it needs a shell that sources ONLY portable.sh -- so it never inherited the `MEDIA_COVERAGE_FILE` seam, and `.ci/media/coverage.sh` therefore reported portable.sh at 7 PERCENT while a 260-line gate test drove every seam in
    it three ways. That number was not a fact about the tests, it was a fact about the instrument. The prelude is empty when the variable is unset, so a normal run is unchanged, and the trace goes to descriptor 9 rather than onto the streams below.
    """
    if not MODULE.is_file():
        gate.log_fail("subject under test is missing: %s" % MODULE)
    script = "%s source '%s'; %s" % (media_verify._coverage_prelude(), MODULE, code)
    return harness.run([media_verify._BASH, "-c", script])


def write_exec(path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def unseamed_uses(directory) -> list[str]:
    """Every line under `directory` that names a platform tool directly, as `<file>:<n>: <text>`.

    An empty list is the invariant holding.

    WHAT IS DELIBERATELY NOT A FINDING, each for a stated reason:
      - portable.sh itself, which is where the real spellings are supposed to be;
      - comment lines, because the seams are explained by naming what they replace,
        and a scan that counted prose would force the explanations out of the file;
      - any line calling `_bridge_ssh`, whose argument is a command that runs ON THE
        BRIDGE VM. That host is Linux by construction and seaming its `sha256sum`
        would be a category error: the seam picks a spelling for THIS machine.
    """
    found = []
    for path in sorted(directory.rglob("*.sh")):
        if path.name == "portable.sh":
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if COMMENT.match(line) or "_bridge_ssh" in line:
                continue
            if UNSEAMED.search(line):
                found.append("%s:%d: %s" % (path, number, line))
    return found


def test_every_seam_answers_on_this_host(gate):
    gate.log_test("all five seams, using this host's own spellings")
    with harness.temp_dir() as d:
        (d / "f").write_text("abc\n", encoding="utf-8")

        result = probe_portable(gate, "\"${MEDIA_SHA256[@]}\" '%s/f' | cut -d' ' -f1" % d)
        if result.rc != 0:
            gate.log_fail("the sha256 seam failed on a host that has one: %s" % result.combined)
        gate.assert_eq(
            result.combined.strip(),
            ABC_SHA256,
            "the sha256 seam must produce the real digest of the bytes it was given",
        )

        result = probe_portable(gate, "media_file_size '%s/f'" % d)
        if result.rc != 0:
            gate.log_fail("media_file_size failed: %s" % result.combined)
        gate.assert_eq(
            result.combined.strip(),
            "4",
            "media_file_size must count bytes, and 'abc' plus a newline is four of them",
        )

        result = probe_portable(gate, "media_mtime '%s/f'" % d)
        if result.rc != 0:
            gate.log_fail("media_mtime failed: %s" % result.combined)
        mtime = result.combined.strip()
        if not mtime.isdigit():
            gate.log_fail("media_mtime printed '%s', which is not an epoch second" % mtime)
        if int(mtime) <= 1600000000:
            gate.log_fail(
                "media_mtime printed %s, which is before 2020 -- a file created a moment ago "
                "cannot be that old, so the seam is reporting a failure as a number" % mtime
            )
        gate.assertions += 2

        result = probe_portable(gate, "media_cpu_count")
        if result.rc != 0:
            gate.log_fail("media_cpu_count failed: %s" % result.combined)
        cpus = result.combined.strip()
        if not cpus.isdigit() or int(cpus) < 1:
            gate.log_fail("media_cpu_count printed '%s', which is not a count of processors" % cpus)
        gate.assertions += 1

        result = probe_portable(gate, "media_avail_mem_gb")
        if result.rc != 0:
            gate.log_fail("media_avail_mem_gb failed: %s" % result.combined)
        mem = result.combined.strip()
        if not mem.isdigit():
            gate.log_fail(
                "media_avail_mem_gb printed '%s', which is not a whole number of gigabytes" % mem
            )
        gate.assertions += 1
    gate.log_pass("all five seams answer correctly using this host's own spellings")


def stage_bsd_host(bindir) -> None:
    """A PATH that looks like macOS: no nproc, no sha256sum, and a REFUSING `stat`.

    Faking the refusal rather than simply omitting `stat` is what makes this a fallback test -- GNU stat exits 1 on `-f`, BSD stat exits 1 on `-c`, and the seam has to try the second AFTER the first fails rather than after it is absent.
    """
    write_exec(
        bindir / "stat",
        "#!/bin/bash\n"
        'case "${1:-}" in\n'
        "    -c*) echo \"stat: invalid option -- 'c'\" >&2; exit 1 ;;\n"
        '    -f)  fmt="$2"; shift 2 ;;\n'
        '    -f*) fmt="${1#-f}"; shift ;;\n'
        "    *)   exit 1 ;;\n"
        "esac\n"
        'case "$fmt" in\n'
        "    %m) echo 1700000000 ;;\n"
        "    %z) echo 4 ;;\n"
        "    *)  exit 1 ;;\n"
        "esac\n",
    )
    write_exec(
        bindir / "sysctl",
        "#!/bin/bash\n"
        '[ "${1:-}" = -n ] && [ "${2:-}" = hw.ncpu ] && { echo 11; exit 0; }\n'
        "exit 1\n",
    )
    write_exec(
        bindir / "shasum",
        "#!/bin/bash\n"
        "# Only the -a 256 spelling, because that is the only one the seam may use.\n"
        '[ "${1:-}" = -a ] && [ "${2:-}" = 256 ] || exit 1\n'
        "shift 2\n"
        'echo "%s  ${1:-}"\n' % ABC_SHA256,
    )


def test_the_bsd_fallbacks_are_reachable(gate):
    gate.log_test("every seam must reach its BSD spelling when the GNU one refuses or is absent")
    with harness.temp_dir() as d:
        (d / "f").write_text("abc\n", encoding="utf-8")
        # cut and bash are real; everything the seams reach for is either the scripted fake or deliberately absent. nproc, sha256sum and GNU stat are all gone from this PATH, which is the whole arrangement.
        with harness.fake_bin("+bash +cut +cat +chmod") as fake:
            stage_bsd_host(fake.dir)

            result = probe_portable(gate, "\"${MEDIA_SHA256[@]}\" '%s/f' | cut -d' ' -f1" % d)
            if result.rc != 0:
                gate.log_fail(
                    "the sha256 seam did not fall through to shasum: %s" % result.combined
                )
            gate.assert_eq(
                result.combined.strip(),
                ABC_SHA256,
                "the shasum fallback must produce the same digest as sha256sum",
            )

            result = probe_portable(gate, "media_mtime '%s/f'" % d)
            if result.rc != 0:
                gate.log_fail(
                    "media_mtime did not fall through to stat -f %%m: %s" % result.combined
                )
            gate.assert_eq(
                result.combined.strip(),
                "1700000000",
                "media_mtime must take the BSD stat's answer once the GNU form is refused",
            )

            result = probe_portable(gate, "media_file_size '%s/f'" % d)
            if result.rc != 0:
                gate.log_fail("media_file_size did not fall through: %s" % result.combined)
            gate.assert_eq(
                result.combined.strip(),
                "4",
                "media_file_size must take the BSD stat's answer once the GNU form is refused",
            )

            result = probe_portable(gate, "media_cpu_count")
            if result.rc != 0:
                gate.log_fail(
                    "media_cpu_count did not fall through to sysctl: %s" % result.combined
                )
            gate.assert_eq(
                result.combined.strip(),
                "11",
                "media_cpu_count must take sysctl's answer when nproc is absent",
            )
    gate.log_pass("every seam reaches its BSD spelling when the GNU one is absent or refuses")


def test_every_seam_refuses_out_loud_when_nothing_answers(gate):
    gate.log_test("with NOTHING on PATH, every seam must refuse BY NAME rather than answer ''")
    with harness.temp_dir() as d:
        (d / "f").write_text("abc\n", encoding="utf-8")
        # NOTHING but bash. No stat, no sha256sum, no shasum, no nproc, no sysctl, no wc.
        with harness.fake_bin("+bash"):
            result = probe_portable(gate, "\"${MEDIA_SHA256[@]}\" '%s/f'" % d)
            if result.rc == 0:
                gate.log_fail(
                    "the sha256 seam succeeded with no hashing tool at all; a caller would "
                    "have taken an empty hash for a real one"
                )
            gate.assertions += 1
            gate.assert_contains(
                result.combined, "no SHA-256 tool found", "the refusal must name what it looked for"
            )

            result = probe_portable(gate, "media_mtime '%s/f'" % d)
            if result.rc == 0:
                gate.log_fail(
                    "media_mtime succeeded with no stat at all -- this is the exact defect the "
                    "seam exists to close"
                )
            gate.assertions += 1
            gate.assert_contains(
                result.combined,
                "cannot read the modification time",
                "the refusal must say what it could not do",
            )

            result = probe_portable(
                gate, "MEDIA_MEMINFO='%s/no-such-meminfo'; media_avail_mem_gb" % d
            )
            if result.rc == 0:
                gate.log_fail(
                    "media_avail_mem_gb succeeded with no meminfo, so the render pool would "
                    "schedule against a fabricated number"
                )
            gate.assertions += 1
            gate.assert_contains(
                result.combined,
                "no portable equivalent of MemAvailable",
                "the refusal must state the limitation rather than guess a number",
            )

            # THE ONE SEAM THAT GUESSES, and it says so. One render at a time is a correct if slow answer; the asymmetry with the four above is deliberate and is documented at the seam.
            result = probe_portable(gate, "media_cpu_count")
            if result.rc != 0:
                gate.log_fail("media_cpu_count must not fail, it must fall back to 1")
            gate.assertions += 1
            gate.assert_contains(
                result.combined, "1", "media_cpu_count falls back to one processor"
            )
            gate.assert_contains(
                result.combined, "assuming 1", "and it says on stderr that it is guessing"
            )
    gate.log_pass("every seam that cannot answer refuses by name, and the one that guesses says so")


def test_no_unseamed_platform_tool_remains_in_this_folder(gate):
    gate.log_test("no file in .ci/media may name a platform tool outside the seam module")
    found = unseamed_uses(media_verify.MEDIA_DIR)
    if found:
        gate.log_fail(
            "un-seamed platform tools in .ci/media:\n%s\nRoute each through "
            ".ci/media/portable.sh, or, if it genuinely runs on another machine, say so at "
            "the call site the way the bridge's remote hash does." % "\n".join(found)
        )
    gate.assertions += 1
    gate.log_pass(
        "no file in .ci/media names nproc, sha256sum, shasum, stat -c, stat -f, grep -P, "
        "MemAvailable, sed -i, readlink -f or date -d outside the seam module"
    )


def test_the_unseamed_scan_can_fail(gate):
    """CONTROL, in both directions.

    A pattern-based invariant is the shape that goes quiet most easily: change a character class and it matches nothing while still reporting success. Plant one of each spelling in a COPY of the folder and require every one to be found, then confirm the scan is silent on the copy once they are removed.
    """
    gate.log_test("CONTROL: the scan must find every planted spelling and refuse none in use")
    with harness.temp_dir() as d:
        media = d / "media"
        media.mkdir()
        for item in sorted(media_verify.MEDIA_DIR.glob("*.sh")):
            shutil.copy2(item, media / item.name)

        # The clean copy must be silent FIRST, or a finding below would prove nothing.
        if unseamed_uses(media):
            gate.log_fail("the scan already reports a finding on an unmodified copy of the folder")
        gate.assertions += 1

        spellings = (
            'x="$(nproc)"',
            'h="$(sha256sum f)"',
            'h="$(shasum -a 256 f)"',
            't="$(stat -c %Y f)"',
            't="$(stat -f %m f)"',
            'g="$(grep -oP "x" f)"',
            'm="$(awk "/MemAvailable/" /proc/meminfo)"',
            'sed -i "s/a/b/" f',
            'sed -E -i "s/a/b/" f',
            'p="$(readlink -f f)"',
            'd="$(date -d @123 +%s)"',
        )
        for index, spelling in enumerate(spellings, start=1):
            planted = media / ("planted-%d.sh" % index)
            planted.write_text("%s\n" % spelling, encoding="utf-8")
            if not unseamed_uses(media):
                gate.log_fail("the scan did not notice the planted spelling: %s" % spelling)
            gate.assertions += 1
            planted.unlink()

        # A COMMENT MUST NOT BE A FINDING, or the seam module's own explanations become unwritable and the next reader loses the reason each seam exists.
        commented = media / "commented.sh"
        commented.write_text(
            "# this comment mentions nproc and sha256sum and stat -c %Y\n", encoding="utf-8"
        )
        if unseamed_uses(media):
            gate.log_fail(
                "the scan treated a comment as a finding, which would force the seams' own "
                "prose out of the folder"
            )
        gate.assertions += 1
        commented.unlink()

        # THE OTHER DIRECTION, and the one an added pattern breaks. Every spelling below is POSIX and works on both platforms, and three of them sit one character away
        # from a pattern above: `date -u` next to `date -d`, `sed -n` next to `sed -i`,
        # `readlink` bare next to `readlink -f`. A regex widened carelessly starts refusing these, the folder goes red for code that is already correct, and the next person's fix is to delete the scan. `.ci/media/tutorials.sh` really does call `date -u +%Y...` and `.ci/media/teaser.sh` really does call `sed -n`, so this is not hypothetical.
        for near in (
            'stamp="$(date -u +%Y%m%dT%H%M%SZ)"',
            'now="$(date +%s)"',
            'y="$(sed -n "s/x//p" f)"',
            'p="$(readlink f)"',
            'n="$(grep -c x f)"',
        ):
            probe = media / "portable-form.sh"
            probe.write_text("%s\n" % near, encoding="utf-8")
            findings = unseamed_uses(media)
            if findings:
                gate.log_fail(
                    "the scan refused a spelling that is portable and in use: %s\n%s"
                    % (near, "\n".join(findings))
                )
            gate.assertions += 1
            probe.unlink()
    gate.log_pass(
        "the un-seamed scan finds all %d spellings when planted, ignores a comment that names "
        "them, and stays silent on the five portable forms this folder actually uses"
        % len(spellings)
    )

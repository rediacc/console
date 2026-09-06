#!/bin/bash
# The seams where this pipeline touches a NON-PORTABLE system tool, in one place.
#
# WHY THIS FILE EXISTS. The media pipeline is the one part of the tooling that is staying
# bash (it drives private/generative and private/growth, gitignored repositories rather
# than submodules, so it cannot be ported with the rest). Everything else gets its
# portability from Python's standard library; this folder has to get it by hand, and the
# way that goes wrong is not dramatic. Nobody writes `stat -c` believing it is portable.
# They write it because they are on Linux, it works, and the file is 400 lines long by the
# time anybody looks. The fix is not to be careful; it is to make the careless spelling
# UNAVAILABLE, which is what .ci/scripts/test/gates/test-media-portable.sh does by
# refusing an un-seamed use anywhere in this folder.
#
# WHAT IS AND IS NOT CLAIMED HERE. This does NOT make the media pipeline run on macOS.
# _tutorial_auto_jobs reads /proc/meminfo, the render pool assumes a Linux GPU host, and
# the bridge helpers assume libvirt. What it does is stop the EASY half of that gap from
# growing: four primitives that every platform has under a different name, behind four
# names that do not change. The hard half is a decision somebody has to make on purpose,
# and it is documented at each seam rather than hidden behind a fallback that half works.
#
# EACH SEAM REFUSES RATHER THAN GUESSES. A seam whose tools are all missing returns a
# failure with the names it looked for, because the alternative is what the un-seamed code
# already did: `stat -c %Y` on BSD prints usage to stderr, exits 1, and the caller's
# arithmetic then evaluates an empty string. That reads as "the file is from 1970", not as
# an error, which is how a guard silently stops guarding.
#
# SOURCED, NEVER EXECUTED. media-entry.sh sources it first, so every other module has the
# seams in scope regardless of source order.

# media_sha256 -- the SHA-256 command as an ARRAY, not a function.
#
# AN ARRAY BECAUSE ONE CALLER IS `find ... -exec`. bridge.sh hashes the CLI source tree
# with `-exec <cmd> {} +`, and find execs a real program: a shell function is not visible
# to it, so a function-shaped seam would have forced that one site to stay un-seamed, and
# one un-seamed site is how the whole invariant gets read as advisory.
#
# THE OUTPUT FORMAT IS PART OF THE CONTRACT. Both spellings print `<64 hex>  <path>` with
# two spaces, and every caller either pipes the lot into another hash or takes field 1, so
# the two are interchangeable. shasum is the BSD/macOS spelling and ships with perl.
#
# NOT USED FOR REMOTE HASHES. bridge.sh runs `sha256sum` inside an ssh command; that runs
# on the bridge VM, which is Linux by construction, and rewriting it to a local seam would
# be a category error. test-media-portable.sh's scan excludes quoted remote commands for
# exactly this reason and says so.
if command -v sha256sum >/dev/null 2>&1; then
    MEDIA_SHA256=(sha256sum)
elif command -v shasum >/dev/null 2>&1; then
    MEDIA_SHA256=(shasum -a 256)
else
    # An array whose first element is a program that does not exist would fail with
    # "command not found" and a caller would see an empty hash, which compares unequal to
    # everything and silently rebuilds the world on every run. Name the problem instead.
    MEDIA_SHA256=(media_no_sha256)
fi
media_no_sha256() {
    echo "media: no SHA-256 tool found (looked for sha256sum, then shasum)" >&2
    return 127
}

# media_mtime <file> -- modification time in epoch seconds, on stdout.
#
# GNU coreutils spells it `stat -c %Y`; BSD and macOS spell it `stat -f %m`. Trying the
# GNU form first and the BSD form second is what the one site in tutorials.sh already did
# by hand; teaser.sh's copy did NOT, and its arithmetic `$(($(date +%s) - $(stat -c %Y ...)))`
# would have died on a BSD host and, worse, on a log file that vanished between the glob
# and the stat.
#
# A MISSING FILE IS AN ERROR, NOT A ZERO. Returning 0 for "cannot tell" is how teaser.sh's
# in-flight guard would decide that a live pass finished 56 years ago and let a second
# pass rebuild the slug it is holding. Callers that genuinely want a default say so.
media_mtime() {
    local file="$1" out
    if out="$(stat -c %Y "$file" 2>/dev/null)" && [ -n "$out" ]; then
        printf '%s\n' "$out"
        return 0
    fi
    if out="$(stat -f %m "$file" 2>/dev/null)" && [ -n "$out" ]; then
        printf '%s\n' "$out"
        return 0
    fi
    echo "media_mtime: cannot read the modification time of $file (tried stat -c %Y, then stat -f %m)" >&2
    return 1
}

# media_cpu_count -- usable CPUs, on stdout.
#
# `nproc` is coreutils and absent on macOS; `sysctl -n hw.ncpu` is the BSD spelling. The
# final fallback is 1 rather than an error, and that asymmetry with media_mtime is
# deliberate: the only caller divides by this to pick a render concurrency, and one render
# at a time is a correct if slow answer, whereas a wrong file timestamp is a wrong
# decision. A seam should fail where failing is safer than guessing and not otherwise.
media_cpu_count() {
    local n
    if n="$(nproc 2>/dev/null)" && [ -n "$n" ]; then
        printf '%s\n' "$n"
        return 0
    fi
    if n="$(sysctl -n hw.ncpu 2>/dev/null)" && [ -n "$n" ]; then
        printf '%s\n' "$n"
        return 0
    fi
    echo "media_cpu_count: neither nproc nor sysctl answered; assuming 1" >&2
    printf '1\n'
}

# media_avail_mem_gb -- available (not free, not total) memory in whole GB, on stdout.
#
# /proc/meminfo IS THE PORTABILITY LIMIT OF THIS PIPELINE and this seam does not pretend
# otherwise. MemAvailable is a Linux kernel estimate with no BSD equivalent worth the
# name: `vm_stat` on macOS reports page counts whose "available" is a different quantity,
# and mapping one onto the other would produce a number that looks right and schedules
# renders that OOM. So the fallback is a REFUSAL with the reason, and the caller decides.
#
# The seam still earns its place: it is the one line to change if that decision is ever
# made, and it puts the limitation somewhere a reader will find it rather than inside an
# awk expression halfway down the render pool.
# THE PATH IS A VARIABLE SO THE REFUSAL CAN BE DRIVEN. /proc cannot be made unreadable in
# a test, and a refusal branch nobody has watched fire is a branch nobody has checked --
# which for this one means the pipeline would discover its own limitation in production.
# Overriding it in production would be meaningless rather than dangerous: the awk below
# only understands MemAvailable.
MEDIA_MEMINFO="${MEDIA_MEMINFO:-/proc/meminfo}"
media_avail_mem_gb() {
    local gb
    if [ -r "$MEDIA_MEMINFO" ]; then
        # THE DIVISION STAYS INSIDE awk, and it is not arbitrary. This is lifted verbatim
        # from the expression that stood in the render pool, and the pool's gate test
        # injects a scripted `awk` as its ONE seam onto the machine's memory (/proc cannot
        # be staged). Moving the arithmetic out into the shell would have left that fake
        # printing kilobytes into a shell divide, silently answering 0 GB, and the test
        # would have failed for a reason that had nothing to do with what it asserts.
        gb="$(awk '/^MemAvailable:/ {print int($2/1024/1024); exit}' "$MEDIA_MEMINFO")"
        if [ -n "$gb" ]; then
            printf '%s\n' "$gb"
            return 0
        fi
    fi
    echo "media_avail_mem_gb: $MEDIA_MEMINFO is unreadable and there is no portable equivalent of MemAvailable" >&2
    return 1
}

# media_file_size <file> -- size in bytes, on stdout.
#
# `stat -c%s` is GNU, `stat -f%z` is BSD, and `wc -c` is POSIX and works everywhere but
# reads the whole file, which for a 300 MB rendered mp4 is real I/O. Hence the order: the
# cheap platform spellings first, the portable one as the answer of last resort rather
# than the answer.
#
# `wc -c <file` and not `wc -c file`: with a redirect wc prints the number alone, with a
# path it prints the number AND the path, and the manifest this feeds records the size as
# a bare integer.
media_file_size() {
    local file="$1" out
    if out="$(stat -c%s "$file" 2>/dev/null)" && [ -n "$out" ]; then
        printf '%s\n' "$out"
        return 0
    fi
    if out="$(stat -f%z "$file" 2>/dev/null)" && [ -n "$out" ]; then
        printf '%s\n' "$out"
        return 0
    fi
    if out="$(wc -c <"$file" 2>/dev/null)" && [ -n "$out" ]; then
        printf '%s\n' "${out// /}"
        return 0
    fi
    echo "media_file_size: cannot size $file (tried stat -c%s, stat -f%z, then wc -c)" >&2
    return 1
}

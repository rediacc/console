#!/usr/bin/env bash
# The gate toolchain: load the pins, and acquire a tool AT the pin.
#
# WHY A GATE ACQUIRES ITS OWN TOOL. Before this, three different mechanisms
# installed the same formatter -- the workflow (curl | sh, unpinned), the image
# (go install @latest), and the gate script (whatever was on PATH) -- which is
# precisely WHY there were three versions. .ci/scripts/security/actionlint.sh
# already had the right answer for one tool; this generalises it.
#
# The rule: a binary already on PATH is used ONLY if its version equals the pin.
# That is what makes this work on a developer's host, where nobody controls PATH
# and a stale shellcheck 0.9.0 would otherwise silently decide the verdict.

# --- loading -----------------------------------------------------------------

toolchain_pins_file() {
    local here
    here="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
    printf '%s/.devcontainer/toolchain.env' "$here"
}

toolchain_load() {
    local f
    # IDEMPOTENT, and not merely as a courtesy. constants.sh sources this same
    # file and then re-declares some keys `readonly` for its existing consumers;
    # a second unguarded source then fails with "readonly variable" on every one
    # of them. Load once, and say nothing the second time.
    [[ -n "${REDIACC_TOOLCHAIN_LOADED:-}" ]] && return 0
    f="$(toolchain_pins_file)"
    [[ -r "$f" ]] || {
        echo "toolchain: pins file missing or unreadable: $f" >&2
        return 1
    }
    set -a
    # shellcheck disable=SC1090  # path is computed; it is this repo's own pins file
    . "$f"
    set +a
    REDIACC_TOOLCHAIN_LOADED=1
}

# The ONLY lines that are valid KEY=value pins. Used both to feed $GITHUB_ENV
# (which rejects comment lines outright, so `cat` would break the job) and by the
# gate to enumerate what is pinned.
toolchain_pairs() {
    grep -E '^[A-Z][A-Z0-9_]*=' "$(toolchain_pins_file)"
}

toolchain_keys() {
    toolchain_pairs | cut -d= -f1
}

# --- version probing ---------------------------------------------------------
#
# EVERY TOOL PRINTS ITS VERSION DIFFERENTLY, and a normaliser that silently
# yields "" would make a comparison of ""=="" pass -- vacuity inside the very
# check meant to prevent it. So each probe is explicit, and the caller asserts
# the result is non-empty and starts with a digit.
#
#   - shfmt       v3.13.1
#   - shellcheck  (multi-line banner) ... version: 0.9.0
#   - ruff        ruff 0.16.1
#   - actionlint  1.7.12
#   - go          go version go1.26.4 linux/arm64
#   - node        v22.23.2
#   - uv          uv 0.12.10
#   - pytest      pytest 9.1.1
#
# (the leading dashes matter: a comment whose first word is the name of a linter
# is parsed by that linter as a DIRECTIVE, and this table broke its own gate)

toolchain_probe_version() {
    local tool="$1" bin="${2:-$1}" out=""
    case "$tool" in
        shfmt) out="$("$bin" --version 2>/dev/null | head -1)" ;;
        shellcheck) out="$("$bin" --version 2>/dev/null | awk -F': *' '/^version:/ {print $2}')" ;;
        ruff) out="$($bin --version 2>/dev/null | awk '{print $2}')" ;;
        actionlint) out="$("$bin" --version 2>/dev/null | head -1)" ;;
        go) out="$("$bin" version 2>/dev/null | awk '{print $3}')" ;;
        node) out="$("$bin" --version 2>/dev/null)" ;;
        # The Python pair. Same "name version" shape as ruff, and probed the
        # same way -- $bin unquoted so a resolver may hand back a multi-word
        # runner (`uv tool run pytest`) rather than a single path, which is how
        # pytest exists at all on a host with no pip.
        uv) out="$($bin --version 2>/dev/null | awk '{print $2}')" ;;
        pytest) out="$($bin --version 2>/dev/null | head -1 | awk '{print $2}')" ;;
        *) return 2 ;;
    esac
    # Strip a leading v or go, then keep the leading dotted-numeric run.
    out="${out#v}"
    out="${out#go}"
    out="$(printf '%s' "$out" | grep -oE '^[0-9]+(\.[0-9]+)*' || true)"
    [[ -n "$out" ]] || return 1
    printf '%s' "$out"
}

toolchain_pin_for() {
    local tool="$1" key
    # LOAD FIRST. Sourcing this library does not populate the pins, so a caller
    # that reached straight for a pin used to get "" back WITH RETURN CODE 0 --
    # and an empty version then travelled into a download URL. Measured
    # 2026-08-26 on a fresh shell:
    #   .../releases/download/v/shellcheck-v.linux.aarch64.tar.xz  -> curl 404
    # The 404 names GitHub, not the missing pin, which is the wrong problem to
    # go debugging. toolchain_load is idempotent, so this is free after the
    # first call.
    toolchain_load || return 2
    case "$tool" in
        shfmt) key=SHFMT_VERSION ;;
        shellcheck) key=SHELLCHECK_VERSION ;;
        ruff) key=RUFF_VERSION ;;
        actionlint) key=ACTIONLINT_VERSION ;;
        go) key=GO_VERSION ;;
        node) key=NODE_VERSION ;;
        uv) key=UV_VERSION ;;
        pytest) key=PYTEST_VERSION ;;
        *) return 2 ;;
    esac
    printf '%s' "${!key:-}"
}

# --- the question every gate asks --------------------------------------------
#
# Returns 0 and echoes the binary to use when PATH already has the pinned
# version; returns 1 and explains otherwise. Deliberately does NOT install:
# acquisition differs per tool and per lane, and a library that shells out to a
# package manager as a side effect of a version check is a library nobody trusts.

toolchain_check() {
    local tool="$1" pin actual bin
    pin="$(toolchain_pin_for "$tool")" || {
        echo "toolchain: no pin defined for '$tool'" >&2
        return 2
    }
    [[ -n "$pin" ]] || {
        echo "toolchain: pin for '$tool' is empty -- did toolchain_load run?" >&2
        return 2
    }
    bin="$(command -v "$tool" 2>/dev/null)" || {
        echo "toolchain: $tool is not on PATH (pinned at $pin)" >&2
        return 1
    }
    actual="$(toolchain_probe_version "$tool" "$bin")" || {
        echo "toolchain: could not read a version from '$tool --version' -- refusing to assume it matches $pin" >&2
        return 1
    }
    # NODE_VERSION is a MAJOR, not a full version: compare only that field.
    if [[ "$tool" == node ]]; then
        [[ "${actual%%.*}" == "$pin" ]] || {
            echo "toolchain: node major ${actual%%.*} != pinned $pin (found $actual at $bin)" >&2
            return 1
        }
    elif [[ "$actual" != "$pin" ]]; then
        echo "toolchain: $tool $actual != pinned $pin (at $bin)" >&2
        return 1
    fi
    printf '%s' "$bin"
}

# --- CLI ---------------------------------------------------------------------
#
# ONE implementation, run in all three lanes. The repo is bind-mounted into the
# devbox at its identical host path, so the container runs THIS file rather than
# a copy baked into the image -- a copy is a second thing to drift, which is the
# disease this whole file treats.
#
#   toolchain.sh --report   what each lane actually has, next to the pin
#   toolchain.sh --verify   exit 1 if any pinned tool is absent or mismatched
#   toolchain.sh --env      the KEY=value lines only, safe for $GITHUB_ENV
#
# `--env` exists because $GITHUB_ENV rejects anything that is not KEY=value:
# `cat toolchain.env >> "$GITHUB_ENV"` would feed it this file's comments and
# fail the job.

toolchain_lane() {
    if [[ -n "${GITHUB_ACTIONS:-}" ]]; then
        printf 'ci'
    elif [[ "${REDIACC_NPM_RUNTIME:-host}" == devbox || -f /.dockerenv ]]; then
        printf 'devbox'
    else
        printf 'host'
    fi
}

toolchain_report() {
    local strict="${1:-}" tool pin actual status rc=0
    toolchain_load || return 2
    printf 'lane: %s\n\n' "$(toolchain_lane)"
    printf '  %-11s %-9s %-15s %s\n' tool pinned actual status
    # uv and pytest are pinned and probeable (see toolchain_pin_for) but are
    # deliberately NOT in this loop. --verify returns non-zero on any MISMATCH,
    # and it runs in lanes that have no business owning a Python toolchain; a
    # host without uv would start failing a check it passed yesterday, for a
    # tool it is not being asked to have. .ci/bootstrap.sh --check and
    # `.ci/bootstrap.sh doctor` are where those two are reported, and they are
    # the thing that can also FIX the answer.
    for tool in shfmt shellcheck ruff actionlint go node; do
        pin="$(toolchain_pin_for "$tool")"
        if actual="$(toolchain_probe_version "$tool" 2>/dev/null)"; then :; else actual="absent"; fi
        if toolchain_check "$tool" >/dev/null 2>&1; then
            status="ok"
        else
            status="MISMATCH"
            rc=1
        fi
        printf '  %-11s %-9s %-15s %s\n' "$tool" "$pin" "$actual" "$status"
    done
    [[ "$strict" == "--verify" ]] || return 0
    return "$rc"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    case "${1:---report}" in
        --report) toolchain_report ;;
        --verify) toolchain_report --verify ;;
        --env) toolchain_pairs ;;
        *)
            echo "usage: toolchain.sh [--report|--verify|--env]" >&2
            exit 2
            ;;
    esac
fi

# --- acquisition -------------------------------------------------------------
#
# toolchain_check only ANSWERS a question; this gets the tool. Generalised from
# .ci/scripts/security/actionlint.sh, which already did exactly this for one
# tool. A PATH binary at the pin always wins, so a developer's own install is
# honoured and CI does not re-download on every invocation.
#
# TWO ACQUISITION MODELS, chosen per tool by what the upstream actually offers:
#
#   go install @vX  (shfmt) -- Go verifies the module against its checksum
#       database, which is a stronger guarantee than a hash we recorded
#       ourselves. shfmt publishes no checksums file at all, so this is also the
#       only verified option available for it.
#   download + recorded sha256 (shellcheck) -- a prebuilt Haskell binary. The
#       hashes live in .ci/config/constants.sh with their provenance stated.

# The SHA256 pins live in .ci/config/constants.sh (the Dockerfile has no use for
# them, so they are not in toolchain.env). A gate script may have sourced only
# THIS file, so load them on demand rather than assuming the caller did -- the
# first version did assume, and acquisition failed with a "no checksum for
# aarch64" error on the very lane it exists to serve.
#
# (Note the rewrap: a comment line whose FIRST word is a linter's name is parsed
# by that linter as a DIRECTIVE. This is the third time in one session that a
# comment about shellcheck broke the shellcheck gate.)
_toolchain_need_checksums() {
    [[ -n "${SHELLCHECK_SHA256_LINUX_X86_64:-}${SHFMT_SHA256_LINUX_AMD64:-}" ]] && return 0
    local c
    c="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)/.ci/config/constants.sh"
    # shellcheck source=/dev/null
    [[ -r "$c" ]] && . "$c" 2>/dev/null
    return 0
}

toolchain_cache_dir() {
    printf '%s/rediacc-toolchain' "${CI_TEMP:-${RUNNER_TEMP:-${TMPDIR:-/tmp}}}"
}

# PORTABLE sha256, because macOS HAS NO sha256sum. Both download helpers below
# verified with a bare `sha256sum`, which on a Mac is "command not found" -- so
# the `|| { checksum MISMATCH }` arm fired, printed a mismatch that had not
# happened, and the tool was refused for a reason that was not true. A verifier
# that cannot run must not read as a verifier that failed.
#
# This was the THIRD copy of this shim in the repo. It is now the SECOND, and
# the count is written down rather than left implicit because it is the number
# that tells the next reader whether the pattern is shrinking. The remaining
# sibling is _sha256sum in .ci/lib/local-common.sh:37, which is not sourceable
# from here: it pulls in the whole local-loop logging apparatus, and this
# library is sourced by gates that must stay cheap and side-effect-free.
#
# The third copy, _sha256sum_portable in .ci/lib/find-port.sh, is GONE as of
# W7 phase 1: that file now delegates to rediacc_ci.core.ports, and hashlib
# has no macOS branch to write. That is the whole argument for the port in one
# line -- the portability shim existed only because bash has no hash function.
#
# Absent BOTH tools this returns non-zero rather than silently succeeding, so
# the caller's `||` arm still fires -- but the message below says which of the
# two situations it is.
_toolchain_sha256sum() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$@"
    elif command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "$@"
    else
        echo "toolchain: no sha256 tool on PATH (need sha256sum or shasum) -- cannot verify a download" >&2
        return 1
    fi
}

# THE OS, DERIVED. Not the literal string `linux`, which is what both download
# URLs below used to carry while deriving only the ARCH from uname. On an arm64
# Mac that was not a 404, which is the part that made it dangerous: uname -m
# says arm64, the ARM64 checksum is present and matches, so a LINUX binary
# downloads, VERIFIES, gets chmod +x, and fails much later with "cannot execute
# binary file" from a gate that has no idea it installed another OS's tool.
#
# Lowercase because that is the spelling both upstreams use in their asset
# names (shfmt_v3.13.1_darwin_arm64, shellcheck-v0.10.0.darwin.aarch64.tar.xz);
# the callers uppercase it to build the checksum variable name.
_toolchain_os() {
    case "$(uname -s)" in
        Linux) printf 'linux' ;;
        Darwin) printf 'darwin' ;;
        *)
            echo "toolchain: unsupported OS '$(uname -s)' -- no pinned build of this tool exists for it" >&2
            return 1
            ;;
    esac
}

_toolchain_download_shfmt() {
    _toolchain_need_checksums
    local want="$1" cache="$2" bin="$3" os osk arch sha sha_var url tmp
    os="$(_toolchain_os)" || return 1
    osk="$(printf '%s' "$os" | tr '[:lower:]' '[:upper:]')"
    case "$(uname -m)" in
        x86_64 | amd64) arch=amd64 ;;
        aarch64 | arm64) arch=arm64 ;;
        *)
            echo "toolchain: no pinned shfmt checksum for $(uname -m); add one rather than downloading unverified" >&2
            return 1
            ;;
    esac
    # The checksum variable is now keyed by OS as well as arch, because the URL
    # is. Only the LINUX_* pair exists in constants.sh today, so a Mac lands in
    # the refusal below -- which is the correct outcome and a strict improvement
    # on the previous one, where a Linux binary was installed and pronounced
    # verified. The message names the constant to add rather than the arch.
    sha_var="SHFMT_SHA256_${osk}_$(printf '%s' "$arch" | tr '[:lower:]' '[:upper:]')"
    sha="${!sha_var:-}"
    [[ -n "$sha" ]] || {
        echo "toolchain: no shfmt checksum for ${os}/${arch} -- define ${sha_var} in .ci/config/constants.sh (and source it) rather than downloading unverified" >&2
        return 1
    }
    mkdir -p "$cache"
    url="https://github.com/mvdan/sh/releases/download/v${want}/shfmt_v${want}_${os}_${arch}"
    # A PRIVATE TEMP PER PROCESS, NOT A SHARED `$bin.tmp`. Every caller that
    # misses the cache lands here at once -- the pytest suite runs under xdist
    # with 8 workers, and several of its modules shell out to gates that acquire
    # shfmt -- and a single fixed temp path turns that into data corruption.
    # Measured 2026-09-16 with 8 concurrent `toolchain_acquire shfmt` into a cold
    # cache: SEVEN of the eight failed. `curl -o` truncates, so they interleave
    # writes into ONE inode; the winner's `mv` then renames that inode out from
    # under the losers, whose checksum step reads a path that no longer exists
    # and reports "checksum MISMATCH -- refusing to install" with an EMPTY
    # `actual`. A RACE THAT ACCUSES THE DOWNLOAD OF BEING TAMPERED WITH is the
    # most misleading message this file could print. Worse, the losers' curls
    # keep writing into the now-installed inode, so `$bin` can be a torn binary
    # that is already in place and +x -- which is how CI job 104650234908 got
    # `shfmt.sh: line 63: .../shfmt: cannot execute`, from a gate whose tool had
    # been "successfully installed".
    #
    # mktemp gives each process its own file, so the only shared operation left
    # is the rename -- atomic, and of a fully verified file. Redundant parallel
    # downloads are the cost, and they are cheap next to a corrupt toolchain.
    tmp="$(mktemp "$cache/shfmt.XXXXXXXX")" || return 1
    curl -fsSL --max-time 180 --retry 3 --retry-delay 5 -o "$tmp" "$url" || {
        echo "toolchain: could not download shfmt from $url" >&2
        rm -f "$tmp"
        return 1
    }
    echo "${sha}  ${tmp}" | _toolchain_sha256sum -c - >/dev/null 2>&1 || {
        echo "toolchain: shfmt checksum MISMATCH -- refusing to install" >&2
        echo "  expected $sha" >&2
        echo "  actual   $(_toolchain_sha256sum "$tmp" | cut -d' ' -f1)" >&2
        rm -f "$tmp"
        return 1
    }
    # 755 EXPLICITLY, not `chmod +x`. mktemp creates at 600, so `+x` would have
    # yielded 700 where the old umask-dependent path yielded 755 -- a difference
    # nothing here would notice until another user shared the cache.
    chmod 755 "$tmp" && mv "$tmp" "$bin" || {
        rm -f "$tmp"
        return 1
    }
    printf '%s' "$bin"
}

_toolchain_acquire_shfmt() {
    local want="$1" cache bin
    cache="$(toolchain_cache_dir)/shfmt-$want"
    bin="$cache/shfmt"
    [[ -x "$bin" ]] && {
        printf '%s' "$bin"
        return 0
    }
    # NO GO? DOWNLOAD THE RELEASE BINARY. The CI Static lane is a bare checkout
    # with no Go toolchain, so a Go-only acquisition simply cannot run there --
    # and the unpinned `curl webi.sh/shfmt | sh` this replaced is what used to
    # cover that lane.
    if ! command -v go >/dev/null 2>&1; then
        _toolchain_download_shfmt "$want" "$cache" "$bin"
        return $?
    fi
    mkdir -p "$cache"
    # GOTOOLCHAIN=local: without it a tool's own go directive can drag in a
    # different toolchain and 404 on a runner without network to fetch it.
    # A FAILED `go install` FALLS BACK TO THE DOWNLOAD, it does not end the
    # attempt. The branch above chooses this path on `command -v go`, i.e. on
    # go being PRESENT -- but the pin check asks whether go is the RIGHT
    # version, and those are different questions. Measured 2026-09-15 in the CI
    # `quality-security` lane: its toolchain report said `go 1.26.6 absent
    # MISMATCH` while `command -v go` still found a go, so acquisition took this
    # branch, `go install` failed, and shfmt came back unacquirable -- exit 77,
    # eight differential cases comparing 77 against 0. The `quality-static` lane
    # in the same run has NO go at all, took the download path, and had shfmt at
    # v3.13.1 in 0.6s. The download was always the answer for that lane; it just
    # was not reachable from this one.
    GOTOOLCHAIN=local GOBIN="$cache" go install "mvdan.cc/sh/v3/cmd/shfmt@v${want}" >/dev/null 2>&1 || {
        echo "toolchain: go install shfmt@v$want failed" >&2
        _toolchain_download_shfmt "$want" "$cache" "$bin"
        return $?
    }
    [[ -x "$bin" ]] || return 1
    printf '%s' "$bin"
}

_toolchain_acquire_shellcheck() {
    _toolchain_need_checksums
    local want="$1" cache bin os osk arch sha sha_var url tmp stage
    cache="$(toolchain_cache_dir)/shellcheck-$want"
    bin="$cache/shellcheck"
    [[ -x "$bin" ]] && {
        printf '%s' "$bin"
        return 0
    }
    os="$(_toolchain_os)" || return 1
    osk="$(printf '%s' "$os" | tr '[:lower:]' '[:upper:]')"
    case "$(uname -m)" in
        x86_64 | amd64) arch=x86_64 ;;
        aarch64 | arm64) arch=aarch64 ;;
        *)
            echo "toolchain: no pinned shellcheck checksum for $(uname -m); add one rather than downloading unverified" >&2
            return 1
            ;;
    esac
    # Keyed by OS as well as arch; see the same change in the shfmt helper for
    # why. shellcheck DOES publish darwin builds, so adding the two DARWIN_*
    # constants is all a Mac needs -- the URL below already asks for the right
    # asset once the hash exists.
    sha_var="SHELLCHECK_SHA256_${osk}_$(printf '%s' "$arch" | tr '[:lower:]' '[:upper:]')"
    sha="${!sha_var:-}"
    [[ -n "$sha" ]] || {
        echo "toolchain: no checksum for shellcheck ${os}/${arch} -- define ${sha_var} in .ci/config/constants.sh (and source it) rather than downloading unverified" >&2
        return 1
    }
    # xz IS A PRECONDITION, and this repo depends on it nowhere else. shellcheck
    # publishes its Linux builds only as .tar.xz, and the CI Static lane runs on
    # a deliberately slim image, so "tar: unrecognized option J" is a plausible
    # future failure whose text names neither xz nor shellcheck.
    if ! command -v xz >/dev/null 2>&1; then
        echo "toolchain: xz is required to extract shellcheck (every release it publishes is .tar.xz only)" >&2
        echo "  install xz-utils, or run this gate in the devbox where shellcheck is already at the pin" >&2
        return 1
    fi
    mkdir -p "$cache"
    # PRIVATE STAGING DIR, for the reason spelled out in the shfmt helper above:
    # a fixed `$cache/sc.tar.xz` is one inode shared by every concurrent
    # acquirer. This one is worse than shfmt's, because the extraction ALSO
    # targeted the shared `$cache` -- two `tar -x` runs racing meant a partially
    # written `shellcheck` could sit at the final path, executable, while a third
    # process ran it. Staging privately and renaming the finished binary in makes
    # the only shared step an atomic rename again.
    stage="$(mktemp -d "$cache/sc.XXXXXXXX")" || return 1
    tmp="$stage/sc.tar.xz"
    url="https://github.com/koalaman/shellcheck/releases/download/v${want}/shellcheck-v${want}.${os}.${arch}.tar.xz"
    curl -fsSL --max-time 180 --retry 3 --retry-delay 5 -o "$tmp" "$url" || {
        echo "toolchain: could not download shellcheck from $url" >&2
        rm -rf "$stage"
        return 1
    }
    # Verify BEFORE extracting: an unverified archive is arbitrary content, and
    # extraction is the point at which that starts to matter.
    echo "${sha}  ${tmp}" | _toolchain_sha256sum -c - >/dev/null 2>&1 || {
        echo "toolchain: shellcheck checksum MISMATCH -- refusing to extract" >&2
        echo "  expected $sha" >&2
        echo "  actual   $(_toolchain_sha256sum "$tmp" | cut -d' ' -f1)" >&2
        rm -rf "$stage"
        return 1
    }
    # The staging dir is torn down on EVERY exit path now, including the failed
    # extraction that used to leak the archive (`tar ... || return 1` with the
    # `rm -f` on the next line). That leak was one file overwritten in place;
    # under private staging it would have become an unbounded pile of
    # multi-megabyte directories, so tidying is not scope creep here, it is what
    # keeps the change from being a regression.
    tar -xJf "$tmp" -C "$stage" --strip-components=1 "shellcheck-v${want}/shellcheck" || {
        rm -rf "$stage"
        return 1
    }
    if ! { [[ -x "$stage/shellcheck" ]] && mv "$stage/shellcheck" "$bin"; }; then
        rm -rf "$stage"
        return 1
    fi
    rm -rf "$stage"
    [[ -x "$bin" ]] || return 1
    printf '%s' "$bin"
}

# Echo a binary that IS the pin, acquiring it if needed. Non-zero and explains
# otherwise.
toolchain_acquire() {
    local tool="$1" pin bin
    if bin="$(toolchain_check "$tool" 2>/dev/null)"; then
        printf '%s' "$bin"
        return 0
    fi
    pin="$(toolchain_pin_for "$tool")" || return 2
    # The same guard toolchain_check already carries. Its absence here was the
    # asymmetry that let an empty pin reach a URL: one entry point refused, the
    # other interpolated.
    [[ -n "$pin" ]] || {
        echo "toolchain: pin for '$tool' is empty -- the pins file did not load" >&2
        return 2
    }
    case "$tool" in
        shfmt) _toolchain_acquire_shfmt "$pin" ;;
        shellcheck) _toolchain_acquire_shellcheck "$pin" ;;
        *)
            toolchain_check "$tool" >/dev/null
            return $?
            ;;
    esac
}

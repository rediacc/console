#!/usr/bin/env bash
# THE PYTHON BOOTSTRAP: locate or install uv, then let uv provide pytest.
#
# WHY THIS FILE IS THE FIRST THING IN THE PYTHON WORKSTREAM. Nothing written in
# Python can be PROVEN on a machine until that machine has a package manager,
# and this one does not. Measured here on 2026-09-06, on the host these gates
# actually run on:
#
#   python3  3.14.4      present
#   ruff     0.16.1      present, on PATH
#   pytest   -           ABSENT
#   uv       -           ABSENT
#   uvx      -           ABSENT
#   pip      -           ABSENT   ("No module named pip" from python3 -m pip)
#   pipx     -           ABSENT
#
# That is not an unusual host; it is a distro Python with no ensurepip. The
# advice block in .ci/scripts/quality/check-python-lint.sh already records the
# same measurement and the same conclusion, and it cost a ~10-minute CI round to
# learn: an instruction that begins "pip install" is a DEAD END here, so the
# repo has to carry its own way in. This is it.
#
# WHAT IT DOES, AND DELIBERATELY NOTHING MORE. It gets uv, checksum-verified
# against a pin, into a repo-local directory; then it gets pytest via uv,
# because uv is the only thing on this host that can install a Python package
# at all; then it gets pytest-xdist INTO THAT SAME pytest environment, because
# the test gate runs the suite in parallel and a plugin that is absent is a
# suite that silently runs on one core. It does not create a venv, does not
# touch the system Python, does not write outside .ci/cache/ (gitignored), and
# does not run any test.
#
# THREE TOOLS, THREE RUNGS, THREE ROWS -- never two tools and an assumption.
# The install arm is IDEMPOTENT BY RESOLUTION rather than by a stamp file, so
# each thing is asked for separately: on a machine that already has pytest,
# resolve_pytest succeeds and install_pytest is never reached, and anything
# folded into that function would then be installed nowhere at all while the
# report still read `ok`.
#
# THE RESOLVER IS A SIBLING, NOT A NEW IDEA. Rungs and their order are lifted
# from resolve_ruff in .ci/scripts/quality/check-python-lint.sh:
#   1. an explicitly provided binary (UV_BIN / PYTEST_BIN)
#   2. a PATH binary AT THE PIN -- at the pin, never merely present, which is
#      the rule .ci/scripts/lib/toolchain.sh exists to enforce and which was
#      once got wrong for ruff specifically
#   3. this repo's own cached install
# A developer's own uv at the pin therefore wins, and CI does not re-download.
#
# NO VERSION LITERAL LIVES IN THIS FILE. check-toolchain-pins.sh assertion A1
# greps every .ci/**/*.sh for a literal copy of any toolchain.env value and
# fails on the second one. Everything below reads UV_VERSION, PYTEST_VERSION and
# UV_SHA256_<OS>_<ARCH> out of the pins file.
#
#   .ci/bootstrap.sh            install what is missing (idempotent)
#   .ci/bootstrap.sh --check    report what is missing, change NOTHING
#   .ci/bootstrap.sh doctor     print the resolved versions
#
# NOT readlink -f ANYWHERE: it is a GNU coreutils extension and macOS does not
# have it. `CDPATH='' cd -- ... && pwd -P` is the portable spelling, and CDPATH
# is cleared because a set CDPATH makes `cd` PRINT the directory it landed in,
# which would then be captured into the variable along with the real answer.
#
# CDPATH='' AND NOT `CDPATH= `. The two are identical to the shell, but the bare
# form trips SC1007 ("remove space after = if trying to assign a value") because
# an empty assignment followed by a space is far more often a typo than an
# intentional one-command environment prefix. Written with explicit quotes it
# reads as deliberate to a human AND to shellcheck, which beats carrying a
# disable directive for a warning that is right about the general case.

set -uo pipefail

CI_DIR="$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd -P)"
ROOT="$(CDPATH='' cd -- "$CI_DIR/.." && pwd -P)"

# shellcheck source=scripts/lib/toolchain.sh
. "$ROOT/.ci/scripts/lib/toolchain.sh"
toolchain_load || exit 1

RED=''
GREEN=''
YELLOW=''
NC=''
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ] && [ "${CI:-}" != "true" ]; then
    RED=$'\033[0;31m'
    GREEN=$'\033[0;32m'
    YELLOW=$'\033[0;33m'
    NC=$'\033[0m'
fi

# Everything this script installs lives here. .ci/cache/ is gitignored and
# per-worktree, so two worktrees never fight over one binary and `git status`
# stays clean.
UV_DIR="$ROOT/.ci/cache/toolchain/uv-${UV_VERSION}"
TOOL_DIR="$ROOT/.ci/cache/toolchain/uv-tools"
TOOL_BIN_DIR="$TOOL_DIR/bin"

# The platform, derived. Same two-axis mapping .ci/scripts/lib/toolchain.sh uses
# for shfmt and shellcheck, and for the same reason: hardcoding `linux` there
# silently installed a Linux binary on macOS, which passed its checksum and then
# failed at exec time. uv names its assets by target triple, so the OS half of
# the key is also the OS half of the URL.
uv_target() { # -> "<arch>-<os-triple> <SHA_VAR_SUFFIX>"
    local os arch triple sfx
    case "$(uname -s)" in
        Linux) os=unknown-linux-gnu sfx=LINUX ;;
        Darwin) os=apple-darwin sfx=DARWIN ;;
        *)
            echo "bootstrap: unsupported OS '$(uname -s)' -- uv publishes no pinned build this repo records for it" >&2
            return 1
            ;;
    esac
    case "$(uname -m)" in
        x86_64 | amd64) arch=x86_64 sfx="${sfx}_X86_64" ;;
        aarch64 | arm64) arch=aarch64 sfx="${sfx}_AARCH64" ;;
        *)
            echo "bootstrap: unsupported architecture '$(uname -m)' -- add its checksum to .devcontainer/toolchain.env rather than downloading unverified" >&2
            return 1
            ;;
    esac
    triple="${arch}-${os}"
    # WITH the newline. `read` returns non-zero at EOF even when it assigned
    # every variable, so a trailing-newline-less printf here made the caller's
    # `|| return 1` fire on a completely successful resolution -- and, because
    # every diagnostic in this file is on stderr behind an error branch that was
    # never reached, the whole script exited 1 having printed nothing at all.
    printf '%s %s\n' "$triple" "$sfx"
}

# Portable sha256. macOS has shasum, not sha256sum; verifying with the bare GNU
# name there does not report "cannot verify", it reports a checksum MISMATCH
# that never happened. Third copy of this shim in the repo, and the siblings are
# named so the next reader knows it is a pattern: _toolchain_sha256sum in
# .ci/scripts/lib/toolchain.sh and _sha256sum in .ci/lib/local-common.sh.
sha256_of() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | cut -d' ' -f1
    elif command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "$1" | cut -d' ' -f1
    else
        echo "bootstrap: no sha256 tool on PATH (need sha256sum or shasum) -- cannot verify the download" >&2
        return 1
    fi
}

# Rungs 1-3, in the order documented in the header. Echoes the binary, or fails.
resolve_uv() {
    if [ -n "${UV_BIN:-}" ]; then
        printf '%s' "$UV_BIN"
        return 0
    fi
    local at_pin
    if at_pin="$(toolchain_check uv 2>/dev/null)"; then
        printf '%s' "$at_pin"
        return 0
    fi
    if [ -x "$UV_DIR/uv" ] && [ "$(toolchain_probe_version uv "$UV_DIR/uv" 2>/dev/null)" = "$UV_VERSION" ]; then
        printf '%s' "$UV_DIR/uv"
        return 0
    fi
    return 1
}

resolve_pytest() {
    if [ -n "${PYTEST_BIN:-}" ]; then
        printf '%s' "$PYTEST_BIN"
        return 0
    fi
    local at_pin
    if at_pin="$(toolchain_check pytest 2>/dev/null)"; then
        printf '%s' "$at_pin"
        return 0
    fi
    if [ -x "$TOOL_BIN_DIR/pytest" ] &&
        [ "$(toolchain_probe_version pytest "$TOOL_BIN_DIR/pytest" 2>/dev/null)" = "$PYTEST_VERSION" ]; then
        printf '%s' "$TOOL_BIN_DIR/pytest"
        return 0
    fi
    return 1
}

# The pytest-xdist version REGISTERED IN THE PYTEST THAT WILL ACTUALLY RUN, or
# nothing. `pytest -VV` lists its registered plugins as `<name>-<version> at
# <path>`, so this asks the resolved binary rather than looking for a file: rung
# 2 of resolve_pytest can return a pytest from PATH whose environment is not
# $TOOL_DIR at all, and a plugin present in the cache but absent from THAT
# interpreter is not installed for any purpose here.
#
# EXACTLY `-VV`, AND NEVER `--version -VV`, WHICH SILENTLY PRINTS THE SHORT FORM.
# Measured against pytest 9.1.1 on 2026-09-07, and it cost one wrong red here:
# `_pytest/config/__init__.py:210-216` short-circuits the whole run when
# `args.count("--version") + args.count("-V") == 1`, counting TOKENS. `-VV` is
# one token that is neither of those, so `pytest --version -VV` scores 1, takes
# the fast path, prints `pytest 9.1.1` and exits 0 having ignored the verbosity
# it was asked for. `pytest --version -V` (score 2) prints the plugin list;
# `pytest --version -VV` does not. A probe on that spelling reports EVERY plugin
# as absent, which reads as a failed install rather than a mis-parsed flag.
#
# NO VERSION LITERAL, per the header: the sed captures whatever digits are
# registered and the caller compares them against $PYTEST_XDIST_VERSION.
xdist_version_of() {
    "$1" -VV 2>/dev/null |
        sed -n 's/.*pytest-xdist-\([0-9][0-9.]*\).*/\1/p' | head -1
}

# A SEPARATE RUNG, NOT A CHANGE TO resolve_pytest, and that is the whole point.
# The install arm below is idempotent BY RESOLUTION: on every machine that
# already has pytest at the pin, resolve_pytest succeeds and install_pytest is
# never called, so folding xdist into that path would silently install it
# nowhere. Asked separately, it is installed separately.
#
# There is no PYTEST_XDIST_BIN rung: xdist has no binary. PYTEST_BIN still
# decides WHICH pytest is asked, which is the only override that means anything.
resolve_xdist() {
    local pytest_bin
    pytest_bin="$(resolve_pytest)" || return 1
    [ "$(xdist_version_of "$pytest_bin")" = "$PYTEST_XDIST_VERSION" ] || return 1
    printf '%s' "$pytest_bin"
    return 0
}

install_uv() {
    local triple sfx sha_var want url tmp got
    read -r triple sfx < <(uv_target) || return 1
    [ -n "${triple:-}" ] || return 1
    sha_var="UV_SHA256_${sfx}"
    want="${!sha_var:-}"
    # A pin with no checksum is not a pin. Refusing here is the whole point:
    # the alternative is an unverified binary that later signs releases.
    [ -n "$want" ] || {
        echo "bootstrap: no checksum for this platform -- define ${sha_var} in .devcontainer/toolchain.env rather than downloading unverified" >&2
        return 1
    }
    url="https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/uv-${triple}.tar.gz"
    tmp="$(mktemp -d)" || return 1
    # shellcheck disable=SC2064  # expand tmp NOW so the trap removes this dir, not a later value
    trap "rm -rf '$tmp'" RETURN
    # STDERR. This function's STDOUT is the resolved binary path, captured by
    # the caller; a progress line on stdout would be concatenated into it.
    echo "bootstrap: downloading uv ${UV_VERSION} for ${triple}" >&2
    curl -fsSL --max-time 300 --retry 3 --retry-delay 5 -o "$tmp/uv.tar.gz" "$url" || {
        echo "${RED}bootstrap${NC}: could not download uv from $url" >&2
        return 1
    }
    got="$(sha256_of "$tmp/uv.tar.gz")" || return 1
    # Verify BEFORE extracting: an unverified archive is arbitrary content, and
    # extraction is where that starts to matter. Same order as
    # _toolchain_acquire_shellcheck, and stated again because the opposite order
    # reads as harmless.
    [ "$got" = "$want" ] || {
        echo "${RED}bootstrap${NC}: uv checksum MISMATCH -- refusing to install" >&2
        echo "  expected $want" >&2
        echo "  actual   $got" >&2
        return 1
    }
    mkdir -p "$UV_DIR" || return 1
    # The tarball is a single uv-<triple>/ directory holding uv and uvx.
    tar -xzf "$tmp/uv.tar.gz" -C "$UV_DIR" --strip-components=1 || {
        echo "${RED}bootstrap${NC}: could not extract the uv archive" >&2
        return 1
    }
    [ -x "$UV_DIR/uv" ] || {
        echo "${RED}bootstrap${NC}: the archive extracted but $UV_DIR/uv is not there" >&2
        return 1
    }
    printf '%s' "$UV_DIR/uv"
}

install_pytest() {
    local uv="$1"
    # STDERR, for the same reason as install_uv: stdout is the binary path.
    echo "bootstrap: installing pytest ${PYTEST_VERSION} via uv" >&2
    # UV_TOOL_DIR/UV_TOOL_BIN_DIR keep this out of ~/.local: a bootstrap that
    # edits the developer's home directory is one that cannot be undone by
    # deleting the worktree.
    UV_TOOL_DIR="$TOOL_DIR" UV_TOOL_BIN_DIR="$TOOL_BIN_DIR" \
        "$uv" tool install --quiet "pytest==${PYTEST_VERSION}" || {
        echo "${RED}bootstrap${NC}: uv tool install pytest failed" >&2
        return 1
    }
    [ -x "$TOOL_BIN_DIR/pytest" ] || {
        echo "${RED}bootstrap${NC}: uv reported success but $TOOL_BIN_DIR/pytest is not there" >&2
        return 1
    }
    printf '%s' "$TOOL_BIN_DIR/pytest"
}

install_xdist() {
    local uv="$1" got
    echo "bootstrap: installing pytest-xdist ${PYTEST_XDIST_VERSION} into the pytest environment via uv" >&2
    # `uv tool install --with` REINSTALLS the pytest tool with the plugin in its
    # environment. That is why the pytest pin is repeated on this line and not
    # dropped: `--with` alone does not name the tool, and naming pytest without
    # its version would resolve the newest one and silently unpin the runner
    # this whole file exists to pin.
    UV_TOOL_DIR="$TOOL_DIR" UV_TOOL_BIN_DIR="$TOOL_BIN_DIR" \
        "$uv" tool install --quiet --force \
        --with "pytest-xdist==${PYTEST_XDIST_VERSION}" "pytest==${PYTEST_VERSION}" || {
        echo "${RED}bootstrap${NC}: uv tool install pytest-xdist failed" >&2
        return 1
    }
    # VERIFIED BY ASKING PYTEST, not by trusting uv's exit code. A plugin that
    # installed into the wrong environment, or that pytest refuses to load,
    # leaves `-n` failing at gate time with a message about an unknown option --
    # which reads as a broken gate rather than a missing plugin.
    got="$(xdist_version_of "$(resolve_pytest)")"
    [ "$got" = "$PYTEST_XDIST_VERSION" ] || {
        echo "${RED}bootstrap${NC}: uv reported success but pytest registers pytest-xdist '${got:-none}'" >&2
        return 1
    }
    printf '%s' "$TOOL_BIN_DIR/pytest"
}

# One row per tool. `want` is always printed next to `have`, because "pytest:
# ok" tells the reader nothing about WHICH pytest answered.
report_row() {
    printf '  %-8s %-9s %s\n' "$1" "$2" "$3"
}

report() {
    local uv pytest xdist rc=0
    printf 'root: %s\n' "$ROOT"
    printf 'lane: %s\n\n' "$(toolchain_lane)"
    report_row tool pinned resolved
    if uv="$(resolve_uv)"; then
        report_row uv "$UV_VERSION" "$uv"
    else
        report_row uv "$UV_VERSION" "${YELLOW}ABSENT${NC}"
        rc=1
    fi
    if pytest="$(resolve_pytest)"; then
        report_row pytest "$PYTEST_VERSION" "$pytest"
    else
        report_row pytest "$PYTEST_VERSION" "${YELLOW}ABSENT${NC}"
        rc=1
    fi
    # ITS OWN ROW, because "pytest: ok" says nothing about whether the suite can
    # be run in parallel. The resolved column shows the pytest the plugin is
    # registered in, since that is the thing the answer is about.
    if xdist="$(resolve_xdist)"; then
        report_row xdist "$PYTEST_XDIST_VERSION" "in $xdist"
    else
        report_row xdist "$PYTEST_XDIST_VERSION" "${YELLOW}ABSENT${NC}"
        rc=1
    fi
    report_row python3 "-" "$(command -v python3 || echo "${YELLOW}ABSENT${NC}")"
    return "$rc"
}

case "${1:-install}" in
    --check)
        # REPORTS, INSTALLS NOTHING. Non-zero when something is missing, so a
        # caller can branch on it; the rows say which.
        if report; then
            echo
            echo "${GREEN}ok${NC}   the Python toolchain is complete"
            exit 0
        fi
        echo
        echo "${YELLOW}missing${NC}: run '.ci/bootstrap.sh' to install what is ABSENT above"
        exit 1
        ;;
    doctor)
        report
        exit $?
        ;;
    install)
        # No `| ""` arm: ${1:-install} substitutes the default for an EMPTY
        # first argument as well as an unset one, so an empty-string arm here
        # would be unreachable -- the shape check-dead-case-arms.sh exists for.
        # IDEMPOTENT BY RESOLUTION, not by a marker file. A stamp can disagree
        # with the disk; asking the binary its version cannot.
        if uv_bin="$(resolve_uv)"; then
            echo "${GREEN}ok${NC}   uv ${UV_VERSION} already at $uv_bin"
        else
            uv_bin="$(install_uv)" || exit 1
            echo "${GREEN}ok${NC}   uv ${UV_VERSION} installed at $uv_bin"
        fi
        if pytest_bin="$(resolve_pytest)"; then
            echo "${GREEN}ok${NC}   pytest ${PYTEST_VERSION} already at $pytest_bin"
        else
            pytest_bin="$(install_pytest "$uv_bin")" || exit 1
            echo "${GREEN}ok${NC}   pytest ${PYTEST_VERSION} installed at $pytest_bin"
        fi
        if xdist_in="$(resolve_xdist)"; then
            echo "${GREEN}ok${NC}   pytest-xdist ${PYTEST_XDIST_VERSION} already in $xdist_in"
        else
            xdist_in="$(install_xdist "$uv_bin")" || exit 1
            echo "${GREEN}ok${NC}   pytest-xdist ${PYTEST_XDIST_VERSION} installed into $xdist_in"
        fi
        exit 0
        ;;
    *)
        echo "usage: bootstrap.sh [install|--check|doctor]" >&2
        exit 2
        ;;
esac

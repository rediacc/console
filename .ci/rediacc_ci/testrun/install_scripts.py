"""The container scripts of `testrun.install_methods`, one per install method.

Taken from what `test-install-methods.sh` hands `docker run` (captured through a fake `docker`), with the run-specific values as `@NAME@` placeholders. `@PROBE@` is the fenced version probe (`install_methods.version_fence_probe`). Comment lines are not compared against the twin: the quick-install script drops a block of comments that cited line numbers of the bash file.
"""

from rediacc_ci.well_known import HOMEBREW_TAP, RELEASES_ORIGIN, UBUNTU_ARCHIVE, UBUNTU_AZURE_MIRROR

RELEASES_HOST = RELEASES_ORIGIN.removeprefix("https://")

APT = (
    r"""
        set -e
        # Point apt at the Azure-hosted Ubuntu mirror. The upstream
        # archive.ubuntu.com / security.ubuntu.com mirrors routinely become
        # unreachable from Azure-hosted GitHub runners for 5-30 minute
        # windows, taking down this test even when the Rediacc apt repo is
        # healthy. Azure mirror is co-located with the runners.
        for f in /etc/apt/sources.list /etc/apt/sources.list.d/ubuntu.sources; do
            [ -f "$f" ] && sed -i \
                -e 's|http://archive\.ubuntu\.com/ubuntu|"""
    + UBUNTU_AZURE_MIRROR
    + r"""|g' \
                -e 's|http://security\.ubuntu\.com/ubuntu|"""
    + UBUNTU_AZURE_MIRROR
    + r"""|g' \
                "$f"
        done
        # FALL BACK if the Azure mirror is the thing that is down. The comment
        # above assumed it never is; on 2026-08-19 it refused connections for
        # ninety minutes and took this test down along with four devcontainer
        # builds. Rewriting every source to one host turns a co-location
        # optimisation into a single point of failure.
        if ! apt-get update -qq; then
            echo 'azure mirror unreachable; falling back to archive.ubuntu.com' >&2
            for f in /etc/apt/sources.list /etc/apt/sources.list.d/ubuntu.sources; do
                [ -f "$f" ] && sed -i \
                    -e 's|http://azure\.archive\.ubuntu\.com/ubuntu|"""
    + UBUNTU_ARCHIVE
    + (
        r"""|g' \
                    "$f"
            done
            apt-get update -qq
        fi
        apt-get install -y -qq curl gnupg ca-certificates >/dev/null 2>&1

        # Add GPG key
        curl -fsSL @RELEASES@/apt@SUFFIX@/gpg.key | gpg --dearmor -o /usr/share/keyrings/rediacc.gpg

        # Add sources list
        echo 'deb [signed-by=/usr/share/keyrings/rediacc.gpg] @RELEASES@/apt@SUFFIX@ stable main' > /etc/apt/sources.list.d/rediacc.list

        # Retry apt-get update for transient network flakes on the way to
        # """
        + RELEASES_HOST
        + r""". The underlying cause of the long flake
        # windows we chased in early iterations -- CF edge caching stale
        # Packages.gz -- is now neutralised by the zone-level Cache Rule
        # that bypasses cache for """
        + RELEASES_HOST
        + r""" (see
        # .ci/docs/r2-setup.md), so 5x15s is sufficient.
        for attempt in 1 2 3 4 5; do
            if apt-get update -qq -o Acquire::Retries=0; then
                break
            fi
            if [[ $attempt -eq 5 ]]; then
                echo 'apt-get update failed after 5 attempts' >&2
                exit 1
            fi
            echo "apt-get update attempt $attempt failed, retrying in 15s..." >&2
            sleep 15
        done
        apt-get install -y -qq @PKG@ >/dev/null 2>&1

        # Verify: fenced so the host compares the BINARY's output, not the
        # version apt-get itself printed while installing the package.
        @PROBE@
    """
    )
)

APT_PROBE = "rdc --version"

DNF = r"""
        set -e
        # Add repo
        curl -fsSL @RELEASES@/rpm@SUFFIX@/rediacc.repo -o /etc/yum.repos.d/rediacc.repo

        # Install
        dnf install -y @PKG@ >/dev/null 2>&1

        # Verify (fenced; see run_container_version_test)
        @PROBE@
    """

DNF_PROBE = "rdc --version"

APK = r"""
        set -e
        # Add APK repository (apk appends arch automatically)
        echo '@RELEASES@/apk@SUFFIX@' >> /etc/apk/repositories
        apk update --allow-untrusted

        # Install from repo
        apk add --no-cache --allow-untrusted @PKG@

        # Verify (fenced; see run_container_version_test)
        @PROBE@
    """

APK_PROBE = "rdc --version"

PACMAN = r"""
        set -e
        # Add rediacc repository
        echo '[rediacc]' >> /etc/pacman.conf
        echo 'SigLevel = Optional TrustAll' >> /etc/pacman.conf
        echo 'Server = @RELEASES@/archlinux@SUFFIX@/$arch' >> /etc/pacman.conf

        pacman -Sy --noconfirm

        # Install from repo
        pacman -S --noconfirm @PKG@

        # Verify (fenced; see run_container_version_test)
        @PROBE@
    """

PACMAN_PROBE = "rdc --version"

NPM = r"""
        set -e
        npm install -g '@RELEASES@/npm@SUFFIX@/@PKG@-latest.tgz' --before '@NPM_BEFORE@'
        # Fenced: npm prints the package version itself while installing, so an
        # unfenced grep over this transcript would match even if the installed
        # binary reported something else.
        @PROBE@
    """

NPM_PROBE = "rdc --version"

QUICK = (
    r"""
        set -e
        # Point apt at the Azure-hosted Ubuntu mirror. The upstream
        # archive.ubuntu.com / security.ubuntu.com mirrors routinely become
        # unreachable from Azure-hosted GitHub runners for 5-30 minute
        # windows, taking down this test even when the Rediacc apt repo is
        # healthy. Azure mirror is co-located with the runners.
        for f in /etc/apt/sources.list /etc/apt/sources.list.d/ubuntu.sources; do
            [ -f "$f" ] && sed -i \
                -e 's|http://archive\.ubuntu\.com/ubuntu|"""
    + UBUNTU_AZURE_MIRROR
    + r"""|g' \
                -e 's|http://security\.ubuntu\.com/ubuntu|"""
    + UBUNTU_AZURE_MIRROR
    + r"""|g' \
                "$f"
        done
        # FALL BACK if the Azure mirror is the thing that is down. The comment
        # above assumed it never is; on 2026-08-19 it refused connections for
        # ninety minutes and took this test down along with four devcontainer
        # builds. Rewriting every source to one host turns a co-location
        # optimisation into a single point of failure.
        if ! apt-get update -qq; then
            echo 'azure mirror unreachable; falling back to archive.ubuntu.com' >&2
            for f in /etc/apt/sources.list /etc/apt/sources.list.d/ubuntu.sources; do
                [ -f "$f" ] && sed -i \
                    -e 's|http://azure\.archive\.ubuntu\.com/ubuntu|"""
    + UBUNTU_ARCHIVE
    + r"""|g' \
                    "$f"
            done
            apt-get update -qq
        fi
        apt-get install -y -qq curl ca-certificates >/dev/null 2>&1

        # Fetch install script and verify its baked default channel matches
        # the channel under test. Catches regressions where channel rewriting
        # (worker or R2 upload) silently falls back to 'stable'.
        script=$(curl -fsSL @RELEASES@/cli@SUFFIX@/install.sh)
        # The inner shell sets `set -e` only, so the pipeline below reports grep's status and the match stands.
        if [ -z "$(echo "$script" | grep 'REDIACC_CHANNEL:-@CHANNEL@')" ]; then
            echo 'FAIL: install.sh default channel is not @CHANNEL@' >&2
            echo "$script" | grep -E 'REDIACC_CHANNEL' >&2 || true
            exit 1
        fi

        # Run install script from channel
        echo "$script" | bash

        # Verify (install.sh puts binary in ~/.local/bin), fenced so the host
        # compares the binary's output and not the version install.sh echoed.
        # $HOME rather than ~: the path is built as a string here and expanded
        # by the container's shell, where a tilde inside a string would not.
        @PROBE@
    """
)

QUICK_PROBE = "$HOME/.local/bin/rdc --version"

HOMEBREW = (
    r"""
        set -e
        brew tap """
    + HOMEBREW_TAP
    + r"""
        brew install @TAP@
        # Fenced: brew prints the formula version while installing.
        @PROBE@
    """
)

HOMEBREW_PROBE = "rdc --version"

#!/usr/bin/env bash
# Machine bootstrap for `./run.sh setup`.
#
# SPLIT OUT OF run.sh, which was 2919 lines before these functions were added and
# would have been well past 3500 after. Everything here answers one question --
# "what does a bare machine need before this repo can build?" -- and none of it is
# referenced by any other run.sh command, so it is a clean seam rather than a
# filing decision.
#
# Sourced by run.sh, which already sources .ci/lib/local-common.sh for log_*,
# prompt_continue and ensure_deps.
#
# EVERY FUNCTION HERE IS IDEMPOTENT and returns 0 early when its condition is
# already met. That is the contract: `./run.sh setup` is expected to be run
# repeatedly, and a second run must do no work.
#
# Each also refuses rather than hanging on a non-TTY, printing the command it
# would have run as PLAIN stdout so it can be pasted (log_* prefixes every line
# with a coloured marker, which breaks a paste).

# Ensure a usable Node.js + npm, installing one if the operator agrees.
#
# WHY THIS EXISTS. check_node_version() only ever REPORTED "Node.js is not
# installed" and returned 1, which is where a bare machine stopped: ./rdc.sh,
# npm run ci and ./run.sh setup itself all died there with nothing to do about
# it but go read another doc. Setup is the one command whose whole job is to
# make a bare machine work, so it is the right place to fix this rather than
# telling each new machine's owner to go install node by hand.
#
# NO SUDO, and no touching a version manager the operator already runs: if fnm,
# nvm, volta, asdf or mise is present, that is their toolchain and this prints
# the one command to run rather than installing a second node behind its back.
#
# THE DOWNLOAD IS CHECKSUM-VERIFIED against the official SHASUMS256.txt. This
# repo blocks dependency lifecycle scripts in .npmrc for supply-chain reasons;
# piping an unverified tarball into the shell right next to that would be the
# same class of mistake this project already paid for once, when a documented
# `curl` of a 404 baked an HTML error page into a signing key.
setup_node_toolchain() {
    local min="${NODE_VERSION_MIN:-22.0.0}"
    local major="${NODE_VERSION_REQUIRED:-22}"
    local cur=""

    if command -v node >/dev/null 2>&1; then
        cur=$(node -v 2>/dev/null | cut -d'v' -f2)
        if [[ -n "$cur" ]] && printf '%s\n%s\n' "$min" "$cur" | sort -V -C; then
            if command -v npm >/dev/null 2>&1; then
                log_info "Node.js $cur and npm $(npm -v 2>/dev/null) already present"
                return 0
            fi
            log_warn "node $cur is present but npm is NOT on PATH."
        else
            log_warn "Node.js ${cur:-unknown} is older than the required $min."
        fi
    else
        log_warn "Node.js is not installed; nothing in this repo can build or test without it."
    fi

    # Their manager, their call. Print the command; do not drive it.
    local mgr=""
    for m in fnm nvm volta asdf mise; do
        command -v "$m" >/dev/null 2>&1 && { mgr="$m"; break; }
    done
    if [[ -z "$mgr" && -s "$HOME/.nvm/nvm.sh" ]]; then mgr="nvm"; fi
    if [[ -n "$mgr" ]]; then
        log_warn "You already use '$mgr'; install node with it rather than letting setup"
        log_warn "put a second toolchain on this machine:"
        echo ""
        case "$mgr" in
            fnm)   echo "fnm install $major && fnm use $major" ;;
            nvm)   echo "nvm install $major && nvm use $major" ;;
            volta) echo "volta install node@$major" ;;
            asdf)  echo "asdf install nodejs latest:$major && asdf global nodejs latest:$major" ;;
            mise)  echo "mise use -g node@$major" ;;
        esac
        echo ""
        echo "Then re-run: ./run.sh setup"
        echo ""
        return 1
    fi

    local os arch
    case "$(uname -s)" in
        Linux)  os=linux ;;
        Darwin) os=darwin ;;
        *)      log_error "Unsupported OS $(uname -s); install Node.js >= $min yourself."; return 1 ;;
    esac
    case "$(uname -m)" in
        x86_64|amd64)  arch=x64 ;;
        aarch64|arm64) arch=arm64 ;;
        *)             log_error "Unsupported arch $(uname -m); install Node.js >= $min yourself."; return 1 ;;
    esac

    if [[ ! -t 0 ]]; then
        log_warn "Non-interactive run; not installing. Install Node.js >= $min, or run"
        log_warn "./run.sh setup from a terminal to be offered an automatic install."
        return 1
    fi

    log_info "Setup can install Node.js $major into ~/.local/share (no sudo, no system changes)."
    prompt_continue "Install a private Node.js $major for this machine?" || {
        log_warn "Skipped. Install Node.js >= $min yourself, then re-run ./run.sh setup."
        return 1
    }

    # Resolve the newest LTS on the required major from the official index, so
    # this does not rot into a pinned version nobody remembers to bump.
    local ver
    ver=$(curl -fsS --max-time 30 https://nodejs.org/dist/index.json 2>/dev/null \
        | node_pick_lts "$major") || ver=""
    if [[ -z "$ver" ]]; then
        log_error "Could not resolve the latest Node.js $major LTS from nodejs.org."
        log_error "Check network access, or install Node.js >= $min yourself."
        return 1
    fi

    local base="node-${ver}-${os}-${arch}"
    local url="https://nodejs.org/dist/${ver}/${base}.tar.xz"
    local dest="$HOME/.local/share/node/${ver}"
    local tmp
    tmp=$(mktemp -d) || return 1

    log_step "Downloading ${base}.tar.xz"
    if ! curl -fsSL --max-time 300 "$url" -o "$tmp/$base.tar.xz"; then
        log_error "Download failed: $url"
        rm -rf "$tmp"; return 1
    fi

    # Verify BEFORE extracting. An unverified tarball is the whole attack.
    log_step "Verifying checksum against the official SHASUMS256.txt"
    if ! curl -fsSL --max-time 60 "https://nodejs.org/dist/${ver}/SHASUMS256.txt" -o "$tmp/SHASUMS256.txt"; then
        log_error "Could not fetch SHASUMS256.txt; refusing to install an unverified tarball."
        rm -rf "$tmp"; return 1
    fi
    local want got
    want=$(grep " ${base}.tar.xz\$" "$tmp/SHASUMS256.txt" | awk '{print $1}')
    got=$(sha256sum "$tmp/$base.tar.xz" | awk '{print $1}')
    if [[ -z "$want" || "$want" != "$got" ]]; then
        log_error "Checksum MISMATCH for ${base}.tar.xz"
        log_error "  expected: ${want:-<not listed in SHASUMS256.txt>}"
        log_error "  got:      $got"
        rm -rf "$tmp"; return 1
    fi
    log_info "Checksum verified"

    log_step "Installing to $dest"
    mkdir -p "$dest"
    if ! tar -xJf "$tmp/$base.tar.xz" -C "$dest" --strip-components=1; then
        log_error "Extraction failed."
        rm -rf "$tmp"; return 1
    fi
    rm -rf "$tmp"

    mkdir -p "$HOME/.local/bin"
    local linked=0
    for b in node npm npx; do
        if [[ -e "$dest/bin/$b" ]]; then
            ln -sf "$dest/bin/$b" "$HOME/.local/bin/$b"
            linked=$((linked + 1))
        fi
    done
    if [[ $linked -eq 0 ]]; then
        log_error "Extracted $dest but found no bin/node; the archive layout was unexpected."
        return 1
    fi

    export PATH="$HOME/.local/bin:$PATH"
    hash -r 2>/dev/null || true

    if ! command -v node >/dev/null 2>&1; then
        log_error "node still not resolvable after install."
        return 1
    fi
    log_info "Node.js $(node -v) and npm $(npm -v 2>/dev/null) installed"

    case ":$PATH:" in
        *":$HOME/.local/bin:"*) ;;
        *)
            echo ""
            echo "Add ~/.local/bin to your PATH so future shells find it:"
            echo ""
            echo "echo 'export PATH=\"$HOME/.local/bin:$PATH\"' >> ~/.bashrc"
            echo ""
            ;;
    esac
    return 0
}

# Newest LTS for a major, read off the official dist index on stdin.
# Split out so setup_node_toolchain stays readable and this is unit-testable.
node_pick_lts() {
    local major="$1"
    python3 -c "
import json, sys
try:
    idx = json.load(sys.stdin)
except Exception:
    sys.exit(1)
rel = [r for r in idx if r.get('version','').startswith('v${major}.') and r.get('lts')]
if not rel:
    rel = [r for r in idx if r.get('version','').startswith('v${major}.')]
if not rel:
    sys.exit(1)
print(rel[0]['version'])
" 2>/dev/null
}

# Ensure a C/C++ toolchain, because install:natives genuinely REQUIRES one.
#
# WHY MANDATORY, not best-effort. `npm run install:natives` rebuilds ssh2,
# cpu-features and esbuild. Measured on a bare Ubuntu 26.04 box: esbuild needs
# no compiler (it downloads a binary) and ssh2 survives on its own ("Failed to
# build optional crypto binding", exit 0), but cpu-features runs node-gyp and
# dies with "Unable to detect compiler type", which fails the whole script and
# therefore fails setup and every ./rdc.sh invocation behind it.
#
# The devcontainer already gets this right -- .devcontainer/Dockerfile installs
# build-essential and python3 (:83-86) alongside node 22 via nvm (:172-173). A
# machine outside that container had no equivalent, which is the gap this fills:
# same toolchain, same outcome, whether or not you use the container.
#
# THIS IS THE ONE PLACE setup NEEDS ROOT, so it asks, and it prints the command
# instead of running it whenever it cannot ask (non-TTY) or cannot elevate.
setup_system_tools() {
    local missing=()
    command -v cc   >/dev/null 2>&1 || missing+=("a C compiler")
    command -v make >/dev/null 2>&1 || missing+=("make")
    command -v jq   >/dev/null 2>&1 || missing+=("jq")

    if [[ ${#missing[@]} -eq 0 ]]; then
        log_info "System tools present: $(cc --version 2>/dev/null | head -1), jq $(jq --version 2>/dev/null)"
        return 0
    fi

    log_warn "Missing required system tools: ${missing[*]}"
    log_warn "  a C compiler + make: 'npm run install:natives' runs node-gyp for cpu-features"
    log_warn "  jq: EVERY PreToolUse hook in .claude/hooks parses its input with it"

    local install_cmd=""
    if [[ "$(uname -s)" == "Darwin" ]]; then
        echo ""
        echo "xcode-select --install   # compiler + make"
        echo "brew install jq          # xcode-select does NOT provide jq"
        echo ""
        echo "Then re-run: ./run.sh setup"
        echo ""
        return 1
    elif command -v apt-get >/dev/null 2>&1; then
        install_cmd="sudo apt-get update && sudo apt-get install -y build-essential python3 jq"
    elif command -v dnf >/dev/null 2>&1; then
        install_cmd="sudo dnf groupinstall -y 'Development Tools' && sudo dnf install -y python3 jq"
    elif command -v pacman >/dev/null 2>&1; then
        install_cmd="sudo pacman -S --noconfirm base-devel python jq"
    elif command -v apk >/dev/null 2>&1; then
        install_cmd="sudo apk add build-base python3 jq"
    else
        log_error "No known package manager; install a C/C++ toolchain and python3 yourself."
        return 1
    fi

    # Cannot ask, or cannot elevate: hand over the command as plain, pasteable
    # stdout. log_* would prefix every line with a marker and break the paste.
    if [[ ! -t 0 ]] || ! command -v sudo >/dev/null 2>&1; then
        log_warn "Cannot install it from here. Run this yourself:"
        echo ""
        echo "$install_cmd"
        echo ""
        echo "Then re-run: ./run.sh setup"
        echo ""
        return 1
    fi

    log_info "This is the only step in setup that needs root."
    echo "  $install_cmd"
    if ! prompt_continue "Install the build toolchain now?"; then
        log_warn "Skipped, but install:natives will fail until it is installed. Run:"
        echo ""
        echo "$install_cmd"
        echo ""
        return 1
    fi

    if ! eval "$install_cmd"; then
        log_error "Toolchain install failed. Run it yourself and re-run ./run.sh setup:"
        echo ""
        echo "$install_cmd"
        echo ""
        return 1
    fi

    hash -r 2>/dev/null || true
    for t in cc make jq; do
        if ! command -v "$t" >/dev/null 2>&1; then
            log_error "'$t' still not resolvable after install."
            return 1
        fi
    done
    log_info "System tools installed ($(cc --version 2>/dev/null | head -1), jq $(jq --version 2>/dev/null))"
    return 0
}

# Ensure a Go toolchain, because ./rdc.sh rebuilds renet from source.
#
# MANDATORY, same reasoning as the C toolchain: ensure_renet_built() fails with
# "Go is not installed (required for building renet)" and every ./rdc.sh
# invocation stops there, so a machine without Go cannot run the CLI at all.
#
# THE VERSION IS READ FROM .devcontainer/Dockerfile's ARG GO_VERSION, not
# duplicated here. That file already pins it, and its own comment records why a
# floating version is dangerous: a `go` directive once resolved the
# never-published go1.26.5 and 404'd the whole image build. One pin, one place.
#
# Checksum-verified against go.dev's signed index, for the same reason the node
# install is: an unverified tarball is the whole attack.
setup_go_toolchain() {
    local want_ver
    want_ver=$(grep -oP '^ARG GO_VERSION=\K[0-9.]+' "$ROOT_DIR/.devcontainer/Dockerfile" 2>/dev/null | head -1)
    if [[ -z "$want_ver" ]]; then
        log_error "Could not read ARG GO_VERSION from .devcontainer/Dockerfile."
        log_error "That file is the pin; fix it rather than hardcoding a version here."
        return 1
    fi

    if command -v go >/dev/null 2>&1; then
        local cur
        cur=$(go version 2>/dev/null | grep -oP 'go\K[0-9.]+' | head -1)
        if [[ -n "$cur" ]] && printf '%s\n%s\n' "$want_ver" "$cur" | sort -V -C; then
            log_info "Go $cur present (pin: $want_ver)"
            return 0
        fi
        log_warn "Go ${cur:-unknown} is older than the pinned $want_ver."
    else
        log_warn "Go is not installed; ./rdc.sh cannot build renet without it."
    fi

    local os arch
    case "$(uname -s)" in
        Linux)  os=linux ;;
        Darwin) os=darwin ;;
        *) log_error "Unsupported OS $(uname -s); install Go $want_ver yourself."; return 1 ;;
    esac
    case "$(uname -m)" in
        x86_64|amd64)  arch=amd64 ;;
        aarch64|arm64) arch=arm64 ;;
        *) log_error "Unsupported arch $(uname -m); install Go $want_ver yourself."; return 1 ;;
    esac

    local file="go${want_ver}.${os}-${arch}.tar.gz"
    if [[ ! -t 0 ]]; then
        log_warn "Non-interactive run; not installing. Install Go $want_ver, or run"
        log_warn "./run.sh setup from a terminal to be offered an automatic install."
        return 1
    fi

    log_info "Setup can install Go $want_ver into ~/.local/share (no sudo)."
    prompt_continue "Install Go $want_ver for this machine?" || {
        log_warn "Skipped. Install Go $want_ver yourself, then re-run ./run.sh setup."
        return 1
    }

    local tmp; tmp=$(mktemp -d) || return 1
    log_step "Resolving $file checksum from go.dev"
    local want_sha
    want_sha=$(curl -fsS --max-time 60 "https://go.dev/dl/?mode=json&include=all" 2>/dev/null \
        | go_pick_sha "$file")
    if [[ -z "$want_sha" ]]; then
        log_error "Could not find a published checksum for $file."
        log_error "Check that $want_ver exists on https://go.dev/dl/ (the pin may be wrong)."
        rm -rf "$tmp"; return 1
    fi

    log_step "Downloading $file"
    if ! curl -fsSL --max-time 600 "https://go.dev/dl/${file}" -o "$tmp/$file"; then
        log_error "Download failed: https://go.dev/dl/${file}"
        rm -rf "$tmp"; return 1
    fi
    local got_sha; got_sha=$(sha256sum "$tmp/$file" | awk '{print $1}')
    if [[ "$want_sha" != "$got_sha" ]]; then
        log_error "Checksum MISMATCH for $file"
        log_error "  expected: $want_sha"
        log_error "  got:      $got_sha"
        rm -rf "$tmp"; return 1
    fi
    log_info "Checksum verified"

    local dest="$HOME/.local/share/go/${want_ver}"
    log_step "Installing to $dest"
    rm -rf "$dest"; mkdir -p "$dest"
    if ! tar -xzf "$tmp/$file" -C "$dest" --strip-components=1; then
        log_error "Extraction failed."
        rm -rf "$tmp"; return 1
    fi
    rm -rf "$tmp"

    mkdir -p "$HOME/.local/bin"
    for b in go gofmt; do
        [[ -e "$dest/bin/$b" ]] && ln -sf "$dest/bin/$b" "$HOME/.local/bin/$b"
    done
    export PATH="$HOME/.local/bin:$PATH"
    hash -r 2>/dev/null || true

    if ! command -v go >/dev/null 2>&1; then
        log_error "go still not resolvable after install."
        return 1
    fi
    log_info "$(go version)"
    return 0
}

# sha256 for one Go release filename, read off go.dev's json index on stdin.
go_pick_sha() {
    local want="$1"
    python3 -c "
import json, sys
try:
    idx = json.load(sys.stdin)
except Exception:
    sys.exit(1)
for rel in idx:
    for f in rel.get('files', []):
        if f.get('filename') == '${want}' and f.get('sha256'):
            print(f['sha256']); sys.exit(0)
sys.exit(1)
" 2>/dev/null
}

# Ensure the GitHub CLI, because this repo's PR flow is built on it.
#
# MANDATORY. `gh` is not a convenience here: block-second-open-pr.sh shells out
# to `gh pr list` and FAILS CLOSED when that errors, so on a machine without gh
# every `gh pr create` is refused; block-admin-merge.sh and block-premature-ready
# both run live `gh` queries for the same reason; and /pr-merge and /pr-babysit
# are written entirely in terms of it. A missing gh does not degrade the PR flow,
# it stops it.
#
# LATEST, NOT PINNED, and that is the deliberate difference from node and Go.
# Those two are pinned because the repo declares an exact version it must build
# against (engines.node, and ARG GO_VERSION in .devcontainer/Dockerfile). `gh`
# has no such contract: it talks to GitHub's API, which moves under it, so the
# newest release is the correct one and a pin would rot. Installing from the
# official apt repository means `apt upgrade` keeps it current with no further
# work here.
#
# The commands below are the official ones from
# https://github.com/cli/cli/blob/trunk/docs/install_linux.md, kept verbatim
# rather than paraphrased: they add a signed keyring and an apt source, and
# getting either subtly wrong is a supply-chain problem, not a typo.
setup_gh_cli() {
    if command -v gh >/dev/null 2>&1; then
        log_info "GitHub CLI present ($(gh --version 2>/dev/null | head -1))"
        return 0
    fi

    log_warn "GitHub CLI (gh) is not installed."
    log_warn "  The PR guards run live gh queries and FAIL CLOSED without it,"
    log_warn "  so gh pr create is refused on a machine that lacks gh."

    if [[ "$(uname -s)" == "Darwin" ]]; then
        echo ""
        echo "brew install gh"
        echo ""
        echo "Then re-run: ./run.sh setup"
        echo ""
        return 1
    fi
    if ! command -v apt-get >/dev/null 2>&1; then
        log_error "Only the Debian/Ubuntu apt path is automated here."
        log_error "See https://github.com/cli/cli/blob/trunk/docs/install_linux.md"
        return 1
    fi
    if [[ ! -t 0 ]] || ! command -v sudo >/dev/null 2>&1; then
        log_warn "Cannot install it from here. Official instructions:"
        echo ""
        echo "https://github.com/cli/cli/blob/trunk/docs/install_linux.md"
        echo ""
        echo "Then re-run: ./run.sh setup"
        echo ""
        return 1
    fi

    log_info "Installing gh from the official GitHub apt repository (needs root)."
    if ! prompt_continue "Install the GitHub CLI now?"; then
        log_warn "Skipped. PR commands will be refused until gh is installed."
        return 1
    fi

    # Verbatim from the official docs, split only for readability.
    if ! (type -p wget >/dev/null || (sudo apt-get update && sudo apt-get install wget -y)) \
        || ! sudo mkdir -p -m 755 /etc/apt/keyrings; then
        log_error "Could not prepare /etc/apt/keyrings."
        return 1
    fi
    local out
    out=$(mktemp) || return 1
    if ! wget -nv -O"$out" https://cli.github.com/packages/githubcli-archive-keyring.gpg; then
        log_error "Could not download the GitHub CLI keyring."
        rm -f "$out"; return 1
    fi
    sudo tee /etc/apt/keyrings/githubcli-archive-keyring.gpg >/dev/null <"$out"
    rm -f "$out"
    sudo chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg
    sudo mkdir -p -m 755 /etc/apt/sources.list.d
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
        | sudo tee /etc/apt/sources.list.d/github-cli.list >/dev/null
    if ! sudo apt-get update || ! sudo apt-get install gh -y; then
        log_error "apt could not install gh. See the official instructions:"
        log_error "  https://github.com/cli/cli/blob/trunk/docs/install_linux.md"
        return 1
    fi

    hash -r 2>/dev/null || true
    if ! command -v gh >/dev/null 2>&1; then
        log_error "gh still not resolvable after install."
        return 1
    fi
    log_info "$(gh --version 2>/dev/null | head -1) installed"
    log_warn "Not authenticated yet. Run 'gh auth login' when you need PR commands."
    return 0
}

# Report Docker's real state early. ADVISORY, never fatal.
#
# Docker is NOT globally mandatory and setup must not pretend it is: check_docker
# is called from exactly four places, all in .ci/lib/service.sh, so Docker gates
# `./run.sh service *` and the account stack while CLI work, www work, the test
# suites and every gate run fine without it. Hard-failing setup here would block
# a machine that only ever intends to do CLI or www work.
#
# It is still worth probing at the START rather than leaving it to be discovered
# later, because the failure mode is confusing on WSL: Docker Desktop puts a
# `docker` shim on PATH that EXISTS but cannot reach an engine, so
# `command -v docker` succeeds and the real problem is a WSL-integration toggle
# in a Windows GUI, which no error further down would ever name.
#
# A timeout is mandatory here: `docker info` against a dead engine can sit for a
# long time, and setup must not hang on an advisory check.
setup_docker_probe() {
    if ! command -v docker >/dev/null 2>&1; then
        log_warn "Docker not found. Fine for CLI, www and test work."
        log_warn "Needed for: ./run.sh service *, and the account dev stack."
        return 0
    fi

    if timeout 30 docker info >/dev/null 2>&1; then
        log_info "Docker engine reachable ($(timeout 15 docker version --format '{{.Server.Version}}' 2>/dev/null || echo 'version unknown'))"
        return 0
    fi

    log_warn "Docker CLI is on PATH but no engine answered."
    if grep -qi microsoft /proc/version 2>/dev/null; then
        log_warn "This is WSL, and the usual cause is Docker Desktop's WSL integration"
        log_warn "being off for this distro. Enable it in:"
        log_warn "  Docker Desktop > Settings > Resources > WSL Integration > $(. /etc/os-release 2>/dev/null && echo "${PRETTY_NAME:-this distro}")"
    else
        log_warn "Start Docker Desktop, or: sudo systemctl start docker"
    fi
    log_warn "Not fatal. CLI, www and test work do not need it; ./run.sh service * does."
    return 0
}

# Detect and, if the operator agrees, configure the global git identity.
#
# A fresh machine has no ~/.gitconfig at all, and git does not complain until the
# first commit -- which is the worst moment to find out, because the commit is
# refused mid-flow (or worse, silently attributed to a guessed
# user@hostname if user.useConfigOnly is unset). Setup is the right place to ask.
#
# This NEVER writes without consent, and never prompts when nobody is there to
# answer: a non-TTY stdin (CI, an agent session, a piped run) reports and moves
# on rather than blocking the whole setup on a read that can never return.
setup_git_identity() {
    local cur_name cur_email
    cur_name=$(git config --global user.name || true)
    cur_email=$(git config --global user.email || true)

    if [[ -n "$cur_name" && -n "$cur_email" ]]; then
        log_info "Git identity: $cur_name <$cur_email>"
        return 0
    fi

    log_warn "Git identity is not configured; commits from this machine will fail."

    # Propose this repo's dominant human author, so a second machine matches the
    # history the first one wrote. Bots are excluded by name.
    local suggested
    suggested=$(git log -200 --format='%an <%ae>' 2>/dev/null \
        | grep -v '\[bot\]' | sort | uniq -c | sort -rn | head -1 \
        | sed 's/^ *[0-9]* //')

    if [[ ! -t 0 ]]; then
        log_warn "Non-interactive run; skipping the prompt. Set it yourself with:"
        [[ -n "$suggested" ]] && log_warn "  git config --global user.name  \"${suggested%% <*}\""
        [[ -n "$suggested" ]] && log_warn "  git config --global user.email \"$(printf '%s' "$suggested" | sed 's/.*<//; s/>.*//')\""
        return 0
    fi

    # Initialised explicitly: run.sh runs under `set -u`, where a bare
    # `local want_name` is UNBOUND, not empty, and the -z test below aborts setup.
    local want_name="" want_email=""
    if [[ -n "$suggested" ]]; then
        log_info "This repo's commits are authored by: $suggested"
        if prompt_continue "Use that identity for this machine?"; then
            want_name="${suggested%% <*}"
            want_email=$(printf '%s' "$suggested" | sed 's/.*<//; s/>.*//')
        fi
    fi

    if [[ -z "$want_name" ]]; then
        read -p "  Full name for git commits (blank to skip): " want_name || true
        [[ -z "$want_name" ]] && { log_warn "Skipped; git identity still unset."; return 0; }
        read -p "  Email for git commits (blank to skip): " want_email || true
        [[ -z "$want_email" ]] && { log_warn "Skipped; git identity still unset."; return 0; }
    fi

    git config --global user.name  "$want_name"
    git config --global user.email "$want_email"
    log_info "Git identity set: $want_name <$want_email>"

    # Two more that are unset on a fresh machine and bite later, not now.
    # Only ever ADD them; an existing operator preference is left alone.
    if [[ -z "$(git config --global init.defaultBranch || true)" ]]; then
        git config --global init.defaultBranch main
        log_info "Set init.defaultBranch=main (matches every repo here)"
    fi
    if [[ -z "$(git config --global pull.ff || true)" && -z "$(git config --global pull.rebase || true)" ]]; then
        git config --global pull.ff only
        log_info "Set pull.ff=only (refuses surprise merge commits on pull)"
    fi
}

# Detect, and if necessary help configure, a usable GitHub credential.
#
# BLOCKING on purpose (operator request 2026-08-26). Read access to this repo
# works ANONYMOUSLY -- `git ls-remote origin` succeeds with no credential at all
# -- so the first sign of a missing credential is normally a failed PUSH, long
# after setup said everything was fine. Checking here turns that into an
# up-front, fixable message.
#
# The probe is `git credential fill`, which is helper-agnostic (store,
# osxkeychain, manager, gh's helper all answer it) and, with prompts disabled,
# fails fast instead of hanging.
#
# Escape hatch: SKIP_GIT_CREDENTIAL_CHECK=1 for environments that legitimately
# have no push credential (a read-only CI checkout, a throwaway container).
setup_git_credentials() {
    if [[ "${SKIP_GIT_CREDENTIAL_CHECK:-}" == "1" ]]; then
        log_warn "SKIP_GIT_CREDENTIAL_CHECK=1; not checking GitHub credentials."
        return 0
    fi

    local helper
    helper=$(git config --global credential.helper || true)

    if [[ -z "$helper" ]] && [[ -t 0 ]]; then
        log_warn "No git credential helper configured; git will re-ask for your"
        log_warn "GitHub token on every push."
        # `store` keeps the token in PLAINTEXT at ~/.git-credentials (mode 0600).
        # That is the operator's standing preference on these boxes; a keychain
        # helper is the alternative where one exists.
        if prompt_continue "Set credential.helper=store (token saved in plaintext at ~/.git-credentials)?"; then
            git config --global credential.helper store
            helper=store
            log_info "Set credential.helper=store"
        fi
    fi

    # Does a GitHub credential actually resolve, without prompting?
    local probe_rc=0
    printf 'protocol=https\nhost=github.com\n\n' \
        | GIT_TERMINAL_PROMPT=0 timeout 20 git credential fill >/dev/null 2>&1 || probe_rc=$?

    if [[ $probe_rc -eq 0 ]]; then
        log_info "GitHub credential available${helper:+ (helper: $helper)}"
        return 0
    fi

    log_warn "No GitHub credential stored yet."
    log_warn "Read access works anonymously here, so this would not bite until your"
    log_warn "first push, which is why setup asks now instead."

    # COLLECT IT HERE rather than printing a recipe to run elsewhere.
    #
    # The recipe version of this step was a real usability failure: it told the
    # operator to paste a `git credential approve` heredoc into another shell,
    # and when they did, nothing was stored -- the placeholder had not been
    # substituted and ~/.git-credentials was never created, while setup had
    # already exited. Two disconnected steps, and the failure was silent between
    # them. Identity and credential are one concern (who you are to git and to
    # GitHub), so setup collects all of it in one place and verifies the result.
    if [[ ! -t 0 ]]; then
        log_warn "Non-interactive run; cannot prompt. Store one with:"
        echo ""
        echo "git credential approve <<'CRED'"
        echo "protocol=https"
        echo "host=github.com"
        echo "username=YOUR_GITHUB_USERNAME"
        echo "password=YOUR_TOKEN"
        echo "CRED"
        echo ""
        echo "Then re-run: ./run.sh setup"
        echo "(or set SKIP_GIT_CREDENTIAL_CHECK=1 if this machine has no push credential)"
        echo ""
        return 1
    fi

    # PREFER gh, and only fall back to a hand-pasted token.
    #
    # `gh auth login` runs GitHub's device/OAuth flow and `gh auth setup-git`
    # then registers gh as git's credential helper for github.com, so git gets
    # its credential from gh on demand. That is strictly better than pasting a
    # PAT: no token is ever typed, shown, or written in plaintext to
    # ~/.git-credentials, gh handles renewal, and the scopes come from the flow
    # instead of a checklist someone has to read.
    #
    # IT IS OFFERED, NEVER RUN UNASKED. `gh auth login` is interactive and
    # outward-facing: it opens a browser and authenticates a real account. That
    # is the operator's call every time, so it is a prompt, not a default.
    if command -v gh >/dev/null 2>&1; then
        if gh auth status >/dev/null 2>&1; then
            log_info "gh is already authenticated; wiring it in as git's credential helper."
            if gh auth setup-git >/dev/null 2>&1; then
                local gh_rc=0
                printf 'protocol=https\nhost=github.com\n\n' \
                    | GIT_TERMINAL_PROMPT=0 timeout 20 git credential fill >/dev/null 2>&1 || gh_rc=$?
                if [[ $gh_rc -eq 0 ]]; then
                    log_info "GitHub credential now served by gh; no token to paste."
                    return 0
                fi
                log_warn "gh auth setup-git ran but git still cannot get a credential."
            else
                log_warn "gh auth setup-git failed; falling back to a stored token."
            fi
        else
            echo ""
            echo "  gh is installed but not logged in. Logging in with gh is the better"
            echo "  option: it opens a browser, and afterwards git gets its credential"
            echo "  from gh, so there is no token to create, paste, or keep in a file."
            echo ""
            if prompt_continue "Run 'gh auth login' now?"; then
                if gh auth login && gh auth setup-git; then
                    local gh_rc2=0
                    printf 'protocol=https\nhost=github.com\n\n' \
                        | GIT_TERMINAL_PROMPT=0 timeout 20 git credential fill >/dev/null 2>&1 || gh_rc2=$?
                    if [[ $gh_rc2 -eq 0 ]]; then
                        log_info "Logged in and wired into git; no token to paste."
                        return 0
                    fi
                fi
                log_warn "gh login did not produce a usable git credential."
            fi
        fi
    fi

    echo ""
    echo "  Falling back to a personal access token."
    echo "  Create one at: https://github.com/settings/tokens   (scope: repo)"
    echo ""
    if ! prompt_continue "Enter a GitHub token now and store it?"; then
        log_warn "Skipped. Pushes will fail until a credential is stored."
        return 1
    fi

    local gh_user gh_token
    read -p "  GitHub username: " gh_user
    [[ -z "$gh_user" ]] && { log_error "No username given; nothing stored."; return 1; }

    # -s so the token never appears on screen or in scrollback. It still reaches
    # the credential helper, which for `store` writes ~/.git-credentials in
    # PLAINTEXT at mode 0600; that is the operator's standing choice on these
    # boxes, not a default this script picked.
    read -r -s -p "  GitHub token (input hidden): " gh_token
    echo ""
    [[ -z "$gh_token" ]] && { log_error "No token given; nothing stored."; return 1; }
    if [[ "$gh_token" == "<"*">" ]]; then
        log_error "That looks like a placeholder ('$gh_token'), not a token. Nothing stored."
        return 1
    fi

    printf 'protocol=https\nhost=github.com\nusername=%s\npassword=%s\n\n' \
        "$gh_user" "$gh_token" | git credential approve
    unset gh_token

    # VERIFY, because approve reports nothing and a silently-empty store is
    # exactly what sent the operator round this loop once already.
    local check_rc=0
    printf 'protocol=https\nhost=github.com\n\n' \
        | GIT_TERMINAL_PROMPT=0 timeout 20 git credential fill >/dev/null 2>&1 || check_rc=$?
    if [[ $check_rc -ne 0 ]]; then
        log_error "Stored nothing: the credential helper did not return it back."
        log_error "Check that credential.helper is set (it is: ${helper:-unset})."
        return 1
    fi
    log_info "GitHub credential stored and verified (helper: ${helper:-store})"
    return 0
}

#!/bin/bash
# Build .rpm package from CLI binary with GPG signing
# Usage:
#   build-rpm.sh --binary PATH --version VER --arch {x86_64|aarch64} [--output DIR] [--dry-run]
#
# Options:
#   --binary PATH   Path to the CLI binary
#   --version VER   Package version (e.g., 0.4.44)
#   --arch ARCH     Target architecture: x86_64, aarch64
#   --output DIR    Output directory (default: dist/packages)
#   --dry-run       Preview without building
#
# Environment:
#   GPG_PRIVATE_KEY   GPG private key for signing (base64 or armored)
#   GPG_PASSPHRASE    GPG key passphrase (optional)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"
source "$SCRIPT_DIR/../../config/constants.sh"

# Defaults
BINARY=""
VERSION=""
ARCH=""
OUTPUT_DIR=""
DRY_RUN=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --binary)
            BINARY="$2"
            shift 2
            ;;
        --version)
            VERSION="$2"
            shift 2
            ;;
        --arch)
            ARCH="$2"
            shift 2
            ;;
        --output)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        -h | --help)
            echo "Usage: $0 --binary PATH --version VER --arch {x86_64|aarch64} [--output DIR] [--dry-run]"
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Validate required arguments
if [[ -z "$BINARY" ]]; then
    log_error "Missing required argument: --binary"
    exit 1
fi
if [[ -z "$VERSION" ]]; then
    log_error "Missing required argument: --version"
    exit 1
fi
if [[ -z "$ARCH" ]]; then
    log_error "Missing required argument: --arch"
    exit 1
fi

# Validate architecture
if [[ "$ARCH" != "x86_64" && "$ARCH" != "aarch64" ]]; then
    log_error "Invalid architecture '$ARCH'. Must be 'x86_64' or 'aarch64'"
    exit 1
fi

# Set output directory
if [[ -z "$OUTPUT_DIR" ]]; then
    OUTPUT_DIR="$(get_repo_root)/dist/packages"
fi

# Package filename
RPM_FILE="${PKG_NAME}-${VERSION}-1.${ARCH}.rpm"

log_step "Building .rpm package: $RPM_FILE"
log_info "  Binary: $BINARY"
log_info "  Version: $VERSION"
log_info "  Arch: $ARCH"
log_info "  Output: $OUTPUT_DIR/$RPM_FILE"

if [[ "$DRY_RUN" == "true" ]]; then
    log_info "[DRY-RUN] Would build $RPM_FILE"
    mkdir -p "$OUTPUT_DIR"
    exit 0
fi

# Validate binary exists (after dry-run check — not needed for validation-only runs)
require_file "$BINARY"

# Require rpmbuild
require_cmd rpmbuild

# Create rpmbuild tree in temp directory
RPMBUILD_DIR="$(mktemp -d)"
CLEANUP_DIRS=("$RPMBUILD_DIR")
cleanup() { rm -rf "${CLEANUP_DIRS[@]}"; }
trap cleanup EXIT

mkdir -p "$RPMBUILD_DIR"/{BUILD,RPMS,SOURCES,SPECS,SRPMS}

# Copy binary to SOURCES
cp "$BINARY" "$RPMBUILD_DIR/SOURCES/$PKG_BINARY_NAME"

# Write spec file
cat >"$RPMBUILD_DIR/SPECS/${PKG_NAME}.spec" <<EOF
Name:           ${PKG_NAME}
Version:        ${VERSION}
Release:        1
Summary:        ${PKG_DESCRIPTION}
License:        Proprietary
URL:            ${PKG_HOMEPAGE}
AutoReqProv:    no

# Disable automatic stripping - the SEA binary is pre-stripped during build
# and further stripping corrupts the injected Node.js blob
%global __os_install_post %{nil}
%define __strip /bin/true
%define debug_package %{nil}

%description
${PKG_DESCRIPTION}

%install
mkdir -p %{buildroot}/usr/local/bin
cp %{_sourcedir}/${PKG_BINARY_NAME} %{buildroot}/usr/local/bin/${PKG_BINARY_NAME}
chmod 755 %{buildroot}/usr/local/bin/${PKG_BINARY_NAME}

%files
/usr/local/bin/${PKG_BINARY_NAME}
EOF

# Build the RPM
#
# Workaround: The CLI binary is a Node.js Single Executable Application (SEA)
# with ~158MB of app data injected into an ELF .note section via postject.
# rpmbuild uses libmagic for file classification, which has a hardcoded 128MB
# limit for ELF note sections (NOTE_MAXSIZE in readelf.c). To bypass this, we
# create a minimal magic database that classifies files without deep ELF
# parsing, and point libmagic to it via the MAGIC environment variable.
MAGIC_SRC="$RPMBUILD_DIR/magic"
printf '0\tstring\t\\x7fELF\tapplication/x-executable\n' >"$MAGIC_SRC"
file -C -m "$MAGIC_SRC"

MAGIC="$MAGIC_SRC" rpmbuild -bb \
    --define "_topdir $RPMBUILD_DIR" \
    --target "$ARCH" \
    "$RPMBUILD_DIR/SPECS/${PKG_NAME}.spec"

# Move output RPM to output directory
mkdir -p "$OUTPUT_DIR"
find "$RPMBUILD_DIR/RPMS" -name "*.rpm" -exec cp {} "$OUTPUT_DIR/$RPM_FILE" \;

# Verify
if [[ ! -f "$OUTPUT_DIR/$RPM_FILE" ]]; then
    log_error "RPM build failed: $RPM_FILE not found"
    exit 1
fi

PACKAGE_SIZE=$(wc -c <"$OUTPUT_DIR/$RPM_FILE")
log_info "Package built: $RPM_FILE ($((PACKAGE_SIZE / 1024))KB)"

# =============================================================================
# GPG Signing (if GPG_PRIVATE_KEY is provided)
# =============================================================================
if [[ -n "${GPG_PRIVATE_KEY:-}" ]]; then
    log_step "Signing RPM package..."

    # Setup temporary GPG home
    GNUPGHOME_TMP="$(mktemp -d)"
    export GNUPGHOME="$GNUPGHOME_TMP"

    # Add to cleanup
    CLEANUP_DIRS+=("$GNUPGHOME_TMP")

    # GPG options for non-interactive use
    GPG_OPTS=(--batch --yes --no-tty --pinentry-mode loopback)
    if [[ -n "${GPG_PASSPHRASE:-}" ]]; then
        GPG_OPTS+=(--passphrase "$GPG_PASSPHRASE")
    fi

    # Import the GPG key with error handling
    if ! echo "$GPG_PRIVATE_KEY" | gpg "${GPG_OPTS[@]}" --import; then
        log_error "Failed to import GPG key. Is GPG_PRIVATE_KEY valid?"
        exit 1
    fi
    log_info "GPG private key imported"

    # Get the key ID (use --list-secret-keys for imported private key)
    GPG_KEY_ID=$(gpg --list-secret-keys --with-colons | grep '^sec' | head -1 | cut -d: -f5)
    if [[ -z "$GPG_KEY_ID" ]]; then
        log_error "Could not determine GPG key ID from imported key."
        exit 1
    fi
    log_info "Using GPG key: $GPG_KEY_ID"

    # Build passphrase option for GPG sign command (uses file descriptor to avoid plaintext in file)
    passphrase_opt=""
    if [[ -n "${GPG_PASSPHRASE:-}" ]]; then
        passphrase_opt="--passphrase-file /proc/self/fd/3"
    fi

    # Create RPM macros for signing (passphrase passed via fd, not written to file)
    cat >"$HOME/.rpmmacros" <<MACROS
%_signature gpg
%_gpg_path $GNUPGHOME
%_gpg_name $GPG_KEY_ID
%__gpg /usr/bin/gpg
%__gpg_sign_cmd %{__gpg} gpg --batch --no-verbose --no-armor --pinentry-mode loopback ${passphrase_opt} -u "%{_gpg_name}" -sbo %{__signature_filename} %{__plaintext_filename}
MACROS

    # Sign the RPM (pass passphrase via file descriptor 3 if set)
    if [[ -n "${GPG_PASSPHRASE:-}" ]]; then
        rpm --addsign "$OUTPUT_DIR/$RPM_FILE" 3<<<"$GPG_PASSPHRASE"
    else
        rpm --addsign "$OUTPUT_DIR/$RPM_FILE"
    fi
    log_info "RPM package signed successfully"

    # Verify signature
    if rpm -K "$OUTPUT_DIR/$RPM_FILE" | grep -q "digests signatures OK"; then
        log_info "Signature verification passed"
    else
        log_warn "Signature verification returned unexpected result (package may still be valid)"
    fi
else
    log_warn "GPG_PRIVATE_KEY not set, skipping RPM signing"
fi

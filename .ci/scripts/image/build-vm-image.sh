#!/bin/bash
# Build custom VM image with renet setup pre-applied
# Usage: build-vm-image.sh [--output <path>] [--os <os-name>] [--base-image <url>]
#
# This script builds a VM image by:
# 1. Downloading a base cloud image for the selected OS
# 2. Booting a temporary VM with cloud-init
# 3. Running renet setup inside the VM (installs Docker, CRIU, packages)
# 4. Shutting down and compacting the image
# 5. Outputting the ready-to-use image
#
# The output image can be used with REDIACC_OPS_DISKS_PATH to skip
# the setup phase during VM provisioning.
#
# Required:
#   - KVM/libvirt installed (run: renet ops host setup)
#   - renet binary available at RENET_BINARY or /tmp/renet
#
# Options:
#   --output      Output directory for the image (default: $RUNNER_TEMP/vm-image)
#   --os          OS name: ubuntu-24.04, debian-12, fedora-43, opensuse-15.6 (default: ubuntu-24.04)
#   --base-image  Base image URL (overrides --os)
#
# Examples:
#   .ci/scripts/image/build-vm-image.sh --output /tmp/vm-image
#   .ci/scripts/image/build-vm-image.sh --os debian-12 --output /tmp/vm-image

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# Parse arguments
parse_args "$@"

# OS image configuration
# Maps OS name to (image URL, virt-install os-variant)
declare -A OS_IMAGES=(
    ["ubuntu-24.04"]="https://cloud-images.ubuntu.com/minimal/releases/noble/release/ubuntu-24.04-minimal-cloudimg-amd64.img"
    ["debian-12"]="https://cloud.debian.org/images/cloud/bookworm/latest/debian-12-generic-amd64.qcow2"
    ["fedora-43"]="https://download.fedoraproject.org/pub/fedora/linux/releases/43/Cloud/x86_64/images/Fedora-Cloud-Base-Generic-43-1.6.x86_64.qcow2"
    ["opensuse-15.6"]="https://download.opensuse.org/distribution/leap/15.6/appliances/openSUSE-Leap-15.6-Minimal-VM.x86_64-Cloud.qcow2"
)

declare -A OS_VARIANTS=(
    ["ubuntu-24.04"]="ubuntu24.04"
    ["debian-12"]="debian12"
    ["fedora-43"]="fedora-unknown"
    ["opensuse-15.6"]="opensuse15.5"
)

# Configuration
OUTPUT_DIR="${ARG_OUTPUT:-${RUNNER_TEMP:-/tmp}/vm-image}"
OS_NAME="${ARG_OS:-ubuntu-24.04}"

# Validate OS name
if [[ -z "${OS_IMAGES[$OS_NAME]:-}" ]]; then
    log_error "Unknown OS: $OS_NAME"
    log_error "Supported: ${!OS_IMAGES[*]}"
    exit 1
fi

# Use explicit base-image if provided, otherwise use OS mapping
BASE_IMAGE_URL="${ARG_BASE_IMAGE:-${OS_IMAGES[$OS_NAME]}}"
BASE_IMAGE_NAME="$(basename "$BASE_IMAGE_URL")"
OS_VARIANT="${OS_VARIANTS[$OS_NAME]}"
RENET_BINARY="${RENET_BINARY:-/tmp/renet}"

# VM configuration (matches renet defaults)
VM_RAM="${VM_RAM:-4096}"
VM_CPU="${VM_CPU:-2}"
VM_NET="${VM_NET:-default}"

# Build directory for temporary files (use /tmp for libvirt-qemu access)
BUILD_DIR="/tmp/rediacc-image-build-$$"

# Require renet binary
require_cmd "$RENET_BINARY" "renet binary not found at $RENET_BINARY"

# Ensure default network is active (created by libvirt installation)
log_info "Ensuring libvirt default network is active..."
sudo virsh net-start default 2>/dev/null || true

log_step "Building VM image with renet setup"
log_info "OS: $OS_NAME"
log_info "Base image: $BASE_IMAGE_NAME"
log_info "OS variant: $OS_VARIANT"
log_info "Output dir: $OUTPUT_DIR"
log_info "Build dir: $BUILD_DIR"

# Create directories
mkdir -p "$OUTPUT_DIR"
mkdir -p "$BUILD_DIR"

# Cleanup function
cleanup() {
    local exit_code=$?
    log_step "Cleaning up..."

    # Destroy and undefine the build VM if it exists
    if [[ -n "${VM_NAME:-}" ]]; then
        sudo virsh destroy "$VM_NAME" 2>/dev/null || true
        sudo virsh undefine "$VM_NAME" 2>/dev/null || true
    fi

    # Remove build directory
    rm -rf "$BUILD_DIR"

    if [[ $exit_code -eq 0 ]]; then
        log_info "Cleanup complete"
    else
        log_error "Build failed with exit code $exit_code"
    fi
}
trap cleanup EXIT INT TERM

# =============================================================================
# STEP 1: Download base image
# =============================================================================
log_step "Step 1/8: Downloading base image..."

BASE_IMAGE_PATH="$BUILD_DIR/$BASE_IMAGE_NAME"
if [[ -f "$BASE_IMAGE_PATH" ]]; then
    log_info "Base image already exists"
else
    log_info "Downloading from $BASE_IMAGE_URL"
    wget -q --show-progress -O "$BASE_IMAGE_PATH" "$BASE_IMAGE_URL"
fi
log_info "Base image: $(du -h "$BASE_IMAGE_PATH" | cut -f1)"

# =============================================================================
# STEP 2: Create working copy
# =============================================================================
log_step "Step 2/8: Creating working copy..."

WORK_IMAGE="$BUILD_DIR/work.qcow2"
cp "$BASE_IMAGE_PATH" "$WORK_IMAGE"

# Resize to add space for packages
qemu-img resize "$WORK_IMAGE" +4G
log_info "Working image resized to $(qemu-img info "$WORK_IMAGE" | grep 'virtual size' | awk '{print $3}')"

# Make build directory accessible to libvirt-qemu user
chmod 755 "$BUILD_DIR"
chmod 666 "$WORK_IMAGE"

# =============================================================================
# STEP 3: Generate SSH key for build
# =============================================================================
log_step "Step 3/8: Generating SSH key..."

BUILD_KEY="$BUILD_DIR/build_key"
ssh-keygen -t rsa -b 2048 -f "$BUILD_KEY" -N "" -q
log_info "SSH key generated"

# =============================================================================
# STEP 4: Create cloud-init config
# =============================================================================
log_step "Step 4/8: Creating cloud-init config..."

USER_DATA="$BUILD_DIR/user-data"
META_DATA="$BUILD_DIR/meta-data"
SEED_ISO="$BUILD_DIR/seed.iso"

cat >"$USER_DATA" <<EOF
#cloud-config
users:
  - default
  - name: builder
    shell: /bin/bash
    sudo: ALL=(ALL) NOPASSWD:ALL
    ssh_authorized_keys:
      - $(cat "${BUILD_KEY}.pub")

chpasswd:
  list: |
    builder:builder123
  expire: false

ssh_pwauth: true

EOF

cat >"$META_DATA" <<EOF
instance-id: renet-image-builder
local-hostname: renet-builder
EOF

# Create seed ISO for cloud-init
cloud-localds "$SEED_ISO" "$USER_DATA" "$META_DATA"
chmod 644 "$SEED_ISO"
log_info "Cloud-init ISO created"

# =============================================================================
# STEP 5: Boot VM
# =============================================================================
log_step "Step 5/8: Booting build VM..."

VM_NAME="renet-image-builder-$$"
MAC_ADDR="52:54:00:$(openssl rand -hex 3 | sed 's/\(..\)/\1:/g; s/:$//')"

# Start VM
sudo virt-install \
    --name "$VM_NAME" \
    --memory "$VM_RAM" \
    --vcpus "$VM_CPU" \
    --disk "path=$WORK_IMAGE,format=qcow2" \
    --disk "path=$SEED_ISO,format=raw" \
    --os-variant "$OS_VARIANT" \
    --network "network=$VM_NET,model=virtio,mac=$MAC_ADDR" \
    --graphics none \
    --noautoconsole \
    --quiet \
    --import

log_info "VM started: $VM_NAME"

# Wait for VM to be ready
log_info "Waiting for VM to boot and get IP..."
RETRIES=60
VM_IP=""
while [[ $RETRIES -gt 0 ]]; do
    if sudo virsh domstate "$VM_NAME" 2>/dev/null | grep -q "running"; then
        VM_IP=$(sudo virsh domifaddr "$VM_NAME" 2>/dev/null | grep -oE '192\.168\.[0-9]+\.[0-9]+' | head -1 || true)
        if [[ -n "$VM_IP" ]]; then
            # Try SSH connection
            if ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
                -i "$BUILD_KEY" "builder@$VM_IP" true 2>/dev/null; then
                log_info "VM is ready at $VM_IP"
                break
            fi
        fi
    fi
    sleep 5
    ((RETRIES--))
done

if [[ -z "$VM_IP" ]] || [[ $RETRIES -eq 0 ]]; then
    log_error "Failed to connect to build VM"
    sudo virsh domifaddr "$VM_NAME" 2>/dev/null || true
    exit 1
fi

# =============================================================================
# STEP 6: Copy renet and run setup
# =============================================================================
log_step "Step 6/8: Running renet setup inside VM..."

# SSH options for build
SSH_OPTS="-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i $BUILD_KEY"

# Copy renet binary to VM
log_info "Copying renet binary to VM..."
scp $SSH_OPTS "$RENET_BINARY" "builder@$VM_IP:/tmp/renet"
ssh $SSH_OPTS "builder@$VM_IP" "chmod +x /tmp/renet"

# Run renet setup
log_info "Running renet setup (this installs Docker, CRIU, packages)..."
ssh $SSH_OPTS "builder@$VM_IP" "sudo /tmp/renet setup --auto" 2>&1 | tee "$BUILD_DIR/setup.log" || {
    log_error "renet setup failed. Check $BUILD_DIR/setup.log"
    exit 1
}

log_info "renet setup completed successfully"

# Clean up inside VM (use package manager appropriate for the OS)
log_info "Cleaning up VM..."
ssh $SSH_OPTS "builder@$VM_IP" "sudo rm -f /tmp/renet && \
  if command -v apt-get &>/dev/null; then sudo apt-get clean && sudo rm -rf /var/cache/apt/archives/*; \
  elif command -v dnf &>/dev/null; then sudo dnf clean all; \
  elif command -v zypper &>/dev/null; then sudo zypper clean --all; \
  fi"

# =============================================================================
# STEP 7: Shutdown VM
# =============================================================================
log_step "Step 7/8: Shutting down VM..."

ssh $SSH_OPTS "builder@$VM_IP" "sudo shutdown -h now" 2>/dev/null || true

# Wait for VM to shut down
RETRIES=30
while [[ $RETRIES -gt 0 ]] && sudo virsh domstate "$VM_NAME" 2>/dev/null | grep -q "running"; do
    sleep 2
    ((RETRIES--))
done

if sudo virsh domstate "$VM_NAME" 2>/dev/null | grep -q "running"; then
    log_warn "VM didn't shut down gracefully, forcing..."
    sudo virsh destroy "$VM_NAME"
fi

# Undefine VM (keep the disk)
sudo virsh undefine "$VM_NAME" 2>/dev/null || true
VM_NAME="" # Clear so cleanup doesn't try again

log_info "VM shut down"

# =============================================================================
# STEP 8: Compact and output image
# =============================================================================
log_step "Step 8/8: Compacting image..."

OUTPUT_IMAGE="$OUTPUT_DIR/$BASE_IMAGE_NAME"

# Use virt-sparsify if available, otherwise qemu-img convert
if command -v virt-sparsify &>/dev/null; then
    log_info "Using virt-sparsify for optimal compression..."
    sudo virt-sparsify --compress "$WORK_IMAGE" "$OUTPUT_IMAGE"
    sudo chown "$(id -u):$(id -g)" "$OUTPUT_IMAGE"
else
    log_info "Using qemu-img convert..."
    qemu-img convert -O qcow2 -c "$WORK_IMAGE" "$OUTPUT_IMAGE"
fi

# Show final image size
FINAL_SIZE=$(du -h "$OUTPUT_IMAGE" | cut -f1)
log_info "Final image: $OUTPUT_IMAGE ($FINAL_SIZE)"

# Verify the image
log_step "Verifying image..."
qemu-img check "$OUTPUT_IMAGE" || {
    log_error "Image verification failed"
    exit 1
}

log_info "Image built successfully!"
log_info "  Path: $OUTPUT_IMAGE"
log_info "  Size: $FINAL_SIZE"
log_info ""
log_info "To use this image, set:"
log_info "  export REDIACC_OPS_DISKS_PATH=$(dirname "$OUTPUT_IMAGE")"

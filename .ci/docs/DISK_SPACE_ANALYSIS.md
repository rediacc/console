# Disk Space Analysis: "No space left on device" in wait-for-signals.sh

## Executive Summary

The `wait-for-signals.sh` script fails with "No space left on device" when creating temporary directories for artifact download verification. Despite the artifact being only ~8KB, the failure occurs because the **filesystem is already at capacity** from earlier job steps.

**Root Cause**: The Infra-Backend job runs multiple disk-intensive operations (Docker images, npm install, VM provisioning) before `wait-for-signals.sh` executes, exhausting the runner's disk space.

---

## Investigation Findings

### 1. RUNNER_TEMP is NOT a Separate Filesystem

The fix to use `$RUNNER_TEMP` (`/home/runner/work/_temp`) instead of `/tmp` does not help because both are on the **same filesystem**.

```
GitHub Actions ubuntu-latest runner disk layout:
/ (root)        - 80-100GB total
├── /tmp        - Same filesystem
├── /home/runner/work/_temp (RUNNER_TEMP) - Same filesystem
└── /home/runner/work/... (workspace) - Same filesystem
```

When one fills up, all locations fail.

### 2. Timeline of Disk Consumption (Infra-Backend Job)

| Step | Operation | Estimated Disk Usage |
|------|-----------|---------------------|
| 1 | `actions/checkout` (with submodules) | ~500MB - 1GB |
| 2 | `ci-pull-images.sh` - 3 Docker images (web, api, bridge) | ~3-5GB |
| 3 | Docker overlay2 storage for running containers | ~1-2GB |
| 4 | `npm ci` - node_modules | ~1.5-2GB |
| 5 | `npm run build:*` - Build artifacts | ~500MB |
| 6 | VM provisioning - KVM disk images (3 VMs) | ~10-30GB |
| 7 | Total accumulated | **~17-40GB** |

GitHub Actions `ubuntu-latest` provides **~14GB free** by default (after system overhead).

### 3. Why the Signal Check Fails

The `check_signal_status()` function needs only **~8KB** per signal artifact:
- `complete.txt` file: ~10 bytes
- Directory structure overhead: ~4KB

But by the time `wait-for-signals.sh` runs (after all provisioning):
```
Step 182 (wait-for-signals.sh) runs AFTER:
- Step 74: Pull Docker images
- Steps 83-110: Start backend services
- Steps 112-125: npm install + build
- Steps 153-172: VM provisioning (if enabled)
```

The disk is already at or near capacity when signal checking begins.

### 4. Artifact Download Behavior

When `gh run download` runs, it:
1. Creates temp directory (needs ~4KB)
2. Downloads artifact zip (varies)
3. Extracts to temp directory
4. Reads `complete.txt`
5. Cleans up

Even with proper cleanup (which we now have with `trap ... RETURN`), the initial directory creation fails when the filesystem is full.

---

## Solutions

### Option A: Pre-cleanup Before Signal Wait (Recommended)

Add disk cleanup step before `wait-for-signals.sh`:

```yaml
- name: Cleanup to free disk space
  if: inputs.provision_vms
  run: |
    # Remove Docker build cache
    docker system prune -f --volumes
    # Remove npm cache (builds already done)
    npm cache clean --force
    # Remove extracted renet binary if no longer needed
    rm -f /tmp/renet
```

**Pros**: Minimal workflow change, reclaims significant space
**Cons**: May interfere with log collection if cleanup is too aggressive

### Option B: Use GitHub API Instead of Artifact Download

Instead of downloading artifacts to check status, use the GitHub API to check artifact metadata:

```bash
# Current approach (downloads artifact):
gh run download "$RUN_ID" --name "$artifact_name" --dir "$temp_dir"
cat "$temp_dir/complete.txt"

# Alternative approach (API only, no disk needed):
# Store status in artifact name itself: test-complete-cli-Linux-success
# Or use a different signaling mechanism
```

**Pros**: Zero disk usage for signal checking
**Cons**: Requires changing the signal creation scripts

### Option C: Use Larger Runner

Switch `infra-backend` from `ubuntu-latest` to a larger runner with more disk:

```yaml
infra-backend:
  runs-on: ubuntu-latest-xlarge  # or custom runner with larger disk
```

**Pros**: Simple fix, no code changes
**Cons**: Increases CI costs

### Option D: Stream Artifact Content via API

Use `gh api` to read artifact content without downloading:

```bash
# Get artifact download URL
artifact_url=$(gh api "repos/$REPO/actions/artifacts/$ID/zip" --jq '.url')
# Stream and read first file
curl -sL "$artifact_url" | unzip -p - complete.txt
```

**Pros**: No temp directory needed
**Cons**: More complex, requires artifact ID lookup

---

## Immediate Recommendation

**Implement Option A** - Add cleanup step before `wait-for-signals.sh`:

```yaml
- name: Free disk space before signal wait
  run: |
    echo "Disk usage before cleanup:"
    df -h /
    # Remove Docker build cache and unused images
    docker system prune -af --volumes 2>/dev/null || true
    # Clear npm cache
    npm cache clean --force 2>/dev/null || true
    echo "Disk usage after cleanup:"
    df -h /
```

This is the lowest-risk, fastest-to-implement solution that addresses the root cause.

---

## Why Error Handling Matters

The previous code used `|| true` to silently ignore failures:

```bash
# BAD: Silently ignores disk space errors
check_signal_status "cli-macOS" "test-complete-cli-macOS" || true
```

This masks real problems. The improved version properly tracks failures:

```bash
# GOOD: Track unknown status for later reporting
if ! temp_dir=$(mktemp -d "${TEMP_BASE}/signal-check.XXXXXX" 2>&1); then
    log_error "Failed to create temp directory: $temp_dir"
    UNKNOWN_STATUS_SIGNALS+=("$signal")
    return 2
fi
```

Now the job properly reports which signals couldn't be verified, enabling investigation rather than silent failures.

---

## Appendix: Disk Usage Commands for Debugging

Add these to CI for debugging disk issues:

```bash
# Show filesystem usage
df -h

# Show largest directories
du -sh /* 2>/dev/null | sort -rh | head -20

# Show Docker disk usage
docker system df

# Show npm cache size
npm cache ls 2>/dev/null | wc -l || echo "npm cache unavailable"
```

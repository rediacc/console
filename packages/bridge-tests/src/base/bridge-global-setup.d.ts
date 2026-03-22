import { FullConfig } from '@playwright/test';
/**
 * Global setup for bridge tests.
 *
 * EXECUTION MODEL: All tests run on VMs via SSH
 * Host → Bridge VM → SSH → Worker/Ceph VM → renet command
 *
 * Setup sequence:
 * 1. Soft reset VMs (ops up --force --parallel) - includes Ceph provisioning if enabled
 * 2. Deploy renet binary to all VMs
 * 3. Run renet setup on ALL VMs (bridge + workers) to install Docker and dependencies
 * 4. Verify all VMs are ready (bridge + workers + ceph)
 * 5. Start RustFS S3 storage on bridge VM
 * 6. Configure rclone on workers for RustFS access
 * 7. Initialize datastores on worker VMs
 * 8. Deploy CRIU to worker VMs
 *
 * RENET BINARY:
 * The renet binary must be available before running tests. In CI, it's pre-extracted
 * from the Docker image. Locally, build with: cd renet && ./go dev
 *
 * NOTE: Ceph provisioning is automatically handled by `ops up` when VM_CEPH_NODES is configured.
 * Do NOT call provisionCeph() separately as this causes duplicate provisioning conflicts.
 */
declare function bridgeGlobalSetup(_config: FullConfig): Promise<void>;
export default bridgeGlobalSetup;
//# sourceMappingURL=bridge-global-setup.d.ts.map

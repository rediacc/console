import type { OpsBackend } from '../../services/executor/ops-executor.js';

/** Values accepted by --backend on the ops commands; typed as OpsBackend so a value outside the union fails the build. */
export const OPS_BACKEND_CHOICES: readonly OpsBackend[] = ['kvm', 'qemu', 'hyperv'];

import type { OpsBackend } from '../../services/executor/ops-executor.js';

/** Every OpsBackend, keyed: an object literal must name each union member, so a backend added to OpsBackend and left out here fails the build. */
const OPS_BACKENDS: Record<OpsBackend, true> = { kvm: true, qemu: true, hyperv: true };

/** Values accepted by --backend on the ops commands, derived from the keyed record above. */
export const OPS_BACKEND_CHOICES: readonly OpsBackend[] = Object.keys(OPS_BACKENDS) as OpsBackend[];

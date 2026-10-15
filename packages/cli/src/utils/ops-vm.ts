/**
 * The local ops VM fleet is development-only (operator ruling 2026-10-15,
 * .claude/agents/ops-vms.md "Agent-mode guardrails"): every machine on the
 * fleet's network is disposable, so the agent-mode grand protections do not
 * apply to it. This module is the ONE predicate the guards share.
 *
 * The exemption keys on the machine's CONFIGURED ADDRESS, never on its name: a
 * machine called `ops-worker` that points at a production host keeps every
 * protection. Repointing a machine's address moves the SSH target with it, so
 * the address the guard reads is the address the command then reaches.
 *
 * The network is the /24 of the fleet's bridge (`VM_NETWORK.BRIDGE_IP` in
 * @rediacc/shared), read from that constant rather than a second literal. It is
 * deliberately NOT read from `VM_NET_BASE`: an environment variable is set by
 * whoever runs the CLI, including the agent the guards exist for.
 */
import { VM_NETWORK } from '@rediacc/shared/config';
import type { Placement } from '@rediacc/shared/config-schema';
import { configService } from '../services/config/config-resources.js';

/** `192.168.111.` for the default fleet: the bridge address without its host octet. */
const OPS_VM_NET_PREFIX = VM_NETWORK.BRIDGE_IP.slice(0, VM_NETWORK.BRIDGE_IP.lastIndexOf('.') + 1);

const OCTET = /^(0|[1-9]\d{0,2})$/;

/**
 * True only for a dotted IPv4 literal inside the ops fleet's /24. A hostname,
 * an IPv6 address, or anything that merely STARTS with the prefix
 * (`192.168.111.5.example.com`) is not an ops VM.
 */
export function isOpsVmAddress(address: string): boolean {
  const octets = address.split('.');
  if (octets.length !== 4) return false;
  if (!octets.every((o) => OCTET.test(o) && Number(o) <= 255)) return false;
  return `${octets.slice(0, 3).join('.')}.` === OPS_VM_NET_PREFIX;
}

/** True when the named machine exists in the active config and its address is an ops VM. */
export async function isOpsVmMachine(machineName: string | undefined): Promise<boolean> {
  if (!machineName) return false;
  const config = await configService.getCurrent();
  const ip = config?.resources?.machines?.[machineName]?.ip;
  return typeof ip === 'string' && isOpsVmAddress(ip);
}

/**
 * True when a repo placement executes on an ops VM: the machine arm names one
 * directly; the datastore arm resolves through the datastore's current attach
 * machine. A cluster datastore stays protected, because a cluster command
 * reaches every node of the cluster, not the one machine the attach names.
 */
export async function isOpsVmPlacement(placement: Placement | undefined): Promise<boolean> {
  if (!placement) return false;
  if ('machine' in placement) return isOpsVmMachine(placement.machine);
  const config = await configService.getCurrent();
  const ds = config?.resources?.datastores?.[placement.datastore];
  if (!ds || ds.cluster !== undefined) return false;
  return isOpsVmMachine(config?.state?.datastores?.[placement.datastore]?.attachedTo);
}

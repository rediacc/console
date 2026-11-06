import type { ExecResult } from './types';

type RunOnMachine = (command: string, timeout?: number) => Promise<ExecResult>;

/**
 * The value of a backup verb's known-hosts flag for a peer the suite names by address.
 *
 * Production pins the key `rdc machine scan-keys` recorded. A suite has no such record and its VMs are rebuilt between runs, so it scans the peer from the machine that will connect to it, on the private fleet network. A peer that answers nothing yields an empty value: the flag stays off and the verb gives its coded refusal (exit 20), rather than the suite hiding the failure.
 */
export async function peerKnownHosts(run: RunOnMachine, host: string): Promise<string> {
  // Single-quoted: a machine name with shell metacharacters is data here, not part of the command.
  const quoted = `'${host.replaceAll("'", "'\\''")}'`;
  const scanned = await run(`ssh-keyscan -T 5 ${quoted} 2>/dev/null | base64 -w0`, 30_000);

  return scanned.code === 0 ? scanned.stdout.trim() : '';
}

/** ` --<flag> <value>` for a command line, or nothing when the peer answered nothing. */
export async function peerKnownHostsArg(
  run: RunOnMachine,
  flag: 'dest-known-hosts' | 'src-known-hosts',
  host: string
): Promise<string> {
  const value = await peerKnownHosts(run, host);

  return value ? ` --${flag} ${value}` : '';
}

/**
 * The vault form of the flags above: a literal `dest_machine` / `source_machine` param gets its scanned record as `dest_known_hosts` / `source_known_hosts`. A peer that answered nothing leaves the key OUT, as the flag form leaves the flag out, so the verb gives its coded refusal rather than reading an empty record; a record the caller already supplied is kept as given.
 */
export async function peerKnownHostParams(
  run: RunOnMachine,
  params: Record<string, unknown>
): Promise<Record<string, unknown>> {
  const out = { ...params };
  for (const [machineKey, recordKey] of [
    ['dest_machine', 'dest_known_hosts'],
    ['source_machine', 'source_known_hosts'],
  ] as const) {
    const machine = params[machineKey];
    if (typeof machine !== 'string') continue;
    const record = await peerKnownHosts(run, machine);
    if (record) out[recordKey] = record;
  }

  return out;
}

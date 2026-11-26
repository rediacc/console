import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { homedir } from 'node:os';
import path from 'node:path';
import { DEFAULTS } from '@rediacc/shared/config';
import { Command, Option } from 'commander';
import { t } from '../../i18n/index.js';
import { outputService } from '../../services/core/output.js';
import { setExitCode } from '../../services/core/request-context.js';
import type { OpsBackend } from '../../services/executor/ops-executor.js';
import { opsExecutorService } from '../../services/executor/ops-executor.js';
import { assertCommandNotBlank } from '../../utils/command-blank.js';
import { handleError } from '../../utils/errors.js';

/** One VM of `renet ops status --json`: `ip` is a bare host, `ssh_port` is set for a forwarded sshd. */
export interface OpsVMInfo {
  id: number;
  name: string;
  ip: string;
  status: string;
  ssh_port?: number;
}

interface OpsStatusResponse {
  vms: OpsVMInfo[];
}

/**
 * Split a VM's ssh endpoint into host and port. `ssh_port` wins; without it, an `ip` an older renet packed
 * as `host:port` (or `[v6]:port`) is split, since ssh reads "127.0.0.1:22211" as a hostname. A bare IPv6
 * address (more than one colon, no brackets) is a host with no port.
 */
export function vmSSHEndpoint(vm: Pick<OpsVMInfo, 'ip' | 'ssh_port'>): {
  host: string;
  port?: number;
} {
  const ip = vm.ip.trim();
  let host = ip;
  let port: number | undefined;
  const bracketed = /^\[([^\]]+)\](?::(\d+))?$/.exec(ip);
  if (bracketed) {
    host = bracketed[1];
    port = bracketed[2] ? Number(bracketed[2]) : undefined;
  } else {
    const hostPort = /^([^:]+):(\d+)$/.exec(ip);
    if (hostPort) {
      host = hostPort[1];
      port = Number(hostPort[2]);
    }
  }
  if (vm.ssh_port) port = vm.ssh_port;
  return { host, port };
}

/**
 * The staging private key renet's own VM probe uses, by renet's path rule (pkg/infra/opsconfig
 * loadDefaults): <data dir>/staging/.ssh/id_rsa, where the data dir is RENET_DATA_DIR, else under CI
 * $RUNNER_TEMP/renet or /tmp/renet, else ~/.renet.
 */
export function renetStagingKeyPath(
  env: NodeJS.ProcessEnv = process.env,
  home: string = homedir()
): string {
  let dataDir: string;
  if (env.RENET_DATA_DIR) {
    dataDir = env.RENET_DATA_DIR;
  } else if (env.CI === 'true') {
    dataDir = env.RUNNER_TEMP ? path.join(env.RUNNER_TEMP, 'renet') : '/tmp/renet';
  } else {
    dataDir = path.join(home, '.renet');
  }
  return path.join(dataDir, 'staging', '.ssh', 'id_rsa');
}

/**
 * The ssh argv for one ops VM: the bare host with `-p` for a forwarded port, never `localhost` (on
 * Windows it resolves to ::1 first and the IPv4-only NAT and QEMU forwards refuse it), and the staging
 * key with IdentitiesOnly when it exists, since rdc loads no key into an agent. UserKnownHostsFile stays
 * /dev/null on win32 too: Win32-OpenSSH maps /dev/null to NUL itself, and renet's Hyper-V probe logs in
 * with the same option on Windows.
 */
export function buildOpsSSHArgs(opts: {
  vm: Pick<OpsVMInfo, 'ip' | 'ssh_port'>;
  user: string;
  command?: string;
  keyPath?: string;
}): string[] {
  const { host, port } = vmSSHEndpoint(opts.vm);
  const args = [
    '-o',
    'StrictHostKeyChecking=no',
    '-o',
    'UserKnownHostsFile=/dev/null',
    '-o',
    'LogLevel=ERROR',
  ];
  if (port) args.push('-p', String(port));
  if (opts.keyPath) args.push('-i', opts.keyPath, '-o', 'IdentitiesOnly=yes');
  args.push(`${opts.user}@${host}`);
  if (opts.command) args.push('--', opts.command);
  return args;
}

export function registerOpsSSHCommand(ops: Command, _program: Command): void {
  ops
    .command('ssh')
    .summary(t('commands.ops.ssh.descriptionShort'))
    .description(t('commands.ops.ssh.description'))
    .requiredOption('--vm-id <id>', t('options.vmId'))
    .option('-c, --command <cmd>', t('options.command'))
    .addOption(new Option('--backend <backend>', t('options.opsBackend')).choices(['kvm', 'qemu']))
    .option('--user <user>', t('options.opsSSHUser'))
    .action(
      async (options: { vmId: string; command?: string; backend?: string; user?: string }) => {
        try {
          assertCommandNotBlank({ command: options.command });
          const vmId = options.vmId;
          const backend = options.backend ? (options.backend as OpsBackend) : undefined;
          const response = await opsExecutorService.runOpsJSON<OpsStatusResponse>('status', [], {
            backend,
          });

          const targetId = Number.parseInt(vmId, 10);
          const vm = response.vms.find((v) => v.id === targetId);

          if (vm?.status !== 'running') {
            outputService.error(t('commands.ops.ssh.vmNotFound', { id: vmId }));
            setExitCode(1);
            return;
          }

          const user = options.user ?? process.env.USER ?? DEFAULTS.CLI_TEST.VM_USER;
          const stagingKey = renetStagingKeyPath();
          const sshArgs = buildOpsSSHArgs({
            vm,
            user,
            command: options.command,
            keyPath: existsSync(stagingKey) ? stagingKey : undefined,
          });

          outputService.info(t('commands.ops.ssh.connecting', { id: vmId }));

          const child = spawn('ssh', sshArgs, { stdio: 'inherit' });
          child.on('close', (code) => {
            setExitCode(code ?? 0);
          });
        } catch (error) {
          handleError(error);
        }
      }
    );
}

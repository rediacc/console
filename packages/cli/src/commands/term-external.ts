import { t } from '../i18n/index.js';
import type { SSHConnection } from '../remote/ssh/index.js';
import { getDefaultTerminalType, launchTerminal } from '../remote/terminal/index.js';
import { getPlatform } from '../remote/utils/platform.js';
import { outputService } from '../services/core/output.js';
import type { ConnectionDetails } from '../services/machine/ssh-connection.js';
import { splitSecretEnv } from '../utils/secret-env.js';
import { shellQuote } from '../utils/shell-quote.js';

/**
 * An external terminal that did not open. With `--external` the user asked for that window, so the command refuses with the reason; otherwise the choice was a default, and the session goes inline after a warning that names the reason.
 */
export function reportExternalLaunchFailure(error: unknown, externalRequired: boolean): void {
  const reason = error instanceof Error ? error.message : String(error);
  if (externalRequired) {
    throw new Error(t('errors.term.externalRefused', { error: reason }));
  }
  outputService.warn(t('commands.term.externalFallback', { error: reason }));
}

/** The Windows terminals whose launch line deletes the handed-off files when ssh ends. */
const WINDOWS_CLEANUP_TERMINALS: ReadonlySet<string> = new Set([
  'windows-terminal',
  'cmd',
  'powershell',
]);

type HandoffResources = SSHConnection['handoffResources'];

/** The resources the external terminal takes over, or undefined when the parent keeps them. */
function planHandoff(
  resources: HandoffResources,
  terminalType: string,
  onWindows: boolean
): HandoffResources | undefined {
  // All or nothing: with an agent pid the wrapper cannot put in its script, everything stays with the parent, whose cleanup stops that agent. Handing off only the files would not help, since the parent would still stop the agent the external ssh authenticates through.
  const eligible = !resources.agentPid || isNumericPid(resources.agentPid);
  const terminalOk = !onWindows || WINDOWS_CLEANUP_TERMINALS.has(terminalType);
  return eligible && terminalOk ? resources : undefined;
}

/** Wait briefly for async spawn errors (e.g. ENOENT when the terminal binary is missing). */
async function waitForSpawnError(result: ReturnType<typeof launchTerminal>): Promise<void> {
  if (!result.process) return;
  await new Promise<void>((resolve, reject) => {
    const timer = setTimeout(resolve, 500);
    result.process!.once('error', (err: Error) => {
      clearTimeout(timer);
      reject(new Error(t('errors.term.launchFailed', { error: err.message })));
    });
  });
}

export async function launchExternalTerminal(
  sshConnection: SSHConnection,
  destination: string,
  remoteCommand: string | undefined,
  title: string,
  connectionDetails: ConnectionDetails
): Promise<void> {
  const sshArgv = ['ssh', ...sshConnection.sshOptions, destination];
  if (remoteCommand) {
    sshArgv.push(remoteCommand);
  }
  const terminalType = getDefaultTerminalType();
  // The external terminal's ssh outlives this process's 500 ms wait, so the credentials move to it. On POSIX it gets the agent socket in its env and its shell removes the key and stops the agent when ssh ends. On Windows the cmd/PowerShell line itself deletes the key and known_hosts when ssh ends (the launcher's cleanupFiles), and the parent skips its own deletion.
  const onWindows = getPlatform() === 'windows';
  const handoff = planHandoff(sshConnection.handoffResources, terminalType, onWindows);
  const argv = handoff && !onWindows ? buildHandoffArgv(sshArgv, handoff) : sshArgv;
  const cleanupFiles =
    handoff && onWindows
      ? [handoff.keyFilePath, handoff.knownHostsPath].filter((f): f is string => !!f)
      : [];

  outputService.info(t('commands.term.launchingTerminal', { type: terminalType }));

  const result = launchTerminal(terminalType, {
    argv,
    title,
    keepOpen: true,
    ...(cleanupFiles.length > 0 && { cleanupFiles }),
    environmentVariables: {
      ...splitSecretEnv(connectionDetails.environment).plain,
      ...(handoff?.agentSocketPath && { SSH_AUTH_SOCK: handoff.agentSocketPath }),
    },
    // No workingDirectory: the repo path is REMOTE, and the launchers use it as the local terminal's cwd. The remote `cd` runs inside the ssh command (buildRemoteCommand).
  });

  if (!result.success) {
    throw new Error(t('errors.term.launchFailed', { error: result.error }));
  }

  await waitForSpawnError(result);

  // Launched: the terminal's shell now owns the credentials.
  if (handoff) sshConnection.release();

  outputService.info(t('commands.term.launchSuccess'));
}

function isNumericPid(pid: string): boolean {
  return /^\d+$/.test(pid);
}

/**
 * Wraps the ssh argv in `sh -c` so the launched terminal removes the temp key
 * files and stops the agent when ssh exits or the terminal is hung up. Only
 * paths and a numeric pid appear on argv, never key material.
 */
export function buildHandoffArgv(
  sshArgv: string[],
  res: { keyFilePath?: string; knownHostsPath?: string; agentPid?: string }
): string[] {
  const files = [res.keyFilePath, res.knownHostsPath].filter((f): f is string => !!f);
  const pid = res.agentPid && isNumericPid(res.agentPid) ? res.agentPid : undefined;
  const steps = [
    files.length > 0 ? `rm -f -- ${files.map(shellQuote).join(' ')}` : '',
    pid ? `kill ${pid} 2>/dev/null` : '',
  ].filter(Boolean);
  if (steps.length === 0) return sshArgv;
  const script = `cleanup() { ${steps.join('; ')}; }; trap cleanup EXIT; trap 'exit 129' HUP; trap 'exit 143' TERM; "$@"`;
  return ['sh', '-c', script, 'sh', ...sshArgv];
}

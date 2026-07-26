/**
 * `rdc executor-daemon run|stop|status` — the executor daemon's operator surface.
 *
 * Hidden and internal: the daemon is started AUTOMATICALLY on first use by the
 * daemon-backed executor (client.ts) and idles itself out after five minutes, so
 * an operator never runs `run` by hand. These subcommands exist for control and
 * introspection — stopping a daemon, or checking what it has warmed.
 *
 * Text here is plain hardcoded English on purpose: this is a debug/ops surface
 * with no place in the translated help tree (mirroring the `run` escape hatch and
 * the detached-job hints), so it does not pull i18n keys into 13 locales.
 */

import type { Command } from 'commander';
import { sendDaemonControl } from '../services/executor/daemon/client.js';
import { startExecutorDaemon } from '../services/executor/daemon/server.js';
import { handleError } from '../utils/errors.js';

function formatUptime(ms: number): string {
  const totalSeconds = Math.floor(ms / 1000);
  if (totalSeconds < 60) return `${totalSeconds}s`;
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}m${seconds}s`;
}

export function registerExecutorDaemonCommands(program: Command): void {
  const group = program
    .command('executor-daemon', { hidden: true })
    .summary('Control the local executor daemon (internal)');

  group
    .command('run')
    .summary('Run the executor daemon in this process (spawned automatically)')
    .action(async () => {
      try {
        // Resolves once listening; the socket keeps the process alive on its own.
        await startExecutorDaemon();
      } catch (error) {
        handleError(error);
      }
    });

  group
    .command('stop')
    .summary('Stop the running executor daemon')
    .action(async () => {
      try {
        const reply = await sendDaemonControl({ type: 'stop' });
        if (!reply) {
          process.stdout.write('No executor daemon is running.\n');
          return;
        }
        process.stdout.write('Executor daemon stopped.\n');
      } catch (error) {
        handleError(error);
      }
    });

  group
    .command('status')
    .summary('Show the running executor daemon (pid, uptime, warm hosts)')
    .action(async () => {
      try {
        const reply = await sendDaemonControl({ type: 'status' });
        if (!reply) {
          process.stdout.write('No executor daemon is running.\n');
          return;
        }
        if (reply.type === 'statusInfo') {
          const hosts = reply.warmHosts.length > 0 ? reply.warmHosts.join(', ') : '(none)';
          process.stdout.write(`pid:        ${reply.pid}\n`);
          process.stdout.write(`uptime:     ${formatUptime(reply.uptimeMs)}\n`);
          process.stdout.write(`identity:   ${reply.identity}\n`);
          process.stdout.write(`warm hosts: ${hosts}\n`);
          return;
        }
        process.stdout.write('An executor daemon is running but is stale; it will exit.\n');
      } catch (error) {
        handleError(error);
      }
    });
}

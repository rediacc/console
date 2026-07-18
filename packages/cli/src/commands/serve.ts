/**
 * `rdc serve` — run this process as an executor.
 *
 * The same binary that operators run on a laptop becomes the thing that runs
 * commands on their behalf. Two placements, one artifact:
 *
 *   --mode daemon     on a customer's own host. It enrolled like any headless
 *                     CLI (`rdc config remote enable --headless`), so it can
 *                     derive the config key by itself and needs no per-session
 *                     grant. This is the strict tier: SSH never leaves the
 *                     customer's network.
 *
 *   --mode container  inside an org-keyed Cloudflare Container. It starts with
 *                     NO key at all and cannot do anything until a client grants
 *                     one for the session (X25519 handoff). This is the
 *                     convenience tier.
 *
 * In both, the config key lives in RAM only, and the SSH keys never leave the
 * executor.
 */

import { serve as honoServe } from '@hono/node-server';
import type { RdcConfig } from '@rediacc/shared/config-schema';
import { Command, Option } from 'commander';
import { t } from '../i18n/index.js';
import { getSubscriptionServerUrl } from '../services/account/subscription-auth.js';
import { configService } from '../services/config/config-resources.js';
import { outputService } from '../services/core/output.js';
import { localExecutorService } from '../services/executor/local-executor.js';
import { createExecutorAudit } from '../services/serve/audit.js';
import { AuthVerifier } from '../services/serve/auth.js';
import { createContainerConfigLoader } from '../services/serve/container-config.js';
import { serveCrypto } from '../services/serve/crypto.js';
import type { ServeDeps } from '../services/serve/deps.js';
import { authorize } from '../services/serve/policy.js';
import { createServeApp } from '../services/serve/server.js';
import { SessionStore } from '../services/serve/sessions.js';
import { handleError, ValidationError } from '../utils/errors.js';

interface ServeOptions {
  port: string;
  host: string;
  mode: 'daemon' | 'container';
}

export function registerServeCommand(program: Command): void {
  program
    .command('serve')
    .summary(t('commands.serve.summary'))
    .description(t('commands.serve.description'))
    .option('-p, --port <port>', t('commands.serve.optionPort'), '8080')
    .option('--host <host>', t('commands.serve.optionHost'), '0.0.0.0')
    .addOption(
      new Option('--mode <mode>', t('commands.serve.optionMode'))
        .choices(['daemon', 'container'])
        .default('daemon')
    )
    .action((options: ServeOptions) => {
      try {
        // --mode is constrained by Commander's .choices(), so an invalid value
        // never reaches here.
        const executorToken = process.env.REDIACC_EXECUTOR_TOKEN;
        if (!executorToken) {
          throw new ValidationError(
            'The executor needs its own account token to verify callers. ' +
              'Set REDIACC_EXECUTOR_TOKEN to a token carrying the proxy:exec scope.'
          );
        }

        const accountUrl = getSubscriptionServerUrl();

        const sessions = new SessionStore();

        // The daemon reads its enrolled config off disk. The container has no
        // disk and no enrollment: it pulls the config encrypted and opens it with
        // the key the caller granted for the session.
        const loadConfig =
          options.mode === 'container'
            ? createContainerConfigLoader({ accountUrl, executorToken, sessions })
            : loadDaemonConfig;

        const deps: ServeDeps = {
          mode: options.mode,
          auth: new AuthVerifier({ accountUrl, executorToken }),
          sessions,
          executor: localExecutorService,
          crypto: serveCrypto,
          loadConfig,
          authorize,
          audit: createExecutorAudit({
            accountUrl,
            executorToken,
            // A command that ran but could not be recorded is exactly the case an
            // audit trail exists to catch, so it is never swallowed.
            onFailure: (error, event) => {
              outputService.warn(
                `Ran "${event.commandPath}" for ${event.principal.userEmail} but could not record it: ` +
                  `${error instanceof Error ? error.message : String(error)}`
              );
            },
          }),
        };

        const app = createServeApp(deps);
        const port = Number.parseInt(options.port, 10);

        const server = honoServe({ fetch: app.fetch, port, hostname: options.host });

        outputService.info(
          t('commands.serve.listening', { host: options.host, port, mode: options.mode })
        );
        outputService.info(t('commands.serve.hint'));

        // A container gets SIGTERM and then 15 minutes before SIGKILL. Stop
        // accepting new work immediately, but let commands already in flight
        // finish rather than orphaning an operation halfway through a machine.
        const shutdown = () => {
          outputService.info(t('commands.serve.draining'));
          server.close(() => process.exit(0));
        };
        process.on('SIGTERM', shutdown);
        process.on('SIGINT', shutdown);
      } catch (error) {
        handleError(error);
      }
    });
}

/**
 * The config a DAEMON executor runs commands against: the enrolled config on
 * disk, which headless enrollment already taught this host to decrypt. No
 * per-session grant is involved, and no config leaves the customer's network.
 *
 * The container tier's loader lives in services/serve/container-config.ts, where
 * the config is pulled encrypted and opened with the key the caller granted.
 */
function loadDaemonConfig(): Promise<RdcConfig> {
  return configService.getLocalConfig() as unknown as Promise<RdcConfig>;
}

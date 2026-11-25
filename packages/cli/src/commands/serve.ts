/**
 * `rdc serve`, run this process as an executor.
 *
 * The same binary that operators run on a laptop becomes the thing that runs
 * commands on their behalf. Two placements, one artifact:
 *
 *   --mode daemon     on a customer's own host. It enrolled like any other
 *                     CLI (`rdc config remote enable`), so it can
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
import { createAiRecorder } from '../services/ai/recorder.js';
import { configService } from '../services/config/config-resources.js';
import { outputService } from '../services/core/output.js';
import { localExecutorService } from '../services/executor/local-executor.js';
import { AgentGrantSessions } from '../services/serve/agent-grant-session.js';
import { createExecutorAudit } from '../services/serve/audit.js';
import { AuthVerifier, resolvePinnedOrgId } from '../services/serve/auth.js';
import { resolveServeBind, serveListenOptions } from '../services/serve/bind.js';
import {
  createContainerConfigLoader,
  createExecutorGrantRecorder,
  routeAgentPrincipals,
  teamOverSharedAiConfigs,
} from '../services/serve/container-config.js';
import { serveCrypto } from '../services/serve/crypto.js';
import type { ExecutorAuditEvent, ServeDeps } from '../services/serve/deps.js';
import { authorize } from '../services/serve/policy.js';
import { createRunIndex } from '../services/serve/run-index.js';
import { createServeApp } from '../services/serve/server.js';
import { SessionStore } from '../services/serve/sessions.js';
import { handleError, ValidationError } from '../utils/errors.js';

interface ServeOptions {
  port: string;
  host?: string;
  mode: 'daemon' | 'container';
  tlsCert?: string;
  tlsKey?: string;
}

export function registerServeCommand(program: Command): void {
  program
    .command('serve')
    .summary(t('commands.serve.summary'))
    .description(t('commands.serve.description'))
    .option('-p, --port <port>', t('commands.serve.optionPort'), '8080')
    // No Commander default: the default depends on --mode (services/serve/bind.ts DEFAULT_HOST).
    .option('--host <host>', t('commands.serve.optionHost'))
    .option('--tls-cert <path>', t('commands.serve.optionTlsCert'))
    .option('--tls-key <path>', t('commands.serve.optionTlsKey'))
    .addOption(
      new Option('--mode <mode>', t('commands.serve.optionMode'))
        .choices(['daemon', 'container'])
        .default('daemon')
    )
    .action((options: ServeOptions) => {
      try {
        // --mode is constrained by Commander's .choices(), so an invalid value never reaches here.
        const executorToken = process.env.REDIACC_TOKEN;
        if (!executorToken) {
          throw new ValidationError(
            'The executor needs its own account token to verify callers. ' +
              'Set REDIACC_TOKEN to a token carrying the proxy:exec scope.'
          );
        }

        const pinnedOrgId = resolvePinnedOrgId(options.mode, process.env);
        // Refused here, before anything listens: a daemon off loopback without TLS would carry bearer tokens in the clear.
        const bind = resolveServeBind(options);

        const accountUrl = getSubscriptionServerUrl();

        const sessions = new SessionStore();

        // The daemon reads its enrolled config off disk. The container has no disk and no enrollment: it pulls the config encrypted and opens it with the key the caller granted for the session.
        const { loadConfig, agentGrants } = configLoading({
          mode: options.mode,
          accountUrl,
          executorToken,
          sessions,
          pinnedOrgId,
        });

        const deps: ServeDeps = {
          mode: options.mode,
          auth: new AuthVerifier({ accountUrl, executorToken, pinnedOrgId }),
          sessions,
          executor: localExecutorService,
          crypto: serveCrypto,
          loadConfig,
          ...(agentGrants ? { agentGrants } : {}),
          // The container's config token is minted only under a grant the account server recorded (PLAN-backup-program S7).
          ...(options.mode === 'container'
            ? { recordGrant: createExecutorGrantRecorder({ accountUrl, executorToken }) }
            : {}),
          authorize,
          runIndex: createRunIndex({
            accountUrl,
            executorToken,
            // The index is a view: a lost event is reported and the command is untouched.
            onFailure: (reason, event) => {
              outputService.warn(
                `Run index event ${event.seq} (${event.state}) of run ${event.runId} was not delivered: ${reason}`
              );
            },
          }),
          ...aiChatDeps({ mode: options.mode, accountUrl, executorToken, loadConfig }),
          audit: createExecutorAudit({
            accountUrl,
            executorToken,
            // A record the audit route refused or could not take is never swallowed: a refused `started` record means the command did not run, a refused `finished` one means it ran unrecorded.
            onFailure: (error, event) => {
              outputService.warn(auditFailureNotice(error, event));
            },
          }),
        };

        const app = createServeApp(deps);
        const port = Number.parseInt(options.port, 10);

        const server = honoServe({ fetch: app.fetch, port, ...serveListenOptions(bind) });

        outputService.info(
          t('commands.serve.listening', {
            scheme: bind.tls ? 'https' : 'http',
            host: bind.hostname,
            port,
            mode: options.mode,
          })
        );
        outputService.info(t('commands.serve.hint'));

        // A container gets SIGTERM and then 15 minutes before SIGKILL. Stop accepting new work immediately, but let commands already in flight finish rather than orphaning an operation halfway through a machine.
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
 * How the executor loads the config a request runs against.
 *
 * The daemon reads its enrolled config off disk; the container has no disk and no enrollment, and opens the config it
 * pulled with the key the caller granted. An agent grant (Design 4 of PLAN-rmcp-agent-grants.md) has neither: its config
 * comes from its own grant session, opened by the secret each `/v1/mcp/call` carries, and the loader routes an agent
 * principal there, never to a user-keyed session. Grant sessions exist wherever the executor is pinned to an org.
 */
function configLoading(input: {
  mode: 'daemon' | 'container';
  accountUrl: string;
  executorToken: string;
  sessions: SessionStore;
  pinnedOrgId: string | undefined;
}): { loadConfig: ServeDeps['loadConfig']; agentGrants: AgentGrantSessions | undefined } {
  const { mode, accountUrl, executorToken, sessions, pinnedOrgId } = input;
  const baseLoader =
    mode === 'container'
      ? createContainerConfigLoader({ accountUrl, executorToken, sessions })
      : loadDaemonConfig;
  const agentGrants =
    pinnedOrgId === undefined
      ? undefined
      : new AgentGrantSessions({ accountUrl, executorToken, orgId: pinnedOrgId });
  return { loadConfig: routeAgentPrincipals(baseLoader, agentGrants), agentGrants };
}

/**
 * What the AI chat routes take from the executor's wiring. A chat's messages, sealed under the
 * session key, are what the account's conversation row (and with it every page approval) is made
 * of. The container opens the org's shared config beside the team's for profile resolution; the
 * daemon has one enrolled config.
 */
function aiChatDeps(input: {
  mode: 'daemon' | 'container';
  accountUrl: string;
  executorToken: string;
  loadConfig: ServeDeps['loadConfig'];
}): Pick<ServeDeps, 'aiRecorder' | 'aiConfigs'> {
  const aiRecorder = createAiRecorder({
    accountUrl: input.accountUrl,
    executorToken: input.executorToken,
    onFailure: (reason, message) => {
      outputService.warn(
        `AI message ${message.messageId} of conversation ${message.conversationId} was not recorded: ${reason}`
      );
    },
  });
  if (input.mode !== 'container') return { aiRecorder };
  return { aiRecorder, aiConfigs: teamOverSharedAiConfigs(input.loadConfig) };
}

/** The warning the daemon prints for an audit record the account server did not take. */
export function auditFailureNotice(
  error: unknown,
  event: Pick<ExecutorAuditEvent, 'commandPath' | 'principal'>
): string {
  return (
    `Could not record "${event.commandPath}" for ${event.principal.userEmail}: ` +
    `${error instanceof Error ? error.message : String(error)}`
  );
}

/**
 * The config a DAEMON executor runs commands against: the enrolled config on
 * disk, which headless enrollment already taught this host to decrypt. No
 * per-session grant is involved, and no config leaves the customer's network.
 *
 * It is the whole decrypted RdcConfig, policy document included. It used to be
 * getLocalConfig(), a machines-and-SSH projection with no `policy` field cast
 * to RdcConfig, so authorize() always saw "no policy document" and a daemon
 * never enforced one.
 *
 * The container tier's loader lives in services/serve/container-config.ts, where
 * the config is pulled encrypted and opened with the key the caller granted.
 */
export async function loadDaemonConfig(): Promise<RdcConfig> {
  const config = await configService.getDecryptedConfig();
  if (!config) {
    throw new ValidationError(
      `The executor has no config named "${configService.getEffectiveConfigName()}" to run commands against.`
    );
  }
  return config;
}

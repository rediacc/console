/**
 * The executor's HTTP surface: `rdc serve`.
 *
 * One artifact, two placements. The same app runs inside an org-keyed warm
 * Cloudflare Container (the convenience tier) and as a daemon on a customer's
 * own host (the strict tier). Nothing here knows which it is, apart from the
 * `mode` it reports in server-info.
 *
 * Dispatch is IN-PROCESS: a request runs the very same Commander tree the CLI
 * runs, rather than shelling out to `rdc`. That is what lets a warm executor keep
 * its SSH connection pool and decrypted-config cache across commands, which is
 * the entire economic argument for keeping it warm.
 *
 * The request pipeline, in order, and each step matters:
 *   1. authenticate  - resolve the caller with the ACCOUNT server (never trust
 *                      a client-asserted identity)
 *   2. version check - refuse a client whose contract disagrees with ours
 *   3. authorize     - evaluate the policy document from the ENCRYPTED config
 *   4. execute       - run it, streaming renet's events back verbatim
 *   5. audit         - ship one event, awaited, before the result line lands
 */

import { CLI_CONTRACT_VERSION } from '@rediacc/shared/cli-contract';
import {
  CONTRACT_VERSION_HEADER,
  CommandRequestSchema,
  PROXY_ROUTES,
  type ServerInfo,
  type StreamLine,
} from '@rediacc/shared/cli-contract/wire';
import { Hono } from 'hono';
import { streamText } from 'hono/streaming';
import { VERSION } from '../../version.js';
import { AuthError, type AuthVerifier } from './auth.js';
import { CommandRejected, dispatchCommand, prepareCommand } from './command-dispatch.js';
import type { ServeDeps } from './deps.js';
import { CekHandoffBlobSchema } from './handoff-schema.js';
import { PolicyDenied } from './policy.js';
import { SessionError } from './sessions.js';

/** Turn any thrown value into an HTTP status plus a message worth reading. */
function statusFor(error: unknown): { status: 400 | 401 | 403 | 404 | 500; message: string } {
  if (error instanceof AuthError) return { status: error.status, message: error.message };
  if (error instanceof PolicyDenied) return { status: 403, message: error.message };
  if (error instanceof SessionError) return { status: 404, message: error.message };
  if (error instanceof CommandRejected) return { status: 400, message: error.message };
  return {
    status: 500,
    message: error instanceof Error ? error.message : 'The executor failed to run this command.',
  };
}

export function createServeApp(deps: ServeDeps): Hono {
  const app = new Hono();

  app.get(PROXY_ROUTES.health, (c) => c.json({ ok: true }));

  app.get(PROXY_ROUTES.serverInfo, (c) => {
    const info: ServerInfo = {
      cliVersion: VERSION,
      contractVersion: CLI_CONTRACT_VERSION,
      mode: deps.mode,
      ...(deps.scope ? { scope: deps.scope } : {}),
    };
    return c.json(info);
  });

  /**
   * Open a session: mint an ephemeral X25519 keypair so the client can seal the
   * config key to it. The server never sees the key any other way.
   */
  app.post(PROXY_ROUTES.session, async (c) => {
    try {
      const principal = await authenticate(c.req.header('authorization'), deps);
      const { sessionId, publicKey } = await deps.sessions.open(
        principal,
        deps.crypto.generateEphemeralKeyPair,
        deps.crypto.exportPublicKey
      );
      return c.json({ sessionId, publicKey });
    } catch (error) {
      const { status, message } = statusFor(error);
      return c.json({ error: message }, status);
    }
  });

  /** Accept the sealed CEK for a session. It is held in RAM and never written. */
  app.post(PROXY_ROUTES.sessionCekPattern, async (c) => {
    try {
      // The grant is bound to the principal who OPENED the session: this is the
      // same identity, resolved by the account server, that grantCek checks the
      // session against. A valid token for a different user cannot complete
      // someone else's grant.
      const principal = await authenticate(c.req.header('authorization'), deps);
      const blob = CekHandoffBlobSchema.parse(await c.req.json());
      await deps.sessions.grantCek(c.req.param('id'), blob, principal);
      return c.json({ ok: true });
    } catch (error) {
      const { status, message } = statusFor(error);
      return c.json({ error: message }, status);
    }
  });

  /**
   * Run a command, named the way an operator names it.
   *
   * The only execution route. The executor resolves command to renet function
   * itself, by running its own CLI, so a caller needs no CLI of its own: that is
   * what lets the web console drive every command, and what lets `rdc --proxy` be
   * a genuinely thin client rather than one that quietly needs the config it is
   * not supposed to have.
   *
   * Responds with NDJSON: renet's events verbatim, then exactly one result line
   * carrying the execution envelope and whatever the command printed.
   */
  app.post(PROXY_ROUTES.command, async (c) => {
    let principal: Awaited<ReturnType<AuthVerifier['verify']>>;
    let request: ReturnType<typeof CommandRequestSchema.parse>;

    try {
      principal = await authenticate(c.req.header('authorization'), deps);
      request = CommandRequestSchema.parse(await c.req.json());
    } catch (error) {
      const { status, message } = statusFor(error);
      return c.json({ error: message }, status);
    }

    const clientContract = c.req.header(CONTRACT_VERSION_HEADER) ?? request.contractVersion;
    if (clientContract !== CLI_CONTRACT_VERSION) {
      return c.json(
        {
          error: 'contract_version_mismatch',
          clientContractVersion: clientContract,
          executorContractVersion: CLI_CONTRACT_VERSION,
          executorCliVersion: VERSION,
        },
        409
      );
    }

    // Refuse before the stream opens, and before policy. prepareCommand rejects
    // an unknown command, a non-proxyable one (config ssh show, repo sync, ...),
    // or a smuggled flag. This is a hard gate independent of the org's rules: a
    // permissive `allow: ['repo *']` still cannot reach `repo sync upload`,
    // because that refusal happens here, above authorize(). And it must happen
    // pre-stream, since once the stream is open the status is already 200 and a
    // rejection could only be described inside the body.
    let prepared: ReturnType<typeof prepareCommand>;
    try {
      prepared = prepareCommand(request.pathKey, request.params);
    } catch (error) {
      const { status, message } = statusFor(error);
      return c.json({ error: message }, status);
    }
    const entry = prepared.entry;

    // Policy is evaluated on the path the caller asked for, and the executor then
    // runs THAT path. There is no second name for the client to disagree with.
    try {
      const config = await deps.loadConfig(principal);
      deps.authorize({
        principal,
        commandPath: request.pathKey,
        config,
        machineName: targetFrom(entry.machineOption, request.params),
        repoName: targetFrom(entry.repoOption, request.params),
      });
    } catch (error) {
      const { status, message } = statusFor(error);
      return c.json({ error: message }, status);
    }

    return streamText(c, async (stream) => {
      const write = async (line: StreamLine) => {
        await stream.write(`${JSON.stringify(line)}\n`);
      };

      const started = Date.now();
      try {
        const { result, functionName, stdout, stderr } = await dispatchCommand({
          prepared,
          executor: deps.executor,
          onEvent: (event) => {
            void write({ kind: 'event', event });
          },
        });

        // The audited function is the one the command actually called, observed
        // as it went past, not one reconstructed from a table. A command that
        // reached no machine has none, and is audited by its path alone.
        await deps.audit?.({
          principal,
          commandPath: request.pathKey,
          functionName: functionName ?? request.pathKey,
          machineName: targetFrom(entry.machineOption, request.params),
          params: request.params,
          success: result.success,
          durationMs: result.durationMs,
          destructive: entry.destructive ?? false,
        });

        await write({ kind: 'result', result, stdout, stderr });
      } catch (error) {
        const message =
          error instanceof Error ? error.message : 'The executor failed to run this command.';
        await write({
          kind: 'result',
          result: {
            success: false,
            exitCode: 1,
            error: message,
            durationMs: Date.now() - started,
          },
        });
      }
    });
  });

  return app;
}

/**
 * The machine or repo a request targets, for the policy check.
 *
 * Which option names it is a property of the COMMAND (the contract resolves
 * `machineOption` / `repoOption` per command), not something the client asserts,
 * so a caller cannot dodge a machine-scoped rule by renaming a field.
 */
function targetFrom(option: string | null, params: Record<string, unknown>): string | undefined {
  if (!option) return undefined;
  const value = params[option];
  return typeof value === 'string' ? value : undefined;
}

async function authenticate(header: string | undefined, deps: ServeDeps) {
  const token = header?.replace(/^Bearer\s+/i, '').trim();
  if (!token) {
    throw new AuthError(
      'This request carried no token. Authenticate with the account server.',
      401
    );
  }
  return deps.auth.verify(token);
}

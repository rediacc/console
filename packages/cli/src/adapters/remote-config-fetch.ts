/**
 * The config server transport of RemoteConfigAdapter: one request under an operation's token
 * lease, the rotated token persisted after every answer, and one token renewal per operation.
 */

import { t } from '../i18n/index.js';
import { rdcCommand } from '../services/config/config-name.js';
import {
  ConfigServerError,
  type ConfigServerFetchOptions,
  configServerFetch,
} from '../services/config/config-server-client.js';
import {
  loginTokenFor,
  REFRESHABLE_AUTH_REASONS,
  refreshDeviceToken,
} from '../services/config/device-token-refresh.js';
import type { RemoteConfig } from '../types/index.js';
import { classifyFetchError, RemoteAuthError } from './remote-config-errors.js';
import { renewalFailure } from './remote-config-support.js';
import type { TokenLease } from './remote-token-storage.js';

/** Test seams for the round-trip harness; production passes nothing. */
export interface RemoteAdapterTransport
  extends Pick<ConfigServerFetchOptions, 'fetchImpl' | 'serverKey'> {
  /**
   * The login token this device holds for `remote.apiUrl`. Production reads the stored
   * `rdc subscription login` token (loginTokenFor); a harness device supplies its own.
   */
  loginToken?: () => string | undefined;
}

export class LeasedConfigFetch {
  /** Operations (by their lease) that already renewed the config token: one renewal each (T11). */
  private readonly refreshed = new WeakSet<TokenLease>();

  constructor(
    private readonly remote: RemoteConfig,
    private readonly configName: string,
    private readonly transport?: RemoteAdapterTransport
  ) {}

  /**
   * One config server request under the operation's lease. The request sends the lease's current
   * token, and the token the server rotated to is persisted, and sent by the next request of the
   * operation, whether the request succeeded or failed: an error body carries the rotated token
   * too (F9), and dropping it spent one grace use of the old token per error.
   *
   * A 401 whose reason a new token cures (REFRESHABLE_AUTH_REASONS: expired, spent, bound to
   * another address, unknown) renews the token with the login token, still under the lease, and
   * sends the refused request once more (T11, D4). One renewal per operation: a second refusal
   * after it is raised as it came.
   */
  async fetch<T>(
    lease: TokenLease,
    path: string,
    options?: { method?: string; body?: unknown }
  ): Promise<{ data: T }> {
    try {
      return await this.fetchOnce<T>(lease, path, options);
    } catch (error) {
      if (
        !(error instanceof RemoteAuthError) ||
        !REFRESHABLE_AUTH_REASONS.has(error.reason) ||
        this.refreshed.has(lease)
      ) {
        throw error;
      }
      this.refreshed.add(lease);
      await this.renewToken(lease, error);
      return this.fetchOnce<T>(lease, path, options);
    }
  }

  private async fetchOnce<T>(
    lease: TokenLease,
    path: string,
    options?: { method?: string; body?: unknown }
  ): Promise<{ data: T }> {
    let resp: Awaited<ReturnType<typeof configServerFetch<T>>>;
    try {
      resp = await configServerFetch<T>(path, {
        ...options,
        fetchImpl: this.transport?.fetchImpl,
        serverKey: this.transport?.serverKey,
        configToken: lease.token ?? '',
        serverUrl: this.remote.apiUrl,
      });
    } catch (error) {
      if (error instanceof ConfigServerError && error.newServerToken) {
        await lease.update(error.newServerToken);
      }
      throw classifyFetchError(error, this.remote, this.configName);
    }
    if (resp.newServerToken) await lease.update(resp.newServerToken);
    return { data: resp.data };
  }

  /**
   * Replace the lease's dead config token with one the account server mints for this device's
   * login (POST /configs/device-token/refresh). The token file keeps its wrapped CEK and sync
   * record; only `token` changes. Without a login token for this server, or when the renewal is
   * refused, the operation fails with the refusal's remedy (the original 401 kept as the cause, or
   * its message extended with both remedies when there was nothing to renew with).
   */
  private async renewToken(lease: TokenLease, refusal: RemoteAuthError): Promise<void> {
    const loginToken = this.transport?.loginToken
      ? this.transport.loginToken()
      : loginTokenFor(this.remote.apiUrl);
    if (!loginToken) {
      refusal.message = `${refusal.message}\n${t('commands.config.remote.tokenRefresh.noLogin', {
        apiUrl: this.remote.apiUrl,
        loginCmd: rdcCommand('subscription login', this.configName),
        cmd: rdcCommand('config remote enable', this.configName),
      })}`;
      throw refusal;
    }
    let token: string;
    try {
      token = await refreshDeviceToken(
        this.remote,
        loginToken,
        { fetchImpl: this.transport?.fetchImpl, serverKey: this.transport?.serverKey },
        this.configName
      );
    } catch (error) {
      throw renewalFailure(this.configName, this.remote.teamId, error, refusal);
    }
    await lease.update(token);
  }
}

import { DEFAULTS } from '@rediacc/shared/config';
import { configFileStorage } from '../adapters/config-file-storage.js';
import type { RemoteConfigAdapter } from '../adapters/remote-config-adapter.js';
import type { RdcConfig } from '../types/index.js';
import { hasCloudCredentials, hasRemoteConfig } from '../types/index.js';
import {
  detectSystemLanguage,
  getSupportedLanguages as getSupportedLanguagesList,
  isLanguageSupported as isLanguageSupportedCheck,
  normalizeLanguage,
} from './context-language.js';
import type { ResourceState } from './resource-state.js';

const DEFAULT_API_URL = 'https://www.rediacc.com/api';

/**
 * Service for managing CLI config files.
 * Each config is a separate file (e.g., rediacc.json, production.json).
 * In self-hosted mode, resource CRUD delegates to LocalResourceState.
 * When a remote pointer is present, transparently fetches/pushes encrypted config.
 */
export class ConfigServiceBase {
  private runtimeConfigOverride: string | null = null;
  private _resourceState: ResourceState | null = null;
  private _remoteAdapter: RemoteConfigAdapter | null = null;
  private _remoteConfig: RdcConfig | null = null;
  private _remoteVersion = 0;
  private _remoteSdkEpoch = 0;

  /**
   * Set a runtime config override (used by --config flag).
   * Takes precedence over default config name.
   */
  setRuntimeConfig(name: string | null): void {
    this.runtimeConfigOverride = name;
    this._resourceState = null;
    this._remoteAdapter = null;
    this._remoteConfig = null;
  }

  /**
   * Get the ResourceState for the current config, initializing lazily.
   * When remote is enabled, uses RemoteResourceState (push on mutation).
   */
  async getResourceState(): Promise<ResourceState> {
    if (this._resourceState) return this._resourceState;

    const config = await this.getCurrent();
    if (!config) throw new Error('No active config');

    const configName = this.getEffectiveConfigName();

    if (hasRemoteConfig(config) && this._remoteAdapter) {
      const { RemoteResourceState } = await import('./resource-state.js');
      this._resourceState = RemoteResourceState.load(
        config,
        configName,
        this._remoteAdapter,
        this._remoteVersion,
        this._remoteSdkEpoch
      );
      return this._resourceState;
    }

    let masterPassword: string | null = null;
    if (config.credentials?.masterPasswordVerifier) {
      const { authService } = await import('./auth.js');
      masterPassword = await authService.requireMasterPassword();
    }

    const { LocalResourceState } = await import('./resource-state.js');
    this._resourceState = await LocalResourceState.load(config, configName, masterPassword);

    return this._resourceState;
  }

  /**
   * Get the effective config name.
   * Priority: --config flag > REDIACC_CONFIG env var > "rediacc"
   */
  getEffectiveConfigName(): string {
    return this.runtimeConfigOverride ?? process.env.REDIACC_CONFIG ?? DEFAULTS.CONTEXT.CONFIG_NAME;
  }

  // ============================================================================
  // Config CRUD Operations
  // ============================================================================

  /**
   * List all available config files.
   */
  async list(): Promise<string[]> {
    return configFileStorage.list();
  }

  /**
   * Get the current active config.
   * When a remote pointer is present, transparently fetches from the server.
   */
  async getCurrent(): Promise<RdcConfig | null> {
    // Return cached remote config if already loaded this session
    if (this._remoteConfig) return this._remoteConfig;

    const name = this.getEffectiveConfigName();

    let config: RdcConfig | null;
    if (name === 'rediacc') {
      config = await configFileStorage.getOrCreateDefault();
    } else {
      const exists = await configFileStorage.exists(name);
      if (!exists) return null;
      config = await configFileStorage.load(name);
    }

    if (hasRemoteConfig(config)) {
      return this.loadRemote(config, name);
    }

    return config;
  }

  /**
   * Load config from the remote server, caching for the session.
   * Preserves all local-only settings (remote pointer, account defaults, language).
   */
  private async loadRemote(localConfig: RdcConfig, configName: string): Promise<RdcConfig> {
    const adapter = await this.getRemoteAdapter(localConfig, configName);
    const { config, version, sdkEpoch } = await adapter.pull();

    // Local pointer fields take precedence over anything remote might send.
    if (localConfig.remote) config.remote = localConfig.remote;
    if (localConfig.account) {
      config.account = { ...(config.account ?? {}), ...localConfig.account };
    }
    if (localConfig.defaults) {
      config.defaults = { ...(config.defaults ?? {}), ...localConfig.defaults };
    }

    this._remoteConfig = config;
    this._remoteVersion = version;
    this._remoteSdkEpoch = sdkEpoch;
    return config;
  }

  /**
   * Get or create a RemoteConfigAdapter for the current config.
   */
  private async getRemoteAdapter(
    config: RdcConfig,
    configName: string
  ): Promise<RemoteConfigAdapter> {
    if (this._remoteAdapter) return this._remoteAdapter;

    const remote = config.remote!;
    const { RemoteConfigAdapter: Adapter } = await import('../adapters/remote-config-adapter.js');
    const { remoteTokenStorage } = await import('../adapters/remote-token-storage.js');
    const { getSecureStorage } = await import('../utils/secure-storage.js');

    this._remoteAdapter = new Adapter(remote, configName, remoteTokenStorage, getSecureStorage());
    return this._remoteAdapter;
  }

  /**
   * Get the current config name.
   */
  getCurrentName(): string {
    return this.getEffectiveConfigName();
  }

  /**
   * Initialize a new config file.
   */
  async init(name: string): Promise<RdcConfig> {
    return configFileStorage.init(name);
  }

  /**
   * Update the current config.
   */
  async update(name: string, updates: Partial<RdcConfig>): Promise<void> {
    await configFileStorage.update(name, (config) => ({
      ...config,
      ...updates,
    }));
  }

  /**
   * Delete a config file.
   */
  async delete(name: string): Promise<void> {
    await configFileStorage.delete(name);
  }

  // ============================================================================
  // Credential Helpers (for API client integration)
  // ============================================================================

  async getApiUrl(): Promise<string> {
    if (process.env.REDIACC_API_URL) {
      return process.env.REDIACC_API_URL;
    }
    const config = await this.getCurrent();
    return config?.account?.apiUrl ?? DEFAULT_API_URL;
  }

  async getToken(): Promise<string | null> {
    if (process.env.REDIACC_TOKEN) {
      return process.env.REDIACC_TOKEN;
    }
    const config = await this.getCurrent();
    return config?.account?.token ?? null;
  }

  async setToken(token: string): Promise<void> {
    const name = this.getEffectiveConfigName();
    const exists = await configFileStorage.exists(name);
    if (!exists) return;
    await configFileStorage.update(name, (cfg) => ({
      ...cfg,
      account: { ...(cfg.account ?? {}), token },
    }));
  }

  async getMasterPassword(): Promise<string | null> {
    const config = await this.getCurrent();
    return config?.credentials?.masterPasswordVerifier ?? null;
  }

  async setMasterPassword(password: string): Promise<void> {
    const name = this.getEffectiveConfigName();
    const exists = await configFileStorage.exists(name);
    if (!exists) return;
    await configFileStorage.update(name, (cfg) => ({
      ...cfg,
      credentials: { ...(cfg.credentials ?? {}), masterPasswordVerifier: password },
    }));
  }

  async getUserEmail(): Promise<string | null> {
    const config = await this.getCurrent();
    return config?.account?.userEmail ?? null;
  }

  // ============================================================================
  // Config Defaults (team, region, bridge, machine)
  // ============================================================================

  async getTeam(): Promise<string | undefined> {
    if (process.env.REDIACC_TEAM) return process.env.REDIACC_TEAM;
    const config = await this.getCurrent();
    return config?.account?.team;
  }

  async getRegion(): Promise<string | undefined> {
    if (process.env.REDIACC_REGION) return process.env.REDIACC_REGION;
    const config = await this.getCurrent();
    return config?.account?.region;
  }

  async getBridge(): Promise<string | undefined> {
    if (process.env.REDIACC_BRIDGE) return process.env.REDIACC_BRIDGE;
    const config = await this.getCurrent();
    return config?.account?.bridge;
  }

  async set(key: 'team' | 'region' | 'bridge', value: string): Promise<void> {
    const name = this.getEffectiveConfigName();
    await configFileStorage.update(name, (cfg) => ({
      ...cfg,
      account: { ...(cfg.account ?? {}), [key]: value },
    }));
  }

  async remove(key: 'team' | 'region' | 'bridge'): Promise<void> {
    const name = this.getEffectiveConfigName();
    await configFileStorage.update(name, (cfg) => ({
      ...cfg,
      account: cfg.account ? { ...cfg.account, [key]: undefined } : undefined,
    }));
  }

  async clearDefaults(): Promise<void> {
    const name = this.getEffectiveConfigName();
    await configFileStorage.update(name, (cfg) => ({
      ...cfg,
      account: cfg.account
        ? { ...cfg.account, team: undefined, region: undefined, bridge: undefined }
        : undefined,
    }));
  }

  // --- Language Settings ---

  async getLanguage(): Promise<string> {
    if (process.env.REDIACC_LANG) return normalizeLanguage(process.env.REDIACC_LANG);
    const config = await this.getCurrent();
    if (config?.defaults?.language) return config.defaults.language;
    return detectSystemLanguage();
  }

  async setLanguage(language: string): Promise<void> {
    const name = this.getEffectiveConfigName();
    await configFileStorage.update(name, (cfg) => ({
      ...cfg,
      defaults: { ...(cfg.defaults ?? {}), language: normalizeLanguage(language) },
    }));
  }

  isLanguageSupported(lang: string): boolean {
    return isLanguageSupportedCheck(lang);
  }

  getSupportedLanguages(): string[] {
    return getSupportedLanguagesList();
  }

  async applyDefaults<T extends object>(
    options: T
  ): Promise<T & { team?: string; region?: string; bridge?: string; machine?: string }> {
    type Result = T & {
      team?: string;
      region?: string;
      bridge?: string;
      machine?: string;
    };
    const base = { ...options };
    const result = base as Result;
    result.team ??= await this.getTeam();
    result.region ??= await this.getRegion();
    result.bridge ??= await this.getBridge();
    return result;
  }

  // ============================================================================
  // Login Helper (creates/updates config on login)
  // ============================================================================

  async saveLoginCredentials(
    configName: string,
    credentials: {
      apiUrl: string;
      token: string;
      userEmail: string;
      masterPassword?: string;
    }
  ): Promise<void> {
    const exists = await configFileStorage.exists(configName);
    const apply = (cfg: RdcConfig): RdcConfig => ({
      ...cfg,
      account: {
        ...(cfg.account ?? {}),
        apiUrl: credentials.apiUrl,
        token: credentials.token,
        userEmail: credentials.userEmail,
      },
      credentials: credentials.masterPassword
        ? { ...(cfg.credentials ?? {}), masterPasswordVerifier: credentials.masterPassword }
        : cfg.credentials,
    });
    if (exists) {
      await configFileStorage.update(configName, apply);
    } else {
      const config = await configFileStorage.init(configName);
      await configFileStorage.save(apply(config), configName);
    }
  }

  async clearCredentials(): Promise<void> {
    const name = this.getEffectiveConfigName();
    const exists = await configFileStorage.exists(name);
    if (!exists) return;
    await configFileStorage.update(name, (cfg) => ({
      ...cfg,
      account: cfg.account ? { ...cfg.account, token: undefined } : undefined,
      credentials: cfg.credentials
        ? { ...cfg.credentials, masterPasswordVerifier: undefined }
        : undefined,
    }));
  }

  async hasToken(): Promise<boolean> {
    const token = await this.getToken();
    return token !== null;
  }

  // ============================================================================
  // Adapter Detection Helpers
  // ============================================================================

  async isCloud(): Promise<boolean> {
    const config = await this.getCurrent();
    return hasCloudCredentials(config);
  }

  async isSelfHosted(): Promise<boolean> {
    return !(await this.isCloud());
  }
}

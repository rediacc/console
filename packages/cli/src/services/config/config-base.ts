import { DEFAULTS } from '@rediacc/shared/config';
import { configFileStorage } from '../../adapters/config-file-storage.js';
import type { RemoteConfigAdapter } from '../../adapters/remote-config-adapter.js';
import type { RdcConfig } from '../../types/index.js';
import { hasRemoteConfig } from '../../types/index.js';
import {
  detectSystemLanguage,
  getSupportedLanguages as getSupportedLanguagesList,
  isLanguageSupported as isLanguageSupportedCheck,
  normalizeLanguage,
} from '../core/context-language.js';
import type { ResourceState } from './resource-state.js';

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

    // Encryption-at-rest is a storage-layer transform in v3: loadDecrypted
    // resolves the master password (env / prompt) only when the config is
    // encrypted and materializes every encrypted leaf into plaintext.
    const decrypted = await configFileStorage.loadDecrypted(configName);
    const { LocalResourceState } = await import('./resource-state.js');
    this._resourceState = LocalResourceState.load(decrypted, configName);

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
   * Get the current config with every encrypted-at-rest leaf materialized into
   * plaintext. Prompts for the master password when the local config is
   * encrypted; remote configs arrive already decrypted from the pull. Use where
   * a sensitive field (cfDnsApiToken, cert-cache data, …) is actually read.
   */
  async getDecryptedConfig(): Promise<RdcConfig | null> {
    const config = await this.getCurrent();
    if (!config) return null;
    if (hasRemoteConfig(config)) return config;
    return configFileStorage.loadDecrypted(this.getEffectiveConfigName());
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
    const { RemoteConfigAdapter: Adapter } = await import(
      '../../adapters/remote-config-adapter.js'
    );
    const { remoteTokenStorage } = await import('../../adapters/remote-token-storage.js');
    const { getSecureStorage } = await import('../../utils/secure-storage.js');

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
  // Credential Helpers
  // ============================================================================

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
  // Config Defaults (team, region, machine)
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

  /**
   * Set one v3 `defaults` field (spec/03 §5.1). The retired `team`/`region`
   * keys (R2-F9) are refused at the command layer, so this only ever writes a
   * real DefaultsSchema field.
   */
  async setDefault(
    key: 'language' | 'datastoreSize' | 'pruneGraceDays',
    value: string
  ): Promise<void> {
    const name = this.getEffectiveConfigName();
    const typed: string | number = key === 'pruneGraceDays' ? Number(value) : value;
    await configFileStorage.update(name, (cfg) => ({
      ...cfg,
      defaults: { ...(cfg.defaults ?? {}), [key]: typed },
    }));
  }

  /** Clear one v3 `defaults` field. */
  async clearDefault(key: 'language' | 'datastoreSize' | 'pruneGraceDays'): Promise<void> {
    const name = this.getEffectiveConfigName();
    await configFileStorage.update(name, (cfg) => ({
      ...cfg,
      defaults: cfg.defaults ? { ...cfg.defaults, [key]: undefined } : undefined,
    }));
  }

  /** Clear the whole v3 `defaults` bucket. */
  async clearDefaults(): Promise<void> {
    const name = this.getEffectiveConfigName();
    await configFileStorage.update(name, (cfg) => ({ ...cfg, defaults: undefined }));
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
  ): Promise<T & { team?: string; region?: string; machine?: string }> {
    type Result = T & {
      team?: string;
      region?: string;
      machine?: string;
    };
    const base = { ...options };
    const result = base as Result;
    result.team ??= await this.getTeam();
    result.region ??= await this.getRegion();
    return result;
  }
}

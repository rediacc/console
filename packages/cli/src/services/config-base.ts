import { DEFAULTS } from '@rediacc/shared/config';
import {
  detectSystemLanguage,
  getSupportedLanguages as getSupportedLanguagesList,
  isLanguageSupported as isLanguageSupportedCheck,
  normalizeLanguage,
} from './context-language.js';
import { configFileStorage } from '../adapters/config-file-storage.js';
import { hasCloudCredentials } from '../types/index.js';
import type { ResourceState } from './resource-state.js';
import type { RdcConfig, S3Config } from '../types/index.js';

const DEFAULT_API_URL = 'https://www.rediacc.com/api';

/**
 * Service for managing CLI config files.
 * Each config is a separate file (e.g., rediacc.json, production.json).
 * In self-hosted modes (local/S3), resource CRUD delegates to ResourceState:
 *   - S3 mode: S3StateService (state.json in bucket)
 *   - Local mode: LocalResourceState (config file, with optional encryption)
 */
export class ConfigServiceBase {
  private runtimeConfigOverride: string | null = null;
  private _resourceState: ResourceState | null = null;

  /**
   * Set a runtime config override (used by --config flag).
   * Takes precedence over default config name.
   */
  setRuntimeConfig(name: string | null): void {
    this.runtimeConfigOverride = name;
    this._resourceState = null;
  }

  /**
   * Get the ResourceState for the current config, initializing lazily.
   * Returns S3StateService when config.s3 is populated, LocalResourceState otherwise.
   */
  async getResourceState(): Promise<ResourceState> {
    if (this._resourceState) return this._resourceState;

    const config = await this.getCurrent();
    if (!config) throw new Error('No active config');

    let masterPassword: string | null = null;
    if (config.masterPassword) {
      const { authService } = await import('./auth.js');
      masterPassword = await authService.requireMasterPassword();
    }

    const configName = this.getEffectiveConfigName();

    if (config.s3) {
      let decryptedSecret: string;
      if (masterPassword) {
        const { nodeCryptoProvider } = await import('../adapters/crypto.js');
        decryptedSecret = await nodeCryptoProvider.decrypt(
          config.s3.secretAccessKey,
          masterPassword
        );
      } else {
        decryptedSecret = config.s3.secretAccessKey;
      }

      const { S3ClientService } = await import('./s3-client.js');
      const s3Client = new S3ClientService({
        ...config.s3,
        secretAccessKey: decryptedSecret,
      });

      const { S3StateService } = await import('./s3-state.js');
      this._resourceState = await S3StateService.load(s3Client, masterPassword);
    } else {
      const { LocalResourceState } = await import('./resource-state.js');
      this._resourceState = await LocalResourceState.load(config, configName, masterPassword);
    }

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
   */
  async getCurrent(): Promise<RdcConfig | null> {
    const name = this.getEffectiveConfigName();

    // Auto-create the default config on first access
    if (name === 'rediacc') {
      return configFileStorage.getOrCreateDefault();
    }

    const exists = await configFileStorage.exists(name);
    if (!exists) return null;
    return configFileStorage.load(name);
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
    return config?.apiUrl ?? DEFAULT_API_URL;
  }

  async getToken(): Promise<string | null> {
    if (process.env.REDIACC_TOKEN) {
      return process.env.REDIACC_TOKEN;
    }
    const config = await this.getCurrent();
    return config?.token ?? null;
  }

  async setToken(token: string): Promise<void> {
    const name = this.getEffectiveConfigName();
    const exists = await configFileStorage.exists(name);
    if (!exists) return;
    await this.update(name, { token });
  }

  async getMasterPassword(): Promise<string | null> {
    const config = await this.getCurrent();
    return config?.masterPassword ?? null;
  }

  async setMasterPassword(password: string): Promise<void> {
    const name = this.getEffectiveConfigName();
    const exists = await configFileStorage.exists(name);
    if (!exists) return;
    await this.update(name, { masterPassword: password });
  }

  async getUserEmail(): Promise<string | null> {
    const config = await this.getCurrent();
    return config?.userEmail ?? null;
  }

  // ============================================================================
  // Config Defaults (team, region, bridge, machine)
  // ============================================================================

  async getTeam(): Promise<string | undefined> {
    if (process.env.REDIACC_TEAM) return process.env.REDIACC_TEAM;
    const config = await this.getCurrent();
    return config?.team;
  }

  async getRegion(): Promise<string | undefined> {
    if (process.env.REDIACC_REGION) return process.env.REDIACC_REGION;
    const config = await this.getCurrent();
    return config?.region;
  }

  async getBridge(): Promise<string | undefined> {
    if (process.env.REDIACC_BRIDGE) return process.env.REDIACC_BRIDGE;
    const config = await this.getCurrent();
    return config?.bridge;
  }

  async getMachine(): Promise<string | undefined> {
    if (process.env.REDIACC_MACHINE) return process.env.REDIACC_MACHINE;
    const config = await this.getCurrent();
    return config?.machine;
  }

  async set(key: 'team' | 'region' | 'bridge' | 'machine', value: string): Promise<void> {
    const name = this.getEffectiveConfigName();
    await this.update(name, { [key]: value });
  }

  async remove(key: 'team' | 'region' | 'bridge' | 'machine'): Promise<void> {
    const name = this.getEffectiveConfigName();
    await this.update(name, { [key]: undefined });
  }

  async clearDefaults(): Promise<void> {
    const name = this.getEffectiveConfigName();
    await this.update(name, {
      team: undefined,
      region: undefined,
      bridge: undefined,
      machine: undefined,
    });
  }

  // --- Language Settings ---

  async getLanguage(): Promise<string> {
    if (process.env.REDIACC_LANG) return normalizeLanguage(process.env.REDIACC_LANG);
    const config = await this.getCurrent();
    if (config?.language) return config.language;
    return detectSystemLanguage();
  }

  async setLanguage(language: string): Promise<void> {
    const name = this.getEffectiveConfigName();
    await this.update(name, { language: normalizeLanguage(language) });
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
    result.machine ??= await this.getMachine();
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
    if (exists) {
      await this.update(configName, {
        apiUrl: credentials.apiUrl,
        token: credentials.token,
        userEmail: credentials.userEmail,
        masterPassword: credentials.masterPassword,
      });
    } else {
      const config = await configFileStorage.init(configName);
      await configFileStorage.save(
        {
          ...config,
          apiUrl: credentials.apiUrl,
          token: credentials.token,
          userEmail: credentials.userEmail,
          masterPassword: credentials.masterPassword,
        },
        configName
      );
    }
  }

  async clearCredentials(): Promise<void> {
    const name = this.getEffectiveConfigName();
    const exists = await configFileStorage.exists(name);
    if (!exists) return;
    await this.update(name, { token: undefined, masterPassword: undefined });
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

  async hasS3ResourceState(): Promise<boolean> {
    const config = await this.getCurrent();
    return config?.s3 != null;
  }

  async getS3Config(): Promise<S3Config> {
    const config = await this.getCurrent();
    const name = this.getEffectiveConfigName();
    if (!config) throw new Error('No active config');
    if (!config.s3) throw new Error(`Config "${name}" has no S3 configuration`);
    return config.s3;
  }
}

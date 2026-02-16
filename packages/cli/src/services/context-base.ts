import { configStorage } from '../adapters/storage.js';
import type { NamedContext, S3Config } from '../types/index.js';
import {
  detectSystemLanguage,
  getSupportedLanguages as getSupportedLanguagesList,
  isLanguageSupported as isLanguageSupportedCheck,
  normalizeLanguage,
} from './context-language.js';
import type { ResourceState } from './resource-state.js';

const DEFAULT_API_URL = 'https://www.rediacc.com/api';

/**
 * Service for managing CLI contexts.
 * Supports multiple named contexts with independent credentials and defaults.
 * In self-hosted modes (local/S3), resource CRUD delegates to ResourceState:
 *   - S3 mode: S3StateService (state.json in bucket)
 *   - Local mode: LocalResourceState (config.json, with optional encryption)
 */
export class ContextServiceBase {
  private runtimeContextOverride: string | null = null;
  private _resourceState: ResourceState | null = null;

  /**
   * Set a runtime context override (used by --context flag).
   * Takes precedence over stored currentContext.
   */
  setRuntimeContext(name: string | null): void {
    this.runtimeContextOverride = name;
    this._resourceState = null; // Reset cached state on context switch
  }

  /**
   * Get the ResourceState for the current context, initializing lazily.
   * Returns S3StateService for S3 mode or LocalResourceState for local mode.
   * Caches the instance for the session.
   */
  async getResourceState(): Promise<ResourceState> {
    if (this._resourceState) return this._resourceState;

    const context = await this.getCurrent();
    if (!context) throw new Error('No active context');

    let masterPassword: string | null = null;
    if (context.masterPassword) {
      const { authService } = await import('./auth.js');
      masterPassword = await authService.requireMasterPassword();
    }

    if (context.mode === 's3') {
      if (!context.s3) throw new Error(`Context "${context.name}" has no S3 configuration`);

      let decryptedSecret: string;
      if (masterPassword) {
        const { nodeCryptoProvider } = await import('../adapters/crypto.js');
        decryptedSecret = await nodeCryptoProvider.decrypt(
          context.s3.secretAccessKey,
          masterPassword
        );
      } else {
        decryptedSecret = context.s3.secretAccessKey;
      }

      const { S3ClientService } = await import('./s3-client.js');
      const s3Client = new S3ClientService({
        ...context.s3,
        secretAccessKey: decryptedSecret,
      });

      const { S3StateService } = await import('./s3-state.js');
      this._resourceState = await S3StateService.load(s3Client, masterPassword);
    } else {
      const { LocalResourceState } = await import('./resource-state.js');
      this._resourceState = await LocalResourceState.load(context, masterPassword);
    }

    return this._resourceState;
  }

  /**
   * Get the effective context name (--context flag or "default").
   * Always returns a context name - never null.
   */
  protected getEffectiveContextName(): string {
    // Only two options: --context flag or "default"
    return this.runtimeContextOverride ?? 'default';
  }

  // ============================================================================
  // Context CRUD Operations
  // ============================================================================

  /**
   * List all contexts.
   */
  async list(): Promise<NamedContext[]> {
    const config = await configStorage.load();
    return Object.values(config.contexts).filter((ctx): ctx is NamedContext => ctx !== undefined);
  }

  /**
   * Get a context by name.
   */
  async get(name: string): Promise<NamedContext | null> {
    const config = await configStorage.load();
    return config.contexts[name] ?? null;
  }

  /**
   * Get the current active context.
   */
  async getCurrent(): Promise<NamedContext | null> {
    const name = this.getEffectiveContextName();
    return this.get(name);
  }

  /**
   * Get the current context name.
   * Always returns a context name (from flag, env var, or "default").
   */
  getCurrentName(): string {
    return this.getEffectiveContextName();
  }

  /**
   * Create a new context.
   */
  async create(context: NamedContext): Promise<void> {
    await configStorage.update((config) => {
      if (config.contexts[context.name]) {
        throw new Error(`Context "${context.name}" already exists`);
      }
      return {
        ...config,
        contexts: {
          ...config.contexts,
          [context.name]: context,
        },
      };
    });
  }

  /**
   * Update an existing context.
   */
  async update(name: string, updates: Partial<Omit<NamedContext, 'name'>>): Promise<void> {
    await configStorage.update((config) => {
      const existing = config.contexts[name];
      if (!existing) {
        throw new Error(`Context "${name}" not found`);
      }
      return {
        ...config,
        contexts: {
          ...config.contexts,
          [name]: { ...existing, ...updates },
        },
      };
    });
  }

  /**
   * Delete a context.
   */
  async delete(name: string): Promise<void> {
    await configStorage.update((config) => {
      if (!config.contexts[name]) {
        throw new Error(`Context "${name}" not found`);
      }
      const remaining = { ...config.contexts };
      delete remaining[name];
      return { ...config, contexts: remaining };
    });
  }

  /**
   * Rename a context.
   */
  async rename(oldName: string, newName: string): Promise<void> {
    await configStorage.update((config) => {
      const existing = config.contexts[oldName];
      if (!existing) {
        throw new Error(`Context "${oldName}" not found`);
      }
      if (config.contexts[newName]) {
        throw new Error(`Context "${newName}" already exists`);
      }
      const remaining = { ...config.contexts };
      delete remaining[oldName];
      return {
        ...config,
        contexts: {
          ...remaining,
          [newName]: { ...existing, name: newName },
        },
      };
    });
  }

  // ============================================================================
  // Credential Helpers (for API client integration)
  // ============================================================================

  /**
   * Get the API URL for the current context.
   */
  async getApiUrl(): Promise<string> {
    // Check env var first
    if (process.env.REDIACC_API_URL) {
      return process.env.REDIACC_API_URL;
    }
    const context = await this.getCurrent();
    return context?.apiUrl ?? DEFAULT_API_URL;
  }

  /**
   * Get the token for the current context.
   */
  async getToken(): Promise<string | null> {
    // Check env var first
    if (process.env.REDIACC_TOKEN) {
      return process.env.REDIACC_TOKEN;
    }
    const context = await this.getCurrent();
    return context?.token ?? null;
  }

  /**
   * Set the token for the current context.
   */
  async setToken(token: string): Promise<void> {
    const name = this.getEffectiveContextName();
    const existing = await this.get(name);

    // Skip token save if context doesn't exist yet (e.g., during first login)
    // The context will be created properly after login completes
    if (!existing) {
      return;
    }

    await this.update(name, { token });
  }

  /**
   * Get the master password for the current context.
   */
  async getMasterPassword(): Promise<string | null> {
    const context = await this.getCurrent();
    return context?.masterPassword ?? null;
  }

  /**
   * Set the master password for the current context.
   */
  async setMasterPassword(password: string): Promise<void> {
    const name = this.getEffectiveContextName();
    const existing = await this.get(name);

    // Skip if context doesn't exist yet
    if (!existing) {
      return;
    }

    await this.update(name, { masterPassword: password });
  }

  /**
   * Get the user email for the current context.
   */
  async getUserEmail(): Promise<string | null> {
    const context = await this.getCurrent();
    return context?.userEmail ?? null;
  }

  // ============================================================================
  // Context Defaults (team, region, bridge, machine)
  // ============================================================================

  async getTeam(): Promise<string | undefined> {
    if (process.env.REDIACC_TEAM) {
      return process.env.REDIACC_TEAM;
    }
    const context = await this.getCurrent();
    return context?.team;
  }

  async getRegion(): Promise<string | undefined> {
    if (process.env.REDIACC_REGION) {
      return process.env.REDIACC_REGION;
    }
    const context = await this.getCurrent();
    return context?.region;
  }

  async getBridge(): Promise<string | undefined> {
    if (process.env.REDIACC_BRIDGE) {
      return process.env.REDIACC_BRIDGE;
    }
    const context = await this.getCurrent();
    return context?.bridge;
  }

  async getMachine(): Promise<string | undefined> {
    if (process.env.REDIACC_MACHINE) {
      return process.env.REDIACC_MACHINE;
    }
    const context = await this.getCurrent();
    return context?.machine;
  }

  async set(key: 'team' | 'region' | 'bridge' | 'machine', value: string): Promise<void> {
    const name = this.getEffectiveContextName();
    await this.update(name, { [key]: value });
  }

  async remove(key: 'team' | 'region' | 'bridge' | 'machine'): Promise<void> {
    const name = this.getEffectiveContextName();
    await this.update(name, { [key]: undefined });
  }

  async clearDefaults(): Promise<void> {
    const name = this.getEffectiveContextName();
    await this.update(name, {
      team: undefined,
      region: undefined,
      bridge: undefined,
      machine: undefined,
    });
  }

  // --- Language Settings ---

  async getLanguage(): Promise<string> {
    if (process.env.REDIACC_LANG) {
      return normalizeLanguage(process.env.REDIACC_LANG);
    }
    const context = await this.getCurrent();
    if (context?.language) return context.language;
    return detectSystemLanguage();
  }

  async setLanguage(language: string): Promise<void> {
    const name = this.getEffectiveContextName();
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
  // Login Helper (creates/updates context on login)
  // ============================================================================

  /**
   * Save login credentials to a context.
   * Creates the context if it doesn't exist.
   */
  async saveLoginCredentials(
    contextName: string,
    credentials: {
      apiUrl: string;
      token: string;
      userEmail: string;
      masterPassword?: string;
    }
  ): Promise<void> {
    await configStorage.update((config) => {
      const existing = config.contexts[contextName];
      const context: NamedContext = {
        name: contextName,
        apiUrl: credentials.apiUrl,
        token: credentials.token,
        userEmail: credentials.userEmail,
        masterPassword: credentials.masterPassword,
        team: existing?.team,
        region: existing?.region,
      };
      return {
        ...config,
        contexts: {
          ...config.contexts,
          [contextName]: context,
        },
      };
    });
  }

  /**
   * Clear credentials from the current context (logout).
   */
  async clearCredentials(): Promise<void> {
    const name = this.getEffectiveContextName();
    const existing = await this.get(name);

    // Skip if context doesn't exist
    if (!existing) {
      return;
    }

    await this.update(name, { token: undefined, masterPassword: undefined });
  }

  /**
   * Check if the current context has a valid token.
   */
  async hasToken(): Promise<boolean> {
    const token = await this.getToken();
    return token !== null;
  }

  // ============================================================================
  // Mode Helpers
  // ============================================================================

  /**
   * Check if the current context is in a self-hosted mode (local or S3).
   */
  async isSelfHostedMode(): Promise<boolean> {
    const context = await this.getCurrent();
    const mode = context?.mode ?? 'cloud';
    return mode !== 'cloud';
  }

  /**
   * Check if the current context is in local mode.
   */
  async isLocalMode(): Promise<boolean> {
    const context = await this.getCurrent();
    return context?.mode === 'local';
  }

  /**
   * Check if a specific context is in local mode.
   */
  async isLocalContext(name: string): Promise<boolean> {
    const context = await this.get(name);
    return context?.mode === 'local';
  }

  /**
   * Check if the current context is in S3 mode.
   */
  async isS3Mode(): Promise<boolean> {
    const context = await this.getCurrent();
    return context?.mode === 's3';
  }

  /**
   * Get S3 configuration for the current context.
   * Throws if context is not in S3 mode.
   */
  async getS3Config(): Promise<S3Config> {
    const context = await this.getCurrent();
    if (!context) {
      throw new Error('No active context');
    }
    if (context.mode !== 's3') {
      throw new Error(`Context "${context.name}" is not in S3 mode`);
    }
    if (!context.s3) {
      throw new Error(`Context "${context.name}" has no S3 configuration`);
    }
    return context.s3;
  }

  /**
   * Create a new S3 context.
   * Only stores S3 credentials, SSH key paths, and master password in config.json.
   * Machines/storages/repositories live in state.json in the S3 bucket.
   */
  async createS3(
    name: string,
    s3Config: S3Config,
    sshKeyPath: string,
    options?: { renetPath?: string; masterPassword?: string }
  ): Promise<void> {
    const context: NamedContext = {
      name,
      mode: 's3',
      apiUrl: 's3://', // Not used in S3 mode but required by interface
      s3: s3Config,
      ssh: {
        privateKeyPath: sshKeyPath,
        publicKeyPath: `${sshKeyPath}.pub`,
      },
      renetPath: options?.renetPath,
      masterPassword: options?.masterPassword,
    };
    await this.create(context);
  }
}

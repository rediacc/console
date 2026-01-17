import { DEFAULTS } from '@rediacc/shared/config';
import { configStorage } from '../adapters/storage.js';
import type { LocalMachineConfig, LocalSSHConfig, NamedContext } from '../types/index.js';

const DEFAULT_API_URL = 'https://www.rediacc.com/api';

/**
 * Service for managing CLI contexts.
 * Supports multiple named contexts with independent credentials and defaults.
 */
class ContextService {
  private runtimeContextOverride: string | null = null;

  /**
   * Set a runtime context override (used by --context flag).
   * Takes precedence over stored currentContext.
   */
  setRuntimeContext(name: string | null): void {
    this.runtimeContextOverride = name;
  }

  /**
   * Get the effective context name (--context flag or "default").
   * Always returns a context name - never null.
   */
  private getEffectiveContextName(): string {
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
      return { contexts: remaining };
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

  // ============================================================================
  // Language Settings
  // ============================================================================

  private readonly supportedLanguages = ['en', 'de', 'es', 'fr', 'ja', 'ar', 'ru', 'tr', 'zh'];

  /**
   * Normalize a language code to a supported language.
   * Handles variants like 'en-US' -> 'en', 'zh-CN' -> 'zh'.
   */
  private normalizeLanguage(lang: string): string {
    const base = lang.split('-')[0].split('_')[0].toLowerCase();
    return this.supportedLanguages.includes(base) ? base : 'en';
  }

  /**
   * Detect system language from environment variables.
   */
  private detectSystemLanguage(): string {
    const sysLang = process.env.LANG ?? process.env.LC_ALL ?? '';
    return this.normalizeLanguage(sysLang);
  }

  /**
   * Get the language for the current context.
   * Priority: REDIACC_LANG env > context.language > system locale > 'en'
   */
  async getLanguage(): Promise<string> {
    // Check env var first
    if (process.env.REDIACC_LANG) {
      return this.normalizeLanguage(process.env.REDIACC_LANG);
    }
    // Check context
    const context = await this.getCurrent();
    if (context?.language) {
      return context.language;
    }
    // Fallback to system locale
    return this.detectSystemLanguage();
  }

  /**
   * Set the language for the current context.
   */
  async setLanguage(language: string): Promise<void> {
    const name = this.getEffectiveContextName();
    const normalized = this.normalizeLanguage(language);
    await this.update(name, { language: normalized });
  }

  /**
   * Check if a language code is supported.
   */
  isLanguageSupported(lang: string): boolean {
    const base = lang.split('-')[0].split('_')[0].toLowerCase();
    return this.supportedLanguages.includes(base);
  }

  /**
   * Get the list of supported languages.
   */
  getSupportedLanguages(): string[] {
    return [...this.supportedLanguages];
  }

  async applyDefaults<T extends object>(
    options: T
  ): Promise<T & { team?: string; region?: string; bridge?: string; machine?: string }> {
    type Result = T & { team?: string; region?: string; bridge?: string; machine?: string };
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
  // Local Mode Support
  // ============================================================================

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
   * Get local configuration for the current context.
   * Throws if context is not in local mode.
   */
  async getLocalConfig(): Promise<{
    machines: Record<string, LocalMachineConfig | undefined>;
    ssh: LocalSSHConfig;
    renetPath: string;
  }> {
    const context = await this.getCurrent();
    if (!context) {
      throw new Error('No active context');
    }
    if (context.mode !== 'local') {
      throw new Error(`Context "${context.name}" is not in local mode`);
    }
    if (!context.machines || Object.keys(context.machines).length === 0) {
      throw new Error(`Context "${context.name}" has no machines configured`);
    }
    if (!context.ssh?.privateKeyPath) {
      throw new Error(`Context "${context.name}" has no SSH key configured`);
    }
    return {
      machines: context.machines,
      ssh: context.ssh,
      renetPath: context.renetPath ?? DEFAULTS.CONTEXT.RENET_BINARY,
    };
  }

  /**
   * Get a specific machine configuration from the current local context.
   */
  async getLocalMachine(machineName: string): Promise<LocalMachineConfig> {
    const config = await this.getLocalConfig();
    const machine = config.machines[machineName];
    if (!machine) {
      const available = Object.keys(config.machines).join(', ');
      throw new Error(`Machine "${machineName}" not found. Available: ${available}`);
    }
    return machine;
  }

  /**
   * Create a new local context.
   */
  async createLocal(
    name: string,
    sshKeyPath: string,
    options?: { renetPath?: string }
  ): Promise<void> {
    const context: NamedContext = {
      name,
      mode: 'local',
      apiUrl: 'local://', // Not used in local mode but required by interface
      ssh: {
        privateKeyPath: sshKeyPath,
        publicKeyPath: `${sshKeyPath}.pub`,
      },
      machines: {},
      renetPath: options?.renetPath,
    };
    await this.create(context);
  }

  /**
   * Add a machine to the current local context.
   */
  async addLocalMachine(machineName: string, config: LocalMachineConfig): Promise<void> {
    const name = this.getEffectiveContextName();
    const context = await this.get(name);
    if (context?.mode !== 'local') {
      throw new Error('Current context is not in local mode');
    }

    const existingMachines = context.machines ?? {};
    await this.update(name, {
      machines: {
        ...existingMachines,
        [machineName]: config,
      },
    });
  }

  /**
   * Remove a machine from the current local context.
   */
  async removeLocalMachine(machineName: string): Promise<void> {
    const name = this.getEffectiveContextName();
    const context = await this.get(name);
    if (context?.mode !== 'local') {
      throw new Error('Current context is not in local mode');
    }

    if (!context.machines?.[machineName]) {
      throw new Error(`Machine "${machineName}" not found`);
    }

    const remaining = { ...context.machines };
    delete remaining[machineName];
    await this.update(name, { machines: remaining });
  }

  /**
   * List machines in the current local context.
   */
  async listLocalMachines(): Promise<{ name: string; config: LocalMachineConfig }[]> {
    const context = await this.getCurrent();
    if (!context) {
      throw new Error('No active context');
    }
    if (context.mode !== 'local') {
      throw new Error('Current context is not in local mode');
    }
    return Object.entries(context.machines ?? {}).map(([name, config]) => ({
      name,
      config,
    }));
  }

  /**
   * Update SSH configuration for the current local context.
   */
  async setLocalSSH(ssh: LocalSSHConfig): Promise<void> {
    const name = this.getEffectiveContextName();
    const context = await this.get(name);
    if (context?.mode !== 'local') {
      throw new Error('Current context is not in local mode');
    }
    await this.update(name, { ssh });
  }

  /**
   * Set renet binary path for the current local context.
   */
  async setRenetPath(renetPath: string): Promise<void> {
    const name = this.getEffectiveContextName();
    const context = await this.get(name);
    if (context?.mode !== 'local') {
      throw new Error('Current context is not in local mode');
    }
    await this.update(name, { renetPath });
  }
}

export const contextService = new ContextService();

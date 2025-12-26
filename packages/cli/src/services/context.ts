import { configStorage } from '../adapters/storage.js';
import type { CliConfig, NamedContext } from '../types/index.js';

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
   * Get the effective context name (runtime override > env var > stored).
   */
  private async getEffectiveContextName(): Promise<string | null> {
    // Priority: runtime override > env var > stored
    if (this.runtimeContextOverride) {
      return this.runtimeContextOverride;
    }
    if (process.env.REDIACC_CONTEXT) {
      return process.env.REDIACC_CONTEXT;
    }
    const config = await configStorage.load();
    return config.currentContext || null;
  }

  // ============================================================================
  // Context CRUD Operations
  // ============================================================================

  /**
   * List all contexts.
   */
  async list(): Promise<NamedContext[]> {
    const config = await configStorage.load();
    return Object.values(config.contexts);
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
    const name = await this.getEffectiveContextName();
    if (!name) return null;
    return this.get(name);
  }

  /**
   * Get the current context name.
   */
  async getCurrentName(): Promise<string | null> {
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
      const { [name]: _, ...remaining } = config.contexts;
      return {
        currentContext: config.currentContext === name ? '' : config.currentContext,
        contexts: remaining,
      };
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
      const { [oldName]: _, ...remaining } = config.contexts;
      return {
        currentContext: config.currentContext === oldName ? newName : config.currentContext,
        contexts: {
          ...remaining,
          [newName]: { ...existing, name: newName },
        },
      };
    });
  }

  /**
   * Switch to a different context.
   */
  async use(name: string): Promise<void> {
    await configStorage.update((config) => {
      if (!config.contexts[name]) {
        throw new Error(`Context "${name}" not found`);
      }
      return {
        ...config,
        currentContext: name,
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
    const name = await this.getEffectiveContextName();
    if (!name) {
      throw new Error('No active context. Create or select a context first.');
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
    const name = await this.getEffectiveContextName();
    if (!name) {
      throw new Error('No active context. Create or select a context first.');
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
    const name = await this.getEffectiveContextName();
    if (!name) {
      throw new Error('No active context. Create or select a context first.');
    }
    await this.update(name, { [key]: value });
  }

  async remove(key: 'team' | 'region' | 'bridge' | 'machine'): Promise<void> {
    const name = await this.getEffectiveContextName();
    if (!name) {
      throw new Error('No active context. Create or select a context first.');
    }
    await this.update(name, { [key]: undefined });
  }

  async clearDefaults(): Promise<void> {
    const name = await this.getEffectiveContextName();
    if (!name) {
      throw new Error('No active context. Create or select a context first.');
    }
    await this.update(name, { team: undefined, region: undefined, bridge: undefined, machine: undefined });
  }

  async applyDefaults(options: { team?: string; region?: string; bridge?: string; machine?: string; [key: string]: unknown }): Promise<typeof options> {
    const result = { ...options };
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
        currentContext: contextName,
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
    const name = await this.getEffectiveContextName();
    if (!name) return;
    await this.update(name, { token: undefined, masterPassword: undefined });
  }

  /**
   * Check if the current context has a valid token.
   */
  async hasToken(): Promise<boolean> {
    const token = await this.getToken();
    return token !== null;
  }
}

export const contextService = new ContextService();

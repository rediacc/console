import { DEFAULTS } from '@rediacc/shared/config';
import { MIN_NETWORK_ID, NETWORK_ID_INCREMENT } from '@rediacc/shared/queue-vault';
import { configStorage } from '../adapters/storage.js';
import type {
  MachineConfig,
  RepositoryConfig,
  SSHConfig,
  StorageConfig,
  NamedContext,
  S3Config,
} from '../types/index.js';
import type { S3StateService } from './s3-state.js';

const DEFAULT_API_URL = 'https://www.rediacc.com/api';

/**
 * Service for managing CLI contexts.
 * Supports multiple named contexts with independent credentials and defaults.
 * In S3 mode, CRUD operations delegate to S3StateService (state.json in bucket).
 * In local mode, CRUD operations read/write config.json directly.
 */
class ContextService {
  private runtimeContextOverride: string | null = null;
  private s3State: S3StateService | null = null;

  /**
   * Set a runtime context override (used by --context flag).
   * Takes precedence over stored currentContext.
   */
  setRuntimeContext(name: string | null): void {
    this.runtimeContextOverride = name;
    this.s3State = null; // Reset cached S3 state on context switch
  }

  /**
   * Get S3StateService for the current context, initializing lazily.
   * Only called when mode === 's3'. Caches the instance for the session.
   */
  private async getS3State(): Promise<S3StateService> {
    if (this.s3State) return this.s3State;

    const context = await this.getCurrent();
    if (!context?.s3) throw new Error(`Context "${context?.name}" has no S3 configuration`);

    let decryptedSecret: string;
    let masterPassword: string | null = null;

    if (context.masterPassword) {
      const { authService } = await import('./auth.js');
      masterPassword = await authService.requireMasterPassword();
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

    const { S3StateService: S3StateSvc } = await import('./s3-state.js');
    this.s3State = await S3StateSvc.load(s3Client, masterPassword);
    return this.s3State;
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

  // ============================================================================
  // S3 Mode Support
  // ============================================================================

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

  /**
   * Require the current context to be in local or S3 mode.
   * If a context name is provided, fetches it directly; otherwise uses the current context.
   */
  private async requireLocalOrS3Mode(contextName?: string): Promise<NamedContext> {
    const context = contextName ? await this.get(contextName) : await this.getCurrent();
    if (!context) {
      throw new Error('No active context');
    }
    if (context.mode !== 'local' && context.mode !== 's3') {
      throw new Error(`Context "${context.name}" is not in local or S3 mode`);
    }
    return context;
  }

  /**
   * Get local configuration for the current context.
   * In S3 mode, reads machines/SSH from state.json; in local mode, from config.json.
   */
  async getLocalConfig(): Promise<{
    machines: Record<string, MachineConfig | undefined>;
    ssh: SSHConfig;
    sshPrivateKey?: string;
    sshPublicKey?: string;
    renetPath: string;
  }> {
    const context = await this.requireLocalOrS3Mode();

    if (context.mode === 's3') {
      const s3 = await this.getS3State();
      const machines = s3.getMachines();
      if (!machines || Object.keys(machines).length === 0) {
        throw new Error(`Context "${context.name}" has no machines configured`);
      }
      const sshContent = s3.getSSH();
      if (!sshContent?.privateKey && !context.ssh?.privateKeyPath) {
        throw new Error(`Context "${context.name}" has no SSH key configured`);
      }
      return {
        machines,
        ssh: context.ssh ?? { privateKeyPath: '' },
        sshPrivateKey: sshContent?.privateKey,
        sshPublicKey: sshContent?.publicKey,
        renetPath: context.renetPath ?? DEFAULTS.CONTEXT.RENET_BINARY,
      };
    }

    // Local mode
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
   * Get a specific machine configuration from the current context.
   */
  async getLocalMachine(machineName: string): Promise<MachineConfig> {
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
   * Add a machine to the current local/s3 context.
   */
  async addLocalMachine(machineName: string, config: MachineConfig): Promise<void> {
    const name = this.getEffectiveContextName();
    const context = await this.requireLocalOrS3Mode(name);

    if (context.mode === 's3') {
      const s3 = await this.getS3State();
      const machines = s3.getMachines();
      machines[machineName] = config;
      await s3.setMachines(machines);
      return;
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
   * Remove a machine from the current local/s3 context.
   */
  async removeLocalMachine(machineName: string): Promise<void> {
    const name = this.getEffectiveContextName();
    const context = await this.requireLocalOrS3Mode(name);

    if (context.mode === 's3') {
      const s3 = await this.getS3State();
      const machines = s3.getMachines();
      if (!machines[machineName]) throw new Error(`Machine "${machineName}" not found`);
      delete machines[machineName];
      await s3.setMachines(machines);
      return;
    }

    if (!context.machines?.[machineName]) {
      throw new Error(`Machine "${machineName}" not found`);
    }

    const remaining = { ...context.machines };
    delete remaining[machineName];
    await this.update(name, { machines: remaining });
  }

  /**
   * List machines in the current local/s3 context.
   */
  async listLocalMachines(): Promise<{ name: string; config: MachineConfig }[]> {
    const context = await this.requireLocalOrS3Mode();

    if (context.mode === 's3') {
      const s3 = await this.getS3State();
      return Object.entries(s3.getMachines()).map(([name, config]) => ({ name, config }));
    }

    return Object.entries(context.machines ?? {}).map(([name, config]) => ({
      name,
      config,
    }));
  }

  /**
   * Update specific fields of an existing machine in the current local/s3 context.
   */
  async updateLocalMachine(
    machineName: string,
    updates: Partial<MachineConfig>
  ): Promise<void> {
    const name = this.getEffectiveContextName();
    const context = await this.requireLocalOrS3Mode(name);

    if (context.mode === 's3') {
      const s3 = await this.getS3State();
      const machines = s3.getMachines();
      const existing = machines[machineName];
      if (!existing) throw new Error(`Machine "${machineName}" not found`);
      machines[machineName] = { ...existing, ...updates };
      await s3.setMachines(machines);
      return;
    }

    const existing = context.machines?.[machineName];
    if (!existing) {
      throw new Error(`Machine "${machineName}" not found`);
    }
    await this.update(name, {
      machines: {
        ...context.machines,
        [machineName]: { ...existing, ...updates },
      },
    });
  }

  /**
   * Update SSH configuration for the current local/s3 context.
   */
  async setLocalSSH(ssh: SSHConfig): Promise<void> {
    const name = this.getEffectiveContextName();
    await this.requireLocalOrS3Mode(name);
    await this.update(name, { ssh });
  }

  /**
   * Set renet binary path for the current local/s3 context.
   */
  async setRenetPath(renetPath: string): Promise<void> {
    const name = this.getEffectiveContextName();
    await this.requireLocalOrS3Mode(name);
    await this.update(name, { renetPath });
  }

  // ============================================================================
  // Local Storage Management
  // ============================================================================

  /**
   * Add a storage to the current local/s3 context.
   */
  async addLocalStorage(storageName: string, config: StorageConfig): Promise<void> {
    const name = this.getEffectiveContextName();
    const context = await this.requireLocalOrS3Mode(name);

    if (context.mode === 's3') {
      const s3 = await this.getS3State();
      const storages = s3.getStorages();
      storages[storageName] = config;
      await s3.setStorages(storages);
      return;
    }

    const existingStorages = context.storages ?? {};
    await this.update(name, {
      storages: {
        ...existingStorages,
        [storageName]: config,
      },
    });
  }

  /**
   * Remove a storage from the current local/s3 context.
   */
  async removeLocalStorage(storageName: string): Promise<void> {
    const name = this.getEffectiveContextName();
    const context = await this.requireLocalOrS3Mode(name);

    if (context.mode === 's3') {
      const s3 = await this.getS3State();
      const storages = s3.getStorages();
      if (!storages[storageName]) throw new Error(`Storage "${storageName}" not found`);
      delete storages[storageName];
      await s3.setStorages(storages);
      return;
    }

    if (!context.storages?.[storageName]) {
      throw new Error(`Storage "${storageName}" not found`);
    }

    const remaining = { ...context.storages };
    delete remaining[storageName];
    await this.update(name, { storages: remaining });
  }

  /**
   * List storages in the current local/s3 context.
   */
  async listLocalStorages(): Promise<{ name: string; config: StorageConfig }[]> {
    const context = await this.requireLocalOrS3Mode();

    if (context.mode === 's3') {
      const s3 = await this.getS3State();
      return Object.entries(s3.getStorages()).map(([name, config]) => ({ name, config }));
    }

    return Object.entries(context.storages ?? {}).map(([name, config]) => ({
      name,
      config,
    }));
  }

  /**
   * Get a specific storage configuration from the current context.
   */
  async getLocalStorage(storageName: string): Promise<StorageConfig> {
    const context = await this.requireLocalOrS3Mode();

    if (context.mode === 's3') {
      const s3 = await this.getS3State();
      const storage = s3.getStorages()[storageName];
      if (!storage) {
        const available = Object.keys(s3.getStorages()).join(', ');
        throw new Error(`Storage "${storageName}" not found. Available: ${available || 'none'}`);
      }
      return storage;
    }

    const storage = context.storages?.[storageName];
    if (!storage) {
      const available = Object.keys(context.storages ?? {}).join(', ');
      throw new Error(`Storage "${storageName}" not found. Available: ${available || 'none'}`);
    }
    return storage;
  }

  // ============================================================================
  // Local Repository Management
  // ============================================================================

  /**
   * Add a repository mapping to the current local/s3 context.
   */
  async addLocalRepository(repoName: string, config: RepositoryConfig): Promise<void> {
    const name = this.getEffectiveContextName();
    const context = await this.requireLocalOrS3Mode(name);

    if (context.mode === 's3') {
      const s3 = await this.getS3State();
      const repos = s3.getRepositories();
      repos[repoName] = config;
      await s3.setRepositories(repos);
      return;
    }

    const existing = context.repositories ?? {};
    await this.update(name, {
      repositories: {
        ...existing,
        [repoName]: config,
      },
    });
  }

  /**
   * Remove a repository mapping from the current local/s3 context.
   */
  async removeLocalRepository(repoName: string): Promise<void> {
    const name = this.getEffectiveContextName();
    const context = await this.requireLocalOrS3Mode(name);

    if (context.mode === 's3') {
      const s3 = await this.getS3State();
      const repos = s3.getRepositories();
      if (!repos[repoName]) throw new Error(`Repository "${repoName}" not found`);
      delete repos[repoName];
      await s3.setRepositories(repos);
      return;
    }

    if (!context.repositories?.[repoName]) {
      throw new Error(`Repository "${repoName}" not found`);
    }

    const remaining = { ...context.repositories };
    delete remaining[repoName];
    await this.update(name, { repositories: remaining });
  }

  /**
   * List repository mappings in the current local/s3 context.
   */
  async listLocalRepositories(): Promise<{ name: string; config: RepositoryConfig }[]> {
    const context = await this.requireLocalOrS3Mode();

    if (context.mode === 's3') {
      const s3 = await this.getS3State();
      return Object.entries(s3.getRepositories()).map(([name, config]) => ({ name, config }));
    }

    return Object.entries(context.repositories ?? {}).map(([repoName, config]) => ({
      name: repoName,
      config,
    }));
  }

  /**
   * Build a GUID-to-display-name map from all repository configurations.
   * Works in any context mode — returns empty map if no repositories are configured.
   */
  async getRepositoryGuidMap(): Promise<Record<string, string>> {
    const context = await this.getCurrent();
    let repos: Record<string, RepositoryConfig> | undefined;

    if (context?.mode === 's3') {
      const s3 = await this.getS3State();
      repos = s3.getRepositories();
    } else {
      repos = context?.repositories;
    }

    if (!repos) return {};
    const map: Record<string, string> = {};
    for (const [repoName, config] of Object.entries(repos)) {
      const tag = config.tag ?? DEFAULTS.REPOSITORY.TAG;
      map[config.repositoryGuid] = `${repoName}:${tag}`;
    }
    return map;
  }

  /**
   * Build a GUID-to-credential map from all repository configurations.
   * Used by vault builder to populate repository_credentials section.
   */
  async getRepositoryCredentials(): Promise<Record<string, string>> {
    const context = await this.getCurrent();
    let repos: Record<string, RepositoryConfig> | undefined;

    if (context?.mode === 's3') {
      const s3 = await this.getS3State();
      repos = s3.getRepositories();
    } else {
      repos = context?.repositories;
    }

    if (!repos) return {};
    const map: Record<string, string> = {};
    for (const [, config] of Object.entries(repos)) {
      if (config.credential) {
        map[config.repositoryGuid] = config.credential;
      }
    }
    return map;
  }

  /**
   * Get a repository config by name. Returns undefined if not found.
   */
  async getLocalRepository(repoName: string): Promise<RepositoryConfig | undefined> {
    const context = await this.getCurrent();

    if (context?.mode === 's3') {
      const s3 = await this.getS3State();
      return s3.getRepositories()[repoName];
    }

    return context?.repositories?.[repoName];
  }

  // ============================================================================
  // Network ID Allocation
  // ============================================================================

  /**
   * Compute the next available network ID based on existing repositories.
   * Returns MIN_NETWORK_ID (2816) if no repos have IDs, or max + INCREMENT otherwise.
   */
  private computeNextNetworkId(repositories: Record<string, RepositoryConfig>): number {
    const usedIds = Object.values(repositories)
      .map((r) => r.networkId)
      .filter((id): id is number => id !== undefined && id > 0);

    if (usedIds.length === 0) return MIN_NETWORK_ID;
    return Math.max(...usedIds) + NETWORK_ID_INCREMENT;
  }

  /**
   * Allocate the next available network ID for a new repository.
   */
  async allocateNetworkId(): Promise<number> {
    const context = await this.requireLocalOrS3Mode();

    if (context.mode === 's3') {
      const s3 = await this.getS3State();
      return this.computeNextNetworkId(s3.getRepositories());
    }

    return this.computeNextNetworkId(context.repositories ?? {});
  }

  /**
   * Ensure a repository has a network ID assigned.
   * If missing, auto-allocates and persists it.
   * Returns the (possibly newly assigned) network ID.
   */
  async ensureRepositoryNetworkId(repoName: string): Promise<number> {
    const name = this.getEffectiveContextName();
    const context = await this.requireLocalOrS3Mode(name);

    if (context.mode === 's3') {
      const s3 = await this.getS3State();
      const repos = s3.getRepositories();
      const repo = repos[repoName];
      if (!repo) throw new Error(`Repository "${repoName}" not found`);
      if (repo.networkId !== undefined && repo.networkId > 0) return repo.networkId;

      const networkId = this.computeNextNetworkId(repos);
      repos[repoName] = { ...repo, networkId };
      await s3.setRepositories(repos);
      return networkId;
    }

    const repo = context.repositories?.[repoName];
    if (!repo) {
      throw new Error(`Repository "${repoName}" not found`);
    }

    if (repo.networkId !== undefined && repo.networkId > 0) {
      return repo.networkId;
    }

    // Auto-allocate and persist
    const networkId = this.computeNextNetworkId(context.repositories ?? {});
    await this.update(name, {
      repositories: {
        ...context.repositories,
        [repoName]: { ...repo, networkId },
      },
    });

    return networkId;
  }
}

export const contextService = new ContextService();

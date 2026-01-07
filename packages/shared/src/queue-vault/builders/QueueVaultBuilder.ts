import { FUNCTION_REQUIREMENTS, isBridgeFunction } from '../data/functionRequirements';
import { safeValidateFunctionParams, getValidationErrors } from '../data/functions.schema';
import { minifyJSON } from '../utils/json';
import { getParamArray, getParamValue, isBase64, validateMachineVault } from '../utils/validation';
import { assertPublicBridgeFunction } from '../validation';
import type {
  ContextSection,
  FunctionRequirements,
  MachineSection,
  PreferencesSection,
  QueueRequestContext,
  QueueVaultV2,
  RepositoryInfo,
  SSHSection,
  StorageSection,
  TaskSection,
  VaultContent,
} from '../types';

export interface QueueVaultBuilderConfig {
  getApiUrl: () => string;
  encodeBase64: (value: string) => string;
  /** Enable validation of function parameters against Zod schemas (default: false) */
  validateParams?: boolean;
  /** Enable validation of machine connection details (default: false) */
  validateConnections?: boolean;
}

export class QueueVaultBuilder {
  constructor(private config: QueueVaultBuilderConfig) {}

  getFunctionRequirements(functionName: string): FunctionRequirements {
    if (!isBridgeFunction(functionName)) {
      return {};
    }
    const entry = FUNCTION_REQUIREMENTS[functionName];
    return entry.requirements;
  }

  buildQueueVault(context: QueueRequestContext): Promise<string> {
    return Promise.resolve(this.buildQueueVaultSync(context));
  }

  private buildQueueVaultSync(context: QueueRequestContext): string {
    try {
      // MANDATORY: Validate function is public before building vault.
      // Unknown, internal, or experimental functions will be rejected.
      assertPublicBridgeFunction(context.functionName);

      // Optional: Validate function parameters against Zod schemas
      if (this.config.validateParams && isBridgeFunction(context.functionName)) {
        const validationResult = safeValidateFunctionParams(context.functionName, context.params);
        if (!validationResult.success) {
          const errors = getValidationErrors(validationResult);
          throw new Error(`Parameter validation failed: ${errors}`);
        }
      }

      const requirements = this.getFunctionRequirements(context.functionName);

      // Build task section
      const task: TaskSection = {
        function: context.functionName,
        machine: context.machineName ?? '',
        team: context.teamName,
      };

      // Add repository to task if specified in params or context
      const repositoryName = context.repositoryName ?? getParamValue(context.params, 'repository');
      if (repositoryName) {
        task.repository = repositoryName;
      }

      // Build SSH section from team vault
      const ssh = this.buildSSHSection(context.teamVault, context.machineVault);

      // Build primary machine section
      const machine = this.buildMachineSection(
        context.machineVault,
        context.machineName ?? undefined
      );

      // Build the vault
      const vault: QueueVaultV2 = {
        $schema: 'queue-vault-v2',
        version: '2.0',
        task,
        ssh,
        machine,
      };

      // Add params if present
      if (Object.keys(context.params).length > 0) {
        vault.params = context.params as Record<string, string | number | boolean>;
      }

      // Build extra_machines for multi-machine operations
      const extraMachines = this.buildExtraMachines(context, requirements);
      if (Object.keys(extraMachines).length > 0) {
        vault.extra_machines = extraMachines;
      }

      // Build storage_systems
      const storageSystems = this.buildStorageSystems(context, requirements);
      if (Object.keys(storageSystems).length > 0) {
        vault.storage_systems = storageSystems;
      }

      // Build repository_credentials
      const repoCredentials = this.buildRepositoryCredentials(context, requirements);
      if (Object.keys(repoCredentials).length > 0) {
        vault.repository_credentials = repoCredentials;
      }

      // Build repositories map
      const repositories = this.buildRepositories(context, requirements);
      if (Object.keys(repositories).length > 0) {
        vault.repositories = repositories;
      }

      // Build context section
      const contextSection = this.buildContextSection(context);
      if (Object.keys(contextSection).length > 0) {
        vault.context = contextSection;
      }

      // Build preferences section
      const preferencesSection = this.buildPreferencesSection(context);
      if (preferencesSection) {
        vault.preferences = preferencesSection;
      }

      return minifyJSON(JSON.stringify(vault));
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unknown error';
      throw new Error(`Failed to build queue vault: ${message}`);
    }
  }

  private buildSSHSection(
    teamVault: VaultContent | undefined,
    machineVault: VaultContent | undefined
  ): SSHSection {
    const teamRecord = this.parseVaultRecord(teamVault);
    const machineRecord = this.parseVaultRecord(machineVault);

    return {
      private_key: String(teamRecord?.['SSH_PRIVATE_KEY'] ?? ''),
      public_key: String(teamRecord?.['SSH_PUBLIC_KEY'] ?? ''),
      known_hosts: teamRecord?.['SSH_KNOWN_HOSTS']
        ? String(teamRecord['SSH_KNOWN_HOSTS'])
        : undefined,
      password: this.resolveSshPassword(teamRecord, machineRecord),
    };
  }

  private resolveSshPassword(
    teamRecord: Record<string, unknown> | undefined,
    machineRecord: Record<string, unknown> | undefined
  ): string | undefined {
    const machinePassword = this.extractPassword(machineRecord);
    if (machinePassword) {
      return machinePassword;
    }
    return this.extractPassword(teamRecord);
  }

  private extractPassword(record: Record<string, unknown> | undefined): string | undefined {
    if (!record) {
      return undefined;
    }
    const raw = record['ssh_password'] ?? record['SSH_PASSWORD'];
    if (typeof raw !== 'string') {
      return undefined;
    }
    const trimmed = raw.trim();
    return trimmed === '' ? undefined : trimmed;
  }

  private parseVaultRecord(vault: VaultContent | undefined): Record<string, unknown> | undefined {
    if (!vault) {
      return undefined;
    }
    if (typeof vault === 'string') {
      try {
        return JSON.parse(vault);
      } catch {
        return undefined;
      }
    }
    return vault;
  }

  private buildMachineSection(
    machineVault: VaultContent | undefined,
    machineName?: string
  ): MachineSection {
    if (!machineVault) {
      return { ip: '', user: '' };
    }

    const vault = typeof machineVault === 'string' ? JSON.parse(machineVault) : machineVault;
    const vaultRecord = vault as Record<string, unknown>;

    // Optional: Validate machine connection details
    if (this.config.validateConnections) {
      const validation = validateMachineVault(vaultRecord);
      if (!validation.valid) {
        const machineRef = machineName ? ` for machine "${machineName}"` : '';
        throw new Error(`Invalid machine connection${machineRef}: ${validation.errors.join('; ')}`);
      }
    }

    return {
      ip: String(vaultRecord['ip'] ?? vaultRecord['IP'] ?? ''),
      user: String(vaultRecord['user'] ?? vaultRecord['USER'] ?? ''),
      port: this.parsePort(vaultRecord['port'] ?? vaultRecord['PORT']),
      datastore: vaultRecord['datastore'] ? String(vaultRecord['datastore']) : undefined,
      known_hosts: vaultRecord['known_hosts'] ? String(vaultRecord['known_hosts']) : undefined,
    };
  }

  private parsePort(value: unknown): number | undefined {
    if (value === undefined || value === null) return undefined;
    const port = typeof value === 'string' ? parseInt(value, 10) : Number(value);
    return isNaN(port) ? undefined : port;
  }

  private buildExtraMachines(
    context: QueueRequestContext,
    _requirements: FunctionRequirements
  ): Record<string, MachineSection> {
    const extraMachines: Record<string, MachineSection> = {};

    // Handle deploy destination machine
    if (context.functionName === 'backup_deploy') {
      const destinationName = (context.params as Record<string, string>).to;
      if (
        destinationName &&
        destinationName !== context.machineName &&
        context.destinationMachineVault
      ) {
        extraMachines[destinationName] = this.buildMachineSection(
          context.destinationMachineVault,
          destinationName
        );
      }
    }

    // Handle pull with machine source
    if (
      context.functionName === 'backup_pull' &&
      (context.params as Record<string, string>).sourceType === 'machine' &&
      (context.params as Record<string, string>).from
    ) {
      const fromName = (context.params as Record<string, string>).from;
      if (context.additionalMachineData?.[fromName]) {
        extraMachines[fromName] = this.buildMachineSection(
          context.additionalMachineData[fromName],
          fromName
        );
      }
    }

    // Handle list with machine source
    if (context.functionName === 'repository_list') {
      const sourceName = getParamValue(context.params, 'from');
      if (sourceName && context.additionalMachineData?.[sourceName]) {
        extraMachines[sourceName] = this.buildMachineSection(
          context.additionalMachineData[sourceName],
          sourceName
        );
      }
    }

    return extraMachines;
  }

  private buildStorageSystems(
    context: QueueRequestContext,
    _requirements: FunctionRequirements
  ): Record<string, StorageSection> {
    const storageSystems: Record<string, StorageSection> = {};

    // Handle backup function
    if (context.functionName === 'backup_create') {
      const targets = getParamArray(context.params, 'storages');
      if (!targets.length) {
        const fallbackTarget = getParamValue(context.params, 'to');
        if (fallbackTarget) {
          targets.push(fallbackTarget);
        }
      }
      targets.forEach((storageName, index) => {
        const storageVault =
          context.additionalStorageData?.[storageName] ??
          (index === 0 ? context.destinationStorageVault : undefined);
        if (storageVault) {
          storageSystems[storageName] = this.buildStorageConfig(storageVault);
        }
      });
    }

    // Handle list function
    if (context.functionName === 'repository_list') {
      const sourceName = getParamValue(context.params, 'from');
      if (sourceName && context.additionalStorageData?.[sourceName]) {
        storageSystems[sourceName] = this.buildStorageConfig(
          context.additionalStorageData[sourceName]
        );
      }
    }

    // Handle pull with storage source
    if (
      context.functionName === 'backup_pull' &&
      (context.params as Record<string, string>).sourceType === 'storage' &&
      (context.params as Record<string, string>).from
    ) {
      const fromName = (context.params as Record<string, string>).from;
      if (context.additionalStorageData?.[fromName]) {
        storageSystems[fromName] = this.buildStorageConfig(context.additionalStorageData[fromName]);
      }
    }

    return storageSystems;
  }

  private buildStorageConfig(vault: VaultContent): StorageSection {
    const parsedVault = typeof vault === 'string' ? JSON.parse(vault) : vault;
    const vaultRecord = parsedVault as Record<string, unknown>;

    const provider = String(vaultRecord.provider ?? '');
    if (!provider) {
      throw new Error('Storage provider type is required');
    }

    const config: StorageSection = {
      backend: provider,
    };

    if (vaultRecord.bucket) {
      config.bucket = String(vaultRecord.bucket);
    }
    if (vaultRecord.region) {
      config.region = String(vaultRecord.region);
    }
    if (vaultRecord.folder !== undefined && vaultRecord.folder !== null) {
      config.folder = String(vaultRecord.folder);
    }
    if (vaultRecord.parameters) {
      config.parameters = vaultRecord.parameters as Record<string, unknown>;
    }

    return config;
  }

  private buildRepositoryCredentials(
    context: QueueRequestContext,
    requirements: FunctionRequirements
  ): Record<string, string> {
    const credentials: Record<string, string> = {};

    // For functions that need all repository credentials (e.g., repository_list)
    if (context.functionName === 'repository_list' && context.allRepositoryCredentials) {
      Object.assign(credentials, context.allRepositoryCredentials);
    }

    // For functions that need a specific repository credential
    if (requirements.repository && context.repositoryGuid && context.repositoryVault) {
      try {
        const repositoryVault =
          typeof context.repositoryVault === 'string'
            ? JSON.parse(context.repositoryVault)
            : context.repositoryVault;

        if ((repositoryVault as Record<string, unknown>).credential) {
          credentials[context.repositoryGuid] = String(
            (repositoryVault as Record<string, unknown>).credential
          );
        }
      } catch {
        // Ignore vault parsing errors
      }
    }

    return credentials;
  }

  private buildRepositories(
    context: QueueRequestContext,
    requirements: FunctionRequirements
  ): Record<string, RepositoryInfo> {
    const repositories: Record<string, RepositoryInfo> = {};

    // Add current repository if specified
    if (requirements.repository && context.repositoryGuid) {
      const repositoryName =
        context.repositoryName ??
        getParamValue(context.params, 'repository') ??
        context.repositoryGuid;
      const repoInfo: RepositoryInfo = {
        guid: context.repositoryGuid,
        name: repositoryName,
      };
      // Include network_id if available (required for container operations)
      if (context.repositoryNetworkId) {
        repoInfo.network_id = context.repositoryNetworkId;
      }
      repositories[repositoryName] = repoInfo;
    }

    // For list function, include all repositories if available
    if (context.functionName === 'repository_list' && context.allRepositories) {
      Object.entries(context.allRepositories).forEach(([name, guid]) => {
        repositories[name] = { guid: String(guid), name };
      });
    }

    return repositories;
  }

  private buildContextSection(context: QueueRequestContext): ContextSection {
    const section: ContextSection = {};

    if (context.organizationCredential) {
      section.organization_id = context.organizationCredential;
    }

    section.api_url = this.config.getApiUrl();

    // Add universal user info from organization vault
    if (context.organizationVault && typeof context.organizationVault === 'object') {
      const orgVault = context.organizationVault;
      if (orgVault.UNIVERSAL_USER_ID) {
        section.universal_user_id = String(orgVault.UNIVERSAL_USER_ID);
      }
      if (orgVault.UNIVERSAL_USER_NAME) {
        section.universal_user_name = String(orgVault.UNIVERSAL_USER_NAME);
      }
    }

    return section;
  }

  private buildPreferencesSection(context: QueueRequestContext): PreferencesSection | undefined {
    if (!context.language) {
      return undefined;
    }
    return {
      locale: { language: context.language },
    };
  }

  private ensureBase64(value: string): string {
    if (!value) return value;
    return isBase64(value) ? value : this.config.encodeBase64(value);
  }
}

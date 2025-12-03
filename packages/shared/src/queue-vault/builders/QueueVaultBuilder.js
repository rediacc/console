import { minifyJSON } from '../utils/json';
import { isBase64, getParamArray, getParamValue } from '../utils/validation';
import { FUNCTION_REQUIREMENTS } from '../data/functionRequirements';
export class QueueVaultBuilder {
    constructor(config) {
        this.config = config;
    }
    getFunctionRequirements(functionName) {
        const functionKey = functionName;
        return FUNCTION_REQUIREMENTS[functionKey]?.requirements || {};
    }
    async buildQueueVault(context) {
        try {
            const requirements = this.getFunctionRequirements(context.functionName);
            const queueVaultData = {
                function: context.functionName,
                machine: context.machineName || '',
                team: context.teamName,
                params: context.params,
                contextData: {
                    GENERAL_SETTINGS: this.buildGeneralSettings(context),
                },
            };
            if (requirements.machine && context.machineVault && context.machineName) {
                queueVaultData.contextData.MACHINES = queueVaultData.contextData.MACHINES || {};
                queueVaultData.contextData.MACHINES[context.machineName] = this.extractMachineData(context.machineVault);
                const destinationName = context.params.to;
                if (context.functionName === 'deploy' &&
                    destinationName &&
                    destinationName !== context.machineName &&
                    context.destinationMachineVault) {
                    queueVaultData.contextData.MACHINES[destinationName] = this.extractMachineData(context.destinationMachineVault);
                }
            }
            // For ssh_test with bridge-only tasks (no machine name), include SSH details directly in vault data
            if (context.functionName === 'ssh_test' && context.machineVault && !context.machineName) {
                const machineData = this.extractMachineData(context.machineVault);
                const parsedVault = typeof context.machineVault === 'string' ? JSON.parse(context.machineVault) : context.machineVault;
                if (parsedVault.ssh_password) {
                    ;
                    machineData.ssh_password = parsedVault.ssh_password;
                }
                // Include the SSH connection info directly in the root vault data for bridge-only tasks
                Object.assign(queueVaultData, machineData);
            }
            if (context.functionName === 'backup') {
                const targets = getParamArray(context.params, 'storages');
                if (!targets.length) {
                    const fallbackTarget = getParamValue(context.params, 'to');
                    if (fallbackTarget) {
                        targets.push(fallbackTarget);
                    }
                }
                if (targets.length > 0) {
                    queueVaultData.contextData.STORAGE_SYSTEMS = queueVaultData.contextData.STORAGE_SYSTEMS || {};
                    targets.forEach((storageName, index) => {
                        const storageVault = context.additionalStorageData?.[storageName] ||
                            (index === 0 ? context.destinationStorageVault : undefined);
                        if (storageVault) {
                            queueVaultData.contextData.STORAGE_SYSTEMS[storageName] = this.buildStorageConfig(storageVault);
                        }
                    });
                }
            }
            if (context.functionName === 'list') {
                const sourceName = getParamValue(context.params, 'from');
                if (sourceName && context.additionalStorageData?.[sourceName]) {
                    queueVaultData.contextData.STORAGE_SYSTEMS = queueVaultData.contextData.STORAGE_SYSTEMS || {};
                    queueVaultData.contextData.STORAGE_SYSTEMS[sourceName] = this.buildStorageConfig(context.additionalStorageData[sourceName]);
                }
                if (sourceName && context.additionalMachineData?.[sourceName]) {
                    queueVaultData.contextData.MACHINES = queueVaultData.contextData.MACHINES || {};
                    queueVaultData.contextData.MACHINES[sourceName] = this.extractMachineData(context.additionalMachineData[sourceName]);
                }
            }
            // Handle pull function with other machines (via additionalMachineData)
            if (context.functionName === 'pull' &&
                context.params.sourceType === 'machine' &&
                context.params.from) {
                const fromName = context.params.from;
                if (context.additionalMachineData?.[fromName]) {
                    queueVaultData.contextData.MACHINES = queueVaultData.contextData.MACHINES || {};
                    queueVaultData.contextData.MACHINES[fromName] = this.extractMachineData(context.additionalMachineData[fromName]);
                }
            }
            // Handle pull function with storage systems (via additionalStorageData)
            if (context.functionName === 'pull' &&
                context.params.sourceType === 'storage' &&
                context.params.from) {
                const fromName = context.params.from;
                if (context.additionalStorageData?.[fromName]) {
                    queueVaultData.contextData.STORAGE_SYSTEMS = queueVaultData.contextData.STORAGE_SYSTEMS || {};
                    queueVaultData.contextData.STORAGE_SYSTEMS[fromName] = this.buildStorageConfig(context.additionalStorageData[fromName]);
                }
            }
            // Add REPO_CREDENTIALS after MACHINES if repository is required
            if (requirements.repository && context.repositoryGuid && context.repositoryVault) {
                try {
                    const repoVault = typeof context.repositoryVault === 'string'
                        ? JSON.parse(context.repositoryVault)
                        : context.repositoryVault;
                    if (repoVault.credential) {
                        queueVaultData.contextData.REPO_CREDENTIALS = {
                            [context.repositoryGuid]: repoVault.credential,
                        };
                    }
                }
                catch {
                    // Ignore vault parsing errors - repository vault is optional
                }
            }
            // Add REPO_LOOPBACK_IP if repository loopback IP is provided
            if (requirements.repository && context.repositoryLoopbackIp) {
                queueVaultData.contextData.REPO_LOOPBACK_IP = context.repositoryLoopbackIp;
            }
            // Add REPO_NETWORK_MODE if repository network mode is provided
            if (requirements.repository && context.repositoryNetworkMode) {
                queueVaultData.contextData.REPO_NETWORK_MODE = context.repositoryNetworkMode;
            }
            // Add REPO_TAG if repository tag is provided
            if (requirements.repository && context.repositoryTag !== undefined) {
                queueVaultData.contextData.REPO_TAG = context.repositoryTag;
            }
            // For functions like 'list' that need all REPO_CREDENTIALS
            // Repository credentials are passed separately, not from company vault
            if (context.functionName === 'list' && context.allRepositoryCredentials) {
                queueVaultData.contextData.REPO_CREDENTIALS = context.allRepositoryCredentials;
            }
            // For 'mount', 'unmount', 'new', and 'up' functions that need PLUGINS
            if (['mount', 'unmount', 'new', 'up'].includes(context.functionName) &&
                context.companyVault &&
                context.companyVault.PLUGINS) {
                queueVaultData.contextData.PLUGINS = context.companyVault.PLUGINS;
            }
            const dataExtractors = [
                [requirements.company, 'company', () => this.extractCompanyData(context.companyVault)],
                [
                    Boolean(requirements.repository && context.repositoryGuid),
                    'repository',
                    () => this.extractRepositoryData(context.repositoryVault, context.repositoryGuid ?? '', context.companyVault),
                ],
                [
                    requirements.storage && Boolean(context.storageName),
                    'storage',
                    () => this.extractStorageData(context.storageVault, context.storageName),
                ],
                [
                    requirements.bridge && Boolean(context.bridgeName),
                    'bridge',
                    () => this.extractBridgeData(context.bridgeVault, context.bridgeName),
                ],
                [requirements.plugin, 'plugins', () => this.extractPluginData(context.companyVault)],
            ];
            dataExtractors.forEach(([condition, key, extractor]) => {
                if (condition) {
                    queueVaultData.contextData[key] = extractor();
                }
            });
            return minifyJSON(JSON.stringify(queueVaultData));
        }
        catch (error) {
            const message = error instanceof Error ? error.message : 'Unknown error';
            throw new Error(`Failed to build queue vault: ${message}`);
        }
    }
    extractCompanyData(companyVault) {
        if (!companyVault)
            return {};
        if (typeof companyVault === 'string') {
            try {
                return JSON.parse(companyVault);
            }
            catch {
                return {};
            }
        }
        const { UNIVERSAL_USER_ID, UNIVERSAL_USER_NAME, DOCKER_JSON_CONF, LOG_FILE, REPO_CREDENTIALS, PLUGINS } = companyVault;
        return { UNIVERSAL_USER_ID, UNIVERSAL_USER_NAME, DOCKER_JSON_CONF, LOG_FILE, REPO_CREDENTIALS, PLUGINS };
    }
    extractMachineData(machineVault) {
        if (!machineVault)
            return {};
        const vault = typeof machineVault === 'string' ? JSON.parse(machineVault) : machineVault;
        const fieldMappings = [
            { targetKey: 'IP', sources: ['ip', 'IP'] },
            { targetKey: 'USER', sources: ['user', 'USER'] },
            { targetKey: 'DATASTORE', sources: ['datastore', 'DATASTORE'] },
            { targetKey: 'HOST_ENTRY', sources: ['host_entry', 'HOST_ENTRY'] },
        ];
        return fieldMappings.reduce((target, { targetKey, sources }) => {
            const sourceKey = sources.find((source) => vault[source] !== undefined);
            if (sourceKey) {
                target[targetKey] = vault[sourceKey];
            }
            return target;
        }, {});
    }
    extractRepositoryData(repositoryVault, repositoryGuid, _companyVault) {
        const repository = typeof repositoryVault === 'string' ? JSON.parse(repositoryVault) : repositoryVault;
        return {
            guid: repositoryGuid,
            ...(repository && {
                size: repository.size,
                credential: repository.credential,
            }),
        };
    }
    extractStorageData(storageVault, storageName) {
        if (!storageVault)
            return { name: storageName };
        if (typeof storageVault === 'string') {
            return { name: storageName, ...JSON.parse(storageVault) };
        }
        return { name: storageName, ...storageVault };
    }
    extractBridgeData(bridgeVault, bridgeName) {
        if (!bridgeVault)
            return { name: bridgeName };
        if (typeof bridgeVault === 'string') {
            return { name: bridgeName, ...JSON.parse(bridgeVault) };
        }
        return { name: bridgeName, ...bridgeVault };
    }
    extractPluginData(companyVault) {
        const company = typeof companyVault === 'string' ? JSON.parse(companyVault) : companyVault;
        return company?.PLUGINS ? company.PLUGINS : {};
    }
    buildStorageConfig(vault) {
        const parsedVault = typeof vault === 'string' ? JSON.parse(vault) : vault;
        const provider = parsedVault.provider;
        if (!provider) {
            throw new Error('Storage provider type is required');
        }
        const storageConfig = {
            RCLONE_REDIACC_BACKEND: provider,
        };
        const folder = parsedVault.folder;
        if (folder !== undefined && folder !== null) {
            storageConfig.RCLONE_REDIACC_FOLDER = folder;
        }
        const parameters = parsedVault.parameters;
        if (parameters) {
            storageConfig.RCLONE_PARAMETERS = parameters;
        }
        const providerPrefix = `RCLONE_${provider.toUpperCase()}`;
        Object.entries(parsedVault).forEach(([key, value]) => {
            if (['provider', 'folder', 'parameters'].includes(key)) {
                return;
            }
            const envKey = `${providerPrefix}_${key.toUpperCase()}`;
            storageConfig[envKey] = value;
        });
        return storageConfig;
    }
    buildGeneralSettings(context) {
        const generalSettings = {};
        if (context.companyCredential) {
            generalSettings.COMPANY_ID = context.companyCredential;
        }
        generalSettings.SYSTEM_API_URL = this.config.getApiUrl();
        generalSettings.TEAM_NAME = context.teamName;
        if (context.machineName) {
            generalSettings.MACHINE_NAME = context.machineName;
        }
        if (context.companyVault && typeof context.companyVault === 'object') {
            this.addCompanyVaultToGeneralSettings(generalSettings, context.companyVault);
        }
        if (context.teamVault && typeof context.teamVault === 'object') {
            this.addTeamVaultToGeneralSettings(generalSettings, context.teamVault);
        }
        return generalSettings;
    }
    addCompanyVaultToGeneralSettings(generalSettings, companyVault) {
        const { UNIVERSAL_USER_ID, UNIVERSAL_USER_NAME, DOCKER_JSON_CONF, PLUGINS } = companyVault;
        if (UNIVERSAL_USER_ID)
            generalSettings.UNIVERSAL_USER_ID = UNIVERSAL_USER_ID;
        if (UNIVERSAL_USER_NAME)
            generalSettings.UNIVERSAL_USER_NAME = UNIVERSAL_USER_NAME;
        if (DOCKER_JSON_CONF)
            generalSettings.DOCKER_JSON_CONF = DOCKER_JSON_CONF;
        if (PLUGINS)
            generalSettings.PLUGINS = PLUGINS;
    }
    addTeamVaultToGeneralSettings(generalSettings, teamVault) {
        const sshKeyFields = ['SSH_PRIVATE_KEY', 'SSH_PUBLIC_KEY'];
        sshKeyFields.forEach((field) => {
            const value = teamVault[field];
            if (value && typeof value === 'string') {
                generalSettings[field] = this.ensureBase64(value);
            }
        });
    }
    ensureBase64(value) {
        if (!value)
            return value;
        return isBase64(value) ? value : this.config.encodeBase64(value);
    }
}
//# sourceMappingURL=QueueVaultBuilder.js.map
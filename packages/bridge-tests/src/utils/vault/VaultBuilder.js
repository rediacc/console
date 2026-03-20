// Import queue-vault types from shared package
import * as fs from 'node:fs/promises';
import * as path from 'node:path';
/**
 * Builder for constructing vault JSON for E2E testing.
 * Simulates middleware vault construction without requiring middleware.
 *
 * @example
 * ```ts
 * const vault = new VaultBuilder()
 *   .withFunction('backup_push')
 *   .withTeam('Private Team')
 *   .withRepository('repo-guid', 'repo-name')
 *   .withMachine('192.168.111.11', 'muhammed', '/mnt/rediacc')
 *   .withPushParams({ destinationType: 'storage', dest: 'backup.tar' })
 *   .build();
 * ```
 */
export class VaultBuilder {
    constructor() {
        this.vault = {
            $schema: 'queue-vault-v2',
            version: '2.0',
            task: {
                function: '',
                machine: '',
                team: '',
            },
            ssh: {
                private_key: '',
                public_key: '',
            },
            machine: {
                ip: '',
                user: '',
            },
        };
    }
    /**
     * Set the function name.
     */
    withFunction(name) {
        this.vault.task.function = name;
        return this;
    }
    /**
     * Set the team name.
     */
    withTeam(name) {
        this.vault.task.team = name;
        return this;
    }
    /**
     * Set the repository information.
     */
    withRepository(guid, name, networkId) {
        var _a, _b;
        this.vault.task.repository = name;
        (_a = this.vault).repositories ?? (_a.repositories = {});
        this.vault.repositories[name] = {
            guid,
            name,
            network_id: networkId,
        };
        // Also add to params
        (_b = this.vault).params ?? (_b.params = {});
        this.vault.params.repository = guid;
        this.vault.params.repositoryName = name;
        return this;
    }
    /**
     * Set the primary machine configuration.
     */
    withMachine(ip, user, datastore, port) {
        this.vault.task.machine = ip;
        this.vault.machine = {
            ip,
            user,
            port: port ?? 22,
            datastore,
        };
        return this;
    }
    /**
     * Set the destination machine for push operations.
     */
    withDestinationMachine(ip, user, datastore) {
        var _a, _b;
        (_a = this.vault).extra_machines ?? (_a.extra_machines = {});
        this.vault.extra_machines.destination = {
            ip,
            user,
            port: 22,
            datastore,
        };
        // Also set dest_machine param for backup_push
        (_b = this.vault).params ?? (_b.params = {});
        this.vault.params.dest_machine = ip;
        return this;
    }
    /**
     * Set the source machine for pull operations.
     */
    withSourceMachine(ip, user) {
        var _a, _b;
        (_a = this.vault).extra_machines ?? (_a.extra_machines = {});
        this.vault.extra_machines.source = {
            ip,
            user,
            port: 22,
        };
        // Also set source_machine param for backup_pull
        (_b = this.vault).params ?? (_b.params = {});
        this.vault.params.source_machine = ip;
        return this;
    }
    /**
     * Set SSH credentials.
     */
    withSSHKey(privateKey, publicKey) {
        this.vault.ssh.private_key = Buffer.from(privateKey).toString('base64');
        this.vault.ssh.public_key = publicKey ? Buffer.from(publicKey).toString('base64') : '';
        return this;
    }
    /**
     * Set SSH password.
     */
    withSSHPassword(password) {
        this.vault.ssh.password = password;
        return this;
    }
    /**
     * Add a storage system configuration.
     */
    withStorage(config) {
        var _a;
        (_a = this.vault).storage_systems ?? (_a.storage_systems = {});
        this.vault.storage_systems[config.name] = {
            backend: config.type,
            bucket: config.bucket,
            region: config.region,
            folder: config.folder,
            parameters: {
                endpoint: config.endpoint,
                access_key_id: config.accessKey,
                secret_access_key: config.secretKey,
            },
        };
        return this;
    }
    /**
     * Add multiple storage system configurations.
     */
    withStorages(configs) {
        for (const config of configs) {
            this.withStorage(config);
        }
        return this;
    }
    /**
     * Set backup_push specific parameters.
     */
    withPushParams(params) {
        var _a;
        (_a = this.vault).params ?? (_a.params = {});
        this.setPushStringParams(params);
        this.setPushBooleanParams(params);
        this.setPushArrayParams(params);
        return this;
    }
    setPushStringParams(params) {
        if (params.destinationType) {
            this.vault.params.destinationType = params.destinationType;
        }
        if (params.to) {
            this.vault.params.to = params.to;
        }
        if (params.dest) {
            this.vault.params.dest = params.dest;
        }
        if (params.tag) {
            this.vault.params.tag = params.tag;
        }
        if (params.state) {
            this.vault.params.state = params.state;
        }
        if (params.grand) {
            this.vault.params.grand = params.grand;
        }
    }
    setPushBooleanParams(params) {
        if (params.checkpoint !== undefined) {
            this.vault.params.checkpoint = params.checkpoint;
        }
        if (params.override !== undefined) {
            this.vault.params.override = params.override;
        }
    }
    setPushArrayParams(params) {
        if (params.machines && params.machines.length > 0) {
            this.vault.params.machines = params.machines.join(',');
        }
        if (params.storages && params.storages.length > 0) {
            this.vault.params.storages = params.storages.join(',');
        }
    }
    /**
     * Set backup_pull specific parameters.
     */
    withPullParams(params) {
        var _a;
        (_a = this.vault).params ?? (_a.params = {});
        if (params.sourceType) {
            this.vault.params.sourceType = params.sourceType;
        }
        if (params.from) {
            this.vault.params.from = params.from;
        }
        if (params.grand) {
            this.vault.params.grand = params.grand;
        }
        return this;
    }
    /**
     * Set custom parameters.
     */
    withParams(params) {
        var _a;
        (_a = this.vault).params ?? (_a.params = {});
        Object.assign(this.vault.params, params);
        return this;
    }
    /**
     * Set the datastore path.
     */
    withDatastore(path) {
        var _a;
        this.vault.machine.datastore = path;
        (_a = this.vault).params ?? (_a.params = {});
        this.vault.params.datastore_path = path;
        return this;
    }
    /**
     * Build and return the vault object.
     */
    build() {
        return { ...this.vault };
    }
    /**
     * Build and return the vault as JSON string.
     */
    toJSON() {
        return JSON.stringify(this.vault, null, 2);
    }
    /**
     * Build and write the vault to a file.
     * Returns the path to the created file.
     */
    async toFile(filePath) {
        const targetPath = filePath ?? `/tmp/vault-${Date.now()}.json`;
        await fs.mkdir(path.dirname(targetPath), { recursive: true });
        await fs.writeFile(targetPath, this.toJSON(), 'utf-8');
        return targetPath;
    }
    /**
     * Create a VaultBuilder pre-configured for backup_push.
     */
    static forPush() {
        return new VaultBuilder().withFunction('backup_push');
    }
    /**
     * Create a VaultBuilder pre-configured for backup_pull.
     */
    static forPull() {
        return new VaultBuilder().withFunction('backup_pull');
    }
    /**
     * Create a VaultBuilder pre-configured for checkpoint_create.
     */
    static forCheckpointCreate() {
        return new VaultBuilder().withFunction('checkpoint_create');
    }
    /**
     * Create a VaultBuilder pre-configured for checkpoint_restore.
     */
    static forCheckpointRestore() {
        return new VaultBuilder().withFunction('checkpoint_restore');
    }
}
//# sourceMappingURL=VaultBuilder.js.map
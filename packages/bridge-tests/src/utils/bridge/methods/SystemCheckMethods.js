/**
 * System check and verification methods for BridgeTestRunner.
 * Contains methods for testing machine health, compatibility, and setup status.
 */
export class SystemCheckMethods {
    constructor(testFunction) {
        this.testFunction = testFunction;
    }
    async ping() {
        return this.testFunction({ function: 'machine_ping' });
    }
    async nop() {
        return this.testFunction({ function: 'daemon_nop' });
    }
    async hello() {
        return this.testFunction({ function: 'machine_version' });
    }
    async sshTest() {
        return this.testFunction({ function: 'machine_ssh_test' });
    }
    async checkKernelCompatibility() {
        return this.testFunction({ function: 'machine_check_kernel' });
    }
    async checkSetup() {
        return this.testFunction({ function: 'machine_check_setup' });
    }
    async checkMemory() {
        return this.testFunction({ function: 'machine_check_memory' });
    }
    async checkSudo() {
        return this.testFunction({ function: 'machine_check_sudo' });
    }
    async checkTools() {
        return this.testFunction({ function: 'machine_check_tools' });
    }
    async checkRenet() {
        return this.testFunction({ function: 'machine_check_renet' });
    }
    async checkCriu() {
        return this.testFunction({ function: 'machine_check_criu' });
    }
    async checkBtrfs() {
        return this.testFunction({ function: 'machine_check_btrfs' });
    }
    async checkDrivers() {
        return this.testFunction({ function: 'machine_check_drivers' });
    }
    async checkSystem() {
        return this.testFunction({ function: 'machine_check_system' });
    }
    async checkUsers() {
        return this.testFunction({ function: 'machine_check_users' });
    }
    async checkRediaccCli() {
        return this.testFunction({ function: 'machine_check_cli' });
    }
    async checkDatastore(datastorePath) {
        return this.testFunction({
            function: 'datastore_status',
            datastorePath,
        });
    }
}
//# sourceMappingURL=SystemCheckMethods.js.map
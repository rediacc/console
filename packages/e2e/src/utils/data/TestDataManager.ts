import fs from 'node:fs';
import path from 'node:path';
import { loadGlobalState } from '../../setup/global-state';
import { E2E_DEFAULTS } from '../constants';
import { getVMEnvVar, VM_DEFAULTS } from '../env';

// UUID v4 function
function v4(): string {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replaceAll(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

export interface TestUser {
  email: string;
  password: string;
  firstName?: string;
  lastName?: string;
  role?: string;
  team?: string;
}

export interface TestMachine {
  name: string;
  ip: string;
  user: string;
  password: string;
  team: string;
  datastore?: string;
}

export interface TestRepository {
  name: string;
  machine: string;
  team: string;
  version?: string;
}

export interface CreatedUser {
  email: string;
  password: string;
  createdAt: string;
  activated?: boolean;
}

export interface TestData {
  users: TestUser[];
  machines: TestMachine[];
  repositories: TestRepository[];
  teams: string[];
  createdUsers: CreatedUser[];
}

export class TestDataManager {
  private readonly dataDir: string;
  private readonly testDataFile: string;
  private _initialized = false;

  constructor(dataDir = 'utils/data') {
    this.dataDir = dataDir;
    this.testDataFile = path.join(this.dataDir, 'test-data.json');
    // Lazy initialization - don't call ensureDataDirectory() here
  }

  private ensureInitialized(): void {
    if (this._initialized) return;

    if (!fs.existsSync(this.dataDir)) {
      fs.mkdirSync(this.dataDir, { recursive: true });
    }

    if (!fs.existsSync(this.testDataFile)) {
      this.initializeTestData();
    }

    this._initialized = true;
  }

  private initializeTestData(): void {
    const globalState = loadGlobalState();

    const defaultData: TestData = {
      users: [
        {
          email: globalState.email,
          password: globalState.password,
          firstName: 'Admin',
          lastName: 'User',
          role: 'admin',
          team: E2E_DEFAULTS.TEAM_NAME,
        },
        {
          email: globalState.email,
          password: globalState.password,
          firstName: 'Standard',
          lastName: 'User',
          role: 'user',
          team: E2E_DEFAULTS.TEAM_NAME,
        },
        {
          email: globalState.email,
          password: globalState.password,
          firstName: 'TempUser',
          lastName: 'User999',
          role: 'tempuser',
          team: E2E_DEFAULTS.TEAM_NAME,
        },
      ],
      machines: [],
      repositories: [
        {
          name: E2E_DEFAULTS.REPO_NAME,
          machine: E2E_DEFAULTS.MACHINE_NAME,
          team: E2E_DEFAULTS.TEAM_NAME,
          version: '1.0.0',
        },
      ],
      teams: [E2E_DEFAULTS.TEAM_NAME],
      createdUsers: [],
    };

    this.saveTestData(defaultData);
  }

  private loadTestData(): TestData {
    this.ensureInitialized();

    let data: TestData;
    try {
      const fileCurrent = fs.readFileSync(this.testDataFile, 'utf8');
      data = JSON.parse(fileCurrent);
    } catch {
      console.warn('Failed to load test data, using defaults');
      this.initializeTestData();
      // Re-read the newly initialized file
      const fileNew = fs.readFileSync(this.testDataFile, 'utf8');
      data = JSON.parse(fileNew);
    }

    return this.applyEnvOverrides(data);
  }

  private applyEnvOverrides(data: TestData): TestData {
    // Override Machines only if VM env vars are available
    const vmIps = getVMEnvVar('VM_WORKER_IPS');
    const vmUser = getVMEnvVar('VM_MACHINE_USER');
    if (vmIps && vmUser) {
      const ips = vmIps
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean);
      data.machines.forEach((m, i) => {
        if (ips[i]) m.ip = ips[i];
        m.user = vmUser;
      });
    }
    return data;
  }

  private saveTestData(data: TestData): void {
    fs.writeFileSync(this.testDataFile, JSON.stringify(data, null, 2));
  }

  /**
   * Lazily populate machines array when first accessed
   * Uses getVMEnvVar which falls back to static defaults in CI
   */
  private ensureMachinesPopulated(data: TestData): void {
    if (data.machines.length > 0) return;

    const vmIps = getVMEnvVar('VM_WORKER_IPS');
    if (!vmIps) {
      throw new Error(
        'VM tests require VM_WORKER_IPS environment variable or VM_DEPLOYMENT=true. ' +
          'Set VM_WORKER_IPS or run with CI=true to use default IPs.'
      );
    }

    const ips = vmIps
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean);
    const vmUser = getVMEnvVar('VM_MACHINE_USER') ?? VM_DEFAULTS.MACHINE_USER;
    const vmPassword = getVMEnvVar('VM_MACHINE_PASSWORD') ?? '';
    const teamName = process.env.TEAM_NAME ?? E2E_DEFAULTS.TEAM_NAME;

    console.warn(`Populating machines with VM IPs: ${ips.join(', ')}`);

    data.machines = ips.map((ip, index) => ({
      name: `machine-${index + 1}`,
      ip,
      user: vmUser,
      password: vmPassword,
      team: teamName,
      datastore: '/mnt/datastore',
    }));

    this.saveTestData(data);
  }

  getUser(role = 'user'): TestUser {
    const data = this.loadTestData();
    const user = data.users.find((u) => u.role === role);

    if (!user) {
      throw new Error(`No user found with role: ${role}`);
    }

    return user;
  }

  getRandomUser(): TestUser {
    const data = this.loadTestData();
    const randomIndex = Math.floor(Math.random() * data.users.length);
    return data.users[randomIndex];
  }

  createTemporaryUser(role = 'user', team?: string): TestUser {
    const timestamp = Date.now();
    const useTeam = team ?? process.env.TEAM_NAME ?? E2E_DEFAULTS.TEAM_NAME;
    return {
      email: `temp_user_${timestamp}@example.com`,
      password: 'temppassword123',
      firstName: 'Temp',
      lastName: `User${timestamp}`,
      role,
      team: useTeam,
    };
  }

  getMachine(name?: string): TestMachine {
    const data = this.loadTestData();

    // Lazily populate machines if empty
    this.ensureMachinesPopulated(data);

    if (name) {
      const machine = data.machines.find((m) => m.name === name);
      if (!machine) {
        throw new Error(`No machine found with name: ${name}`);
      }
      return machine;
    }

    return data.machines[0];
  }

  createTemporaryMachine(team?: string): TestMachine {
    const timestamp = Date.now();
    const data = this.loadTestData();
    const useTeam = team ?? process.env.TEAM_NAME ?? E2E_DEFAULTS.TEAM_NAME;

    // Use first machine's IP or get from VM env vars
    let machineIp: string;
    let machineUser: string;
    let machinePassword: string;

    if (data.machines.length > 0) {
      machineIp = data.machines[0].ip;
      machineUser = data.machines[0].user;
      machinePassword = data.machines[0].password;
    } else {
      const vmIps = getVMEnvVar('VM_WORKER_IPS');
      if (!vmIps) {
        throw new Error('VM_WORKER_IPS required for createTemporaryMachine');
      }
      machineIp = vmIps.split(',')[0].trim();
      machineUser = getVMEnvVar('VM_MACHINE_USER') ?? VM_DEFAULTS.MACHINE_USER;
      machinePassword = getVMEnvVar('VM_MACHINE_PASSWORD') ?? '';
    }

    return {
      name: `temp-machine-${timestamp}`,
      ip: machineIp,
      user: machineUser,
      password: machinePassword,
      team: useTeam,
      datastore: '/mnt/rediacc',
    };
  }

  getRepository(name?: string): TestRepository {
    const data = this.loadTestData();

    if (name) {
      const repo = data.repositories.find((r) => r.name === name);
      if (!repo) {
        throw new Error(`No repository found with name: ${name}`);
      }
      return repo;
    }

    return data.repositories[0];
  }

  createTemporaryRepository(machine?: string, team?: string): TestRepository {
    const timestamp = Date.now();
    const data = this.loadTestData();
    const defaultMachine = data.machines[0]?.name ?? E2E_DEFAULTS.MACHINE_NAME;
    const targetMachine = machine ?? defaultMachine;
    const useTeam = team ?? process.env.TEAM_NAME ?? E2E_DEFAULTS.TEAM_NAME;

    return {
      name: `temp-repo-${timestamp}`,
      machine: targetMachine,
      team: useTeam,
      version: '1.0.0',
    };
  }

  getTeam(index = 0): string {
    const data = this.loadTestData();
    return data.teams[index];
  }

  getRandomTeam(): string {
    const data = this.loadTestData();
    const randomIndex = Math.floor(Math.random() * data.teams.length);
    return data.teams[randomIndex];
  }

  generateUniqueId(): string {
    return v4();
  }

  generateTestEmail(prefix = 'test'): string {
    const timestamp = Date.now();
    return `${prefix}_${timestamp}@example.com`;
  }

  generateRandomString(length = 10): string {
    const characters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
    let result = '';

    for (let i = 0; i < length; i++) {
      result += characters.charAt(Math.floor(Math.random() * characters.length));
    }

    return result;
  }

  loadTestDataFromFile(filePath: string): unknown {
    try {
      const fullPath = path.resolve(filePath);
      const data = fs.readFileSync(fullPath, 'utf8');
      return JSON.parse(data) as unknown;
    } catch (loadError) {
      throw new Error(`Failed to load test data from ${filePath}: ${loadError}`);
    }
  }

  saveTestResults(testName: string, results: unknown): void {
    const resultsDir = path.join(this.dataDir, 'results');

    if (!fs.existsSync(resultsDir)) {
      fs.mkdirSync(resultsDir, { recursive: true });
    }

    const timestamp = new Date().toISOString().replaceAll(/[:.]/g, '-');
    const fileName = `${testName}_${timestamp}.json`;
    const filePath = path.join(resultsDir, fileName);

    fs.writeFileSync(filePath, JSON.stringify(results, null, 2));
    console.warn(`Test results saved: ${filePath}`);
  }

  addUser(user: TestUser): void {
    const data = this.loadTestData();
    data.users.push(user);
    this.saveTestData(data);
  }

  addMachine(machine: TestMachine): void {
    const data = this.loadTestData();
    data.machines.push(machine);
    this.saveTestData(data);
  }

  addRepository(repository: TestRepository): void {
    const data = this.loadTestData();
    data.repositories.push(repository);
    this.saveTestData(data);
  }

  addCreatedUser(email: string, password: string, activated = false): void {
    const data = this.loadTestData();

    // Check if user already exists
    const existingUser = data.createdUsers.find((u) => u.email === email);
    if (existingUser) {
      // Update existing user
      existingUser.password = password;
      existingUser.activated = activated;
      existingUser.createdAt = new Date().toISOString();
    } else {
      // Add new user
      data.createdUsers.push({
        email,
        password,
        activated,
        createdAt: new Date().toISOString(),
      });
    }

    this.saveTestData(data);
    console.warn(`Created user saved: ${email}`);
  }

  getCreatedUser(email?: string): CreatedUser {
    const data = this.loadTestData();

    if (email) {
      const user = data.createdUsers.find((u) => u.email === email);
      if (!user) {
        throw new Error(`No created user found with email: ${email}`);
      }
      return user;
    }

    // Return the most recently created user
    if (data.createdUsers.length === 0) {
      throw new Error('No created users found');
    }

    return data.createdUsers[data.createdUsers.length - 1];
  }

  getAllCreatedUsers(): CreatedUser[] {
    const data = this.loadTestData();
    return data.createdUsers;
  }

  updateCreatedUserActivation(email: string, activated: boolean): void {
    const data = this.loadTestData();
    const user = data.createdUsers.find((u) => u.email === email);

    if (!user) {
      throw new Error(`No created user found with email: ${email}`);
    }

    user.activated = activated;
    this.saveTestData(data);
    console.warn(`User activation updated: ${email} -> ${activated}`);
  }

  removeCreatedUser(email: string): void {
    const data = this.loadTestData();
    data.createdUsers = data.createdUsers.filter((u) => u.email !== email);
    this.saveTestData(data);
    console.warn(`Removed created user: ${email}`);
  }

  cleanup(): void {
    console.warn('Cleaning up test data...');

    const data = this.loadTestData();

    data.users = data.users.filter((user) => !user.email.includes('temp_user_'));
    data.machines = data.machines.filter((machine) => !machine.name.includes('temp-machine-'));
    data.repositories = data.repositories.filter((repo) => !repo.name.includes('temp-repo-'));
    data.createdUsers = [];

    this.saveTestData(data);
  }

  getAllTestData(): TestData {
    return this.loadTestData();
  }
}

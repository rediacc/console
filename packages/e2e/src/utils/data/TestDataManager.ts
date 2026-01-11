import fs from 'fs';
import path from 'path';
import { requireEnvVar } from '../env';

// UUID v4 function
function v4(): string {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
    const r = Math.random() * 16 | 0;
    const v = c === 'x' ? r : (r & 0x3 | 0x8);
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
  private dataDir: string;
  private testDataFile: string;

  constructor(dataDir: string = 'utils/data') {
    this.dataDir = dataDir;
    this.testDataFile = path.join(this.dataDir, 'test-data.json');
    this.ensureDataDirectory();
  }

  private ensureDataDirectory(): void {
    if (!fs.existsSync(this.dataDir)) {
      fs.mkdirSync(this.dataDir, { recursive: true });
    }

    if (!fs.existsSync(this.testDataFile)) {
      this.initializeTestData();
    }
  }

  private initializeTestData(): void {
    const machineIps = requireEnvVar('VM_WORKER_IPS').split(',').map(ip => ip.trim()).filter(ip => ip);
    console.log(`Using VM_WORKER_IPS from environment: ${machineIps.join(', ')}`);

    const defaultData: TestData = {
      users: [
        {
          email: requireEnvVar('ADMIN_USER_EMAIL'),
          password: requireEnvVar('ADMIN_USER_PASSWORD'),
          firstName: 'Admin',
          lastName: 'User',
          role: 'admin',
          team: requireEnvVar('TEAM_NAME')
        },
        {
          email: requireEnvVar('TEST_USER_EMAIL'),
          password: requireEnvVar('TEST_USER_PASSWORD'),
          firstName: 'Standard',
          lastName: 'User',
          role: 'user',
          team: requireEnvVar('TEAM_NAME')
        },
        {
          email: requireEnvVar('TEMP_USER_EMAIL'),
          password: requireEnvVar('TEMP_USER_PASSWORD'),
          firstName: 'TempUser',
          lastName: 'User999',
          role: 'tempuser',
          team: requireEnvVar('TEAM_NAME')
        }
      ],
      machines: machineIps.map((ip, index) => ({
        name: `machine-${index + 1}`,
        ip: ip,
        password: requireEnvVar('VM_MACHINE_PASSWORD'),
        user: requireEnvVar('VM_MACHINE_USER'),
        team: requireEnvVar('TEAM_NAME'),
        datastore: '/mnt/datastore'
      })),
      repositories: [
        {
          name: requireEnvVar('REPO_NAME'),
          machine: 'machine-1',
          team: requireEnvVar('TEAM_NAME'),
          version: '1.0.0'
        }
      ],
      teams: [requireEnvVar('TEAM_NAME')],
      createdUsers: []
    };

    this.saveTestData(defaultData);
  }

  private loadTestData(): TestData {
    let data: TestData;
    try {
      const fileCurrent = fs.readFileSync(this.testDataFile, 'utf8');
      data = JSON.parse(fileCurrent);
    } catch (error) {
      console.warn('Failed to load test data, using defaults');
      this.initializeTestData();
      // Re-read the newly initialized file
      const fileNew = fs.readFileSync(this.testDataFile, 'utf8');
      data = JSON.parse(fileNew);
    }

    return this.applyEnvOverrides(data);
  }

  private applyEnvOverrides(data: TestData): TestData {
    const adminEmail = requireEnvVar('ADMIN_USER_EMAIL');
    const adminPass = requireEnvVar('ADMIN_USER_PASSWORD');
    const userEmail = requireEnvVar('TEST_USER_EMAIL');
    const userPass = requireEnvVar('TEST_USER_PASSWORD');
    const teamName = requireEnvVar('TEAM_NAME');
    const vmUser = requireEnvVar('VM_MACHINE_USER');
    const vmIps = requireEnvVar('VM_WORKER_IPS').split(',').map(s => s.trim()).filter(Boolean);

    // Override Admin
    const admin = data.users.find(u => u.role === 'admin');
    if (admin) {
      admin.email = adminEmail;
      admin.password = adminPass;
      admin.team = teamName;
    }

    // Override Standard User
    const user = data.users.find(u => u.role === 'user');
    if (user) {
      user.email = userEmail;
      user.password = userPass;
      user.team = teamName;
    }

    // Ensure Team exists
    if (!data.teams.includes(teamName)) {
      data.teams.push(teamName);
    }

    // Override Machines
    data.machines.forEach((m, i) => {
      if (vmIps[i]) m.ip = vmIps[i];
      m.user = vmUser;
      m.team = teamName;
    });

    // Override Repo
    const repoName = requireEnvVar('REPO_NAME');
    data.repositories.forEach(r => {
      // Assuming we want to override all or just find specific?
      // Since we initialized with REPO_NAME, let's just make sure it matches?
      // But if we have multiple repos, this might be aggressive.
      // For now, let's update the default one or all?
      // The prompt implies "test data from .env".
      // Let's assume the main test repo is the one.
      if (r.name !== repoName && r.version === '1.0.0') {
        // Maybe don't blindly rename all repos.
        // But if we generated it, it should match.
      }
      r.team = teamName;
    });

    // More strictly, if we have a specific repo name env var, we might want to ensure it's in the list
    // but the array structure is complex. Let's stick to the requested pattern:
    // Update the 'test-repo' if it exists or was renamed.
    // Actually, simply relying on `initializeTestData` structure might be safer for complex arrays
    // unless we identify them by ID.
    // However, for the single-item arrays we setup, let's just update the first one if present.
    if (data.repositories.length > 0) {
      data.repositories[0].name = repoName;
      data.repositories[0].team = teamName;
    }

    return data;
  }

  private saveTestData(data: TestData): void {
    fs.writeFileSync(this.testDataFile, JSON.stringify(data, null, 2));
  }

  getUser(role: string = 'user'): TestUser {
    const data = this.loadTestData();
    const user = data.users.find(u => u.role === role);

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

  createTemporaryUser(role: string = 'user', team?: string): TestUser {
    const timestamp = Date.now();
    const useTeam = team || requireEnvVar('TEAM_NAME');
    return {
      email: `temp_user_${timestamp}@example.com`,
      password: 'temppassword123',
      firstName: 'Temp',
      lastName: `User${timestamp}`,
      role,
      team: useTeam
    };
  }

  getMachine(name?: string): TestMachine {
    const data = this.loadTestData();

    if (name) {
      const machine = data.machines.find(m => m.name === name);
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
    const useTeam = team || requireEnvVar('TEAM_NAME');

    // Use first machine's IP or strictly require env var
    const machineIp = data.machines[0]?.ip || requireEnvVar('VM_WORKER_IPS').split(',')[0].trim();
    const machineUser = data.machines[0]?.user || requireEnvVar('VM_MACHINE_USER');
    const machinePassword = requireEnvVar('VM_MACHINE_PASSWORD');

    return {
      name: `temp-machine-${timestamp}`,
      ip: machineIp,
      user: machineUser,
      password: machinePassword,
      team: useTeam,
      datastore: '/mnt/rediacc'
    };
  }

  getRepository(name?: string): TestRepository {
    const data = this.loadTestData();

    if (name) {
      const repo = data.repositories.find(r => r.name === name);
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
    const targetMachine = machine || data.machines[0]?.name || 'machine-1';
    const useTeam = team || requireEnvVar('TEAM_NAME');

    return {
      name: `temp-repo-${timestamp}`,
      machine: targetMachine,
      team: useTeam,
      version: '1.0.0'
    };
  }

  getTeam(index: number = 0): string {
    const data = this.loadTestData();
    return data.teams[index] || requireEnvVar('TEAM_NAME');
  }

  getRandomTeam(): string {
    const data = this.loadTestData();
    const randomIndex = Math.floor(Math.random() * data.teams.length);
    return data.teams[randomIndex];
  }

  generateUniqueId(): string {
    return v4();
  }

  generateTestEmail(prefix: string = 'test'): string {
    const timestamp = Date.now();
    return `${prefix}_${timestamp}@example.com`;
  }

  generateRandomString(length: number = 10): string {
    const characters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
    let result = '';

    for (let i = 0; i < length; i++) {
      result += characters.charAt(Math.floor(Math.random() * characters.length));
    }

    return result;
  }

  loadTestDataFromFile(filePath: string): any {
    try {
      const fullPath = path.resolve(filePath);
      const data = fs.readFileSync(fullPath, 'utf8');
      return JSON.parse(data);
    } catch (error) {
      throw new Error(`Failed to load test data from ${filePath}: ${error}`);
    }
  }

  saveTestResults(testName: string, results: any): void {
    const resultsDir = path.join(this.dataDir, 'results');

    if (!fs.existsSync(resultsDir)) {
      fs.mkdirSync(resultsDir, { recursive: true });
    }

    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
    const fileName = `${testName}_${timestamp}.json`;
    const filePath = path.join(resultsDir, fileName);

    fs.writeFileSync(filePath, JSON.stringify(results, null, 2));
    console.log(`💾 Test results saved: ${filePath}`);
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

  addCreatedUser(email: string, password: string, activated: boolean = false): void {
    const data = this.loadTestData();

    // Check if user already exists
    const existingUser = data.createdUsers.find(u => u.email === email);
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
        createdAt: new Date().toISOString()
      });
    }

    this.saveTestData(data);
    console.log(`✅ Created user saved: ${email}`);
  }

  getCreatedUser(email?: string): CreatedUser {
    const data = this.loadTestData();

    if (email) {
      const user = data.createdUsers.find(u => u.email === email);
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
    const user = data.createdUsers.find(u => u.email === email);

    if (!user) {
      throw new Error(`No created user found with email: ${email}`);
    }

    user.activated = activated;
    this.saveTestData(data);
    console.log(`✅ User activation updated: ${email} -> ${activated}`);
  }

  removeCreatedUser(email: string): void {
    const data = this.loadTestData();
    data.createdUsers = data.createdUsers.filter(u => u.email !== email);
    this.saveTestData(data);
    console.log(`🗑️ Removed created user: ${email}`);
  }

  cleanup(): void {
    console.log('🧹 Cleaning up test data...');

    const data = this.loadTestData();

    data.users = data.users.filter(user => !user.email.includes('temp_user_'));
    data.machines = data.machines.filter(machine => !machine.name.includes('temp-machine-'));
    data.repositories = data.repositories.filter(repo => !repo.name.includes('temp-repo-'));
    data.createdUsers = [];

    this.saveTestData(data);
  }

  getAllTestData(): TestData {
    return this.loadTestData();
  }
}

export interface TestConfig {
  baseURL: string;
  timeout: number;
  retries: number;
  workers: number;
}

export interface TestUser {
  email: string;
  password: string;
  role: 'user' | 'admin' | 'manager';
  team?: string;
  firstName?: string;
  lastName?: string;
}

export interface TestMachine {
  name: string;
  ip: string;
  user: string;
  team: string;
  datastore?: string;
  status?: 'online' | 'offline' | 'maintenance';
}

export interface TestRepository {
  name: string;
  machine: string;
  team: string;
  version?: string;
  status?: 'active' | 'inactive' | 'archived';
}

export interface TestResult {
  testName: string;
  status: 'passed' | 'failed' | 'skipped';
  duration: number;
  error?: string;
  screenshots: string[];
  startTime: Date;
  endTime: Date;
}

export interface ScreenshotConfig {
  fullPage: boolean;
  quality: number;
  type: 'png' | 'jpeg';
  path: string;
}

export interface ReportConfig {
  outputDir: string;
  generateHTML: boolean;
  generateJSON: boolean;
  includeScreenshots: boolean;
}

export interface UIElement {
  selector: string;
  name: string;
  type: 'input' | 'button' | 'dropdown' | 'checkbox' | 'radio' | 'text';
  required?: boolean;
}

export interface PageConfig {
  url: string;
  elements: Record<string, UIElement>;
  loadTimeout: number;
}

export interface TestStep {
  name: string;
  action: () => Promise<void>;
  screenshot?: boolean;
  validation?: () => Promise<boolean>;
}
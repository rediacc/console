import { nodeStorageAdapter } from '../adapters/storage.js';
import type { CliContext, CommandOptions } from '../types/index.js';

const STORAGE_KEY = 'context';

class ContextService {
  private cache: CliContext | null = null;

  async get(): Promise<CliContext> {
    if (this.cache) return this.cache;

    const stored = await nodeStorageAdapter.getItem(STORAGE_KEY);
    if (stored) {
      try {
        this.cache = JSON.parse(stored);
        return this.cache!;
      } catch {
        // Invalid JSON, return empty context
      }
    }
    return {};
  }

  async set(key: keyof CliContext, value: string): Promise<void> {
    const context = await this.get();
    context[key] = value;
    await this.save(context);
  }

  async remove(key: keyof CliContext): Promise<void> {
    const context = await this.get();
    delete context[key];
    await this.save(context);
  }

  async clear(): Promise<void> {
    await this.save({});
  }

  async getTeam(): Promise<string | undefined> {
    // Priority: env var > stored context
    if (process.env.REDIACC_TEAM) {
      return process.env.REDIACC_TEAM;
    }
    const context = await this.get();
    return context.team;
  }

  async getRegion(): Promise<string | undefined> {
    // Priority: env var > stored context
    if (process.env.REDIACC_REGION) {
      return process.env.REDIACC_REGION;
    }
    const context = await this.get();
    return context.region;
  }

  /**
   * Apply context defaults to command options
   * Priority: explicit options > env vars > stored context
   */
  async applyDefaults(options: CommandOptions): Promise<CommandOptions> {
    const result = { ...options };

    if (!result.team) {
      result.team = await this.getTeam();
    }

    if (!result.region) {
      result.region = await this.getRegion();
    }

    return result;
  }

  private async save(context: CliContext): Promise<void> {
    this.cache = context;
    await nodeStorageAdapter.setItem(STORAGE_KEY, JSON.stringify(context));
  }
}

export const contextService = new ContextService();

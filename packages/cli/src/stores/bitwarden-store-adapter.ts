import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import type { IStoreAdapter, PullResult, PushResult } from './types.js';
import type { RdcConfig } from '../types/index.js';
import type { StoreEntry } from '../types/store.js';

const execFileAsync = promisify(execFile);

/** Prefix for all config items in Bitwarden */
const ITEM_PREFIX = 'rdc:';

/** Bitwarden item type for secure notes */
const SECURE_NOTE_TYPE = 2;

interface BwItem {
  id: string;
  name: string;
  notes: string | null;
  type: number;
  folderId: string | null;
  [key: string]: unknown;
}

interface BwStatus {
  status: 'unauthenticated' | 'locked' | 'unlocked';
  userEmail?: string;
  serverUrl?: string;
}

/**
 * Bitwarden store adapter. Stores each config as a separate secure note
 * in the Bitwarden vault, named with a `rdc:` prefix (e.g., `rdc:rediacc`).
 *
 * Requires the `bw` CLI to be installed, logged in, and unlocked.
 * Set BW_SESSION env var or run `export BW_SESSION=$(bw unlock --raw)`.
 */
export class BitwardenStoreAdapter implements IStoreAdapter {
  private readonly folderId: string | null;
  private sessionKey: string | null = null;

  constructor(entry: StoreEntry) {
    this.folderId = entry.bwFolderId ?? null;
  }

  // ============================================================================
  // Session Management
  // ============================================================================

  /**
   * Ensure we have a valid BW_SESSION. Checks env var first, then vault status.
   * Throws with actionable instructions if the vault is locked or not logged in.
   */
  private async ensureSession(): Promise<string> {
    if (this.sessionKey) return this.sessionKey;

    // Check env var first
    if (process.env.BW_SESSION) {
      this.sessionKey = process.env.BW_SESSION;
      return this.sessionKey;
    }

    // Check vault status
    const status = await this.getStatus();

    if (status.status === 'unauthenticated') {
      throw new Error('Bitwarden vault is not logged in. Run: bw login');
    }

    if (status.status === 'locked') {
      throw new Error('Bitwarden vault is locked. Run: export BW_SESSION=$(bw unlock --raw)');
    }

    // Vault is unlocked but no session key in env — user may have unlocked in another way.
    // We can still try to use bw commands without --session in this case.
    this.sessionKey = '';
    return this.sessionKey;
  }

  private async getStatus(): Promise<BwStatus> {
    try {
      const output = await this.bwRaw(['status']);
      return JSON.parse(output) as BwStatus;
    } catch {
      throw new Error(
        'Bitwarden CLI not found or not working. Install it from: https://bitwarden.com/help/cli/'
      );
    }
  }

  // ============================================================================
  // bw CLI helpers
  // ============================================================================

  /**
   * Execute a bw command without session management (for status checks).
   */
  private async bwRaw(args: string[]): Promise<string> {
    const { stdout } = await execFileAsync('bw', args, {
      timeout: 30000,
      env: { ...process.env },
    });
    return stdout.trim();
  }

  /**
   * Execute a bw command with session token.
   */
  private async bw(args: string[]): Promise<string> {
    const session = await this.ensureSession();
    const sessionArgs = session ? [...args, '--session', session] : args;
    try {
      const { stdout } = await execFileAsync('bw', sessionArgs, {
        timeout: 30000,
        env: { ...process.env },
      });
      return stdout.trim();
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error);
      throw new Error(`Bitwarden CLI error: ${msg}`);
    }
  }

  // ============================================================================
  // Item naming and discovery
  // ============================================================================

  private itemName(configName: string): string {
    return `${ITEM_PREFIX}${configName}`;
  }

  private configNameFromItem(itemName: string): string {
    return itemName.slice(ITEM_PREFIX.length);
  }

  /**
   * Find a BW item by exact name match. bw search is fuzzy, so we filter results.
   */
  private async findItem(configName: string): Promise<BwItem | null> {
    const name = this.itemName(configName);
    const output = await this.bw(['list', 'items', '--search', name, '--raw']);
    const items = JSON.parse(output) as BwItem[];

    return (
      items.find((item) => {
        if (item.name !== name) return false;
        if (this.folderId && item.folderId !== this.folderId) return false;
        return true;
      }) ?? null
    );
  }

  // ============================================================================
  // IStoreAdapter implementation
  // ============================================================================

  /**
   * Check an existing Bitwarden item for GUID or version conflicts.
   * Returns a PushResult if there's a conflict, or null if OK to proceed.
   */
  private checkExistingConflict(existing: BwItem, config: RdcConfig): PushResult | null {
    if (!existing.notes) return null;
    try {
      const remote = JSON.parse(existing.notes) as RdcConfig;
      if (remote.id !== config.id) {
        return {
          success: false,
          error: `GUID mismatch: local config id "${config.id}" does not match remote "${remote.id}".`,
        };
      }
      if (remote.version > config.version) {
        return {
          success: false,
          error: `Version conflict: remote version ${remote.version} is newer than local version ${config.version}. Run "rdc store pull" first.`,
        };
      }
    } catch {
      // Existing notes aren't valid JSON — overwrite
    }
    return null;
  }

  async push(config: RdcConfig, configName: string): Promise<PushResult> {
    const existing = await this.findItem(configName);

    if (existing) {
      // Check for conflicts
      const conflict = this.checkExistingConflict(existing, config);
      if (conflict) return conflict;

      // Update existing item
      const updated = { ...existing, notes: JSON.stringify(config, null, 2) };
      const encoded = Buffer.from(JSON.stringify(updated)).toString('base64');
      await this.bw(['edit', 'item', existing.id, encoded]);
    } else {
      // Create new secure note
      const item = {
        type: SECURE_NOTE_TYPE,
        secureNote: { type: 0 },
        name: this.itemName(configName),
        notes: JSON.stringify(config, null, 2),
        folderId: this.folderId,
      };
      const encoded = Buffer.from(JSON.stringify(item)).toString('base64');
      await this.bw(['create', 'item', encoded]);
    }

    return { success: true, remoteVersion: config.version };
  }

  async pull(configName: string): Promise<PullResult> {
    const item = await this.findItem(configName);

    if (!item?.notes) {
      return { success: false, error: `Config "${configName}" not found in Bitwarden store` };
    }

    try {
      const config = JSON.parse(item.notes) as RdcConfig;
      return { success: true, config };
    } catch {
      return { success: false, error: `Config "${configName}" in Bitwarden has invalid JSON` };
    }
  }

  async list(): Promise<string[]> {
    const output = await this.bw(['list', 'items', '--search', ITEM_PREFIX, '--raw']);
    const items = JSON.parse(output) as BwItem[];

    return items
      .filter((item) => {
        if (!item.name.startsWith(ITEM_PREFIX)) return false;
        if (this.folderId && item.folderId !== this.folderId) return false;
        return true;
      })
      .map((item) => this.configNameFromItem(item.name))
      .sort();
  }

  async delete(configName: string): Promise<PushResult> {
    const item = await this.findItem(configName);

    if (!item) {
      return { success: false, error: `Config "${configName}" not found in Bitwarden store` };
    }

    await this.bw(['delete', 'item', item.id]);
    return { success: true };
  }

  async verify(): Promise<boolean> {
    try {
      const status = await this.getStatus();
      if (status.status !== 'unlocked') return false;

      // Try a list to confirm access
      await this.ensureSession();
      await this.bw(['list', 'items', '--search', ITEM_PREFIX, '--raw']);
      return true;
    } catch {
      return false;
    }
  }
}

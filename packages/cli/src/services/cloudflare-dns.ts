/**
 * Cloudflare DNS API client for managing DNS records.
 *
 * Used by push-infra to auto-create machine subdomain records.
 * Uses native https module — no external dependencies.
 */

import { request as httpsRequest } from 'node:https';

const CF_API_BASE = 'https://api.cloudflare.com/client/v4';

interface DnsRecord {
  id: string;
  type: string;
  name: string;
  content: string;
  ttl: number;
  proxied: boolean;
}

interface CloudflareResponse<T> {
  success: boolean;
  result: T | null;
  errors: { code: number; message: string }[];
}

export type DnsAction = 'created' | 'updated' | 'unchanged';

export class CloudflareDnsClient {
  constructor(private readonly token: string) {}

  async getZoneId(domain: string): Promise<string> {
    const res = await this.request<CloudflareResponse<{ id: string }[]>>(
      'GET',
      `/zones?name=${encodeURIComponent(domain)}`
    );
    if (!res.result || res.result.length === 0) {
      throw new Error(`Cloudflare zone not found for "${domain}"`);
    }
    return res.result[0].id;
  }

  async ensureRecord(
    zoneId: string,
    type: string,
    name: string,
    content: string
  ): Promise<DnsAction> {
    const existing = await this.listRecords(zoneId, type, name);

    if (existing.length > 0) {
      const record = existing[0];
      if (record.content === content) {
        return 'unchanged';
      }
      await this.updateRecord(zoneId, record.id, type, name, content);
      return 'updated';
    }

    await this.createRecord(zoneId, type, name, content);
    return 'created';
  }

  /**
   * Search for DNS records matching a name suffix (e.g., all records under "machine.example.com").
   * Uses Cloudflare's .contains search to find records, then filters by exact suffix match.
   */
  async searchRecordsBySuffix(zoneId: string, nameSuffix: string): Promise<DnsRecord[]> {
    const res = await this.request<CloudflareResponse<DnsRecord[]>>(
      'GET',
      `/zones/${zoneId}/dns_records?name.contains=${encodeURIComponent(nameSuffix)}&per_page=100`
    );
    const all = res.result ?? [];
    // Filter to exact suffix match (Cloudflare .contains is substring, not suffix)
    return all.filter((r) => r.name === nameSuffix || r.name.endsWith(`.${nameSuffix}`));
  }

  async deleteRecord(zoneId: string, recordId: string): Promise<void> {
    await this.request<CloudflareResponse<{ id: string }>>(
      'DELETE',
      `/zones/${zoneId}/dns_records/${recordId}`
    );
  }

  private async listRecords(zoneId: string, type: string, name: string): Promise<DnsRecord[]> {
    const res = await this.request<CloudflareResponse<DnsRecord[]>>(
      'GET',
      `/zones/${zoneId}/dns_records?type=${encodeURIComponent(type)}&name=${encodeURIComponent(name)}`
    );
    return res.result ?? [];
  }

  private async createRecord(
    zoneId: string,
    type: string,
    name: string,
    content: string
  ): Promise<void> {
    const res = await this.request<CloudflareResponse<DnsRecord>>(
      'POST',
      `/zones/${zoneId}/dns_records`,
      { type, name, content, ttl: 1, proxied: false }
    );
    if (!res.success) {
      const msg = res.errors.map((e) => e.message).join(', ');
      throw new Error(`Failed to create DNS record ${type} ${name}: ${msg}`);
    }
  }

  private async updateRecord(
    zoneId: string,
    recordId: string,
    type: string,
    name: string,
    content: string
  ): Promise<void> {
    const res = await this.request<CloudflareResponse<DnsRecord>>(
      'PUT',
      `/zones/${zoneId}/dns_records/${recordId}`,
      { type, name, content, ttl: 1, proxied: false }
    );
    if (!res.success) {
      const msg = res.errors.map((e) => e.message).join(', ');
      throw new Error(`Failed to update DNS record ${type} ${name}: ${msg}`);
    }
  }

  private request<T>(method: string, path: string, body?: unknown): Promise<T> {
    return new Promise((resolve, reject) => {
      const url = new URL(CF_API_BASE + path);
      const postData = body ? JSON.stringify(body) : undefined;

      const req = httpsRequest(
        {
          hostname: url.hostname,
          path: url.pathname + url.search,
          method,
          headers: {
            Authorization: `Bearer ${this.token}`,
            'Content-Type': 'application/json',
            ...(postData ? { 'Content-Length': Buffer.byteLength(postData) } : {}),
          },
          timeout: 15_000,
        },
        (res) => {
          const chunks: Buffer[] = [];
          res.on('data', (chunk: Buffer) => chunks.push(chunk));
          res.on('end', () => {
            const text = Buffer.concat(chunks).toString();
            try {
              resolve(JSON.parse(text) as T);
            } catch {
              reject(new Error(`Invalid JSON from Cloudflare API: ${text.slice(0, 200)}`));
            }
          });
          res.on('error', reject);
        }
      );

      req.on('error', reject);
      req.on('timeout', () => {
        req.destroy();
        reject(new Error('Cloudflare API request timeout'));
      });

      if (postData) req.write(postData);
      req.end();
    });
  }
}

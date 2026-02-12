import { describe, expect, it } from 'vitest';
import {
  mapRcloneToStorageProvider,
  parseRcloneConfig,
  processConfigValue,
  PROVIDER_MAPPING,
  type RcloneConfig,
} from '../rclone.js';

// ============================================
// PROVIDER_MAPPING Tests
// ============================================

describe('PROVIDER_MAPPING', () => {
  const EXPECTED_BACKENDS = [
    'drive',
    'onedrive',
    's3',
    'b2',
    'mega',
    'dropbox',
    'box',
    'azureblob',
    'swift',
    'webdav',
    'ftp',
    'sftp',
  ];

  it('should contain all 12 supported backends', () => {
    for (const backend of EXPECTED_BACKENDS) {
      expect(PROVIDER_MAPPING).toHaveProperty(backend);
    }
    expect(Object.keys(PROVIDER_MAPPING)).toHaveLength(12);
  });

  it('should have string values for all entries', () => {
    for (const [key, value] of Object.entries(PROVIDER_MAPPING)) {
      expect(typeof value).toBe('string');
      expect(value.length).toBeGreaterThan(0);
    }
  });
});

// ============================================
// parseRcloneConfig Tests
// ============================================

describe('parseRcloneConfig', () => {
  describe('valid configs', () => {
    it('should parse single section with type', () => {
      const content = `[myremote]
type = s3
region = us-east-1`;

      const result = parseRcloneConfig(content);
      expect(result).toHaveLength(1);
      expect(result[0].name).toBe('myremote');
      expect(result[0].type).toBe('s3');
      expect(result[0].config.region).toBe('us-east-1');
    });

    it('should parse multiple sections', () => {
      const content = `[remote-s3]
type = s3
bucket = my-bucket

[remote-drive]
type = drive
root_folder_id = root`;

      const result = parseRcloneConfig(content);
      expect(result).toHaveLength(2);
      expect(result[0].name).toBe('remote-s3');
      expect(result[0].type).toBe('s3');
      expect(result[1].name).toBe('remote-drive');
      expect(result[1].type).toBe('drive');
    });

    it('should parse JSON values in config fields', () => {
      const content = `[gdrive]
type = drive
token = {"access_token":"ya29.test","expiry":"2026-01-01T00:00:00Z"}`;

      const result = parseRcloneConfig(content);
      expect(result).toHaveLength(1);
      // parseKeyValuePair tries JSON.parse on all values
      expect(typeof result[0].config.token).toBe('object');
      expect((result[0].config.token as Record<string, unknown>).access_token).toBe('ya29.test');
    });

    it('should handle values containing equals signs', () => {
      const content = `[myremote]
type = s3
secret_key = abc=def=ghi`;

      const result = parseRcloneConfig(content);
      expect(result[0].config.secret_key).toBe('abc=def=ghi');
    });

    it('should handle empty values', () => {
      const content = `[myremote]
type = s3
prefix =`;

      const result = parseRcloneConfig(content);
      expect(result[0].config.prefix).toBe('');
    });

    it('should skip lines starting with #', () => {
      const content = `# This is a comment
[myremote]
type = s3
# Another comment
region = us-east-1`;

      const result = parseRcloneConfig(content);
      expect(result).toHaveLength(1);
      expect(result[0].config.region).toBe('us-east-1');
    });

    it('should skip lines starting with ;', () => {
      const content = `; This is a comment
[myremote]
type = s3
; Another comment
region = eu-west-1`;

      const result = parseRcloneConfig(content);
      expect(result).toHaveLength(1);
      expect(result[0].config.region).toBe('eu-west-1');
    });

    it('should skip blank lines', () => {
      const content = `
[myremote]

type = s3

region = us-east-1

`;

      const result = parseRcloneConfig(content);
      expect(result).toHaveLength(1);
      expect(result[0].config.region).toBe('us-east-1');
    });
  });

  describe('edge cases', () => {
    it('should return empty array for empty string', () => {
      expect(parseRcloneConfig('')).toEqual([]);
    });

    it('should return empty array for only comments', () => {
      const content = `# comment 1
; comment 2
# comment 3`;

      expect(parseRcloneConfig(content)).toEqual([]);
    });

    it('should skip sections without type field', () => {
      const content = `[no-type-remote]
region = us-east-1
bucket = test`;

      expect(parseRcloneConfig(content)).toEqual([]);
    });

    it('should ignore key-value pairs before any section header', () => {
      const content = `orphan_key = orphan_value
type = s3
[myremote]
type = drive`;

      const result = parseRcloneConfig(content);
      expect(result).toHaveLength(1);
      expect(result[0].name).toBe('myremote');
    });

    it('should include section with only type field', () => {
      const content = `[minimal]
type = s3`;

      const result = parseRcloneConfig(content);
      expect(result).toHaveLength(1);
      expect(result[0].name).toBe('minimal');
      expect(result[0].type).toBe('s3');
    });
  });

  describe('realistic config', () => {
    it('should parse multi-section rclone.conf with real providers', () => {
      const content = `# Rclone config file
[s3-digitalocean]
type = s3
provider = DigitalOcean
access_key_id = AKIA123
secret_access_key = secret123
region = nyc3
endpoint = nyc3.digitaloceanspaces.com

[google]
type = drive
scope = drive
token = {"access_token":"ya29.xxx","token_type":"Bearer","expiry":"2026-12-01T00:00:00Z"}
root_folder_id =

[microsoft]
type = onedrive
token = {"access_token":"EwB4A","expiry":"2026-06-01T00:00:00Z"}
drive_id = abc123
drive_type = personal`;

      const result = parseRcloneConfig(content);
      expect(result).toHaveLength(3);

      // S3
      expect(result[0].name).toBe('s3-digitalocean');
      expect(result[0].type).toBe('s3');
      expect(result[0].config.provider).toBe('DigitalOcean');
      expect(result[0].config.access_key_id).toBe('AKIA123');
      expect(result[0].config.endpoint).toBe('nyc3.digitaloceanspaces.com');

      // Drive
      expect(result[1].name).toBe('google');
      expect(result[1].type).toBe('drive');
      expect(typeof result[1].config.token).toBe('object');
      expect(result[1].config.root_folder_id).toBe('');

      // OneDrive
      expect(result[2].name).toBe('microsoft');
      expect(result[2].type).toBe('onedrive');
      expect(result[2].config.drive_type).toBe('personal');
    });
  });
});

// ============================================
// processConfigValue Tests
// ============================================

describe('processConfigValue', () => {
  it('should return non-string values unchanged', () => {
    expect(processConfigValue('token', 42)).toBe(42);
    expect(processConfigValue('token', true)).toBe(true);

    const obj = { access_token: 'abc' };
    expect(processConfigValue('token', obj)).toBe(obj);

    expect(processConfigValue('token', undefined)).toBeUndefined();
  });

  it('should return string values for non-token keys unchanged', () => {
    expect(processConfigValue('region', 'us-east-1')).toBe('us-east-1');
    expect(processConfigValue('bucket', 'my-bucket')).toBe('my-bucket');
    expect(processConfigValue('endpoint', '{"not":"parsed"}')).toBe('{"not":"parsed"}');
  });

  it('should parse JSON string for "token" key', () => {
    const result = processConfigValue('token', '{"access_token":"abc","expiry":"2026-01-01"}');
    expect(typeof result).toBe('object');
    expect((result as Record<string, unknown>).access_token).toBe('abc');
  });

  it('should parse JSON string for keys ending in "_token"', () => {
    const result = processConfigValue('drive_token', '{"access_token":"xyz"}');
    expect(typeof result).toBe('object');
    expect((result as Record<string, unknown>).access_token).toBe('xyz');
  });

  it('should return original string for "token" key with non-JSON value', () => {
    expect(processConfigValue('token', 'plaintext-token')).toBe('plaintext-token');
  });

  it('should return original string for "token" key with malformed JSON', () => {
    expect(processConfigValue('token', '{bad json}')).toBe('{bad json}');
  });

  it('should not parse JSON for key containing "token" but not at end', () => {
    // 'token_bucket' does not match: it's not 'token' and doesn't end with '_token'
    expect(processConfigValue('token_bucket', '{"key":"value"}')).toBe('{"key":"value"}');
  });
});

// ============================================
// mapRcloneToStorageProvider Tests
// ============================================

describe('mapRcloneToStorageProvider', () => {
  it('should map s3 config to vault with provider field', () => {
    const config: RcloneConfig = {
      name: 'my-s3',
      type: 's3',
      config: { type: 's3', region: 'us-east-1', access_key_id: 'AKIA123' },
    };

    const result = mapRcloneToStorageProvider(config);
    expect(result).not.toBeNull();
    expect(result!.provider).toBe('s3');
  });

  it('should exclude type field and store rclone sub-provider separately', () => {
    const config: RcloneConfig = {
      name: 'my-s3',
      type: 's3',
      config: { type: 's3', provider: 'DigitalOcean', region: 'us-east-1', bucket: 'my-bucket' },
    };

    const result = mapRcloneToStorageProvider(config)!;
    expect(result.type).toBeUndefined(); // 'type' is excluded
    expect(result.provider).toBe('s3'); // mapped provider, NOT the config's sub-provider
    expect(result.sub_provider).toBe('DigitalOcean'); // rclone sub-provider stored separately
    expect(result.region).toBe('us-east-1');
    expect(result.bucket).toBe('my-bucket');
  });

  it('should not store sub_provider when rclone provider matches mapped provider', () => {
    const config: RcloneConfig = {
      name: 'my-s3',
      type: 's3',
      config: { type: 's3', provider: 's3', region: 'us-east-1' },
    };

    const result = mapRcloneToStorageProvider(config)!;
    expect(result.provider).toBe('s3');
    expect(result.sub_provider).toBeUndefined();
  });

  it('should return null for unknown type', () => {
    const config: RcloneConfig = {
      name: 'encrypted',
      type: 'crypt',
      config: { type: 'crypt', password: 'secret' },
    };

    expect(mapRcloneToStorageProvider(config)).toBeNull();
  });

  it('should map all 12 supported provider types', () => {
    for (const backendType of Object.keys(PROVIDER_MAPPING)) {
      const config: RcloneConfig = {
        name: `test-${backendType}`,
        type: backendType,
        config: { type: backendType },
      };

      const result = mapRcloneToStorageProvider(config);
      expect(result).not.toBeNull();
      expect(result!.provider).toBe(PROVIDER_MAPPING[backendType]);
    }
  });

  it('should return only provider when config has no extra fields', () => {
    const config: RcloneConfig = {
      name: 'minimal',
      type: 'sftp',
      config: { type: 'sftp' },
    };

    const result = mapRcloneToStorageProvider(config)!;
    expect(result).toEqual({ provider: 'sftp' });
  });

  it('should preserve non-token string values as-is', () => {
    const config: RcloneConfig = {
      name: 'my-s3',
      type: 's3',
      config: { type: 's3', region: 'eu-west-1', endpoint: 'https://s3.example.com' },
    };

    const result = mapRcloneToStorageProvider(config)!;
    expect(result.region).toBe('eu-west-1');
    expect(result.endpoint).toBe('https://s3.example.com');
  });

  it('should process token values through processConfigValue', () => {
    // When parseKeyValuePair already parsed the JSON, token is already an object.
    // processConfigValue returns non-string values unchanged.
    const config: RcloneConfig = {
      name: 'gdrive',
      type: 'drive',
      config: {
        type: 'drive',
        token: { access_token: 'ya29.test', expiry: '2026-01-01' } as unknown as string,
      },
    };

    const result = mapRcloneToStorageProvider(config)!;
    expect(typeof result.token).toBe('object');
    expect((result.token as Record<string, unknown>).access_token).toBe('ya29.test');
  });
});

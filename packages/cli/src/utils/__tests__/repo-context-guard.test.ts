import { describe, expect, it } from 'vitest';
import { detectRepoContextCommand, REPO_CONTEXT_PATTERNS } from '../repo-context-guard.js';

describe('detectRepoContextCommand', () => {
  describe('positive cases (should detect)', () => {
    it.each([
      ['docker ps', 'docker'],
      ['docker compose up -d', 'docker'],
      ['Docker ps', 'docker'],
      ['docker-compose up -d', 'docker'],
      ['DOCKER_HOST=unix:///var/run/rediacc/docker-3072.sock docker ps', 'docker'],
      ['ls /var/run/rediacc/docker-3072.sock', 'docker'],
      ['sudo renet compose -- up -d', 'renet compose'],
      ['ls /mnt/rediacc/mounts/a1b2c3d4-e5f6-7890-abcd-ef1234567890/', 'repo mount path'],
      ['docker ps | grep nginx', 'docker'],
      ['echo start && docker logs web', 'docker'],
      ['bash -c "docker ps"', 'docker'],
    ])('%s → detects "%s"', (command, expectedLabel) => {
      const result = detectRepoContextCommand(command);
      expect(result).not.toBeNull();
      expect(result!.label).toBe(expectedLabel);
    });
  });

  describe('specific pattern matches (no generic docker word)', () => {
    it('detects DOCKER_HOST= without docker command', () => {
      const result = detectRepoContextCommand('DOCKER_HOST=/tmp/sock curl localhost');
      expect(result).not.toBeNull();
      expect(result!.label).toBe('DOCKER_HOST');
    });

    it('detects repo docker socket path without docker word', () => {
      const result = detectRepoContextCommand('ls /var/run/rediacc/docker-3072.sock');
      // matches 'docker' pattern (word boundary before hyphen)
      expect(result).not.toBeNull();
    });

    it('detects renet compose', () => {
      const result = detectRepoContextCommand('sudo renet compose -- up -d');
      expect(result).not.toBeNull();
      expect(result!.label).toBe('renet compose');
    });

    it('detects repo mount path with GUID', () => {
      const result = detectRepoContextCommand(
        'cat /mnt/rediacc/mounts/a1b2c3d4-e5f6-7890-abcd-ef1234567890/config.yml'
      );
      expect(result).not.toBeNull();
      expect(result!.label).toBe('repo mount path');
    });
  });

  describe('negative cases (should NOT detect)', () => {
    it.each([
      'uptime',
      'df -h',
      'cat /etc/hostname',
      'free -m',
      'cat .dockerignore',
      'sudo renet list all --json',
      'ls /mnt/rediacc/mounts/',
    ])('%s → no match', (command) => {
      expect(detectRepoContextCommand(command)).toBeNull();
    });
  });

  it('returns null for empty string', () => {
    expect(detectRepoContextCommand('')).toBeNull();
  });

  it('has 6 patterns defined', () => {
    expect(REPO_CONTEXT_PATTERNS).toHaveLength(6);
  });
});

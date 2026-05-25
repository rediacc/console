import { afterEach, describe, expect, it } from 'vitest';
import {
  detectDockerComposeCommand,
  detectFileWriteCommand,
  detectRepoContextCommand,
  FILE_WRITE_PATTERNS,
  REPO_CONTEXT_PATTERNS,
} from '../repo-context-guard.js';

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

describe('detectFileWriteCommand', () => {
  afterEach(() => {
    delete process.env.REDIACC_SKIP_FILE_WRITE_GUARD;
  });

  describe('positive cases (should detect)', () => {
    it.each([
      ['tee /tmp/out', 'tee'],
      ['tee somefile.txt', 'tee'],
      ['sudo tee /etc/config', 'tee'],
      ['cat > file.txt', 'redirect'],
      ['cat>file', 'redirect'],
      ['echo "x" > out.txt', 'redirect'],
      ['echo hi >> log.txt', 'redirect'],
      ['printf "%s" > /tmp/f', 'redirect'],
      ['base64 -d > /tmp/decoded', 'redirect'],
      ["printf '%s' 'data' > file.new && mv file.new file", 'redirect'],
    ])('%s -> detects "%s"', (command, expectedLabel) => {
      const result = detectFileWriteCommand(command);
      expect(result).not.toBeNull();
      expect(result!.label).toBe(expectedLabel);
    });
  });

  describe('negative cases (should NOT detect)', () => {
    it.each([
      'tee --help',
      'tee -a --append',
      'tee /dev/null',
      'cat /etc/hostname',
      'cat somefile | grep pattern',
      'echo hello',
      'echo hello | grep x',
      'echo test 2>&1',
      'cat file 2>/dev/null',
      'grep foo > /dev/null',
      'ls -la',
      'uptime',
      '',
    ])('%s -> no match', (command) => {
      expect(detectFileWriteCommand(command)).toBeNull();
    });
  });

  it('respects REDIACC_SKIP_FILE_WRITE_GUARD=1', () => {
    process.env.REDIACC_SKIP_FILE_WRITE_GUARD = '1';
    expect(detectFileWriteCommand('tee /tmp/out')).toBeNull();
    expect(detectFileWriteCommand('cat > file.txt')).toBeNull();
  });

  it('has 2 patterns defined', () => {
    expect(FILE_WRITE_PATTERNS).toHaveLength(2);
  });
});

describe('detectDockerComposeCommand', () => {
  describe('positive cases (should detect — docker-compose at command position)', () => {
    it.each([
      'docker compose up -d',
      'docker-compose up',
      'sudo docker compose up -d',
      'sudo docker-compose down',
      'sudo --preserve-env=X docker compose up',
      // FIX 1: sudo -u <user> must not treat <user> as the command
      'sudo -u root docker compose up',
      'sudo --user root docker compose up',
      'sudo -u root -g staff docker compose up',
      '/usr/bin/docker compose up',
      '/usr/local/bin/docker-compose ps',
      'DOCKER_HOST=/tmp/sock docker compose up',
      'FOO=bar docker compose up',
      'env docker-compose down',
      'docker  compose  up',
      'Docker Compose up',
      'DOCKER-COMPOSE ps',
      'cd /app && docker compose restart',
      'cat x.yml; docker-compose up',
      'docker compose up 2>&1',
    ])('%s → detected', (command) => {
      expect(detectDockerComposeCommand(command)).toBe(true);
    });
  });

  describe('negative cases (should NOT detect — substring in args, not a command)', () => {
    it.each([
      'docker ps',
      'docker run -d nginx',
      'docker exec -it web bash',
      'docker-composer --version',
      'renet compose -- up -d',
      'sudo renet compose -- ps',
      'uptime',
      '',
      // rediacc/console#490: reads/searches that merely name the file are allowed
      'cat docker-compose.yml',
      "find . -iname 'docker-compose*'",
      'grep compose docker-compose.yml',
      'head -c 4096 docker-compose.yml',
      // command nested in an opaque -c string is a documented non-match
      'bash -c "docker compose up"',
      'echo "use docker compose"',
    ])('%s → no match', (command) => {
      expect(detectDockerComposeCommand(command)).toBe(false);
    });
  });
});

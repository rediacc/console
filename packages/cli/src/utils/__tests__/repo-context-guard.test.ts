import {
  repoDockerHost,
  repoDockerSocketPath,
  repoSecretsDir,
} from '@rediacc/shared/config/runtime-paths';
import { WK_DATASTORE_PATH, WK_RUNTIME_DIR } from '@rediacc/shared/config/well-known.generated';
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
      ['docker-compose up -d', 'docker-compose'],
      ['DOCKER_HOST=unix:///tmp/other.sock docker ps', 'docker'],
      [`ls ${repoDockerSocketPath(3072)}`, 'repo runtime dir'],
      [`cat ${repoSecretsDir(3072)}/STRIPE_KEY`, 'repo runtime dir'],
      ['sudo renet compose -- up -d', 'renet compose'],
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
      const result = detectRepoContextCommand(`ls ${repoDockerSocketPath(3072)}`);
      // matches the runtime dir pattern (the socket lives inside net-<N>/)
      expect(result).not.toBeNull();
    });

    it('detects a file-mode secret path, which carries no docker word', () => {
      const result = detectRepoContextCommand(`cat ${repoSecretsDir(3072)}/STRIPE_KEY`);
      expect(result).not.toBeNull();
      expect(result!.label).toBe('repo runtime dir');
    });

    it('does not treat the retired flat socket path as a runtime dir', () => {
      expect(
        REPO_CONTEXT_PATTERNS.find((p) => p.label === 'repo runtime dir')!.pattern.test(
          `${WK_RUNTIME_DIR}/docker-3072.sock`
        )
      ).toBe(false);
    });

    it('detects renet compose', () => {
      const result = detectRepoContextCommand('sudo renet compose -- up -d');
      expect(result).not.toBeNull();
      expect(result!.label).toBe('renet compose');
    });
  });

  describe('a docker segment that names one repo socket itself', () => {
    const moved = repoDockerHost(3136);
    const flat = `unix://${WK_RUNTIME_DIR}/docker-3136.sock`;

    it.each([
      `sudo docker -H ${flat} ps`,
      `sudo docker -H ${moved} ps`,
      `docker --host ${moved} ps -a`,
      `docker --host=${moved} ps`,
      `docker -H=${flat} logs web`,
      `docker -H '${moved}' ps`,
      `DOCKER_HOST=${moved} docker ps`,
      `sudo DOCKER_HOST=${flat} docker ps`,
      `env DOCKER_HOST=${moved} docker inspect web`,
      `sudo docker -H ${flat} ps | grep nginx`,
      `uptime && sudo docker -H ${moved} ps`,
    ])('%s → admitted', (command) => {
      expect(detectRepoContextCommand(command)).toBeNull();
    });

    it.each([
      // A second docker segment without its own host still needs repo context.
      [`sudo docker -H ${moved} ps; docker ps`, 'docker'],
      // The socket of the host's system daemon, or an arbitrary path, is not a repo socket.
      ['sudo docker -H unix:///var/run/docker.sock ps', 'docker'],
      [`docker -H unix://${WK_RUNTIME_DIR}/net-3136/docker-3137.sock ps`, 'docker'],
      [`docker -H unix://${WK_RUNTIME_DIR}/net-3136/../docker-3137.sock ps`, 'docker'],
      // Without the unix:// scheme docker reads no socket, so nothing is named.
      [`docker -H ${WK_RUNTIME_DIR}/docker-3136.sock ps`, 'docker'],
      // A flag before -H that may take a value ends the scan.
      [`docker --context x -H ${moved} ps`, 'docker'],
      // An assignment exported in an earlier segment does not travel.
      [`export DOCKER_HOST=${moved}; docker ps`, 'docker'],
      // The host names a socket, but the segment runs something else.
      [`DOCKER_HOST=${moved} curl localhost`, 'DOCKER_HOST'],
    ])('%s → still detects "%s"', (command, expectedLabel) => {
      const result = detectRepoContextCommand(command);
      expect(result).not.toBeNull();
      expect(result!.label).toBe(expectedLabel);
    });

    it.each([
      `sudo docker -H ${moved} compose up -d`,
      `docker --host=${moved} compose down`,
      `docker --context x compose up`,
      `DOCKER_HOST=${flat} docker compose up -d`,
    ])('leaves %s to the compose guard, which refuses it', (command) => {
      expect(detectDockerComposeCommand(command)).toBe(true);
    });
  });

  describe('commands that only NAME docker in a unit or path (not docker client calls)', () => {
    const mount = `${WK_DATASTORE_PATH}/mounts/a1b2c3d4-e5f6-7890-abcd-ef1234567890`;
    it.each([
      "systemctl list-units 'rediacc-docker-*'",
      'systemctl status rediacc-docker-12288',
      'find / -path /var/lib/docker',
      'ls /var/lib/docker',
      'cat /etc/docker/daemon.json',
      // Mount metadata reads need no DOCKER_HOST.
      `ls -la ${mount}`,
      `stat ${mount}`,
      `du -sh ${mount}`,
      `df ${mount}`,
      `findmnt ${mount}`,
      `cat ${mount}/some-file`,
      `cat ${mount}/docker-compose.yml`,
    ])('%s → admitted', (command) => {
      expect(detectRepoContextCommand(command)).toBeNull();
    });

    it.each([
      ['sudo docker ps', 'docker'],
      ['nice -n 5 docker ps', 'docker'],
      ['timeout 10 docker ps', 'docker'],
      ['ls | xargs docker rm', 'docker'],
      ['sudo /usr/bin/docker-compose up', 'docker-compose'],
      ['bash -c "docker ps"', 'docker'],
      ['docker compose up -d', 'docker'],
      [`docker run -v ${mount}:/data nginx`, 'docker'],
      [`DOCKER_HOST=unix:///tmp/x.sock ls ${mount}`, 'DOCKER_HOST'],
      ['echo $(docker ps -q)', 'docker'],
      ['echo `docker ps -q`', 'docker'],
      ['echo $(sudo $(which true) && docker info)', 'docker'],
      ['/usr/bin/docker ps', 'docker'],
      ['watch docker ps', 'docker'],
      ["bash -lc 'docker ps'", 'docker'],
      ['sh -ec "docker ps"', 'docker'],
      ['su -c "docker ps" root', 'docker'],
      ['flock /tmp/l -c "docker ps"', 'docker'],
      ['nohup docker ps', 'docker'],
      ['eval docker ps', 'docker'],
      ['setsid docker ps', 'docker'],
      ['ionice -c3 docker ps', 'docker'],
      ['find / -name x -exec docker rm {} \\;', 'docker'],
      [
        `curl --unix-socket ${WK_RUNTIME_DIR}/docker-3136.sock http://x/containers/json`,
        'repo docker socket',
      ],
    ])('%s → still detects "%s"', (command, label) => {
      expect(detectRepoContextCommand(command)?.label).toBe(label);
    });
  });

  describe('negative cases (should NOT detect)', () => {
    it.each([
      'uptime',
      'df -h',
      'cat /etc/hostname',
      'free -m',
      'cat .dockerignore',
      'systemctl restart docker',
      'journalctl -u docker --since today',
      'sudo systemctl status docker',
      'grep -c docker /etc/group',
      'sudo renet list all --json',
      `ls ${WK_DATASTORE_PATH}/mounts/`,
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

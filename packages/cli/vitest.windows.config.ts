import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vitest/config';

// The Windows lane (PLAN-windows-lane D10, D13): the test files that exercise win32 or fake it, named one by one. A file is added by name once it has been measured on the Windows VM (`PYTHONPATH=.ci python3 -m rediacc_ci.drills.win_check -- --suite unit`); the whole suite is deliberately not run, because POSIX-only tests would fail on it for reasons that say nothing about win32.
//
// Files in the list that skip quietly on win32 (a green run does not cover them there):
//   remote/terminal/__tests__/launchers-windows-cleanup  (posixIt cases)
//   remote/terminal/__tests__/launchers-secret-env       (posixIt cases)
//   remote/sync/__tests__/sftp-fallback                  (posixIt cases)
//   remote/ssh/__tests__/session-exit                    (POSIX describe skipped)
//   remote/vscode/__tests__/bootstrap-secret-env         (one POSIX case)
//   remote/vscode/__tests__/keyPersistence               (0600 mode assertion skipped)
//   commands/__tests__/term-secret-env                   (posixIt cases)
//   commands/__tests__/term-docker-socket                (POSIX describe skipped)
//   commands/mcp/__tests__/stdio-e2e                     (whole suite skipped)
//   commands/__tests__/tools-path-lookup                 (real-filesystem describe skipped)
//   utils/__tests__/secure-storage.tools                 (posixIt cases)
//   utils/__tests__/process-ancestry                     (Linux /proc cases skipped; the win32 helper path is covered by the lane's renet process-ancestry step)
//
// setupFiles and globalSetup equal vitest.config.ts, so the isolated config home and the per-run TEMP directory hold here as they do there.
const tierA = [
  // VS Code
  'remote/vscode/__tests__/executable-spawn',
  'remote/vscode/__tests__/executable-launch',
  'remote/vscode/__tests__/envCompose',
  'remote/vscode/__tests__/settings',
  'remote/vscode/__tests__/sshConfig',
  // term --external
  '__tests__/term-external-handoff',
  '__tests__/term-external-launch',
  '__tests__/term-external-windows-handoff',
  // rsync and MSYS2
  'remote/sync/__tests__/rsync-args',
  'remote/sync/__tests__/rsync-bytes-wiring',
  'remote/sync/__tests__/rsync-count',
  'remote/sync/__tests__/rsync-deleted',
  'remote/sync/__tests__/rsync-failure-reason',
  'remote/sync/__tests__/rsync-inplace-partial',
  'remote/sync/__tests__/rsync-missing-windows',
  'remote/sync/__tests__/rsync-skipped',
  'remote/sync/__tests__/pathConverter',
  'remote/msys2/__tests__/paths',
  'remote/msys2/__tests__/paths-cache',
  // host keys, agent guard, secure storage
  'utils/__tests__/host-keys',
  'utils/__tests__/host-keys-scan',
  'utils/__tests__/agent-guard',
  'utils/__tests__/process-ancestry',
  'utils/__tests__/secure-storage.tools',
  'utils/__tests__/secure-storage.dpapi-timeout',
  'commands/machine/__tests__/scan-keys',
  'commands/machine/__tests__/scan-keys-envelope',
  'remote/ssh/__tests__/agent-windows',
  // doctor and tools
  'commands/__tests__/doctor-ops-timeout',
  'commands/__tests__/doctor-secret-store',
  'commands/__tests__/doctor-subscription',
  'commands/__tests__/doctor-tools',
  'commands/__tests__/doctor-windows',
  'commands/__tests__/tools-install',
  'commands/__tests__/tools-path-lookup',
  'services/tools/__tests__/rsync-install',
  // MCP
  'commands/mcp/__tests__/server',
  'commands/mcp/__tests__/tools',
  'commands/mcp/__tests__/executor',
];

// The nine POSIX-only files of D13 (WL19): portable where the code under test is portable, else skipped on win32 with a BLOCKER comment.
const posixPortable = [
  'commands/__tests__/term-secret-env',
  'commands/__tests__/term-docker-socket',
  'remote/terminal/__tests__/launchers-secret-env',
  'remote/terminal/__tests__/launchers-windows-cleanup',
  'remote/ssh/__tests__/session-exit',
  'remote/vscode/__tests__/keyPersistence',
  'remote/sync/__tests__/sftp-fallback',
  'remote/vscode/__tests__/bootstrap-secret-env',
  'commands/mcp/__tests__/stdio-e2e',
];

export default defineConfig({
  test: {
    globalSetup: [fileURLToPath(new URL('../../scripts/lib/vitest-run-tmp.ts', import.meta.url))],
    fsModuleCachePath: fileURLToPath(
      new URL('../../node_modules/.vitest-cache-cli-windows', import.meta.url)
    ),
    globals: true,
    environment: 'node',
    testTimeout: 30_000,
    include: [
      ...[...tierA, ...posixPortable].map((name) => `src/${name}.test.ts`),
      'src/commands/ops/__tests__/*.test.ts',
    ],
    setupFiles: ['src/__tests__/isolate-config-home.ts'],
    exclude: ['node_modules', 'dist', 'tests/**', 'src/**/*.integration.test.ts'],
  },
});

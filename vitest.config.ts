/**
 * NO VITEST RUN BELONGS AT THE REPOSITORY ROOT. Each workspace's own vitest.config.ts carries
 * what its tests rely on, and the CLI's `setupFiles` is what points every test at a throwaway
 * config home (packages/cli/src/__tests__/isolate-config-home.ts). A run started here loaded no
 * package config, so that isolation never ran: on 2026-10-14 a root-level
 * `npx vitest run packages/cli/...` let config-remote-reenroll.test.ts delete the developer's
 * real ~/.config/rediacc, the BWS bootstrap token with it (#61fb7bc3).
 *
 * So a root run stops here and names the command that runs the same files safely.
 */
throw new Error(
  'vitest was started at the repository root, where no workspace config (and no test isolation) applies. ' +
    'Run it from the workspace instead, e.g. `cd packages/cli && npx vitest run src/commands/__tests__/x.test.ts`.'
);

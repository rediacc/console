/**
 * Command planes — where each command actually executes.
 *
 * A plane is a claim the web console and the `rdc --proxy` thin client trust:
 * a machine-plane command is offered for remote execution on the operator's
 * behalf, a config-plane command is not. Nothing in the type system checks it,
 * so two gates do: check-command-planes.ts cross-checks every plane against the
 * import graph, and plane-coverage.test.ts fails when a command resolves none.
 *
 * Kept separate from command-metadata.ts because planes resolve by ancestor
 * inheritance (a domain entry is the default, the rest are exceptions), which
 * none of the MCP or policy annotations do — and because that file is already
 * at its max-lines budget.
 */

/**
 * - `machine`: reaches a customer machine — renet execute (services/executor/
 *   local-executor), services/machine/*, remote/ssh, remote/sftp, or
 *   services/tofu.
 * - `config`: only reads or writes local CLI config and resource state.
 * - `other`: neither — local tooling (self-update, diagnostics, local KVM dev
 *   VMs, the MCP server) and account-server HTTPS calls (licensing, the
 *   encrypted remote-config store). An account-server call is NOT `machine`.
 */
export type CommandPlane = 'config' | 'machine' | 'other';

export interface PlaneMeta {
  plane?: CommandPlane;
  /**
   * The command's default invocation needs a TTY or never returns on its own:
   * an interactive shell, $EDITOR, a tunnel or stream held until Ctrl+C, or a
   * browser callback. Such commands cannot be driven by a headless executor or
   * a web console, so they are never proxyable regardless of plane.
   */
  interactive?: boolean;
}

/**
 * Domain entries are the default; everything else is an exception that breaks
 * its domain's default, with the evidence for it.
 */
export const COMMAND_PLANES: Record<string, PlaneMeta> = {
  // ── Domain defaults ───────────────────────────────────────────────────
  machine: { plane: 'machine' },
  repo: { plane: 'machine' },
  cluster: { plane: 'machine' },
  term: { plane: 'machine' },
  // Every `job` verb SSHes to a machine to drive `renet job ...` against its
  // spool. Not interactive: even `logs --follow` streams to stdout and ends on
  // its own when the job finishes, so a headless executor can drive it.
  job: { plane: 'machine' },
  datastore: { plane: 'machine' },
  vscode: { plane: 'machine' },
  config: { plane: 'config' },
  // Mostly CRUD over the local storage list; only `prune` reaches a machine and
  // only `browse` shells out to a local rclone.
  storage: { plane: 'config' },
  // login/logout/status are account-server HTTPS; the -m subcommands are not.
  subscription: { plane: 'other' },
  // Local KVM/QEMU dev VMs, driven by spawning the *local* renet binary
  // (services/executor/ops-executor). Never uses the machine-plane services.
  ops: { plane: 'other' },
  doctor: { plane: 'other' },
  credits: { plane: 'other' },
  update: { plane: 'other' },
  mcp: { plane: 'other' },

  // ── machine: the CRUD four only touch the config file ──────────────────
  'machine list': { plane: 'config' },
  'machine create': { plane: 'config' },
  'machine rename': { plane: 'config' },
  'machine delete': { plane: 'config' },
  // Renders machine.backupStrategies straight out of the config.
  'machine backup list': { plane: 'config' },

  // ── repo: config-side ref and secret ops, and the local template catalog ─
  // The one git-like ref op that never leaves the config: it rewrites the
  // repository's `branches` map. (`repo log`, `commit`, `checkout`, `merge`,
  // `gc` and `fsck` all read or write objects on the machine.)
  'repo branch': { plane: 'config' },
  // The store IS the encrypted config (repo-secrets-store imports no executor
  // or SSH). Values reach the machine later, via `repo up`.
  'repo secret': { plane: 'config' },
  // Resource-state reads; the rest of both families dispatch to the machine.
  'repo replicate status': { plane: 'config' },
  'repo canary status': { plane: 'config' },
  // Prints the compiled-in catalog (templates/embedded.generated.ts). No
  // config, no machine. `repo template apply` inherits repo's machine default.
  'repo template list': { plane: 'other' },
  // Holds an SSH tunnel open until Ctrl+C.
  'repo tunnel': { interactive: true },

  // ── storage ───────────────────────────────────────────────────────────
  'storage prune': { plane: 'machine' },
  // Lists a bucket by spawning the operator's local rclone against the vault
  // credentials — it reaches the storage backend, never a machine.
  'storage browse': { plane: 'other' },

  // ── cluster ───────────────────────────────────────────────────────────
  // Prints the cluster's config block (configService.listClusters); it does not
  // query the live cluster, so it is the one config-plane leaf in the domain.
  'cluster status': { plane: 'config' },

  // ── config: the leaves that DO reach a machine ────────────────────────
  // scan-keys shells out to `ssh-keyscan` against the host; setup SFTPs the
  // renet binary over and runs `renet setup`; set-ceph is a retired stub that
  // always throws, but is nominally a machine op.
  'config machine scan-keys': { plane: 'machine' },
  'config machine setup': { plane: 'machine' },
  'config machine set-ceph': { plane: 'machine' },
  // `config infra push` runs `renet proxy configure` on the machine. `config
  // infra set`/`show` only read and write the machine's infra block in the
  // local config — their -m flag is a config key, not a connection.
  'config infra push': { plane: 'machine' },
  // pull/push move Traefik's acme.json to and from the machine over SSH;
  // status/clear only touch the local cache.
  'config cert-cache pull': { plane: 'machine' },
  'config cert-cache push': { plane: 'machine' },
  // The zero-knowledge config store on the account server (HTTPS), not a machine.
  'config remote': { plane: 'other' },
  // Opens a browser and blocks on a localhost callback (unless --headless).
  'config remote enable': { interactive: true },
  // $EDITOR round-trip on the decrypted config (unless --dump/--apply).
  'config edit': { interactive: true },
  // Hard-refuses a non-TTY stdin before re-wrapping field keys.
  'config field rotate': { interactive: true },
  // watchFile-based follow; never exits on its own.
  'config audit tail': { interactive: true },

  // ── vscode: only connect and the remote code-server lifecycle are remote ─
  // list/cleanup edit the local ~/.ssh/config block; check probes the local
  // VS Code install. (`vscode serve status`/`stop` inherit machine: they drive
  // the remote code-server over SSH.)
  'vscode list': { plane: 'config' },
  'vscode cleanup': { plane: 'config' },
  'vscode check': { plane: 'other' },
  // Launches the local VS Code GUI, or holds an SSH tunnel open until SIGINT.
  'vscode connect': { interactive: true },

  // ── term ──────────────────────────────────────────────────────────────
  // `term connect -c "<cmd>"` is a non-interactive one-shot, but the default
  // invocation is an interactive `ssh -tt` with stdio inherited.
  'term connect': { interactive: true },

  // ── subscription: the -m subcommands push license contracts over SSH ───
  // Each SFTPs renet to the machine and runs `renet repository license-*` on
  // it, so they are machine-plane even though the domain default is `other`.
  'subscription activation': { plane: 'machine' },
  'subscription repo': { plane: 'machine' },
  'subscription refresh': { plane: 'machine' },

  // ── ops ───────────────────────────────────────────────────────────────
  // Spawns `ssh` with stdio inherited into a local dev VM.
  'ops ssh': { interactive: true },

  // ── serve ─────────────────────────────────────────────────────────────
  // The executor daemon. `plane: machine` is honest — running machine
  // operations on a caller's behalf is its entire job, and it imports
  // local-executor to do it. `interactive` because it listens until SIGINT and
  // never returns, which is also what keeps it out of the proxy: forwarding
  // `rdc serve` to an executor would ask the executor to start another one.
  serve: { plane: 'machine', interactive: true },
};

/** Indexed for lookup: a Map.get() is honestly optional, a Record index is not. */
const PLANES = new Map<string, PlaneMeta>(Object.entries(COMMAND_PLANES));

/** Walk a command path from the most specific entry up to its domain. */
function resolveAncestor<T>(
  commandPath: string,
  pick: (meta: PlaneMeta) => T | undefined
): T | undefined {
  const parts = commandPath.split(' ');
  for (let i = parts.length; i > 0; i--) {
    const meta = PLANES.get(parts.slice(0, i).join(' '));
    if (!meta) continue;
    const value = pick(meta);
    // An explicit `false` is an answer, not a miss: it lets a leaf opt out of
    // an ancestor's flag.
    if (value !== undefined) return value;
  }
  return undefined;
}

/**
 * Resolve a command's execution plane, inheriting from the nearest ancestor.
 *
 * "repo secret list" checks "repo secret list", then "repo secret", then
 * "repo" — so a domain entry supplies the default and only exceptions need an
 * entry of their own.
 *
 * Throws on an unresolvable path: every command must declare a plane, directly
 * or by inheritance, so a new command cannot reach the web console or the proxy
 * unclassified.
 */
export function getCommandPlane(commandPath: string): CommandPlane {
  const plane = resolveAncestor(commandPath, (m) => m.plane);
  if (plane) return plane;

  const domain = commandPath.split(' ')[0];
  throw new Error(
    `No plane for command "${commandPath}". Add an entry to COMMAND_PLANES in ` +
      `command-planes.ts (or give its domain "${domain}" a default). A plane says where the ` +
      'command runs: machine (reaches a customer machine), config (local config only), or ' +
      'other (local tooling / account server).'
  );
}

/** True when the command needs a TTY or never returns (see PlaneMeta.interactive). */
export function isInteractiveCommand(commandPath: string): boolean {
  return resolveAncestor(commandPath, (m) => m.interactive) ?? false;
}

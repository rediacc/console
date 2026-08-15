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
  // schedule/run/status/cancel/list/restore all reach a machine (systemd timers,
  // renet, SSH). Only the `strategy` subgroup is config-only (see below).
  backup: { plane: 'machine' },
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

  // ── machine: config-CRUD leaves only touch the config file ─────────────
  // add/remove/list write or read the config record; provider add/remove/list
  // register cloud-provider credentials in the config; `infra set`/`show` edit
  // the machine's infra block in the config; `infra cert status`/`clear` read
  // and clear the LOCAL cert cache. All would produce the CALLER's answer, so
  // they must stay config-plane inside a machine-default domain (spec/03 §4.9).
  // `setup`, `scan-keys`, `infra push`, `infra cert pull`/`push`, provision,
  // deprovision, prune, health, status all reach the machine via the default.
  'machine list': { plane: 'config' },
  'machine add': { plane: 'config' },
  'machine remove': { plane: 'config' },
  'machine provider': { plane: 'config' },
  'machine infra set': { plane: 'config' },
  'machine infra show': { plane: 'config' },
  'machine infra cert status': { plane: 'config' },
  'machine infra cert clear': { plane: 'config' },

  // ── backup: named strategy records are config-only; the rest reach a machine ─
  // `backup strategy set/remove/list/show` edit strategy records in the config
  // (backup-strategy.ts imports no executor or SSH).
  'backup strategy': { plane: 'config' },
  // `backup usage`/`backup manifests` are account-tunnel READS (accountServerFetch),
  // not machine executor commands — control-plane, so `other` (like `subscription`).
  // `backup verify` DOES reach a machine (backup_verify verb), so it keeps the
  // backup-domain machine default.
  'backup usage': { plane: 'other' },
  'backup manifests': { plane: 'other' },
  // `backup retention` (and its set/clear children) is the same shape: it reads
  // and writes the policy through accountServerFetch and never touches a
  // machine. Without these entries it inherits the backup-domain MACHINE
  // default and becomes proxyCapable, which would offer a policy that decides
  // what gets DELETED for execution against the wrong target.
  'backup retention': { plane: 'other' },
  'backup retention set': { plane: 'other' },
  'backup retention clear': { plane: 'other' },

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
  // Archived-record bookkeeping: list/restore/purge read and write the config's
  // archive map and nothing else (repo-admin.ts imports no executor or SSH). These
  // leaves were `config repository {list,restore,purge}-archived` — config-plane by
  // their old domain's default — and the §5.4 relocation into `repo` silently
  // flipped them to repo's MACHINE default, which made them proxyCapable. Through
  // the proxy that is a wrong-target bug in the §4.9 sense: the effect is the
  // CALLER's config, so a remote `archive purge` would permanently delete the proxy
  // host's archived records instead. The plane gate cannot see this — it checks
  // domains, not leaves, and `repo` plainly reaches machines.
  'repo admin archive': { plane: 'config' },
  // Prints the compiled-in catalog (templates/embedded.generated.ts). No config, no
  // machine. `repo admin template apply` inherits repo's machine default. Moved under
  // `repo admin` with its command in w2b (§5.4).
  'repo admin template list': { plane: 'other' },
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

  // ── config: machine/provider/infra/cert-cache moved to the `machine` noun ─
  // (their planes now live under `machine …` above).
  // `config reconcile` reaches every machine (renet list all) to rebuild state,
  // so it is honestly machine-plane — and it is config's ONLY machine leaf, which
  // keeps Rule 2 satisfied now that the machine/infra leaves left. It is barred
  // from the proxy (PROXY_EXCLUSIONS) because its effect is the CALLER's state.
  'config reconcile': { plane: 'machine' },
  // Rotates the ORGANIZATION's config-encryption key via the account server
  // (HTTPS), not a machine.
  'config rotate-cek': { plane: 'other' },
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

  // ── subscription: the -m forms push license contracts over SSH ─────────
  // Each SFTPs renet to the machine and runs `renet repository license-*` on
  // it, so they are machine-plane even though the domain default is `other`.
  // w2b flattened `activation status` / `repo status` into `status -m`, and
  // `refresh {activation,repos,repo}` into `refresh [-m] [--repo]`, so `status`
  // is now a machine-plane exception too (the account-only form was not).
  'subscription status': { plane: 'machine' },
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

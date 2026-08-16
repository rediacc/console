/**
 * Command Plane Coverage
 *
 * Every command the CLI can actually run must declare where it runs. The web
 * console and the proxy read `plane` to decide whether a command may be
 * executed remotely, so an unclassified command is not a missing label — it is
 * a command that reaches those consumers with no answer to "does this touch a
 * machine?".
 *
 * Walks the LIVE Commander tree (the same walker the contract generator uses)
 * and fails when a command resolves no plane, or when the plane map has grown
 * entries that no longer match a real command.
 */
import { describe, expect, it } from 'vitest';
import {
  createDescriptionResolver,
  EXCLUDED_TOP_LEVEL,
  loadLocale,
  walkContractCommands,
} from '../../../scripts/lib/command-tree-lib.js';
import { cli } from '../../cli.js';
import { COMMAND_PLANES, getCommandPlane, isInteractiveCommand } from '../command-planes.js';

const resolver = createDescriptionResolver(loadLocale('en'));
const COMMANDS = walkContractCommands(cli, resolver);

/** Every command path in the live tree, including non-runnable groups. */
function allTreePaths(): Set<string> {
  const paths = new Set<string>();
  const walk = (cmd: (typeof cli.commands)[number], prefix: string): void => {
    if (cmd.name() === 'help') return;
    const path = prefix ? `${prefix} ${cmd.name()}` : cmd.name();
    paths.add(path);
    for (const sub of cmd.commands) walk(sub, path);
  };
  for (const cmd of cli.commands) walk(cmd, '');
  return paths;
}

describe('command plane coverage', () => {
  it('every runnable command resolves a plane', () => {
    const unresolved: string[] = [];

    for (const cmd of COMMANDS) {
      try {
        getCommandPlane(cmd.pathKey);
      } catch {
        unresolved.push(cmd.pathKey);
      }
    }

    if (unresolved.length > 0) {
      const hint = unresolved
        .map((p) => `  - "${p}": add a plane in command-metadata.ts (or to an ancestor)`)
        .join('\n');
      expect.fail(`${unresolved.length} command(s) resolve no plane:\n${hint}`);
    }
  });

  it('resolves only known planes', () => {
    for (const cmd of COMMANDS) {
      expect(['config', 'machine', 'other']).toContain(getCommandPlane(cmd.pathKey));
    }
  });

  /**
   * A held-out top level is invisible to every consumer of the contract — this
   * gate, MCP coverage, console coverage, the docs checks. So a stale entry fails
   * OPEN: it names a command that does not exist, and the day someone adds that
   * command it is silently exempt from all of them. P4 found five stale entries
   * (`login`, `logout`, `trace`, `cancel`, `retry`) sitting in the list.
   */
  it('holds out only commands that actually exist', () => {
    const topLevel = new Set(cli.commands.map((c) => c.name()));
    const stale = [...EXCLUDED_TOP_LEVEL].filter((name) => !topLevel.has(name));

    expect(stale).toEqual([]);
  });

  /**
   * A count snapshot, so that moving a command between planes is a deliberate,
   * reviewable edit rather than a silent side effect. Update the numbers when
   * you add a command, and say why in the commit.
   */
  it('plane counts match the recorded distribution', () => {
    const counts = { config: 0, machine: 0, other: 0 };
    for (const cmd of COMMANDS) counts[getCommandPlane(cmd.pathKey)]++;

    // Post-P4-w2a totals (the config exodus consolidated ~20 leaves: config
    // machine/provider/infra/cert-cache/storage/repository/cluster/backup-strategy
    // all moved onto their resource nouns, and the new `backup` noun + `config
    // reconcile` were added), minus the hidden `_refprobe run` P4 task-zero probe
    // retired by w2b (its `repo cat` acceptance vehicle is now a real leaf), minus
    // `repo mount`/`repo unmount` folded into `repo up --no-start` / `repo down
    // --unmount` by w2b (both machine-plane, so 93 -> 91). Still includes the +5
    // `rdc job` verbs.
    //
    // 160 -> 162 (machine 91 -> 93) in the w2b cluster batch: `repo canary`'s
    // actionable parent became the real leaf `repo canary create` (net 0), and the
    // two NEW `cluster snapshot create|list` leaves landed (R2-F13). Both reach a
    // machine (the control node's group-snapshot bridge verbs), so both are
    // machine-plane.
    //
    // 162 -> 157 in the w2b subscription flatten (§5.11): `activation status`,
    // `repo status`, `refresh activation`, `refresh repos`, `refresh repo` (5
    // leaves) collapse into `status [-m]` and `refresh [-m] [--repo]`. Their two
    // parent nouns go with them. `subscription status` becomes machine-plane (its
    // -m form SSHes), which is why machine only drops 93 -> 89 and other 21 -> 20.
    //
    // 157 -> 162 (machine 89 -> 94) in the w2b datastore batch (#34): the family
    // was a facade (init dispatched a renet verb that does not exist; fork/unfork
    // were leaves whose whole body was a throw). It becomes the real 10-leaf
    // surface over P1's named registry: create/list/status/attach/detach/fork/
    // snapshot create|list/resize/delete. All machine-plane: every one dispatches
    // a datastore_* bridge verb at the machine holding the pool.
    //
    // 162 -> 164 (machine 94 -> 96): the two NEW leaves `repo logs` and `repo exec`
    // (R2-F14). They are what let `term connect` drop its container side door
    // (--container/--log-lines/--follow) and be honestly excluded from MCP: an agent
    // asks for a log line or a command run, not for a shell to type into.
    //
    //
    // The `repo admin` subtree move (§5.4) relocated validate/fsck/ownership/
    // autostart/template. The counts are UNCHANGED by it, and that is the point: the
    // COMMAND_PLANES exception moved WITH the command (`repo template list` ->
    // `repo admin template list`, the one `other`-plane leaf, which prints the
    // compiled-in catalog). Had the plane entry been left behind, the leaf would have
    // silently inherited repo's `machine` default and claimed to reach a machine it
    // never touches — the §4.10 staleness hazard, made real.
    //
    // machine 96 -> 93, config 48 -> 51: `repo admin archive {list,restore,purge}` are
    // config-plane. That hazard had ALREADY struck them and nobody noticed: they came
    // from `config repository *-archived` (config-plane by their old domain's default),
    // the relocation into `repo` handed them repo's MACHINE default, and no entry was
    // written. They import no executor and no SSH — they only read and write the
    // config's archive map — so the machine plane was a false claim, and it made them
    // proxy-capable: a proxied `archive purge` would have permanently deleted the
    // PROXY HOST's archived records rather than the caller's (§4.9).
    // 164 -> 166, config 51 -> 53: the two NEW leaves `backup strategy bind` and
    // `unbind`. `machine.backupStrategies[]` decides which strategies `backup
    // schedule` deploys, and nothing could write it — the only writer was
    // config-refs-prune, which only removes — so completing a strategy rename
    // required hand-editing the config file. They inherit the `backup strategy`
    // subtree's config plane, which is correct and deliberate: both only
    // read-modify-write the local config and import no executor or SSH. The
    // machine-plane default of the `backup` domain would have been a false claim.
    // 166 -> 167, config 53 -> 54: the new `config current` leaf, a read-only
    // config-plane command that reports the resolved server/channel/token state.
    // 167 -> 170, machine 93 -> 94, other 20 -> 22: the chunk-store backup reads.
    // `backup verify` reaches a machine (backup_verify verb) so it keeps the backup
    // domain's machine default; `backup usage` and `backup manifests` are
    // account-tunnel reads (accountServerFetch), so `other` like `subscription`.
    // 170 -> 171: `backup snapshot`, the chunk-store WRITE verb.
    // 171 -> 174, other 22 -> 25: `backup retention` and its `set`/`clear`
    // children — the CLI half of retention enforcement, without which the
    // policy was enforceable server-side but UNDECLARABLE. They are `other`
    // for the same reason `usage` and `manifests` are: accountServerFetch
    // against the control plane, never a machine. Inheriting the backup
    // domain's machine default would have made them proxyCapable, offering
    // the command that decides what gets DELETED for remote execution.
    expect(COMMANDS.length).toBe(175);
    expect(counts).toEqual({ config: 54, machine: 96, other: 25 });
  });

  it('records the interactive commands', () => {
    const interactive = COMMANDS.filter((c) => isInteractiveCommand(c.pathKey))
      .map((c) => c.pathKey)
      .sort();

    // Commands that need a TTY or never return: an interactive shell, $EDITOR,
    // a tunnel or stream held until Ctrl+C, a browser callback, or a daemon
    // that listens until SIGINT.
    expect(interactive).toEqual([
      'config audit tail',
      'config edit',
      'config field rotate',
      'config remote enable',
      'ops ssh',
      'repo tunnel',
      'serve',
      'term connect',
      'vscode connect',
    ]);
  });

  it('records the machine-plane commands a remote executor could run', () => {
    // These are the candidates for proxying. The contract narrows them further
    // via PROXY_EXCLUSIONS in generate-cli-contract.ts (client-side transfers,
    // and commands whose effect lands in the caller's own config); the exclusion
    // set itself is asserted in the shared cli-contract tests.
    const machineNonInteractive = COMMANDS.filter(
      (c) => getCommandPlane(c.pathKey) === 'machine' && !isInteractiveCommand(c.pathKey)
    ).map((c) => c.pathKey);

    expect(machineNonInteractive).toContain('repo up');

    // The `rdc job` verbs are proxyable too: even `job logs --follow` streams to
    // stdout and ends on its own when the job finishes, so none of them needs a
    // TTY and a headless executor can drive all five.
    expect(machineNonInteractive).toContain('job logs');
    // The hidden `_refprobe run` P4 task-zero probe was retired by w2b (90 -> 89),
    // then `repo mount`/`repo unmount` folded into `repo up`/`repo down` (89 -> 87),
    // then the w2b cluster batch added `cluster snapshot create|list` (87 -> 89),
    // then the subscription flatten collapsed 5 machine-plane leaves into 2 (89 -> 85),
    // then the datastore family went from 5 facade leaves to 10 real ones (85 -> 90),
    // then `repo logs` + `repo exec` landed (90 -> 92). The `repo admin` subtree move
    // changes no count: the plane exceptions moved with their commands.
    //
    // 92 -> 89: `repo admin archive {list,restore,purge}` are config-plane, so a remote
    // executor can no longer be handed them. They were never machine commands — the
    // relocation out of the `config` noun silently gave them repo's machine default,
    // and this list is exactly the set the proxy will run remotely, which is why an
    // archive verb appearing in it was a wrong-target data-loss bug (§4.9).
    // 89 -> 90: `backup verify` is a machine-plane, non-interactive read (the
    // backup_verify verb runs on the machine that holds the anchor).
    // 90 -> 91: `backup snapshot` is machine-plane and non-interactive, so a
    // remote executor can run it, exactly like its `backup verify` sibling.
    // 91 -> 92: `backup browse` reads the repository IMAGE, which only exists on
    // the machine holding it, so it is machine-plane for the same reason
    // `backup verify` is. Note it is NOT `other` like `usage`/`manifests`: those
    // ask the account server, this one cannot be answered without the image.
    expect(machineNonInteractive.length).toBe(92);
  });

  it('plane and interactive entries all point at real commands', () => {
    const treePaths = allTreePaths();

    const stale = Object.keys(COMMAND_PLANES).filter((path) => !treePaths.has(path));

    if (stale.length > 0) {
      expect.fail(
        `COMMAND_PLANES entries that are not commands in the CLI tree: ${stale.join(', ')}`
      );
    }
  });
});

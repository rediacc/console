/**
 * CLI contract — the machine-readable description of the `rdc` command surface.
 *
 * Generated from the live Commander tree joined with COMMAND_METADATA, the
 * command registry, and the English i18n catalogue
 * (packages/cli/scripts/generate-cli-contract.ts). One contract drives three
 * consumers: the web console, the `rdc --proxy` thin client, and the executor.
 *
 * Entries are language-neutral apart from `label`, which carries the English
 * string so a consumer that never localises does not have to load a bundle.
 * Translations live in separate per-language bundles (see ./i18n) so a web
 * build does not embed all thirteen languages.
 */

/**
 * Where a command executes.
 *
 * - `machine`: reaches a customer machine (renet execute, SSH, SFTP, or cloud
 *   VM provisioning). Only these are candidates for remote execution.
 * - `config`: local CLI config and resource state only.
 * - `other`: local tooling (self-update, diagnostics, local dev VMs, the MCP
 *   server) and account-server HTTPS calls. An account-server call is not
 *   `machine`.
 */
export type CommandPlane = 'config' | 'machine' | 'other';

/** Timeout class carried over from the MCP annotations. */
export type TimeoutClass = 'read' | 'write';

/** Registry grouping used for help and navigation. */
export type CommandGroup =
  | 'INFRASTRUCTURE'
  | 'REPOSITORIES'
  | 'EXECUTION'
  | 'ORGANIZATION'
  | 'TOOLS';

/**
 * What a positional token names, so a consumer can bind a picker to it without
 * guessing from the argument's spelling.
 *
 * This is the load-bearing field of a positional. `repo-ref` means "this token
 * is a repository reference", which is what lets the console render a repo
 * picker for `rdc repo up <ref>` exactly as it renders one for `--repo`. The
 * generator derives it from the argument's name against the per-noun table in
 * the addressing grammar (docs/design/spec/03-cli-contracts.md §2.2); anything
 * it cannot classify is `plain`, an ordinary text token.
 */
export type PositionalKind =
  | 'repo-ref'
  | 'machine'
  | 'datastore-ref'
  | 'cluster'
  | 'storage'
  | 'strategy'
  | 'artifact-ref'
  | 'job-id'
  | 'target'
  | 'file'
  | 'plain';

/**
 * A positional argument of a command, e.g. the `<ref>` in `rdc repo up <ref>`.
 *
 * Positionals are serialised in DECLARED order (variadic last), between the
 * command path and its flags. A consumer rebuilds the argv a laptop would have
 * typed by emitting each value bare, in this order.
 */
export interface ContractPositional {
  /** Argument.name(), e.g. "ref". The form field key and the positionals-bag key. */
  name: string;
  /** What the token names, so a consumer can bind a picker without guessing. */
  kind: PositionalKind;
  /** `<ref>` (required) vs `[ref]` (optional). */
  required: boolean;
  /** `<refs...>`: collects the remaining tokens. */
  variadic: boolean;
  /** i18n key for the description, or null (see ContractOption.descriptionKey). */
  descriptionKey: string | null;
  /** English description, always present (may be empty). */
  label: string;
}

export interface ContractOption {
  /** Raw Commander flags string, e.g. "-m, --machine <machine>". */
  flags: string;
  /** Long flag without the leading dashes, e.g. "machine". */
  long: string;
  /** Short flag without the leading dash, e.g. "m". */
  short?: string;
  /** False for a boolean switch; true when the flag takes a value. */
  valueTaking: boolean;
  /** The flag may be repeated / collects multiple values. */
  variadic: boolean;
  /** Declared with requiredOption() — the CLI refuses to run without it. */
  mandatory: boolean;
  /** Serialised default, or null when there is none. */
  defaultValue: string | null;
  /**
   * The closed set of accepted values, when the option declared one via
   * Commander's `.choices()`. Absent for a free-form value, so a consumer can
   * render a hard Select exactly when this is present and a text input
   * otherwise. The CLI itself rejects an out-of-set value.
   */
  choices?: string[];
  /**
   * i18n key for the description, or null when the English string could not be
   * traced back to a key (a handful of factory-generated CRUD descriptions are
   * built at runtime and have no static key).
   */
  descriptionKey: string | null;
  /** English description, always present. */
  label: string;
}

export interface ContractCommand {
  /** Path segments, e.g. ["repo", "secret", "list"]. */
  path: string[];
  /** Space-joined path — the stable identity of a command, e.g. "repo secret list". */
  pathKey: string;
  /** Top-level command name, e.g. "repo". Always defined; group by this. */
  domain: string;
  /**
   * Registry grouping for the domain, or null when the domain has no registry
   * entry (today: `cluster` and `credits`).
   */
  group: CommandGroup | null;
  /** Hidden unless REDIACC_EXPERIMENTAL=1. */
  experimental: boolean;
  /** Where this command runs. */
  plane: CommandPlane;
  /** i18n key for the description, or null (see ContractOption.descriptionKey). */
  descriptionKey: string | null;
  /** English description, always present. */
  label: string;
  options: ContractOption[];
  /**
   * Positional arguments, in declared order. Empty for the options-only leaves
   * that make up most of the surface. A consumer serialises these bare, before
   * the flags, to rebuild the argv a laptop would have typed.
   */
  positionals: ContractPositional[];
  /**
   * True when this command also has subcommands — a runnable group such as
   * `repo replicate`. Its subcommands are separate entries.
   */
  hasSubcommands: boolean;

  // ── Policy and agent annotations (from COMMAND_METADATA) ────────────────
  /** Mutates state in a way that is not trivially undone. Undefined when unannotated. */
  destructive?: boolean;
  /** Re-running with the same arguments converges. Undefined when unannotated. */
  idempotent?: boolean;
  /** Timeout class from the MCP annotation. */
  timeout?: TimeoutClass;
  /** Resolved timeout in milliseconds, so a consumer need not duplicate the constants. */
  timeoutMs?: number;
  /** Name of the option that carries the repository, per the MCP annotation. */
  repoArg?: string;
  /** Blocks grand (non-fork) repos in agent mode. */
  grandGuard?: boolean;
  /** Nonsensical against a fork. */
  forkBlocked?: boolean;
  /** Never available to an agent, with no override. */
  agentBlocked?: boolean;
  /** Why this command is not exposed over MCP. */
  mcpExcludeReason?: string;

  // ── Execution capability ───────────────────────────────────────────────
  /**
   * Needs a TTY or never returns on its own (interactive shell, $EDITOR, a
   * tunnel or stream held until Ctrl+C, a browser callback).
   */
  interactive: boolean;
  /**
   * Safe to run through a remote executor on the operator's behalf. True only
   * when the command reaches a machine (`plane === 'machine'`), is not
   * interactive, and is not excluded because it does client-side file transfer
   * or because its effect lands in the caller's own config.
   *
   * This is the field the CLI's `--proxy` guard reads to refuse a command.
   */
  proxyCapable: boolean;
  /**
   * Why the command cannot be proxied, phrased for the operator. Present
   * exactly when `proxyCapable` is false, so a refusal always has a message.
   */
  proxyBlockedReason?: string;
  /**
   * Safe to run as a DETACHED renet job: start it under a transient unit and
   * follow its spool, so a dropped connection does not lose the work.
   *
   * Derived as `proxyCapable && domain !== 'job'` (minus a small exclusion
   * table): the classes proxyCapable already rules out are exactly the ones that
   * break under detach, and `rdc job *` manages jobs rather than doing machine
   * work, so detaching one is circular. The serve dispatch turns detach on for a
   * proxied command; `--background` turns it on for a local one.
   */
  detachable: boolean;

  // ── Resource binding (how a caller targets this command) ────────────────
  /**
   * Long flag naming the target machine, or null when the command takes none.
   * Resolved as: `--machine` when present; otherwise `--name` on the `machine`
   * domain, where the machine is named by --name.
   */
  machineOption: string | null;
  /**
   * Long flag naming the target repository, or null.
   * Resolved as: the MCP `repoArg` when annotated; otherwise `--repo` when
   * present; otherwise `--name` on the `repo` domain.
   */
  repoOption: string | null;
  /**
   * Name of the POSITIONAL that names the target machine, or null. The flag
   * binding (`machineOption`) and the positional binding are kept distinct so a
   * policy check can scope on whichever the caller actually used: a positional
   * value lives in the positionals bag, not in params, and reading only the flag
   * would silently unscope a positional-addressed command (a fail-open).
   */
  machinePositional: string | null;
  /**
   * Name of the POSITIONAL that names the target repository (a `repo-ref`
   * positional), or null. Kept distinct from `repoOption` for the same reason as
   * `machinePositional`.
   */
  repoPositional: string | null;
}

export interface CliContract {
  /** Injected at build time; 'dev' in a working tree (see CLI_CONTRACT_VERSION). */
  version: string;
  /** Languages with a bundle under ./data/i18n. */
  languages: string[];
  commands: ContractCommand[];
}

/** A flattened i18n bundle: key -> translated string. */
export type ContractStrings = Record<string, string>;

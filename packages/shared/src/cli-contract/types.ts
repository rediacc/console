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
  | 'provider'
  | 'plain';

/**
 * A kind of resource an option can be BOUND to, so a console can offer a picker
 * fed from the operator's decrypted config or a discovery command.
 *
 * This is a HINT, not a constraint. Unlike {@link ContractOption.choices} (a
 * HARD closed set the CLI itself rejects out-of-set values for), `kinds` says
 * "these are the resources this flag usually names" — the console renders a
 * pick-or-type combobox, never a blocking Select. A consumer MUST NOT promote
 * `kinds` to a hard constraint: an operator can always type a value the picker
 * did not list (a machine that is not yet in config, a fork tag typed by hand).
 *
 * The 12 kinds are the noun set the addressing grammar binds. Seven resolve
 * from config families (machine/repo/datastore/storage/cluster/provider/
 * strategy); five resolve by running a discovery command
 * (container/template/snapshot/job/artifact). The mapping lives in
 * {@link RESOURCE_DISCOVERY} (./discovery). There are deliberately NO
 * branch/commit kinds in v1.
 */
export type ResourceKind =
  | 'machine'
  | 'repo'
  | 'datastore'
  | 'storage'
  | 'cluster'
  | 'provider'
  | 'container'
  | 'template'
  | 'snapshot'
  | 'job'
  | 'strategy'
  | 'artifact';

/**
 * A rendering hint for a free-form option value, so a console can pick a control
 * (a stepper for `integer`, a masked/validated box for `cidr`) and validate
 * client-side. Purely cosmetic: the CLI does not enforce it, and an absent hint
 * means an ordinary text box. Distinct from {@link ContractOption.choices}
 * (a closed value set) and {@link ContractOption.kinds} (a resource binding).
 */
export type FormatHint =
  | 'size'
  | 'cron'
  | 'duration'
  | 'integer'
  | 'port'
  | 'path'
  | 'ip'
  | 'ipv4'
  | 'ipv6'
  | 'cidr'
  | 'domain'
  | 'url'
  | 'percent'
  | 'guid'
  | 'bandwidth';

/**
 * How prominent an option is in a rendered form. `common` options show by
 * default; `advanced` options fold behind a disclosure. Derived by the
 * generator (mandatory, resource-bound, or enum options are always `common`);
 * an override may never demote a mandatory option to `advanced`.
 */
export type OptionTier = 'common' | 'advanced';

/**
 * A worked example of a command, e.g. `rdc repo fork shop --tag test`.
 *
 * `command` is the full argv a laptop would type (concrete dummy values such as
 * `shop` / `prod-1`, never `<placeholders>`). `values` is that same example
 * parsed back into a field-name → value map by the generator, so a console can
 * offer click-to-fill: applying `values` to the form reproduces `command`. The
 * generator's parse doubles as a gate — an unknown flag, bad arity, or
 * out-of-choices value fails generation.
 */
export interface CommandExample {
  /** The full example argv, e.g. "rdc repo fork shop --tag test". */
  command: string;
  /** The example parsed into form field name → value, for click-to-fill. */
  values: Record<string, string>;
  /** i18n key for the one-line description of what the example does. */
  descriptionKey: string;
  /** English description, always present. */
  label: string;
}

/**
 * How a console should tabulate this command's `-o json` output: which column
 * identifies a row (so a click routes to a detail page) and the column order to
 * show. Present only on list-shaped commands; when present, BOTH fields are
 * required and `primaryKey` must be one of `columns`.
 */
export interface OutputHints {
  /** The column that identifies a row (a name or id). Must be in `columns`. */
  primaryKey: string;
  /** Column keys in display order. */
  columns: string[];
}

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
   * Resource kinds this option usually names, so a console can render a
   * pick-or-type combobox fed from config/discovery. A HINT, never a hard
   * constraint (see {@link ResourceKind}): free text is always allowed. Nonempty
   * when present, and only on a value-taking option. Absent for options that
   * name no resource.
   */
  kinds?: ResourceKind[];
  /**
   * Rendering hint for a free-form value (see {@link FormatHint}), so a console
   * can pick a control and validate client-side. Absent means a plain text box.
   */
  format?: FormatHint;
  /**
   * How prominent this option is in a rendered form (see {@link OptionTier}).
   * Always emitted by the generator.
   */
  tier: OptionTier;
  /**
   * The value is a secret (a token, a password). A console redacts it in run
   * history and masks the input. Absent means an ordinary value.
   */
  sensitive?: boolean;
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

  // ── Console affordances (examples, search, output shape) ────────────────
  /**
   * Worked examples of this command (see {@link CommandExample}), for the CLI
   * help "Examples:" block and console click-to-fill. Absent when the command
   * has no curated example.
   */
  examples?: CommandExample[];
  /**
   * Lowercase english search tokens for palette/command search, beyond the
   * words already in the path and label. Untranslated by design (the palette
   * scores against the operator's typing, which is language-neutral for CLI
   * nouns). Absent when the command needs no extra tokens.
   */
  keywords?: string[];
  /**
   * How a console should tabulate this command's list output (see
   * {@link OutputHints}). Present only on list-shaped commands.
   */
  output?: OutputHints;

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

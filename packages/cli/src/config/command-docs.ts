/**
 * Curated per-command documentation registries: worked examples, palette
 * search keywords, and list-output tabulation hints. A separate module from
 * COMMAND_METADATA (which is at its max-lines budget) — this file is pure
 * data with NO imports, so the contract generator AND the repo-root
 * scripts/validate-cli-examples.ts can both load it without dragging in the
 * CLI. Keep it dependency-free.
 *
 * Every registry is keyed by a command's pathKey (e.g. "repo fork"). The
 * generator gates every key against the live tree — a stale key fails the
 * regen loudly. Curation rules per registry:
 *
 * COMMAND_EXAMPLES — ~35 high-traffic commands, 1-3 examples each.
 *   - `command`: the full line a laptop would type, positional-ref syntax,
 *     CONCRETE dummy values (shop, prod-1, test) — never `<placeholders>`.
 *   - `descriptionKey`: `commands.<path>.examples.<slug>`; the English string
 *     MUST exist in i18n/locales/en/cli.json (the generator resolves the label
 *     from it and fails when missing). The key shape makes the strings flow
 *     into the per-language contract bundles automatically.
 *   - The generator parses each command against the command's own declared
 *     positionals/options to derive the click-to-fill `values` map; an unknown
 *     flag, bad arity, out-of-choices value, missing mandatory option, or
 *     missing required positional fails the regen.
 *
 * COMMAND_KEYWORDS — 3-8 lowercase english tokens per command, beyond the
 *   words already in the path and label. Untranslated by design (the palette
 *   scores against the operator's typing, which is language-neutral for CLI
 *   nouns). Gated: lowercase ascii ([a-z][a-z0-9-]*).
 *
 * COMMAND_OUTPUT_HINTS — the ~17 list-shaped commands. `columns` must be read
 *   from the command's REAL `-o json` output implementation (never guessed),
 *   in display order; `primaryKey` is the column that identifies a row and
 *   must be one of `columns` (gated).
 */

/** A worked example: the command line plus the i18n key of its description. */
export interface CommandExampleDef {
  /** Full example line, e.g. "rdc repo fork shop --tag test". */
  command: string;
  /** i18n key following `commands.<path>.examples.<slug>`. */
  descriptionKey: string;
}

/** Tabulation hint for a list command's `-o json` output. */
export interface CommandOutputHintDef {
  /** The column that identifies a row (a name or id). Must be in `columns`. */
  primaryKey: string;
  /** Column keys in display order, read from the real output implementation. */
  columns: readonly string[];
}

export const COMMAND_EXAMPLES: Record<string, readonly CommandExampleDef[]> = {
  // ── repo lifecycle ───────────────────────────────────────────────────────
  'repo up': [
    { command: 'rdc repo up shop', descriptionKey: 'commands.repo.up.examples.basic' },
    { command: 'rdc repo up --all -m prod-1', descriptionKey: 'commands.repo.up.examples.all' },
  ],
  'repo down': [
    { command: 'rdc repo down shop', descriptionKey: 'commands.repo.down.examples.basic' },
    {
      command: 'rdc repo down shop --unmount',
      descriptionKey: 'commands.repo.down.examples.unmount',
    },
  ],
  'repo create': [
    {
      command: 'rdc repo create shop -m prod-1',
      descriptionKey: 'commands.repo.create.examples.basic',
    },
    {
      command: 'rdc repo create shop -m prod-1 --size 5G',
      descriptionKey: 'commands.repo.create.examples.sized',
    },
  ],
  'repo fork': [
    {
      command: 'rdc repo fork shop --tag test',
      descriptionKey: 'commands.repo.fork.examples.basic',
    },
    {
      command: 'rdc repo fork shop --tag staging --up',
      descriptionKey: 'commands.repo.fork.examples.andStart',
    },
  ],
  'repo delete': [
    { command: 'rdc repo delete shop', descriptionKey: 'commands.repo.delete.examples.basic' },
    { command: 'rdc repo delete shop:test', descriptionKey: 'commands.repo.delete.examples.fork' },
  ],
  'repo promote': [
    {
      command: 'rdc repo promote shop:test',
      descriptionKey: 'commands.repo.promote.examples.basic',
    },
    {
      command: 'rdc repo promote shop:test --yes',
      descriptionKey: 'commands.repo.promote.examples.noConfirm',
    },
  ],
  'repo list': [
    { command: 'rdc repo list -m prod-1', descriptionKey: 'commands.repo.list.examples.basic' },
    {
      command: 'rdc repo list --datastore data-1',
      descriptionKey: 'commands.repo.list.examples.byDatastore',
    },
  ],
  // The storage examples are gone with the arm they demonstrated. An example is
  // the most load-bearing documentation there is: the backup-restore tutorial
  // ran `rdc repo push my-app --to my-storage` straight out of this list and
  // failed 14 seconds into a CI job.
  'repo push': [
    {
      command: 'rdc repo push shop --to-machine server-1',
      descriptionKey: 'commands.repo.push.examples.toMachine',
    },
  ],
  'repo pull': [
    {
      command: 'rdc repo pull shop --from-machine server-1',
      descriptionKey: 'commands.repo.pull.examples.basic',
    },
    {
      command: 'rdc repo pull shop --from-machine server-1 --up',
      descriptionKey: 'commands.repo.pull.examples.andStart',
    },
  ],
  'repo migrate': [
    {
      command: 'rdc repo migrate shop --to server-1',
      descriptionKey: 'commands.repo.migrate.examples.basic',
    },
    {
      command: 'rdc repo migrate shop --to server-1 --strategy physical',
      descriptionKey: 'commands.repo.migrate.examples.strategy',
    },
  ],
  'repo logs': [
    { command: 'rdc repo logs shop', descriptionKey: 'commands.repo.logs.examples.basic' },
    {
      command: 'rdc repo logs shop -c web --lines 50',
      descriptionKey: 'commands.repo.logs.examples.container',
    },
  ],
  'repo exec': [
    {
      command: 'rdc repo exec shop -c web whoami',
      descriptionKey: 'commands.repo.exec.examples.basic',
    },
    {
      command: 'rdc repo exec shop -c web -i bash',
      descriptionKey: 'commands.repo.exec.examples.interactive',
    },
    {
      command: 'rdc repo exec shop -c web -- ls -la /var/log',
      descriptionKey: 'commands.repo.exec.examples.separator',
    },
  ],
  'repo cat': [
    {
      command: 'rdc repo cat shop --remote-file etc/config.toml',
      descriptionKey: 'commands.repo.cat.examples.basic',
    },
  ],
  'repo sync upload': [
    {
      command: 'rdc repo sync upload shop --local ./site',
      descriptionKey: 'commands.repo.sync.upload.examples.dir',
    },
    {
      command: 'rdc repo sync upload shop --local ./config.toml --remote-file etc/config.toml',
      descriptionKey: 'commands.repo.sync.upload.examples.file',
    },
  ],
  'repo sync download': [
    {
      command: 'rdc repo sync download shop --local ./backup',
      descriptionKey: 'commands.repo.sync.download.examples.dir',
    },
    {
      command: 'rdc repo sync download shop --local ./out --remote-file etc/config.toml',
      descriptionKey: 'commands.repo.sync.download.examples.file',
    },
  ],
  'repo secret set': [
    {
      command: 'rdc repo secret set shop --key API_TOKEN --value s3cr3t',
      descriptionKey: 'commands.repo.secret.set.examples.basic',
    },
    {
      command: 'rdc repo secret set shop --key DB_PASSWORD --value hunter2 --mode env',
      descriptionKey: 'commands.repo.secret.set.examples.envMode',
    },
  ],
  'repo secret get': [
    {
      command: 'rdc repo secret get shop --key API_TOKEN',
      descriptionKey: 'commands.repo.secret.get.examples.basic',
    },
  ],
  // ── machine ──────────────────────────────────────────────────────────────
  'machine add': [
    {
      command: 'rdc machine add prod-1 --ip 203.0.113.10 --user root',
      descriptionKey: 'commands.machine.add.examples.basic',
    },
    {
      command: 'rdc machine add prod-1 --ip 203.0.113.10 --user admin --port 2222',
      descriptionKey: 'commands.machine.add.examples.customPort',
    },
  ],
  'machine list': [
    { command: 'rdc machine list', descriptionKey: 'commands.machine.list.examples.basic' },
    {
      command: 'rdc machine list --sort name',
      descriptionKey: 'commands.machine.list.examples.sorted',
    },
  ],
  'machine status': [
    {
      command: 'rdc machine status prod-1',
      descriptionKey: 'commands.machine.status.examples.basic',
    },
    {
      command: 'rdc machine status prod-1 --containers',
      descriptionKey: 'commands.machine.status.examples.containers',
    },
  ],
  'machine provision': [
    {
      command: 'rdc machine provision prod-1 --provider hetzner',
      descriptionKey: 'commands.machine.provision.examples.basic',
    },
    {
      command: 'rdc machine provision prod-1 --provider hetzner --region fsn1 --type cx22',
      descriptionKey: 'commands.machine.provision.examples.sized',
    },
  ],
  // ── backup ───────────────────────────────────────────────────────────────
  'backup run': [
    {
      command: 'rdc backup run nightly -m prod-1',
      descriptionKey: 'commands.backup.run.examples.basic',
    },
  ],
  'backup list': [
    { command: 'rdc backup list -m prod-1', descriptionKey: 'commands.backup.list.examples.basic' },
    {
      command: 'rdc backup list -m prod-1 --path hot',
      descriptionKey: 'commands.backup.list.examples.byPath',
    },
  ],
  'backup restore': [
    {
      command: 'rdc backup restore shop -m prod-1',
      descriptionKey: 'commands.backup.restore.examples.basic',
    },
    {
      command: 'rdc backup restore shop --as shop-restored -m prod-1 --up',
      descriptionKey: 'commands.backup.restore.examples.asNewRepo',
    },
  ],
  'backup strategy set': [
    {
      command: 'rdc backup strategy set nightly --storage backups-s3 --mode hot',
      descriptionKey: 'commands.backup.strategy.set.examples.configure',
    },
    {
      command: 'rdc backup strategy set nightly --disable',
      descriptionKey: 'commands.backup.strategy.set.examples.disable',
    },
  ],
  // ── datastore ────────────────────────────────────────────────────────────
  'datastore create': [
    {
      command: 'rdc datastore create data-1 -m prod-1 --size 50G',
      descriptionKey: 'commands.datastore.create.examples.basic',
    },
    {
      command: 'rdc datastore create pool-a -m prod-1 --size 100G --backend rbd',
      descriptionKey: 'commands.datastore.create.examples.ceph',
    },
  ],
  'datastore attach': [
    {
      command: 'rdc datastore attach data-1 --to prod-1',
      descriptionKey: 'commands.datastore.attach.examples.basic',
    },
    {
      command: 'rdc datastore attach data-1 --to prod-1 --writes ceph',
      descriptionKey: 'commands.datastore.attach.examples.cephWrites',
    },
  ],
  'datastore fork': [
    {
      command: 'rdc datastore fork data-1 --tag test',
      descriptionKey: 'commands.datastore.fork.examples.basic',
    },
    {
      command: 'rdc datastore fork data-1 --tag test --attach-to prod-1',
      descriptionKey: 'commands.datastore.fork.examples.andAttach',
    },
  ],
  'datastore list': [
    { command: 'rdc datastore list', descriptionKey: 'commands.datastore.list.examples.basic' },
    {
      command: 'rdc datastore list prod-1',
      descriptionKey: 'commands.datastore.list.examples.byPlace',
    },
  ],
  // ── cluster ──────────────────────────────────────────────────────────────
  'cluster create': [
    {
      command: 'rdc cluster create k8s-main --provider hetzner',
      descriptionKey: 'commands.cluster.create.examples.basic',
    },
    {
      command: 'rdc cluster create k8s-main --declare-only --control-node prod-1',
      descriptionKey: 'commands.cluster.create.examples.declareOnly',
    },
  ],
  'cluster fork': [
    {
      command: 'rdc cluster fork k8s-main --tag test --to k8s-copy',
      descriptionKey: 'commands.cluster.fork.examples.basic',
    },
    {
      command: 'rdc cluster fork k8s-main --tag staging --to k8s-stage --up',
      descriptionKey: 'commands.cluster.fork.examples.andStart',
    },
  ],
  'cluster join': [
    {
      command: 'rdc cluster join server-2 --cluster k8s-main',
      descriptionKey: 'commands.cluster.join.examples.basic',
    },
  ],
  // ── access ───────────────────────────────────────────────────────────────
  'term connect': [
    {
      command: 'rdc term connect prod-1',
      descriptionKey: 'commands.term.connect.examples.machine',
    },
    { command: 'rdc term connect shop', descriptionKey: 'commands.term.connect.examples.repo' },
    {
      command: 'rdc term connect prod-1 -c uptime',
      descriptionKey: 'commands.term.connect.examples.runCommand',
    },
  ],
  'vscode connect': [
    {
      command: 'rdc vscode connect shop',
      descriptionKey: 'commands.vscode.connect.examples.basic',
    },
    {
      command: 'rdc vscode connect shop -f /workspace',
      descriptionKey: 'commands.vscode.connect.examples.folder',
    },
  ],
  // ── jobs ─────────────────────────────────────────────────────────────────
  'job list': [
    { command: 'rdc job list -m prod-1', descriptionKey: 'commands.job.list.examples.basic' },
  ],
  'job status': [
    {
      command: 'rdc job status 12345 -m prod-1',
      descriptionKey: 'commands.job.status.examples.basic',
    },
  ],
  'job logs': [
    { command: 'rdc job logs 12345 -m prod-1', descriptionKey: 'commands.job.logs.examples.basic' },
    {
      command: 'rdc job logs 12345 -m prod-1 --follow',
      descriptionKey: 'commands.job.logs.examples.follow',
    },
  ],
  'job cancel': [
    {
      command: 'rdc job cancel 12345 -m prod-1',
      descriptionKey: 'commands.job.cancel.examples.basic',
    },
  ],
  // ── config / server / storage ────────────────────────────────────────────
  'config init': [
    {
      command: 'rdc config init production',
      descriptionKey: 'commands.config.init.examples.basic',
    },
    {
      command: 'rdc config init staging --server https://eu.rediacc.com',
      descriptionKey: 'commands.config.init.examples.withServer',
    },
  ],
  serve: [
    { command: 'rdc serve', descriptionKey: 'commands.serve.examples.basic' },
    { command: 'rdc serve --port 8080', descriptionKey: 'commands.serve.examples.customPort' },
    { command: 'rdc serve --mode container', descriptionKey: 'commands.serve.examples.container' },
  ],
  'storage add': [
    {
      command: 'rdc storage add backups-s3 --vault \'{"type":"s3"}\'',
      descriptionKey: 'commands.storage.add.examples.basic',
    },
  ],
};

export const COMMAND_KEYWORDS: Record<string, readonly string[]> = {
  // ── repo lifecycle ───────────────────────────────────────────────────────
  'repo up': ['deploy', 'start', 'boot', 'launch', 'compose'],
  'repo down': ['stop', 'halt', 'teardown', 'shutdown'],
  'repo create': ['new', 'init', 'provision'],
  'repo fork': ['clone', 'cow', 'branch', 'copy', 'snapshot'],
  'repo delete': ['remove', 'rm', 'destroy', 'teardown'],
  'repo list': ['ls', 'repos', 'inventory'],
  'repo push': ['upload', 'backup', 'replicate', 'send'],
  'repo pull': ['download', 'fetch', 'restore', 'retrieve'],
  'repo migrate': ['move', 'relocate', 'transfer', 'cutover'],
  'repo diff': ['compare', 'delta', 'changes'],
  'repo promote': ['publish', 'finalize', 'graduate', 'merge'],
  'repo logs': ['log', 'tail', 'output', 'container'],
  'repo exec': ['run', 'shell', 'command', 'container'],
  'repo cat': ['read', 'view', 'print', 'file', 'show'],
  'repo sync upload': ['push', 'copy', 'rsync', 'files'],
  'repo sync download': ['pull', 'fetch', 'rsync', 'files'],
  'repo secret set': ['env', 'credential', 'password', 'store'],
  'repo secret get': ['env', 'credential', 'read', 'reveal'],
  // ── machine ──────────────────────────────────────────────────────────────
  'machine add': ['register', 'host', 'server', 'node'],
  'machine remove': ['delete', 'rm', 'deregister', 'unregister'],
  'machine list': ['ls', 'hosts', 'servers', 'inventory', 'nodes'],
  'machine status': ['info', 'health', 'inspect', 'overview'],
  'machine provision': ['create', 'vm', 'cloud', 'spinup', 'tofu'],
  // ── backup ───────────────────────────────────────────────────────────────
  'backup run': ['execute', 'snapshot', 'save', 'trigger'],
  'backup list': ['ls', 'snapshots', 'archives', 'restores'],
  'backup restore': ['recover', 'download', 'rollback'],
  'backup strategy set': ['schedule', 'policy', 'configure', 'cron'],
  // ── datastore ────────────────────────────────────────────────────────────
  'datastore create': ['new', 'pool', 'volume', 'storage'],
  'datastore attach': ['mount', 'connect', 'bind'],
  'datastore fork': ['clone', 'cow', 'snapshot', 'copy'],
  'datastore list': ['ls', 'pools', 'volumes', 'datastores'],
  // ── cluster ──────────────────────────────────────────────────────────────
  'cluster create': ['new', 'k8s', 'kubernetes', 'provision'],
  'cluster fork': ['clone', 'cow', 'copy', 'k8s'],
  'cluster join': ['add', 'enroll', 'node', 'member', 'k8s'],
  // ── access ───────────────────────────────────────────────────────────────
  'term connect': ['ssh', 'shell', 'terminal', 'console', 'login'],
  'vscode connect': ['code', 'editor', 'ide', 'remote', 'tunnel'],
  // ── jobs ─────────────────────────────────────────────────────────────────
  'job list': ['ls', 'jobs', 'tasks', 'queue'],
  'job status': ['info', 'state', 'progress', 'inspect'],
  'job logs': ['log', 'tail', 'output'],
  'job cancel': ['kill', 'stop', 'abort', 'terminate'],
  // ── config / server / storage / diagnostics ──────────────────────────────
  'config init': ['setup', 'create', 'configure', 'profile'],
  serve: ['server', 'daemon', 'executor', 'host', 'api'],
  'storage add': ['register', 's3', 'bucket', 'endpoint', 'remote'],
  doctor: ['diagnose', 'check', 'troubleshoot', 'health'],
  update: ['upgrade', 'version', 'self-update'],
};

export const COMMAND_OUTPUT_HINTS: Record<string, CommandOutputHintDef> = {
  'job list': {
    primaryKey: 'id',
    columns: ['id', 'state', 'function', 'repo', 'started', 'duration'],
  },
  'machine list': {
    primaryKey: 'name',
    columns: ['name', 'ip', 'user', 'port', 'datastore'],
  },
  'machine provider list': {
    primaryKey: 'name',
    columns: ['name', 'provider', 'region', 'instanceType', 'sshUser'],
  },
  'repo list': {
    primaryKey: 'name',
    columns: [
      'name',
      'tag',
      'type',
      'size',
      'mounted',
      'docker',
      'containers',
      'services',
      'modified',
    ],
  },
  'repo secret list': {
    primaryKey: 'key',
    columns: ['key', 'mode'],
  },
  'repo admin archive list': {
    primaryKey: 'name',
    columns: ['name', 'tag', 'guid', 'credential', 'deletedAt'],
  },
  'repo admin autostart list': {
    primaryKey: 'repository',
    columns: ['repository', 'guid', 'enabled', 'onDisk'],
  },
  'backup list': {
    primaryKey: 'name',
    columns: ['mode', 'name', 'guid', 'size', 'modified'],
  },
  'datastore list': {
    primaryKey: 'name',
    columns: ['name', 'backend', 'size', 'cluster', 'attachedTo', 'writes', 'repos'],
  },
  'storage list': {
    primaryKey: 'name',
    columns: ['name', 'provider'],
  },
  'config list': {
    primaryKey: 'name',
    columns: ['name', 'active', 'machines', 'status'],
  },
  'config field list': {
    primaryKey: 'pointer',
    columns: ['pointer', 'kind', 'redactAs', 'commit', 'encryptAtRest'],
  },
  // SKIPPED (non-tabular / unstable output — deliberately no hint):
  //   backup strategy list        — free-text `info` lines, not a table
  //   repo admin template list    — padded `info` lines, not a table
  //   vscode list                 — custom connection renderer, not `-o json`
  //   datastore snapshot list     — prints raw renet JSON verbatim
  //   cluster snapshot list       — prints the raw snapshot array verbatim
};

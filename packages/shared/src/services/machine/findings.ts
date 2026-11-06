/**
 * The findings table (D-remedy, X1): every issue `rdc machine health` and `rdc repo health` can raise carries a
 * machine-readable code, a severity, a subject and, where a fix exists, `fix {action, class, window_only}`. This
 * table is the one source the CLI, the local refresher and the docs read: a code's fix lives here and nowhere else.
 *
 * Safety classes:
 * - `auto-safe`: restart a stuck container, trim, prune anonymous dangling volumes and unused images (hub excluded),
 *   restart Traefik, write the ACME anchor. `rdc machine repair` runs these by default.
 * - `auto-with-backup`: runs only with `--with-backup`, after a successful snapshot of the affected repository.
 * - `operator-only`: never run by any tool; printed as the exact command for the operator.
 * `window_only` is an attribute on top of the class: such a fix runs only inside the machine's `maintenance_window`.
 */

/** How serious a finding is; each maps to the exit code of `machine health` (info 0, warning 1, error 2, critical 3). */
export type FindingSeverity = 'info' | 'warning' | 'error' | 'critical';

/** The safety class of a fix. */
export type FixClass = 'auto-safe' | 'auto-with-backup' | 'operator-only';

/** What a fix does; `rdc machine repair` maps each action to one renet call, or prints it for the operator. */
export type FixAction =
  | 'trim-prune'
  | 'restart-container'
  | 'restart-service'
  | 'restart-repo-supervisors'
  | 'restart-traefik'
  | 'acme-anchor'
  | 'repo-repair'
  | 'repo-up'
  | 'run-backup'
  | 'bind-backup-strategy'
  | 'license-refresh'
  | 'machine-setup'
  | 'redeploy-ops-health';

export interface FindingFix {
  action: FixAction;
  class: FixClass;
  window_only: boolean;
}

/** What a fix acts on beyond the subject: the repository GUID, its network id, a container or a systemd unit. */
export interface FindingTarget {
  repository?: string;
  networkId?: number;
  container?: string;
  unit?: string;
}

/** One coded finding. `fix` comes from the table (withFix); `target` names what the fix acts on. */
export interface HealthFinding {
  code: string;
  severity: FindingSeverity;
  subject: string;
  detail: string;
  fix?: FindingFix;
  target?: FindingTarget;
}

const fix = (action: FixAction, cls: FixClass, windowOnly = false): FindingFix => ({
  action,
  class: cls,
  window_only: windowOnly,
});

/** One row of the table: a one-line description (docs) and the fix, when one exists. */
export interface FindingRow {
  description: string;
  fix?: FindingFix;
}

/**
 * Every finding code, its description and its fix. A code a producer raises that is missing here is a defect, which
 * the findings test catches by walking every producer.
 */
export const FINDING_TABLE = {
  'machine.status.unavailable': { description: 'the machine returned no status listing' },
  'memory.usage.high': { description: 'memory use above 80% (error above 90%)' },
  'disk.usage.high': { description: 'system disk use above 85% (error above 95%)' },
  'datastore.usage.high': {
    description:
      'datastore use above 85% (error above 95%); the residual after trim and prune (named volumes, archives) is the operator’s',
    fix: fix('trim-prune', 'auto-safe'),
  },
  'repo.disk.high': {
    description: 'a repository filesystem above 85% (error above 95%)',
    fix: fix('trim-prune', 'auto-safe'),
  },
  'repo.unmounted': {
    description: 'an autostart repository is not mounted',
    fix: fix('repo-up', 'operator-only'),
  },
  'container.unhealthy': {
    description: 'a container reports unhealthy',
    fix: fix('restart-container', 'auto-safe'),
  },
  'container.restart-loop': {
    description: 'a container is in a Restarting loop',
    fix: fix('restart-container', 'auto-safe'),
  },
  'container.health-streak': { description: 'a container health check keeps failing' },
  'service.failed': {
    description: 'a systemd service failed',
    fix: fix('restart-service', 'operator-only'),
  },
  'service.restart-loop': {
    description: 'a systemd service keeps restarting',
    fix: fix('restart-service', 'operator-only'),
  },
  'storage.smart.failing': { description: 'a disk reports a SMART failure' },
  'storage.temperature.high': { description: 'a disk runs above 60 °C' },
  'backup.stale': {
    description: 'repositories not backed up in over 10 days',
    fix: fix('run-backup', 'operator-only'),
  },
  'backup.never': {
    description: 'repositories skipped and never backed up',
    fix: fix('run-backup', 'operator-only'),
  },
  'backup.schedule.behind': {
    description: 'repositories last backed up more than twice their schedule interval ago',
    fix: fix('run-backup', 'operator-only'),
  },
  'backup.target.missed': {
    description: 'repositories behind their declared backup target',
    fix: fix('run-backup', 'operator-only'),
  },
  'backup.target.missed-latest': {
    description: 'repositories whose latest backup run missed its target',
  },
  'backup.verify.failed': { description: 'repositories whose last backup verify failed' },
  'backup.coverage.absent': {
    description: 'no backup coverage is recorded for an autostart repository',
    fix: fix('bind-backup-strategy', 'operator-only'),
  },
  'license.refresh-due': {
    description: 'repository licenses inside their refresh window',
    fix: fix('license-refresh', 'operator-only'),
  },
  'license.expired': {
    description: 'repository licenses expired',
    fix: fix('license-refresh', 'operator-only'),
  },
  'license.machine-mismatch': {
    description: 'repository licenses issued for another machine',
    fix: fix('license-refresh', 'operator-only'),
  },
  'license.invalid-signature': { description: 'repository licenses with an invalid signature' },
  'license.missing': {
    description: 'repository licenses missing',
    fix: fix('license-refresh', 'operator-only'),
  },
  'renet.binary.replaced': {
    description: 'renet processes run a replaced binary',
    fix: fix('restart-repo-supervisors', 'auto-safe', true),
  },
  'renet.repo-health.unsupported': {
    description: 'the machine’s renet predates repository health checks',
    fix: fix('machine-setup', 'operator-only'),
  },
  'repo.health.warning': {
    description: 'a repository health() reported a warning',
    fix: fix('repo-repair', 'auto-safe'),
  },
  'repo.health.error': {
    description: 'a repository health() reported an error',
    fix: fix('repo-repair', 'auto-safe'),
  },
  'repo.health.failed': { description: 'the repository health checks could not run' },
  'cert.expiry.near': {
    description: 'a proxy certificate expires in under 21 days (error under 7)',
    fix: fix('restart-traefik', 'auto-safe'),
  },
  'cert.store.unreadable': { description: 'the proxy certificate store could not be read' },
  'acme.challenge.cname-shared': {
    description: 'ACME challenge names share a CNAME end, so their renewals collide',
    fix: fix('acme-anchor', 'auto-safe'),
  },
  'acme.challenge.unknown': {
    description:
      'the ACME challenge chain of a certificate name could not be resolved, so the shared-CNAME check is unknown',
  },
  'ops.targets.drift': {
    description: 'the ops-health Worker runs a target list other than the ops repository’s file',
    fix: fix('redeploy-ops-health', 'operator-only'),
  },
} as const satisfies Record<string, FindingRow>;

export type FindingCode = keyof typeof FINDING_TABLE;

/** Whether a code is in the table. */
export function isKnownFindingCode(code: string): code is FindingCode {
  return Object.hasOwn(FINDING_TABLE, code);
}

/**
 * The finding with its fix from the table. A repo's `repo-repair` runs only the repair() functions whose declared
 * class the caller allows; renet enforces that per Rediaccfile, so the table's `auto-safe` admits the action, not
 * every function behind it.
 */
export function withFix(finding: HealthFinding): HealthFinding {
  if (!isKnownFindingCode(finding.code)) return finding;
  const row: FindingRow = FINDING_TABLE[finding.code];
  return row.fix ? { ...finding, fix: { ...row.fix } } : finding;
}

const SEVERITY_EXIT: Readonly<Record<FindingSeverity, number>> = {
  info: 0,
  warning: 1,
  error: 2,
  critical: 3,
};

/** The `machine health` exit code a severity raises. */
export function severityExitCode(severity: FindingSeverity): number {
  return SEVERITY_EXIT[severity];
}

/** The severity of an exit code a usage or health check raises (1 warning, 2 error, 3 critical). */
export function severityOfExit(exitCode: number): FindingSeverity {
  if (exitCode >= 3) return 'critical';
  if (exitCode === 2) return 'error';
  if (exitCode === 1) return 'warning';
  return 'info';
}

const OPERATOR_COMMANDS: Readonly<
  Partial<Record<FixAction, (f: HealthFinding, machine: string) => string>>
> = {
  'repo-up': (f, m) => `rdc repo up ${f.subject}@${m}`,
  'restart-service': (f, m) =>
    `rdc term connect -m ${m} -c 'sudo systemctl restart ${f.target?.unit ?? f.subject}'`,
  'run-backup': (_f, m) => `rdc backup status -m ${m}`,
  'bind-backup-strategy': (_f, m) => `rdc backup strategy bind <strategy> -m ${m}`,
  'license-refresh': (_f, m) => `rdc subscription refresh -m ${m}`,
  'machine-setup': (_f, m) => `rdc machine setup ${m}`,
  'redeploy-ops-health': () => 'PYTHONPATH=.ci python3 -m rediacc_ci.ops.deploy_ops_health',
};

/** The exact command an operator runs for a finding's fix, or undefined when it has no fix. */
export function operatorCommand(finding: HealthFinding, machine: string): string | undefined {
  const action = finding.fix?.action;
  if (!action) return undefined;
  const build = OPERATOR_COMMANDS[action];
  return build ? build(finding, machine) : `rdc machine repair ${machine} --code ${finding.code}`;
}

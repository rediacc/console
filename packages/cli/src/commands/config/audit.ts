/**
 * `rdc config audit {log, tail, verify}` — inspect the append-only
 * hash-chained audit log at `<configdir>/audit.log.jsonl`.
 */

import { createReadStream, watchFile, unwatchFile, existsSync, statSync } from 'node:fs';
import { createInterface } from 'node:readline';
import type { Command } from 'commander';
import { t } from '../../i18n/index.js';
import { outputService } from '../../services/output.js';
import { readAuditLog, verifyChain, type AuditEntry } from '../../services/audit-log.js';
import { handleError } from '../../utils/errors.js';

function auditLogPath(): string {
  const xdg = process.env.XDG_CONFIG_HOME ?? `${process.env.HOME ?? ''}/.config`;
  return `${xdg}/rediacc/audit.log.jsonl`;
}

/** Parse relative time strings like "24h", "7d", "30m" to a cutoff epoch ms. */
// Regex /^(\d+)([hdm])$/ guarantees match[2] is always one of these keys.
const UNIT_MS = new Map<string, number>([
  ['h', 3_600_000],
  ['d', 86_400_000],
  ['m', 60_000],
]);

function parseSince(value: string): number | null {
  const match = /^(\d+)([hdm])$/.exec(value.trim());
  if (match) {
    const n = Number.parseInt(match[1], 10);
    // Regex guarantees match[2] is h/d/m; safe cast.
    const mult = UNIT_MS.get(match[2]) as number;
    return Date.now() - n * mult;
  }
  const iso = Date.parse(value);
  return Number.isNaN(iso) ? null : iso;
}

function matchesPath(entry: AuditEntry, glob: string | undefined): boolean {
  if (!glob) return true;
  if (entry.paths.length === 0) return false;
  // Support simple `*` wildcard per segment, matching metaForPointer behavior.
  const parts = glob.split('/');
  return entry.paths.some((p) => {
    const ps = p.split('/');
    if (ps.length !== parts.length) return false;
    return parts.every((seg, i) => seg === '*' || seg === ps[i]);
  });
}

export function registerAuditCommands(parent: Command, _program: Command): void {
  const audit = parent.command('audit').description(t('commands.config.audit.description'));

  audit
    .command('log')
    .description(t('commands.config.audit.log.description'))
    .option('--since <spec>', t('commands.config.audit.log.optionSince'))
    .option('--path <glob>', t('commands.config.audit.log.optionPath'))
    .option('--actor <kind>', t('commands.config.audit.log.optionActor'))
    .action((options: { since?: string; path?: string; actor?: string }) => {
      try {
        const path = auditLogPath();
        const entries = readAuditLog(path);
        const sinceMs = options.since ? parseSince(options.since) : null;
        const filtered = entries.filter((e) => {
          if (sinceMs !== null && Date.parse(e.ts) < sinceMs) return false;
          if (options.actor && e.actor.kind !== options.actor) return false;
          if (!matchesPath(e, options.path)) return false;
          return true;
        });
        outputService.print(filtered, 'json');
      } catch (error) {
        handleError(error);
      }
    });

  audit
    .command('tail')
    .description(t('commands.config.audit.tail.description'))
    .action(() => {
      const path = auditLogPath();
      if (!existsSync(path)) {
        process.stderr.write(`Audit log not found: ${path}\n`);
        process.exit(1);
      }
      // Print existing entries first, then stream new ones.
      const existing = readAuditLog(path);
      for (const entry of existing) {
        process.stdout.write(`${JSON.stringify(entry)}\n`);
      }
      // watchFile polls mtime; good enough for a user-facing tail command.
      let lastSize = existsSync(path) ? statSync(path).size : 0;
      watchFile(path, { interval: 500 }, (curr) => {
        if (curr.size > lastSize) {
          const stream = createReadStream(path, { start: lastSize, end: curr.size });
          const rl = createInterface({ input: stream });
          rl.on('line', (line) => {
            if (line.trim()) process.stdout.write(`${line}\n`);
          });
          lastSize = curr.size;
        }
      });
      process.on('SIGINT', () => {
        unwatchFile(path);
        process.exit(0);
      });
    });

  audit
    .command('verify')
    .description(t('commands.config.audit.verify.description'))
    .action(() => {
      try {
        const path = auditLogPath();
        const broken = verifyChain(path);
        const entries = readAuditLog(path);
        if (broken === null) {
          outputService.success(
            t('commands.config.audit.verify.chainOk', { count: entries.length })
          );
        } else {
          outputService.error(t('commands.config.audit.verify.chainBroken', { line: broken }));
          process.exit(1);
        }
      } catch (error) {
        handleError(error);
      }
    });
}

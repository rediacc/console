/**
 * Reader and classifier for `scripts/data/domains.json`.
 *
 * The partition is the deliverable that lets W9's domain moves and W7's `.ci`
 * relocation land without colliding (driver contract section 5d). A JSON file
 * nobody executes is a document, not a partition, so this module makes it
 * answerable: given a repository-relative path, which domain owns it, and where
 * does that domain say it belongs.
 *
 * THE MATCHER IS DELIBERATELY TINY. Three constructs, no dependency:
 *
 *   `**`  any number of path segments, including zero
 *   `*`   any run of characters within ONE segment
 *   everything else is literal
 *
 * A bigger glob dialect would be a second thing to be wrong about. The whole
 * partition is 20 rules, and `.ci/scripts/ci/*.cjs` plus `scripts/check-*.ts`
 * is the entire vocabulary it needs.
 *
 * FIRST MATCH WINS, and order is semantics. That is the same contract
 * `.ci/scripts/ci/scope-map.cjs` runs under, and driver contract section 3 says
 * so explicitly for that file: one writer at a time, and every mover states
 * where its rule sits. Inserting a rule in the middle silently re-homes
 * everything below it that the new rule also matches.
 */

import fs from 'node:fs';

import { repoPath } from './repo-root.js';

export interface DomainRule {
  id: string;
  paths: string[];
  home: string;
  stays: boolean;
  why: string;
  owner?: string;
  mergeInto?: string;
  blockedOn?: string;
  breaksIfMoved?: string[];
  consumers?: string[];
  exceptions?: string[];
  notes?: string[];
}

export interface DomainPartition {
  version: number;
  onUnclassified: string;
  rules: DomainRule[];
  openQuestions?: string[];
}

/** Where the partition lives. One constant, so a move is one edit. */
export const DOMAINS_PATH = repoPath('scripts', 'data', 'domains.json');

/**
 * Compile one pattern to an anchored regular expression.
 *
 * `**` is consumed before `*` so that `a/**` does not degrade into two
 * single-segment stars, which would stop it matching nested paths.
 */
function compile(pattern: string): RegExp {
  let out = '';
  for (let i = 0; i < pattern.length; i++) {
    const ch = pattern[i];
    if (ch === '*' && pattern[i + 1] === '*') {
      // `**` at a segment boundary swallows the following slash too, so that
      // `scripts/lib/**` matches `scripts/lib/a.ts` and not just `scripts/lib/`.
      out += '.*';
      i++;
      if (pattern[i + 1] === '/') i++;
      continue;
    }
    if (ch === '*') {
      out += '[^/]*';
      continue;
    }
    out += ch.replace(/[.+?^${}()|[\]\\]/g, '\\$&');
  }
  return new RegExp(`^${out}$`);
}

/** Load and validate the partition. */
export function loadPartition(file: string = DOMAINS_PATH): DomainPartition {
  const raw = JSON.parse(fs.readFileSync(file, 'utf-8')) as DomainPartition;
  if (!Array.isArray(raw.rules) || raw.rules.length === 0) {
    throw new Error(`${file}: no rules. An empty partition classifies nothing and would pass.`);
  }
  const seen = new Set<string>();
  for (const rule of raw.rules) {
    if (seen.has(rule.id)) {
      throw new Error(`${file}: duplicate rule id "${rule.id}". Ids name the domain in reports.`);
    }
    seen.add(rule.id);
    if (!Array.isArray(rule.paths) || rule.paths.length === 0) {
      throw new Error(`${file}: rule "${rule.id}" matches nothing.`);
    }
    if (typeof rule.why !== 'string' || rule.why.trim() === '') {
      throw new Error(
        `${file}: rule "${rule.id}" has no \`why\`. A home nobody justified is a home the ` +
          'next session will move back.'
      );
    }
  }
  return raw;
}

export interface Classification {
  /** The owning rule, or null when nothing matched. */
  rule: DomainRule | null;
  /** Where the file belongs. Null when unclassified. */
  home: string | null;
  /** True when the file is already where its rule says it belongs. */
  inPlace: boolean;
}

/**
 * Classify one repository-relative path.
 *
 * A path matching no rule returns `rule: null`, which the layout gate treats as
 * RED with the file named. That default is the reason the partition survives
 * files added after it was written: forgetting to declare a new family is loud,
 * where a permissive default would be silent.
 */
export function classify(partition: DomainPartition, relPath: string): Classification {
  for (const rule of partition.rules) {
    if (!rule.paths.some((p) => compile(p).test(relPath))) continue;
    const dir = relPath.includes('/') ? relPath.slice(0, relPath.lastIndexOf('/')) : '';
    const inPlace = dir === rule.home || dir.startsWith(`${rule.home}/`);
    return { rule, home: rule.home, inPlace };
  }
  return { rule: null, home: null, inPlace: false };
}
